"""Retry utilities with exponential backoff."""

import functools
import logging
import time
from typing import Callable, TypeVar, Tuple

logger = logging.getLogger(__name__)

T = TypeVar('T')


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    exceptions: Tuple[type, ...] = (Exception,),
    on_retry: Callable[[Exception, int], None] | None = None,
) -> Callable:
    """Decorator for retrying functions with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts.
        base_delay: Initial delay between retries in seconds.
        max_delay: Maximum delay between retries.
        exponential_base: Base for exponential calculation.
        exceptions: Tuple of exceptions to catch and retry.
        on_retry: Optional callback called on each retry.

    Returns:
        Decorated function.
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        delay = min(
                            base_delay * (exponential_base ** attempt),
                            max_delay
                        )
                        
                        logger.warning(
                            "Attempt %d/%d failed for %s: %s. Retrying in %.1fs...",
                            attempt + 1,
                            max_retries + 1,
                            func.__name__,
                            str(e),
                            delay
                        )
                        
                        if on_retry:
                            on_retry(e, attempt + 1)
                        
                        time.sleep(delay)
                    else:
                        logger.error(
                            "All %d attempts failed for %s",
                            max_retries + 1,
                            func.__name__
                        )
            
            raise last_exception
        
        return wrapper
    return decorator


def retry_on_rate_limit(
    max_retries: int = 3,
    base_delay: float = 2.0,
) -> Callable:
    """Specialized retry decorator for rate-limited APIs."""
    return retry_with_backoff(
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=300.0,  # 5 minutes max
        exponential_base=2.0,
        exceptions=(Exception,),
    )
