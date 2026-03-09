"""
Tests for UploadStats class
"""
import json
from datetime import datetime
import pytest
from tools.cloud.sync import UploadStats


class TestUploadStatsInit:
    """Tests for UploadStats initialization"""
    
    def test_init_creates_empty_stats(self):
        """Verifies initialization creates empty statistics"""
        stats = UploadStats()
        
        assert stats.timestamp_start is not None
        assert stats.timestamp_end is None
        assert stats.uploaded == []
        assert stats.updated == []
        assert stats.skipped == []
        assert stats.deleted == []
        assert stats.errors == []
    
    def test_init_timestamp_format(self):
        """Verifies initial timestamp is in ISO-8601 format"""
        stats = UploadStats()
        
        # Should be parseable as datetime
        dt = datetime.fromisoformat(stats.timestamp_start.replace('Z', '+00:00'))
        assert dt.tzinfo is not None  # Must have timezone


class TestUploadStatsAddMethods:
    """Tests for add_*() methods"""
    
    def test_add_uploaded(self):
        """Verifies add_uploaded() registers correctly"""
        stats = UploadStats()
        
        stats.add_uploaded("file1.txt", 1024, 0.5)
        
        assert len(stats.uploaded) == 1
        assert stats.uploaded[0]["key"] == "file1.txt"
        assert stats.uploaded[0]["size_bytes"] == 1024
        assert stats.uploaded[0]["duration_sec"] == 0.5
        assert "speed_mb_s" in stats.uploaded[0]
    
    def test_add_uploaded_multiple(self):
        """Verifies multiple uploads can be added"""
        stats = UploadStats()
        
        stats.add_uploaded("file1.txt", 1024, 0.5)
        stats.add_uploaded("file2.txt", 2048, 1.0)
        
        assert len(stats.uploaded) == 2
    
    def test_add_updated(self):
        """Verifies add_updated() registers correctly"""
        stats = UploadStats()
        
        stats.add_updated("file3.txt", 512)
        
        assert len(stats.updated) == 1
        assert stats.updated[0]["key"] == "file3.txt"
        assert stats.updated[0]["size_bytes"] == 512
    
    def test_add_skipped(self):
        """Verifies add_skipped() registers correctly"""
        stats = UploadStats()
        
        stats.add_skipped("file4.txt", 256)
        
        assert len(stats.skipped) == 1
        assert stats.skipped[0]["key"] == "file4.txt"
        assert stats.skipped[0]["size_bytes"] == 256
    
    def test_add_deleted(self):
        """Verifies add_deleted() registers correctly"""
        stats = UploadStats()
        
        stats.add_deleted("file5.txt")
        
        assert len(stats.deleted) == 1
        assert stats.deleted[0]["key"] == "file5.txt"
    
    def test_add_error(self):
        """Verifies add_error() registers correctly"""
        stats = UploadStats()
        
        stats.add_error("/path/to/file.txt", "Permission denied")
        
        assert len(stats.errors) == 1
        assert stats.errors[0]["path"] == "/path/to/file.txt"
        assert stats.errors[0]["error"] == "Permission denied"


class TestUploadStatsFinalize:
    """Tests for finalize() method"""
    
    def test_finalize_sets_end_timestamp(self):
        """Verifies finalize() sets end timestamp"""
        stats = UploadStats()
        
        assert stats.timestamp_end is None
        stats.finalize()
        assert stats.timestamp_end is not None
    
    def test_finalize_timestamp_after_start(self):
        """Verifies end timestamp is after start timestamp"""
        stats = UploadStats()
        
        stats.finalize()
        
        start = datetime.fromisoformat(stats.timestamp_start.replace('Z', '+00:00'))
        end = datetime.fromisoformat(stats.timestamp_end.replace('Z', '+00:00'))
        
        assert end >= start


class TestUploadStatsCounts:
    """Tests for statistics counts in to_dict()"""
    
    def test_counts_empty(self):
        """Verifies counts are 0 for empty stats"""
        stats = UploadStats()
        stats.finalize()
        
        result = stats.to_dict()
        
        assert result["counts"]["uploaded"] == 0
        assert result["counts"]["updated"] == 0
        assert result["counts"]["skipped"] == 0
        assert result["counts"]["deleted"] == 0
        assert result["counts"]["errors"] == 0
        assert result["counts"]["total"] == 0
    
    def test_counts_with_data(self):
        """Verifies counts are correct with data"""
        stats = UploadStats()
        
        stats.add_uploaded("file1.txt", 1024, 0.5)
        stats.add_uploaded("file2.txt", 2048, 1.0)
        stats.add_updated("file3.txt", 512)
        stats.add_skipped("file4.txt", 256)
        stats.add_error("/path/file5.txt", "Error")
        
        stats.finalize()
        result = stats.to_dict()
        
        assert result["counts"]["uploaded"] == 2
        assert result["counts"]["updated"] == 1
        assert result["counts"]["skipped"] == 1
        assert result["counts"]["errors"] == 1
        assert result["counts"]["total"] == 4  # uploaded + updated + skipped


class TestUploadStatsBytes:
    """Tests for byte statistics in to_dict()"""
    
    def test_bytes_empty(self):
        """Verifies bytes are 0 for empty stats"""
        stats = UploadStats()
        stats.finalize()
        
        result = stats.to_dict()
        
        assert result["bytes"]["uploaded"] == 0
        assert result["bytes"]["updated"] == 0
        assert result["bytes"]["skipped"] == 0
        assert result["bytes"]["total"] == 0
    
    def test_bytes_with_data(self):
        """Verifies byte counts are correct"""
        stats = UploadStats()
        
        stats.add_uploaded("file1.txt", 1024, 0.5)
        stats.add_uploaded("file2.txt", 2048, 1.0)
        stats.add_updated("file3.txt", 512)
        stats.add_skipped("file4.txt", 256)
        
        stats.finalize()
        result = stats.to_dict()
        
        assert result["bytes"]["uploaded"] == 3072  # 1024 + 2048
        assert result["bytes"]["updated"] == 512
        assert result["bytes"]["skipped"] == 256
        assert result["bytes"]["total"] == 3840  # 3072 + 512 + 256


class TestUploadStatsToDict:
    """Tests for to_dict() method"""
    
    def test_to_dict_basic_structure(self):
        """Verifies basic structure of to_dict() output"""
        stats = UploadStats()
        stats.finalize()
        
        result = stats.to_dict()
        
        assert "timestamp_start" in result
        assert "timestamp_end" in result
        assert "duration_seconds" in result
        assert "status" in result
        assert "counts" in result
        assert "bytes" in result
        assert "throughput_mb_s" in result
        assert "throughput_gb" in result
    
    def test_to_dict_without_details(self):
        """Verifies details are not included by default"""
        stats = UploadStats()
        stats.add_uploaded("file1.txt", 1024, 0.5)
        stats.finalize()
        
        result = stats.to_dict(include_details=False)
        
        assert "details" not in result
    
    def test_to_dict_with_details(self):
        """Verifies details are included when requested"""
        stats = UploadStats()
        stats.add_uploaded("file1.txt", 1024, 0.5)
        stats.add_updated("file2.txt", 512)
        stats.add_error("/path/file3.txt", "Error")
        stats.finalize()
        
        result = stats.to_dict(include_details=True)
        
        assert "details" in result
        assert "uploaded" in result["details"]
        assert "updated" in result["details"]
        assert "errors" in result["details"]
        assert len(result["details"]["uploaded"]) == 1
        assert len(result["details"]["updated"]) == 1
        assert len(result["details"]["errors"]) == 1
    
    def test_to_dict_status_completed(self):
        """Verifies status is 'success' when no errors"""
        stats = UploadStats()
        stats.add_uploaded("file1.txt", 1024, 0.5)
        stats.finalize()
        
        result = stats.to_dict()
        
        assert result["status"] == "success"
    
    def test_to_dict_status_with_errors(self):
        """Verifies status is 'completed_with_errors' when errors exist"""
        stats = UploadStats()
        stats.add_uploaded("file1.txt", 1024, 0.5)
        stats.add_error("/path/file2.txt", "Error")
        stats.finalize()
        
        result = stats.to_dict()
        
        assert result["status"] == "completed_with_errors"
    
    def test_to_dict_json_serializable(self):
        """Verifies to_dict() output is JSON serializable"""
        stats = UploadStats()
        stats.add_uploaded("file1.txt", 1024, 0.5)
        stats.add_updated("file2.txt", 512)
        stats.finalize()
        
        result = stats.to_dict(include_details=True)
        
        # Should not raise exception
        json_str = json.dumps(result)
        assert json_str is not None


class TestUploadStatsEdgeCases:
    """Tests for edge cases"""
    
    def test_zero_duration_upload(self):
        """Verifies handling of zero-duration upload (instant)"""
        stats = UploadStats()
        
        # Upload with 0 duration should not cause division by zero
        stats.add_uploaded("file1.txt", 1024, 0.0)
        
        assert len(stats.uploaded) == 1
        assert stats.uploaded[0]["speed_mb_s"] == 0  # Avoids division by zero
    
    def test_large_file_sizes(self):
        """Verifies handling of large file sizes (multi-GB)"""
        stats = UploadStats()
        
        # Upload 5GB file
        large_size = 5 * 1024 * 1024 * 1024  # 5GB in bytes
        stats.add_uploaded("large_file.iso", large_size, 60.0)
        stats.finalize()
        
        result = stats.to_dict()
        
        assert result["bytes"]["uploaded"] == large_size
        assert result["throughput_gb"] > 0
    
    def test_many_files(self):
        """Verifies handling of many files"""
        stats = UploadStats()
        
        # Upload 1000 files
        for i in range(1000):
            stats.add_uploaded(f"file{i}.txt", 1024, 0.01)
        
        stats.finalize()
        result = stats.to_dict()
        
        assert result["counts"]["uploaded"] == 1000
        assert result["bytes"]["uploaded"] == 1024 * 1000
