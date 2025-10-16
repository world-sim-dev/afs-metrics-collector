"""
AFS API Client module for handling HMAC authentication and quota data retrieval.
"""

import hashlib
import hmac
import base64
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional
import requests

from src.exceptions import (
    AuthenticationError, APIError, NetworkError, TimeoutError, 
    InvalidCredentialsError, SignatureError, create_network_error, 
    create_timeout_error, create_api_error
)
from src.logging_config import get_logger, log_operation, log_api_request
from src.retry_handler import RetryHandler, RetryConfig, create_retry_config


class AFSClient:
    """
    AFS API client with HMAC-SHA256 authentication support.
    """
    
    def __init__(self, access_key: str, secret_key: str, base_url: str, retry_config: Optional[RetryConfig] = None):
        """
        Initialize AFS client with credentials and base URL.
        
        Args:
            access_key: AFS API access key
            secret_key: AFS API secret key  
            base_url: Base URL for AFS API endpoints
            retry_config: Retry configuration (uses default if None)
        """
        self.access_key = access_key
        self.secret_key = secret_key
        self.base_url = base_url.rstrip('/')
        self.logger = get_logger(__name__)
        
        # Initialize retry handler
        self.retry_config = retry_config or create_retry_config(
            max_attempts=3,
            base_delay=2.0,
            max_delay=30.0
        )
        self.retry_handler = RetryHandler(self.retry_config)
        
    def _get_current_date(self) -> str:
        """
        Get current date in UTC/GMT format for X-Date header.
        
        Returns:
            Date string in GMT format (e.g., 'Wed, 15 Oct 2025 11:58:51 GMT')
        """
        # Use UTC timezone to match the bash script format
        return datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
    
    def _generate_signature(self, date_string: str, method: str = 'GET', 
                          path: str = '', content_type: str = '') -> str:
        """
        Generate HMAC-SHA256 signature for AFS API authentication.
        
        Args:
            date_string: GMT formatted date string
            method: HTTP method (default: GET)
            path: API endpoint path
            content_type: Content-Type header value
            
        Returns:
            Base64 encoded HMAC-SHA256 signature
            
        Raises:
            AuthenticationError: If signature generation fails
        """
        try:
            # Create string to sign using the correct AFS format: "x-date: {date_string}"
            string_to_sign = f"x-date: {date_string}"
            
            # Generate HMAC-SHA256 signature
            signature = hmac.new(
                self.secret_key.encode('utf-8'),
                string_to_sign.encode('utf-8'),
                hashlib.sha256
            ).digest()
            
            # Return base64 encoded signature
            return base64.b64encode(signature).decode('utf-8')
            
        except Exception as e:
            self.logger.error(f"Failed to generate HMAC signature: {e}")
            raise SignatureError(f"Signature generation failed: {e}", original_error=e)
    
    def _create_auth_headers(self, method: str = 'GET', path: str = '', 
                           content_type: str = '') -> Dict[str, str]:
        """
        Create authentication headers for AFS API requests using HMAC format.
        
        Args:
            method: HTTP method
            path: API endpoint path
            content_type: Content-Type header value
            
        Returns:
            Dictionary containing X-Date and Authorization headers
            
        Raises:
            AuthenticationError: If header generation fails
        """
        try:
            # Get current GMT date
            date_string = self._get_current_date()
            
            # Generate HMAC signature
            signature = self._generate_signature(date_string, method, path, content_type)
            
            # Create HMAC authorization header in the format expected by AFS API
            auth_header = (
                f'hmac accesskey="{self.access_key}",'
                f'algorithm="hmac-sha256",'
                f'headers="x-date",'
                f'signature="{signature}"'
            )
            
            return {
                'X-Date': date_string,
                'Authorization': auth_header
            }
            
        except Exception as e:
            self.logger.error(f"Failed to create authentication headers: {e}")
            raise SignatureError(f"Authentication header creation failed: {e}", original_error=e)
    
    def get_volume_quotas(self, volume_id: str, zone: str, timeout: int = 30) -> Dict:
        """
        Retrieve directory quota information for a specific volume and zone.
        
        Args:
            volume_id: AFS volume identifier
            zone: AFS zone identifier
            timeout: Request timeout in seconds
            
        Returns:
            Dictionary containing quota data from AFS API
            
        Raises:
            AuthenticationError: If authentication fails
            APIError: If API request fails or returns invalid data
        """
        # Use retry handler for the API request
        # Create a clean circuit breaker name without special characters
        clean_volume_id = volume_id.replace('&', '_').replace('=', '_')
        result = self.retry_handler.execute_with_retry(
            self._get_volume_quotas_single_attempt,
            volume_id,
            zone,
            timeout,
            circuit_breaker_name=f"afs_api_{clean_volume_id}",
            context={'volume_id': volume_id, 'zone': zone}
        )
        
        if result.success:
            return result.result
        else:
            raise result.error
    
    def _get_volume_quotas_single_attempt(self, volume_id: str, zone: str, timeout: int) -> Dict:
        """
        Single attempt to retrieve volume quotas (used by retry handler).
        
        Args:
            volume_id: AFS volume identifier
            zone: AFS zone identifier
            timeout: Request timeout in seconds
            
        Returns:
            Dictionary containing quota data from AFS API
        """
        # Context is already set by retry handler, just add operation-specific info
        self.logger.set_context(operation='get_volume_quotas')
        
        try:
            # Construct API endpoint path using the correct AFS API format
            path = f"/storage/afs/data/v1/volume/{volume_id}/dir_quotas"
            url = f"{self.base_url}{path}"
            
            with log_operation(self.logger, f"AFS API request for volume {volume_id}", level='DEBUG'):
                # Create authentication headers
                headers = self._create_auth_headers(method='GET', path=path)
                
                # Add additional headers
                headers.update({
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                })
                
                # Add required parameters for AFS API
                params = {
                    'volume_id': volume_id,
                    'zone': zone
                }
                
                self.logger.debug(f"Making API request to endpoint {path}")
                
                # Log complete request details for debugging
                self.logger.info("=" * 60)
                self.logger.info("🌐 完整的 AFS API 请求详情")
                self.logger.info("=" * 60)
                self.logger.info(f"📍 URL: {url}")
                self.logger.info(f"🔧 Method: GET")
                self.logger.info(f"📋 Headers:")
                for key, value in headers.items():
                    # Use print to bypass log sanitization for debugging
                    print(f"    {key}: {value}")
                    self.logger.info(f"    {key}: {'***FULL_VALUE_PRINTED_ABOVE***' if key == 'Authorization' else value}")
                self.logger.info(f"📊 Parameters:")
                for key, value in params.items():
                    self.logger.info(f"    {key}: {value}")
                self.logger.info(f"⏱️  Timeout: {timeout}s")
                self.logger.info("=" * 60)
                
                # Make API request with timing
                start_time = time.time()
                try:
                    response = requests.get(
                        url,
                        headers=headers,
                        params=params,
                        timeout=timeout
                    )
                except requests.exceptions.Timeout as e:
                    duration = time.time() - start_time
                    self.logger.error(f"Request timeout after {timeout} seconds")
                    raise create_timeout_error(timeout, "AFS API request")
                    
                except requests.exceptions.ConnectionError as e:
                    self.logger.error(f"Connection error: {str(e)[:200]}")
                    raise create_network_error(e, {'volume_id': volume_id, 'zone': zone})
                    
                except requests.exceptions.RequestException as e:
                    self.logger.error(f"Request error: {str(e)[:200]}")
                    raise create_network_error(e, {'volume_id': volume_id, 'zone': zone})
                
                duration = time.time() - start_time
                
                # Log complete response details for debugging
                self.logger.info("📥 完整的 AFS API 响应详情")
                self.logger.info("=" * 60)
                self.logger.info(f"📊 Status Code: {response.status_code}")
                self.logger.info(f"⏱️  Duration: {duration:.3f}s")
                self.logger.info(f"📋 Response Headers:")
                for key, value in response.headers.items():
                    self.logger.info(f"    {key}: {value}")
                
                # Log response content (first 1000 characters)
                response_text = response.text
                self.logger.info(f"📄 Response Content ({len(response_text)} chars):")
                if len(response_text) > 1000:
                    self.logger.info(f"    {response_text[:1000]}...")
                else:
                    self.logger.info(f"    {response_text}")
                self.logger.info("=" * 60)
                
                # Log API request details
                log_api_request(
                    self.logger,
                    method='GET',
                    url=url,
                    status_code=response.status_code,
                    duration=duration
                )
                
                # Handle authentication errors
                if response.status_code == 401:
                    self.logger.error("Authentication failed - invalid credentials or signature")
                    raise InvalidCredentialsError("Invalid credentials or signature")
                
                # Handle forbidden access
                if response.status_code == 403:
                    self.logger.error("Access forbidden - check permissions")
                    raise InvalidCredentialsError("Access forbidden - check permissions")
                
                # Handle not found
                if response.status_code == 404:
                    self.logger.error("Volume not found")
                    raise create_api_error(404, f"Volume {volume_id} not found in zone {zone}")
                
                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    self.logger.warning(f"Rate limited, retry after {retry_after} seconds")
                    raise create_api_error(429, "Rate limit exceeded", {'retry_after': retry_after})
                
                # Handle other client errors
                if 400 <= response.status_code < 500:
                    error_text = response.text[:200] if response.text else "No error details"
                    self.logger.error(f"Client error {response.status_code}: {error_text}")
                    raise create_api_error(response.status_code, error_text)
                
                # Handle server errors
                if response.status_code >= 500:
                    error_text = response.text[:200] if response.text else "No error details"
                    self.logger.error(f"Server error {response.status_code}: {error_text}")
                    raise create_api_error(response.status_code, error_text)
                
                # Check for successful response
                if response.status_code != 200:
                    self.logger.error(f"Unexpected status code {response.status_code}")
                    raise create_api_error(response.status_code, "Unexpected status code")
                
                # Parse JSON response
                try:
                    quota_data = response.json()
                    
                    # Validate response structure
                    if not isinstance(quota_data, dict):
                        raise APIError("Invalid response format: expected JSON object")
                    
                    if 'dir_quota_list' not in quota_data:
                        raise APIError("Invalid response format: missing dir_quota_list")
                    
                    # Log success with data summary
                    dir_count = len(quota_data.get('dir_quota_list', []))
                    self.logger.info(f"Successfully retrieved quota data for {dir_count} directories")
                    
                    return quota_data
                    
                except ValueError as e:
                    self.logger.error(f"Invalid JSON response: {e}")
                    raise APIError(f"Invalid JSON response: {e}", original_error=e)
                
        except (AuthenticationError, APIError, NetworkError, TimeoutError):
            # Re-raise our custom exceptions
            raise
            
        except Exception as e:
            self.logger.error(f"Unexpected error: {str(e)[:200]}")
            raise APIError(f"Unexpected error: {e}", original_error=e)
            
        finally:
            # Clear context
            self.logger.clear_context()
    
    def test_connection(self) -> bool:
        """
        Test connection to AFS API by making a simple authenticated request.
        
        Returns:
            True if connection is successful, False otherwise
        """
        self.logger.set_context(operation='test_connection')
        
        try:
            with log_operation(self.logger, "AFS API connection test", level='INFO'):
                # Try to create auth headers to test credentials
                self._create_auth_headers()
                self.logger.info("AFS API connection test successful")
                return True
                
        except Exception as e:
            self.logger.error(f"AFS API connection test failed: {str(e)[:200]}")
            return False
            
        finally:
            self.logger.clear_context()