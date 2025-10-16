"""
Metrics handler module for orchestrating AFS data collection and transformation.

This module provides the MetricsHandler class that coordinates data fetching
from AFS API, transformation to Prometheus metrics, and caching for concurrent
request handling.
"""

import time
import threading
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.afs_client import AFSClient
from src.metrics_transformer import MetricsTransformer
from src.config import Config, VolumeConfig
from src.data_models import PrometheusMetric
from src.exceptions import AuthenticationError, APIError, PartialCollectionError
from src.logging_config import get_logger, log_operation


@dataclass
class CachedMetrics:
    """Container for cached metrics data."""
    metrics: List[PrometheusMetric]
    timestamp: float
    collection_duration: float


@dataclass
class VolumeCollectionResult:
    """Result of collecting metrics from a single volume."""
    volume_id: str
    zone: str
    success: bool
    metrics: List[PrometheusMetric]
    error: Optional[str] = None
    duration: float = 0.0


class MetricsHandler:
    """
    Orchestrates AFS data collection and transformation with caching support.
    
    This class handles:
    - Concurrent data collection from multiple AFS volumes
    - Brief caching to handle concurrent scrape requests
    - Partial failure handling for individual volumes
    - Collection metadata generation
    """
    
    def __init__(self, config: Config, afs_client: AFSClient, transformer: MetricsTransformer):
        """
        Initialize the metrics handler.
        
        Args:
            config: Configuration object
            afs_client: AFS API client instance
            transformer: Metrics transformer instance
        """
        self.config = config
        self.afs_client = afs_client
        self.transformer = transformer
        self.logger = get_logger(__name__)
        
        # Cache for handling concurrent requests
        self._cache: Optional[CachedMetrics] = None
        self._cache_lock = threading.RLock()
        self._collection_lock = threading.RLock()
        
        # Collection statistics
        self._last_collection_time: Optional[float] = None
        self._collection_count = 0
    
    def collect_metrics(self) -> Tuple[List[PrometheusMetric], float]:
        """
        Collect metrics from all configured AFS volumes.
        
        Uses caching to handle concurrent requests efficiently. If cached data
        is available and fresh, returns it immediately. Otherwise, performs
        a new collection.
        
        Returns:
            Tuple of (metrics list, collection duration in seconds)
        """
        collection_config = self.config.get_collection_config()
        
        # Check cache first
        with self._cache_lock:
            if self._cache and self._is_cache_valid():
                self.logger.debug("Returning cached metrics")
                return self._cache.metrics, self._cache.collection_duration
        
        # Perform new collection (with lock to prevent concurrent collections)
        with self._collection_lock:
            # Double-check cache after acquiring collection lock
            with self._cache_lock:
                if self._cache and self._is_cache_valid():
                    self.logger.debug("Returning cached metrics (double-check)")
                    return self._cache.metrics, self._cache.collection_duration
            
            # Perform actual collection
            self.logger.set_context(operation='collect_metrics', collection_id=self._collection_count + 1)
            
            start_time = time.time()
            try:
                with log_operation(self.logger, "metrics collection", level='INFO'):
                    # Collect from all volumes
                    all_metrics = self._fetch_all_volumes()
                    
                    # Add collection metadata
                    collection_duration = time.time() - start_time
                    metadata_metrics = self._create_collection_metadata(collection_duration)
                    all_metrics.extend(metadata_metrics)
                    
                    # Update cache
                    with self._cache_lock:
                        self._cache = CachedMetrics(
                            metrics=all_metrics,
                            timestamp=time.time(),
                            collection_duration=collection_duration
                        )
                    
                    self._last_collection_time = time.time()
                    self._collection_count += 1
                    
                    self.logger.info(f"Collected {len(all_metrics)} metrics from {len(self.config.get_afs_config().volumes)} volumes")
                    
                    return all_metrics, collection_duration
                    
            except Exception as e:
                self.logger.error(f"Metrics collection failed: {str(e)[:200]}")
                # Return error metrics
                error_metrics = self._create_error_metrics(str(e))
                collection_duration = time.time() - start_time
                return error_metrics, collection_duration
                
            finally:
                self.logger.clear_context()
    
    def _is_cache_valid(self) -> bool:
        """
        Check if cached metrics are still valid.
        
        Returns:
            True if cache is valid and fresh
        """
        if not self._cache:
            return False
        
        collection_config = self.config.get_collection_config()
        cache_age = time.time() - self._cache.timestamp
        
        return cache_age < collection_config.cache_duration
    
    def _fetch_all_volumes(self) -> List[PrometheusMetric]:
        """
        Fetch metrics from all configured AFS volumes.
        
        Uses concurrent execution to collect from multiple volumes in parallel.
        Handles partial failures gracefully.
        
        Returns:
            List of PrometheusMetric objects from all successful collections
        """
        afs_config = self.config.get_afs_config()
        collection_config = self.config.get_collection_config()
        
        all_metrics = []
        collection_results = []
        
        # Use ThreadPoolExecutor for concurrent collection
        max_workers = min(len(afs_config.volumes), 5)  # Limit concurrent requests
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit collection tasks for all volumes
            future_to_volume = {
                executor.submit(
                    self._collect_volume_metrics,
                    volume_config,
                    collection_config.timeout_seconds
                ): volume_config
                for volume_config in afs_config.volumes
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_volume):
                volume_config = future_to_volume[future]
                
                try:
                    result = future.result()
                    collection_results.append(result)
                    
                    if result.success:
                        all_metrics.extend(result.metrics)
                        self.logger.debug(f"Successfully collected {len(result.metrics)} metrics "
                                        f"from volume {result.volume_id} in {result.duration:.3f}s")
                    else:
                        self.logger.error(f"Failed to collect metrics from volume {result.volume_id}: "
                                        f"{result.error}")
                        
                except Exception as e:
                    error_msg = str(e)[:200]
                    self.logger.error(f"Unexpected error collecting from volume "
                                    f"{volume_config.volume_id}: {error_msg}")
                    collection_results.append(VolumeCollectionResult(
                        volume_id=volume_config.volume_id,
                        zone=volume_config.zone,
                        success=False,
                        metrics=[],
                        error=error_msg
                    ))
        
        # Add per-volume collection status metrics
        status_metrics = self._create_volume_status_metrics(collection_results)
        all_metrics.extend(status_metrics)
        
        # Check for partial failures
        failed_results = [r for r in collection_results if not r.success]
        if failed_results:
            failed_volumes = [f"{r.volume_id}@{r.zone}" for r in failed_results]
            self.logger.warning(f"Partial collection failure: {len(failed_results)}/{len(collection_results)} volumes failed")
            
            # If all volumes failed, raise an exception
            if len(failed_results) == len(collection_results):
                raise PartialCollectionError(
                    f"All {len(failed_results)} volumes failed during collection",
                    failed_volumes=failed_volumes
                )
        
        return all_metrics
    
    def _collect_volume_metrics(self, volume_config: VolumeConfig, timeout: int) -> VolumeCollectionResult:
        """
        Collect metrics from a single AFS volume.
        
        Args:
            volume_config: Volume configuration
            timeout: Request timeout in seconds
            
        Returns:
            VolumeCollectionResult with collection outcome
        """
        # Set context for this volume collection
        volume_logger = get_logger(f"{__name__}.volume_collection")
        volume_logger.set_context(
            volume_id=volume_config.volume_id,
            zone=volume_config.zone,
            operation='collect_volume_metrics'
        )
        
        start_time = time.time()
        
        try:
            with log_operation(volume_logger, f"volume {volume_config.volume_id} collection", level='DEBUG'):
                # Fetch quota data from AFS API
                quota_data = self.afs_client.get_volume_quotas(
                    volume_id=volume_config.volume_id,
                    zone=volume_config.zone,
                    timeout=timeout
                )
                
                # Transform to Prometheus metrics
                metrics = self.transformer.transform_quota_data(
                    quota_data=quota_data,
                    volume_id=volume_config.volume_id,
                    zone=volume_config.zone
                )
                
                duration = time.time() - start_time
                volume_logger.info(f"Successfully collected {len(metrics)} metrics")
                
                return VolumeCollectionResult(
                    volume_id=volume_config.volume_id,
                    zone=volume_config.zone,
                    success=True,
                    metrics=metrics,
                    duration=duration
                )
                
        except (AuthenticationError, APIError) as e:
            duration = time.time() - start_time
            error_msg = str(e)[:200]
            
            volume_logger.error(f"Collection failed: {error_msg}")
            
            return VolumeCollectionResult(
                volume_id=volume_config.volume_id,
                zone=volume_config.zone,
                success=False,
                metrics=[],
                error=error_msg,
                duration=duration
            )
            
        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"Unexpected error: {str(e)[:200]}"
            
            volume_logger.error(f"Unexpected collection error: {str(e)[:200]}")
            
            return VolumeCollectionResult(
                volume_id=volume_config.volume_id,
                zone=volume_config.zone,
                success=False,
                metrics=[],
                error=error_msg,
                duration=duration
            )
            
        finally:
            volume_logger.clear_context()
    
    def _create_volume_status_metrics(self, results: List[VolumeCollectionResult]) -> List[PrometheusMetric]:
        """
        Create metrics indicating the success/failure status of volume collections.
        
        Args:
            results: List of collection results for all volumes
            
        Returns:
            List of PrometheusMetric objects for collection status
        """
        status_metrics = []
        successful_count = 0
        failed_count = 0
        total_duration = 0.0
        
        for result in results:
            # Track overall statistics
            if result.success:
                successful_count += 1
            else:
                failed_count += 1
            total_duration += result.duration
            
            # Collection success metric (1 for success, 0 for failure)
            status_metrics.append(PrometheusMetric(
                name='afs_collection_success',
                value=1.0 if result.success else 0.0,
                labels={
                    'volume_id': result.volume_id,
                    'zone': result.zone
                },
                help_text='Success indicator for volume collection (1=success, 0=failure)',
                metric_type='gauge'
            ))
            
            # Collection duration metric
            status_metrics.append(PrometheusMetric(
                name='afs_collection_duration_seconds',
                value=result.duration,
                labels={
                    'volume_id': result.volume_id,
                    'zone': result.zone
                },
                help_text='Duration of volume collection in seconds',
                metric_type='gauge'
            ))
            
            # Metrics count per volume (only for successful collections)
            if result.success:
                status_metrics.append(PrometheusMetric(
                    name='afs_volume_metrics_count',
                    value=float(len(result.metrics)),
                    labels={
                        'volume_id': result.volume_id,
                        'zone': result.zone
                    },
                    help_text='Number of metrics collected from this volume',
                    metric_type='gauge'
                ))
            
            # Error metric (only if there was an error)
            if not result.success and result.error:
                # Categorize error type for better monitoring
                error_category = "unknown"
                if "timeout" in result.error.lower():
                    error_category = "timeout"
                elif "connection" in result.error.lower():
                    error_category = "connection"
                elif "authentication" in result.error.lower():
                    error_category = "authentication"
                elif "rate limit" in result.error.lower():
                    error_category = "rate_limit"
                elif any(code in result.error for code in ["404", "500", "502", "503"]):
                    error_category = "api_error"
                
                status_metrics.append(PrometheusMetric(
                    name='afs_collection_error',
                    value=1.0,
                    labels={
                        'volume_id': result.volume_id,
                        'zone': result.zone,
                        'error_category': error_category,
                        'error_message': result.error[:100]  # Truncate long error messages
                    },
                    help_text='Indicates an error occurred during volume collection',
                    metric_type='gauge'
                ))
        
        # Add aggregate metrics
        total_volumes = len(results)
        if total_volumes > 0:
            status_metrics.extend([
                PrometheusMetric(
                    name='afs_collection_success_rate',
                    value=successful_count / total_volumes,
                    labels={},
                    help_text='Success rate of volume collections (0.0 to 1.0)',
                    metric_type='gauge'
                ),
                PrometheusMetric(
                    name='afs_collection_volumes_successful',
                    value=float(successful_count),
                    labels={},
                    help_text='Number of volumes successfully collected',
                    metric_type='gauge'
                ),
                PrometheusMetric(
                    name='afs_collection_volumes_failed',
                    value=float(failed_count),
                    labels={},
                    help_text='Number of volumes that failed collection',
                    metric_type='gauge'
                ),
                PrometheusMetric(
                    name='afs_collection_volumes_total',
                    value=float(total_volumes),
                    labels={},
                    help_text='Total number of volumes attempted',
                    metric_type='gauge'
                ),
                PrometheusMetric(
                    name='afs_collection_average_duration_seconds',
                    value=total_duration / total_volumes,
                    labels={},
                    help_text='Average collection duration per volume in seconds',
                    metric_type='gauge'
                )
            ])
        
        return status_metrics
    
    def _create_collection_metadata(self, duration: float) -> List[PrometheusMetric]:
        """
        Create metadata metrics about the overall collection process.
        
        Args:
            duration: Total collection duration in seconds
            
        Returns:
            List of PrometheusMetric objects for collection metadata
        """
        metadata_metrics = []
        current_time = time.time()
        
        # Total scrape duration
        metadata_metrics.append(PrometheusMetric(
            name='afs_scrape_duration_seconds',
            value=duration,
            labels={},
            help_text='Total duration of the metrics scrape in seconds',
            metric_type='gauge'
        ))
        
        # Scrape timestamp
        metadata_metrics.append(PrometheusMetric(
            name='afs_scrape_timestamp',
            value=current_time,
            labels={},
            help_text='Unix timestamp of the last successful scrape',
            metric_type='gauge'
        ))
        
        # Collection count
        metadata_metrics.append(PrometheusMetric(
            name='afs_collection_total',
            value=float(self._collection_count),
            labels={},
            help_text='Total number of collection cycles performed',
            metric_type='counter'
        ))
        
        # Configured volumes count
        afs_config = self.config.get_afs_config()
        metadata_metrics.append(PrometheusMetric(
            name='afs_configured_volumes',
            value=float(len(afs_config.volumes)),
            labels={},
            help_text='Number of configured AFS volumes',
            metric_type='gauge'
        ))
        
        # Cache status metrics
        cache_status = self.get_cache_status()
        metadata_metrics.append(PrometheusMetric(
            name='afs_cache_hit',
            value=1.0 if cache_status['cached'] else 0.0,
            labels={},
            help_text='Whether the last scrape used cached data (1=cached, 0=fresh)',
            metric_type='gauge'
        ))
        
        if cache_status['cached']:
            metadata_metrics.append(PrometheusMetric(
                name='afs_cache_age_seconds',
                value=cache_status['cache_age'],
                labels={},
                help_text='Age of cached data in seconds',
                metric_type='gauge'
            ))
        
        # Collection performance metrics
        if self._last_collection_time:
            time_since_last = current_time - self._last_collection_time
            metadata_metrics.append(PrometheusMetric(
                name='afs_time_since_last_collection_seconds',
                value=time_since_last,
                labels={},
                help_text='Time since last collection in seconds',
                metric_type='gauge'
            ))
        
        # Configuration metadata
        collection_config = self.config.get_collection_config()
        metadata_metrics.extend([
            PrometheusMetric(
                name='afs_config_max_retries',
                value=float(collection_config.max_retries),
                labels={},
                help_text='Configured maximum retry attempts',
                metric_type='gauge'
            ),
            PrometheusMetric(
                name='afs_config_timeout_seconds',
                value=float(collection_config.timeout_seconds),
                labels={},
                help_text='Configured collection timeout in seconds',
                metric_type='gauge'
            ),
            PrometheusMetric(
                name='afs_config_cache_duration_seconds',
                value=float(collection_config.cache_duration),
                labels={},
                help_text='Configured cache duration in seconds',
                metric_type='gauge'
            )
        ])
        
        # Circuit breaker status (if available)
        if hasattr(self.afs_client, 'retry_handler'):
            cb_status = self.afs_client.retry_handler.get_circuit_breaker_status()
            for cb_name, status in cb_status.items():
                metadata_metrics.extend([
                    PrometheusMetric(
                        name='afs_circuit_breaker_state',
                        value=1.0 if status['state'] == 'closed' else 0.0,
                        labels={'circuit_breaker': cb_name, 'state': status['state']},
                        help_text='Circuit breaker state (1=closed/healthy, 0=open/failing)',
                        metric_type='gauge'
                    ),
                    PrometheusMetric(
                        name='afs_circuit_breaker_failures',
                        value=float(status['failure_count']),
                        labels={'circuit_breaker': cb_name},
                        help_text='Number of failures recorded by circuit breaker',
                        metric_type='gauge'
                    )
                ])
        
        return metadata_metrics
    
    def _create_error_metrics(self, error_message: str) -> List[PrometheusMetric]:
        """
        Create error metrics when collection fails completely.
        
        Args:
            error_message: Error description
            
        Returns:
            List of PrometheusMetric objects for error reporting
        """
        error_metrics = []
        
        # General collection error
        error_metrics.append(PrometheusMetric(
            name='afs_collection_error',
            value=1.0,
            labels={'error': error_message[:100]},  # Truncate long error messages
            help_text='Indicates an error occurred during metrics collection',
            metric_type='gauge'
        ))
        
        # Scrape timestamp (even for failed scrapes)
        error_metrics.append(PrometheusMetric(
            name='afs_scrape_timestamp',
            value=time.time(),
            labels={},
            help_text='Unix timestamp of the last scrape attempt',
            metric_type='gauge'
        ))
        
        return error_metrics
    
    def clear_cache(self) -> None:
        """Clear the metrics cache to force fresh collection."""
        with self._cache_lock:
            self._cache = None
            self.logger.debug("Metrics cache cleared")
    
    def get_cache_status(self) -> Dict[str, any]:
        """
        Get information about the current cache status.
        
        Returns:
            Dictionary with cache status information
        """
        with self._cache_lock:
            if not self._cache:
                return {
                    'cached': False,
                    'cache_age': None,
                    'metrics_count': 0,
                    'collection_duration': None
                }
            
            cache_age = time.time() - self._cache.timestamp
            collection_config = self.config.get_collection_config()
            
            return {
                'cached': True,
                'cache_age': cache_age,
                'cache_valid': cache_age < collection_config.cache_duration,
                'metrics_count': len(self._cache.metrics),
                'collection_duration': self._cache.collection_duration,
                'cache_duration_limit': collection_config.cache_duration
            }
    
    def get_collection_stats(self) -> Dict[str, any]:
        """
        Get statistics about collection performance.
        
        Returns:
            Dictionary with collection statistics
        """
        return {
            'total_collections': self._collection_count,
            'last_collection_time': self._last_collection_time,
            'cache_status': self.get_cache_status()
        }