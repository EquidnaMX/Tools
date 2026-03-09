"""
Tests para la clase DigitalOceanSync
"""
import pytest
from unittest.mock import Mock, patch
import tempfile
import logging
from pathlib import Path
from datetime import datetime, timezone
from tools.cloud.sync import DigitalOceanSync, SyncStats


@pytest.fixture
def mock_logger():
    """Fixture que crea un logger mock"""
    return Mock(spec=logging.Logger)


@pytest.fixture
def temp_dest():
    """Fixture que crea un directorio temporal para tests"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def basic_syncer(mock_logger, temp_dest):
    """Fixture que crea un DigitalOceanSync básico"""
    return DigitalOceanSync(
        region="sfo3",
        bucket="test-bucket",
        dest=str(temp_dest),
        logger=mock_logger
    )


class TestDigitalOceanSyncInit:
    """Tests para inicialización de DigitalOceanSync"""
    
    def test_init_sets_basic_attributes(self, mock_logger, temp_dest):
        """Verifica que __init__ establece atributos básicos"""
        syncer = DigitalOceanSync(
            region="sfo3",
            bucket="my-bucket",
            dest=str(temp_dest),
            logger=mock_logger
        )
        
        assert syncer.region == "sfo3"
        assert syncer.bucket == "my-bucket"
        assert syncer.dest_root == temp_dest
        assert syncer.logger == mock_logger
        assert syncer.workers == 16  # default
        assert syncer.delete is False  # default
        assert syncer.dry_run is False  # default
        assert syncer.client is None  # no creado aún
    
    def test_init_with_custom_params(self, mock_logger, temp_dest):
        """Verifica inicialización con parámetros personalizados"""
        syncer = DigitalOceanSync(
            region="nyc3",
            bucket="custom-bucket",
            dest=str(temp_dest),
            prefix="backups/2026/",
            workers=32,
            delete=True,
            dry_run=True,
            exclude=["*.tmp", "*.log"],
            show_progress=False,
            logger=mock_logger
        )
        
        assert syncer.region == "nyc3"
        assert syncer.prefix == "backups/2026/"
        assert syncer.workers == 32
        assert syncer.delete is True
        assert syncer.dry_run is True
        assert syncer.exclude == ["*.tmp", "*.log"]
        assert syncer.show_progress is False
    
    def test_init_creates_stats(self, basic_syncer):
        """Verifica que __init__ crea objeto SyncStats"""
        assert isinstance(basic_syncer.stats, SyncStats)
    
    def test_init_creates_logger_if_none(self, temp_dest):
        """Verifica que crea logger por defecto si no se proporciona"""
        syncer = DigitalOceanSync(
            region="sfo3",
            bucket="test-bucket",
            dest=str(temp_dest)
        )
        
        assert syncer.logger is not None


class TestDigitalOceanSyncBuildClient:
    """Tests para método _build_client()"""
    
    @patch('tools.cloud.sync.boto3.Session')
    def test_build_client_creates_s3_client(self, mock_session, basic_syncer):
        """Verifica que _build_client() crea cliente S3"""
        mock_client = Mock()
        mock_session.return_value.client.return_value = mock_client
        
        client = basic_syncer._build_client()
        
        assert client == mock_client
        mock_session.return_value.client.assert_called_once()
    
    @patch('tools.cloud.sync.boto3.Session')
    def test_build_client_uses_profile(self, mock_session, mock_logger, temp_dest):
        """Verifica que usa perfil AWS si se proporciona"""
        syncer = DigitalOceanSync(
            region="sfo3",
            bucket="test-bucket",
            dest=str(temp_dest),
            profile="my-profile",
            logger=mock_logger
        )
        
        mock_client = Mock()
        mock_session.return_value.client.return_value = mock_client
        
        syncer._build_client()
        
        # Debe crear sesión con profile_name
        mock_session.assert_called_with(profile_name="my-profile")
    
    @patch('tools.cloud.sync.boto3.Session')
    def test_build_client_sets_endpoint(self, mock_session, basic_syncer):
        """Verifica que establece endpoint correcto"""
        mock_client = Mock()
        mock_session.return_value.client.return_value = mock_client
        
        basic_syncer._build_client()
        
        # Verificar que se llama con endpoint de DigitalOcean
        call_kwargs = mock_session.return_value.client.call_args[1]
        assert "endpoint_url" in call_kwargs
        assert "sfo3.digitaloceanspaces.com" in call_kwargs["endpoint_url"]


class TestDigitalOceanSyncValidateCredentials:
    """Tests para método _validate_credentials()"""
    
    def test_validate_credentials_success(self, basic_syncer):
        """Verifica validación exitosa de credenciales"""
        basic_syncer.client = Mock()
        basic_syncer.client.head_bucket.return_value = {}
        
        result = basic_syncer._validate_credentials()
        
        assert result is True
        basic_syncer.client.head_bucket.assert_called_once_with(Bucket="test-bucket")
    
    def test_validate_credentials_bucket_not_found(self, basic_syncer):
        """Verifica manejo de bucket no encontrado"""
        from botocore.exceptions import ClientError
        
        basic_syncer.client = Mock()
        error_response = {'Error': {'Code': '404'}}
        basic_syncer.client.head_bucket.side_effect = ClientError(error_response, 'head_bucket')
        
        result = basic_syncer._validate_credentials()
        
        assert result is False
    
    def test_validate_credentials_access_denied(self, basic_syncer):
        """Verifica manejo de acceso denegado"""
        from botocore.exceptions import ClientError
        
        basic_syncer.client = Mock()
        error_response = {'Error': {'Code': '403'}}
        basic_syncer.client.head_bucket.side_effect = ClientError(error_response, 'head_bucket')
        
        result = basic_syncer._validate_credentials()
        
        assert result is False


class TestDigitalOceanSyncListObjects:
    """Tests para método _list_objects()"""
    
    def test_list_objects_yields_objects(self, basic_syncer):
        """Verifica que _list_objects() devuelve objetos"""
        basic_syncer.client = Mock()
        
        # Simular respuesta paginada
        mock_paginator = Mock()
        basic_syncer.client.get_paginator.return_value = mock_paginator
        
        mock_pages = [
            {"Contents": [
                {"Key": "file1.txt", "Size": 100, "LastModified": datetime.now(timezone.utc)},
                {"Key": "file2.txt", "Size": 200, "LastModified": datetime.now(timezone.utc)}
            ]},
            {"Contents": [
                {"Key": "file3.txt", "Size": 300, "LastModified": datetime.now(timezone.utc)}
            ]}
        ]
        mock_paginator.paginate.return_value = iter(mock_pages)
        
        objects = list(basic_syncer._list_objects())
        
        assert len(objects) == 3
        assert objects[0]["Key"] == "file1.txt"
        assert objects[1]["Key"] == "file2.txt"
        assert objects[2]["Key"] == "file3.txt"
    
    def test_list_objects_handles_empty(self, basic_syncer):
        """Verifica manejo de bucket vacío"""
        basic_syncer.client = Mock()
        
        mock_paginator = Mock()
        basic_syncer.client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = iter([{}])  # Sin "Contents"
        
        objects = list(basic_syncer._list_objects())
        
        assert len(objects) == 0


class TestDigitalOceanSyncDownloadFile:
    """Tests para método _download_file()"""
    
    def test_download_file_success(self, basic_syncer, temp_dest):
        """Verifica descarga exitosa de archivo"""
        obj = {
            "Key": "test.txt",
            "Size": 100,
            "LastModified": datetime.now(timezone.utc)
        }
        
        basic_syncer.client = Mock()
        
        # Simular respuesta de get_object
        mock_response = {
            "Body": Mock(),
            "ContentLength": 100
        }
        mock_response["Body"].read = Mock(side_effect=[b"test content", b""])
        basic_syncer.client.get_object.return_value = mock_response
        
        key, success, error, duration = basic_syncer._download_file(obj)
        
        assert key == "test.txt"
        assert success is True
        assert error is None
        assert duration >= 0
    
    def test_download_file_dry_run(self, basic_syncer):
        """Verifica que dry_run no descarga"""
        basic_syncer.dry_run = True
        
        obj = {
            "Key": "test.txt",
            "Size": 100,
            "LastModified": datetime.now(timezone.utc)
        }
        
        key, success, error, duration = basic_syncer._download_file(obj)
        
        assert key == "test.txt"
        assert success is False
        assert error is None
        assert duration == 0.0
    
    def test_download_file_retries_on_error(self, basic_syncer, temp_dest):
        """Verifica que reintenta en caso de error"""
        from botocore.exceptions import ClientError
        
        obj = {
            "Key": "test.txt",
            "Size": 100,
            "LastModified": datetime.now(timezone.utc)
        }
        
        basic_syncer.client = Mock()
        error_response = {'Error': {'Code': '500'}}
        basic_syncer.client.get_object.side_effect = ClientError(error_response, 'get_object')
        
        key, success, error, duration = basic_syncer._download_file(obj)
        
        assert key == "test.txt"
        assert success is False
        assert error is not None
        # Debe haber intentado 5 veces
        assert basic_syncer.client.get_object.call_count == 5


class TestDigitalOceanSyncSyncMethod:
    """Tests para método sync() (integración)"""
    
    @patch.object(DigitalOceanSync, '_build_client')
    @patch.object(DigitalOceanSync, '_validate_credentials')
    @patch.object(DigitalOceanSync, '_list_objects')
    @patch.object(DigitalOceanSync, '_download_file')
    def test_sync_basic_flow(self, mock_download, mock_list, mock_validate, mock_build, basic_syncer):
        """Verifica flujo básico de sync()"""
        # Configurar mocks
        mock_build.return_value = Mock()
        mock_validate.return_value = True
        
        mock_objects = [
            {"Key": "file1.txt", "Size": 100, "LastModified": datetime.now(timezone.utc)},
            {"Key": "file2.txt", "Size": 200, "LastModified": datetime.now(timezone.utc)}
        ]
        mock_list.return_value = iter(mock_objects)
        
        mock_download.return_value = ("file1.txt", True, None, 0.5)
        
        stats = basic_syncer.sync()

        # Verificar que se llamaron los métodos
        mock_build.assert_called_once()
        mock_validate.assert_called_once()
        mock_list.assert_called_once()

        # Verificar que retorna SyncStats
        assert isinstance(stats, SyncStats)
    
    @patch.object(DigitalOceanSync, '_build_client')
    @patch.object(DigitalOceanSync, '_validate_credentials')
    def test_sync_fails_on_invalid_credentials(self, mock_validate, mock_build, basic_syncer):
        """Verifica que falla si las credenciales son inválidas"""
        mock_build.return_value = Mock()
        mock_validate.return_value = False
        
        with pytest.raises(RuntimeError):
            basic_syncer.sync()


class TestDigitalOceanSyncEdgeCases:
    """Tests de casos límite"""
    
    def test_handles_nested_paths(self, mock_logger, temp_dest):
        """Verifica manejo de paths anidados"""
        syncer = DigitalOceanSync(
            region="sfo3",
            bucket="test-bucket",
            dest=str(temp_dest),
            prefix="deep/nested/path/",
            logger=mock_logger
        )
        
        assert syncer.prefix == "deep/nested/path/"
    
    def test_handles_unicode_filenames(self, basic_syncer, temp_dest):
        """Verifica manejo de nombres con unicode"""
        obj = {
            "Key": "archivo_español_日本語.txt",
            "Size": 100,
            "LastModified": datetime.now(timezone.utc)
        }
        
        basic_syncer.dry_run = True
        key, success, error, duration = basic_syncer._download_file(obj)
        
        assert key == "archivo_español_日本語.txt"
