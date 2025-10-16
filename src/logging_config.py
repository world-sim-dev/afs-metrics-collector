"""
Structured logging configuration for AFS Prometheus metrics collector.

This module provides centralized logging configuration with:
- Structured logging with contextual information
- Log sanitization to prevent credential exposure
- Configurable log levels and formats
- Context managers for operation-specific logging
"""

import logging
import logging.config
import re
import sys
from typing import Dict, Any, Optional, Union
from contextlib import contextmanager
from functools import wraps

from src.config import LoggingConfig


class SanitizingFormatter(logging.Formatter):
    """
    Custom formatter that sanitizes sensitive information from log messages.
    
    Removes or masks credentials, API keys, and other sensitive data before
    logging to prevent accidental exposure in log files.
    """
    
    # Patterns for sensitive data that should be sanitized
    SENSITIVE_PATTERNS = [
        # API keys and tokens (various formats)
        (re.compile(r'(access_key["\s]*[:=]["\s]*)([^"\s,}]+)', re.IGNORECASE), r'\1***REDACTED***'),
        (re.compile(r'(secret_key["\s]*[:=]["\s]*)([^"\s,}]+)', re.IGNORECASE), r'\1***REDACTED***'),
        (re.compile(r'(api_key["\s]*[:=]["\s]*)([^"\s,}]+)', re.IGNORECASE), r'\1***REDACTED***'),
        (re.compile(r'(token["\s]*[:=]["\s]*)([^"\s,}]+)', re.IGNORECASE), r'\1***REDACTED***'),
        (re.compile(r'(password["\s]*[:=]["\s]*)([^"\s,}]+)', re.IGNORECASE), r'\1***REDACTED***'),
        
        # Authorization headers
        (re.compile(r'(Authorization["\s]*[:=]["\s]*)([^"\s,}]+)', re.IGNORECASE), r'\1***REDACTED***'),
        (re.compile(r'(Bearer\s+)([^\s,}]+)', re.IGNORECASE), r'\1***REDACTED***'),
        (re.compile(r'(AWS\s+[^:]+:)([^\s,}]+)', re.IGNORECASE), r'\1***REDACTED***'),
        
        # HMAC signatures and hashes
        (re.compile(r'(signature["\s]*[:=]["\s]*)([^"\s,}]+)', re.IGNORECASE), r'\1***REDACTED***'),
        (re.compile(r'(hmac["\s]*[:=]["\s]*)([^"\s,}]+)', re.IGNORECASE), r'\1***REDACTED***'),
        
        # URLs with credentials
        (re.compile(r'(https?://[^:]+:)([^@]+)(@)', re.IGNORECASE), r'\1***REDACTED***\3'),
        
        # Generic patterns for long alphanumeric strings that might be secrets
        (re.compile(r'(["\s=:])([a-zA-Z0-9+/]{32,})(["\s,}])', re.IGNORECASE), r'\1***REDACTED***\3'),
    ]
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record with sanitization of sensitive information.
        
        Args:
            record: Log record to format
            
        Returns:
            Formatted and sanitized log message
        """
        # Format the record normally first
        formatted = super().format(record)
        
        # Apply sanitization patterns
        sanitized = formatted
        for pattern, replacement in self.SENSITIVE_PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)
        
        return sanitized


class ContextualLogger:
    """
    Logger wrapper that adds contextual information to log messages.
    
    Provides methods to add context like volume_id, zone, operation type
    to log messages for better traceability and debugging.
    """
    
    def __init__(self, logger: logging.Logger):
        """
        Initialize contextual logger.
        
        Args:
            logger: Base logger instance
        """
        self.logger = logger
        self.context: Dict[str, Any] = {}
    
    def set_context(self, **kwargs) -> None:
        """
        Set context information for subsequent log messages.
        
        Args:
            **kwargs: Context key-value pairs
        """
        self.context.update(kwargs)
    
    def clear_context(self) -> None:
        """Clear all context information."""
        self.context.clear()
    
    def remove_context(self, *keys) -> None:
        """
        Remove specific context keys.
        
        Args:
            *keys: Context keys to remove
        """
        for key in keys:
            self.context.pop(key, None)
    
    def _format_message(self, message: str) -> str:
        """
        Format message with context information.
        
        Args:
            message: Original log message
            
        Returns:
            Message with context information prepended
        """
        if not self.context:
            return message
        
        context_parts = []
        for key, value in self.context.items():
            context_parts.append(f"{key}={value}")
        
        context_str = " ".join(context_parts)
        return f"[{context_str}] {message}"
    
    def debug(self, message: str, *args, **kwargs) -> None:
        """Log debug message with context."""
        self.logger.debug(self._format_message(message), *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs) -> None:
        """Log info message with context."""
        self.logger.info(self._format_message(message), *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs) -> None:
        """Log warning message with context."""
        self.logger.warning(self._format_message(message), *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs) -> None:
        """Log error message with context."""
        self.logger.error(self._format_message(message), *args, **kwargs)
    
    def critical(self, message: str, *args, **kwargs) -> None:
        """Log critical message with context."""
        self.logger.critical(self._format_message(message), *args, **kwargs)
    
    def exception(self, message: str, *args, **kwargs) -> None:
        """Log exception message with context and traceback."""
        self.logger.exception(self._format_message(message), *args, **kwargs)


def setup_logging(logging_config: LoggingConfig) -> None:
    """
    Set up logging configuration for the application.
    
    Args:
        logging_config: Logging configuration object
    """
    # Create logging configuration dictionary
    config_dict = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'main': {
                '()': SanitizingFormatter,
                'format': logging_config.format,
                'datefmt': '%Y-%m-%d %H:%M:%S'
            },
            'detailed': {
                '()': SanitizingFormatter,
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(funcName)s - %(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S'
            }
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': logging_config.level,
                'formatter': 'main',
                'stream': sys.stdout
            },
            'error_console': {
                'class': 'logging.StreamHandler',
                'level': 'ERROR',
                'formatter': 'detailed',
                'stream': sys.stderr
            }
        },
        'loggers': {
            'src': {
                'level': logging_config.level,
                'handlers': ['console', 'error_console'],
                'propagate': False
            },
            'requests': {
                'level': 'WARNING',
                'handlers': ['console'],
                'propagate': False
            },
            'urllib3': {
                'level': 'WARNING',
                'handlers': ['console'],
                'propagate': False
            }
        },
        'root': {
            'level': logging_config.level,
            'handlers': ['console', 'error_console']
        }
    }
    
    # Apply logging configuration
    logging.config.dictConfig(config_dict)


def get_contextual_logger(name: str) -> ContextualLogger:
    """
    Get a contextual logger instance.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        ContextualLogger instance
    """
    base_logger = logging.getLogger(name)
    return ContextualLogger(base_logger)


@contextmanager
def log_operation(logger: Union[logging.Logger, ContextualLogger], 
                  operation: str, 
                  level: str = 'INFO',
                  **context):
    """
    Context manager for logging operation start/end with timing.
    
    Args:
        logger: Logger instance
        operation: Operation description
        level: Log level for operation messages
        **context: Additional context for the operation
    """
    import time
    
    # Set context if using contextual logger
    if isinstance(logger, ContextualLogger):
        original_context = logger.context.copy()
        logger.set_context(**context)
        log_func = getattr(logger, level.lower())
    else:
        log_func = getattr(logger, level.lower())
    
    start_time = time.time()
    log_func(f"Starting {operation}")
    
    try:
        yield
        duration = time.time() - start_time
        log_func(f"Completed {operation} in {duration:.3f}s")
        
    except Exception as e:
        duration = time.time() - start_time
        if isinstance(logger, ContextualLogger):
            logger.error(f"Failed {operation} after {duration:.3f}s: {e}")
        else:
            logger.error(f"Failed {operation} after {duration:.3f}s: {e}")
        raise
        
    finally:
        # Restore original context if using contextual logger
        if isinstance(logger, ContextualLogger):
            logger.context = original_context


def log_with_context(**context_kwargs):
    """
    Decorator to add context to all log messages within a function.
    
    Args:
        **context_kwargs: Context key-value pairs
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Try to find a contextual logger in the instance
            if args and hasattr(args[0], 'logger') and isinstance(args[0].logger, ContextualLogger):
                logger = args[0].logger
                original_context = logger.context.copy()
                logger.set_context(**context_kwargs)
                
                try:
                    return func(*args, **kwargs)
                finally:
                    logger.context = original_context
            else:
                return func(*args, **kwargs)
        
        return wrapper
    return decorator


def sanitize_for_logging(data: Any) -> Any:
    """
    Sanitize data structure for safe logging.
    
    Recursively processes dictionaries, lists, and strings to remove
    sensitive information before logging.
    
    Args:
        data: Data to sanitize
        
    Returns:
        Sanitized copy of the data
    """
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            # Check if key indicates sensitive data
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in ['key', 'secret', 'token', 'password', 'auth']):
                sanitized[key] = '***REDACTED***'
            else:
                sanitized[key] = sanitize_for_logging(value)
        return sanitized
    
    elif isinstance(data, (list, tuple)):
        return type(data)(sanitize_for_logging(item) for item in data)
    
    elif isinstance(data, str):
        # Apply sanitization patterns to strings
        sanitized = data
        for pattern, replacement in SanitizingFormatter.SENSITIVE_PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized
    
    else:
        return data


# Module-level convenience functions
def get_logger(name: str) -> ContextualLogger:
    """Get a contextual logger for the given name."""
    return get_contextual_logger(name)


def log_config_validation(logger: Union[logging.Logger, ContextualLogger], 
                         config_type: str, 
                         success: bool, 
                         details: Optional[str] = None) -> None:
    """
    Log configuration validation results.
    
    Args:
        logger: Logger instance
        config_type: Type of configuration being validated
        success: Whether validation succeeded
        details: Additional details about validation
    """
    if success:
        logger.info(f"{config_type} configuration validation successful")
        if details:
            logger.debug(f"{config_type} validation details: {details}")
    else:
        logger.error(f"{config_type} configuration validation failed")
        if details:
            logger.error(f"{config_type} validation error: {details}")


def log_api_request(logger: Union[logging.Logger, ContextualLogger],
                   method: str,
                   url: str,
                   status_code: Optional[int] = None,
                   duration: Optional[float] = None,
                   error: Optional[str] = None) -> None:
    """
    Log API request details in a standardized format.
    
    Args:
        logger: Logger instance
        method: HTTP method
        url: Request URL (will be sanitized)
        status_code: HTTP status code
        duration: Request duration in seconds
        error: Error message if request failed
    """
    # Sanitize URL to remove credentials
    sanitized_url = url
    for pattern, replacement in SanitizingFormatter.SENSITIVE_PATTERNS:
        sanitized_url = pattern.sub(replacement, sanitized_url)
    
    if error:
        logger.error(f"API request failed: {method} {sanitized_url} - {error}")
    elif status_code:
        level = 'info' if 200 <= status_code < 400 else 'warning'
        duration_str = f" ({duration:.3f}s)" if duration else ""
        getattr(logger, level)(f"API request: {method} {sanitized_url} - {status_code}{duration_str}")
    else:
        logger.debug(f"API request: {method} {sanitized_url}")