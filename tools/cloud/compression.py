"""
Compression utilities for cloud transfers.

Provides transparent compression before upload and decompression after download
to reduce bandwidth usage and storage costs.

Supported algorithms:
- gzip (standard, compatible, good compression)
- lz4 (fast, lower compression ratio, requires lz4 package)
"""

import gzip
import io
from pathlib import Path
from typing import BinaryIO


class CompressionError(Exception):
    """Raised when compression or decompression fails."""
    pass


def compress_file(input_path: Path, compression_type: str = "gzip") -> bytes:
    """
    Compress file contents.
    
    Args:
        input_path: Path to file to compress
        compression_type: Compression algorithm ('gzip' or 'lz4')
        
    Returns:
        Compressed data as bytes
        
    Raises:
        CompressionError: If compression fails
    """
    try:
        with open(input_path, 'rb') as f:
            data = f.read()
        
        if compression_type == 'gzip':
            return gzip.compress(data, compresslevel=6)
        elif compression_type == 'lz4':
            try:
                import lz4.frame
                return lz4.frame.compress(data)
            except ImportError:
                raise CompressionError("lz4 package not installed. Run: pip install lz4")
        else:
            raise CompressionError(f"Unknown compression type: {compression_type}")
    
    except Exception as e:
        raise CompressionError(f"Failed to compress {input_path}: {e}")


def decompress_file(compressed_data: bytes, output_path: Path, compression_type: str = "gzip") -> int:
    """
    Decompress data to file.
    
    Args:
        compressed_data: Compressed data bytes
        output_path: Path where to write decompressed file
        compression_type: Compression algorithm used
        
    Returns:
        Number of bytes written
        
    Raises:
        CompressionError: If decompression fails
    """
    try:
        if compression_type == 'gzip':
            data = gzip.decompress(compressed_data)
        elif compression_type == 'lz4':
            try:
                import lz4.frame
                data = lz4.frame.decompress(compressed_data)
            except ImportError:
                raise CompressionError("lz4 package not installed. Run: pip install lz4")
        else:
            raise CompressionError(f"Unknown compression type: {compression_type}")
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(data)
        
        return len(data)
    
    except Exception as e:
        raise CompressionError(f"Failed to decompress to {output_path}: {e}")


def compress_stream(input_stream: BinaryIO, compression_type: str = "gzip") -> BinaryIO:
    """
    Create compressed stream from input stream.
    
    Args:
        input_stream: Input file-like object
        compression_type: Compression algorithm
        
    Returns:
        Compressed stream (BytesIO object)
        
    Raises:
        CompressionError: If compression fails
    """
    try:
        data = input_stream.read()
        
        if compression_type == 'gzip':
            compressed = gzip.compress(data, compresslevel=6)
        elif compression_type == 'lz4':
            try:
                import lz4.frame
                compressed = lz4.frame.compress(data)
            except ImportError:
                raise CompressionError("lz4 package not installed. Run: pip install lz4")
        else:
            raise CompressionError(f"Unknown compression type: {compression_type}")
        
        return io.BytesIO(compressed)
    
    except Exception as e:
        raise CompressionError(f"Failed to compress stream: {e}")


def decompress_stream(compressed_stream: BinaryIO, compression_type: str = "gzip") -> BinaryIO:
    """
    Create decompressed stream from compressed stream.
    
    Args:
        compressed_stream: Compressed file-like object
        compression_type: Compression algorithm used
        
    Returns:
        Decompressed stream (BytesIO object)
        
    Raises:
        CompressionError: If decompression fails
    """
    try:
        compressed_data = compressed_stream.read()
        
        if compression_type == 'gzip':
            data = gzip.decompress(compressed_data)
        elif compression_type == 'lz4':
            try:
                import lz4.frame
                data = lz4.frame.decompress(compressed_data)
            except ImportError:
                raise CompressionError("lz4 package not installed. Run: pip install lz4")
        else:
            raise CompressionError(f"Unknown compression type: {compression_type}")
        
        return io.BytesIO(data)
    
    except Exception as e:
        raise CompressionError(f"Failed to decompress stream: {e}")


def get_compressed_size(input_path: Path, compression_type: str = "gzip") -> dict:
    """
    Get compression statistics for a file without writing output.
    
    Args:
        input_path: Path to file to analyze
        compression_type: Compression algorithm to test
        
    Returns:
        Dictionary with original_size, compressed_size, ratio
    """
    try:
        original_size = input_path.stat().st_size
        compressed_data = compress_file(input_path, compression_type)
        compressed_size = len(compressed_data)
        ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
        
        return {
            'original_size': original_size,
            'compressed_size': compressed_size,
            'compression_ratio': ratio,
            'worth_compressing': compressed_size < original_size * 0.9,  # >10% savings
        }
    except Exception as e:
        return {
            'error': str(e),
            'worth_compressing': False,
        }


def should_compress(file_path: Path, compression_type: str = "gzip") -> bool:
    """
    Determine if compressing a file is worthwhile.
    
    Checks file extension and tests compression on a sample.
    
    Args:
        file_path: Path to file
        compression_type: Compression algorithm to test
        
    Returns:
        True if compression is likely beneficial
    """
    # Already compressed formats - don't compress again
    skip_extensions = {
        '.gz', '.zip', '.bz2', '.xz', '.7z', '.rar',
        '.jpg', '.jpeg', '.png', '.gif', '.webp',
        '.mp3', '.mp4', '.avi', '.mkv', '.mov',
        '.pdf', '.docx', '.xlsx', '.pptx',
    }
    
    if file_path.suffix.lower() in skip_extensions:
        return False
    
    # Small files - compression overhead not worth it
    if file_path.stat().st_size < 1024:  # < 1KB
        return False
    
    # For large text files, always worth it
    text_extensions = {'.txt', '.log', '.json', '.xml', '.csv', '.yaml', '.yml', '.md'}
    if file_path.suffix.lower() in text_extensions:
        return True
    
    # For other files, test compression on first 64KB
    try:
        with open(file_path, 'rb') as f:
            sample = f.read(65536)  # 64KB sample
        
        if compression_type == 'gzip':
            compressed = gzip.compress(sample, compresslevel=6)
        elif compression_type == 'lz4':
            import lz4.frame
            compressed = lz4.frame.compress(sample)
        else:
            return False
        
        # Worth compressing if we save >10%
        return len(compressed) < len(sample) * 0.9
    
    except Exception:
        return False
