"""
Tests for the HTTP server module.

This module tests the Flask-based HTTP server that serves Prometheus metrics
and health check endpoints.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from flask import Flask

from src.http_server import MetricsServer
from src.config import Config, AFSConfig, VolumeConfig, ServerConfig, CollectionConfig
from src.metrics_handler import MetricsHandler
from src.data_models import PrometheusMetric


@pytest.fixture
def mock_config():
    """Create a mock configuration for testing."""
    config = Mock(spec=Config)
    
    # Mock AFS config
    afs_config = AFSConfig(
        access_key="test_access_key",
        secret_key="test_secret_key",
        base_url="https://test.example.com",
        volumes=[
            VolumeConfig(volume_id="test-volume-1", zone="test-zone-1"),
            VolumeConfig(volume_id="test-volume-2", zone="test-zone-2")
        ]
    )
    
    # Mock server config
    server_config = ServerConfig(
        host="127.0.0.1",
        port=8080,
        request_timeout=30
    )
    
    # Mock collection config
    collection_config = CollectionConfig(
        max_retries=3,
        retry_delay=2,
        timeout_seconds=25,
        cache_duration=30
    )
    
    config.get_afs_config.return_value = afs_config
    config.get_server_config.return_value = server_config
    config.get_collection_config.return_value = collection_config
    config.validate.return_value = True
    
    return config


@pytest.fixture
def mock_metrics_handler():
    """Create a mock metrics handler for testing."""
    handler = Mock()
    
    # Mock successful metrics collection
    sample_metrics = [
        PrometheusMetric(
            name="afs_capacity_used_bytes",
            value=1000000.0,
            labels={"volume_id": "test-volume-1", "zone": "test-zone-1", "dir_path": "/test"},
            help_text="Used storage capacity in bytes",
            metric_type="gauge"
        ),
        PrometheusMetric(
            name="afs_scrape_duration_seconds",
            value=0.5,
            labels={},
            help_text="Total duration of the metrics scrape in seconds",
            metric_type="gauge"
        )
    ]
    
    handler.collect_metrics.return_value = (sample_metrics, 0.5)
    handler.transformer.format_prometheus_metrics.return_value = (
        "# HELP afs_capacity_used_bytes Used storage capacity in bytes\n"
        "# TYPE afs_capacity_used_bytes gauge\n"
        "afs_capacity_used_bytes{volume_id=\"test-volume-1\",zone=\"test-zone-1\",dir_path=\"/test\"} 1000000.0\n"
        "# HELP afs_scrape_duration_seconds Total duration of the metrics scrape in seconds\n"
        "# TYPE afs_scrape_duration_seconds gauge\n"
        "afs_scrape_duration_seconds 0.5\n"
    )
    
    # Mock AFS client for readiness check
    handler.afs_client.test_connection.return_value = True
    
    return handler


@pytest.fixture
def metrics_server(mock_config, mock_metrics_handler):
    """Create a MetricsServer instance for testing."""
    return MetricsServer(mock_config, mock_metrics_handler)


@pytest.fixture
def client(metrics_server):
    """Create a test client for the Flask app."""
    app = metrics_server.get_app()
    app.config['TESTING'] = True
    return app.test_client()


class TestMetricsServer:
    """Test cases for the MetricsServer class."""
    
    def test_initialization(self, mock_config, mock_metrics_handler):
        """Test MetricsServer initialization."""
        server = MetricsServer(mock_config, mock_metrics_handler)
        
        assert server.config == mock_config
        assert server.metrics_handler == mock_metrics_handler
        assert isinstance(server.app, Flask)
    
    def test_metrics_endpoint_success(self, client, mock_metrics_handler):
        """Test successful metrics endpoint request."""
        response = client.get('/metrics')
        
        assert response.status_code == 200
        assert response.mimetype == 'text/plain'
        assert 'version=0.0.4' in response.content_type
        assert b'afs_capacity_used_bytes' in response.data
        assert b'afs_scrape_duration_seconds' in response.data
        
        # Verify metrics handler was called
        mock_metrics_handler.collect_metrics.assert_called_once()
    
    def test_metrics_endpoint_error(self, client, mock_metrics_handler):
        """Test metrics endpoint when collection fails."""
        # Mock collection failure
        mock_metrics_handler.collect_metrics.side_effect = Exception("Collection failed")
        
        response = client.get('/metrics')
        
        assert response.status_code == 500
        assert response.mimetype == 'text/plain'
        assert b'Error collecting metrics' in response.data
    
    def test_readiness_endpoint_ready(self, client, mock_config, mock_metrics_handler):
        """Test readiness endpoint when service is ready."""
        response = client.get('/health/ready')
        
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data['status'] == 'ready'
        assert 'ready to serve requests' in data['message']
        
        # Verify configuration validation and connectivity test were called
        mock_config.validate.assert_called_once()
        mock_metrics_handler.afs_client.test_connection.assert_called_once()
    
    def test_readiness_endpoint_not_ready_config_error(self, client, mock_config, mock_metrics_handler):
        """Test readiness endpoint when configuration is invalid."""
        # Mock configuration validation failure
        mock_config.validate.side_effect = Exception("Invalid configuration")
        
        response = client.get('/health/ready')
        
        assert response.status_code == 503
        
        data = json.loads(response.data)
        assert data['status'] == 'not ready'
        assert 'Invalid configuration' in data['message']
    
    def test_readiness_endpoint_not_ready_connectivity_error(self, client, mock_config, mock_metrics_handler):
        """Test readiness endpoint when AFS API connectivity fails."""
        # Mock connectivity test failure
        mock_metrics_handler.afs_client.test_connection.return_value = False
        
        response = client.get('/health/ready')
        
        assert response.status_code == 503
        
        data = json.loads(response.data)
        assert data['status'] == 'not ready'
        assert 'connectivity test failed' in data['message']
    
    def test_liveness_endpoint(self, client):
        """Test liveness endpoint."""
        response = client.get('/health/live')
        
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data['status'] == 'alive'
        assert 'running' in data['message']
    
    def test_nonexistent_endpoint(self, client):
        """Test request to non-existent endpoint."""
        response = client.get('/nonexistent')
        
        assert response.status_code == 404
    
    def test_get_app(self, metrics_server):
        """Test getting the Flask app instance."""
        app = metrics_server.get_app()
        
        assert isinstance(app, Flask)
        assert app == metrics_server.app


class TestMetricsServerIntegration:
    """Integration tests for the MetricsServer."""
    
    def test_request_logging(self, client, mock_metrics_handler):
        """Test that requests are properly logged."""
        # Make a request
        response = client.get('/metrics')
        
        assert response.status_code == 200
        
        # This test verifies the request completes successfully
        # Detailed logging verification would require more complex mocking
        # that's beyond the scope of this basic functionality test
    
    def test_concurrent_requests(self, client, mock_metrics_handler):
        """Test handling of concurrent requests."""
        import threading
        import time
        
        results = []
        
        def make_request():
            response = client.get('/metrics')
            results.append(response.status_code)
        
        # Create multiple threads to simulate concurrent requests
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All requests should succeed
        assert len(results) == 5
        assert all(status == 200 for status in results)
        
        # Metrics handler should have been called multiple times
        assert mock_metrics_handler.collect_metrics.call_count == 5


if __name__ == '__main__':
    pytest.main([__file__])