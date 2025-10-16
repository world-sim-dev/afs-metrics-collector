"""
Data models for AFS Prometheus metrics system.

This module contains dataclasses for representing Prometheus metrics
and AFS quota data structures.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class PrometheusMetric:
    """
    Represents a single Prometheus metric with its metadata.
    
    Attributes:
        name: The metric name following Prometheus naming conventions
        value: The numeric value of the metric
        labels: Dictionary of label key-value pairs
        help_text: Human-readable description of the metric
        metric_type: Type of metric (gauge, counter, histogram, summary)
    """
    name: str
    value: float
    labels: Dict[str, str]
    help_text: str
    metric_type: str = "gauge"


@dataclass
class AFSQuotaData:
    """
    Represents AFS quota data structure matching the API response.
    
    This dataclass matches the structure of individual items in the
    dir_quota_list from the AFS API response.
    
    Attributes:
        volume_id: Unique identifier for the storage volume
        zone: The zone where the volume is located
        dir_path: Directory path within the volume
        file_quantity_quota: Maximum number of files allowed (0 = unlimited)
        file_quantity_used_quota: Current number of files used
        capacity_quota: Maximum storage capacity in bytes (0 = unlimited)
        capacity_used_quota: Current storage capacity used in bytes
        state: Directory state (1 = active, 0 = inactive)
    """
    volume_id: str
    zone: str
    dir_path: str
    file_quantity_quota: int
    file_quantity_used_quota: int
    capacity_quota: int
    capacity_used_quota: int
    state: int

    @classmethod
    def from_api_response(cls, quota_item: Dict, zone: str) -> 'AFSQuotaData':
        """
        Create AFSQuotaData instance from API response item.
        
        Args:
            quota_item: Dictionary from dir_quota_list API response
            zone: Zone identifier to include in the data
            
        Returns:
            AFSQuotaData instance
        """
        return cls(
            volume_id=quota_item['volume_id'],
            zone=zone,
            dir_path=quota_item['dir_path'],
            file_quantity_quota=quota_item['file_quantity_quota'],
            file_quantity_used_quota=quota_item['file_quantity_used_quota'],
            capacity_quota=quota_item['capacity_quota'],
            capacity_used_quota=quota_item['capacity_used_quota'],
            state=quota_item['state']
        )