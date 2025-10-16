"""
Performance and load tests for AFS Prometheus metrics system.

This module tests server performance under concurrent scrape requests,
memory usage during long-running operations, and behavior with large
numbers of directories.
"""

import pytest
import time
import threading
import psutil
import os
import gc
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import Mock, patch, MagicMock
from typing import List, Dict, Any
import requests

from src.config import Config, AFSConfig, VolumeConfig, ServerConfig, CollectionConfig, LoggingConfig
from src.afs_client import AFSClient
from src.metrics_transformer import MetricsTransformer
from src.metrics_handler import MetricsHandler
from src.http_server import MetricsServer
from src.data_models import PrometheusMetric, AFSQuotaData
from src.retry_handler import create_retry_config


class PerformanceTestHelper:
    """Helper class for performance testing utilities."""
    
    @staticmethod
    def get_memory_usage() -> Dict[str, float]:
        """Get current memory usage statistics."""
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        return {
            'rss_mb': memory_info.rss / 1024 / 1024,  # Resident Set Size in MB
            'vms_mb': memory_info.vms / 1024 / 1024,  # Virtual Memory Size in MB
            'percent': process.memory_percent()
        }
    
    @staticmethod
    def create_large_afs_response(num_directories: int = 1000) -> Dict[str, Any]:
        """Create a large AFS response with many directories for testing."""
        dir_quota_list = []
        
        for i in range(num_directories):
            dir_quota_list.append({
                "volume_id": f"volume-{i % 10}",  # 10 different volumes
                "dir_path": f"/data/directory_{i:06d}",
                "file_quantity_quota": 1000000 if i % 5 == 0 else 0,  # 20% have quotas
                "file_quantity_used_quota": 50000 + (i * 100),
                "capacity_quota": 1073741824000 if i % 5 == 0 else 0,  # 1TB quota for 20%
                "capacity_used_quota": 536870912000 + (i * 1000000),  # ~500GB + variation
                "state": 1
            })
        
        return {"dir_quota_list": dir_quota_list}
    
    @staticmethod
    def create_test_config(num_volumes: int = 3) -> Config:
        """Create a test configuration with specified number of volumes."""
        config = Config()
        
        volumes = []
        for i in range(num_volumes):
            volumes.append(VolumeConfig(
                volume_id=f"test-volume-{i}",
                zone=f"test-zone-{i}"
            ))
        
        config.afs = AFSConfig(
            access_key="test_access_key",
            secret_key="test_secret_key",
            base_url="https://test.example.com",
            volumes=volumes
        )
        
        config.server = ServerConfig(
            host="127.0.0.1",
            port=8080,
            request_timeout=30
        )
        
        config.collection = CollectionConfig(
            max_retries=3,
            retry_delay=1,  # Faster for testing
            timeout_seconds=25,
            cache_duration=5  # Shorter cache for testing
        )
        
        config.logging = LoggingConfig(
            level="WARNING",  # Reduce logging noise during performance tests
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        
        return config


class TestConcurrentRequests:
    """Test server performance under concurrent scrape requests."""
    
    @pytest.fixture
    def performance_config(self):
        """Create configuration optimized for performance testing."""
        return PerformanceTestHelper.create_test_config(num_volumes=5)
    
    @pytest.fixture
    def mock_afs_response(self):
        """Create a realistic AFS response for performance testing."""
        return PerformanceTestHelper.create_large_afs_response(num_directories=100)
    
    def test_concurrent_metrics_requests_light_load(self, performance_config, mock_afs_response):
        """Test server performance with light concurrent load (10 requests)."""
        with patch('requests.get') as mock_get:
            # Configure mock response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_afs_response
            mock_get.return_value = mock_response
            
            # Create server components
            retry_config = create_retry_config(max_attempts=3, base_delay=1.0, max_delay=10.0)
            afs_client = AFSClient(
                access_key=performance_config.afs.access_key,
                secret_key=performance_config.afs.secret_key,
                base_url=performance_config.afs.base_url,
                retry_config=retry_config
            )
            
            transformer = MetricsTransformer()
            metrics_handler = MetricsHandler(performance_config, afs_client, transformer)
            server = MetricsServer(performance_config, metrics_handler)
            
            # Create test client
            app = server.get_app()
            app.config['TESTING'] = True
            
            # Performance tracking
            results = []
            errors = []
            start_memory = PerformanceTestHelper.get_memory_usage()
            
            def make_request(request_id: int):
                """Make a single request and track performance."""
                try:
                    start_time = time.time()
                    with app.test_client() as client:
                        response = client.get('/metrics')
                        duration = time.time() - start_time
                        
                        results.append({
                            'request_id': request_id,
                            'status_code': response.status_code,
                            'duration': duration,
                            'content_length': len(response.data),
                            'timestamp': start_time
                        })
                except Exception as e:
                    errors.append(f"Request {request_id}: {str(e)}")
            
            # Execute concurrent requests
            num_requests = 10
            start_time = time.time()
            
            with ThreadPoolExecutor(max_workers=num_requests) as executor:
                futures = [executor.submit(make_request, i) for i in range(num_requests)]
                for future in as_completed(futures):
                    future.result()  # Wait for completion
            
            total_duration = time.time() - start_time
            end_memory = PerformanceTestHelper.get_memory_usage()
            
            # Verify results
            assert len(errors) == 0, f"Errors occurred: {errors}"
            assert len(results) == num_requests
            
            # Performance assertions
            successful_requests = [r for r in results if r['status_code'] == 200]
            assert len(successful_requests) == num_requests, "All requests should succeed"
            
            # Response time assertions
            response_times = [r['duration'] for r in successful_requests]
            avg_response_time = sum(response_times) / len(response_times)
            max_response_time = max(response_times)
            
            assert avg_response_time < 2.0, f"Average response time too high: {avg_response_time:.3f}s"
            assert max_response_time < 5.0, f"Max response time too high: {max_response_time:.3f}s"
            
            # Throughput assertion
            requests_per_second = num_requests / total_duration
            assert requests_per_second > 2.0, f"Throughput too low: {requests_per_second:.2f} req/s"
            
            # Memory usage assertion (should not increase significantly)
            memory_increase = end_memory['rss_mb'] - start_memory['rss_mb']
            assert memory_increase < 50, f"Memory usage increased too much: {memory_increase:.2f} MB"
            
            # Verify caching effectiveness (should reduce API calls)
            # With 5 volumes and caching, we should see fewer API calls than total requests
            assert mock_get.call_count <= num_requests, "Caching should reduce API calls"
    
    def test_concurrent_metrics_requests_heavy_load(self, performance_config, mock_afs_response):
        """Test server performance with heavy concurrent load (50 requests)."""
        with patch('requests.get') as mock_get:
            # Configure mock response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_afs_response
            mock_get.return_value = mock_response
            
            # Create server components
            retry_config = create_retry_config(max_attempts=3, base_delay=1.0, max_delay=10.0)
            afs_client = AFSClient(
                access_key=performance_config.afs.access_key,
                secret_key=performance_config.afs.secret_key,
                base_url=performance_config.afs.base_url,
                retry_config=retry_config
            )
            
            transformer = MetricsTransformer()
            metrics_handler = MetricsHandler(performance_config, afs_client, transformer)
            server = MetricsServer(performance_config, metrics_handler)
            
            # Create test client
            app = server.get_app()
            app.config['TESTING'] = True
            
            # Performance tracking
            results = []
            errors = []
            start_memory = PerformanceTestHelper.get_memory_usage()
            
            def make_request(request_id: int):
                """Make a single request and track performance."""
                try:
                    start_time = time.time()
                    with app.test_client() as client:
                        response = client.get('/metrics')
                        duration = time.time() - start_time
                        
                        results.append({
                            'request_id': request_id,
                            'status_code': response.status_code,
                            'duration': duration,
                            'content_length': len(response.data),
                            'timestamp': start_time
                        })
                except Exception as e:
                    errors.append(f"Request {request_id}: {str(e)}")
            
            # Execute concurrent requests
            num_requests = 50
            max_workers = 20  # Limit concurrent workers
            start_time = time.time()
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(make_request, i) for i in range(num_requests)]
                for future in as_completed(futures):
                    future.result()  # Wait for completion
            
            total_duration = time.time() - start_time
            end_memory = PerformanceTestHelper.get_memory_usage()
            
            # Verify results
            assert len(errors) == 0, f"Errors occurred: {errors}"
            assert len(results) == num_requests
            
            # Performance assertions
            successful_requests = [r for r in results if r['status_code'] == 200]
            assert len(successful_requests) == num_requests, "All requests should succeed"
            
            # Response time assertions (more lenient for heavy load)
            response_times = [r['duration'] for r in successful_requests]
            avg_response_time = sum(response_times) / len(response_times)
            max_response_time = max(response_times)
            p95_response_time = sorted(response_times)[int(0.95 * len(response_times))]
            
            assert avg_response_time < 5.0, f"Average response time too high: {avg_response_time:.3f}s"
            assert p95_response_time < 10.0, f"95th percentile response time too high: {p95_response_time:.3f}s"
            assert max_response_time < 15.0, f"Max response time too high: {max_response_time:.3f}s"
            
            # Throughput assertion
            requests_per_second = num_requests / total_duration
            assert requests_per_second > 1.0, f"Throughput too low: {requests_per_second:.2f} req/s"
            
            # Memory usage assertion
            memory_increase = end_memory['rss_mb'] - start_memory['rss_mb']
            assert memory_increase < 100, f"Memory usage increased too much: {memory_increase:.2f} MB"
    
    def test_sustained_concurrent_load(self, performance_config):
        """Test server performance under sustained concurrent load over time."""
        # Create a smaller response for sustained testing
        small_response = PerformanceTestHelper.create_large_afs_response(num_directories=50)
        
        with patch('requests.get') as mock_get:
            # Configure mock response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = small_response
            mock_get.return_value = mock_response
            
            # Create server components
            retry_config = create_retry_config(max_attempts=3, base_delay=1.0, max_delay=10.0)
            afs_client = AFSClient(
                access_key=performance_config.afs.access_key,
                secret_key=performance_config.afs.secret_key,
                base_url=performance_config.afs.base_url,
                retry_config=retry_config
            )
            
            transformer = MetricsTransformer()
            metrics_handler = MetricsHandler(performance_config, afs_client, transformer)
            server = MetricsServer(performance_config, metrics_handler)
            
            # Create test client
            app = server.get_app()
            app.config['TESTING'] = True
            
            # Performance tracking
            all_results = []
            all_errors = []
            memory_samples = []
            
            def make_requests_batch(batch_id: int, num_requests: int = 10):
                """Make a batch of requests."""
                batch_results = []
                batch_errors = []
                
                for i in range(num_requests):
                    try:
                        start_time = time.time()
                        with app.test_client() as client:
                            response = client.get('/metrics')
                            duration = time.time() - start_time
                            
                            batch_results.append({
                                'batch_id': batch_id,
                                'request_id': i,
                                'status_code': response.status_code,
                                'duration': duration,
                                'content_length': len(response.data),
                                'timestamp': start_time
                            })
                    except Exception as e:
                        batch_errors.append(f"Batch {batch_id}, Request {i}: {str(e)}")
                
                return batch_results, batch_errors
            
            # Run sustained load test
            start_memory = PerformanceTestHelper.get_memory_usage()
            memory_samples.append(('start', start_memory))
            
            num_batches = 5
            batch_interval = 2  # seconds between batches
            
            for batch_id in range(num_batches):
                batch_start = time.time()
                
                # Execute batch
                batch_results, batch_errors = make_requests_batch(batch_id)
                all_results.extend(batch_results)
                all_errors.extend(batch_errors)
                
                # Sample memory usage
                current_memory = PerformanceTestHelper.get_memory_usage()
                memory_samples.append((f'batch_{batch_id}', current_memory))
                
                # Wait before next batch (except for last batch)
                if batch_id < num_batches - 1:
                    elapsed = time.time() - batch_start
                    sleep_time = max(0, batch_interval - elapsed)
                    if sleep_time > 0:
                        time.sleep(sleep_time)
            
            end_memory = PerformanceTestHelper.get_memory_usage()
            memory_samples.append(('end', end_memory))
            
            # Verify results
            assert len(all_errors) == 0, f"Errors occurred: {all_errors}"
            assert len(all_results) == num_batches * 10
            
            # Performance assertions
            successful_requests = [r for r in all_results if r['status_code'] == 200]
            assert len(successful_requests) == len(all_results), "All requests should succeed"
            
            # Check response time consistency across batches
            batch_avg_times = {}
            for batch_id in range(num_batches):
                batch_requests = [r for r in all_results if r['batch_id'] == batch_id]
                batch_times = [r['duration'] for r in batch_requests]
                batch_avg_times[batch_id] = sum(batch_times) / len(batch_times)
            
            # Response times should remain consistent (no significant degradation)
            first_batch_avg = batch_avg_times[0]
            last_batch_avg = batch_avg_times[num_batches - 1]
            degradation_ratio = last_batch_avg / first_batch_avg
            
            assert degradation_ratio < 2.0, f"Response time degraded too much: {degradation_ratio:.2f}x"
            
            # Memory usage should remain stable
            memory_increases = []
            for i, (label, memory) in enumerate(memory_samples[1:], 1):
                prev_memory = memory_samples[i-1][1]
                increase = memory['rss_mb'] - prev_memory['rss_mb']
                memory_increases.append(increase)
            
            total_memory_increase = end_memory['rss_mb'] - start_memory['rss_mb']
            assert total_memory_increase < 100, f"Total memory increase too high: {total_memory_increase:.2f} MB"


class TestMemoryUsage:
    """Test memory usage during long-running operations."""
    
    def test_memory_usage_large_response(self):
        """Test memory usage when processing large AFS responses."""
        # Create a very large response
        large_response = PerformanceTestHelper.create_large_afs_response(num_directories=5000)
        
        config = PerformanceTestHelper.create_test_config(num_volumes=1)
        
        with patch('requests.get') as mock_get:
            # Configure mock response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = large_response
            mock_get.return_value = mock_response
            
            # Measure memory before processing
            gc.collect()  # Force garbage collection
            start_memory = PerformanceTestHelper.get_memory_usage()
            
            # Create server components
            retry_config = create_retry_config(max_attempts=3, base_delay=1.0, max_delay=10.0)
            afs_client = AFSClient(
                access_key=config.afs.access_key,
                secret_key=config.afs.secret_key,
                base_url=config.afs.base_url,
                retry_config=retry_config
            )
            
            transformer = MetricsTransformer()
            metrics_handler = MetricsHandler(config, afs_client, transformer)
            
            # Measure memory after component creation
            after_init_memory = PerformanceTestHelper.get_memory_usage()
            
            # Process large response multiple times
            memory_samples = []
            for i in range(10):
                metrics, duration = metrics_handler.collect_metrics()
                current_memory = PerformanceTestHelper.get_memory_usage()
                memory_samples.append({
                    'iteration': i,
                    'memory': current_memory,
                    'num_metrics': len(metrics),
                    'duration': duration
                })
                
                # Verify we got metrics for all directories
                assert len(metrics) > 5000 * 5, f"Expected >25000 metrics, got {len(metrics)}"  # 5+ metrics per directory
            
            # Force garbage collection and measure final memory
            gc.collect()
            final_memory = PerformanceTestHelper.get_memory_usage()
            
            # Memory usage assertions
            init_increase = after_init_memory['rss_mb'] - start_memory['rss_mb']
            total_increase = final_memory['rss_mb'] - start_memory['rss_mb']
            
            # Memory should not grow excessively during processing
            assert total_increase < 200, f"Total memory increase too high: {total_increase:.2f} MB"
            
            # Check for memory leaks - memory should not continuously grow
            memory_values = [sample['memory']['rss_mb'] for sample in memory_samples]
            first_half_avg = sum(memory_values[:5]) / 5
            second_half_avg = sum(memory_values[5:]) / 5
            memory_growth = second_half_avg - first_half_avg
            
            assert memory_growth < 50, f"Memory appears to be leaking: {memory_growth:.2f} MB growth"
            
            # Performance should remain consistent
            durations = [sample['duration'] for sample in memory_samples]
            first_duration = durations[0]
            last_duration = durations[-1]
            performance_degradation = last_duration / first_duration
            
            assert performance_degradation < 2.0, f"Performance degraded: {performance_degradation:.2f}x slower"
    
    def test_memory_usage_multiple_volumes(self):
        """Test memory usage when processing multiple volumes concurrently."""
        # Create configuration with many volumes
        config = PerformanceTestHelper.create_test_config(num_volumes=20)
        
        # Create different responses for each volume
        def mock_get_side_effect(url, **kwargs):
            mock_response = Mock()
            mock_response.status_code = 200
            
            # Extract volume ID from URL to create different responses
            volume_id = url.split('/')[-2] if '/' in url else 'default'
            num_dirs = 100 + hash(volume_id) % 200  # 100-300 directories per volume
            
            mock_response.json.return_value = PerformanceTestHelper.create_large_afs_response(
                num_directories=num_dirs
            )
            return mock_response
        
        with patch('requests.get', side_effect=mock_get_side_effect) as mock_get:
            # Measure memory before processing
            gc.collect()
            start_memory = PerformanceTestHelper.get_memory_usage()
            
            # Create server components
            retry_config = create_retry_config(max_attempts=3, base_delay=1.0, max_delay=10.0)
            afs_client = AFSClient(
                access_key=config.afs.access_key,
                secret_key=config.afs.secret_key,
                base_url=config.afs.base_url,
                retry_config=retry_config
            )
            
            transformer = MetricsTransformer()
            metrics_handler = MetricsHandler(config, afs_client, transformer)
            server = MetricsServer(config, metrics_handler)
            
            # Create test client
            app = server.get_app()
            app.config['TESTING'] = True
            
            # Measure memory after initialization
            after_init_memory = PerformanceTestHelper.get_memory_usage()
            
            # Make multiple requests to test memory usage
            memory_samples = []
            for i in range(5):
                with app.test_client() as client:
                    response = client.get('/metrics')
                    assert response.status_code == 200
                    
                    current_memory = PerformanceTestHelper.get_memory_usage()
                    memory_samples.append({
                        'request': i,
                        'memory': current_memory,
                        'response_size': len(response.data)
                    })
            
            # Force garbage collection and measure final memory
            gc.collect()
            final_memory = PerformanceTestHelper.get_memory_usage()
            
            # Memory usage assertions
            total_increase = final_memory['rss_mb'] - start_memory['rss_mb']
            assert total_increase < 300, f"Total memory increase too high: {total_increase:.2f} MB"
            
            # Verify all volumes were processed
            assert mock_get.call_count >= 20, f"Expected >=20 API calls, got {mock_get.call_count}"
            
            # Check memory stability across requests
            memory_values = [sample['memory']['rss_mb'] for sample in memory_samples]
            memory_variance = max(memory_values) - min(memory_values)
            assert memory_variance < 100, f"Memory usage too variable: {memory_variance:.2f} MB variance"


class TestLargeDirectoryHandling:
    """Test behavior with large numbers of directories."""
    
    def test_processing_many_directories(self):
        """Test processing responses with very large numbers of directories."""
        # Create response with many directories
        num_directories = 10000
        large_response = PerformanceTestHelper.create_large_afs_response(num_directories)
        
        config = PerformanceTestHelper.create_test_config(num_volumes=1)
        
        with patch('requests.get') as mock_get:
            # Configure mock response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = large_response
            mock_get.return_value = mock_response
            
            # Create server components
            retry_config = create_retry_config(max_attempts=3, base_delay=1.0, max_delay=10.0)
            afs_client = AFSClient(
                access_key=config.afs.access_key,
                secret_key=config.afs.secret_key,
                base_url=config.afs.base_url,
                retry_config=retry_config
            )
            
            transformer = MetricsTransformer()
            metrics_handler = MetricsHandler(config, afs_client, transformer)
            server = MetricsServer(config, metrics_handler)
            
            # Create test client
            app = server.get_app()
            app.config['TESTING'] = True
            
            # Measure processing time
            start_time = time.time()
            start_memory = PerformanceTestHelper.get_memory_usage()
            
            with app.test_client() as client:
                response = client.get('/metrics')
            
            end_time = time.time()
            end_memory = PerformanceTestHelper.get_memory_usage()
            
            processing_time = end_time - start_time
            memory_increase = end_memory['rss_mb'] - start_memory['rss_mb']
            
            # Verify response
            assert response.status_code == 200
            response_text = response.data.decode('utf-8')
            
            # Count metrics in response
            metric_lines = [line for line in response_text.split('\n') 
                          if line and not line.startswith('#')]
            
            # Should have multiple metrics per directory (capacity, file count, state, utilization)
            expected_min_metrics = num_directories * 3  # At least 3 metrics per directory
            assert len(metric_lines) >= expected_min_metrics, \
                f"Expected >={expected_min_metrics} metrics, got {len(metric_lines)}"
            
            # Performance assertions
            assert processing_time < 30.0, f"Processing time too high: {processing_time:.3f}s"
            assert memory_increase < 500, f"Memory increase too high: {memory_increase:.2f} MB"
            
            # Verify specific metrics are present
            assert 'afs_capacity_used_bytes' in response_text
            assert 'afs_file_quantity_used' in response_text
            assert 'afs_directory_state' in response_text
            assert 'afs_scrape_duration_seconds' in response_text
            
            # Verify directory paths are properly handled
            assert 'dir_path="/data/directory_000000"' in response_text
            assert 'dir_path="/data/directory_009999"' in response_text
    
    def test_directory_label_sanitization_performance(self):
        """Test performance of label sanitization with many directories."""
        # Create response with directories that need sanitization
        dir_quota_list = []
        for i in range(1000):
            dir_quota_list.append({
                "volume_id": "test-volume",
                "dir_path": f"/data/directory with spaces & special chars #{i}",
                "file_quantity_quota": 0,
                "file_quantity_used_quota": 1000,
                "capacity_quota": 0,
                "capacity_used_quota": 1000000,
                "state": 1
            })
        
        response_with_special_chars = {"dir_quota_list": dir_quota_list}
        
        config = PerformanceTestHelper.create_test_config(num_volumes=1)
        
        with patch('requests.get') as mock_get:
            # Configure mock response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = response_with_special_chars
            mock_get.return_value = mock_response
            
            # Create transformer for testing
            transformer = MetricsTransformer()
            
            # Measure sanitization performance
            start_time = time.time()
            
            metrics = transformer.transform_quota_data(
                response_with_special_chars, "test-volume", "test-zone"
            )
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            # Performance assertion
            assert processing_time < 5.0, f"Label sanitization too slow: {processing_time:.3f}s"
            
            # Verify sanitization worked
            assert len(metrics) > 0
            
            # Check that labels are properly sanitized
            for metric in metrics:
                if 'dir_path' in metric.labels:
                    dir_path = metric.labels['dir_path']
                    # Should not contain problematic characters
                    assert '"' not in dir_path
                    assert '\\' not in dir_path
                    assert '\n' not in dir_path
    
    def test_mixed_directory_sizes_performance(self):
        """Test performance with mixed directory sizes and quota configurations."""
        # Create response with varied directory configurations
        dir_quota_list = []
        
        # Small directories (no quotas)
        for i in range(5000):
            dir_quota_list.append({
                "volume_id": f"volume-{i % 5}",
                "dir_path": f"/small/dir_{i}",
                "file_quantity_quota": 0,
                "file_quantity_used_quota": 10 + i,
                "capacity_quota": 0,
                "capacity_used_quota": 1000 + (i * 100),
                "state": 1
            })
        
        # Large directories (with quotas)
        for i in range(1000):
            dir_quota_list.append({
                "volume_id": f"volume-{i % 5}",
                "dir_path": f"/large/dir_{i}",
                "file_quantity_quota": 1000000,
                "file_quantity_used_quota": 500000 + (i * 100),
                "capacity_quota": 1073741824000,  # 1TB
                "capacity_used_quota": 536870912000 + (i * 1000000),  # ~500GB + variation
                "state": 1
            })
        
        mixed_response = {"dir_quota_list": dir_quota_list}
        
        config = PerformanceTestHelper.create_test_config(num_volumes=5)
        
        with patch('requests.get') as mock_get:
            # Configure mock response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mixed_response
            mock_get.return_value = mock_response
            
            # Create server components
            retry_config = create_retry_config(max_attempts=3, base_delay=1.0, max_delay=10.0)
            afs_client = AFSClient(
                access_key=config.afs.access_key,
                secret_key=config.afs.secret_key,
                base_url=config.afs.base_url,
                retry_config=retry_config
            )
            
            transformer = MetricsTransformer()
            metrics_handler = MetricsHandler(config, afs_client, transformer)
            server = MetricsServer(config, metrics_handler)
            
            # Create test client
            app = server.get_app()
            app.config['TESTING'] = True
            
            # Measure processing performance
            start_time = time.time()
            start_memory = PerformanceTestHelper.get_memory_usage()
            
            with app.test_client() as client:
                response = client.get('/metrics')
            
            end_time = time.time()
            end_memory = PerformanceTestHelper.get_memory_usage()
            
            processing_time = end_time - start_time
            memory_increase = end_memory['rss_mb'] - start_memory['rss_mb']
            
            # Verify response
            assert response.status_code == 200
            response_text = response.data.decode('utf-8')
            
            # Performance assertions
            assert processing_time < 20.0, f"Processing time too high: {processing_time:.3f}s"
            assert memory_increase < 400, f"Memory increase too high: {memory_increase:.2f} MB"
            
            # Verify both small and large directories are processed
            assert '/small/dir_' in response_text
            assert '/large/dir_' in response_text
            
            # Verify utilization metrics are calculated for directories with quotas
            assert 'afs_capacity_utilization_percent' in response_text
            assert 'afs_file_quantity_utilization_percent' in response_text
            
            # Count total metrics
            metric_lines = [line for line in response_text.split('\n') 
                          if line and not line.startswith('#')]
            
            # Should have metrics for all directories
            expected_min_metrics = 6000 * 3  # At least 3 metrics per directory
            assert len(metric_lines) >= expected_min_metrics, \
                f"Expected >={expected_min_metrics} metrics, got {len(metric_lines)}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])