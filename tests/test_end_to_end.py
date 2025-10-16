"""
End-to-end integration tests for AFS Prometheus metrics system.

This module tests the complete flow from HTTP request through AFS API
to Prometheus output, verifying metrics format compatibility and using
actual dir_quota_list response structures.
"""

import pytest
import json
import time
import threading
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, List
import requests

from src.config import Config, AFSConfig, VolumeConfig, ServerConfig, CollectionConfig, LoggingConfig
from src.afs_client import AFSClient
from src.metrics_transformer import MetricsTransformer
from src.metrics_handler import MetricsHandler
from src.http_server import MetricsServer
from src.data_models import PrometheusMetric, AFSQuotaData
from src.exceptions import AuthenticationError, APIError
from src.retry_handler import create_retry_config


class TestEndToEndFlow:
    """End-to-end tests for the complete AFS metrics collection flow."""
    
    @pytest.fixture
    def real_afs_response(self):
        """Real AFS API response structure from the design document."""
        return {
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
                    "file_quantity_quota": 0,
                    "file_quantity_used_quota": 58108,
                    "capacity_quota": 0,
                    "capacity_used_quota": 5619439059,
                    "state": 1
                },
                {
                    "volume_id": "80433778-429e-11ef-bc97-4eca24dcdba9",
                    "dir_path": "/models",
                    "file_quantity_quota": 1000000,
                    "file_quantity_used_quota": 125000,
                    "capacity_quota": 1073741824000,  # 1TB
                    "capacity_used_quota": 536870912000,  # 500GB
                    "state": 1
                }
            ]
        }
    
    @pytest.fixture
    def multi_volume_afs_response(self):
        """AFS API response for multiple volumes."""
        return {
            "volume_1": {
                "dir_quota_list": [
                    {
                        "volume_id": "volume-1-id",
                        "dir_path": "/data",
                        "file_quantity_quota": 500000,
                        "file_quantity_used_quota": 250000,
                        "capacity_quota": 2147483648000,  # 2TB
                        "capacity_used_quota": 1073741824000,  # 1TB
                        "state": 1
                    }
                ]
            },
            "volume_2": {
                "dir_quota_list": [
                    {
                        "volume_id": "volume-2-id",
                        "dir_path": "/backup",
                        "file_quantity_quota": 0,
                        "file_quantity_used_quota": 100000,
                        "capacity_quota": 0,
                        "capacity_used_quota": 500000000000,  # 500GB
                        "state": 1
                    }
                ]
            }
        }
    
    @pytest.fixture
    def complete_config(self):
        """Complete configuration for end-to-end testing."""
        config = Config()
        
        config.afs = AFSConfig(
            access_key="test_access_key_12345",
            secret_key="test_secret_key_67890",
            base_url="https://afs.cn-sh-01.sensecoreapi.cn",
            volumes=[
                VolumeConfig(volume_id="80433778-429e-11ef-bc97-4eca24dcdba9", zone="cn-sh-01e"),
                VolumeConfig(volume_id="volume-1-id", zone="us-west-1"),
                VolumeConfig(volume_id="volume-2-id", zone="eu-central-1")
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
        
        config.logging = LoggingConfig(
            level="INFO",
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        
        return config
    
    def test_complete_flow_single_volume(self, complete_config, real_afs_response):
        """Test complete flow from HTTP request to Prometheus output with single volume."""
        # Mock the requests.get call to return our test data
        with patch('requests.get') as mock_get:
            # Configure mock response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = real_afs_response
            mock_get.return_value = mock_response
            
            # Create retry configuration
            retry_config = create_retry_config(
                max_attempts=3,
                base_delay=2.0,
                max_delay=30.0
            )
            
            # Create real components
            afs_client = AFSClient(
                access_key=complete_config.afs.access_key,
                secret_key=complete_config.afs.secret_key,
                base_url=complete_config.afs.base_url,
                retry_config=retry_config
            )
            
            transformer = MetricsTransformer()
            
            # Use only the first volume for this test
            single_volume_config = Config()
            single_volume_config.afs = AFSConfig(
                access_key=complete_config.afs.access_key,
                secret_key=complete_config.afs.secret_key,
                base_url=complete_config.afs.base_url,
                volumes=[complete_config.afs.volumes[0]]  # Only first volume
            )
            single_volume_config.server = complete_config.server
            single_volume_config.collection = complete_config.collection
            single_volume_config.logging = complete_config.logging
            
            metrics_handler = MetricsHandler(single_volume_config, afs_client, transformer)
            server = MetricsServer(single_volume_config, metrics_handler)
            
            # Create test client
            app = server.get_app()
            app.config['TESTING'] = True
            client = app.test_client()
            
            # Make request to metrics endpoint
            response = client.get('/metrics')
            
            # Verify response
            assert response.status_code == 200
            assert response.mimetype == 'text/plain'
            assert 'version=0.0.4' in response.content_type
            
            response_text = response.data.decode('utf-8')
            
            # Verify API was called correctly
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            
            # Check URL construction
            expected_url = "https://afs.cn-sh-01.sensecoreapi.cn/storage/afs/data/v1/volume/80433778-429e-11ef-bc97-4eca24dcdba9/dir_quotas"
            assert call_args[0][0] == expected_url
            
            # Check headers include authentication
            headers = call_args[1]['headers']
            assert 'X-Date' in headers
            assert 'Authorization' in headers
            assert 'hmac accesskey="test_access_key_12345"' in headers['Authorization']
            assert headers['Content-Type'] == 'application/json'
            assert headers['Accept'] == 'application/json'
            
            # Check parameters
            params = call_args[1]['params']
            assert params['volume_id'] == '80433778-429e-11ef-bc97-4eca24dcdba9'
            assert params['zone'] == 'cn-sh-01e'
            
            # Check timeout
            assert call_args[1]['timeout'] == 25
            
            # Verify Prometheus metrics format
            self._verify_prometheus_format(response_text)
            
            # Verify specific metrics from the real AFS response
            self._verify_real_afs_metrics(response_text, real_afs_response)
    
    def test_complete_flow_multiple_volumes(self, complete_config, multi_volume_afs_response):
        """Test complete flow with multiple volumes and concurrent collection."""
        # Mock the requests.get call to return different data based on volume
        def mock_get_side_effect(url, **kwargs):
            mock_response = Mock()
            mock_response.status_code = 200
            
            if "volume-1-id" in url:
                mock_response.json.return_value = multi_volume_afs_response["volume_1"]
            elif "volume-2-id" in url:
                mock_response.json.return_value = multi_volume_afs_response["volume_2"]
            else:
                # Default to first volume response for the main volume
                mock_response.json.return_value = {
                    "dir_quota_list": [
                        {
                            "volume_id": "80433778-429e-11ef-bc97-4eca24dcdba9",
                            "dir_path": "/test",
                            "file_quantity_quota": 1000,
                            "file_quantity_used_quota": 500,
                            "capacity_quota": 1000000000,
                            "capacity_used_quota": 500000000,
                            "state": 1
                        }
                    ]
                }
            
            return mock_response
        
        with patch('requests.get', side_effect=mock_get_side_effect) as mock_get:
            # Create retry configuration
            retry_config = create_retry_config(
                max_attempts=3,
                base_delay=2.0,
                max_delay=30.0
            )
            
            # Create real components
            afs_client = AFSClient(
                access_key=complete_config.afs.access_key,
                secret_key=complete_config.afs.secret_key,
                base_url=complete_config.afs.base_url,
                retry_config=retry_config
            )
            
            transformer = MetricsTransformer()
            metrics_handler = MetricsHandler(complete_config, afs_client, transformer)
            server = MetricsServer(complete_config, metrics_handler)
            
            # Create test client
            app = server.get_app()
            app.config['TESTING'] = True
            client = app.test_client()
            
            # Make request to metrics endpoint
            response = client.get('/metrics')
            
            # Verify response
            assert response.status_code == 200
            response_text = response.data.decode('utf-8')
            
            # Verify all volumes were called
            assert mock_get.call_count == 3  # Three volumes configured
            
            # Verify metrics from all volumes are present
            assert 'volume_id="80433778-429e-11ef-bc97-4eca24dcdba9"' in response_text
            assert 'volume_id="volume-1-id"' in response_text
            assert 'volume_id="volume-2-id"' in response_text
            
            # Verify zone labels
            assert 'zone="cn-sh-01e"' in response_text
            assert 'zone="us-west-1"' in response_text
            assert 'zone="eu-central-1"' in response_text
            
            # Verify collection status metrics for all volumes
            assert 'afs_collection_success{volume_id="80433778-429e-11ef-bc97-4eca24dcdba9",zone="cn-sh-01e"} 1.0' in response_text
            assert 'afs_collection_success{volume_id="volume-1-id",zone="us-west-1"} 1.0' in response_text
            assert 'afs_collection_success{volume_id="volume-2-id",zone="eu-central-1"} 1.0' in response_text
            
            # Verify aggregate metrics
            assert 'afs_collection_volumes_total 3.0' in response_text
            assert 'afs_collection_volumes_successful 3.0' in response_text
            assert 'afs_collection_volumes_failed 0.0' in response_text
    
    def test_complete_flow_with_authentication_error(self, complete_config):
        """Test complete flow when AFS API returns authentication error."""
        with patch('requests.get') as mock_get:
            # Configure mock to return 401 Unauthorized
            mock_response = Mock()
            mock_response.status_code = 401
            mock_get.return_value = mock_response
            
            # Create retry configuration
            retry_config = create_retry_config(
                max_attempts=3,
                base_delay=2.0,
                max_delay=30.0
            )
            
            # Create real components
            afs_client = AFSClient(
                access_key=complete_config.afs.access_key,
                secret_key=complete_config.afs.secret_key,
                base_url=complete_config.afs.base_url,
                retry_config=retry_config
            )
            
            transformer = MetricsTransformer()
            
            # Use single volume for this test
            single_volume_config = Config()
            single_volume_config.afs = AFSConfig(
                access_key=complete_config.afs.access_key,
                secret_key=complete_config.afs.secret_key,
                base_url=complete_config.afs.base_url,
                volumes=[complete_config.afs.volumes[0]]
            )
            single_volume_config.server = complete_config.server
            single_volume_config.collection = complete_config.collection
            single_volume_config.logging = complete_config.logging
            
            metrics_handler = MetricsHandler(single_volume_config, afs_client, transformer)
            server = MetricsServer(single_volume_config, metrics_handler)
            
            # Create test client
            app = server.get_app()
            app.config['TESTING'] = True
            client = app.test_client()
            
            # Make request to metrics endpoint
            response = client.get('/metrics')
            
            # Should still return 200 with error metrics
            assert response.status_code == 200
            response_text = response.data.decode('utf-8')
            
            # Verify error metrics are present
            assert 'afs_collection_success{volume_id="80433778-429e-11ef-bc97-4eca24dcdba9",zone="cn-sh-01e"} 0.0' in response_text
            assert 'afs_collection_error' in response_text
            assert 'Invalid credentials' in response_text
            
            # Verify scrape timestamp is still present
            assert 'afs_scrape_timestamp' in response_text
    
    def test_complete_flow_with_mixed_success_failure(self, complete_config):
        """Test complete flow with some volumes succeeding and others failing."""
        def mock_get_side_effect(url, **kwargs):
            mock_response = Mock()
            
            if "volume-1-id" in url:
                # Success for volume-1
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "dir_quota_list": [
                        {
                            "volume_id": "volume-1-id",
                            "dir_path": "/success",
                            "file_quantity_quota": 1000,
                            "file_quantity_used_quota": 500,
                            "capacity_quota": 1000000000,
                            "capacity_used_quota": 500000000,
                            "state": 1
                        }
                    ]
                }
            elif "volume-2-id" in url:
                # Failure for volume-2 (404 Not Found)
                mock_response.status_code = 404
            else:
                # Timeout for main volume
                raise requests.exceptions.Timeout("Request timeout")
            
            return mock_response
        
        with patch('requests.get', side_effect=mock_get_side_effect) as mock_get:
            # Create retry configuration
            retry_config = create_retry_config(
                max_attempts=3,
                base_delay=2.0,
                max_delay=30.0
            )
            
            # Create real components
            afs_client = AFSClient(
                access_key=complete_config.afs.access_key,
                secret_key=complete_config.afs.secret_key,
                base_url=complete_config.afs.base_url,
                retry_config=retry_config
            )
            
            transformer = MetricsTransformer()
            metrics_handler = MetricsHandler(complete_config, afs_client, transformer)
            server = MetricsServer(complete_config, metrics_handler)
            
            # Create test client
            app = server.get_app()
            app.config['TESTING'] = True
            client = app.test_client()
            
            # Make request to metrics endpoint
            response = client.get('/metrics')
            
            # Should still return 200 with partial results
            assert response.status_code == 200
            response_text = response.data.decode('utf-8')
            
            # Verify successful volume metrics are present
            assert 'volume_id="volume-1-id"' in response_text
            assert 'dir_path="/success"' in response_text
            assert 'afs_collection_success{volume_id="volume-1-id",zone="us-west-1"} 1.0' in response_text
            
            # Verify failed volume status metrics
            assert 'afs_collection_success{volume_id="80433778-429e-11ef-bc97-4eca24dcdba9",zone="cn-sh-01e"} 0.0' in response_text
            assert 'afs_collection_success{volume_id="volume-2-id",zone="eu-central-1"} 0.0' in response_text
            
            # Verify aggregate metrics show partial failure
            assert 'afs_collection_volumes_total 3.0' in response_text
            assert 'afs_collection_volumes_successful 1.0' in response_text
            assert 'afs_collection_volumes_failed 2.0' in response_text
            
            # Verify error categorization
            assert 'error_category="timeout"' in response_text
            assert 'error_category="api_error"' in response_text
    
    def test_prometheus_format_compatibility(self, complete_config, real_afs_response):
        """Test that output is compatible with Prometheus parser."""
        with patch('requests.get') as mock_get:
            # Configure mock response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = real_afs_response
            mock_get.return_value = mock_response
            
            # Create retry configuration
            retry_config = create_retry_config(
                max_attempts=3,
                base_delay=2.0,
                max_delay=30.0
            )
            
            # Create real components
            afs_client = AFSClient(
                access_key=complete_config.afs.access_key,
                secret_key=complete_config.afs.secret_key,
                base_url=complete_config.afs.base_url,
                retry_config=retry_config
            )
            
            transformer = MetricsTransformer()
            
            # Use single volume for this test
            single_volume_config = Config()
            single_volume_config.afs = AFSConfig(
                access_key=complete_config.afs.access_key,
                secret_key=complete_config.afs.secret_key,
                base_url=complete_config.afs.base_url,
                volumes=[complete_config.afs.volumes[0]]
            )
            single_volume_config.server = complete_config.server
            single_volume_config.collection = complete_config.collection
            single_volume_config.logging = complete_config.logging
            
            metrics_handler = MetricsHandler(single_volume_config, afs_client, transformer)
            server = MetricsServer(single_volume_config, metrics_handler)
            
            # Create test client
            app = server.get_app()
            app.config['TESTING'] = True
            client = app.test_client()
            
            # Make request to metrics endpoint
            response = client.get('/metrics')
            
            assert response.status_code == 200
            response_text = response.data.decode('utf-8')
            
            # Test Prometheus format compatibility
            self._test_prometheus_parser_compatibility(response_text)
    
    def test_concurrent_requests_end_to_end(self, complete_config, real_afs_response):
        """Test concurrent requests to the metrics endpoint."""
        with patch('requests.get') as mock_get:
            # Configure mock response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = real_afs_response
            mock_get.return_value = mock_response
            
            # Create retry configuration
            retry_config = create_retry_config(
                max_attempts=3,
                base_delay=2.0,
                max_delay=30.0
            )
            
            # Create real components
            afs_client = AFSClient(
                access_key=complete_config.afs.access_key,
                secret_key=complete_config.afs.secret_key,
                base_url=complete_config.afs.base_url,
                retry_config=retry_config
            )
            
            transformer = MetricsTransformer()
            
            # Use single volume for this test
            single_volume_config = Config()
            single_volume_config.afs = AFSConfig(
                access_key=complete_config.afs.access_key,
                secret_key=complete_config.afs.secret_key,
                base_url=complete_config.afs.base_url,
                volumes=[complete_config.afs.volumes[0]]
            )
            single_volume_config.server = complete_config.server
            single_volume_config.collection = complete_config.collection
            single_volume_config.logging = complete_config.logging
            
            metrics_handler = MetricsHandler(single_volume_config, afs_client, transformer)
            server = MetricsServer(single_volume_config, metrics_handler)
            
            # Create test client
            app = server.get_app()
            app.config['TESTING'] = True
            
            # Function to make concurrent requests
            results = []
            errors = []
            
            def make_request():
                try:
                    with app.test_client() as client:
                        response = client.get('/metrics')
                        results.append({
                            'status_code': response.status_code,
                            'content_length': len(response.data),
                            'content_type': response.content_type
                        })
                except Exception as e:
                    errors.append(str(e))
            
            # Create and start multiple threads
            threads = []
            num_requests = 10
            
            for _ in range(num_requests):
                thread = threading.Thread(target=make_request)
                threads.append(thread)
            
            # Start all threads
            for thread in threads:
                thread.start()
            
            # Wait for all threads to complete
            for thread in threads:
                thread.join()
            
            # Verify results
            assert len(errors) == 0, f"Errors occurred: {errors}"
            assert len(results) == num_requests
            
            # All requests should succeed
            for result in results:
                assert result['status_code'] == 200
                assert result['content_length'] > 0
                assert 'text/plain' in result['content_type']
            
            # Due to caching, AFS API should only be called once
            assert mock_get.call_count == 1
    
    def test_health_endpoints_end_to_end(self, complete_config):
        """Test health check endpoints in end-to-end flow."""
        with patch('src.afs_client.AFSClient.test_connection', return_value=True):
            # Create retry configuration
            retry_config = create_retry_config(
                max_attempts=3,
                base_delay=2.0,
                max_delay=30.0
            )
            
            # Create real components
            afs_client = AFSClient(
                access_key=complete_config.afs.access_key,
                secret_key=complete_config.afs.secret_key,
                base_url=complete_config.afs.base_url,
                retry_config=retry_config
            )
            
            transformer = MetricsTransformer()
            metrics_handler = MetricsHandler(complete_config, afs_client, transformer)
            server = MetricsServer(complete_config, metrics_handler)
            
            # Create test client
            app = server.get_app()
            app.config['TESTING'] = True
            client = app.test_client()
            
            # Test liveness endpoint
            response = client.get('/health/live')
            assert response.status_code == 200
            
            data = json.loads(response.data)
            assert data['status'] == 'alive'
            assert 'running' in data['message']
            
            # Test readiness endpoint
            response = client.get('/health/ready')
            assert response.status_code == 200
            
            data = json.loads(response.data)
            assert data['status'] == 'ready'
            assert 'ready to serve requests' in data['message']
    
    def _verify_prometheus_format(self, metrics_text: str):
        """Verify that metrics text follows Prometheus exposition format."""
        lines = metrics_text.strip().split('\n')
        
        # Should have HELP and TYPE lines
        help_lines = [line for line in lines if line.startswith('# HELP')]
        type_lines = [line for line in lines if line.startswith('# TYPE')]
        metric_lines = [line for line in lines if not line.startswith('#') and line.strip()]
        
        assert len(help_lines) > 0, "Should have HELP lines"
        assert len(type_lines) > 0, "Should have TYPE lines"
        assert len(metric_lines) > 0, "Should have metric lines"
        
        # Each metric should have corresponding HELP and TYPE
        metric_names = set()
        for line in metric_lines:
            if '{' in line:
                metric_name = line.split('{')[0]
            else:
                metric_name = line.split(' ')[0]
            metric_names.add(metric_name)
        
        for metric_name in metric_names:
            help_found = any(f'# HELP {metric_name}' in line for line in help_lines)
            type_found = any(f'# TYPE {metric_name}' in line for line in type_lines)
            assert help_found, f"Missing HELP for {metric_name}"
            assert type_found, f"Missing TYPE for {metric_name}"
    
    def _verify_real_afs_metrics(self, metrics_text: str, afs_response: Dict):
        """Verify that metrics contain expected values from real AFS response."""
        # Check for expected metric names
        expected_metrics = [
            'afs_capacity_used_bytes',
            'afs_capacity_quota_bytes',
            'afs_file_quantity_used',
            'afs_file_quantity_quota',
            'afs_directory_state',
            'afs_scrape_duration_seconds',
            'afs_scrape_timestamp'
        ]
        
        for metric_name in expected_metrics:
            assert metric_name in metrics_text, f"Missing metric {metric_name}"
        
        # Check specific values from the AFS response
        dir_quota_list = afs_response['dir_quota_list']
        
        # Check /datasets directory metrics
        datasets_dir = next(d for d in dir_quota_list if d['dir_path'] == '/datasets')
        assert f'afs_capacity_used_bytes{{dir_path="/datasets",volume_id="80433778-429e-11ef-bc97-4eca24dcdba9",zone="cn-sh-01e"}} {float(datasets_dir["capacity_used_quota"])}' in metrics_text
        assert f'afs_file_quantity_used{{dir_path="/datasets",volume_id="80433778-429e-11ef-bc97-4eca24dcdba9",zone="cn-sh-01e"}} {float(datasets_dir["file_quantity_used_quota"])}' in metrics_text
        
        # Check /models directory with quotas and utilization
        models_dir = next(d for d in dir_quota_list if d['dir_path'] == '/models')
        assert f'afs_capacity_quota_bytes{{dir_path="/models",volume_id="80433778-429e-11ef-bc97-4eca24dcdba9",zone="cn-sh-01e"}} {float(models_dir["capacity_quota"])}' in metrics_text
        assert f'afs_file_quantity_quota{{dir_path="/models",volume_id="80433778-429e-11ef-bc97-4eca24dcdba9",zone="cn-sh-01e"}} {float(models_dir["file_quantity_quota"])}' in metrics_text
        
        # Check utilization metrics for /models (has quotas)
        expected_capacity_util = (models_dir["capacity_used_quota"] / models_dir["capacity_quota"]) * 100
        expected_file_util = (models_dir["file_quantity_used_quota"] / models_dir["file_quantity_quota"]) * 100
        
        assert f'afs_capacity_utilization_percent{{dir_path="/models",volume_id="80433778-429e-11ef-bc97-4eca24dcdba9",zone="cn-sh-01e"}} {expected_capacity_util}' in metrics_text
        assert f'afs_file_quantity_utilization_percent{{dir_path="/models",volume_id="80433778-429e-11ef-bc97-4eca24dcdba9",zone="cn-sh-01e"}} {expected_file_util}' in metrics_text
        
        # Verify no utilization metrics for unlimited quotas (/datasets, /guhao)
        assert 'afs_capacity_utilization_percent{dir_path="/datasets"' not in metrics_text
        assert 'afs_file_quantity_utilization_percent{dir_path="/datasets"' not in metrics_text
        assert 'afs_capacity_utilization_percent{dir_path="/guhao"' not in metrics_text
        assert 'afs_file_quantity_utilization_percent{dir_path="/guhao"' not in metrics_text
    
    def _test_prometheus_parser_compatibility(self, metrics_text: str):
        """Test compatibility with Prometheus text format parser."""
        lines = metrics_text.strip().split('\n')
        
        current_metric = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('# HELP'):
                # HELP line format: # HELP metric_name description
                parts = line.split(' ', 3)
                assert len(parts) >= 3, f"Invalid HELP line format: {line}"
                current_metric = parts[2]
                
            elif line.startswith('# TYPE'):
                # TYPE line format: # TYPE metric_name type
                parts = line.split(' ', 3)
                assert len(parts) >= 3, f"Invalid TYPE line format: {line}"
                metric_name = parts[2]
                metric_type = parts[3]
                assert metric_type in ['counter', 'gauge', 'histogram', 'summary'], f"Invalid metric type: {metric_type}"
                
            elif not line.startswith('#'):
                # Metric line format: metric_name{labels} value [timestamp]
                if '{' in line:
                    # Has labels
                    metric_part, rest = line.split('}', 1)
                    metric_name = metric_part.split('{')[0]
                    labels_part = metric_part.split('{')[1]
                    
                    # Validate labels format
                    if labels_part:
                        # Simple validation - should have key="value" pairs
                        assert '=' in labels_part, f"Invalid labels format: {labels_part}"
                        assert '"' in labels_part, f"Label values should be quoted: {labels_part}"
                    
                    value_part = rest.strip().split()[0]
                else:
                    # No labels
                    parts = line.split()
                    metric_name = parts[0]
                    value_part = parts[1]
                
                # Validate metric name
                assert metric_name.replace('_', '').replace(':', '').isalnum(), f"Invalid metric name: {metric_name}"
                
                # Validate value is numeric
                try:
                    float(value_part)
                except ValueError:
                    pytest.fail(f"Invalid metric value: {value_part}")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])