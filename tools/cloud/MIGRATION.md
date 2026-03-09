# Migration Guide: DigitalOcean Spaces to Multi-Provider

This guide helps you migrate from the legacy DigitalOcean-only implementation to the new multi-provider cloud storage system.

## What Changed?

### v2.6.0 - Multi-Provider Support

- Added support for AWS S3, Google Cloud Storage, and Azure Blob Storage
- Introduced CloudProviderFactory for unified provider management
- Maintained backward compatibility with DigitalOcean Spaces

### v2.7.0 - Advanced Features

- **Local Cache System**: Skip already-synced files automatically
- **Sync Direction Control**: Choose orphan deletion behavior
- **Credential Management**: Securely store and manage cloud credentials
- **Management Commands**: list, delete, info, copy operations
- **Performance**: Improved caching and parallel operations

## Migration Path

### Option 1: Keep Using DigitalOcean Spaces (No Changes Needed)

Your existing commands continue to work:

```bash
# Old command (still works)
tools cloud sync --region sfo3 --bucket my-space --dest ./backup

# Upload (still works)
tools cloud upload ./data --region sfo3 --bucket my-space --dest backups/
```

**Backward Compatibility Guarantee:** All DigitalOcean Spaces commands from previous versions continue to work without modification.

### Option 2: Update to Explicit Provider Syntax (Recommended)

Explicitly specify the provider for clarity and future-proofing:

```bash
# New recommended syntax
tools cloud sync --provider digitalocean --region sfo3 \
  --bucket my-space --dest ./backup

# or use short alias
tools cloud sync --provider do --region sfo3 \
  --bucket my-space --dest ./backup
```

**Benefits:**

- Clearer intent
- Easier to switch providers later
- Consistent with AWS/GCS/Azure syntax

### Option 3: Use Configuration Profiles (Best Practice)

Create a YAML configuration file for reusable settings:

**~/.cloud-tools/config.yaml:**

```yaml
profiles:
  digitalocean-backup:
    provider: digitalocean
    region: sfo3
    bucket: my-spaces-bucket
    dest: ./local-backup
    prefix: backups/
    delete: false
    workers: 16
    exclude:
      - "*.tmp"
      - "*.log"
```

**Usage:**

```bash
tools cloud sync --profile digitalocean-backup
tools cloud upload ./data --profile digitalocean-backup
```

**Benefits:**

- Store credentials securely
- Reuse configurations
- Version control friendly (without secrets)
- Easy to maintain multiple environments

## Step-by-Step Migration Examples

### Example 1: Simple Download Sync

**Before (v2.5.0):**

```bash
tools cloud sync \
  --region sfo3 \
  --bucket my-backup \
  --dest /local/backup \
  --access-key DO000001 \
  --secret-key abc123...
```

**After (v2.7.0) - Option 1: Direct Migration**

```bash
# Enable cache and set sync direction
tools cloud sync \
  --provider digitalocean \
  --region sfo3 \
  --bucket my-backup \
  --dest /local/backup \
  --access-key DO000001 \
  --secret-key abc123... \
  --use-cache \
  --sync-direction download
```

**After (v2.7.0) - Option 2: Use Credentials**

```bash
# Store credentials once
tools cloud credentials set my-do \
  --provider digitalocean \
  --region sfo3 \
  --access-key DO000001 \
  --secret-key abc123... \
  --description "DigitalOcean production"

# Create profile
cat > ~/.cloud-tools/config.yaml << EOF
profiles:
  do-backup:
    provider: digitalocean
    bucket: my-backup
    dest: /local/backup
    credential: my-do
EOF

# Use profile
tools cloud sync --profile do-backup
```

### Example 2: Upload with Mirror Mode

**Before (v2.5.0):**

```bash
tools cloud upload ./data \
  --region sfo3 \
  --bucket my-backup \
  --dest uploads/ \
  --access-key DO000001 \
  --secret-key abc123...
```

**After (v2.7.0):**

```bash
# Upload with orphan deletion on remote side
tools cloud upload ./data \
  --provider digitalocean \
  --region sfo3 \
  --bucket my-backup \
  --dest uploads/ \
  --delete \
  --sync-direction upload \
  --use-cache \
  --access-key DO000001 \
  --secret-key abc123...
```

### Example 3: Scheduled Backups

**Before (v2.5.0) - Cron job:**

```cron
0 2 * * * /usr/bin/tools cloud sync --region sfo3 --bucket backups --dest /srv/backup
```

**After (v2.7.0) - Cron job with profiles:**

```cron
# Setup once
0 2 * * * /usr/bin/tools cloud sync --profile nightly-backup --delete --sync-direction download
```

**Config ~/.cloud-tools/config.yaml:**

```yaml
profiles:
  nightly-backup:
    provider: digitalocean
    region: sfo3
    bucket: backups
    dest: /srv/backup
    use_cache: true
    delete: true
    sync_direction: download
    workers: 32
    exclude:
      - "*.tmp"
```

## Migrating to Different Providers

### From DigitalOcean to AWS S3

**DigitalOcean:**

```yaml
profiles:
  old-do:
    provider: digitalocean
    region: sfo3
    bucket: my-space
    dest: ./backup
```

**AWS S3:**

```yaml
profiles:
  new-aws:
    provider: aws
    region: us-east-1
    bucket: my-s3-bucket
    dest: ./backup
```

**Copy data between providers:**

```bash
# Copy all files from DO to AWS
tools cloud list --profile old-do --format simple | while read key; do
  tools cloud copy "$key" "$key" \
    --source-profile old-do \
    --dest-profile new-aws
done
```

### From DigitalOcean to Google Cloud Storage

**Google Cloud Storage:**

```yaml
profiles:
  gcs-backup:
    provider: gcs
    bucket: my-gcs-bucket
    dest: ./backup
    project_id: my-gcp-project
    credentials_path: /path/to/service-account.json
```

## New Features to Adopt

### 1. Local Cache (Recommended)

**Benefits:**

- Skip files that haven't changed
- Faster syncs (no redundant downloads)
- Bandwidth savings

**Enable by default:**

```bash
tools cloud sync --profile prod --use-cache  # DEFAULT in v2.7.0
```

**When to disable:**

```bash
# Force re-check all files (useful after remote changes)
tools cloud sync --profile prod --no-cache
```

### 2. Sync Direction (Important for --delete)

**Before v2.7.0:**

```bash
# --delete always deleted LOCAL orphans
tools cloud sync --profile prod --delete
```

**After v2.7.0:**

```bash
# Delete LOCAL orphans (same as before, now explicit)
tools cloud sync --profile prod --delete --sync-direction download

# Delete REMOTE orphans
tools cloud upload ./data --profile prod --delete --sync-direction upload

# Delete orphans on BOTH sides (use with caution!)
tools cloud sync --profile prod --delete --sync-direction bidirectional
```

**⚠️ Important:** Review `--sync-direction` when using `--delete` to avoid accidental data loss!

### 3. Credential Management

**Instead of repeating credentials:**

```bash
# Store once
tools cloud credentials set prod-do \
  --provider digitalocean \
  --region sfo3 \
  --access-key DO000001 \
  --secret-key abc123...

# Use in profile
cat > ~/.cloud-tools/config.yaml << EOF
profiles:
  production:
    provider: digitalocean
    bucket: prod-backups
    dest: /srv/backup
    credential: prod-do
EOF

# Use
tools cloud sync --profile production
```

**Benefits:**

- Secrets encrypted with system keyring or AES-256
- No credentials in command history
- Easy rotation (update once, works everywhere)

### 4. Management Commands

**New commands not requiring full sync:**

```bash
# List files quickly
tools cloud list --profile prod --prefix backups/2024/

# Get bucket info
tools cloud info --profile prod

# Delete specific files
tools cloud delete old-file.zip --profile prod

# Copy between buckets
tools cloud copy file.txt backup/file.txt --profile prod
```

## Breaking Changes (None!)

**There are NO breaking changes.** All v2.5.0 commands continue to work in v2.7.0.

However, we **recommend** adopting:

1. Explicit `--provider` flag for clarity
2. Configuration profiles for reusability
3. Credential management for security
4. Cache system for performance
5. Sync direction for safety

## Testing Your Migration

### 1. Test with Dry Run

```bash
# Test sync
tools cloud sync --profile prod --dry-run

# Test upload
tools cloud upload ./data --profile prod --dry-run
```

### 2. Test Credentials

```bash
tools cloud credentials set test-creds \
  --provider digitalocean \
  --region sfo3 \
  --access-key YOUR_KEY \
  --secret-key YOUR_SECRET

tools cloud credentials test test-creds
```

### 3. Small Scale Test

```bash
# Sync a small prefix first
tools cloud sync --profile prod --prefix test/ --use-cache
```

### 4. Verify Cache

```bash
# Check cache stats
tools cloud cache-stats

# List cached files
tools cloud cache-list --provider digitalocean --bucket your-bucket
```

## Rollback Plan

If you encounter issues:

### 1. Disable New Features

```bash
# Disable cache
tools cloud sync --profile prod --no-cache

# Use download-only sync direction (v2.5.0 behavior)
tools cloud sync --profile prod --delete --sync-direction download
```

### 2. Clear Cache

```bash
tools cloud cache-clear --all
```

### 3. Use Legacy Syntax

```bash
# v2.5.0 syntax still works
tools cloud sync --region sfo3 --bucket my-bucket --dest ./backup
```

## Getting Help

### Check Installation

```bash
# Verify providers are available
tools cloud providers

# Check credentials
tools cloud credentials list
```

### View Cache Status

```bash
tools cloud cache-stats
tools cloud cache-list --provider digitalocean --bucket your-bucket
```

### Enable Debug Logging

```bash
tools cloud sync --profile prod --log-level DEBUG
```

### Documentation

- README.md - Full feature documentation
- MIGRATION.md (this file) - Migration guide
- Examples in ~/.cloud-tools/config.yaml

## Summary

**Recommended Migration Steps:**

1. ✅ **Continue using existing commands** (no immediate action needed)
2. ✅ **Add `--provider digitalocean`** to commands for clarity
3. ✅ **Create configuration profiles** for frequently used operations
4. ✅ **Store credentials securely** using `tools cloud credentials set`
5. ✅ **Enable cache** with `--use-cache` (default in v2.7.0)
6. ✅ **Review `--sync-direction`** when using `--delete`
7. ✅ **Test with `--dry-run`** before running destructive operations

**Timeline:**

- **Immediate:** No changes required, everything works
- **Week 1:** Test new features with `--dry-run`
- **Week 2:** Adopt configuration profiles
- **Week 3:** Migrate credentials to secure storage
- **Week 4:** Enable cache and optimize sync direction

**Questions?**

- Check `tools cloud --help`
- Check `tools cloud COMMAND --help` for specific commands
- Review logs with `--log-level DEBUG`
