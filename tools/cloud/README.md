# Cloud Storage Module

Multi-cloud storage synchronization and management for AWS S3, Google Cloud Storage, Azure Blob Storage, and DigitalOcean Spaces.

## Features

### Core Functionality

- **Multi-cloud support**: AWS S3, Google Cloud Storage, Azure Blob Storage, DigitalOcean Spaces
- **Unified API**: Single interface for all cloud providers
- **Optional dependencies**: Install only the SDKs you need
- **Auto-detection**: Automatically detect provider from configuration
- **Synchronization**: Bidirectional sync between cloud and local filesystem
- **Upload/Download**: Transfer files and directories with parallel workers

### Advanced Features (v2.7.0)

- **Local Cache System**: SQLite-based cache to skip already-synced files
- **Sync Direction Control**: Choose orphan deletion behavior (download/upload/bidirectional)
- **Secure Credential Storage**: Encrypted credential management with system keyring
- **Cloud Management Commands**: list, delete, info, copy operations
- **Progress Tracking**: Real-time progress bars and detailed statistics
- **Profile Management**: YAML-based configuration profiles

### Performance Optimizations (v2.7.0)

- **Compression**: Transparent gzip/lz4 compression before upload to reduce bandwidth
- **Client-Side Encryption**: AES-256-GCM encryption for data at rest security
- **Bandwidth Limiting**: Control upload/download speeds to prevent network saturation
- **Multipart Uploads**: Resumable transfers for large files with parallel chunks
- **Smart Compression Detection**: Skip already-compressed files automatically
- **Authenticated Encryption**: HMAC tags prevent data tampering

## Installation

### Basic Installation

```bash
pip install -r requirements.txt
```

### With Cloud Provider Support

**AWS S3:**

```bash
pip install boto3>=1.26.0
```

**Google Cloud Storage:**

```bash
pip install google-cloud-storage>=2.10.0
```

**Azure Blob Storage:**

```bash
pip install azure-storage-blob>=12.14.0
```

**DigitalOcean Spaces (S3-compatible):**
No additional packages needed (uses boto3)

## Usage

### CLI Commands

#### List Available Providers

```bash
# Show all available providers and installation status
tools cloud providers

# Output as JSON
tools cloud providers --json
```

Output example:

```
☁️  Available Cloud Providers

  • AWS S3                         [aws, s3, aws-s3     ] ✓ installed
  • Google Cloud Storage           [google, gcs, google-cloud ...] ✓ installed
  • Azure Blob Storage             [azure, azure-blob   ] ✓ installed
  • DigitalOcean Spaces            [digitalocean, do    ] ✓ installed
```

#### Show Credential Requirements

```bash
# Show what credentials are needed for a provider
tools cloud credentials aws

# Show GCS credentials
tools cloud credentials gcs

# Output as JSON
tools cloud credentials azure --json
```

#### Synchronize from Cloud Storage

Using profiles (YAML configuration):

```bash
tools cloud sync --profile production_backup
```

Direct CLI arguments:

```bash
# AWS S3
tools cloud sync --provider aws \
  --bucket my-bucket \
  --dest ./backup \
  --region us-east-1 \
  --access-key YOUR_KEY \
  --secret-key YOUR_SECRET

# Google Cloud Storage
tools cloud sync --provider gcs \
  --bucket my-bucket \
  --dest ./backup \
  --project-id my-project

# Azure Blob Storage
tools cloud sync --provider azure \
  --container my-container \
  --dest ./backup \
  --account-name myaccount \
  --account-key ACCOUNT_KEY

# DigitalOcean Spaces
tools cloud sync --provider digitalocean \
  --bucket my-space \
  --dest ./backup \
  --region sfo3
```

#### Upload Files to Cloud

```bash
# Using a profile
tools cloud upload ./data --profile production_uploads

# Direct arguments (AWS S3)
tools cloud upload ./backups \
  --region us-east-1 \
  --bucket my-bucket \
  --dest backups/
```

### Python API

#### List Available Providers

```python
from tools.cloud.factory import CloudProviderFactory

# Get available providers
providers = CloudProviderFactory._load_providers()
for name, provider_class in providers.items():
    if provider_class:
        print(f"✓ {name}: available")
    else:
        print(f"✗ {name}: not installed")
```

#### Create Provider Instance

```python
from tools.cloud.factory import CloudProviderFactory

# Create provider from configuration
config = {
    "bucket": "my-bucket",
    "dest": "/local/path",
    "region": "us-east-1",
    "access_key": "YOUR_ACCESS_KEY",
    "secret_key": "YOUR_SECRET_ACCESS_KEY",
}

provider = CloudProviderFactory.create("aws", config)
```

#### Auto-detect Provider

```python
from tools.cloud.factory import CloudProviderFactory

config = {
    "bucket": "my-bucket",
    "dest": "/local/path",
    "project_id": "my-gcp-project",  # GCS uses project_id
}

# Automatically detect provider
provider_type = CloudProviderFactory.detect_provider_from_config(config)
provider = CloudProviderFactory.create(provider_type, config)
```

#### Synchronize Files

```python
from tools.cloud.factory import CloudProviderFactory

config = {
    "bucket": "my-bucket",
    "dest": "/local/path",
    "region": "us-east-1",
}

provider = CloudProviderFactory.create("aws", config)

# Download files
sync_result = provider.sync(
    exclude=["*.tmp", "logs/*"],
    dry_run=False,
    workers=16
)

print(f"Downloaded: {len(sync_result.downloaded)} files")
print(f"Skipped: {len(sync_result.skipped)} files")
print(f"Errors: {len(sync_result.errors)} files")
```

## New Features in v2.7.0

### Local Cache System

The cache system tracks synced files to avoid re-downloading/uploading unchanged files.

**CLI Usage:**

```bash
# Sync with cache enabled (default)
tools cloud sync --profile production

# Disable cache for a single sync
tools cloud sync --profile production --no-cache

# View cache statistics
tools cloud cache-stats

# List cached files
tools cloud cache-list --provider aws --bucket my-bucket

# Clear cache
tools cloud cache-clear --provider aws --bucket my-bucket
tools cloud cache-clear --all  # Clear entire cache
```

**Python API:**

```python
from tools.cloud.providers import SyncDirection

config = {
    "bucket": "my-bucket",
    "dest": "/local/path",
    "region": "us-east-1",
    "use_cache": True,  # Enable cache (default)
}

provider = CloudProviderFactory.create("aws", config)
stats = provider.sync()
```

### Sync Direction Control

Control orphan file deletion behavior during sync operations.

**Modes:**

- `download` (default): Delete local orphans not in remote
- `upload`: Delete remote orphans not in local
- `bidirectional`: Delete orphans on both sides

**CLI Usage:**

```bash
# Download mode: delete local orphans (DEFAULT)
tools cloud sync --profile prod --delete --sync-direction download

# Upload mode: delete remote orphans
tools cloud upload ./data --profile prod --delete --sync-direction upload

# Bidirectional: delete orphans on both sides
tools cloud sync --profile prod --delete --sync-direction bidirectional
```

**Python API:**

```python
from tools.cloud.providers import SyncDirection

config = {
    "bucket": "my-bucket",
    "dest": "/local/path",
    "delete": True,
    "sync_direction": SyncDirection.BIDIRECTIONAL,  # or DOWNLOAD, UPLOAD
}
```

### Secure Credential Management

Store cloud credentials securely using system keyring or encrypted file storage.

**Store Credentials:**

```bash
# AWS credentials
tools cloud credentials set my-aws \
  --provider aws \
  --region us-east-1 \
  --access-key AKIAIOSFODNN7EXAMPLE \
  --secret-key wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY \
  --description "Production AWS account"

# GCS credentials
tools cloud credentials set my-gcs \
  --provider gcs \
  --project-id my-project \
  --credentials-path /path/to/service-account.json

# Azure credentials
tools cloud credentials set my-azure \
  --provider azure \
  --account-name myaccount \
  --account-key base64-encoded-key
```

**List Credentials:**

```bash
tools cloud credentials list
tools cloud credentials list --format json
```

**Get Credential Details:**

```bash
tools cloud credentials get my-aws
tools cloud credentials get my-aws --show-secrets
```

**Delete Credentials:**

```bash
tools cloud credentials delete my-aws
tools cloud credentials delete my-aws -y  # Skip confirmation
```

**Test Credentials:**

```bash
tools cloud credentials test my-aws
```

### Cloud Management Commands

#### List Objects

```bash
# List all objects
tools cloud list --provider aws --bucket my-bucket --region us-east-1

# List with prefix filter
tools cloud list --profile prod --prefix backups/2024/

# List with pattern
tools cloud list --provider gcs --bucket my-bucket --pattern "*.jpg"

# Sort and limit
tools cloud list --profile prod --sort-by size --reverse --limit 100

# Different formats
tools cloud list --profile prod --format json
tools cloud list --profile prod --format csv
tools cloud list --profile prod --format simple  # Just filenames
```

#### Delete Objects

```bash
# Delete specific files
tools cloud delete file1.txt file2.txt --provider aws --bucket my-bucket

# Delete by prefix
tools cloud delete --prefix old-backups/ --provider aws --bucket my-bucket

# Delete by pattern
tools cloud delete --pattern "*.tmp" --provider gcs --bucket my-bucket

# Dry run
tools cloud delete --prefix temp/ --dry-run --profile prod

# Skip confirmation
tools cloud delete --prefix temp/ -y --profile prod
```

#### Get Object/Bucket Info

```bash
# Get bucket info
tools cloud info --provider aws --bucket my-bucket --region us-east-1

# Get object info
tools cloud info backups/data.zip --provider aws --bucket my-bucket

# JSON output
tools cloud info file.txt --profile prod --format json
```

#### Copy Objects

```bash
# Copy within same bucket
tools cloud copy file.txt backup/file.txt \
  --provider aws --bucket my-bucket

# Copy between buckets (same provider)
tools cloud copy data.zip data.zip \
  --source-bucket bucket1 --dest-bucket bucket2 \
  --provider aws --region us-east-1

# Copy between providers using profiles
tools cloud copy data.zip data.zip \
  --source-profile aws-prod --dest-profile gcs-backup

# Copy between providers (manual)
tools cloud copy file.txt file.txt \
  --source-provider aws --source-bucket s3-bucket \
  --dest-provider gcs --dest-bucket gcs-bucket \
  --source-region us-east-1 --dest-project-id my-project
```

#### Upload Files

```python
from tools.cloud.factory import CloudProviderFactory

config = {
    "bucket": "my-bucket",
    "dest": "/local/path",
    "region": "us-east-1",
}

provider = CloudProviderFactory.create("aws", config)

# Upload files
upload_result = provider.upload(
    source="/path/to/files",
    exclude=["*.tmp"],
    dry_run=False,
    workers=16
)
```

### Performance Optimizations

Advanced features to optimize transfers, reduce bandwidth, and enhance security.

#### Compression

Compress files before upload to reduce bandwidth usage and storage costs.

**CLI Usage:**

```bash
# Enable gzip compression (default)
tools cloud upload ./data --profile prod --compress

# Use lz4 compression (faster, lower ratio)
tools cloud upload ./data --profile prod --compress --compression-type lz4

# Compression with sync
tools cloud sync --profile prod --compress --compression-type gzip
```

**Python API:**

```python
from tools.cloud.factory import CloudProviderFactory

config = {
    "bucket": "my-bucket",
    "dest": "/local/path",
    "compress": True,
    "compression_type": "gzip",  # or "lz4"
}

provider = CloudProviderFactory.create("aws", config)
result = provider.upload("/path/to/files")
```

**Notes:**

- Automatically skips already-compressed formats (jpg, png, zip, gz, etc.)
- Tests compression on file samples to determine if beneficial
- Adds `.gz` or `.lz4` extension to compressed files
- Transparent decompression during download

#### Client-Side Encryption

Encrypt files before upload with AES-256-GCM for data-at-rest security.

**CLI Usage:**

```bash
# Enable encryption (auto-generates key)
tools cloud upload ./data --profile prod --encrypt

# Use specific encryption key
tools cloud upload ./data --profile prod --encrypt \
  --encryption-key a1b2c3d4e5f6...  # 64 hex characters

# Encrypted sync
tools cloud sync --profile prod --encrypt --encryption-key $MY_KEY
```

**Python API:**

```python
from tools.cloud.encryption import generate_key

# Generate key
key = generate_key()
print(f"Save this key securely: {key}")

config = {
    "bucket": "my-bucket",
    "dest": "/local/path",
    "encrypt": True,
    "encryption_key": key,
}

provider = CloudProviderFactory.create("aws", config)
result = provider.upload("/path/to/files")
```

**Key Management:**

```python
# Derive key from password
from tools.cloud.encryption import derive_key_from_password

key, salt = derive_key_from_password("my-secure-password")

# Store key in credential manager
tools cloud credentials set my-encrypted \
  --provider aws \
  --custom-field encryption_key=$key
```

**Security Features:**

- AES-256-GCM authenticated encryption
- Unique nonce per file prevents pattern analysis
- HMAC authentication tags prevent tampering
- PBKDF2 key derivation from passwords (100,000 iterations)

#### Bandwidth Limiting

Control upload/download speeds to prevent network saturation.

**CLI Usage:**

```bash
# Limit to 5000 KB/s (5 MB/s)
tools cloud upload ./data --profile prod --bandwidth-limit 5000

# Limit sync operations
tools cloud sync --profile prod --bandwidth-limit 2000  # 2 MB/s
```

**Python API:**

```python
config = {
    "bucket": "my-bucket",
    "dest": "/local/path",
    "bandwidth_limit": 5000,  # KB/s
}

provider = CloudProviderFactory.create("aws", config)
result = provider.upload("/path/to/files")
```

**Notes:**

- Uses token bucket algorithm for smooth rate limiting
- Thread-safe for parallel workers
- Real-time statistics and current rate reporting
- Affects both upload and download operations

#### Multipart Uploads

Enable resumable transfers for large files with parallel chunk uploads.

**CLI Usage:**

```bash
# Set threshold for multipart (default: 100MB)
tools cloud upload ./large-files --profile prod --multipart-threshold 50

# Combine with other optimizations
tools cloud upload ./data --profile prod \
  --compress \
  --bandwidth-limit 10000 \
  --multipart-threshold 200
```

**Python API:**

```python
config = {
    "bucket": "my-bucket",
    "dest": "/local/path",
    "multipart_threshold": 100,  # MB
}

provider = CloudProviderFactory.create("aws", config)
result = provider.upload("/path/to/large-files")
```

**Benefits:**

- Resume interrupted uploads without starting over
- Parallel chunk uploads for faster transfers
- Better handling of large files (>100MB)
- Automatic chunking and reassembly

#### Combined Optimizations

Use multiple optimizations together for maximum efficiency:

**CLI:**

```bash
tools cloud upload ./sensitive-data --profile prod \
  --compress --compression-type lz4 \
  --encrypt --encryption-key $ENCRYPTION_KEY \
  --bandwidth-limit 8000 \
  --multipart-threshold 100 \
  --workers 8
```

**Python:**

```python
from tools.cloud.factory import CloudProviderFactory
from tools.cloud.encryption import generate_key

config = {
    "bucket": "my-bucket",
    "dest": "/local/path",
    "compress": True,
    "compression_type": "lz4",
    "encrypt": True,
    "encryption_key": generate_key(),
    "bandwidth_limit": 8000,  # 8 MB/s
    "multipart_threshold": 100,  # 100 MB
    "workers": 8,
}

provider = CloudProviderFactory.create("aws", config)
result = provider.upload("/path/to/data")

print(f"Uploaded {result['uploaded']} files")
print(f"Bandwidth savings: {result['compression_ratio']}%")
```

## Provider Configuration

### AWS S3

**Environment Variables:**

```bash
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
export AWS_DEFAULT_REGION=us-east-1  # optional
```

**Configuration File (YAML):**

```yaml
profiles:
  my-backup:
    provider: aws
    bucket: my-bucket
    dest: ./backup
    region: us-east-1
    access_key: ${AWS_ACCESS_KEY_ID}
    secret_key: ${AWS_SECRET_ACCESS_KEY}
```

**Python API:**

```python
config = {
    "bucket": "my-bucket",
    "dest": "./backup",
    "region": "us-east-1",
    "access_key": "...",
    "secret_key": "...",
}
```

### Google Cloud Storage

**Environment Variables:**

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
export GOOGLE_CLOUD_PROJECT=my-project
```

**Configuration File (YAML):**

```yaml
profiles:
  gcs-backup:
    provider: gcs
    bucket: my-bucket
    dest: ./backup
    project_id: my-project
    credentials_path: /path/to/service-account.json
```

**Python API:**

```python
config = {
    "bucket": "my-bucket",
    "dest": "./backup",
    "project_id": "my-project",
}
# Uses GOOGLE_APPLICATION_CREDENTIALS by default
```

### Azure Blob Storage

**Environment Variables:**

```bash
# Option 1: Connection string
export AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;...

# Option 2: Account credentials
export AZURE_STORAGE_ACCOUNT_NAME=myaccount
export AZURE_STORAGE_ACCOUNT_KEY=mykey
```

**Configuration File (YAML):**

```yaml
profiles:
  azure-backup:
    provider: azure
    container: my-container
    dest: ./backup
    account_name: myaccount
    account_key: mykey
```

**Python API:**

```python
config = {
    "container": "my-container",
    "dest": "./backup",
    "account_name": "myaccount",
    "account_key": "mykey",
}
```

### DigitalOcean Spaces

**Environment Variables:**

```bash
export AWS_ACCESS_KEY_ID=your-spaces-key
export AWS_SECRET_ACCESS_KEY=your-spaces-secret
```

**Configuration File (YAML):**

```yaml
profiles:
  do-backup:
    provider: digitalocean
    bucket: my-space
    dest: ./backup
    region: sfo3
    endpoint_url: https://sfo3.digitaloceanspaces.com
    access_key: ${AWS_ACCESS_KEY_ID}
    secret_key: ${AWS_SECRET_ACCESS_KEY}
```

**Python API:**

```python
config = {
    "bucket": "my-space",
    "dest": "./backup",
    "region": "sfo3",
    "endpoint_url": "https://sfo3.digitaloceanspaces.com",
}
```

## Architecture

### Provider Classes

- **CloudProvider** (base class): Abstract interface for all cloud providers
- **S3Provider**: AWS S3 implementation
- **GCSProvider**: Google Cloud Storage implementation
- **AzureBlobProvider**: Azure Blob Storage implementation
- **CloudProviderFactory**: Factory for creating provider instances

### CloudObject Dataclass

Represents a cloud storage object:

```python
@dataclass
class CloudObject:
    key: str              # Object path/key
    size_bytes: int       # File size
    modified: str = None  # Last modified timestamp
    etag: str = None      # Entity tag (version/hash)
    storage_class: str = None  # Storage class (optional)
```

### SyncResult

Returned from sync operations:

```python
class SyncResult:
    downloaded: List[CloudObject]
    skipped: List[CloudObject]
    deleted: List[CloudObject]
    errors: Dict[str, str]
```

## Optional Dependencies

All cloud provider SDKs are optional. The module gracefully handles missing dependencies:

```python
try:
    from tools.cloud import S3Provider
    if S3Provider is None:
        print("AWS S3 support not available - install boto3")
except ImportError:
    print("AWS S3 support not available - install boto3")
```

## Error Handling

### Missing Dependencies

When a provider's dependencies are not installed:

```
tools cloud sync --provider gcs
Error: Provider 'gcs' dependencies not installed:
  No module named 'google.cloud.storage'

To install: pip install google-cloud-storage>=2.10.0
```

### Invalid Configuration

```python
from tools.cloud.factory import CloudProviderFactory

# Missing required fields
try:
    provider = CloudProviderFactory.create("aws", {"bucket": "test"})
except ValueError as e:
    print(f"Invalid configuration: {e}")
```

### Authentication Errors

Handled gracefully with clear error messages:

```
Error: Could not authenticate with AWS:
  InvalidClientTokenId

Check your AWS credentials are set correctly:
  export AWS_ACCESS_KEY_ID=...
  export AWS_SECRET_ACCESS_KEY=...
```

## Testing

Run the test suite:

```bash
pytest tests/cloud/ -v

# Run specific provider tests
pytest tests/cloud/test_cloud_providers.py::TestS3Provider -v

# Run with coverage
pytest tests/cloud/ --cov=tools.cloud --cov-report=html
```

## Performance Tips

1. **Parallel Workers**: Use `--workers` flag to control parallelism

   ```bash
   tools cloud sync -p myprofile --workers 32  # More parallelism
   ```

2. **Exclude Patterns**: Speed up sync by excluding unnecessary files

   ```bash
   tools cloud sync -p myprofile --exclude "*.tmp" --exclude "node_modules/*"
   ```

3. **Dry Run**: Test before actually syncing

   ```bash
   tools cloud sync -p myprofile --dry-run
   ```

4. **Limit to Prefix**: Only sync specific paths
   ```bash
   tools cloud sync -p myprofile --prefix "2024/"
   ```

## Troubleshooting

### "Provider X dependencies not installed"

Install the required package:

```bash
# AWS S3
pip install boto3

# Google Cloud Storage
pip install google-cloud-storage

# Azure Blob Storage
pip install azure-storage-blob
```

### "Authentication failed"

Check your credentials:

```bash
# Check environment variables are set
tools cloud credentials aws

# Test connection with dry-run
tools cloud sync -p myprofile --dry-run
```

### "Connection timeout"

- Check network connectivity
- Verify endpoint/region is correct
- Try with fewer workers: `--workers 4`

## See Also

- [tools system](../system/README.md) - System administration tools
- [tools remote](../remote/README.md) - Remote server management
- [Configuration Management](../core/config.py) - Config file format and profiles
