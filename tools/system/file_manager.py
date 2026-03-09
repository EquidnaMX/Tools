"""
File management utilities.

Provides file operations like merging, cleanup, and batch processing.
"""

import re
from pathlib import Path
from typing import List, Optional, Dict
from dataclasses import dataclass

from tools.core.logger import get_logger
from tools.core.exceptions import ToolsException

logger = get_logger(__name__)


class FileManagerError(ToolsException):
    """Raised when file operations fail."""
    pass


@dataclass
class FileStats:
    """Statistics for file operations."""
    processed: int = 0
    deleted: int = 0
    merged: int = 0
    errors: int = 0
    total_size: int = 0


class FileManager:
    """Manage file operations and batch processing."""

    def __init__(self):
        """Initialize file manager."""
        self.stats = FileStats()
        logger.debug("Initialized FileManager")

    def delete_empty_files(
        self,
        directory: Path,
        recursive: bool = True,
        dry_run: bool = False
    ) -> FileStats:
        """
        Delete files that are empty or contain only whitespace.

        Args:
            directory: Directory to scan
            recursive: Whether to scan subdirectories
            dry_run: If True, only report what would be deleted

        Returns:
            FileStats: Statistics about the operation

        Raises:
            FileManagerError: If directory doesn't exist or operation fails
        """
        directory = Path(directory)
        
        if not directory.exists():
            raise FileManagerError(f"Directory not found: {directory}")
        
        if not directory.is_dir():
            raise FileManagerError(f"Not a directory: {directory}")
        
        logger.info(f"Scanning for empty files in: {directory} (recursive={recursive})")
        
        stats = FileStats()
        pattern = "**/*" if recursive else "*"
        
        try:
            for file_path in directory.glob(pattern):
                if not file_path.is_file():
                    continue
                
                stats.processed += 1
                
                try:
                    if self._is_empty_or_whitespace(file_path):
                        stats.total_size += file_path.stat().st_size
                        
                        if dry_run:
                            logger.info(f"[DRY-RUN] Would delete: {file_path}")
                        else:
                            file_path.unlink()
                            logger.debug(f"Deleted empty file: {file_path}")
                        
                        stats.deleted += 1
                        
                except Exception as e:
                    logger.error(f"Error processing {file_path}: {e}")
                    stats.errors += 1
            
            self.stats = stats
            logger.info(
                f"Completed: {stats.deleted} files deleted "
                f"({stats.processed} processed, {stats.errors} errors)"
            )
            return stats
            
        except Exception as e:
            raise FileManagerError(f"Failed to scan directory: {e}")

    def _is_empty_or_whitespace(self, file_path: Path) -> bool:
        """
        Check if file is empty or contains only whitespace.

        Args:
            file_path: Path to file

        Returns:
            bool: True if file is empty or whitespace-only
        """
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            # Remove all whitespace and check if anything remains
            return not content.strip()
        except Exception as e:
            logger.warning(f"Could not read {file_path}: {e}")
            return False

    def merge_files(
        self,
        source_dir: Path,
        output_file: Path,
        exclude_empty_lines: bool = False,
        pattern: str = "*",
        recursive: bool = False,
        separator: Optional[str] = None,
        overwrite: bool = False
    ) -> FileStats:
        """
        Merge multiple files into a single output file.

        Args:
            source_dir: Directory containing files to merge
            output_file: Path to output file
            exclude_empty_lines: If True, skip empty lines
            pattern: Glob pattern for files to include (default: all files)
            recursive: Whether to include subdirectories
            separator: Optional separator between files
            overwrite: Whether to overwrite existing output file

        Returns:
            FileStats: Statistics about the operation

        Raises:
            FileManagerError: If operation fails
        """
        source_dir = Path(source_dir)
        output_file = Path(output_file)
        
        # Validation
        if not source_dir.exists():
            raise FileManagerError(f"Source directory not found: {source_dir}")
        
        if not source_dir.is_dir():
            raise FileManagerError(f"Not a directory: {source_dir}")
        
        if output_file.exists() and not overwrite:
            raise FileManagerError(
                f"Output file already exists: {output_file}. "
                "Use overwrite=True to replace it."
            )
        
        logger.info(f"Merging files from {source_dir} -> {output_file}")
        
        stats = FileStats()
        glob_pattern = f"**/{pattern}" if recursive else pattern
        
        try:
            # Collect files to merge
            files_to_merge = []
            for file_path in sorted(source_dir.glob(glob_pattern)):
                if file_path.is_file() and file_path != output_file:
                    files_to_merge.append(file_path)
            
            if not files_to_merge:
                logger.warning(f"No files found matching pattern: {pattern}")
                return stats
            
            logger.info(f"Found {len(files_to_merge)} files to merge")
            
            # Create output file
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with output_file.open('w', encoding='utf-8') as outfile:
                for file_path in files_to_merge:
                    stats.processed += 1
                    
                    try:
                        # Add separator if specified and not first file
                        if separator and stats.merged > 0:
                            outfile.write(separator)
                            outfile.write('\n')
                        
                        # Read and write file content
                        content = file_path.read_text(encoding='utf-8', errors='ignore')
                        
                        if exclude_empty_lines:
                            # Filter out empty lines
                            lines = [
                                line for line in content.split('\n')
                                if line.strip()
                            ]
                            content = '\n'.join(lines)
                        
                        outfile.write(content)
                        if not content.endswith('\n'):
                            outfile.write('\n')
                        
                        stats.merged += 1
                        stats.total_size += file_path.stat().st_size
                        logger.debug(f"Merged: {file_path}")
                        
                    except Exception as e:
                        logger.error(f"Error reading {file_path}: {e}")
                        stats.errors += 1
            
            self.stats = stats
            logger.info(
                f"Merged {stats.merged} files into {output_file} "
                f"({stats.total_size} bytes total, {stats.errors} errors)"
            )
            return stats
            
        except Exception as e:
            raise FileManagerError(f"Failed to merge files: {e}")

    def find_files_by_pattern(
        self,
        directory: Path,
        pattern: str,
        regex: bool = False,
        recursive: bool = True
    ) -> List[Path]:
        """
        Find files matching a pattern.

        Args:
            directory: Directory to search
            pattern: Glob pattern or regex
            regex: If True, treat pattern as regex
            recursive: Whether to search subdirectories

        Returns:
            list: List of matching file paths

        Raises:
            FileManagerError: If directory doesn't exist
        """
        directory = Path(directory)
        
        if not directory.exists():
            raise FileManagerError(f"Directory not found: {directory}")
        
        glob_pattern = f"**/{pattern}" if recursive else pattern
        matches = []
        
        try:
            if regex:
                # Use regex matching
                compiled_pattern = re.compile(pattern)
                search_pattern = "**/*" if recursive else "*"
                
                for file_path in directory.glob(search_pattern):
                    if file_path.is_file() and compiled_pattern.search(file_path.name):
                        matches.append(file_path)
            else:
                # Use glob matching
                for file_path in directory.glob(glob_pattern):
                    if file_path.is_file():
                        matches.append(file_path)
            
            logger.info(f"Found {len(matches)} files matching: {pattern}")
            return sorted(matches)
            
        except Exception as e:
            raise FileManagerError(f"Failed to find files: {e}")

    def get_directory_stats(self, directory: Path) -> Dict:
        """
        Get statistics about a directory.

        Args:
            directory: Directory to analyze

        Returns:
            dict: Directory statistics

        Raises:
            FileManagerError: If directory doesn't exist
        """
        directory = Path(directory)
        
        if not directory.exists():
            raise FileManagerError(f"Directory not found: {directory}")
        
        stats = {
            "path": str(directory),
            "total_files": 0,
            "total_dirs": 0,
            "total_size": 0,
            "empty_files": 0,
            "largest_file": None,
            "largest_size": 0
        }
        
        try:
            for item in directory.rglob("*"):
                if item.is_file():
                    stats["total_files"] += 1
                    size = item.stat().st_size
                    stats["total_size"] += size
                    
                    # Check if empty
                    if size == 0 or self._is_empty_or_whitespace(item):
                        stats["empty_files"] += 1
                    
                    # Track largest file
                    if size > stats["largest_size"]:
                        stats["largest_size"] = size
                        stats["largest_file"] = str(item)
                        
                elif item.is_dir():
                    stats["total_dirs"] += 1
            
            logger.debug(f"Directory stats: {stats}")
            return stats
            
        except Exception as e:
            raise FileManagerError(f"Failed to get directory stats: {e}")
