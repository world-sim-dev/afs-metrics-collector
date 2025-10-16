"""
Retry handling module for AFS Prometheus metrics collector.

This module provides retry logic with exponential backoff, circuit breaker
pattern, and intelligent retry decision making based on error types.
"""

import time
import random
import threading
from typing import Callable, Any, Optional, Dict, List, Type
from functools import wraps
from dataclasses import dataclass, field
from enum import Enum

from src.exceptions import AFSCollectorError, ErrorCategory, ErrorSeverity
from src.logging_config import get_logger


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    backoff_multiplier: float = 1.0
    
    # Circuit breaker settings
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    half_open_max_calls: int = 3


@dataclass
class RetryAttempt:
    """Information about a retry attempt."""
    attempt_number: int
    delay: float
    error: Optional[Exception] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class RetryResult:
    """Result of a retry operation."""
    success: bool
    result: Any = None
    error: Optional[Exception] = None
    attempts: List[RetryAttempt] = field(default_factory=list)
    total_duration: float = 0.0
    circuit_breaker_triggered: bool = False


class CircuitBreaker:
    """
    Circuit breaker implementation to prevent cascading failures.
    
    Tracks failure rates and temporarily stops making requests to failing
    services to allow them time to recover.
    """
    
    def __init__(self, config: RetryConfig, name: str = "default"):
        """
        Initialize circuit breaker.
        
        Args:
            config: Retry configuration
            name: Circuit breaker name for logging
        """
        self.config = config
        self.name = name
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_calls = 0
        self.lock = threading.RLock()
        self.logger = get_logger(f"{__name__}.{name}")
    
    def can_execute(self) -> bool:
        """
        Check if execution is allowed based on circuit state.
        
        Returns:
            True if execution is allowed
        """
        with self.lock:
            if self.state == CircuitState.CLOSED:
                return True
            
            elif self.state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                if time.time() - self.last_failure_time >= self.config.recovery_timeout:
                    self.logger.info(f"Circuit breaker {self.name} transitioning to HALF_OPEN")
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_calls = 0
                    return True
                return False
            
            elif self.state == CircuitState.HALF_OPEN:
                # Allow limited calls in half-open state
                return self.half_open_calls < self.config.half_open_max_calls
            
            return False
    
    def record_success(self) -> None:
        """Record a successful operation."""
        with self.lock:
            if self.state == CircuitState.HALF_OPEN:
                self.half_open_calls += 1
                if self.half_open_calls >= self.config.half_open_max_calls:
                    self.logger.info(f"Circuit breaker {self.name} transitioning to CLOSED")
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
            elif self.state == CircuitState.CLOSED:
                self.failure_count = max(0, self.failure_count - 1)
    
    def record_failure(self) -> None:
        """Record a failed operation."""
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.state == CircuitState.HALF_OPEN:
                self.logger.warning(f"Circuit breaker {self.name} transitioning back to OPEN")
                self.state = CircuitState.OPEN
            elif self.state == CircuitState.CLOSED and self.failure_count >= self.config.failure_threshold:
                self.logger.warning(f"Circuit breaker {self.name} transitioning to OPEN after {self.failure_count} failures")
                self.state = CircuitState.OPEN
    
    def get_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state information."""
        with self.lock:
            return {
                'name': self.name,
                'state': self.state.value,
                'failure_count': self.failure_count,
                'last_failure_time': self.last_failure_time,
                'half_open_calls': self.half_open_calls
            }


class RetryHandler:
    """
    Retry handler with exponential backoff and circuit breaker support.
    
    Provides intelligent retry logic based on error types and maintains
    circuit breakers for different operations to prevent cascading failures.
    """
    
    def __init__(self, config: RetryConfig):
        """
        Initialize retry handler.
        
        Args:
            config: Retry configuration
        """
        self.config = config
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.lock = threading.RLock()
        self.logger = get_logger(__name__)
    
    def get_circuit_breaker(self, name: str) -> CircuitBreaker:
        """
        Get or create a circuit breaker for the given name.
        
        Args:
            name: Circuit breaker name
            
        Returns:
            CircuitBreaker instance
        """
        with self.lock:
            if name not in self.circuit_breakers:
                self.circuit_breakers[name] = CircuitBreaker(self.config, name)
            return self.circuit_breakers[name]
    
    def should_retry(self, error: Exception, attempt: int) -> bool:
        """
        Determine if an error should trigger a retry.
        
        Args:
            error: Exception that occurred
            attempt: Current attempt number (1-based)
            
        Returns:
            True if retry should be attempted
        """
        # Don't retry if we've exceeded max attempts
        if attempt >= self.config.max_attempts:
            return False
        
        # Check if error is retryable
        if isinstance(error, AFSCollectorError):
            return error.retryable
        
        # Default retry logic for non-AFSCollectorError exceptions
        # Retry on network-related errors
        if isinstance(error, (ConnectionError, TimeoutError)):
            return True
        
        # Don't retry on other types of errors
        return False
    
    def calculate_delay(self, attempt: int, error: Optional[Exception] = None) -> float:
        """
        Calculate delay before next retry attempt.
        
        Args:
            attempt: Current attempt number (1-based)
            error: Exception that triggered the retry
            
        Returns:
            Delay in seconds
        """
        # Use error-specific retry delay if available
        if isinstance(error, AFSCollectorError) and error.retry_after:
            base_delay = error.retry_after
        else:
            base_delay = self.config.base_delay
        
        # Calculate exponential backoff
        delay = base_delay * (self.config.exponential_base ** (attempt - 1))
        delay *= self.config.backoff_multiplier
        
        # Apply jitter to avoid thundering herd
        if self.config.jitter:
            jitter_range = delay * 0.1  # 10% jitter
            delay += random.uniform(-jitter_range, jitter_range)
        
        # Cap at maximum delay
        delay = min(delay, self.config.max_delay)
        
        return max(0, delay)
    
    def execute_with_retry(self, 
                          func: Callable,
                          *args,
                          circuit_breaker_name: Optional[str] = None,
                          context: Optional[Dict] = None,
                          **kwargs) -> RetryResult:
        """
        Execute a function with retry logic and circuit breaker protection.
        
        Args:
            func: Function to execute
            *args: Function arguments
            circuit_breaker_name: Name for circuit breaker (optional)
            context: Additional context for logging
            **kwargs: Function keyword arguments
            
        Returns:
            RetryResult with execution outcome
        """
        start_time = time.time()
        attempts = []
        circuit_breaker = None
        
        if circuit_breaker_name:
            circuit_breaker = self.get_circuit_breaker(circuit_breaker_name)
        
        # Set up logging context
        self.logger.set_context(
            operation=func.__name__,
            circuit_breaker=circuit_breaker_name,
            **(context or {})
        )
        
        try:
            for attempt in range(1, self.config.max_attempts + 1):
                # Check circuit breaker
                if circuit_breaker and not circuit_breaker.can_execute():
                    self.logger.warning(f"Circuit breaker {circuit_breaker_name} is OPEN, aborting retry")
                    return RetryResult(
                        success=False,
                        error=AFSCollectorError(
                            f"Circuit breaker {circuit_breaker_name} is open",
                            retryable=False
                        ),
                        attempts=attempts,
                        total_duration=time.time() - start_time,
                        circuit_breaker_triggered=True
                    )
                
                try:
                    self.logger.debug(f"Executing attempt {attempt}/{self.config.max_attempts}")
                    
                    # Execute the function
                    result = func(*args, **kwargs)
                    
                    # Record success
                    if circuit_breaker:
                        circuit_breaker.record_success()
                    
                    attempts.append(RetryAttempt(attempt_number=attempt, delay=0))
                    
                    self.logger.info(f"Operation succeeded on attempt {attempt}")
                    
                    return RetryResult(
                        success=True,
                        result=result,
                        attempts=attempts,
                        total_duration=time.time() - start_time
                    )
                
                except Exception as error:
                    # Record failure
                    if circuit_breaker:
                        circuit_breaker.record_failure()
                    
                    # Determine if we should retry
                    should_retry = self.should_retry(error, attempt)
                    
                    if should_retry and attempt < self.config.max_attempts:
                        # Calculate delay
                        delay = self.calculate_delay(attempt, error)
                        
                        attempts.append(RetryAttempt(
                            attempt_number=attempt,
                            delay=delay,
                            error=error
                        ))
                        
                        self.logger.warning(f"Attempt {attempt} failed: {str(error)[:200]}, "
                                          f"retrying in {delay:.1f}s")
                        
                        # Wait before retry
                        if delay > 0:
                            time.sleep(delay)
                    else:
                        # No more retries
                        attempts.append(RetryAttempt(
                            attempt_number=attempt,
                            delay=0,
                            error=error
                        ))
                        
                        self.logger.error(f"Operation failed after {attempt} attempts: {str(error)[:200]}")
                        
                        return RetryResult(
                            success=False,
                            error=error,
                            attempts=attempts,
                            total_duration=time.time() - start_time
                        )
            
            # Should not reach here, but handle gracefully
            return RetryResult(
                success=False,
                error=AFSCollectorError("Maximum retry attempts exceeded"),
                attempts=attempts,
                total_duration=time.time() - start_time
            )
        
        finally:
            self.logger.clear_context()
    
    def get_circuit_breaker_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status of all circuit breakers.
        
        Returns:
            Dictionary mapping circuit breaker names to their status
        """
        with self.lock:
            return {name: cb.get_state() for name, cb in self.circuit_breakers.items()}


# Decorator for automatic retry
def retry_on_failure(config: Optional[RetryConfig] = None,
                    circuit_breaker_name: Optional[str] = None,
                    context: Optional[Dict] = None):
    """
    Decorator to automatically retry function calls on failure.
    
    Args:
        config: Retry configuration (uses default if None)
        circuit_breaker_name: Name for circuit breaker
        context: Additional context for logging
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retry_config = config or RetryConfig()
            handler = RetryHandler(retry_config)
            
            result = handler.execute_with_retry(
                func,
                *args,
                circuit_breaker_name=circuit_breaker_name,
                context=context,
                **kwargs
            )
            
            if result.success:
                return result.result
            else:
                raise result.error
        
        return wrapper
    return decorator


# Convenience function for creating retry configurations
def create_retry_config(max_attempts: int = 3,
                       base_delay: float = 1.0,
                       max_delay: float = 60.0,
                       exponential_base: float = 2.0) -> RetryConfig:
    """
    Create a retry configuration with common settings.
    
    Args:
        max_attempts: Maximum number of retry attempts
        base_delay: Base delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        exponential_base: Base for exponential backoff
        
    Returns:
        RetryConfig instance
    """
    return RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        exponential_base=exponential_base
    )