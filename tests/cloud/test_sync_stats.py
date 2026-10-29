"""
Tests para la clase SyncStats
"""
import json
from datetime import datetime

from tools.cloud.sync import SyncStats


class TestSyncStatsInit:
    """Tests para inicialización de SyncStats"""
    
    def test_init_creates_empty_stats(self):
        """Verifica que la inicialización crea estadísticas vacías"""
        stats = SyncStats()
        
        assert stats.timestamp_start is not None
        assert stats.timestamp_end is None
        assert stats.downloaded == []
        assert stats.updated == []
        assert stats.skipped == []
        assert stats.deleted == []
        assert stats.errors == []
    
    def test_init_timestamp_format(self):
        """Verifica que el timestamp inicial está en formato ISO-8601"""
        stats = SyncStats()
        
        # Debe poder parsearse como datetime
        dt = datetime.fromisoformat(stats.timestamp_start.replace('Z', '+00:00'))
        assert dt.tzinfo is not None  # Debe tener timezone


class TestSyncStatsAddMethods:
    """Tests para métodos add_*()"""
    
    def test_add_downloaded(self):
        """Verifica que add_downloaded() registra correctamente"""
        stats = SyncStats()
        
        stats.add_downloaded("file1.txt", 1024, 0.5)
        
        assert len(stats.downloaded) == 1
        assert stats.downloaded[0]["key"] == "file1.txt"
        assert stats.downloaded[0]["size_bytes"] == 1024
        assert stats.downloaded[0]["duration_sec"] == 0.5
        assert "speed_mb_s" in stats.downloaded[0]
    
    def test_add_downloaded_multiple(self):
        """Verifica que se pueden agregar múltiples archivos descargados"""
        stats = SyncStats()
        
        stats.add_downloaded("file1.txt", 1024, 0.5)
        stats.add_downloaded("file2.txt", 2048, 1.0)
        
        assert len(stats.downloaded) == 2
    
    def test_add_updated(self):
        """Verifica que add_updated() registra correctamente"""
        stats = SyncStats()
        
        stats.add_updated("file3.txt", 512)
        
        assert len(stats.updated) == 1
        assert stats.updated[0]["key"] == "file3.txt"
        assert stats.updated[0]["size_bytes"] == 512
    
    def test_add_skipped(self):
        """Verifica que add_skipped() registra correctamente"""
        stats = SyncStats()
        
        stats.add_skipped("file4.txt", 256)
        
        assert len(stats.skipped) == 1
        assert stats.skipped[0]["key"] == "file4.txt"
        assert stats.skipped[0]["size_bytes"] == 256
    
    def test_add_deleted(self):
        """Verifica que add_deleted() registra correctamente"""
        stats = SyncStats()
        
        stats.add_deleted("/path/to/file.txt")
        
        assert len(stats.deleted) == 1
        assert stats.deleted[0]["path"] == "/path/to/file.txt"
    
    def test_add_error(self):
        """Verifica que add_error() registra correctamente"""
        stats = SyncStats()
        
        stats.add_error("file5.txt", "Connection timeout")
        
        assert len(stats.errors) == 1
        assert stats.errors[0]["key"] == "file5.txt"
        assert stats.errors[0]["error"] == "Connection timeout"


class TestSyncStatsFinalize:
    """Tests para método finalize()"""
    
    def test_finalize_sets_end_timestamp(self):
        """Verifica que finalize() establece timestamp_end"""
        stats = SyncStats()
        
        assert stats.timestamp_end is None
        stats.finalize()
        assert stats.timestamp_end is not None
    
    def test_finalize_timestamp_after_start(self):
        """Verifica que timestamp_end >= timestamp_start"""
        stats = SyncStats()
        stats.finalize()
        
        start = datetime.fromisoformat(stats.timestamp_start.replace('Z', '+00:00'))
        end = datetime.fromisoformat(stats.timestamp_end.replace('Z', '+00:00'))
        
        assert end >= start


class TestSyncStatsCounts:
    """Tests para método counts()"""
    
    def test_counts_empty(self):
        """Verifica counts() con estadísticas vacías"""
        stats = SyncStats()
        stats.finalize()
        result = stats.to_dict()
        counts = result["counts"]
        
        assert counts["downloaded"] == 0
        assert counts["updated"] == 0
        assert counts["skipped"] == 0
        assert counts["deleted"] == 0
        assert counts["errors"] == 0
        assert counts["total"] == 0
    
    def test_counts_with_data(self):
        """Verifica counts() con datos"""
        stats = SyncStats()
        stats.add_downloaded("file1.txt", 1024, 0.5)
        stats.add_downloaded("file2.txt", 2048, 1.0)
        stats.add_updated("file3.txt", 512)
        stats.add_skipped("file4.txt", 256)
        stats.add_deleted("/path/file.txt")
        stats.add_error("file5.txt", "error")
        stats.finalize()
        
        result = stats.to_dict()
        counts = result["counts"]
        
        assert counts["downloaded"] == 2
        assert counts["updated"] == 1
        assert counts["skipped"] == 1
        assert counts["deleted"] == 1
        assert counts["errors"] == 1
        assert counts["total"] == 4  # downloaded + updated + skipped


class TestSyncStatsBytes:
    """Tests para método bytes_summary()"""
    
    def test_bytes_empty(self):
        """Verifica bytes_summary() con estadísticas vacías"""
        stats = SyncStats()
        stats.finalize()
        result = stats.to_dict()
        bytes_sum = result["bytes"]
        
        assert bytes_sum["downloaded"] == 0
        assert bytes_sum["updated"] == 0
        assert bytes_sum["skipped"] == 0
        assert bytes_sum["total"] == 0
    
    def test_bytes_with_data(self):
        """Verifica bytes_summary() con datos"""
        stats = SyncStats()
        stats.add_downloaded("file1.txt", 1024, 0.5)
        stats.add_downloaded("file2.txt", 2048, 1.0)
        stats.add_updated("file3.txt", 512)
        stats.add_skipped("file4.txt", 256)
        stats.finalize()
        
        result = stats.to_dict()
        bytes_sum = result["bytes"]
        
        assert bytes_sum["downloaded"] == 3072  # 1024 + 2048
        assert bytes_sum["updated"] == 512
        assert bytes_sum["skipped"] == 256
        assert bytes_sum["total"] == 3840  # 3072 + 512 + 256


class TestSyncStatsToDict:
    """Tests para método to_dict()"""
    
    def test_to_dict_basic_structure(self):
        """Verifica estructura básica del diccionario"""
        stats = SyncStats()
        stats.finalize()
        
        result = stats.to_dict(include_details=False)
        
        assert "timestamp_start" in result
        assert "timestamp_end" in result
        assert "duration_seconds" in result
        assert "status" in result
        assert "counts" in result
        assert "bytes" in result
        assert "throughput_mb_s" in result
        assert "throughput_gb" in result
    
    def test_to_dict_without_details(self):
        """Verifica que sin include_details no hay sección 'details'"""
        stats = SyncStats()
        stats.add_downloaded("file1.txt", 1024, 0.5)
        stats.finalize()
        
        result = stats.to_dict(include_details=False)
        
        assert "details" not in result
    
    def test_to_dict_with_details(self):
        """Verifica que con include_details hay sección 'details'"""
        stats = SyncStats()
        stats.add_downloaded("file1.txt", 1024, 0.5)
        stats.add_error("file2.txt", "error")
        stats.finalize()
        
        result = stats.to_dict(include_details=True)
        
        assert "details" in result
        assert "downloaded" in result["details"]
        assert "errors" in result["details"]
        assert len(result["details"]["downloaded"]) == 1
        assert len(result["details"]["errors"]) == 1
    
    def test_to_dict_status_completed(self):
        """Verifica que status sea 'success' sin errores"""
        stats = SyncStats()
        stats.add_downloaded("file.txt", 1000, 0.5)
        stats.finalize()
        
        result = stats.to_dict()
        
        assert result["status"] == "success"
    
    def test_to_dict_status_with_errors(self):
        """Verifica que status es 'completed_with_errors' con errores"""
        stats = SyncStats()
        stats.add_downloaded("file1.txt", 1024, 0.5)
        stats.add_error("file2.txt", "Connection timeout")
        stats.finalize()
        
        result = stats.to_dict()
        
        assert result["status"] == "completed_with_errors"
    
    def test_to_dict_json_serializable(self):
        """Verifica que el resultado es serializable a JSON"""
        stats = SyncStats()
        stats.add_downloaded("file1.txt", 1024, 0.5)
        stats.add_error("file2.txt", "error")
        stats.finalize()
        
        result = stats.to_dict(include_details=True)
        
        # No debe lanzar excepción
        json_str = json.dumps(result)
        assert json_str is not None
        
        # Y debe poder parsearse de vuelta
        parsed = json.loads(json_str)
        assert parsed["counts"]["downloaded"] == 1
        assert parsed["counts"]["errors"] == 1


class TestSyncStatsEdgeCases:
    """Tests para casos límite"""
    
    def test_zero_duration_download(self):
        """Verifica manejo de duración cero"""
        stats = SyncStats()
        stats.add_downloaded("fast_file.txt", 1024, 0.0)
        
        # No debe lanzar excepción por división por cero
        result = stats.to_dict()
        assert result["throughput_mb_s"] == 0
    
    def test_large_file_sizes(self):
        """Verifica manejo de archivos grandes (GB)"""
        stats = SyncStats()
        
        # 5 GB file
        stats.add_downloaded("large_file.iso", 5 * 1024**3, 120.0)
        stats.finalize()
        
        result = stats.to_dict()
        assert result["bytes"]["downloaded"] == 5 * 1024**3
        assert result["throughput_gb"] > 0
    
    def test_many_files(self):
        """Verifica manejo de muchos archivos"""
        stats = SyncStats()
        
        for i in range(1000):
            stats.add_downloaded(f"file_{i}.txt", 1024, 0.1)
        
        stats.finalize()
        result = stats.to_dict()
        counts = result["counts"]
        assert counts["downloaded"] == 1000
        assert counts["total"] == 1000
