"""
Bandwidth limiting utilities for cloud transfers.

Provides rate limiting for upload and download operations to control
bandwidth usage and prevent network saturation.
"""

import time
from threading import Lock
from typing import Optional


class BandwidthLimiter:
    """
    Rate limiter for controlling bandwidth usage.
    
    Uses token bucket algorithm for smooth rate limiting.
    Thread-safe for use with parallel workers.
    """
    
    def __init__(self, rate_bytes_per_sec: int, bucket_size: Optional[int] = None):
        """
        Initialize bandwidth limiter.
        
        Args:
            rate_bytes_per_sec: Target transfer rate in bytes per second
            bucket_size: Token bucket size (default: 2x rate for burst tolerance)
        """
        self.rate = rate_bytes_per_sec
        self.bucket_size = bucket_size or (rate_bytes_per_sec * 2)
        self.tokens = float(self.bucket_size)
        self.last_refill = time.time()
        self.lock = Lock()
    
    def consume(self, bytes_count: int) -> float:
        """
        Consume tokens for bytes transferred.
        
        Blocks if insufficient tokens available, refilling at configured rate.
        
        Args:
            bytes_count: Number of bytes to consume tokens for
            
        Returns:
            Time waited in seconds (0 if no wait required)
        """
        with self.lock:
            # Refill tokens based on elapsed time
            now = time.time()
            elapsed = now - self.last_refill
            self.tokens = min(self.bucket_size, self.tokens + elapsed * self.rate)
            self.last_refill = now
            
            # If we have enough tokens, consume and return
            if self.tokens >= bytes_count:
                self.tokens -= bytes_count
                return 0.0
            
            # Calculate wait time needed
            needed = bytes_count - self.tokens
            wait_time = needed / self.rate
            
            # Wait and refill
            time.sleep(wait_time)
            self.tokens = 0
            self.last_refill = time.time()
            
            return wait_time
    
    def get_current_rate(self) -> float:
        """
        Get current instantaneous rate in bytes/sec.
        
        Returns:
            Current rate based on token bucket fill level
        """
        with self.lock:
            return self.tokens / max(1, time.time() - self.last_refill)
    
    def reset(self):
        """Reset limiter to full bucket."""
        with self.lock:
            self.tokens = float(self.bucket_size)
            self.last_refill = time.time()


class ThrottledFile:
    """
    File wrapper that applies bandwidth limiting to read operations.
    
    Useful for wrapping file objects before upload to cloud storage.
    """
    
    def __init__(self, file_obj, limiter: BandwidthLimiter):
        """
        Initialize throttled file wrapper.
        
        Args:
            file_obj: File-like object to wrap (must support read())
            limiter: BandwidthLimiter instance
        """
        self.file_obj = file_obj
        self.limiter = limiter
        self.bytes_transferred = 0
        self.start_time = time.time()
    
    def read(self, size: int = -1) -> bytes:
        """
        Read from file with bandwidth limiting.
        
        Args:
            size: Number of bytes to read (-1 for all)
            
        Returns:
            Bytes read from file
        """
        data = self.file_obj.read(size)
        if data:
            self.limiter.consume(len(data))
            self.bytes_transferred += len(data)
        return data
    
    def seek(self, *args, **kwargs):
        """Pass-through seek to wrapped file."""
        return self.file_obj.seek(*args, **kwargs)
    
    def tell(self):
        """Pass-through tell to wrapped file."""
        return self.file_obj.tell()
    
    def close(self):
        """Close wrapped file."""
        return self.file_obj.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, *args):
        """Context manager exit."""
        self.close()
    
    def get_stats(self) -> dict:
        """
        Get transfer statistics.
        
        Returns:
            Dictionary with bytes_transferred and average_rate
        """
        elapsed = time.time() - self.start_time
        avg_rate = self.bytes_transferred / max(1, elapsed)
        return {
            'bytes_transferred': self.bytes_transferred,
            'elapsed_seconds': elapsed,
            'average_rate_bytes_per_sec': avg_rate,
            'average_rate_kb_per_sec': avg_rate / 1024,
        }
