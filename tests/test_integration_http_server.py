"""
Integration tests for the HTTP server with real components.

This module tests the integration between HTTP server, metrics handler,
and other components using real instances (with mocked external dependencies).
"""

import pytest
from unittest.mock import Mock, patch
import json
import threading
import time
import concurrent.futures
from typing import List

from src.http_server import MetricsServer
from src.metrics_handler import MetricsHandler
from src.config import Config, AFSConfig, VolumeConfig, ServerConfig, CollectionConfig
from src.afs_client import AFSClient
from src.metrics_transformer import MetricsTransformer
from src.data_models import PrometheusMetric
from src.exceptions import AuthenticationError, APIError


@pytest.fixture
def real_config():
    """Create a real configuration for testing."""
    config = Config()
    
    # Set up test configuration
    config.afs = AFSConfig(
        access_key="test_access_key",
        secret_key="test_secret_key",
        base_url="https://test.example.com",
        volumes=[
            VolumeConfig(volume_id="test-volume-1", zone="test-zone-1")
        ]
    )
    
    config.server = ServerConfig(
        host="127.0.0.1",
        port=8080,
        request_timeout=30
    )
    
    config.collection = CollectionConfig(
        max_retries=3,
        retry_delay=2,
        timeout_seconds=25,
        cache_duration=30
    )
    
    return config


@pytest.fixture
def mock_afs_client():
    """Create a mock AFS client."""
    client = Mock(spec=AFSClient)
    
    # Mock successful API response
    client.get_volume_quotas.return_value = {
        "dir_quota_list": [
            {
                "volume_id": "test-volume-1",
                "dir_path": "/test",
                "file_quantity_quota": 0,
                "file_quantity_used_quota": 1000,
                "capacity_quota": 0,
                "capacity_used_quota": 5000000,
                "state": 1
            }
        ]
    }
    
    client.test_connection.return_value = True
    
    return client


@pytest.fixture
def mock_afs_client_multi_volume():
    """Create a mock AFS client with multiple volumes."""
    client = Mock(spec=AFSClient)
    
    def mock_get_volume_quotas(volume_id, zone, timeout=30):
        """Mock different responses based on volume_id."""
        if volume_id == "test-volume-1":
            return {
                "dir_quota_list": [
                    {
                        "volume_id": "test-volume-1",
                        "dir_path": "/datasets",
                        "file_quantity_quota": 0,
                        "file_quantity_used_quota": 26351937,
                        "capacity_quota": 0,
                        "capacity_used_quota": 21643634736022,
                        "state": 1
                    },
                    {
                        "volume_id": "test-volume-1",
                        "dir_path": "/models",
                        "file_quantity_quota": 1000000,
                        "file_quantity_used_quota": 58108,
                        "capacity_quota": 1000000000000,
                        "capacity_used_quota": 5619439059,
                        "state": 1
                    }
                ]
            }
        elif volume_id == "test-volume-2":
            return {
                "dir_quota_list": [
                    {
                        "volume_id": "test-volume-2",
                        "dir_path": "/backup",
                        "file_quantity_quota": 0,
                        "file_quantity_used_quota": 12345,
                        "capacity_quota": 0,
                        "capacity_used_quota": 987654321,
                        "state": 1
                    }
                ]
            }
        else:
            raise APIError(f"Volume {volume_id} not found")
    
    client.get_volume_quotas.side_effect = mock_get_volume_quotas
    client.test_connection.return_value = True
    
    return client


@pytest.fixture
def real_config_multi_volume():
    """Create a real configuration with multiple volumes for testing."""
    config = Config()
    
    # Set up test configuration with multiple volumes
    config.afs = AFSConfig(
        access_key="test_access_key",
        secret_key="test_secret_key",
        base_url="https://test.example.com",
        volumes=[
            VolumeConfig(volume_id="test-volume-1", zone="test-zone-1"),
            VolumeConfig(volume_id="test-volume-2", zone="test-zone-2")
        ]
    )
    
    config.server = ServerConfig(
        host="127.0.0.1",
        port=8080,
        request_timeout=30
    )
    
    config.collection = CollectionConfig(
        max_retries=3,
        retry_delay=2,
        timeout_seconds=25,
        cache_duration=30
    )
    
    return config


@pytest.fixture
def real_transformer():
    """Create a real metrics transformer."""
    return MetricsTransformer()


@pytest.fixture
def real_metrics_handler(real_config, mock_afs_client, real_transformer):
    """Create a real metrics handler with mocked AFS client."""
    return MetricsHandler(real_config, mock_afs_client, real_transformer)


@pytest.fixture
def real_metrics_server(real_config, real_metrics_handler):
    """Create a real metrics server."""
    return MetricsServer(real_config, real_metrics_handler)


@pytest.fixture
def client(real_metrics_server):
    """Create a test client for the Flask app."""
    app = real_metrics_server.get_app()
    app.config['TESTING'] = True
    return app.test_client()


class TestHTTPServerIntegration:
    """Integration tests for the HTTP server with real components."""
    
    def test_metrics_endpoint_integration(self, client, mock_afs_client):
        """Test the complete metrics endpoint flow with real components."""
        response = client.get('/metrics')
        
        assert response.status_code == 200
        assert response.mimetype == 'text/plain'
        assert 'version=0.0.4' in response.content_type
        
        # Verify the response contains expected metrics
        response_text = response.data.decode('utf-8')
        
        # Check for metric names
        assert 'afs_capacity_used_bytes' in response_text
        assert 'afs_file_quantity_used' in response_text
        assert 'afs_directory_state' in response_text
        assert 'afs_scrape_duration_seconds' in response_text
        assert 'afs_scrape_timestamp' in response_text
        
        # Check for labels
        assert 'volume_id="test-volume-1"' in response_text
        assert 'zone="test-zone-1"' in response_text
        assert 'dir_path="/test"' in response_text
        
        # Check for HELP and TYPE lines
        assert '# HELP afs_capacity_used_bytes' in response_text
        assert '# TYPE afs_capacity_used_bytes gauge' in response_text
        
        # Verify AFS client was called
        mock_afs_client.get_volume_quotas.assert_called_once_with(
            volume_id="test-volume-1",
            zone="test-zone-1",
            timeout=25
        )
    
    def test_metrics_endpoint_with_multiple_volumes(self, real_config_multi_volume, mock_afs_client_multi_volume, real_transformer):
        """Test metrics endpoint with multiple volumes and directories."""
        # Create metrics handler and server with multi-volume config
        metrics_handler = MetricsHandler(real_config_multi_volume, mock_afs_client_multi_volume, real_transformer)
        metrics_server = MetricsServer(real_config_multi_volume, metrics_handler)
        
        app = metrics_server.get_app()
        app.config['TESTING'] = True
        client = app.test_client()
        
        response = client.get('/metrics')
        
        assert response.status_code == 200
        response_text = response.data.decode('utf-8')
        
        # Should contain metrics from both volumes
        assert 'volume_id="test-volume-1"' in response_text
        assert 'volume_id="test-volume-2"' in response_text
        
        # Should contain metrics from multiple directories
        assert 'dir_path="/datasets"' in response_text
        assert 'dir_path="/models"' in response_text
        assert 'dir_path="/backup"' in response_text
        
        # Should contain collection status metrics for both volumes
        assert 'afs_collection_success{volume_id="test-volume-1",zone="test-zone-1"} 1.0' in response_text
        assert 'afs_collection_success{volume_id="test-volume-2",zone="test-zone-2"} 1.0' in response_text
        
        # Verify both volumes were called
        assert mock_afs_client_multi_volume.get_volume_quotas.call_count == 2
    
    def test_metrics_endpoint_with_mixed_success_failure(self, real_config_multi_volume, real_transformer):
        """Test metrics endpoint when some volumes succeed and others fail."""
        # Create a mock client that fails for one volume
        mock_client = Mock(spec=AFSClient)
        
        def mock_get_volume_quotas(volume_id, zone, timeout=30):
            if volume_id == "test-volume-1":
                return {
                    "dir_quota_list": [
                        {
                            "volume_id": "test-volume-1",
                            "dir_path": "/success",
                            "file_quantity_quota": 0,
                            "file_quantity_used_quota": 1000,
                            "capacity_quota": 0,
                            "capacity_used_quota": 5000000,
                            "state": 1
                        }
                    ]
                }
            elif volume_id == "test-volume-2":
                raise APIError("Volume not accessible")
        
        mock_client.get_volume_quotas.side_effect = mock_get_volume_quotas
        mock_client.test_connection.return_value = True
        
        # Create metrics handler and server
        metrics_handler = MetricsHandler(real_config_multi_volume, mock_client, real_transformer)
        metrics_server = MetricsServer(real_config_multi_volume, metrics_handler)
        
        app = metrics_server.get_app()
        app.config['TESTING'] = True
        client = app.test_client()
        
        response = client.get('/metrics')
        
        assert response.status_code == 200
        response_text = response.data.decode('utf-8')
        
        # Should contain metrics from successful volume
        assert 'volume_id="test-volume-1"' in response_text
        assert 'dir_path="/success"' in response_text
        
        # Should contain success metric for volume 1
        assert 'afs_collection_success{volume_id="test-volume-1",zone="test-zone-1"} 1.0' in response_text
        
        # Should contain failure metric for volume 2
        assert 'afs_collection_success{volume_id="test-volume-2",zone="test-zone-2"} 0.0' in response_text
        
        # Should contain error metric for volume 2
        assert 'afs_collection_error{error="Volume not accessible",volume_id="test-volume-2",zone="test-zone-2"} 1.0' in response_text
    
    def test_readiness_endpoint_integration(self, client, mock_afs_client):
        """Test the readiness endpoint with real components."""
        response = client.get('/health/ready')
        
        assert response.status_code == 200
        assert response.mimetype == 'application/json'
        
        data = json.loads(response.data)
        assert data['status'] == 'ready'
        assert 'ready to serve requests' in data['message']
        
        # Verify AFS client connectivity test was called
        mock_afs_client.test_connection.assert_called_once()
    
    def test_liveness_endpoint_integration(self, client):
        """Test the liveness endpoint."""
        response = client.get('/health/live')
        
        assert response.status_code == 200
        assert response.mimetype == 'application/json'
        
        data = json.loads(response.data)
        assert data['status'] == 'alive'
        assert 'running' in data['message']
    
    def test_caching_behavior(self, client, mock_afs_client):
        """Test that caching works correctly for concurrent requests."""
        # Make first request
        response1 = client.get('/metrics')
        assert response1.status_code == 200
        
        # Make second request immediately (should use cache)
        response2 = client.get('/metrics')
        assert response2.status_code == 200
        
        # Both responses should be identical (from cache)
        assert response1.data == response2.data
        
        # AFS client should only be called once due to caching
        assert mock_afs_client.get_volume_quotas.call_count == 1
    
    def test_cache_expiration(self, client, mock_afs_client, real_config):
        """Test that cache expires correctly."""
        # Temporarily reduce cache duration for testing
        original_cache_duration = real_config.collection.cache_duration
        real_config.collection.cache_duration = 1  # 1 second
        
        try:
            # Make first request
            response1 = client.get('/metrics')
            assert response1.status_code == 200
            assert mock_afs_client.get_volume_quotas.call_count == 1
            
            # Wait for cache to expire
            time.sleep(1.1)
            
            # Make second request (should not use cache)
            response2 = client.get('/metrics')
            assert response2.status_code == 200
            
            # AFS client should be called again
            assert mock_afs_client.get_volume_quotas.call_count == 2
            
        finally:
            # Restore original cache duration
            real_config.collection.cache_duration = original_cache_duration
    
    def test_error_handling_integration(self, client, mock_afs_client):
        """Test error handling when AFS client fails."""
        # Mock AFS client failure
        mock_afs_client.get_volume_quotas.side_effect = Exception("API Error")
        
        response = client.get('/metrics')
        
        # Should still return 200 with error metrics
        assert response.status_code == 200
        
        response_text = response.data.decode('utf-8')
        
        # Should contain error metrics
        assert 'afs_collection_error' in response_text
        assert 'afs_scrape_timestamp' in response_text
        assert 'API Error' in response_text
    
    def test_authentication_error_handling(self, client, mock_afs_client):
        """Test handling of authentication errors."""
        # Mock authentication failure
        mock_afs_client.get_volume_quotas.side_effect = AuthenticationError("Invalid credentials")
        
        response = client.get('/metrics')
        
        assert response.status_code == 200
        response_text = response.data.decode('utf-8')
        
        # Should contain error metrics with authentication error
        assert 'afs_collection_error' in response_text
        assert 'Invalid credentials' in response_text
    
    def test_readiness_failure_integration(self, client, mock_afs_client):
        """Test readiness endpoint when AFS connectivity fails."""
        # Mock connectivity failure
        mock_afs_client.test_connection.return_value = False
        
        response = client.get('/health/ready')
        
        assert response.status_code == 503
        
        data = json.loads(response.data)
        assert data['status'] == 'not ready'
        assert 'connectivity test failed' in data['message']
    
    def test_readiness_configuration_error(self, real_config, mock_afs_client, real_transformer):
        """Test readiness endpoint when configuration validation fails."""
        # Create a server with invalid configuration
        real_config.afs.access_key = ""  # Invalid empty access key
        
        metrics_handler = MetricsHandler(real_config, mock_afs_client, real_transformer)
        metrics_server = MetricsServer(real_config, metrics_handler)
        
        app = metrics_server.get_app()
        app.config['TESTING'] = True
        client = app.test_client()
        
        response = client.get('/health/ready')
        
        assert response.status_code == 503
        
        data = json.loads(response.data)
        assert data['status'] == 'not ready'
        assert 'access_key' in data['message']


class TestConcurrentRequestHandling:
    """Test concurrent request handling capabilities."""
    
    def test_concurrent_metrics_requests(self, real_config, mock_afs_client, real_transformer):
        """Test handling multiple concurrent requests to metrics endpoint."""
        # Create metrics handler and server
        metrics_handler = MetricsHandler(real_config, mock_afs_client, real_transformer)
        metrics_server = MetricsServer(real_config, metrics_handler)
        
        app = metrics_server.get_app()
        app.config['TESTING'] = True
        
        # Function to make a request
        def make_request():
            with app.test_client() as client:
                response = client.get('/metrics')
                return response.status_code, len(response.data)
        
        # Make multiple concurrent requests
        num_requests = 10
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request) for _ in range(num_requests)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        # All requests should succeed
        assert len(results) == num_requests
        for status_code, response_length in results:
            assert status_code == 200
            assert response_length > 0
        
        # Due to caching, AFS client should only be called once
        assert mock_afs_client.get_volume_quotas.call_count == 1
    
    def test_concurrent_mixed_requests(self, real_config, mock_afs_client, real_transformer):
        """Test handling concurrent requests to different endpoints."""
        # Create metrics handler and server
        metrics_handler = MetricsHandler(real_config, mock_afs_client, real_transformer)
        metrics_server = MetricsServer(real_config, metrics_handler)
        
        app = metrics_server.get_app()
        app.config['TESTING'] = True
        
        def make_metrics_request():
            with app.test_client() as client:
                response = client.get('/metrics')
                return 'metrics', response.status_code
        
        def make_readiness_request():
            with app.test_client() as client:
                response = client.get('/health/ready')
                return 'ready', response.status_code
        
        def make_liveness_request():
            with app.test_client() as client:
                response = client.get('/health/live')
                return 'live', response.status_code
        
        # Make concurrent requests to different endpoints
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = []
            futures.extend([executor.submit(make_metrics_request) for _ in range(3)])
            futures.extend([executor.submit(make_readiness_request) for _ in range(2)])
            futures.extend([executor.submit(make_liveness_request) for _ in range(2)])
            
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        # All requests should succeed
        assert len(results) == 7
        for endpoint, status_code in results:
            assert status_code == 200
        
        # Check that we got requests to all endpoints
        endpoints = [result[0] for result in results]
        assert 'metrics' in endpoints
        assert 'ready' in endpoints
        assert 'live' in endpoints
    
    def test_concurrent_requests_with_slow_afs_response(self, real_config, real_transformer):
        """Test concurrent requests when AFS API is slow."""
        # Create a mock client with slow response
        mock_client = Mock(spec=AFSClient)
        
        def slow_get_volume_quotas(volume_id, zone, timeout=30):
            time.sleep(0.1)  # Simulate slow API response
            return {
                "dir_quota_list": [
                    {
                        "volume_id": volume_id,
                        "dir_path": "/slow",
                        "file_quantity_quota": 0,
                        "file_quantity_used_quota": 1000,
                        "capacity_quota": 0,
                        "capacity_used_quota": 5000000,
                        "state": 1
                    }
                ]
            }
        
        mock_client.get_volume_quotas.side_effect = slow_get_volume_quotas
        mock_client.test_connection.return_value = True
        
        # Create metrics handler and server
        metrics_handler = MetricsHandler(real_config, mock_client, real_transformer)
        metrics_server = MetricsServer(real_config, metrics_handler)
        
        app = metrics_server.get_app()
        app.config['TESTING'] = True
        
        def make_request():
            with app.test_client() as client:
                start_time = time.time()
                response = client.get('/metrics')
                duration = time.time() - start_time
                return response.status_code, duration
        
        # Make concurrent requests
        num_requests = 5
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(make_request) for _ in range(num_requests)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        # All requests should succeed
        for status_code, duration in results:
            assert status_code == 200
            # Due to caching, subsequent requests should be much faster
        
        # Only the first request should trigger AFS API call
        assert mock_client.get_volume_quotas.call_count == 1
        
        # Check that some requests were fast (from cache)
        durations = [result[1] for result in results]
        fast_requests = [d for d in durations if d < 0.05]  # Less than 50ms
        # At least half of the requests should be fast due to caching
        assert len(fast_requests) >= num_requests // 2, f"Expected at least {num_requests // 2} fast requests, got {len(fast_requests)}. Durations: {durations}"
    
    def test_request_timeout_handling(self, real_config, real_transformer):
        """Test handling of request timeouts."""
        # Create a mock client that times out
        mock_client = Mock(spec=AFSClient)
        mock_client.get_volume_quotas.side_effect = APIError("Request timeout after 25 seconds")
        mock_client.test_connection.return_value = True
        
        # Create metrics handler and server
        metrics_handler = MetricsHandler(real_config, mock_client, real_transformer)
        metrics_server = MetricsServer(real_config, metrics_handler)
        
        app = metrics_server.get_app()
        app.config['TESTING'] = True
        client = app.test_client()
        
        response = client.get('/metrics')
        
        # Should still return 200 with error metrics
        assert response.status_code == 200
        response_text = response.data.decode('utf-8')
        
        # Should contain timeout error
        assert 'afs_collection_error' in response_text
        assert 'timeout' in response_text.lower()


class TestPrometheusMetricsFormat:
    """Test Prometheus metrics format compliance."""
    
    def test_metrics_format_compliance(self, client, mock_afs_client):
        """Test that metrics output complies with Prometheus format."""
        response = client.get('/metrics')
        
        assert response.status_code == 200
        response_text = response.data.decode('utf-8')
        
        lines = response_text.strip().split('\n')
        
        # Check for proper HELP and TYPE lines
        help_lines = [line for line in lines if line.startswith('# HELP')]
        type_lines = [line for line in lines if line.startswith('# TYPE')]
        metric_lines = [line for line in lines if not line.startswith('#') and line.strip()]
        
        assert len(help_lines) > 0
        assert len(type_lines) > 0
        assert len(metric_lines) > 0
        
        # Each metric should have HELP and TYPE
        metric_names = set()
        for line in metric_lines:
            metric_name = line.split('{')[0].split(' ')[0]
            metric_names.add(metric_name)
        
        for metric_name in metric_names:
            help_found = any(f'# HELP {metric_name}' in line for line in help_lines)
            type_found = any(f'# TYPE {metric_name}' in line for line in type_lines)
            assert help_found, f"Missing HELP for metric {metric_name}"
            assert type_found, f"Missing TYPE for metric {metric_name}"
    
    def test_metric_naming_conventions(self, client, mock_afs_client):
        """Test that metric names follow Prometheus conventions."""
        response = client.get('/metrics')
        
        assert response.status_code == 200
        response_text = response.data.decode('utf-8')
        
        lines = response_text.strip().split('\n')
        metric_lines = [line for line in lines if not line.startswith('#') and line.strip()]
        
        for line in metric_lines:
            metric_name = line.split('{')[0].split(' ')[0]
            
            # Should start with afs_
            assert metric_name.startswith('afs_'), f"Metric {metric_name} should start with 'afs_'"
            
            # Should be snake_case
            assert metric_name.islower(), f"Metric {metric_name} should be lowercase"
            assert '_' in metric_name, f"Metric {metric_name} should use underscores"
            
            # Should not contain invalid characters
            valid_chars = set('abcdefghijklmnopqrstuvwxyz0123456789_')
            assert all(c in valid_chars for c in metric_name), f"Metric {metric_name} contains invalid characters"
    
    def test_label_format_compliance(self, client, mock_afs_client):
        """Test that labels are properly formatted."""
        response = client.get('/metrics')
        
        assert response.status_code == 200
        response_text = response.data.decode('utf-8')
        
        lines = response_text.strip().split('\n')
        metric_lines = [line for line in lines if not line.startswith('#') and line.strip() and '{' in line]
        
        for line in metric_lines:
            # Extract labels part
            if '{' in line and '}' in line:
                labels_part = line.split('{')[1].split('}')[0]
                
                # Parse individual labels
                if labels_part:
                    # Simple parsing - split by comma and check format
                    labels = [label.strip() for label in labels_part.split(',')]
                    
                    for label in labels:
                        assert '=' in label, f"Label {label} should contain '='"
                        key, value = label.split('=', 1)
                        
                        # Key should be valid
                        assert key.strip(), f"Label key should not be empty in {label}"
                        
                        # Value should be quoted
                        assert value.startswith('"') and value.endswith('"'), f"Label value should be quoted in {label}"


if __name__ == '__main__':
    pytest.main([__file__])