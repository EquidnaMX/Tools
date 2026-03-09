#!/usr/bin/env python3
"""Examples for the current tools.cloud API.

These examples avoid legacy aliases/modules and demonstrate:
- YAML profile handling via ConfigManager/ConfigProfile
- Provider detection and requirements via CloudProviderFactory
- Secure credentials via CredentialManager
- Local cache inspection via SyncCache
- DigitalOcean sync setup (without forcing network calls)
"""

from __future__ import annotations

import os
from pathlib import Path

from tools.cloud.cache import SyncCache
from tools.cloud.config_manager import ConfigManager
from tools.cloud.credentials import CredentialManager, StoredCredential
from tools.cloud.factory import CloudProviderFactory
from tools.cloud.sync import DigitalOceanSync


def example_config_profiles() -> None:
    """Load and inspect profiles from ~/.tools/cloud_profiles.yml."""
    manager = ConfigManager()
    loaded = manager.load_config()

    print("=" * 70)
    print("EXAMPLE 1: Profile Loading")
    print("=" * 70)

    if not loaded:
        print("No profile file found in default paths.")
        print("Create one at ~/.tools/cloud_profiles.yml")
        return

    print(f"Loaded file: {manager.get_loaded_file()}")
    profiles = manager.list_profiles()
    print(f"Profiles: {profiles}")

    if profiles:
        first = manager.get_profile(profiles[0])
        if first is not None:
            print(f"First profile ({first.name}) -> CLI args:")
            print(" ".join(first.to_cli_args()))


def example_provider_factory() -> None:
    """Show provider auto-detection and credential requirements."""
    print("\n" + "=" * 70)
    print("EXAMPLE 2: Provider Factory")
    print("=" * 70)

    detected = CloudProviderFactory.detect_provider_from_config(
        {
            "provider": "s3",
            "bucket": "my-bucket",
            "region": "us-east-1",
            "dest": str(Path.home() / "backups"),
        }
    )
    print(f"Detected provider: {detected}")

    requirements = CloudProviderFactory.get_credential_requirements("s3")
    print("Credential environment variables for s3:")
    for key, desc in requirements.items():
        print(f"- {key}: {desc}")


def example_credentials() -> None:
    """Store and retrieve credentials through CredentialManager."""
    print("\n" + "=" * 70)
    print("EXAMPLE 3: Credential Manager")
    print("=" * 70)

    manager = CredentialManager()
    name = "example-digitalocean"

    manager.set_credential(
        StoredCredential(
            name=name,
            provider="digitalocean",
            region="sfo3",
            access_key=os.getenv("DO_SPACES_KEY", "example-key"),
            secret_key=os.getenv("DO_SPACES_SECRET", "example-secret"),
            description="Example credential created by examples/cloud.py",
        )
    )

    restored = manager.get_credential(name)
    if restored is None:
        print("Credential was not found after storing it.")
        return

    print(f"Stored credential name: {restored.name}")
    print(f"Provider: {restored.provider}")
    print(f"Region: {restored.region}")


def example_cache_stats() -> None:
    """Read local sync cache stats from default SQLite cache."""
    print("\n" + "=" * 70)
    print("EXAMPLE 4: Sync Cache")
    print("=" * 70)

    cache = SyncCache()
    stats = cache.get_stats()

    print(f"Total cached files: {stats.get('total_files', 0)}")
    print(f"Total cached size bytes: {stats.get('total_size_bytes', 0)}")
    print(f"Cache path: {cache.cache_path}")


def example_digitalocean_sync_setup() -> None:
    """Build a DigitalOceanSync instance and validate parameters.

    This example does not execute sync() to avoid accidental network calls.
    """
    print("\n" + "=" * 70)
    print("EXAMPLE 5: DigitalOcean Sync Setup")
    print("=" * 70)

    syncer = DigitalOceanSync(
        region="sfo3",
        bucket="my-space",
        dest=str(Path.home() / "Downloads" / "do-sync"),
        prefix="backups/",
        access_key=os.getenv("AWS_ACCESS_KEY_ID"),
        secret_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        workers=8,
        dry_run=True,
        exclude=["*.tmp", "*.log"],
    )

    print(f"Region: {syncer.region}")
    print(f"Bucket: {syncer.bucket}")
    print(f"Destination: {syncer.dest_root}")
    print(f"Dry run: {syncer.dry_run}")
    print("Call syncer.sync() when credentials and bucket are ready.")


def main() -> None:
    """Run all examples."""
    example_config_profiles()
    example_provider_factory()
    example_credentials()
    example_cache_stats()
    example_digitalocean_sync_setup()


if __name__ == "__main__":
    main()
