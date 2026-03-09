"""Tests for cloud provider implementations."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

from tools.cloud.providers import CloudProvider, CloudObject
from tools.cloud.factory import CloudProviderFactory
from tools.cloud.aws_s3 import S3Provider
from tools.cloud.google_cloud import GCSProvider
from tools.cloud.azure_blob import AzureBlobProvider


class TestCloudObject:
    """Tests for CloudObject dataclass."""
    
    def test_cloud_object_creation(self):
        obj = CloudObject(
            key="path/to/file.txt",
            size_bytes=1024,
            modified="2026-03-07T12:00:00Z",
            etag="abc123",
            storage_class="STANDARD"
        )
        
        assert obj.key == "path/to/file.txt"
        assert obj.size_bytes == 1024
        assert obj.modified == "2026-03-07T12:00:00Z"
        assert obj.etag == "abc123"
        assert obj.storage_class == "STANDARD"
    
    def test_cloud_object_minimal(self):
        obj = CloudObject(key="file.txt", size_bytes=512)
        
        assert obj.key == "file.txt"
        assert obj.size_bytes == 512
        assert obj.modified is None
        assert obj.etag is None
        assert obj.storage_class is None


class TestCloudProviderFactory:
    """Tests for CloudProviderFactory."""
    
    def test_supported_providers(self):
        """Verify supported provider aliases."""
        providers = CloudProviderFactory._load_providers()
        assert "aws" in providers
        assert "s3" in providers
        assert "google" in providers
        assert "gcs" in providers
        assert "azure" in providers
        assert "azure-blob" in providers
    
    def test_create_aws_provider(self):
        """Test creating AWS S3 provider."""
        config = {
            "bucket": "test-bucket",
            "dest": "/tmp/test",
            "region": "us-east-1",
            "access_key": "test-key",
            "secret_key": "test-secret",
        }
        
        with patch("tools.cloud.aws_s3.boto3.Session"):
            provider = CloudProviderFactory.create("aws", config)
            assert isinstance(provider, S3Provider)
            assert provider.bucket == "test-bucket"
            assert provider.region == "us-east-1"
    
    @pytest.mark.skipif(GCSProvider is None, reason="google-cloud-storage not installed")
    def test_create_gcs_provider(self):
        """Test creating Google Cloud Storage provider."""
        config = {
            "bucket": "test-bucket",
            "dest": "/tmp/test",
            "project_id": "test-project",
        }
        
        # Check if GCS is actually available in the factory
        providers = CloudProviderFactory._load_providers()
        if providers.get("gcs") is None:
            pytest.skip("GCS provider dependencies not available")
        
        # Mock at the google.cloud.storage level
        try:
            import google.cloud.storage as gcs_storage_module
            with patch.object(gcs_storage_module, "Client"):
                provider = CloudProviderFactory.create("gcs", config)
                assert isinstance(provider, GCSProvider)
                assert provider.bucket == "test-bucket"
                assert provider.project_id == "test-project"
        except ImportError:
            pytest.skip("google-cloud-storage not available")
    
    @pytest.mark.skipif(AzureBlobProvider is None, reason="azure-storage-blob not installed")
    def test_create_azure_provider(self):
        """Test creating Azure Blob Storage provider."""
        config = {
            "container": "test-container",
            "dest": "/tmp/test",
            "account_name": "testaccount",
            "account_key": "test-key",
        }
        
        # Check if Azure is actually available in the factory
        providers = CloudProviderFactory._load_providers()
        if providers.get("azure") is None:
            pytest.skip("Azure provider dependencies not available")
        
        # Mock at the azure.storage.blob level
        try:
            import azure.storage.blob as azure_blob_module
            with patch.object(azure_blob_module, "BlobServiceClient"):
                provider = CloudProviderFactory.create("azure", config)
                assert isinstance(provider, AzureBlobProvider)
                assert provider.container == "test-container"
                assert provider.account_name == "testaccount"
        except ImportError:
            pytest.skip("azure-storage-blob not available")
    
    def test_create_unknown_provider(self):
        """Test error when creating unknown provider."""
        config = {"bucket": "test", "dest": "/tmp"}
        
        with pytest.raises(ValueError, match="Unknown provider"):
            CloudProviderFactory.create("unknown", config)
    
    def test_detect_provider_from_explicit_config(self):
        """Test detecting provider from explicit 'provider' field."""
        config = {"provider": "aws", "bucket": "test", "dest": "/tmp"}
        
        provider_type = CloudProviderFactory.detect_provider_from_config(config)
        assert provider_type == "aws"
    
    def test_detect_provider_from_digitalocean_endpoint(self):
        """Test auto-detecting DigitalOcean from endpoint."""
        config = {
            "endpoint_url": "https://sfo3.digitaloceanspaces.com",
            "bucket": "test",
            "dest": "/tmp"
        }
        
        provider_type = CloudProviderFactory.detect_provider_from_config(config)
        assert provider_type == "digitalocean"
    
    def test_detect_provider_from_aws_endpoint(self):
        """Test auto-detecting AWS from endpoint."""
        config = {
            "endpoint_url": "https://s3.amazonaws.com",
            "bucket": "test",
            "dest": "/tmp"
        }
        
        provider_type = CloudProviderFactory.detect_provider_from_config(config)
        assert provider_type == "aws"
    
    def test_detect_provider_from_gcs_config(self):
        """Test auto-detecting Google Cloud Storage."""
        config = {
            "project_id": "my-project",
            "bucket": "test",
            "dest": "/tmp"
        }
        
        provider_type = CloudProviderFactory.detect_provider_from_config(config)
        assert provider_type == "gcs"
    
    def test_detect_provider_from_azure_config(self):
        """Test auto-detecting Azure."""
        config = {
            "account_name": "myaccount",
            "container": "test",
            "dest": "/tmp"
        }
        
        provider_type = CloudProviderFactory.detect_provider_from_config(config)
        assert provider_type == "azure"
    
    def test_detect_provider_missing_fields(self):
        """Test error when provider cannot be detected."""
        config = {"bucket": "test", "dest": "/tmp"}
        
        with pytest.raises(ValueError, match="Cannot auto-detect provider"):
            CloudProviderFactory.detect_provider_from_config(config)


class TestS3Provider:
    """Tests for AWS S3 provider."""
    
    @pytest.fixture
    def s3_provider(self, tmp_path):
        """Create S3 provider instance."""
        with patch("tools.cloud.aws_s3.boto3.Session"):
            provider = S3Provider(
                bucket="test-bucket",
                dest=str(tmp_path),
                region="us-east-1",
                access_key="test-key",
                secret_key="test-secret",
            )
            provider.client = MagicMock()
            return provider
    
    def test_provider_name(self, s3_provider):
        """Test provider name."""
        assert "AWS S3" in s3_provider.provider_name
        assert "us-east-1" in s3_provider.provider_name
    
    def test_should_exclude(self, s3_provider):
        """Test pattern exclusion."""
        s3_provider.exclude = ["*.tmp", "logs/*"]
        
        assert s3_provider._should_exclude("file.tmp")
        assert s3_provider._should_exclude("logs/file.txt")
        assert not s3_provider._should_exclude("data/file.txt")
    
    def test_get_local_path(self, s3_provider, tmp_path):
        """Test local path conversion."""
        local_path = s3_provider._get_local_path("folder/file.txt")
        
        # Normalize path for cross-platform compatibility
        local_path_normalized = str(local_path).replace("\\", "/")
        assert local_path_normalized.endswith("folder/file.txt")
        assert local_path.parent.parent == tmp_path


@pytest.mark.skipif(GCSProvider is None, reason="google-cloud-storage not installed")
class TestGCSProvider:
    """Tests for Google Cloud Storage provider."""
    
    @pytest.fixture
    def gcs_provider(self, tmp_path):
        """Create GCS provider instance."""
        try:
            import google.cloud.storage as gcs_storage_module
            with patch.object(gcs_storage_module, "Client"):
                provider = GCSProvider(
                    bucket="test-bucket",
                    dest=str(tmp_path),
                    project_id="test-project",
                )
                provider.client = MagicMock()
                return provider
        except ImportError:
            pytest.skip("google-cloud-storage not available")
    
    def test_provider_name(self, gcs_provider):
        """Test provider name."""
        assert "Google Cloud Storage" in gcs_provider.provider_name
        assert "test-project" in gcs_provider.provider_name
    
    def test_get_credential_variables(self, gcs_provider):
        """Test credential variable requirements."""
        vars = gcs_provider.get_credential_variables()
        
        assert "GOOGLE_CLOUD_PROJECT" in vars
        assert "GOOGLE_APPLICATION_CREDENTIALS" in vars


@pytest.mark.skipif(AzureBlobProvider is None, reason="azure-storage-blob not installed")
@pytest.mark.skipif(AzureBlobProvider is None, reason="azure-storage-blob not installed")
class TestAzureBlobProvider:
    """Tests for Azure Blob Storage provider."""
    
    @pytest.fixture
    def azure_provider(self, tmp_path):
        """Create Azure provider instance."""
        try:
            import azure.storage.blob as azure_blob_module
            with patch.object(azure_blob_module, "BlobServiceClient"):
                provider = AzureBlobProvider(
                    container="test-container",
                    dest=str(tmp_path),
                    account_name="testaccount",
                    account_key="test-key",
                )
                provider.client = MagicMock()
                return provider
        except ImportError:
            pytest.skip("azure-storage-blob not available")
    
    def test_provider_name(self, azure_provider):
        """Test provider name."""
        assert "Azure Blob Storage" in azure_provider.provider_name
        assert "testaccount" in azure_provider.provider_name
    
    def test_get_credential_variables(self, azure_provider):
        """Test credential variable requirements."""
        vars = azure_provider.get_credential_variables()
        
        assert "AZURE_STORAGE_CONNECTION_STRING" in vars
        assert "AZURE_STORAGE_ACCOUNT_NAME" in vars
        assert "AZURE_STORAGE_ACCOUNT_KEY" in vars
