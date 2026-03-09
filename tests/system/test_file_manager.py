"""
Tests for FileManager.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
import tempfile
import shutil

from tools.system.file_manager import FileManager, FileManagerError, FileStats


class TestFileManager:
    """Test FileManager functionality."""

    def test_init(self):
        """Test FileManager initialization."""
        manager = FileManager()
        assert isinstance(manager.stats, FileStats)

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        tmpdir = tempfile.mkdtemp()
        yield Path(tmpdir)
        # Cleanup
        shutil.rmtree(tmpdir, ignore_errors=True)

    @pytest.fixture
    def manager(self):
        """Create a FileManager instance."""
        return FileManager()

    def test_delete_empty_files_directory_not_found(self, manager):
        """Test error when directory doesn't exist."""
        with pytest.raises(FileManagerError, match="Directory not found"):
            manager.delete_empty_files(Path("/nonexistent/path"))

    def test_delete_empty_files_not_a_directory(self, manager, temp_dir):
        """Test error when path is not a directory."""
        file_path = temp_dir / "test.txt"
        file_path.write_text("test")
        
        with pytest.raises(FileManagerError, match="Not a directory"):
            manager.delete_empty_files(file_path)

    def test_delete_empty_files_success(self, manager, temp_dir):
        """Test deleting empty files."""
        # Create some files
        (temp_dir / "empty.txt").write_text("")
        (temp_dir / "whitespace.txt").write_text("   \n  \n  ")
        (temp_dir / "not_empty.txt").write_text("content")
        
        stats = manager.delete_empty_files(temp_dir, recursive=False)
        
        assert stats.processed == 3
        assert stats.deleted == 2  # empty.txt and whitespace.txt
        assert stats.errors == 0
        
        # Verify remaining file
        assert (temp_dir / "not_empty.txt").exists()
        assert not (temp_dir / "empty.txt").exists()

    def test_delete_empty_files_dry_run(self, manager, temp_dir):
        """Test dry run mode."""
        (temp_dir / "empty.txt").write_text("")
        
        stats = manager.delete_empty_files(temp_dir, dry_run=True)
        
        # File should still exist
        assert (temp_dir / "empty.txt").exists()
        assert stats.deleted == 1

    def test_delete_empty_files_recursive(self, manager, temp_dir):
        """Test recursive directory scanning."""
        # Create subdirectory
        subdir = temp_dir / "subdir"
        subdir.mkdir()
        
        (temp_dir / "empty1.txt").write_text("")
        (subdir / "empty2.txt").write_text("")
        
        stats = manager.delete_empty_files(temp_dir, recursive=True)
        
        assert stats.deleted == 2

    def test_is_empty_or_whitespace(self, manager, temp_dir):
        """Test whitespace detection."""
        empty_file = temp_dir / "empty.txt"
        empty_file.write_text("")
        assert manager._is_empty_or_whitespace(empty_file) is True
        
        whitespace_file = temp_dir / "whitespace.txt"
        whitespace_file.write_text("  \n\t\n  ")
        assert manager._is_empty_or_whitespace(whitespace_file) is True
        
        content_file = temp_dir / "content.txt"
        content_file.write_text("hello")
        assert manager._is_empty_or_whitespace(content_file) is False

    def test_merge_files_directory_not_found(self, manager):
        """Test error when source directory doesn't exist."""
        with pytest.raises(FileManagerError, match="Source directory not found"):
            manager.merge_files(
                Path("/nonexistent"),
                Path("output.txt")
            )

    def test_merge_files_output_exists(self, manager, temp_dir):
        """Test error when output file already exists."""
        output = temp_dir / "output.txt"
        output.write_text("existing")
        
        with pytest.raises(FileManagerError, match="already exists"):
            manager.merge_files(temp_dir, output)

    def test_merge_files_success(self, manager, temp_dir):
        """Test merging files."""
        # Create files to merge
        (temp_dir / "file1.txt").write_text("Line 1\n")
        (temp_dir / "file2.txt").write_text("Line 2\n")
        (temp_dir / "file3.txt").write_text("Line 3\n")
        
        output = temp_dir / "merged.txt"
        
        stats = manager.merge_files(temp_dir, output, pattern="*.txt")
        
        assert stats.merged == 3
        assert stats.errors == 0
        assert output.exists()
        
        content = output.read_text()
        assert "Line 1" in content
        assert "Line 2" in content
        assert "Line 3" in content

    def test_merge_files_with_separator(self, manager, temp_dir):
        """Test merging with separator."""
        (temp_dir / "file1.txt").write_text("Content 1")
        (temp_dir / "file2.txt").write_text("Content 2")
        
        output = temp_dir / "merged.txt"
        
        manager.merge_files(temp_dir, output, separator="---")
        
        content = output.read_text()
        assert "---" in content

    def test_merge_files_exclude_empty_lines(self, manager, temp_dir):
        """Test excluding empty lines."""
        (temp_dir / "file1.txt").write_text("Line 1\n\nLine 2\n")
        
        output = temp_dir / "merged.txt"
        
        manager.merge_files(temp_dir, output, exclude_empty_lines=True)
        
        content = output.read_text()
        lines = [line for line in content.split('\n') if line.strip()]
        assert len(lines) == 2

    def test_merge_files_with_pattern(self, manager, temp_dir):
        """Test merging only matching files."""
        (temp_dir / "data1.txt").write_text("Text 1")
        (temp_dir / "data2.log").write_text("Log 1")
        (temp_dir / "data3.txt").write_text("Text 2")
        
        output = temp_dir / "merged.txt"
        
        stats = manager.merge_files(temp_dir, output, pattern="*.txt")
        
        # Should only merge .txt files (excluding output.txt itself)
        assert stats.merged == 2

    def test_merge_files_recursive(self, manager, temp_dir):
        """Test recursive merging."""
        subdir = temp_dir / "subdir"
        subdir.mkdir()
        
        (temp_dir / "file1.txt").write_text("Root file")
        (subdir / "file2.txt").write_text("Sub file")
        
        output = temp_dir / "merged.txt"
        
        stats = manager.merge_files(temp_dir, output, recursive=True, pattern="*.txt")
        
        assert stats.merged == 2

    def test_find_files_by_pattern_glob(self, manager, temp_dir):
        """Test finding files with glob pattern."""
        (temp_dir / "test1.txt").write_text("")
        (temp_dir / "test2.txt").write_text("")
        (temp_dir / "other.log").write_text("")
        
        matches = manager.find_files_by_pattern(temp_dir, "*.txt")
        
        assert len(matches) == 2

    def test_find_files_by_pattern_regex(self, manager, temp_dir):
        """Test finding files with regex."""
        (temp_dir / "test_001.txt").write_text("")
        (temp_dir / "test_002.txt").write_text("")
        (temp_dir / "other.txt").write_text("")
        
        matches = manager.find_files_by_pattern(temp_dir, r"test_\d+\.txt", regex=True)
        
        assert len(matches) == 2

    def test_find_files_directory_not_found(self, manager):
        """Test error when directory doesn't exist."""
        with pytest.raises(FileManagerError, match="Directory not found"):
            manager.find_files_by_pattern(Path("/nonexistent"), "*.txt")

    def test_get_directory_stats(self, manager, temp_dir):
        """Test getting directory statistics."""
        # Create some files
        (temp_dir / "file1.txt").write_text("content")
        (temp_dir / "file2.txt").write_text("")
        
        subdir = temp_dir / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("more content")
        
        stats = manager.get_directory_stats(temp_dir)
        
        assert stats["total_files"] == 3
        assert stats["total_dirs"] == 1
        assert stats["empty_files"] >= 1
        assert stats["total_size"] > 0
        assert "path" in stats

    def test_get_directory_stats_not_found(self, manager):
        """Test error when directory doesn't exist."""
        with pytest.raises(FileManagerError, match="Directory not found"):
            manager.get_directory_stats(Path("/nonexistent"))

    def test_stats_dataclass(self):
        """Test FileStats dataclass."""
        stats = FileStats(processed=10, deleted=5, merged=3)
        
        assert stats.processed == 10
        assert stats.deleted == 5
        assert stats.merged == 3
        assert stats.errors == 0
        assert stats.total_size == 0
