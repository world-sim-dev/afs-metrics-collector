"""
Custom exception classes for AFS Prometheus metrics collector.

This module provides a hierarchy of exceptions for different error scenarios
with support for error categorization, retry logic, and detailed error context.
"""

from typing import Optional, Dict, Any
from enum import Enum


class ErrorSeverity(Enum):
    """Error severity levels for categorizing exceptions."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for different types of failures."""
    AUTHENTICATION = "authentication"
    NETWORK = "network"
    API = "api"
    CONFIGURATION = "configuration"
    DATA_PROCESSING = "data_processing"
    SERVER = "server"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"


class AFSCollectorError(Exception):
    """
    Base exception for AFS collector with enhanced error context.
    
    Provides common functionality for all collector exceptions including
    error categorization, severity levels, and retry hints.
    """
    
    def __init__(self, 
                 message: str, 
                 category: ErrorCategory = ErrorCategory.API,
                 severity: ErrorSeverity = ErrorSeverity.MEDIUM,
                 retryable: bool = False,
                 retry_after: Optional[int] = None,
                 context: Optional[Dict[str, Any]] = None,
                 original_error: Optional[Exception] = None):
        """
        Initialize AFS collector error.
        
        Args:
            message: Error message
            category: Error category for classification
            severity: Error severity level
            retryable: Whether this error is retryable
            retry_after: Suggested retry delay in seconds
            context: Additional error context
            original_error: Original exception that caused this error
        """
        super().__init__(message)
        self.category = category
        self.severity = severity
        self.retryable = retryable
        self.retry_after = retry_after
        self.context = context or {}
        self.original_error = original_error
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert exception to dictionary for logging/serialization.
        
        Returns:
            Dictionary representation of the exception
        """
        return {
            'error_type': self.__class__.__name__,
            'message': str(self),
            'category': self.category.value,
            'severity': self.severity.value,
            'retryable': self.retryable,
            'retry_after': self.retry_after,
            'context': self.context,
            'original_error': str(self.original_error) if self.original_error else None
        }


class AuthenticationError(AFSCollectorError):
    """Authentication related errors."""
    
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault('category', ErrorCategory.AUTHENTICATION)
        kwargs.setdefault('severity', ErrorSeverity.HIGH)
        kwargs.setdefault('retryable', False)  # Auth errors usually not retryable
        super().__init__(message, **kwargs)


class InvalidCredentialsError(AuthenticationError):
    """Invalid or expired credentials."""
    
    def __init__(self, message: str = "Invalid or expired credentials", **kwargs):
        kwargs.setdefault('severity', ErrorSeverity.CRITICAL)
        super().__init__(message, **kwargs)


class SignatureError(AuthenticationError):
    """HMAC signature generation or validation errors."""
    
    def __init__(self, message: str = "Signature generation or validation failed", **kwargs):
        kwargs.setdefault('retryable', True)  # Signature errors might be transient
        kwargs.setdefault('retry_after', 1)
        super().__init__(message, **kwargs)


class APIError(AFSCollectorError):
    """API communication errors."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, **kwargs):
        kwargs.setdefault('category', ErrorCategory.API)
        kwargs.setdefault('severity', ErrorSeverity.MEDIUM)
        
        # Set retryability based on status code
        if status_code:
            kwargs.setdefault('retryable', status_code >= 500 or status_code == 429)
            if status_code == 429:  # Rate limited
                kwargs['category'] = ErrorCategory.RATE_LIMIT
                kwargs.setdefault('retry_after', 60)
            elif status_code >= 500:
                kwargs.setdefault('retry_after', 5)
        
        if 'context' not in kwargs:
            kwargs['context'] = {}
        kwargs['context']['status_code'] = status_code
        
        super().__init__(message, **kwargs)


class NetworkError(AFSCollectorError):
    """Network connectivity errors."""
    
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault('category', ErrorCategory.NETWORK)
        kwargs.setdefault('severity', ErrorSeverity.MEDIUM)
        kwargs.setdefault('retryable', True)
        kwargs.setdefault('retry_after', 5)
        super().__init__(message, **kwargs)


class TimeoutError(AFSCollectorError):
    """Request timeout errors."""
    
    def __init__(self, message: str, timeout_duration: Optional[float] = None, **kwargs):
        kwargs.setdefault('category', ErrorCategory.TIMEOUT)
        kwargs.setdefault('severity', ErrorSeverity.MEDIUM)
        kwargs.setdefault('retryable', True)
        kwargs.setdefault('retry_after', 10)
        
        if 'context' not in kwargs:
            kwargs['context'] = {}
        kwargs['context']['timeout_duration'] = timeout_duration
        
        super().__init__(message, **kwargs)


class ConfigurationError(AFSCollectorError):
    """Configuration related errors."""
    
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault('category', ErrorCategory.CONFIGURATION)
        kwargs.setdefault('severity', ErrorSeverity.CRITICAL)
        kwargs.setdefault('retryable', False)  # Config errors need manual intervention
        super().__init__(message, **kwargs)


class MetricsError(AFSCollectorError):
    """Metrics processing errors."""
    
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault('category', ErrorCategory.DATA_PROCESSING)
        kwargs.setdefault('severity', ErrorSeverity.MEDIUM)
        kwargs.setdefault('retryable', False)  # Data processing errors usually not retryable
        super().__init__(message, **kwargs)


class DataValidationError(MetricsError):
    """Data validation and parsing errors."""
    
    def __init__(self, message: str, invalid_data: Optional[Any] = None, **kwargs):
        if 'context' not in kwargs:
            kwargs['context'] = {}
        kwargs['context']['invalid_data_type'] = type(invalid_data).__name__ if invalid_data else None
        super().__init__(message, **kwargs)


class ServerError(AFSCollectorError):
    """HTTP server errors."""
    
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault('category', ErrorCategory.SERVER)
        kwargs.setdefault('severity', ErrorSeverity.HIGH)
        kwargs.setdefault('retryable', False)
        super().__init__(message, **kwargs)


class PartialCollectionError(AFSCollectorError):
    """Error when some volumes fail during collection."""
    
    def __init__(self, message: str, failed_volumes: Optional[list] = None, **kwargs):
        kwargs.setdefault('category', ErrorCategory.DATA_PROCESSING)
        kwargs.setdefault('severity', ErrorSeverity.MEDIUM)
        kwargs.setdefault('retryable', True)
        kwargs.setdefault('retry_after', 30)
        
        if 'context' not in kwargs:
            kwargs['context'] = {}
        kwargs['context']['failed_volumes'] = failed_volumes or []
        kwargs['context']['failed_count'] = len(failed_volumes) if failed_volumes else 0
        
        super().__init__(message, **kwargs)


class RateLimitError(APIError):
    """Rate limiting errors from API."""
    
    def __init__(self, message: str = "API rate limit exceeded", retry_after: int = 60, **kwargs):
        kwargs.setdefault('category', ErrorCategory.RATE_LIMIT)
        kwargs.setdefault('severity', ErrorSeverity.MEDIUM)
        kwargs['retryable'] = True
        kwargs['retry_after'] = retry_after
        super().__init__(message, status_code=429, **kwargs)


# Convenience functions for creating common errors

def create_network_error(original_error: Exception, context: Optional[Dict] = None) -> NetworkError:
    """Create a network error from an original exception."""
    return NetworkError(
        message=f"Network error: {str(original_error)}",
        original_error=original_error,
        context=context
    )


def create_timeout_error(timeout_duration: float, operation: str = "request") -> TimeoutError:
    """Create a timeout error with duration context."""
    return TimeoutError(
        message=f"Operation '{operation}' timed out after {timeout_duration:.1f} seconds",
        timeout_duration=timeout_duration
    )


def create_api_error(status_code: int, response_text: str = "", context: Optional[Dict] = None) -> APIError:
    """Create an API error with status code and response context."""
    message = f"API error {status_code}"
    if response_text:
        message += f": {response_text[:200]}"
    
    return APIError(
        message=message,
        status_code=status_code,
        context=context
    )


def create_config_error(config_type: str, details: str) -> ConfigurationError:
    """Create a configuration error with specific details."""
    return ConfigurationError(
        message=f"Configuration error in {config_type}: {details}",
        context={'config_type': config_type}
    )