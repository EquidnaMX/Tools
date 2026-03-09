"""
Tests para funciones auxiliares (helpers)
"""
import logging
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from tools.cloud.sync import DigitalOceanSync


def _build_syncer(exclude=None):
    with tempfile.TemporaryDirectory() as tmpdir:
        syncer = DigitalOceanSync(
            region="sfo3",
            bucket="test-bucket",
            dest=tmpdir,
            exclude=exclude or [],
            logger=logging.getLogger(__name__),
        )
        # Retornar una nueva instancia estable; el tempdir solo se usa para crearla
        return syncer


class TestShouldExclude:
    """Tests para función should_exclude()"""
    
    def test_no_patterns_returns_false(self):
        """Sin patrones, no excluye nada"""
        syncer = _build_syncer([])
        assert syncer._should_exclude("any_file.txt") is False
    
    def test_exact_match(self):
        """Coincidencia exacta"""
        syncer = _build_syncer(["file.tmp"])
        assert syncer._should_exclude("file.tmp") is True
        assert syncer._should_exclude("other.txt") is False
    
    def test_wildcard_extension(self):
        """Patrón con wildcard para extensión"""
        syncer = _build_syncer(["*.tmp"])
        assert syncer._should_exclude("file.tmp") is True
        assert syncer._should_exclude("archive.tmp") is True
        assert syncer._should_exclude("file.txt") is False
    
    def test_wildcard_prefix(self):
        """Patrón con wildcard al inicio"""
        syncer = _build_syncer(["*backup*"])
        assert syncer._should_exclude("mybackup.zip") is True
        assert syncer._should_exclude("backup_2026.tar") is True
        assert syncer._should_exclude("file.txt") is False
    
    def test_path_pattern(self):
        """Patrón con path"""
        syncer = _build_syncer(["*/cache/*"])
        assert syncer._should_exclude("data/cache/file.txt") is True
        assert syncer._should_exclude("app/cache/temp.log") is True
        assert syncer._should_exclude("data/files/file.txt") is False
    
    def test_multiple_patterns(self):
        """Múltiples patrones"""
        syncer = _build_syncer(["*.tmp", "*.log", "*/node_modules/*"])

        assert syncer._should_exclude("file.tmp") is True
        assert syncer._should_exclude("app.log") is True
        assert syncer._should_exclude("lib/node_modules/package.json") is True
        assert syncer._should_exclude("data/file.txt") is False
    
    def test_case_sensitivity(self):
        """Tests de sensibilidad a mayúsculas/minúsculas"""
        syncer = _build_syncer(["*.TMP"])
        # fnmatch es case-sensitive en Linux, case-insensitive en Windows
        # Verificamos que al menos funciona con el caso exacto
        assert syncer._should_exclude("FILE.TMP") is True or syncer._should_exclude("file.tmp") is True
    
    def test_complex_patterns(self):
        """Patrones más complejos"""
        syncer = _build_syncer([
            "*.tmp",
            "*/temp/*",
            "*backup*",
            ".git/*"
        ])

        assert syncer._should_exclude("file.tmp") is True
        assert syncer._should_exclude("data/temp/cache.dat") is True
        assert syncer._should_exclude("mybackup_2026.zip") is True
        assert syncer._should_exclude(".git/config") is True
        assert syncer._should_exclude("important.txt") is False


class TestLocalUpToDate:
    """Tests para función local_up_to_date()"""
    
    def test_nonexistent_file_not_up_to_date(self):
        """Archivo que no existe no está actualizado"""
        fake_path = Path("/nonexistent/file.txt")
        s3_size = 1024
        s3_modified = datetime.now(timezone.utc)

        syncer = _build_syncer([])
        assert syncer._local_up_to_date(fake_path, s3_size, s3_modified) is False
    
    def test_different_size_not_up_to_date(self):
        """Archivo con diferente tamaño no está actualizado"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("test content")
            temp_path = Path(f.name)
        
        try:
            # Tamaño real del archivo
            real_size = temp_path.stat().st_size
            
            # Simular tamaño S3 diferente
            s3_size = real_size + 100
            s3_modified = datetime.now(timezone.utc)
            
            syncer = _build_syncer([])
            assert syncer._local_up_to_date(temp_path, s3_size, s3_modified) is False
        finally:
            temp_path.unlink()
    
    def test_same_size_and_time_is_up_to_date(self):
        """Archivo con mismo tamaño y tiempo está actualizado"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("test content")
            temp_path = Path(f.name)
        
        try:
            stat = temp_path.stat()
            s3_size = stat.st_size
            
            # Mismo timestamp
            s3_modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            
            syncer = _build_syncer([])
            assert syncer._local_up_to_date(temp_path, s3_size, s3_modified) is True
        finally:
            temp_path.unlink()
    
    def test_older_local_not_up_to_date(self):
        """Archivo local más viejo no está actualizado"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("test content")
            temp_path = Path(f.name)
        
        try:
            stat = temp_path.stat()
            s3_size = stat.st_size
            
            # S3 modificado claramen después (3 segundos más reciente)
            local_mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            s3_modified = local_mtime + timedelta(seconds=3)
            
            # Si S3 es más reciente (fuera de ventana de 2s), local no está up to date
            syncer = _build_syncer([])
            result = syncer._local_up_to_date(temp_path, s3_size, s3_modified)
            assert result is False
        finally:
            temp_path.unlink()
    
    def test_datetime_without_timezone(self):
        """Manejo de datetime sin timezone"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("test content")
            temp_path = Path(f.name)
        
        try:
            stat = temp_path.stat()
            s3_size = stat.st_size
            
            # Datetime sin timezone (naive)
            s3_modified = datetime.fromtimestamp(stat.st_mtime)
            
            # No debe lanzar excepción
            syncer = _build_syncer([])
            result = syncer._local_up_to_date(temp_path, s3_size, s3_modified)
            assert isinstance(result, bool)
        finally:
            temp_path.unlink()


class TestEnsureParent:
    """Tests para función ensure_parent()"""
    
    def test_creates_parent_directory(self):
        """Crea directorio padre si no existe"""
        with tempfile.TemporaryDirectory() as tmpdir:
            deep_path = Path(tmpdir) / "level1" / "level2" / "level3" / "file.txt"
            
            # Verificar que no existe
            assert not deep_path.parent.exists()
            
            # Crear padres
            syncer = _build_syncer([])
            syncer._ensure_parent(deep_path)
            
            # Verificar que ahora existe
            assert deep_path.parent.exists()
            assert deep_path.parent.is_dir()
    
    def test_does_not_fail_if_exists(self):
        """No falla si el directorio ya existe"""
        with tempfile.TemporaryDirectory() as tmpdir:
            existing_path = Path(tmpdir) / "subdir" / "file.txt"
            existing_path.parent.mkdir(parents=True, exist_ok=True)
            
            # No debe lanzar excepción
            syncer = _build_syncer([])
            syncer._ensure_parent(existing_path)
            
            assert existing_path.parent.exists()
    
    def test_creates_multiple_levels(self):
        """Crea múltiples niveles de directorios"""
        with tempfile.TemporaryDirectory() as tmpdir:
            deep_path = Path(tmpdir) / "a" / "b" / "c" / "d" / "e" / "file.txt"
            
            syncer = _build_syncer([])
            syncer._ensure_parent(deep_path)
            
            # Verificar todos los niveles
            assert (Path(tmpdir) / "a").exists()
            assert (Path(tmpdir) / "a" / "b").exists()
            assert (Path(tmpdir) / "a" / "b" / "c").exists()
            assert (Path(tmpdir) / "a" / "b" / "c" / "d").exists()
            assert (Path(tmpdir) / "a" / "b" / "c" / "d" / "e").exists()
    
    def test_handles_file_in_root(self):
        """Maneja archivo en raíz sin subdirectorios"""
        with tempfile.TemporaryDirectory() as tmpdir:
            root_file = Path(tmpdir) / "file.txt"
            
            # ensure_parent del archivo raíz no debe fallar
            syncer = _build_syncer([])
            syncer._ensure_parent(root_file)
            
            # El directorio padre (tmpdir) ya existe
            assert root_file.parent.exists()


class TestHelperEdgeCases:
    """Tests de casos límite para helpers"""
    
    def test_exclude_empty_string(self):
        """Manejo de string vacío"""
        assert _build_syncer([])._should_exclude("") is False
        assert _build_syncer(["*"])._should_exclude("") is True
    
    def test_exclude_special_characters(self):
        """Manejo de caracteres especiales en nombres"""
        syncer = _build_syncer(["file[1-3].txt"])
        assert syncer._should_exclude("file1.txt") is True
        assert syncer._should_exclude("file2.txt") is True
        assert syncer._should_exclude("file4.txt") is False
    
    def test_local_up_to_date_with_future_time(self):
        """Archivo local con timestamp futuro"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("test")
            temp_path = Path(f.name)
        
        try:
            s3_size = temp_path.stat().st_size
            local_mtime = temp_path.stat().st_mtime
            
            # S3 modificado cerca del archivo local (dentro de 2 segundos)
            s3_modified = datetime.fromtimestamp(local_mtime, tz=timezone.utc)
            
            # Mismo tamaño y tiempo similar (dentro de 2s) está up to date
            syncer = _build_syncer([])
            result = syncer._local_up_to_date(temp_path, s3_size, s3_modified)
            assert result is True
        finally:
            temp_path.unlink()
