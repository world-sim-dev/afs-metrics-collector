"""
Metrics transformer for converting AFS quota data to Prometheus metrics.

This module handles the transformation of AFS API responses into
Prometheus-compatible metrics with proper labeling and sanitization.
"""

import re
from typing import Dict, List
from src.data_models import PrometheusMetric, AFSQuotaData


class MetricsTransformer:
    """
    Transforms AFS quota data into Prometheus metrics format.
    
    This class handles the conversion of AFS dir_quota_list data into
    properly formatted Prometheus metrics with sanitized labels.
    """
    
    def __init__(self):
        """Initialize the metrics transformer."""
        pass
    
    def transform_quota_data(self, quota_data: Dict, volume_id: str, zone: str) -> List[PrometheusMetric]:
        """
        Transform AFS quota data into Prometheus metrics.
        
        Args:
            quota_data: AFS API response containing dir_quota_list
            volume_id: Volume identifier for labeling
            zone: Zone identifier for labeling
            
        Returns:
            List of PrometheusMetric objects
        """
        metrics = []
        
        # Extract dir_quota_list from the API response
        dir_quota_list = quota_data.get('dir_quota_list', [])
        
        for quota_item in dir_quota_list:
            # Create AFSQuotaData instance for easier handling
            afs_data = AFSQuotaData.from_api_response(quota_item, zone)
            
            # Generate metrics for this quota item
            metrics.extend(self._create_usage_metrics(afs_data))
        
        return metrics
    
    def _create_usage_metrics(self, quota_data: AFSQuotaData) -> List[PrometheusMetric]:
        """
        Create individual Prometheus metrics from AFS quota data.
        
        Args:
            quota_data: AFSQuotaData instance
            
        Returns:
            List of PrometheusMetric objects for this quota data
        """
        metrics = []
        
        # Create base labels for all metrics
        base_labels = self._sanitize_labels({
            'volume_id': quota_data.volume_id,
            'zone': quota_data.zone,
            'dir_path': quota_data.dir_path
        })
        
        # Capacity used metric
        metrics.append(PrometheusMetric(
            name='afs_capacity_used_bytes',
            value=float(quota_data.capacity_used_quota),
            labels=base_labels.copy(),
            help_text='Used storage capacity in bytes',
            metric_type='gauge'
        ))
        
        # Capacity quota metric (0 means unlimited)
        metrics.append(PrometheusMetric(
            name='afs_capacity_quota_bytes',
            value=float(quota_data.capacity_quota),
            labels=base_labels.copy(),
            help_text='Total capacity quota in bytes (0 means unlimited)',
            metric_type='gauge'
        ))
        
        # File quantity used metric
        metrics.append(PrometheusMetric(
            name='afs_file_quantity_used',
            value=float(quota_data.file_quantity_used_quota),
            labels=base_labels.copy(),
            help_text='Number of files used',
            metric_type='gauge'
        ))
        
        # File quantity quota metric (0 means unlimited)
        metrics.append(PrometheusMetric(
            name='afs_file_quantity_quota',
            value=float(quota_data.file_quantity_quota),
            labels=base_labels.copy(),
            help_text='File quantity quota (0 means unlimited)',
            metric_type='gauge'
        ))
        
        # Directory state metric
        metrics.append(PrometheusMetric(
            name='afs_directory_state',
            value=float(quota_data.state),
            labels=base_labels.copy(),
            help_text='Directory state (1=active, 0=inactive)',
            metric_type='gauge'
        ))
        
        # Calculate utilization percentages if quotas are set (not 0)
        if quota_data.capacity_quota > 0:
            capacity_utilization = (quota_data.capacity_used_quota / quota_data.capacity_quota) * 100
            metrics.append(PrometheusMetric(
                name='afs_capacity_utilization_percent',
                value=capacity_utilization,
                labels=base_labels.copy(),
                help_text='Storage capacity utilization percentage',
                metric_type='gauge'
            ))
        
        if quota_data.file_quantity_quota > 0:
            file_utilization = (quota_data.file_quantity_used_quota / quota_data.file_quantity_quota) * 100
            metrics.append(PrometheusMetric(
                name='afs_file_quantity_utilization_percent',
                value=file_utilization,
                labels=base_labels.copy(),
                help_text='File quantity utilization percentage',
                metric_type='gauge'
            ))
        
        return metrics
    
    def _sanitize_labels(self, labels: Dict[str, str]) -> Dict[str, str]:
        """
        Sanitize label values for Prometheus compatibility.
        
        Prometheus labels must follow specific naming conventions:
        - Label names must match [a-zA-Z_:][a-zA-Z0-9_:]*
        - Label values can contain any Unicode characters
        - But it's good practice to sanitize special characters
        
        Args:
            labels: Dictionary of label key-value pairs
            
        Returns:
            Dictionary with sanitized label values
        """
        sanitized = {}
        
        for key, value in labels.items():
            # Convert value to string if it isn't already
            str_value = str(value)
            
            # Replace problematic characters in label values
            # Keep alphanumeric, hyphens, underscores, slashes, and dots
            sanitized_value = re.sub(r'[^a-zA-Z0-9\-_/.]', '_', str_value)
            
            # Remove leading/trailing underscores that might result from sanitization
            sanitized_value = sanitized_value.strip('_')
            
            # Ensure we don't have empty values
            if not sanitized_value:
                sanitized_value = 'unknown'
            
            sanitized[key] = sanitized_value
        
        return sanitized
    
    def format_prometheus_metrics(self, metrics: List[PrometheusMetric]) -> str:
        """
        Format Prometheus metrics into the standard exposition format.
        
        The Prometheus exposition format consists of:
        - HELP lines describing the metric
        - TYPE lines specifying the metric type
        - Metric lines with name, labels, and values
        
        Args:
            metrics: List of PrometheusMetric objects to format
            
        Returns:
            String in Prometheus exposition format
        """
        if not metrics:
            return ""
        
        output_lines = []
        processed_metrics = set()
        
        # Group metrics by name to avoid duplicate HELP and TYPE lines
        metrics_by_name = {}
        for metric in metrics:
            if metric.name not in metrics_by_name:
                metrics_by_name[metric.name] = []
            metrics_by_name[metric.name].append(metric)
        
        # Format each metric group
        for metric_name, metric_list in metrics_by_name.items():
            if metric_name not in processed_metrics:
                # Add HELP line (use help text from first metric with this name)
                help_text = metric_list[0].help_text
                output_lines.append(f"# HELP {metric_name} {help_text}")
                
                # Add TYPE line (use type from first metric with this name)
                metric_type = metric_list[0].metric_type
                output_lines.append(f"# TYPE {metric_name} {metric_type}")
                
                processed_metrics.add(metric_name)
            
            # Add metric lines for all instances of this metric
            for metric in metric_list:
                metric_line = self._format_metric_line(metric)
                output_lines.append(metric_line)
        
        # Add final newline
        return '\n'.join(output_lines) + '\n'
    
    def _format_metric_line(self, metric: PrometheusMetric) -> str:
        """
        Format a single metric line in Prometheus format.
        
        Format: metric_name{label1="value1",label2="value2"} value
        
        Args:
            metric: PrometheusMetric to format
            
        Returns:
            Formatted metric line string
        """
        if not metric.labels:
            # No labels case
            return f"{metric.name} {metric.value}"
        
        # Format labels
        label_pairs = []
        for key, value in sorted(metric.labels.items()):
            # Escape quotes and backslashes in label values
            escaped_value = value.replace('\\', '\\\\').replace('"', '\\"')
            label_pairs.append(f'{key}="{escaped_value}"')
        
        labels_str = '{' + ','.join(label_pairs) + '}'
        
        return f"{metric.name}{labels_str} {metric.value}"