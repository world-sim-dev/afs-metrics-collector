"""
Unit tests for metrics transformation functionality.

This module tests the conversion of AFS quota data to Prometheus metrics,
including label sanitization, metric naming, and edge case handling.
"""

import pytest
from unittest.mock import Mock, patch

from src.metrics_transformer import MetricsTransformer
from src.data_models import PrometheusMetric, AFSQuotaData


class TestMetricsTransformer:
    """Test cases for MetricsTransformer functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.transformer = MetricsTransformer()
        
        # Sample AFS API response data matching the design document
        self.sample_afs_response = {
            "dir_quota_list": [
                {
                    "volume_id": "80433778-429e-11ef-bc97-4eca24dcdba9",
                    "dir_path": "/datasets",
                    "file_quantity_quota": 0,
                    "file_quantity_used_quota": 26351937,
                    "capacity_quota": 0,
                    "capacity_used_quota": 21643634736022,
                    "state": 1
                },
                {
                    "volume_id": "80433778-429e-11ef-bc97-4eca24dcdba9",
                    "dir_path": "/guhao",
                    "file_quantity_quota": 1000000,
                    "file_quantity_used_quota": 58108,
                    "capacity_quota": 1073741824000,  # 1TB
                    "capacity_used_quota": 5619439059,
                    "state": 1
                }
            ]
        }
        
        self.volume_id = "test-volume-id"
        self.zone = "cn-sh-01e"
    
    def test_transform_quota_data_success(self):
        """Test successful transformation of AFS quota data to Prometheus metrics."""
        metrics = self.transformer.transform_quota_data(
            self.sample_afs_response, 
            self.volume_id, 
            self.zone
        )
        
        # Should have metrics for both directories
        # Each directory should generate 5 base metrics + utilization metrics where applicable
        # First directory: 5 base metrics (no utilization since quotas are 0)
        # Second directory: 5 base metrics + 2 utilization metrics
        expected_metric_count = 5 + 7  # 12 total metrics
        assert len(metrics) == expected_metric_count
        
        # Verify all metrics are PrometheusMetric instances
        for metric in metrics:
            assert isinstance(metric, PrometheusMetric)
        
        # Check that we have the expected metric names
        metric_names = [metric.name for metric in metrics]
        expected_names = [
            'afs_capacity_used_bytes',
            'afs_capacity_quota_bytes', 
            'afs_file_quantity_used',
            'afs_file_quantity_quota',
            'afs_directory_state',
            'afs_capacity_utilization_percent',
            'afs_file_quantity_utilization_percent'
        ]
        
        for expected_name in expected_names:
            assert expected_name in metric_names
    
    def test_transform_quota_data_with_labels(self):
        """Test that metrics include correct labels."""
        metrics = self.transformer.transform_quota_data(
            self.sample_afs_response,
            self.volume_id,
            self.zone
        )
        
        # Check labels on first metric
        first_metric = metrics[0]
        expected_labels = {
            'volume_id': '80433778-429e-11ef-bc97-4eca24dcdba9',  # This comes from the sample data
            'zone': self.zone,
            'dir_path': '/datasets'
        }
        
        assert first_metric.labels == expected_labels
        
        # Verify all metrics have the required label keys
        for metric in metrics:
            assert 'volume_id' in metric.labels
            assert 'zone' in metric.labels
            assert 'dir_path' in metric.labels
    
    def test_transform_quota_data_metric_values(self):
        """Test that metric values are correctly extracted from AFS data."""
        metrics = self.transformer.transform_quota_data(
            self.sample_afs_response,
            self.volume_id,
            self.zone
        )
        
        # Find metrics for the first directory (/datasets)
        datasets_metrics = [m for m in metrics if m.labels['dir_path'] == '/datasets']
        
        # Check specific metric values
        capacity_used = next(m for m in datasets_metrics if m.name == 'afs_capacity_used_bytes')
        assert capacity_used.value == 21643634736022.0
        
        file_quantity_used = next(m for m in datasets_metrics if m.name == 'afs_file_quantity_used')
        assert file_quantity_used.value == 26351937.0
        
        directory_state = next(m for m in datasets_metrics if m.name == 'afs_directory_state')
        assert directory_state.value == 1.0
    
    def test_transform_quota_data_utilization_metrics(self):
        """Test that utilization metrics are calculated correctly when quotas are set."""
        metrics = self.transformer.transform_quota_data(
            self.sample_afs_response,
            self.volume_id,
            self.zone
        )
        
        # Find metrics for the second directory (/guhao) which has quotas set
        guhao_metrics = [m for m in metrics if m.labels['dir_path'] == '/guhao']
        
        # Check capacity utilization calculation
        capacity_utilization = next(
            (m for m in guhao_metrics if m.name == 'afs_capacity_utilization_percent'), 
            None
        )
        assert capacity_utilization is not None
        expected_capacity_util = (5619439059 / 1073741824000) * 100
        assert abs(capacity_utilization.value - expected_capacity_util) < 0.01
        
        # Check file quantity utilization calculation
        file_utilization = next(
            (m for m in guhao_metrics if m.name == 'afs_file_quantity_utilization_percent'),
            None
        )
        assert file_utilization is not None
        expected_file_util = (58108 / 1000000) * 100
        assert abs(file_utilization.value - expected_file_util) < 0.01
    
    def test_transform_quota_data_no_utilization_for_unlimited(self):
        """Test that utilization metrics are not created when quotas are 0 (unlimited)."""
        metrics = self.transformer.transform_quota_data(
            self.sample_afs_response,
            self.volume_id,
            self.zone
        )
        
        # Find metrics for the first directory (/datasets) which has unlimited quotas
        datasets_metrics = [m for m in metrics if m.labels['dir_path'] == '/datasets']
        
        # Should not have utilization metrics
        utilization_metrics = [
            m for m in datasets_metrics 
            if 'utilization_percent' in m.name
        ]
        assert len(utilization_metrics) == 0
    
    def test_transform_quota_data_empty_response(self):
        """Test handling of empty AFS response."""
        empty_response = {"dir_quota_list": []}
        
        metrics = self.transformer.transform_quota_data(
            empty_response,
            self.volume_id,
            self.zone
        )
        
        assert len(metrics) == 0
    
    def test_transform_quota_data_missing_dir_quota_list(self):
        """Test handling of response missing dir_quota_list."""
        invalid_response = {"some_other_field": "value"}
        
        metrics = self.transformer.transform_quota_data(
            invalid_response,
            self.volume_id,
            self.zone
        )
        
        assert len(metrics) == 0
    
    def test_create_usage_metrics_single_item(self):
        """Test creation of metrics for a single AFS quota data item."""
        quota_data = AFSQuotaData(
            volume_id="test-volume",
            zone="test-zone",
            dir_path="/test/path",
            file_quantity_quota=1000,
            file_quantity_used_quota=500,
            capacity_quota=1073741824,  # 1GB
            capacity_used_quota=536870912,  # 512MB
            state=1
        )
        
        metrics = self.transformer._create_usage_metrics(quota_data)
        
        # Should have 5 base metrics + 2 utilization metrics
        assert len(metrics) == 7
        
        # Verify metric names and values
        metric_dict = {m.name: m.value for m in metrics}
        
        assert metric_dict['afs_capacity_used_bytes'] == 536870912.0
        assert metric_dict['afs_capacity_quota_bytes'] == 1073741824.0
        assert metric_dict['afs_file_quantity_used'] == 500.0
        assert metric_dict['afs_file_quantity_quota'] == 1000.0
        assert metric_dict['afs_directory_state'] == 1.0
        assert metric_dict['afs_capacity_utilization_percent'] == 50.0
        assert metric_dict['afs_file_quantity_utilization_percent'] == 50.0


class TestMetricsTransformerLabelSanitization:
    """Test cases for label sanitization functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.transformer = MetricsTransformer()
    
    def test_sanitize_labels_normal_values(self):
        """Test sanitization of normal label values."""
        labels = {
            'volume_id': 'test-volume-123',
            'zone': 'us-west-1',
            'dir_path': '/normal/path'
        }
        
        sanitized = self.transformer._sanitize_labels(labels)
        
        # Normal values should remain unchanged
        assert sanitized == labels
    
    def test_sanitize_labels_special_characters(self):
        """Test sanitization of labels with special characters."""
        labels = {
            'volume_id': 'test@volume#123',
            'zone': 'us west 1',
            'dir_path': '/path with spaces/and@symbols!'
        }
        
        sanitized = self.transformer._sanitize_labels(labels)
        
        expected = {
            'volume_id': 'test_volume_123',
            'zone': 'us_west_1',
            'dir_path': '/path_with_spaces/and_symbols'  # Trailing underscore gets stripped
        }
        
        assert sanitized == expected
    
    def test_sanitize_labels_preserve_allowed_characters(self):
        """Test that allowed characters are preserved during sanitization."""
        labels = {
            'volume_id': 'test-volume_123',
            'zone': 'us-west-1.example.com',
            'dir_path': '/path/with-underscores_and.dots'
        }
        
        sanitized = self.transformer._sanitize_labels(labels)
        
        # These should remain unchanged as they contain only allowed characters
        assert sanitized == labels
    
    def test_sanitize_labels_empty_values(self):
        """Test handling of empty label values."""
        labels = {
            'volume_id': '',
            'zone': 'test-zone',
            'dir_path': '   '  # Only whitespace
        }
        
        sanitized = self.transformer._sanitize_labels(labels)
        
        expected = {
            'volume_id': 'unknown',
            'zone': 'test-zone',
            'dir_path': 'unknown'  # Whitespace gets stripped and replaced
        }
        
        assert sanitized == expected
    
    def test_sanitize_labels_non_string_values(self):
        """Test sanitization of non-string label values."""
        labels = {
            'volume_id': 12345,
            'zone': None,
            'dir_path': '/test'
        }
        
        sanitized = self.transformer._sanitize_labels(labels)
        
        expected = {
            'volume_id': '12345',
            'zone': 'None',
            'dir_path': '/test'
        }
        
        assert sanitized == expected
    
    def test_sanitize_labels_unicode_characters(self):
        """Test sanitization of Unicode characters."""
        labels = {
            'volume_id': 'test-volume-中文',
            'zone': 'région-française',
            'dir_path': '/path/with/émojis/🚀'
        }
        
        sanitized = self.transformer._sanitize_labels(labels)
        
        # Unicode characters should be replaced with underscores
        expected = {
            'volume_id': 'test-volume-',  # Unicode chars become underscores, trailing dash preserved
            'zone': 'r_gion-fran_aise',
            'dir_path': '/path/with/_mojis/'  # Unicode chars become underscores, slash preserved
        }
        
        assert sanitized == expected
    
    def test_sanitize_labels_leading_trailing_underscores(self):
        """Test removal of leading/trailing underscores from sanitization."""
        labels = {
            'volume_id': '!!!test-volume!!!',
            'zone': '@@@zone@@@',
            'dir_path': '###/path/###'
        }
        
        sanitized = self.transformer._sanitize_labels(labels)
        
        # Leading/trailing underscores should be stripped, but slashes preserved
        expected = {
            'volume_id': 'test-volume',
            'zone': 'zone',
            'dir_path': '/path/'  # ### becomes _, then trailing _ stripped, but / remains
        }
        
        assert sanitized == expected


class TestMetricsTransformerPrometheusFormat:
    """Test cases for Prometheus exposition format functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.transformer = MetricsTransformer()
    
    def test_format_prometheus_metrics_single_metric(self):
        """Test formatting of a single Prometheus metric."""
        metric = PrometheusMetric(
            name='test_metric',
            value=42.0,
            labels={'label1': 'value1', 'label2': 'value2'},
            help_text='Test metric description',
            metric_type='gauge'
        )
        
        formatted = self.transformer.format_prometheus_metrics([metric])
        
        expected_lines = [
            '# HELP test_metric Test metric description',
            '# TYPE test_metric gauge',
            'test_metric{label1="value1",label2="value2"} 42.0',
            ''  # Final newline
        ]
        
        assert formatted == '\n'.join(expected_lines)
    
    def test_format_prometheus_metrics_no_labels(self):
        """Test formatting of metric without labels."""
        metric = PrometheusMetric(
            name='simple_metric',
            value=123.45,
            labels={},
            help_text='Simple metric',
            metric_type='counter'
        )
        
        formatted = self.transformer.format_prometheus_metrics([metric])
        
        expected_lines = [
            '# HELP simple_metric Simple metric',
            '# TYPE simple_metric counter',
            'simple_metric 123.45',
            ''
        ]
        
        assert formatted == '\n'.join(expected_lines)
    
    def test_format_prometheus_metrics_multiple_same_name(self):
        """Test formatting of multiple metrics with the same name."""
        metrics = [
            PrometheusMetric(
                name='test_metric',
                value=10.0,
                labels={'instance': 'server1'},
                help_text='Test metric',
                metric_type='gauge'
            ),
            PrometheusMetric(
                name='test_metric',
                value=20.0,
                labels={'instance': 'server2'},
                help_text='Test metric',
                metric_type='gauge'
            )
        ]
        
        formatted = self.transformer.format_prometheus_metrics(metrics)
        
        # Should have only one HELP and TYPE line
        lines = formatted.strip().split('\n')
        help_lines = [line for line in lines if line.startswith('# HELP')]
        type_lines = [line for line in lines if line.startswith('# TYPE')]
        
        assert len(help_lines) == 1
        assert len(type_lines) == 1
        
        # Should have two metric lines
        metric_lines = [line for line in lines if not line.startswith('#')]
        assert len(metric_lines) == 2
        assert 'test_metric{instance="server1"} 10.0' in metric_lines
        assert 'test_metric{instance="server2"} 20.0' in metric_lines
    
    def test_format_prometheus_metrics_empty_list(self):
        """Test formatting of empty metrics list."""
        formatted = self.transformer.format_prometheus_metrics([])
        assert formatted == ""
    
    def test_format_metric_line_with_quotes_in_labels(self):
        """Test formatting of metric line with quotes in label values."""
        metric = PrometheusMetric(
            name='test_metric',
            value=1.0,
            labels={'path': '/path/with"quotes', 'description': 'Value with\\backslash'},
            help_text='Test',
            metric_type='gauge'
        )
        
        formatted_line = self.transformer._format_metric_line(metric)
        
        # Quotes and backslashes should be escaped
        expected = 'test_metric{description="Value with\\\\backslash",path="/path/with\\"quotes"} 1.0'
        assert formatted_line == expected
    
    def test_format_metric_line_label_sorting(self):
        """Test that labels are sorted in metric line formatting."""
        metric = PrometheusMetric(
            name='test_metric',
            value=1.0,
            labels={'z_label': 'z_value', 'a_label': 'a_value', 'm_label': 'm_value'},
            help_text='Test',
            metric_type='gauge'
        )
        
        formatted_line = self.transformer._format_metric_line(metric)
        
        # Labels should be sorted alphabetically
        expected = 'test_metric{a_label="a_value",m_label="m_value",z_label="z_value"} 1.0'
        assert formatted_line == expected


class TestMetricsTransformerEdgeCases:
    """Test cases for edge cases and error conditions."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.transformer = MetricsTransformer()
    
    def test_transform_quota_data_invalid_data_types(self):
        """Test handling of invalid data types in AFS response."""
        invalid_response = {
            "dir_quota_list": [
                {
                    "volume_id": "test-volume",
                    "dir_path": "/test",
                    "file_quantity_quota": "not_a_number",  # Invalid type
                    "file_quantity_used_quota": None,  # Invalid type
                    "capacity_quota": 1000,
                    "capacity_used_quota": 500,
                    "state": 1
                }
            ]
        }
        
        # This should raise an exception when AFSQuotaData.from_api_response is called
        with pytest.raises((TypeError, ValueError, KeyError)):
            self.transformer.transform_quota_data(
                invalid_response,
                "test-volume",
                "test-zone"
            )
    
    def test_transform_quota_data_missing_required_fields(self):
        """Test handling of missing required fields in AFS response."""
        invalid_response = {
            "dir_quota_list": [
                {
                    "volume_id": "test-volume",
                    # Missing required fields
                    "capacity_quota": 1000,
                    "capacity_used_quota": 500
                }
            ]
        }
        
        # This should raise a KeyError when trying to access missing fields
        with pytest.raises(KeyError):
            self.transformer.transform_quota_data(
                invalid_response,
                "test-volume",
                "test-zone"
            )
    
    def test_create_usage_metrics_zero_division_protection(self):
        """Test that zero division is handled in utilization calculations."""
        # This test verifies that when quotas are 0, no utilization metrics are created
        quota_data = AFSQuotaData(
            volume_id="test-volume",
            zone="test-zone",
            dir_path="/test",
            file_quantity_quota=0,  # Zero quota (unlimited)
            file_quantity_used_quota=1000,
            capacity_quota=0,  # Zero quota (unlimited)
            capacity_used_quota=1000000,
            state=1
        )
        
        metrics = self.transformer._create_usage_metrics(quota_data)
        
        # Should have 5 base metrics but no utilization metrics
        assert len(metrics) == 5
        
        utilization_metrics = [m for m in metrics if 'utilization_percent' in m.name]
        assert len(utilization_metrics) == 0
    
    def test_create_usage_metrics_negative_values(self):
        """Test handling of negative values in quota data."""
        quota_data = AFSQuotaData(
            volume_id="test-volume",
            zone="test-zone",
            dir_path="/test",
            file_quantity_quota=1000,
            file_quantity_used_quota=-100,  # Negative value
            capacity_quota=1000000,
            capacity_used_quota=-50000,  # Negative value
            state=1
        )
        
        metrics = self.transformer._create_usage_metrics(quota_data)
        
        # Should still create metrics, but with negative values
        capacity_used = next(m for m in metrics if m.name == 'afs_capacity_used_bytes')
        assert capacity_used.value == -50000.0
        
        file_used = next(m for m in metrics if m.name == 'afs_file_quantity_used')
        assert file_used.value == -100.0
        
        # Utilization should still be calculated (will be negative)
        capacity_util = next(m for m in metrics if m.name == 'afs_capacity_utilization_percent')
        assert capacity_util.value == -5.0  # -50000 / 1000000 * 100
    
    def test_create_usage_metrics_very_large_numbers(self):
        """Test handling of very large numbers in quota data."""
        quota_data = AFSQuotaData(
            volume_id="test-volume",
            zone="test-zone",
            dir_path="/test",
            file_quantity_quota=999999999999999,  # Very large number
            file_quantity_used_quota=123456789012345,
            capacity_quota=999999999999999999999,  # Very large number
            capacity_used_quota=123456789012345678901,
            state=1
        )
        
        metrics = self.transformer._create_usage_metrics(quota_data)
        
        # Should handle large numbers correctly
        capacity_used = next(m for m in metrics if m.name == 'afs_capacity_used_bytes')
        assert capacity_used.value == 123456789012345678901.0
        
        # Utilization should be calculated correctly
        capacity_util = next(m for m in metrics if m.name == 'afs_capacity_utilization_percent')
        expected_util = (123456789012345678901 / 999999999999999999999) * 100
        assert abs(capacity_util.value - expected_util) < 0.01
    
    @patch('src.data_models.AFSQuotaData.from_api_response')
    def test_transform_quota_data_afs_data_creation_failure(self, mock_from_api_response):
        """Test handling of AFSQuotaData creation failure."""
        mock_from_api_response.side_effect = ValueError("Invalid data format")
        
        response = {
            "dir_quota_list": [
                {"volume_id": "test", "dir_path": "/test"}
            ]
        }
        
        # Should propagate the exception
        with pytest.raises(ValueError, match="Invalid data format"):
            self.transformer.transform_quota_data(response, "volume", "zone")