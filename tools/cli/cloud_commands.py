"""
Cloud storage CLI subcommands.
Provides: tools cloud sync, tools cloud profiles
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import click

from tools.core.logger import get_logger
from tools.cloud import DigitalOceanSync, ConfigManager, ConfigError, SyncStats
from tools.cloud.sync import save_json_report

logger = get_logger(__name__)


def setup_sync_logger(log_level: str = "INFO") -> logging.Logger:
    """Configure logger for sync operations."""
    import sys
    
    sync_logger = logging.getLogger("cloud.sync")
    sync_logger.setLevel(log_level)
    
    # Evitar duplicar handlers
    if sync_logger.handlers:
        return sync_logger
    
    # Formato con timestamp
    formatter = logging.Formatter(
        fmt='[%(asctime)s] [%(levelname)-8s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Handler para consola con encoding UTF-8 en Windows
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Fix encoding for Windows console
    if sys.platform == 'win32' and hasattr(console_handler.stream, 'reconfigure'):
        try:
            console_handler.stream.reconfigure(encoding='utf-8')
        except Exception:
            pass  # Fallback to default encoding
    
    sync_logger.addHandler(console_handler)
    
    # Handler para archivo
    log_filename = f"sync_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setFormatter(formatter)
    sync_logger.addHandler(file_handler)
    
    # Safe log message without emoji for Windows compatibility
    if sys.platform == 'win32':
        sync_logger.info(f"Logs saved to: {log_filename}")
    else:
        sync_logger.info(f"📝 Logs guardados en: {log_filename}")
    
    return sync_logger


@click.group(name="cloud")
def cloud() -> None:
    """Cloud storage synchronization and management."""
    pass


# ============================================================================
# SYNC COMMAND
# ============================================================================

@cloud.command(name="sync")
@click.option(
    "--profile",
    "-p",
    type=str,
    help="Use configuration profile from YAML file"
)
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    help="Path to configuration file (YAML)"
)
@click.option(
    "--provider",
    type=str,
    help="Cloud provider (aws, gcs, azure, digitalocean). Auto-detected from config if not specified."
)
@click.option(
    "--region",
    "-r",
    type=str,
    help="Cloud region (e.g., us-east-1 for AWS, sfo3 for DigitalOcean)"
)
@click.option(
    "--bucket",
    "-b",
    type=str,
    help="Bucket/container name"
)
@click.option(
    "--dest",
    "-d",
    type=click.Path(),
    help="Local destination directory"
)
@click.option(
    "--prefix",
    type=str,
    default="",
    help="Remote prefix/path to sync"
)
@click.option(
    "--workers",
    "-w",
    type=int,
    default=16,
    help="Number of parallel workers [default: 16]"
)
@click.option(
    "--delete",
    is_flag=True,
    help="Mirror mode: delete local files not in remote"
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Simulation mode: don't actually download"
)
@click.option(
    "--exclude",
    "-e",
    multiple=True,
    help="Exclude patterns (can specify multiple times)"
)
@click.option(
    "--no-progress",
    is_flag=True,
    help="Disable progress bars"
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default="INFO",
    help="Logging level [default: INFO]"
)
@click.option(
    "--output-json",
    "-o",
    type=click.Path(),
    help="Save JSON report to file"
)
@click.option(
    "--detailed-report",
    is_flag=True,
    help="Include detailed file list in JSON report"
)
# Provider-specific options
@click.option(
    "--access-key",
    type=str,
    help="AWS/DigitalOcean access key"
)
@click.option(
    "--secret-key",
    type=str,
    help="AWS/DigitalOcean secret key"
)
@click.option(
    "--project-id",
    type=str,
    help="Google Cloud project ID"
)
@click.option(
    "--credentials-path",
    type=click.Path(exists=True),
    help="Path to GCS service account JSON"
)
@click.option(
    "--account-name",
    type=str,
    help="Azure storage account name"
)
@click.option(
    "--account-key",
    type=str,
    help="Azure storage account key"
)
@click.option(
    "--connection-string",
    type=str,
    help="Azure connection string"
)
@click.option(
    "--container",
    type=str,
    help="Azure container name (alias for --bucket)"
)
@click.option(
    "--use-cache/--no-cache",
    default=True,
    help="Use local cache to skip already-synced files [default: use-cache]"
)
@click.option(
    "--sync-direction",
    type=click.Choice(["download", "upload", "bidirectional"], case_sensitive=False),
    default="download",
    help="Sync direction for orphan deletion: download (delete local), upload (delete remote), bidirectional (both) [default: download]"
)
@click.option(
    "--compress/--no-compress",
    default=False,
    help="Compress files before upload to reduce bandwidth [default: no-compress]"
)
@click.option(
    "--compression-type",
    type=click.Choice(["gzip", "lz4"], case_sensitive=False),
    default="gzip",
    help="Compression algorithm (gzip or lz4) [default: gzip]"
)
@click.option(
    "--encrypt/--no-encrypt",
    default=False,
    help="Enable client-side encryption (AES-256-GCM) [default: no-encrypt]"
)
@click.option(
    "--encryption-key",
    type=str,
    help="Encryption key (64 hex characters). Auto-generated if not provided."
)
@click.option(
    "--bandwidth-limit",
    type=int,
    help="Bandwidth limit in KB/s (e.g., 5000 for 5 MB/s)"
)
@click.option(
    "--multipart-threshold",
    type=int,
    default=100,
    help="File size threshold for multipart upload in MB [default: 100]"
)
def sync_command(
    profile: Optional[str],
    config: Optional[str],
    provider: Optional[str],
    region: Optional[str],
    bucket: Optional[str],
    dest: Optional[str],
    prefix: str,
    workers: int,
    delete: bool,
    dry_run: bool,
    exclude: tuple,
    no_progress: bool,
    log_level: str,
    output_json: Optional[str],
    detailed_report: bool,
    access_key: Optional[str],
    secret_key: Optional[str],
    project_id: Optional[str],
    credentials_path: Optional[str],
    account_name: Optional[str],
    account_key: Optional[str],
    connection_string: Optional[str],
    container: Optional[str],
    use_cache: bool,
    sync_direction: str,
    compress: bool,
    compression_type: str,
    encrypt: bool,
    encryption_key: Optional[str],
    bandwidth_limit: Optional[int],
    multipart_threshold: int
) -> None:
    """
    Synchronize cloud storage to local filesystem.
    
    Supports AWS S3, Google Cloud Storage, Azure Blob Storage, and DigitalOcean Spaces.
    Can use a profile from YAML configuration or direct CLI arguments.
    
    Examples:
    
      # Using a profile (auto-detects provider)
      tools cloud sync --profile daily_backups
      
      # AWS S3
      tools cloud sync --provider aws --bucket my-bucket \
                       --dest ./backup --region us-east-1
      
      # Google Cloud Storage
      tools cloud sync --provider gcs --bucket my-bucket \
                       --dest ./backup --project-id my-project
      
      # Azure Blob Storage
      tools cloud sync --provider azure --container my-container \
                       --dest ./backup --account-name myaccount
      
      # DigitalOcean Spaces (legacy, still supported)
      tools cloud sync --region sfo3 --bucket my-bucket --dest ./backup
      
      # Dry run with exclusions
      tools cloud sync -p prod --dry-run --exclude "*.tmp" --exclude "*.log"
    """
    sync_logger = setup_sync_logger(log_level)
    
    try:
        # Azure uses 'container' instead of 'bucket'
        if container and not bucket:
            bucket = container
        
        # Build provider configuration
        provider_config = {}
        
        # Determine sync parameters
        if profile:
            # Load from profile
            config_mgr = ConfigManager(logger=sync_logger)
            config_mgr.load_config(config)
            
            profile_obj = config_mgr.get_profile(profile)
            if not profile_obj:
                click.secho(f"✗ Profile '{profile}' not found", fg="red", err=True)
                available = config_mgr.list_profiles()
                if available:
                    click.echo(f"Available profiles: {', '.join(available)}", err=True)
                raise click.Abort()
            
            sync_logger.info(f"📋 Using profile: {profile}")
            
            # Get parameters from profile
            provider_config = dict(profile_obj)  # Copy all profile settings
            provider = provider or provider_config.get("provider")
            region = region or provider_config.get("region")
            bucket = bucket or provider_config.get("bucket") or provider_config.get("container")
            dest = dest or provider_config.get("dest")
            prefix = prefix or provider_config.get("prefix", "")
            workers = workers if workers != 16 else provider_config.get("workers", 16)
            delete = delete or provider_config.get("delete", False)
            dry_run = dry_run or provider_config.get("dry_run", False)
            exclude = list(exclude) if exclude else provider_config.get("exclude", [])
            no_progress = no_progress or not provider_config.get("show_progress", True)
            
            # Provider-specific from profile
            access_key = access_key or provider_config.get("access_key")
            secret_key = secret_key or provider_config.get("secret_key")
            project_id = project_id or provider_config.get("project_id")
            credentials_path = credentials_path or provider_config.get("credentials_path")
            account_name = account_name or provider_config.get("account_name")
            account_key = account_key or provider_config.get("account_key")
            connection_string = connection_string or provider_config.get("connection_string")
        
        else:
            # Validate required arguments
            if not bucket or not dest:
                click.secho(
                    "✗ Error: --bucket and --dest are required when not using --profile",
                    fg="red",
                    err=True
                )
                click.echo("Use --profile or provide all required arguments", err=True)
                raise click.Abort()
            
            exclude = list(exclude)
        
        # Auto-detect provider if not specified
        if not provider:
            # Try to auto-detect from configuration
            detection_config = {
                "bucket": bucket,
                "dest": dest,
            }
            if region:
                detection_config["region"] = region
            if project_id:
                detection_config["project_id"] = project_id
            if account_name:
                detection_config["account_name"] = account_name
            if container:
                detection_config["container"] = container
            
            try:
                from tools.cloud.factory import CloudProviderFactory
                provider = CloudProviderFactory.detect_provider_from_config(detection_config)
                sync_logger.info(f"🔍 Auto-detected provider: {provider}")
            except ValueError:
                # Default to DigitalOcean for backward compatibility
                provider = "digitalocean"
                sync_logger.info("⚙️  Using default provider: DigitalOcean Spaces (legacy mode)")
        
        # Build provider-specific configuration
        from tools.cloud.providers import SyncDirection
        
        # Convert sync_direction string to enum
        sync_dir_map = {
            "download": SyncDirection.DOWNLOAD,
            "upload": SyncDirection.UPLOAD,
            "bidirectional": SyncDirection.BIDIRECTIONAL,
        }
        sync_direction_enum = sync_dir_map.get(sync_direction.lower(), SyncDirection.DOWNLOAD)
        
        sync_config = {
            "bucket": bucket,
            "dest": dest,
            "prefix": prefix,
            "workers": workers,
            "delete": delete,
            "dry_run": dry_run,
            "exclude": exclude,
            "show_progress": not no_progress,
            "logger": sync_logger,
            "use_cache": use_cache,
            "sync_direction": sync_direction_enum,
            "compress": compress,
            "compression_type": compression_type.lower(),
            "encrypt": encrypt,
            "encryption_key": encryption_key,
            "bandwidth_limit": bandwidth_limit,
            "multipart_threshold": multipart_threshold,
        }
        
        # Add provider-specific credentials
        if provider.lower() in ["aws", "s3", "aws-s3", "digitalocean", "do"]:
            if region:
                sync_config["region"] = region
            if access_key:
                sync_config["access_key"] = access_key
            if secret_key:
                sync_config["secret_key"] = secret_key
        
        elif provider.lower() in ["google", "gcs", "google-cloud", "google-cloud-storage"]:
            if project_id:
                sync_config["project_id"] = project_id
            if credentials_path:
                sync_config["credentials_path"] = credentials_path
        
        elif provider.lower() in ["azure", "azure-blob"]:
            sync_config["container"] = bucket  # Azure uses 'container'
            if account_name:
                sync_config["account_name"] = account_name
            if account_key:
                sync_config["account_key"] = account_key
            if connection_string:
                sync_config["connection_string"] = connection_string
        
        # Display configuration
        click.echo("=" * 60)
        click.echo("SYNCHRONIZATION CONFIGURATION")
        click.echo("=" * 60)
        click.echo(f"  Provider:        {provider}")
        if region:
            click.echo(f"  Region:          {region}")
        click.echo(f"  Bucket:          {bucket}")
        click.echo(f"  Prefix:          {prefix or '(root)'}")
        click.echo(f"  Dest:            {dest}")
        click.echo(f"  Workers:         {workers}")
        click.echo(f"  Delete:          {delete}")
        if delete:
            click.echo(f"  Sync direction:  {sync_direction}")
        click.echo(f"  Use cache:       {use_cache}")
        if compress:
            click.echo(f"  Compression:     {compression_type}")
        if encrypt:
            click.echo(f"  Encryption:      AES-256-GCM")
        if bandwidth_limit:
            click.echo(f"  Bandwidth limit: {bandwidth_limit} KB/s")
        if multipart_threshold != 100:
            click.echo(f"  Multipart:       >{multipart_threshold} MB")
        click.echo(f"  Dry run:         {dry_run}")
        if exclude:
            click.echo(f"  Exclude:         {', '.join(exclude)}")
        click.echo("=" * 60)
        
        # Create provider instance using factory or legacy DigitalOceanSync
        if provider.lower() in ["digitalocean", "do"]:
            # Use legacy DigitalOceanSync for backward compatibility
            syncer = DigitalOceanSync(**sync_config)
        else:
            # Use new CloudProviderFactory
            from tools.cloud.factory import CloudProviderFactory
            try:
                # Remove logger from config dict since it's passed as a parameter to factory
                factory_config = {k: v for k, v in sync_config.items() if k != "logger"}
                syncer = CloudProviderFactory.create(provider, factory_config, logger=sync_logger)
            except ValueError as e:
                click.secho(f"✗ {e}", fg="red", err=True)
                click.echo("\nAvailable providers:")
                click.echo("  - aws, s3: Amazon S3")
                click.echo("  - gcs, google: Google Cloud Storage")
                click.echo("  - azure: Azure Blob Storage")
                click.echo("  - digitalocean, do: DigitalOcean Spaces")
                raise click.Abort()
        
        # Execute synchronization
        stats = syncer.sync()
        
        # Generate report
        report = stats.to_dict(include_details=detailed_report)
        
        # Display summary
        click.echo()
        click.secho("📊 SYNCHRONIZATION SUMMARY", fg="cyan", bold=True)
        click.echo("=" * 60)
        click.echo(f"  Downloaded:  {report['counts']['downloaded']:,} files")
        click.echo(f"  Skipped:     {report['counts']['skipped']:,} files")
        if delete:
            click.echo(f"  Deleted:     {report['counts']['deleted']:,} files")
        click.echo(f"  Errors:      {report['counts']['errors']:,}")
        click.echo(f"  Duration:    {report['duration_seconds']:.2f} seconds")
        click.echo(f"  Throughput:  {report['throughput_mb_s']:.2f} MB/s")
        click.echo(f"  Total data:  {report['throughput_gb']:.2f} GB")
        click.echo("=" * 60)
        
        # Save JSON report if requested
        if output_json:
            save_json_report(report, output_json, sync_logger)
            click.secho(f"✓ JSON report saved to: {output_json}", fg="green")
        
        # Exit code based on errors
        if report['counts']['errors'] > 0:
            click.secho("⚠️  Completed with errors", fg="yellow")
            raise click.exceptions.Exit(2)
        else:
            click.secho("✅ Synchronization completed successfully", fg="green")
    
    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        click.secho(f"✗ Configuration error: {e}", fg="red", err=True)
        raise click.Abort()
    
    except Exception as e:
        logger.error(f"Sync failed: {e}", exc_info=True)
        click.secho(f"✗ Synchronization failed: {e}", fg="red", err=True)
        raise click.Abort()


# ============================================================================
# PROFILES COMMAND
# ============================================================================

@cloud.command(name="profiles")
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    help="Path to configuration file (YAML)"
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output as JSON"
)
def profiles_command(config: Optional[str], output_json: bool) -> None:
    """
    List available configuration profiles.
    
    Examples:
    
      # List profiles from default locations
      tools cloud profiles
      
      # List from specific config file
      tools cloud profiles --config ~/my-profiles.yml
      
      # Output as JSON
      tools cloud profiles --json
    """
    try:
        config_mgr = ConfigManager(logger=logger)
        
        if not config_mgr.load_config(config):
            click.secho("No configuration file found", fg="yellow")
            click.echo("\nSearched paths:")
            for path in config_mgr.CONFIG_PATHS:
                exists = "✓" if path.exists() else "✗"
                click.echo(f"  {exists} {path}")
            return
        
        profiles_list = config_mgr.list_profiles()
        
        if not profiles_list:
            click.secho("No profiles configured", fg="yellow")
            return
        
        if output_json:
            # JSON output
            profiles_data = []
            for name in profiles_list:
                profile = config_mgr.get_profile(name)
                profiles_data.append({
                    "name": name,
                    "config": profile.to_dict()
                })
            
            click.echo(json.dumps({
                "config_file": str(config_mgr.get_loaded_file()),
                "profiles": profiles_data
            }, indent=2))
        
        else:
            # Human-readable output
            loaded_file = config_mgr.get_loaded_file()
            click.secho(f"\n📋 Available profiles (from {loaded_file}):\n", fg="cyan", bold=True)
            
            for name in profiles_list:
                profile = config_mgr.get_profile(name)
                desc = profile.get("description", "No description")
                region = profile.get("region", "unknown")
                bucket = profile.get("bucket", "unknown")
                dest = profile.get("dest", "unknown")
                
                click.secho(f"  • {name}", fg="green", bold=True)
                click.echo(f"    Description: {desc}")
                click.echo(f"    Region:      {region}")
                click.echo(f"    Bucket:      {bucket}")
                click.echo(f"    Dest:        {dest}")
                click.echo()
    
    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        click.secho(f"✗ Configuration error: {e}", fg="red", err=True)
        raise click.Abort()
    
    except Exception as e:
        logger.error(f"Failed to list profiles: {e}")
        click.secho(f"✗ Error: {e}", fg="red", err=True)
        raise click.Abort()


# ============================================================================
# UPLOAD COMMAND
# ============================================================================

@cloud.command(name="upload")
@click.argument("source", type=click.Path(exists=True))
@click.option("--profile", "-p", help="Config profile name")
@click.option("--config", "-c", type=click.Path(exists=True), help="Path to config file")
# Provider selection
@click.option("--provider", type=click.Choice(['aws', 's3', 'gcs', 'google', 'azure', 'digitalocean', 'do']),
              help="Cloud provider (auto-detected if not specified)")
# AWS/S3 options
@click.option("--access-key", help="AWS Access Key ID or DigitalOcean Spaces Key")
@click.option("--secret-key", help="AWS Secret Access Key or DigitalOcean Spaces Secret")
# GCS options
@click.option("--project-id", help="Google Cloud Project ID")
@click.option("--credentials-path", type=click.Path(exists=True), help="Path to GCS credentials JSON file")
# Azure options
@click.option("--account-name", help="Azure Storage Account Name")
@click.option("--account-key", help="Azure Storage Account Key")
@click.option("--connection-string", help="Azure Storage Connection String")
@click.option("--container", help="Azure Blob Storage Container")
# Common options
@click.option("--region", "-r", help="Cloud region (e.g., us-east-1, sfo3, westus)")
@click.option("--bucket", "-b", help="Bucket name (S3/GCS/Spaces) or container (Azure)")
@click.option("--dest", "-d", help="Remote destination prefix/path in bucket")
@click.option("--prefix", help="Prefix within bucket (legacy alias for --dest)")
@click.option("--workers", "-w", type=int, default=16, help="Parallel workers (default: 16)")
@click.option("--dry-run", is_flag=True, help="Simulate without uploading")
@click.option("--exclude", "-e", multiple=True, help="Exclude patterns (can be used multiple times)")
@click.option("--acl", type=click.Choice(['private', 'public-read', 'public-read-write']), 
              help="Access Control List for uploaded files")
@click.option("--content-type", help="Force specific content-type for all files")
@click.option("--no-progress", is_flag=True, help="Disable progress bars")
@click.option("--log-level", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]), 
              default="INFO", help="Logging level")
@click.option("--output-json", type=click.Path(), help="Save report as JSON file")
@click.option("--detailed-report", is_flag=True, help="Include detailed file list in JSON report")
@click.option("--delete", is_flag=True, help="Mirror mode: delete remote files not in source")
@click.option("--use-cache/--no-cache", default=True, help="Use local cache to skip already-uploaded files [default: use-cache]")
@click.option("--sync-direction", type=click.Choice(["download", "upload", "bidirectional"], case_sensitive=False), 
              default="upload", help="Sync direction for orphan deletion: download (delete local), upload (delete remote), bidirectional (both) [default: upload]")
@click.option("--compress/--no-compress", default=False, help="Compress files before upload to reduce bandwidth [default: no-compress]")
@click.option("--compression-type", type=click.Choice(["gzip", "lz4"], case_sensitive=False), default="gzip", 
              help="Compression algorithm (gzip or lz4) [default: gzip]")
@click.option("--encrypt/--no-encrypt", default=False, help="Enable client-side encryption (AES-256-GCM) [default: no-encrypt]")
@click.option("--encryption-key", type=str, help="Encryption key (64 hex characters). Auto-generated if not provided.")
@click.option("--bandwidth-limit", type=int, help="Bandwidth limit in KB/s (e.g., 5000 for 5 MB/s)")
@click.option("--multipart-threshold", type=int, default=100, help="File size threshold for multipart upload in MB [default: 100]")
def upload_command(
    source: str,
    profile: Optional[str],
    config: Optional[str],
    provider: Optional[str],
    access_key: Optional[str],
    secret_key: Optional[str],
    project_id: Optional[str],
    credentials_path: Optional[str],
    account_name: Optional[str],
    account_key: Optional[str],
    connection_string: Optional[str],
    container: Optional[str],
    region: Optional[str],
    bucket: Optional[str],
    dest: Optional[str],
    prefix: Optional[str],
    workers: int,
    dry_run: bool,
    exclude: tuple,
    acl: Optional[str],
    content_type: Optional[str],
    no_progress: bool,
    log_level: str,
    output_json: Optional[str],
    detailed_report: bool,
    delete: bool,
    use_cache: bool,
    sync_direction: str,
    compress: bool,
    compression_type: str,
    encrypt: bool,
    encryption_key: Optional[str],
    bandwidth_limit: Optional[int],
    multipart_threshold: int
) -> None:
    """
    Upload files to cloud storage (AWS S3, Google Cloud Storage, Azure, DigitalOcean Spaces).
    
    SOURCE: Local file or directory to upload
    
    Examples:
    
      # Upload using a profile
      tools cloud upload ./backups --profile production_uploads
    
      # Upload to AWS S3
      tools cloud upload ./data --provider aws --bucket my-bucket --region us-east-1 --dest backups/
      
      # Upload to Google Cloud Storage
      tools cloud upload ./data --provider gcs --bucket my-bucket --project-id my-project --dest backups/
      
      # Upload to Azure Blob Storage
      tools cloud upload ./data --provider azure --container my-container --account-name myaccount --dest backups/
    
      # Upload to DigitalOcean Spaces (backward compatibility)
      tools cloud upload ./data --region sfo3 --bucket my-bucket --dest backups/
    
      # Upload with ACL and dry-run
      tools cloud upload ./public --provider aws --bucket web-assets --acl public-read --dry-run
    
      # Upload single file
      tools cloud upload report.pdf --provider aws --bucket docs --region us-east-1 --dest reports/
    """
    from tools.cloud import DigitalOceanSync, ConfigManager
    from tools.cloud.sync import save_json_report
    
    # Setup logger
    logger = setup_sync_logger(log_level)
    
    try:
        # Handle --dest vs --prefix
        dest_prefix = dest or prefix or""
        
        # Load configuration from profile if specified
        if profile or config:
            config_manager = ConfigManager(config_file=config)
            
            if profile:
                if not config_manager.has_profile(profile):
                    available = ", ".join(config_manager.list_profiles())
                    click.secho(f"✗ Profile '{profile}' not found", fg="red", err=True)
                    click.echo(f"Available profiles: {available}")
                    raise click.Abort()
                
                profile_config = config_manager.get_profile(profile)
                
                # CLI args override profile config
                provider = provider or profile_config.get('provider')
                region = region or profile_config.get('region')
                bucket = bucket or profile_config.get('bucket')
                container = container or profile_config.get('container')
                dest_prefix = dest_prefix or profile_config.get('dest', '')
                workers = workers if workers != 16 else profile_config.get('workers', 16)
                dry_run = dry_run or profile_config.get('dry_run', False)
                exclude = exclude or profile_config.get('exclude', [])
                acl = acl or profile_config.get('acl')
                content_type = content_type or profile_config.get('content_type')
                
                # Provider-specific credentials from profile
                access_key = access_key or profile_config.get('access_key')
                secret_key = secret_key or profile_config.get('secret_key')
                project_id = project_id or profile_config.get('project_id')
                credentials_path = credentials_path or profile_config.get('credentials_path')
                account_name = account_name or profile_config.get('account_name')
                account_key = account_key or profile_config.get('account_key')
                connection_string = connection_string or profile_config.get('connection_string')
                
                logger.info(f"Using profile: {profile}")
        
        # Auto-detect provider if not specified
        if not provider:
            from tools.cloud.factory import CloudProviderFactory
            
            upload_config = {
                "region": region,
                "bucket": bucket or container,
                "access_key": access_key,
                "secret_key": secret_key,
                "project_id": project_id,
                "credentials_path": credentials_path,
                "account_name": account_name,
                "account_key": account_key,
                "connection_string": connection_string,
                "container": container,
            }
            
            provider = CloudProviderFactory.detect_provider_from_config(upload_config)
            logger.info(f"🔍 Auto-detected provider: {provider}")
        
        # Normalize provider aliases
        provider_aliases = {
            's3': 'aws',
            'google': 'gcs',
            'do': 'digitalocean'
        }
        provider = provider_aliases.get(provider.lower(), provider.lower())
        
        # Build provider-specific config
        from tools.cloud.providers import SyncDirection
        
        # Convert sync_direction string to enum
        sync_dir_map = {
            "download": SyncDirection.DOWNLOAD,
            "upload": SyncDirection.UPLOAD,
            "bidirectional": SyncDirection.BIDIRECTIONAL,
        }
        sync_direction_enum = sync_dir_map.get(sync_direction.lower(), SyncDirection.UPLOAD)
        
        upload_config = {
            "bucket": bucket or container,
            "dest": "",  # Not used directly by provider
            "prefix": "",  # Not used directly by provider
            "workers": workers,
            "delete": delete,
            "dry_run": dry_run,
            "exclude": list(exclude) if exclude else [],
            "show_progress": not no_progress,
            "logger": logger,
            "use_cache": use_cache,
            "sync_direction": sync_direction_enum,
            "compress": compress,
            "compression_type": compression_type.lower(),
            "encrypt": encrypt,
            "encryption_key": encryption_key,
            "bandwidth_limit": bandwidth_limit,
            "multipart_threshold": multipart_threshold,
        }
        
        # Add provider-specific credentials
        if provider == "aws":
            if not bucket:
                click.secho("✗ --bucket is required for AWS S3", fg="red", err=True)
                raise click.Abort()
            
            upload_config["region"] = region or "us-east-1"
            if access_key:
                upload_config["access_key"] = access_key
            if secret_key:
                upload_config["secret_key"] = secret_key
            if profile:
                upload_config["profile"] = profile
        
        elif provider == "gcs":
            if not bucket:
                click.secho("✗ --bucket is required for Google Cloud Storage", fg="red", err=True)
                raise click.Abort()
            
            upload_config["region"] = region
            if project_id:
                upload_config["project_id"] = project_id
            if credentials_path:
                upload_config["credentials_path"] = credentials_path
        
        elif provider == "azure":
            if not container:
                click.secho("✗ --container is required for Azure Blob Storage", fg="red", err=True)
                raise click.Abort()
            
            upload_config["bucket"] = container  # Rename container to bucket for provider
            upload_config["region"] = region
            if account_name:
                upload_config["account_name"] = account_name
            if account_key:
                upload_config["account_key"] = account_key
            if connection_string:
                upload_config["connection_string"] = connection_string
        
        elif provider == "digitalocean":
            if not region:
                click.secho("✗ --region is required for DigitalOcean Spaces", fg="red", err=True)
                raise  click.Abort()
            
            if not bucket:
                click.secho("✗ --bucket is required for DigitalOcean Spaces", fg="red", err=True)
                raise click.Abort()
            
            upload_config["region"] = region
            if access_key:
                upload_config["access_key"] = access_key
            if secret_key:
                upload_config["secret_key"] = secret_key
        
        # Display configuration
        click.echo("=" * 60)
        click.echo("UPLOAD CONFIGURATION")
        click.echo("=" * 60)
        click.echo(f"  Provider:        {provider}")
        if region:
            click.echo(f"  Region:          {region}")
        click.echo(f"  Bucket:          {bucket or container or '(not set)'}")
        click.echo(f"  Source:          {source}")
        click.echo(f"  Dest:            {dest_prefix or '(root)'}")
        click.echo(f"  Workers:         {workers}")
        click.echo(f"  Delete:          {delete}")
        if delete:
            click.echo(f"  Sync direction:  {sync_direction}")
        click.echo(f"  Use cache:       {use_cache}")
        click.echo(f"  Dry run:         {dry_run}")
        if acl:
            click.echo(f"  ACL:             {acl}")
        if content_type:
            click.echo(f"  Content:         {content_type}")
        if exclude:
            click.echo(f"  Exclude:         {', '.join(exclude)}")
        click.echo("=" * 60)
        
        # Create uploader instance using factory or legacy DigitalOceanSync
        if provider.lower() in ["digitalocean", "do"]:
            # Use legacy DigitalOceanSync for backward compatibility
            uploader = DigitalOceanSync(**upload_config)
        else:
            # Use new CloudProviderFactory
            from tools.cloud.factory import CloudProviderFactory
            try:
                # Remove logger from config dict since it's passed as a parameter to factory
                factory_config = {k: v for k, v in upload_config.items() if k != "logger"}
                uploader = CloudProviderFactory.create(provider, factory_config, logger=logger)
            except ValueError as e:
                click.secho(f"✗ {e}", fg="red", err=True)
                click.echo("\nAvailable providers:")
                click.echo("  - aws, s3: Amazon S3")
                click.echo("  - gcs, google: Google Cloud Storage")
                click.echo("  - azure: Azure Blob Storage")
                click.echo("  - digitalocean, do: DigitalOcean Spaces")
                raise click.Abort()
        
        # Prepare kwargs for upload
        upload_kwargs = {}
        if acl:
            upload_kwargs['acl'] = acl
        if content_type:
            upload_kwargs['content_type'] = content_type
        
        # Execute upload
        upload_stats = uploader.upload(
            source=source,
            dest_prefix=dest_prefix,
            **upload_kwargs
        )
        
        # Generate report from stats
        if hasattr(upload_stats, 'to_dict'):
            report = upload_stats.to_dict(include_details=detailed_report)
        else:
            # If uploader returns dict directly (from CloudProvider base class)
            report = upload_stats
        
        # Save JSON report if requested
        if output_json:
            save_json_report(report, output_json, logger)
            click.secho(f"✓ JSON report saved to: {output_json}", fg="green")
        
        # Display console summary
        if hasattr(upload_stats, 'uploaded'):
            # DigitalOceanSync UploadStats object
            uploaded = len(upload_stats.uploaded)
            updated = len(upload_stats.updated)
            skipped = len(upload_stats.skipped)
            errors = len(upload_stats.errors)
        else:
            # CloudProvider dict-based stats
            uploaded = report.get('uploaded', 0)
            updated = report.get('updated', 0)
            skipped = report.get('skipped', 0)
            errors = len(report.get('errors', []))
        
        if errors > 0:
            click.secho(f"⚠️  Upload completed with {errors} error(s)", fg="yellow")
            for err in report.get('errors', [])[:5]:
                click.echo(f"   - {err}")
            if errors > 5:
                click.echo(f"   ... and {errors - 5} more errors")
        else:
            click.secho(f"✅ Upload completed successfully", fg="green")
            click.echo(f"   Uploaded: {uploaded:,} | Updated: {updated:,} | Skipped: {skipped:,}")
    
    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        click.secho(f"✗ Configuration error: {e}", fg="red", err=True)
        raise click.Abort()
    
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        click.secho(f"✗ File not found: {e}", fg="red", err=True)
        raise click.Abort()
    
    except Exception as e:
        logger.error(f"Upload failed: {e}", exc_info=True)
        click.secho(f"✗ Upload failed: {e}", fg="red", err=True)
        raise click.Abort()


# ============================================================================
# PROVIDERS COMMAND - List available cloud providers
# ============================================================================

@cloud.command(name="providers")
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output as JSON"
)
def providers_command(output_json: bool) -> None:
    """
    List available cloud providers and their status.
    
    Shows which providers are available and installed.
    
    Examples:
    
      # List all providers
      tools cloud providers
      
      # Output as JSON
      tools cloud providers --json
    """
    from tools.cloud.factory import CloudProviderFactory
    
    try:
        providers = CloudProviderFactory._load_providers()
        errors = CloudProviderFactory._ERRORS_CACHE
        
        if output_json:
            # JSON output
            providers_list = []
            for name, provider_class in providers.items():
                status = "installed" if provider_class is not None else "missing"
                error_msg = errors.get(name, None)
                providers_list.append({
                    "name": name,
                    "status": status,
                    "error": error_msg
                })
            
            # Remove duplicates by keeping one per provider type
            seen = set()
            unique_providers = []
            for p in providers_list:
                base_name = p["name"].split("-")[0] if "-" in p["name"] else p["name"]
                if base_name not in seen:
                    seen.add(base_name)
                    unique_providers.append(p)
            
            click.echo(json.dumps({
                "providers": unique_providers
            }, indent=2))
        
        else:
            # Human-readable output
            click.secho("\n☁️  Available Cloud Providers\n", fg="cyan", bold=True)
            
            # Group by provider type
            provider_types = {}
            for alias, provider_class in providers.items():
                # Get base provider name
                if alias in ["aws", "s3", "aws-s3"]:
                    base = "AWS S3"
                elif alias in ["google", "gcs", "google-cloud", "google-cloud-storage"]:
                    base = "Google Cloud Storage"
                elif alias in ["azure", "azure-blob"]:
                    base = "Azure Blob Storage"
                elif alias in ["digitalocean", "do"]:
                    base = "DigitalOcean Spaces"
                else:
                    base = alias
                
                if base not in provider_types:
                    provider_types[base] = {"class": provider_class, "aliases": []}
                provider_types[base]["aliases"].append(alias)
            
            for provider_name in sorted(provider_types.keys()):
                provider_info = provider_types[provider_name]
                provider_class = provider_info["class"]
                aliases = provider_info["aliases"]
                
                if provider_class:
                    status = click.style("✓ installed", fg="green")
                else:
                    error = errors.get(aliases[0], "dependencies not installed")
                    status = click.style(f"✗ {error.split(':')[0]}", fg="red")
                
                aliases_str = ", ".join(aliases)
                click.echo(f"  • {provider_name:30s} [{aliases_str:20s}] {status}")
            
            click.echo()
    
    except Exception as e:
        logger.error(f"Failed to list providers: {e}")
        click.secho(f"✗ Error: {e}", fg="red", err=True)
        raise click.Abort()


# ============================================================================
# CREDENTIALS COMMAND - Show credential requirements
# ============================================================================

@cloud.command(name="credentials")
@click.argument("provider", type=str)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output as JSON"
)
def credentials_command(provider: str, output_json: bool) -> None:
    """
    Show credential requirements for a cloud provider.
    
    PROVIDER: Cloud provider name (aws, gcs, azure, etc.)
    
    Examples:
    
      # Show AWS S3 credentials needed
      tools cloud credentials aws
      
      # Show Google Cloud Storage credentials
      tools cloud credentials gcs
      
      # Output as JSON
      tools cloud credentials azure --json
    """
    from tools.cloud.factory import CloudProviderFactory
    
    try:
        credentials = CloudProviderFactory.get_credential_requirements(provider)
        
        if output_json:
            # JSON output
            click.echo(json.dumps({
                "provider": provider,
                "credentials": credentials
            }, indent=2))
        
        else:
            # Human-readable output
            click.secho(f"\n🔐 Credential Requirements for {provider.upper()}\n", fg="cyan", bold=True)
            
            if not credentials:
                click.echo("  No specific credentials required or provider not found")
            else:
                for var_name, description in credentials.items():
                    current_value = f"(set)" if var_name in __import__("os").environ else "(not set)"
                    click.echo(f"  • {var_name:40s} {current_value}")
                    if description:
                        click.echo(f"    → {description}")
            
            # Show setup instructions for common providers
            if provider.lower() in ["aws", "s3"]:
                click.secho("\n📝 AWS S3 Setup Instructions:", fg="yellow")
                click.echo("""
  1. Create AWS account at https://aws.amazon.com
  2. Create new S3 bucket
  3. Create IAM user with S3 permissions
  4. Configure credentials:
     - Option A: Set environment variables
       export AWS_ACCESS_KEY_ID=your-key
       export AWS_SECRET_ACCESS_KEY=your-secret
     
     - Option B: Use AWS profile
       tools cloud sync --profile myprofile
       (requires AWS_PROFILE environment variable)
""")
            
            elif provider.lower() in ["gcs", "google", "google-cloud", "google-cloud-storage"]:
                click.secho("\n📝 Google Cloud Storage Setup Instructions:", fg="yellow")
                click.echo("""
  1. Create GCP project at https://console.cloud.google.com
  2. Enable Cloud Storage API
  3. Create service account and download JSON credentials
  4. Configure credentials:
     - Option A: Set environment variable
       export GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
     
     - Option B: Use in configuration profile
       provide credentials_path in YAML config
""")
            
            elif provider.lower() in ["azure", "azure-blob"]:
                click.secho("\n📝 Azure Blob Storage Setup Instructions:", fg="yellow")
                click.echo("""
  1. Create Azure account at https://azure.microsoft.com
  2. Create Storage Account
  3. Create Blob Container
  4. Get connection string or access keys
  5. Configure credentials:
     - Option A: Set environment variable
       export AZURE_STORAGE_CONNECTION_STRING=connection-string
     
     - Option B: Set account credentials
       export AZURE_STORAGE_ACCOUNT_NAME=account-name
       export AZURE_STORAGE_ACCOUNT_KEY=account-key
""")
            
            click.echo()
    
    except ValueError as e:
        logger.error(f"Invalid provider: {e}")
        click.secho(f"✗ {e}", fg="red", err=True)
        click.echo("\nUse 'tools cloud providers' to see available providers")
        raise click.Abort()
    
    except Exception as e:
        logger.error(f"Failed to get credentials: {e}")
        click.secho(f"✗ Error: {e}", fg="red", err=True)
        raise click.Abort()

# ============================================================================
# CACHE COMMAND GROUP - Manage local sync cache
# ============================================================================

@cloud.command(name="cache-stats")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def cache_stats_command(output_json: bool) -> None:
    """
    Show cache statistics and information.
    
    Examples:
    
      # Show cache stats
      tools cloud cache-stats
      
      # Output as JSON
      tools cloud cache-stats --json
    """
    from tools.cloud.cache import SyncCache
    import json
    
    try:
        with SyncCache() as cache:
            stats = cache.get_stats()
        
        if output_json:
            click.echo(json.dumps(stats, indent=2))
        else:
            click.secho("\n📊 Sync Cache Statistics\n", fg="cyan", bold=True)
            click.echo(f"Cache Path:      {stats['cache_path']}")
            click.echo(f"Total Files:     {stats['total_files']:,}")
            click.echo(f"Total Size:      {stats['total_size_gb']:.2f} GB ({stats['total_size_bytes']:,} bytes)")
            
            if stats['oldest_sync'] and stats['newest_sync']:
                click.echo(f"Oldest Sync:     {stats['oldest_sync']}")
                click.echo(f"Newest Sync:     {stats['newest_sync']}")
            
            if stats['by_provider']:
                click.echo("\n📦 By Provider:")
                for provider, data in stats['by_provider'].items():
                    size_gb = data['size'] / (1024**3)
                    click.echo(f"  {provider:15} {data['count']:>6,} files  {size_gb:>8.2f} GB")
            
            if stats['by_bucket']:
                click.echo("\n🗂️  By Bucket:")
                for provider, bucket, count, size in stats['by_bucket']:
                    size_gb = size / (1024**3)
                    click.echo(f"  {provider}/{bucket:20} {count:>6,} files  {size_gb:>8.2f} GB")
            
            click.echo()
    
    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}")
        click.secho(f"✗ Error: {e}", fg="red", err=True)
        raise click.Abort()


@cloud.command(name="cache-list")
@click.option("--provider", help="Filter by provider")
@click.option("--bucket", help="Filter by bucket")
@click.option("--limit", type=int, default=50, help="Maximum results (default: 50)")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def cache_list_command(provider: Optional[str], bucket: Optional[str], 
                       limit: int, output_json: bool) -> None:
    """
    List cached file entries.
    
    Examples:
    
      # List recent cached files
      tools cloud cache-list
      
      # List AWS files
      tools cloud cache-list --provider aws
      
      # List specific bucket
      tools cloud cache-list --provider aws --bucket my-bucket
      
      # Limit results
      tools cloud cache-list --limit 100
      
      # Output as JSON
      tools cloud cache-list --json
    """
    from tools.cloud.cache import SyncCache
    import json
    
    try:
        with SyncCache() as cache:
            files = cache.list_files(provider=provider, bucket=bucket, limit=limit)
        
        if output_json:
            click.echo(json.dumps(files, indent=2))
        else:
            if not files:
                click.secho("No cached files found", fg="yellow")
                return
            
            click.secho(f"\n📁 Cached Files (showing {len(files)} of max {limit})\n", 
                       fg="cyan", bold=True)
            
            for file in files:
                size_mb = file['file_size'] / (1024**2)
                click.echo(f"Provider:  {file['provider']}")
                click.echo(f"Bucket:    {file['bucket']}")
                click.echo(f"Remote:    {file['remote_key']}")
                click.echo(f"Local:     {file['local_path']}")
                click.echo(f"Size:      {size_mb:.2f} MB")
                click.echo(f"Synced:    {file['synced_at']}")
                if file['checksum']:
                    click.echo(f"Checksum:  {file['checksum']}")
                click.echo()
    
    except Exception as e:
        logger.error(f"Failed to list cache: {e}")
        click.secho(f"✗ Error: {e}", fg="red", err=True)
        raise click.Abort()


@cloud.command(name="cache-clear")
@click.option("--provider", help="Clear only specific provider")
@click.option("--bucket", help="Clear only specific bucket (requires --provider)")
@click.option("--all", "clear_all", is_flag=True, help="Clear entire cache")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def cache_clear_command(provider: Optional[str], bucket: Optional[str], 
                        clear_all: bool, yes: bool) -> None:
    """
    Clear sync cache entries.
    
    Examples:
    
      # Clear specific bucket
      tools cloud cache-clear --provider aws --bucket my-bucket
      
      # Clear all AWS entries
      tools cloud cache-clear --provider aws
      
      # Clear entire cache
      tools cloud cache-clear --all
      
      # Skip confirmation
      tools cloud cache-clear --all -y
    """
    from tools.cloud.cache import SyncCache
    
    try:
        with SyncCache() as cache:
            # Determine what to clear
            if clear_all:
                target = "entire cache"
            elif provider and bucket:
                target = f"{provider}/{bucket}"
            elif provider:
                target = f"all {provider} entries"
            else:
                click.secho("✗ Must specify --provider, --bucket, or --all", fg="red", err=True)
                click.echo("\nExamples:")
                click.echo("  tools cloud cache-clear --all")
                click.echo("  tools cloud cache-clear --provider aws")
                click.echo("  tools cloud cache-clear --provider aws --bucket my-bucket")
                raise click.Abort()
            
            # Confirm
            if not yes:
                if not click.confirm(f"Clear {target}?"):
                    click.echo("Cancelled")
                    return
            
            # Clear
            if clear_all:
                deleted = cache.clear_all()
            elif bucket:
                deleted = cache.clear_bucket(provider, bucket)
            else:
                # Clear all for provider
                deleted = cache.clear_bucket(provider, "")  # Empty bucket clears all
            
            click.secho(f"✓ Cleared {deleted:,} entries from cache", fg="green")
    
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        click.secho(f"✗ Error: {e}", fg="red", err=True)
        raise click.Abort()


# ============================================================================
# LIST COMMAND
# ============================================================================

@cloud.command(name="list")
@click.option("--profile", "-p", help="Config profile name")
@click.option("--config", "-c", type=click.Path(exists=True), help="Path to config file")
@click.option("--provider", type=click.Choice(['aws', 's3', 'gcs', 'google', 'azure', 'digitalocean', 'do']),
              help="Cloud provider")
@click.option("--region", "-r", help="Cloud region")
@click.option("--bucket", "-b", help="Bucket/container name")
@click.option("--prefix", help="Filter by prefix")
@click.option("--pattern", help="Filter by glob pattern (e.g., '*.jpg')")
@click.option("--limit", type=int, help="Limit number of results")
@click.option("--format", "output_format", type=click.Choice(['table', 'json', 'csv', 'simple']),
              default='table', help="Output format [default: table]")
@click.option("--sort-by", type=click.Choice(['name', 'size', 'date']),
              default='name', help="Sort by field [default: name]")
@click.option("--reverse", is_flag=True, help="Reverse sort order")
# Provider credentials
@click.option("--access-key", help="AWS/DigitalOcean access key")
@click.option("--secret-key", help="AWS/DigitalOcean secret key")
@click.option("--project-id", help="Google Cloud project ID")
@click.option("--credentials-path", type=click.Path(exists=True), help="Path to GCS credentials JSON")
@click.option("--account-name", help="Azure storage account name")
@click.option("--account-key", help="Azure storage account key")
@click.option("--connection-string", help="Azure connection string")
@click.option("--container", help="Azure container name (alias for --bucket)")
def list_command(
    profile: Optional[str],
    config: Optional[str],
    provider: Optional[str],
    region: Optional[str],
    bucket: Optional[str],
    prefix: Optional[str],
    pattern: Optional[str],
    limit: Optional[int],
    output_format: str,
    sort_by: str,
    reverse: bool,
    access_key: Optional[str],
    secret_key: Optional[str],
    project_id: Optional[str],
    credentials_path: Optional[str],
    account_name: Optional[str],
    account_key: Optional[str],
    connection_string: Optional[str],
    container: Optional[str]
) -> None:
    """
    List objects in cloud storage bucket.
    
    Examples:
    
      # List using profile
      tools cloud list --profile production
      
      # List AWS S3 bucket
      tools cloud list --provider aws --bucket my-bucket --region us-east-1
      
      # List with prefix filter
      tools cloud list --profile prod --prefix backups/2024/
      
      # List with pattern filter
      tools cloud list --provider gcs --bucket my-bucket --pattern "*.jpg"
      
      # List sorted by size
      tools cloud list --profile prod --sort-by size --reverse
      
      # List in JSON format
      tools cloud list --provider aws --bucket my-bucket --format json
    """
    from tools.cloud.factory import CloudProviderFactory
    import fnmatch
    import json as json_module
    
    logger = setup_sync_logger("ERROR")  # Minimal logging for list command
    
    try:
        # Load from profile if specified
        if profile:
            config_manager = ConfigManager(config_file=config)
            profile_obj = config_manager.get_profile(profile)
            if not profile_obj:
                click.secho(f"✗ Profile '{profile}' not found", fg="red", err=True)
                raise click.Abort()
            
            provider = provider or profile_obj.get('provider')
            region = region or profile_obj.get('region')
            bucket = bucket or profile_obj.get('bucket') or profile_obj.get('container')
            prefix = prefix or profile_obj.get('prefix', '')
            access_key = access_key or profile_obj.get('access_key')
            secret_key = secret_key or profile_obj.get('secret_key')
            project_id = project_id or profile_obj.get('project_id')
            credentials_path = credentials_path or profile_obj.get('credentials_path')
            account_name = account_name or profile_obj.get('account_name')
            account_key = account_key or profile_obj.get('account_key')
            connection_string = connection_string or profile_obj.get('connection_string')
        
        # Validate required parameters
        if not bucket and not container:
            click.secho("✗ --bucket (or --container) is required", fg="red", err=True)
            raise click.Abort()
        
        bucket = bucket or container
        
        # Build provider config
        provider_config = {
            "bucket": bucket,
            "dest": "/tmp",  # Dummy dest for list operation
            "prefix": prefix or "",
            "dry_run": True,  # List doesn't modify anything
            "logger": logger
        }
        
        # Add provider-specific credentials
        if provider in ["aws", "s3", "digitalocean", "do"]:
            if region:
                provider_config["region"] = region
            if access_key:
                provider_config["access_key"] = access_key
            if secret_key:
                provider_config["secret_key"] = secret_key
        elif provider in ["gcs", "google"]:
            if project_id:
                provider_config["project_id"] = project_id
            if credentials_path:
                provider_config["credentials_path"] = credentials_path
        elif provider in ["azure"]:
            if account_name:
                provider_config["account_name"] = account_name
            if account_key:
                provider_config["account_key"] = account_key
            if connection_string:
                provider_config["connection_string"] = connection_string
        
        # Create provider instance
        cloud_provider = CloudProviderFactory.create(provider, provider_config, logger=logger)
        
        # List objects
        objects = list(cloud_provider._list_objects())
        
        # Filter by pattern if specified
        if pattern:
            objects = [obj for obj in objects if fnmatch.fnmatch(obj.key, pattern)]
        
        # Apply limit
        if limit:
            objects = objects[:limit]
        
        # Sort objects
        if sort_by == 'name':
            objects.sort(key=lambda x: x.key, reverse=reverse)
        elif sort_by == 'size':
            objects.sort(key=lambda x: x.size_bytes, reverse=reverse)
        elif sort_by == 'date':
            objects.sort(key=lambda x: x.modified, reverse=reverse)
        
        # Output based on format
        if output_format == 'json':
            data = [{
                "key": obj.key,
                "size_bytes": obj.size_bytes,
                "modified": obj.modified.isoformat() if obj.modified else None,
                "etag": obj.etag
            } for obj in objects]
            click.echo(json_module.dumps(data, indent=2))
        
        elif output_format == 'csv':
            click.echo("key,size_bytes,modified,etag")
            for obj in objects:
                modified_str = obj.modified.isoformat() if obj.modified else ""
                click.echo(f'"{obj.key}",{obj.size_bytes},"{modified_str}","{obj.etag or ""}"')
        
        elif output_format == 'simple':
            for obj in objects:
                click.echo(obj.key)
        
        else:  # table
            if not objects:
                click.echo("No objects found")
                return
            
            click.echo(f"\n{len(objects)} object(s) in {provider}://{bucket}/{prefix or ''}\n")
            click.echo(f"{'KEY':<60} {'SIZE':>12} {'MODIFIED':<20}")
            click.echo("-" * 95)
            
            for obj in objects:
                size_str = f"{obj.size_bytes:,}" if obj.size_bytes < 1024**3 else f"{obj.size_bytes/(1024**3):.2f} GB"
                modified_str = obj.modified.strftime("%Y-%m-%d %H:%M:%S") if obj.modified else "-"
                click.echo(f"{obj.key:<60} {size_str:>12} {modified_str:<20}")
            
            total_size = sum(obj.size_bytes for obj in objects)
            total_gb = total_size / (1024**3)
            click.echo("-" * 95)
            click.echo(f"Total: {len(objects):,} objects, {total_gb:.2f} GB")
    
    except Exception as e:
        click.secho(f"✗ Error listing objects: {e}", fg="red", err=True)
        raise click.Abort()


# ============================================================================
# DELETE COMMAND
# ============================================================================

@cloud.command(name="delete")
@click.argument("keys", nargs=-1, required=True)
@click.option("--profile", "-p", help="Config profile name")
@click.option("--config", "-c", type=click.Path(exists=True), help="Path to config file")
@click.option("--provider", type=click.Choice(['aws', 's3', 'gcs', 'google', 'azure', 'digitalocean', 'do']),
              help="Cloud provider")
@click.option("--region", "-r", help="Cloud region")
@click.option("--bucket", "-b", help="Bucket/container name")
@click.option("--prefix", help="Delete all objects with prefix")
@click.option("--pattern", help="Delete objects matching glob pattern")
@click.option("--dry-run", is_flag=True, help="Simulate without deleting")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
# Provider credentials
@click.option("--access-key", help="AWS/DigitalOcean access key")
@click.option("--secret-key", help="AWS/DigitalOcean secret key")
@click.option("--project-id", help="Google Cloud project ID")
@click.option("--credentials-path", type=click.Path(exists=True), help="Path to GCS credentials JSON")
@click.option("--account-name", help="Azure storage account name")
@click.option("--account-key", help="Azure storage account key")
@click.option("--connection-string", help="Azure connection string")
@click.option("--container", help="Azure container name (alias for --bucket)")
def delete_command(
    keys: tuple,
    profile: Optional[str],
    config: Optional[str],
    provider: Optional[str],
    region: Optional[str],
    bucket: Optional[str],
    prefix: Optional[str],
    pattern: Optional[str],
    dry_run: bool,
    yes: bool,
    access_key: Optional[str],
    secret_key: Optional[str],
    project_id: Optional[str],
    credentials_path: Optional[str],
    account_name: Optional[str],
    account_key: Optional[str],
    connection_string: Optional[str],
    container: Optional[str]
) -> None:
    """
    Delete objects from cloud storage.
    
    KEYS: One or more object keys to delete
    
    Examples:
    
      # Delete specific files
      tools cloud delete file1.txt file2.txt --provider aws --bucket my-bucket
      
      # Delete with prefix
      tools cloud delete --prefix backups/old/ --provider aws --bucket my-bucket
      
      # Delete with pattern
      tools cloud delete --pattern "*.tmp" --provider gcs --bucket my-bucket
      
      # Dry run
      tools cloud delete --prefix temp/ --dry-run --profile production
    """
    from tools.cloud.factory import CloudProviderFactory
    import fnmatch
    
    logger = setup_sync_logger("INFO")
    
    try:
        # Load from profile if specified
        if profile:
            config_manager = ConfigManager(config_file=config)
            profile_obj = config_manager.get_profile(profile)
            if not profile_obj:
                click.secho(f"✗ Profile '{profile}' not found", fg="red", err=True)
                raise click.Abort()
            
            provider = provider or profile_obj.get('provider')
            region = region or profile_obj.get('region')
            bucket = bucket or profile_obj.get('bucket') or profile_obj.get('container')
            access_key = access_key or profile_obj.get('access_key')
            secret_key = secret_key or profile_obj.get('secret_key')
            project_id = project_id or profile_obj.get('project_id')
            credentials_path = credentials_path or profile_obj.get('credentials_path')
            account_name = account_name or profile_obj.get('account_name')
            account_key = account_key or profile_obj.get('account_key')
            connection_string = connection_string or profile_obj.get('connection_string')
        
        # Validate required parameters
        if not bucket and not container:
            click.secho("✗ --bucket (or --container) is required", fg="red", err=True)
            raise click.Abort()
        
        bucket = bucket or container
        
        # Build provider config
        provider_config = {
            "bucket": bucket,
            "dest": "/tmp",  # Dummy dest
            "prefix": "",
            "dry_run": dry_run,
            "logger": logger
        }
        
        # Add provider-specific credentials
        if provider in ["aws", "s3", "digitalocean", "do"]:
            if region:
                provider_config["region"] = region
            if access_key:
                provider_config["access_key"] = access_key
            if secret_key:
                provider_config["secret_key"] = secret_key
        elif provider in ["gcs", "google"]:
            if project_id:
                provider_config["project_id"] = project_id
            if credentials_path:
                provider_config["credentials_path"] = credentials_path
        elif provider in ["azure"]:
            if account_name:
                provider_config["account_name"] = account_name
            if account_key:
                provider_config["account_key"] = account_key
            if connection_string:
                provider_config["connection_string"] = connection_string
        
        # Create provider instance
        cloud_provider = CloudProviderFactory.create(provider, provider_config, logger=logger)
        
        # Determine what to delete
        to_delete = []
        
        if prefix:
            # Delete by prefix
            provider_config["prefix"] = prefix
            cloud_provider.prefix = prefix  # Update provider prefix
            objects = list(cloud_provider._list_objects())
            to_delete = [obj.key for obj in objects]
        
        elif pattern:
            # Delete by pattern
            objects = list(cloud_provider._list_objects())
            to_delete = [obj.key for obj in objects if fnmatch.fnmatch(obj.key, pattern)]
        
        else:
            # Delete specific keys
            to_delete = list(keys)
        
        if not to_delete:
            click.echo("No objects to delete")
            return
        
        # Confirm
        if not yes and not dry_run:
            click.echo(f"\nAbout to delete {len(to_delete)} object(s):")
            for key in to_delete[:10]:
                click.echo(f"  - {key}")
            if len(to_delete) > 10:
                click.echo(f"  ... and {len(to_delete) - 10} more")
            
            if not click.confirm("\nProceed with deletion?"):
                click.echo("Cancelled")
                return
        
        # Delete objects
        deleted = 0
        failed = 0
        
        for key in to_delete:
            try:
                if dry_run:
                    click.echo(f"[DRY-RUN] Would delete: {key}")
                    deleted += 1
                else:
                    if cloud_provider._delete_object(key):
                        click.echo(f"✓ Deleted: {key}")
                        deleted += 1
                    else:
                        click.secho(f"✗ Failed: {key}", fg="red")
                        failed += 1
            except Exception as e:
                click.secho(f"✗ Error deleting {key}: {e}", fg="red", err=True)
                failed += 1
        
        # Summary
        click.echo("-" * 60)
        click.secho(f"✓ Deleted: {deleted}", fg="green")
        if failed:
            click.secho(f"✗ Failed: {failed}", fg="red")
    
    except Exception as e:
        click.secho(f"✗ Error: {e}", fg="red", err=True)
        raise click.Abort()


# ============================================================================
# INFO COMMAND
# ============================================================================

@cloud.command(name="info")
@click.argument("key", required=False)
@click.option("--profile", "-p", help="Config profile name")
@click.option("--config", "-c", type=click.Path(exists=True), help="Path to config file")
@click.option("--provider", type=click.Choice(['aws', 's3', 'gcs', 'google', 'azure', 'digitalocean', 'do']),
              help="Cloud provider")
@click.option("--region", "-r", help="Cloud region")
@click.option("--bucket", "-b", help="Bucket/container name to get info (if no KEY specified)")
@click.option("--format", "output_format", type=click.Choice(['text', 'json']),
              default='text', help="Output format [default: text]")
# Provider credentials
@click.option("--access-key", help="AWS/DigitalOcean access key")
@click.option("--secret-key", help="AWS/DigitalOcean secret key")
@click.option("--project-id", help="Google Cloud project ID")
@click.option("--credentials-path", type=click.Path(exists=True), help="Path to GCS credentials JSON")
@click.option("--account-name", help="Azure storage account name")
@click.option("--account-key", help="Azure storage account key")
@click.option("--connection-string", help="Azure connection string")
@click.option("--container", help="Azure container name (alias for --bucket)")
def info_command(
    key: Optional[str],
    profile: Optional[str],
    config: Optional[str],
    provider: Optional[str],
    region: Optional[str],
    bucket: Optional[str],
    output_format: str,
    access_key: Optional[str],
    secret_key: Optional[str],
    project_id: Optional[str],
    credentials_path: Optional[str],
    account_name: Optional[str],
    account_key: Optional[str],
    connection_string: Optional[str],
    container: Optional[str]
) -> None:
    """
    Get information about bucket or specific object.
    
    KEY: Optional object key to get info (if omitted, shows bucket info)
    
    Examples:
    
      # Get bucket info
      tools cloud info --provider aws --bucket my-bucket --region us-east-1
      
      # Get object info
      tools cloud info backups/data.zip --provider aws --bucket my-bucket
      
      # JSON output
      tools cloud info file.txt --profile production --format json
    """
    from tools.cloud.factory import CloudProviderFactory
    import json as json_module
    
    logger = setup_sync_logger("ERROR")
    
    try:
        # Load from profile if specified
        if profile:
            config_manager = ConfigManager(config_file=config)
            profile_obj = config_manager.get_profile(profile)
            if not profile_obj:
                click.secho(f"✗ Profile '{profile}' not found", fg="red", err=True)
                raise click.Abort()
            
            provider = provider or profile_obj.get('provider')
            region = region or profile_obj.get('region')
            bucket = bucket or profile_obj.get('bucket') or profile_obj.get('container')
            access_key = access_key or profile_obj.get('access_key')
            secret_key = secret_key or profile_obj.get('secret_key')
            project_id = project_id or profile_obj.get('project_id')
            credentials_path = credentials_path or profile_obj.get('credentials_path')
            account_name = account_name or profile_obj.get('account_name')
            account_key = account_key or profile_obj.get('account_key')
            connection_string = connection_string or profile_obj.get('connection_string')
        
        # Validate required parameters
        if not bucket and not container:
            click.secho("✗ --bucket (or --container) is required", fg="red", err=True)
            raise click.Abort()
        
        bucket = bucket or container
        
        # Build provider config
        provider_config = {
            "bucket": bucket,
            "dest": "/tmp",  # Dummy dest
            "prefix": "",
            "dry_run": True,
            "logger": logger
        }
        
        # Add provider-specific credentials
        if provider in ["aws", "s3", "digitalocean", "do"]:
            if region:
                provider_config["region"] = region
            if access_key:
                provider_config["access_key"] = access_key
            if secret_key:
                provider_config["secret_key"] = secret_key
        elif provider in ["gcs", "google"]:
            if project_id:
                provider_config["project_id"] = project_id
            if credentials_path:
                provider_config["credentials_path"] = credentials_path
        elif provider in ["azure"]:
            if account_name:
                provider_config["account_name"] = account_name
            if account_key:
                provider_config["account_key"] = account_key
            if connection_string:
                provider_config["connection_string"] = connection_string
        
        # Create provider instance
        cloud_provider = CloudProviderFactory.create(provider, provider_config, logger=logger)
        
        if key:
            # Get object info
            metadata = cloud_provider._get_object_metadata(key)
            
            if not metadata:
                click.secho(f"✗ Object not found: {key}", fg="red", err=True)
                raise click.Abort()
            
            if output_format == 'json':
                click.echo(json_module.dumps(metadata, indent=2, default=str))
            else:
                click.echo(f"\nObject: {key}")
                click.echo("=" * 60)
                click.echo(f"Size:         {metadata.get('size_bytes', 0):,} bytes")
                size_mb = metadata.get('size_bytes', 0) / (1024**2)
                click.echo(f"              ({size_mb:.2f} MB)")
                if metadata.get('modified'):
                    click.echo(f"Modified:     {metadata['modified']}")
                if metadata.get('etag'):
                    click.echo(f"ETag:         {metadata['etag']}")
                if metadata.get('content_type'):
                    click.echo(f"Content-Type: {metadata['content_type']}")
                if metadata.get('storage_class'):
                    click.echo(f"Storage:      {metadata['storage_class']}")
                click.echo("=" * 60)
        else:
            # Get bucket info
            objects = list(cloud_provider._list_objects())
            
            total_size = sum(obj.size_bytes for obj in objects)
            total_gb = total_size / (1024**3)
            
            info = {
                "provider": provider,
                "bucket": bucket,
                "region": region or "default",
                "object_count": len(objects),
                "total_size_bytes": total_size,
                "total_size_gb": round(total_gb, 2)
            }
            
            if output_format == 'json':
                click.echo(json_module.dumps(info, indent=2))
            else:
                click.echo(f"\nBucket: {bucket}")
                click.echo("=" * 60)
                click.echo(f"Provider:     {provider}")
                if region:
                    click.echo(f"Region:       {region}")
                click.echo(f"Objects:      {len(objects):,}")
                click.echo(f"Total size:   {total_size:,} bytes ({total_gb:.2f} GB)")
                click.echo("=" * 60)
    
    except Exception as e:
        click.secho(f"✗ Error: {e}", fg="red", err=True)
        raise click.Abort()


# ============================================================================
# COPY COMMAND
# ============================================================================

@cloud.command(name="copy")
@click.argument("source_key")
@click.argument("dest_key")
@click.option("--source-profile", help="Source config profile")
@click.option("--dest-profile", help="Destination config profile")
@click.option("--config", "-c", type=click.Path(exists=True), help="Path to config file")
@click.option("--source-provider", type=click.Choice(['aws', 's3', 'gcs', 'google', 'azure', 'digitalocean', 'do']),
              help="Source cloud provider")
@click.option("--dest-provider", type=click.Choice(['aws', 's3', 'gcs', 'google', 'azure', 'digitalocean', 'do']),
              help="Destination cloud provider")
@click.option("--source-bucket", "-sb", help="Source bucket/container")
@click.option("--dest-bucket", "-db", help="Destination bucket/container")
@click.option("--source-region", help="Source region")
@click.option("--dest-region", help="Destination region")
@click.option("--dry-run", is_flag=True, help="Simulate without copying")
# Source credentials
@click.option("--source-access-key", help="Source AWS/DO access key")
@click.option("--source-secret-key", help="Source AWS/DO secret key")
@click.option("--source-project-id", help="Source GCS project ID")
@click.option("--source-credentials-path", type=click.Path(exists=True), help="Source GCS credentials")
@click.option("--source-account-name", help="Source Azure account name")
@click.option("--source-account-key", help="Source Azure account key")
# Dest credentials
@click.option("--dest-access-key", help="Dest AWS/DO access key")
@click.option("--dest-secret-key", help="Dest AWS/DO secret key")
@click.option("--dest-project-id", help="Dest GCS project ID")
@click.option("--dest-credentials-path", type=click.Path(exists=True), help="Dest GCS credentials")
@click.option("--dest-account-name", help="Dest Azure account name")
@click.option("--dest-account-key", help="Dest Azure account key")
def copy_command(
    source_key: str,
    dest_key: str,
    source_profile: Optional[str],
    dest_profile: Optional[str],
    config: Optional[str],
    source_provider: Optional[str],
    dest_provider: Optional[str],
    source_bucket: Optional[str],
    dest_bucket: Optional[str],
    source_region: Optional[str],
    dest_region: Optional[str],
    dry_run: bool,
    source_access_key: Optional[str],
    source_secret_key: Optional[str],
    source_project_id: Optional[str],
    source_credentials_path: Optional[str],
    source_account_name: Optional[str],
    source_account_key: Optional[str],
    dest_access_key: Optional[str],
    dest_secret_key: Optional[str],
    dest_project_id: Optional[str],
    dest_credentials_path: Optional[str],
    dest_account_name: Optional[str],
    dest_account_key: Optional[str]
) -> None:
    """
    Copy object between buckets or providers.
    
    SOURCE_KEY: Source object key
    DEST_KEY: Destination object key
    
    Examples:
    
      # Copy within same bucket
      tools cloud copy file.txt backup/file.txt --provider aws --bucket my-bucket
      
      # Copy between buckets (same provider)
      tools cloud copy file.txt file.txt --source-bucket bucket1 --dest-bucket bucket2 \
                       --provider aws --region us-east-1
      
      # Copy between providers using profiles
      tools cloud copy data.zip data.zip --source-profile aws_prod --dest-profile gcs_backup
      
      # Copy between providers (manual credentials)
      tools cloud copy file.txt file.txt \
                       --source-provider aws --source-bucket s3-bucket \
                       --dest-provider gcs --dest-bucket gcs-bucket \
                       --source-region us-east-1 --dest-project-id my-project
    """
    from tools.cloud.factory import CloudProviderFactory
    from pathlib import Path
    import tempfile
    
    logger = setup_sync_logger("INFO")
    
    try:
        # Load source profile
        if source_profile:
            config_manager = ConfigManager(config_file=config)
            profile_obj = config_manager.get_profile(source_profile)
            if not profile_obj:
                click.secho(f"✗ Source profile '{source_profile}' not found", fg="red", err=True)
                raise click.Abort()
            
            source_provider = source_provider or profile_obj.get('provider')
            source_bucket = source_bucket or profile_obj.get('bucket')
            source_region = source_region or profile_obj.get('region')
            source_access_key = source_access_key or profile_obj.get('access_key')
            source_secret_key = source_secret_key or profile_obj.get('secret_key')
            source_project_id = source_project_id or profile_obj.get('project_id')
            source_credentials_path = source_credentials_path or profile_obj.get('credentials_path')
            source_account_name = source_account_name or profile_obj.get('account_name')
            source_account_key = source_account_key or profile_obj.get('account_key')
        
        # Load dest profile
        if dest_profile:
            config_manager = ConfigManager(config_file=config)
            profile_obj = config_manager.get_profile(dest_profile)
            if not profile_obj:
                click.secho(f"✗ Dest profile '{dest_profile}' not found", fg="red", err=True)
                raise click.Abort()
            
            dest_provider = dest_provider or profile_obj.get('provider')
            dest_bucket = dest_bucket or profile_obj.get('bucket')
            dest_region = dest_region or profile_obj.get('region')
            dest_access_key = dest_access_key or profile_obj.get('access_key')
            dest_secret_key = dest_secret_key or profile_obj.get('secret_key')
            dest_project_id = dest_project_id or profile_obj.get('project_id')
            dest_credentials_path = dest_credentials_path or profile_obj.get('credentials_path')
            dest_account_name = dest_account_name or profile_obj.get('account_name')
            dest_account_key = dest_account_key or profile_obj.get('account_key')
        
        # Validate required parameters
        if not source_bucket:
            click.secho("✗ Source bucket is required", fg="red", err=True)
            raise click.Abort()
        
        # Default dest bucket to source bucket if not specified
        dest_bucket = dest_bucket or source_bucket
        dest_provider = dest_provider or source_provider
        dest_region = dest_region or source_region
        
        # Build source provider config
        source_config = {
            "bucket": source_bucket,
            "dest": "/tmp",
            "prefix": "",
            "dry_run": dry_run,
            "logger": logger
        }
        
        if source_provider in ["aws", "s3", "digitalocean", "do"]:
            if source_region:
                source_config["region"] = source_region
            if source_access_key:
                source_config["access_key"] = source_access_key
            if source_secret_key:
                source_config["secret_key"] = source_secret_key
        elif source_provider in ["gcs", "google"]:
            if source_project_id:
                source_config["project_id"] = source_project_id
            if source_credentials_path:
                source_config["credentials_path"] = source_credentials_path
        elif source_provider in ["azure"]:
            if source_account_name:
                source_config["account_name"] = source_account_name
            if source_account_key:
                source_config["account_key"] = source_account_key
        
        # Build dest provider config
        dest_config = {
            "bucket": dest_bucket,
            "dest": "/tmp",
            "prefix": "",
            "dry_run": dry_run,
            "logger": logger
        }
        
        if dest_provider in ["aws", "s3", "digitalocean", "do"]:
            if dest_region:
                dest_config["region"] = dest_region
            if dest_access_key:
                dest_config["access_key"] = dest_access_key
            if dest_secret_key:
                dest_config["secret_key"] = dest_secret_key
        elif dest_provider in ["gcs", "google"]:
            if dest_project_id:
                dest_config["project_id"] = dest_project_id
            if dest_credentials_path:
                dest_config["credentials_path"] = dest_credentials_path
        elif dest_provider in ["azure"]:
            if dest_account_name:
                dest_config["account_name"] = dest_account_name
            if dest_account_key:
                dest_config["account_key"] = dest_account_key
        
        # Create provider instances
        source_cloud = CloudProviderFactory.create(source_provider, source_config, logger=logger)
        dest_cloud = CloudProviderFactory.create(dest_provider, dest_config, logger=logger)
        
        # Get source object metadata
        metadata = source_cloud._get_object_metadata(source_key)
        if not metadata:
            click.secho(f"✗ Source object not found: {source_key}", fg="red", err=True)
            raise click.Abort()
        
        click.echo(f"\nCopying:")
        click.echo(f"  From: {source_provider}://{source_bucket}/{source_key}")
        click.echo(f"  To:   {dest_provider}://{dest_bucket}/{dest_key}")
        click.echo(f"  Size: {metadata.get('size_bytes', 0):,} bytes")
        
        if dry_run:
            click.echo("[DRY-RUN] Would copy object")
            return
        
        # Download to temp file
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)
        
        try:
            # Create CloudObject for download
            from tools.cloud.providers import CloudObject
            source_obj = CloudObject(
                key=source_key,
                size_bytes=metadata.get('size_bytes', 0),
                modified=metadata.get('modified'),
                etag=metadata.get('etag')
            )
            
            # Download
            click.echo("Downloading from source...")
            if not source_cloud._download_object(source_obj, tmp_path):
                click.secho("✗ Download failed", fg="red", err=True)
                raise click.Abort()
            
            # Upload
            click.echo("Uploading to destination...")
            if not dest_cloud._upload_object(tmp_path, dest_key):
                click.secho("✗ Upload failed", fg="red", err=True)
                raise click.Abort()
            
            click.secho("✓ Copy completed successfully", fg="green")
        
        finally:
            # Clean up temp file
            if tmp_path.exists():
                tmp_path.unlink()
    
    except Exception as e:
        click.secho(f"✗ Error: {e}", fg="red", err=True)
        raise click.Abort()


# ============================================================================
# CREDENTIALS COMMANDS
# ============================================================================

@cloud.group(name="credentials")
def credentials() -> None:
    """Manage stored cloud credentials securely."""
    pass


@credentials.command(name="set")
@click.argument("name")
@click.option("--provider", type=click.Choice(['aws', 's3', 'gcs', 'google', 'azure', 'digitalocean', 'do']),
              required=True, help="Cloud provider")
@click.option("--region", help="Default region")
@click.option("--description", help="Description of this credential")
# AWS/DigitalOcean
@click.option("--access-key", help="AWS/DigitalOcean access key")
@click.option("--secret-key", help="AWS/DigitalOcean secret key (will be encrypted)")
# GCS
@click.option("--project-id", help="Google Cloud project ID")
@click.option("--credentials-path", type=click.Path(exists=True), help="Path to GCS credentials JSON")
# Azure
@click.option("--account-name", help="Azure storage account name")
@click.option("--account-key", help="Azure storage account key (will be encrypted)")
@click.option("--connection-string", help="Azure connection string (will be encrypted)")
def credentials_set_command(
    name: str,
    provider: str,
    region: Optional[str],
    description: Optional[str],
    access_key: Optional[str],
    secret_key: Optional[str],
    project_id: Optional[str],
    credentials_path: Optional[str],
    account_name: Optional[str],
    account_key: Optional[str],
    connection_string: Optional[str]
) -> None:
    """
    Store cloud credentials securely.
    
    NAME: Unique name for this credential set
    
    Credentials are encrypted and stored securely using the system keyring
    or encrypted file storage.
    
    Examples:
    
      # Store AWS credentials
      tools cloud credentials set my-aws --provider aws --region us-east-1 \
                                  --access-key AKIAIOSFODNN7EXAMPLE \
                                  --secret-key wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
      
      # Store GCS credentials
      tools cloud credentials set my-gcs --provider gcs --project-id my-project \
                                  --credentials-path /path/to/service-account.json
      
      # Store Azure credentials
      tools cloud credentials set my-azure --provider azure \
                                   --account-name myaccount \
                                   --account-key <key>
    """
    from tools.cloud.credentials import CredentialManager, StoredCredential
    
    try:
        manager = CredentialManager()
        
        # Create credential object
        credential = StoredCredential(
            name=name,
            provider=provider,
            region=region,
            access_key=access_key,
            secret_key=secret_key,
            project_id=project_id,
            credentials_path=credentials_path,
            account_name=account_name,
            account_key=account_key,
            connection_string=connection_string,
            description=description
        )
        
        # Validate at least some credentials provided
        has_credentials = (
            access_key or secret_key or
            project_id or credentials_path or
            account_name or account_key or connection_string
        )
        
        if not has_credentials:
            click.secho("✗ No credentials provided", fg="red", err=True)
            click.echo("Provide at least one credential option for the provider")
            raise click.Abort()
        
        # Store
        manager.set_credential(credential)
        click.secho(f"✓ Credentials '{name}' stored securely", fg="green")
        
        # Show what was stored
        click.echo(f"\nStored:")
        click.echo(f"  Name:        {name}")
        click.echo(f"  Provider:    {provider}")
        if region:
            click.echo(f"  Region:      {region}")
        if description:
            click.echo(f"  Description: {description}")
        
        # Show which sensitive fields were encrypted
        sensitive_fields = []
        if secret_key:
            sensitive_fields.append("secret_key")
        if account_key:
            sensitive_fields.append("account_key")
        if connection_string:
            sensitive_fields.append("connection_string")
        
        if sensitive_fields:
            click.echo(f"\nEncrypted fields: {', '.join(sensitive_fields)}")
    
    except Exception as e:
        click.secho(f"✗ Error storing credentials: {e}", fg="red", err=True)
        raise click.Abort()


@credentials.command(name="list")
@click.option("--format", "output_format", type=click.Choice(['table', 'json']),
              default='table', help="Output format [default: table]")
def credentials_list_command(output_format: str) -> None:
    """
    List all stored credentials.
    
    Examples:
    
      # List in table format
      tools cloud credentials list
      
      # List in JSON format
      tools cloud credentials list --format json
    """
    from tools.cloud.credentials import CredentialManager
    import json as json_module
    
    try:
        manager = CredentialManager()
        names = manager.list_credentials()
        
        if not names:
            click.echo("No credentials stored")
            return
        
        # Load details for each
        credentials = []
        for name in names:
            cred = manager.get_credential(name)
            if cred:
                credentials.append(cred)
        
        if output_format == 'json':
            # Output as JSON (exclude sensitive fields)
            data = []
            for cred in credentials:
                cred_dict = {
                    'name': cred.name,
                    'provider': cred.provider,
                    'region': cred.region,
                    'description': cred.description,
                }
                # Add non-sensitive fields
                if cred.access_key:
                    cred_dict['access_key'] = cred.access_key
                if cred.project_id:
                    cred_dict['project_id'] = cred.project_id
                if cred.account_name:
                    cred_dict['account_name'] = cred.account_name
                data.append(cred_dict)
            
            click.echo(json_module.dumps(data, indent=2))
        else:
            # Table format
            click.echo(f"\n{len(credentials)} stored credential(s)\n")
            click.echo(f"{'NAME':<20} {'PROVIDER':<12} {'REGION':<15} {'DESCRIPTION':<30}")
            click.echo("-" * 80)
            
            for cred in credentials:
                region = cred.region or "-"
                desc = cred.description or "-"
                click.echo(f"{cred.name:<20} {cred.provider:<12} {region:<15} {desc:<30}")
    
    except Exception as e:
        click.secho(f"✗ Error listing credentials: {e}", fg="red", err=True)
        raise click.Abort()


@credentials.command(name="get")
@click.argument("name")
@click.option("--show-secrets", is_flag=True, help="Show encrypted secret values")
def credentials_get_command(name: str, show_secrets: bool) -> None:
    """
    Get details of a stored credential.
    
    NAME: Credential name
    
    Examples:
    
      # Get credential details
      tools cloud credentials get my-aws
      
      # Show secret values
      tools cloud credentials get my-aws --show-secrets
    """
    from tools.cloud.credentials import CredentialManager
    
    try:
        manager = CredentialManager()
        cred = manager.get_credential(name)
        
        if not cred:
            click.secho(f"✗ Credential '{name}' not found", fg="red", err=True)
            raise click.Abort()
        
        click.echo(f"\nCredential: {name}")
        click.echo("=" * 60)
        click.echo(f"Provider:     {cred.provider}")
        if cred.region:
            click.echo(f"Region:       {cred.region}")
        if cred.description:
            click.echo(f"Description:  {cred.description}")
        
        # AWS/DigitalOcean
        if cred.access_key:
            click.echo(f"Access Key:   {cred.access_key}")
        if cred.secret_key:
            if show_secrets:
                click.echo(f"Secret Key:   {cred.secret_key}")
            else:
                click.echo(f"Secret Key:   {'*' * 20} (use --show-secrets)")
        
        # GCS
        if cred.project_id:
            click.echo(f"Project ID:   {cred.project_id}")
        if cred.credentials_path:
            click.echo(f"Creds Path:   {cred.credentials_path}")
        
        # Azure
        if cred.account_name:
            click.echo(f"Account Name: {cred.account_name}")
        if cred.account_key:
            if show_secrets:
                click.echo(f"Account Key:  {cred.account_key}")
            else:
                click.echo(f"Account Key:  {'*' * 20} (use --show-secrets)")
        if cred.connection_string:
            if show_secrets:
                click.echo(f"Connection:   {cred.connection_string}")
            else:
                click.echo(f"Connection:   {'*' * 20} (use --show-secrets)")
        
        click.echo("=" * 60)
    
    except Exception as e:
        click.secho(f"✗ Error: {e}", fg="red", err=True)
        raise click.Abort()


@credentials.command(name="delete")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def credentials_delete_command(name: str, yes: bool) -> None:
    """
    Delete a stored credential.
    
    NAME: Credential name to delete
    
    Examples:
    
      # Delete with confirmation
      tools cloud credentials delete my-aws
      
      # Delete without confirmation
      tools cloud credentials delete my-aws -y
    """
    from tools.cloud.credentials import CredentialManager
    
    try:
        manager = CredentialManager()
        
        # Check if exists
        cred = manager.get_credential(name)
        if not cred:
            click.secho(f"✗ Credential '{name}' not found", fg="red", err=True)
            raise click.Abort()
        
        # Confirm
        if not yes:
            if not click.confirm(f"Delete credential '{name}' ({cred.provider})?"):
                click.echo("Cancelled")
                return
        
        # Delete
        if manager.delete_credential(name):
            click.secho(f"✓ Deleted credential '{name}'", fg="green")
        else:
            click.secho(f"✗ Failed to delete '{name}'", fg="red", err=True)
    
    except Exception as e:
        click.secho(f"✗ Error: {e}", fg="red", err=True)
        raise click.Abort()


@credentials.command(name="test")
@click.argument("name")
def credentials_test_command(name: str) -> None:
    """
    Test if stored credentials are valid.
    
    NAME: Credential name to test
    
    Examples:
    
      # Test credentials
      tools cloud credentials test my-aws
    """
    from tools.cloud.credentials import CredentialManager
    
    try:
        manager = CredentialManager()
        
        # Get credential
        cred = manager.get_credential(name)
        if not cred:
            click.secho(f"✗ Credential '{name}' not found", fg="red", err=True)
            raise click.Abort()
        
        click.echo(f"Testing credential '{name}' ({cred.provider})...")
        
        # Test
        if manager.test_credential(name):
            click.secho(f"✓ Credential '{name}' is valid", fg="green")
        else:
            click.secho(f"✗ Credential '{name}' validation failed", fg="red", err=True)
    
    except Exception as e:
        click.secho(f"✗ Error: {e}", fg="red", err=True)
        raise click.Abort()