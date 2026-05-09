"""API call retry primitives.

Helpers for retrying calls to external APIs (LLMs, etc.) with exponential
backoff and jitter.
"""

import time
import random
import functools
from typing import Callable, Any, Optional, Type, Tuple
from ..utils.logger import get_logger
from .locale import t

logger = get_logger('mirofish.retry')


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """Decorator that retries a callable with exponential backoff.

    Args:
        max_retries: Maximum number of retries before giving up.
        initial_delay: Initial delay in seconds before the first retry.
        max_delay: Cap on the delay between retries (seconds).
        backoff_factor: Multiplicative factor applied to the delay each retry.
        jitter: When ``True``, randomize the delay to avoid thundering herd.
        exceptions: Exception types that should trigger a retry.
        on_retry: Optional callback invoked on each retry as ``(exception, retry_count)``.

    Usage:
        @retry_with_backoff(max_retries=3)
        def call_llm_api():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            delay = initial_delay
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                    
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(t(
                            "log.retry.m001",
                            func_name=func.__name__,
                            max_retries=max_retries,
                            e=str(e),
                        ))
                        raise
                    
                    # Compute the next delay, capped at ``max_delay``.
                    current_delay = min(delay, max_delay)
                    if jitter:
                        current_delay = current_delay * (0.5 + random.random())
                    
                    logger.warning(
                        f"函数 {func.__name__} 第 {attempt + 1} 次尝试失败: {str(e)}, "
                        f"{current_delay:.1f}秒后重试..."
                    )
                    
                    if on_retry:
                        on_retry(e, attempt + 1)
                    
                    time.sleep(current_delay)
                    delay *= backoff_factor
            
            raise last_exception
        
        return wrapper
    return decorator


def retry_with_backoff_async(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """Async variant of :func:`retry_with_backoff`."""
    import asyncio
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            delay = initial_delay
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                    
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(t(
                            "log.retry.m002",
                            func_name=func.__name__,
                            max_retries=max_retries,
                            e=str(e),
                        ))
                        raise
                    
                    current_delay = min(delay, max_delay)
                    if jitter:
                        current_delay = current_delay * (0.5 + random.random())
                    
                    logger.warning(
                        f"异步函数 {func.__name__} 第 {attempt + 1} 次尝试失败: {str(e)}, "
                        f"{current_delay:.1f}秒后重试..."
                    )
                    
                    if on_retry:
                        on_retry(e, attempt + 1)
                    
                    await asyncio.sleep(current_delay)
                    delay *= backoff_factor
            
            raise last_exception
        
        return wrapper
    return decorator


class RetryableAPIClient:
    """Class-based wrapper around the retry helpers."""
    
    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
    
    def call_with_retry(
        self,
        func: Callable,
        *args,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
        **kwargs
    ) -> Any:
        """Invoke ``func`` with retry on failure.

        Args:
            func: Callable to invoke.
            *args: Positional arguments forwarded to ``func``.
            exceptions: Exception types that should trigger a retry.
            **kwargs: Keyword arguments forwarded to ``func``.

        Returns:
            The value returned by ``func``.
        """
        last_exception = None
        delay = self.initial_delay
        
        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
                
            except exceptions as e:
                last_exception = e
                
                if attempt == self.max_retries:
                    logger.error(t(
                        "log.retry.m003",
                        max_retries=self.max_retries,
                        e=str(e),
                    ))
                    raise
                
                current_delay = min(delay, self.max_delay)
                current_delay = current_delay * (0.5 + random.random())
                
                logger.warning(
                    f"API调用第 {attempt + 1} 次尝试失败: {str(e)}, "
                    f"{current_delay:.1f}秒后重试..."
                )
                
                time.sleep(current_delay)
                delay *= self.backoff_factor
        
        raise last_exception
    
    def call_batch_with_retry(
        self,
        items: list,
        process_func: Callable,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
        continue_on_failure: bool = True
    ) -> Tuple[list, list]:
        """Process ``items`` in sequence, retrying each independently on failure.

        Args:
            items: Items to process.
            process_func: Callable invoked once per item.
            exceptions: Exception types that should trigger a retry.
            continue_on_failure: When ``True``, keep processing remaining items after a failure.

        Returns:
            ``(successes, failures)`` — a list of successful results and a list
            of failure descriptors ``{"index", "item", "error"}``.
        """
        results = []
        failures = []
        
        for idx, item in enumerate(items):
            try:
                result = self.call_with_retry(
                    process_func,
                    item,
                    exceptions=exceptions
                )
                results.append(result)
                
            except Exception as e:
                logger.error(t("log.retry.m004", index=idx + 1, e=str(e)))
                failures.append({
                    "index": idx,
                    "item": item,
                    "error": str(e)
                })
                
                if not continue_on_failure:
                    raise
        
        return results, failures

