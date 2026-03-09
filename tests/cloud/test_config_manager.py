"""
Tests para config_manager.py
"""
import pytest
import tempfile
import yaml
from pathlib import Path
from tools.cloud.config_manager import ConfigProfile, ConfigManager, ConfigError


class TestConfigProfile:
    """Tests para ConfigProfile"""
    
    def test_profile_creation_valid(self):
        """Verifica creación de perfil válido"""
        config = {
            "region": "sfo3",
            "bucket": "test-bucket",
            "dest": "/backup",
            "workers": 16
        }
        profile = ConfigProfile("test", config)
        
        assert profile.name == "test"
        assert profile.get("region") == "sfo3"
        assert profile.get("bucket") == "test-bucket"
        assert profile.get("workers") == 16
    
    def test_profile_creation_missing_required(self):
        """Verifica que falte campo requerido"""
        config = {
            "region": "sfo3",
            # falta bucket y dest
        }
        
        with pytest.raises(ConfigError):
            ConfigProfile("test", config)
    
    def test_profile_get_default(self):
        """Verifica get con valores por defecto"""
        config = {
            "region": "sfo3",
            "bucket": "test-bucket",
            "dest": "/backup"
        }
        profile = ConfigProfile("test", config)
        
        assert profile.get("workers") is None
        assert profile.get("workers", 16) == 16
    
    def test_profile_to_dict(self):
        """Verifica conversión a diccionario"""
        config = {
            "region": "sfo3",
            "bucket": "test-bucket",
            "dest": "/backup"
        }
        profile = ConfigProfile("test", config)
        result = profile.to_dict()
        
        assert result["region"] == "sfo3"
        assert result["bucket"] == "test-bucket"
        assert result["dest"] == "/backup"
    
    def test_profile_to_cli_args(self):
        """Verifica conversión a argumentos CLI"""
        config = {
            "region": "sfo3",
            "bucket": "test-bucket",
            "dest": "/backup",
            "workers": 24,
            "delete": True,
            "log_level": "DEBUG"
        }
        profile = ConfigProfile("test", config)
        args = profile.to_cli_args()
        
        assert "--region" in args
        assert "sfo3" in args
        assert "--workers" in args
        assert "24" in args
        assert "--delete" in args
        assert "--log-level" in args
        assert "DEBUG" in args


class TestConfigManager:
    """Tests para ConfigManager"""
    
    def test_load_config_from_file(self):
        """Verifica carga de archivo YAML"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            yaml.dump({
                "profile1": {
                    "region": "sfo3",
                    "bucket": "bucket1",
                    "dest": "/backup1"
                },
                "profile2": {
                    "region": "nyc3",
                    "bucket": "bucket2",
                    "dest": "/backup2"
                }
            }, f)
            temp_file = f.name
        
        try:
            manager = ConfigManager()
            manager.load_config(temp_file)
            
            assert len(manager.profiles) == 2
            assert manager.has_profile("profile1")
            assert manager.has_profile("profile2")
        finally:
            Path(temp_file).unlink()
    
    def test_load_config_invalid_file(self):
        """Verifica error si archivo no existe"""
        manager = ConfigManager()
        
        with pytest.raises(ConfigError):
            manager.load_config("/nonexistent/config.yml")
    
    def test_load_config_invalid_yaml(self):
        """Verifica error si YAML es inválido"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("[ broken yaml: {invalid:")
            temp_file = f.name
        
        try:
            manager = ConfigManager()
            with pytest.raises(ConfigError):
                manager.load_config(temp_file)
        finally:
            Path(temp_file).unlink()
    
    def test_get_profile(self):
        """Verifica obtención de perfil"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            yaml.dump({
                "test": {
                    "region": "sfo3",
                    "bucket": "bucket",
                    "dest": "/backup"
                }
            }, f)
            temp_file = f.name
        
        try:
            manager = ConfigManager()
            manager.load_config(temp_file)
            
            profile = manager.get_profile("test")
            assert profile is not None
            assert profile.get("region") == "sfo3"
            assert manager.get_profile("nonexistent") is None
        finally:
            Path(temp_file).unlink()
    
    def test_list_profiles(self):
        """Verifica listado de perfiles"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            yaml.dump({
                "alpha": {"region": "sfo3", "bucket": "b1", "dest": "/d1"},
                "beta": {"region": "nyc3", "bucket": "b2", "dest": "/d2"},
                "gamma": {"region": "ams3", "bucket": "b3", "dest": "/d3"}
            }, f)
            temp_file = f.name
        
        try:
            manager = ConfigManager()
            manager.load_config(temp_file)
            
            profiles = manager.list_profiles()
            assert len(profiles) == 3
            assert profiles == ["alpha", "beta", "gamma"]  # sorted
        finally:
            Path(temp_file).unlink()
    
    def test_load_config_with_optional_fields(self):
        """Verifica carga de perfiles con campos opcionales"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            yaml.dump({
                "full": {
                    "region": "sfo3",
                    "bucket": "bucket",
                    "dest": "/backup",
                    "prefix": "data/2026",
                    "workers": 32,
                    "delete": True,
                    "dry_run": False,
                    "exclude": ["*.tmp", "*.log"],
                    "show_progress": True,
                    "log_level": "DEBUG",
                    "output_json": "report.json",
                    "detailed_report": True,
                    "description": "Full profile test"
                }
            }, f)
            temp_file = f.name
        
        try:
            manager = ConfigManager()
            manager.load_config(temp_file)
            
            profile = manager.get_profile("full")
            assert profile.get("prefix") == "data/2026"
            assert profile.get("workers") == 32
            assert profile.get("delete") is True
            assert profile.get("exclude") == ["*.tmp", "*.log"]
            assert profile.get("description") == "Full profile test"
        finally:
            Path(temp_file).unlink()
    
    def test_load_config_empty_file(self):
        """Verifica carga de archivo vacío"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("")
            temp_file = f.name
        
        try:
            manager = ConfigManager()
            result = manager.load_config(temp_file)
            
            assert result is False
            assert len(manager.profiles) == 0
        finally:
            Path(temp_file).unlink()


class TestConfigIntegration:
    """Tests de integración"""
    
    def test_end_to_end_profile_workflow(self):
        """Verifica flujo completo de perfil"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            yaml.dump({
                "production": {
                    "region": "sfo3",
                    "bucket": "prod-backup",
                    "dest": "/mnt/backups/prod",
                    "workers": 24,
                    "exclude": ["*.tmp", "*/cache/*"],
                    "log_level": "INFO"
                }
            }, f)
            temp_file = f.name
        
        try:
            manager = ConfigManager()
            manager.load_config(temp_file)
            
            profile = manager.get_profile("production")
            assert profile is not None
            
            # Convertir a CLI args
            cli_args = profile.to_cli_args()
            assert "--region" in cli_args
            assert "sfo3" in cli_args
            assert "--workers" in cli_args
            assert "24" in cli_args
            
            # Verificar que CLI args pueden reconstruir configuración
            config_dict = profile.to_dict()
            assert config_dict["region"] == "sfo3"
            assert config_dict["bucket"] == "prod-backup"
        finally:
            Path(temp_file).unlink()
