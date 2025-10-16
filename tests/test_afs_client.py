"""
Unit tests for AFS API client authentication and API functionality.
"""

import pytest
import hashlib
import hmac
import base64
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
import requests

from src.afs_client import AFSClient
from src.exceptions import AuthenticationError, APIError


class TestAFSClientAuthentication:
    """Test cases for AFS client authentication functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.access_key = "test_access_key"
        self.secret_key = "test_secret_key"
        self.base_url = "https://afs.example.com"
        self.client = AFSClient(self.access_key, self.secret_key, self.base_url)
    
    def test_init(self):
        """Test AFSClient initialization."""
        assert self.client.access_key == self.access_key
        assert self.client.secret_key == self.secret_key
        assert self.client.base_url == self.base_url
    
    def test_init_strips_trailing_slash(self):
        """Test that trailing slash is stripped from base URL."""
        client = AFSClient(self.access_key, self.secret_key, "https://afs.example.com/")
        assert client.base_url == "https://afs.example.com"
    
    def test_get_current_date_format(self):
        """Test that current date is returned in correct GMT format."""
        date_string = self.client._get_current_date()
        
        # Verify format matches expected pattern (e.g., 'Wed, 15 Oct 2025 10:30:45 GMT')
        assert date_string.endswith(' GMT')
        assert len(date_string.split()) == 6
        
        # Verify it can be parsed back to datetime
        parsed_date = datetime.strptime(date_string, '%a, %d %b %Y %H:%M:%S %Z')
        assert parsed_date is not None
    
    def test_generate_signature_with_known_values(self):
        """Test HMAC signature generation with known values."""
        # Known test values
        date_string = "Wed, 15 Oct 2025 10:30:45 GMT"
        method = "GET"
        path = "/storage/afs/data/v1/volume/test-volume/dir_quotas"
        content_type = ""
        
        # Expected string to sign
        expected_string_to_sign = f"{method}\n{content_type}\n{date_string}\n{path}"
        
        # Calculate expected signature manually
        expected_signature = hmac.new(
            self.secret_key.encode('utf-8'),
            expected_string_to_sign.encode('utf-8'),
            hashlib.sha256
        ).digest()
        expected_signature_b64 = base64.b64encode(expected_signature).decode('utf-8')
        
        # Test the method
        actual_signature = self.client._generate_signature(date_string, method, path, content_type)
        
        assert actual_signature == expected_signature_b64
    
    def test_generate_signature_different_methods(self):
        """Test signature generation with different HTTP methods."""
        date_string = "Wed, 15 Oct 2025 10:30:45 GMT"
        path = "/api/v1/test"
        
        get_signature = self.client._generate_signature(date_string, "GET", path)
        post_signature = self.client._generate_signature(date_string, "POST", path)
        
        # Different methods should produce different signatures
        assert get_signature != post_signature
    
    def test_generate_signature_different_paths(self):
        """Test signature generation with different paths."""
        date_string = "Wed, 15 Oct 2025 10:30:45 GMT"
        method = "GET"
        
        path1_signature = self.client._generate_signature(date_string, method, "/api/v1/path1")
        path2_signature = self.client._generate_signature(date_string, method, "/api/v1/path2")
        
        # Different paths should produce different signatures
        assert path1_signature != path2_signature
    
    def test_generate_signature_with_content_type(self):
        """Test signature generation with content type."""
        date_string = "Wed, 15 Oct 2025 10:30:45 GMT"
        method = "POST"
        path = "/api/v1/test"
        
        no_content_type = self.client._generate_signature(date_string, method, path, "")
        with_content_type = self.client._generate_signature(date_string, method, path, "application/json")
        
        # Different content types should produce different signatures
        assert no_content_type != with_content_type
    
    def test_generate_signature_error_handling(self):
        """Test signature generation error handling."""
        # Test with invalid secret key type
        client = AFSClient(self.access_key, None, self.base_url)
        
        with pytest.raises(AuthenticationError) as exc_info:
            client._generate_signature("Wed, 15 Oct 2025 10:30:45 GMT", "GET", "/test")
        
        assert "Signature generation failed" in str(exc_info.value)
    
    @patch('src.afs_client.AFSClient._get_current_date')
    def test_create_auth_headers(self, mock_get_date):
        """Test authentication headers creation."""
        # Mock the current date
        mock_date = "Wed, 15 Oct 2025 10:30:45 GMT"
        mock_get_date.return_value = mock_date
        
        method = "GET"
        path = "/storage/afs/data/v1/volume/test/dir_quotas"
        
        headers = self.client._create_auth_headers(method, path)
        
        # Verify headers structure
        assert 'X-Date' in headers
        assert 'Authorization' in headers
        assert headers['X-Date'] == mock_date
        assert headers['Authorization'].startswith(f"AWS {self.access_key}:")
        
        # Verify authorization header format
        auth_parts = headers['Authorization'].split(':')
        assert len(auth_parts) == 2
        assert auth_parts[0] == f"AWS {self.access_key}"
        
        # Verify signature is base64 encoded
        signature = auth_parts[1]
        try:
            base64.b64decode(signature)
        except Exception:
            pytest.fail("Signature is not valid base64")
    
    def test_create_auth_headers_error_handling(self):
        """Test authentication headers creation error handling."""
        # Test with invalid client setup
        client = AFSClient(self.access_key, None, self.base_url)
        
        with pytest.raises(AuthenticationError) as exc_info:
            client._create_auth_headers("GET", "/test")
        
        assert "Authentication header creation failed" in str(exc_info.value)


class TestAFSClientAPI:
    """Test cases for AFS client API functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.access_key = "test_access_key"
        self.secret_key = "test_secret_key"
        self.base_url = "https://afs.example.com"
        self.client = AFSClient(self.access_key, self.secret_key, self.base_url)
        self.volume_id = "test-volume-id"
        self.zone = "test-zone"
    
    @patch('requests.get')
    @patch('src.afs_client.AFSClient._create_auth_headers')
    def test_get_volume_quotas_success(self, mock_auth_headers, mock_requests_get):
        """Test successful volume quota retrieval."""
        # Mock authentication headers
        mock_auth_headers.return_value = {
            'X-Date': 'Wed, 15 Oct 2025 10:30:45 GMT',
            'Authorization': 'AWS test_access_key:mock_signature'
        }
        
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "dir_quota_list": [
                {
                    "volume_id": self.volume_id,
                    "dir_path": "/test",
                    "file_quantity_quota": 1000,
                    "file_quantity_used_quota": 500,
                    "capacity_quota": 1073741824,
                    "capacity_used_quota": 536870912,
                    "state": 1
                }
            ]
        }
        mock_requests_get.return_value = mock_response
        
        # Test the method
        result = self.client.get_volume_quotas(self.volume_id, self.zone)
        
        # Verify the result
        assert "dir_quota_list" in result
        assert len(result["dir_quota_list"]) == 1
        assert result["dir_quota_list"][0]["volume_id"] == self.volume_id
        
        # Verify API call was made correctly
        expected_url = f"{self.base_url}/storage/afs/data/v1/volume/{self.volume_id}/dir_quotas"
        expected_headers = {
            'X-Date': 'Wed, 15 Oct 2025 10:30:45 GMT',
            'Authorization': 'hmac accesskey="test_access_key",algorithm="hmac-sha256",headers="x-date",signature="mock_signature"',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        expected_params = {'volume_id': self.volume_id, 'zone': self.zone}
        
        mock_requests_get.assert_called_once_with(
            expected_url,
            headers=expected_headers,
            params=expected_params,
            timeout=30
        )
    
    @patch('requests.get')
    @patch('src.afs_client.AFSClient._create_auth_headers')
    def test_get_volume_quotas_authentication_error_401(self, mock_auth_headers, mock_requests_get):
        """Test handling of 401 authentication error."""
        mock_auth_headers.return_value = {'X-Date': 'test', 'Authorization': 'test'}
        
        # Mock 401 response
        mock_response = Mock()
        mock_response.status_code = 401
        mock_requests_get.return_value = mock_response
        
        with pytest.raises(AuthenticationError) as exc_info:
            self.client.get_volume_quotas(self.volume_id, self.zone)
        
        assert "Invalid credentials or signature" in str(exc_info.value)
    
    @patch('requests.get')
    @patch('src.afs_client.AFSClient._create_auth_headers')
    def test_get_volume_quotas_forbidden_error_403(self, mock_auth_headers, mock_requests_get):
        """Test handling of 403 forbidden error."""
        mock_auth_headers.return_value = {'X-Date': 'test', 'Authorization': 'test'}
        
        # Mock 403 response
        mock_response = Mock()
        mock_response.status_code = 403
        mock_requests_get.return_value = mock_response
        
        with pytest.raises(AuthenticationError) as exc_info:
            self.client.get_volume_quotas(self.volume_id, self.zone)
        
        assert "Access forbidden - check permissions" in str(exc_info.value)
    
    @patch('requests.get')
    @patch('src.afs_client.AFSClient._create_auth_headers')
    def test_get_volume_quotas_not_found_error_404(self, mock_auth_headers, mock_requests_get):
        """Test handling of 404 not found error."""
        mock_auth_headers.return_value = {'X-Date': 'test', 'Authorization': 'test'}
        
        # Mock 404 response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_requests_get.return_value = mock_response
        
        with pytest.raises(APIError) as exc_info:
            self.client.get_volume_quotas(self.volume_id, self.zone)
        
        assert f"Volume {self.volume_id} not found in zone {self.zone}" in str(exc_info.value)
    
    @patch('requests.get')
    @patch('src.afs_client.AFSClient._create_auth_headers')
    def test_get_volume_quotas_client_error_400(self, mock_auth_headers, mock_requests_get):
        """Test handling of 400 client error."""
        mock_auth_headers.return_value = {'X-Date': 'test', 'Authorization': 'test'}
        
        # Mock 400 response
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"
        mock_requests_get.return_value = mock_response
        
        with pytest.raises(APIError) as exc_info:
            self.client.get_volume_quotas(self.volume_id, self.zone)
        
        assert "Client error 400: Bad request" in str(exc_info.value)
    
    @patch('requests.get')
    @patch('src.afs_client.AFSClient._create_auth_headers')
    def test_get_volume_quotas_server_error_500(self, mock_auth_headers, mock_requests_get):
        """Test handling of 500 server error."""
        mock_auth_headers.return_value = {'X-Date': 'test', 'Authorization': 'test'}
        
        # Mock 500 response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"
        mock_requests_get.return_value = mock_response
        
        with pytest.raises(APIError) as exc_info:
            self.client.get_volume_quotas(self.volume_id, self.zone)
        
        assert "Server error 500: Internal server error" in str(exc_info.value)
    
    @patch('requests.get')
    @patch('src.afs_client.AFSClient._create_auth_headers')
    def test_get_volume_quotas_unexpected_status_code(self, mock_auth_headers, mock_requests_get):
        """Test handling of unexpected status codes."""
        mock_auth_headers.return_value = {'X-Date': 'test', 'Authorization': 'test'}
        
        # Mock unexpected status code (418 is in 400-499 range, so use a different code)
        mock_response = Mock()
        mock_response.status_code = 418  # I'm a teapot (this is actually a client error)
        mock_response.text = "I'm a teapot"
        mock_requests_get.return_value = mock_response
        
        with pytest.raises(APIError) as exc_info:
            self.client.get_volume_quotas(self.volume_id, self.zone)
        
        assert "Client error 418: I'm a teapot" in str(exc_info.value)
    
    @patch('requests.get')
    @patch('src.afs_client.AFSClient._create_auth_headers')
    def test_get_volume_quotas_invalid_json(self, mock_auth_headers, mock_requests_get):
        """Test handling of invalid JSON response."""
        mock_auth_headers.return_value = {'X-Date': 'test', 'Authorization': 'test'}
        
        # Mock response with invalid JSON
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_requests_get.return_value = mock_response
        
        with pytest.raises(APIError) as exc_info:
            self.client.get_volume_quotas(self.volume_id, self.zone)
        
        assert "Invalid JSON response" in str(exc_info.value)
    
    @patch('requests.get')
    @patch('src.afs_client.AFSClient._create_auth_headers')
    def test_get_volume_quotas_timeout(self, mock_auth_headers, mock_requests_get):
        """Test handling of request timeout."""
        mock_auth_headers.return_value = {'X-Date': 'test', 'Authorization': 'test'}
        
        # Mock timeout exception
        mock_requests_get.side_effect = requests.exceptions.Timeout()
        
        with pytest.raises(APIError) as exc_info:
            self.client.get_volume_quotas(self.volume_id, self.zone, timeout=10)
        
        assert "Request timeout after 10 seconds" in str(exc_info.value)
    
    @patch('requests.get')
    @patch('src.afs_client.AFSClient._create_auth_headers')
    def test_get_volume_quotas_connection_error(self, mock_auth_headers, mock_requests_get):
        """Test handling of connection error."""
        mock_auth_headers.return_value = {'X-Date': 'test', 'Authorization': 'test'}
        
        # Mock connection error
        mock_requests_get.side_effect = requests.exceptions.ConnectionError("Connection failed")
        
        with pytest.raises(APIError) as exc_info:
            self.client.get_volume_quotas(self.volume_id, self.zone)
        
        assert "Connection error: Connection failed" in str(exc_info.value)
    
    @patch('requests.get')
    @patch('src.afs_client.AFSClient._create_auth_headers')
    def test_get_volume_quotas_request_exception(self, mock_auth_headers, mock_requests_get):
        """Test handling of general request exception."""
        mock_auth_headers.return_value = {'X-Date': 'test', 'Authorization': 'test'}
        
        # Mock general request exception
        mock_requests_get.side_effect = requests.exceptions.RequestException("Request failed")
        
        with pytest.raises(APIError) as exc_info:
            self.client.get_volume_quotas(self.volume_id, self.zone)
        
        assert "Request error: Request failed" in str(exc_info.value)
    
    @patch('src.afs_client.AFSClient._create_auth_headers')
    def test_get_volume_quotas_auth_header_creation_failure(self, mock_auth_headers):
        """Test handling of authentication header creation failure."""
        # Mock authentication header creation failure
        mock_auth_headers.side_effect = AuthenticationError("Auth header creation failed")
        
        with pytest.raises(AuthenticationError) as exc_info:
            self.client.get_volume_quotas(self.volume_id, self.zone)
        
        assert "Auth header creation failed" in str(exc_info.value)
    
    @patch('requests.get')
    @patch('src.afs_client.AFSClient._create_auth_headers')
    def test_get_volume_quotas_unexpected_exception(self, mock_auth_headers, mock_requests_get):
        """Test handling of unexpected exceptions."""
        mock_auth_headers.return_value = {'X-Date': 'test', 'Authorization': 'test'}
        
        # Mock unexpected exception
        mock_requests_get.side_effect = Exception("Unexpected error")
        
        with pytest.raises(APIError) as exc_info:
            self.client.get_volume_quotas(self.volume_id, self.zone)
        
        assert "Unexpected error: Unexpected error" in str(exc_info.value)
    
    @patch('requests.get')
    @patch('src.afs_client.AFSClient._create_auth_headers')
    def test_get_volume_quotas_custom_timeout(self, mock_auth_headers, mock_requests_get):
        """Test volume quota retrieval with custom timeout."""
        mock_auth_headers.return_value = {'X-Date': 'test', 'Authorization': 'test'}
        
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"dir_quota_list": []}
        mock_requests_get.return_value = mock_response
        
        # Test with custom timeout
        custom_timeout = 60
        self.client.get_volume_quotas(self.volume_id, self.zone, timeout=custom_timeout)
        
        # Verify timeout was passed correctly
        call_args = mock_requests_get.call_args
        assert call_args[1]['timeout'] == custom_timeout


class TestAFSClientConnectionTest:
    """Test cases for AFS client connection testing functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.access_key = "test_access_key"
        self.secret_key = "test_secret_key"
        self.base_url = "https://afs.example.com"
        self.client = AFSClient(self.access_key, self.secret_key, self.base_url)
    
    @patch('src.afs_client.AFSClient._create_auth_headers')
    def test_connection_test_success(self, mock_auth_headers):
        """Test successful connection test."""
        mock_auth_headers.return_value = {'X-Date': 'test', 'Authorization': 'test'}
        
        result = self.client.test_connection()
        
        assert result is True
        mock_auth_headers.assert_called_once()
    
    @patch('src.afs_client.AFSClient._create_auth_headers')
    def test_connection_test_failure(self, mock_auth_headers):
        """Test connection test failure."""
        mock_auth_headers.side_effect = AuthenticationError("Auth failed")
        
        result = self.client.test_connection()
        
        assert result is False
        mock_auth_headers.assert_called_once()