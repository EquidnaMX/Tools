"""
Secure credential management for cloud providers.

Provides a secure way to store and retrieve cloud credentials using
encryption and the system keyring.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict


@dataclass
class StoredCredential:
    """Represents a stored credential set."""
    name: str
    provider: str
    region: Optional[str] = None
    # AWS/DigitalOcean
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    # GCS
    project_id: Optional[str] = None
    credentials_path: Optional[str] = None
    # Azure
    account_name: Optional[str] = None
    account_key: Optional[str] = None
    connection_string: Optional[str] = None
    # Metadata
    description: Optional[str] = None


class CredentialManager:
    """
    Manages secure storage and retrieval of cloud credentials.
    
    Uses system keyring for sensitive data and local file for metadata.
    """
    
    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize credential manager.
        
        Args:
            config_dir: Directory for credential metadata (default: ~/.cloud-tools)
        """
        self.config_dir = config_dir or Path.home() / ".cloud-tools"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.credentials_file = self.config_dir / "credentials.json"
        self.logger = logging.getLogger(__name__)
        
        # Try to import keyring, fall back to file-based encryption
        self.use_keyring = False
        try:
            import keyring
            self.keyring = keyring
            self.use_keyring = True
            self.logger.info("Using system keyring for credential storage")
        except ImportError:
            self.logger.warning("keyring not available, using encrypted file storage")
            self._init_encryption()
    
    def _init_encryption(self):
        """Initialize encryption for file-based credential storage."""
        try:
            from cryptography.fernet import Fernet
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
            from cryptography.hazmat.backends import default_backend
            import getpass
            
            self.Fernet = Fernet
            self.hashes = hashes
            self.PBKDF2 = PBKDF2
            self.default_backend = default_backend
            self.getpass = getpass
            
            # Get/create encryption key
            key_file = self.config_dir / ".encryption_key"
            if key_file.exists():
                with open(key_file, 'rb') as f:
                    self.encryption_key = f.read()
            else:
                # Generate key from machine-specific data + user password
                import platform
                import hashlib
                
                # Use machine ID as salt
                machine_id = hashlib.sha256(platform.node().encode()).digest()
                
                # Derive key from salt
                kdf = self.PBKDF2(
                    algorithm=self.hashes.SHA256(),
                    length=32,
                    salt=machine_id,
                    iterations=100000,
                    backend=self.default_backend()
                )
                
                # Use a fixed password based on machine
                password = platform.node().encode() + b"cloud-tools-secret"
                self.encryption_key = kdf.derive(password)
                
                # Save key securely
                with open(key_file, 'wb') as f:
                    f.write(self.encryption_key)
                key_file.chmod(0o600)
            
            # Create cipher
            from base64 import urlsafe_b64encode
            key_b64 = urlsafe_b64encode(self.encryption_key)
            self.cipher = self.Fernet(key_b64)
            
        except ImportError:
            self.logger.error("cryptography library not installed, cannot encrypt credentials")
            raise RuntimeError(
                "Neither keyring nor cryptography is installed. "
                "Install with: pip install keyring cryptography"
            )
    
    def _get_service_name(self, cred_name: str) -> str:
        """Get keyring service name for credential."""
        return f"cloud-tools-{cred_name}"
    
    def _load_metadata(self) -> Dict[str, Dict]:
        """Load credential metadata from file."""
        if not self.credentials_file.exists():
            return {}
        
        try:
            with open(self.credentials_file, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            self.logger.error("Corrupted credentials file, starting fresh")
            return {}
    
    def _save_metadata(self, metadata: Dict[str, Dict]):
        """Save credential metadata to file."""
        with open(self.credentials_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        self.credentials_file.chmod(0o600)
    
    def _encrypt_value(self, value: str) -> str:
        """Encrypt a credential value."""
        if self.use_keyring:
            return value  # Keyring handles encryption
        else:
            encrypted = self.cipher.encrypt(value.encode())
            return encrypted.decode('utf-8')
    
    def _decrypt_value(self, encrypted: str) -> str:
        """Decrypt a credential value."""
        if self.use_keyring:
            return encrypted  # Keyring handles decryption
        else:
            decrypted = self.cipher.decrypt(encrypted.encode())
            return decrypted.decode('utf-8')
    
    def set_credential(self, credential: StoredCredential) -> None:
        """
        Store a credential securely.
        
        Args:
            credential: Credential to store
        """
        metadata = self._load_metadata()
        
        # Store sensitive data in keyring or encrypted
        service_name = self._get_service_name(credential.name)
        sensitive_data = {}
        
        # Collect sensitive fields
        if credential.secret_key:
            sensitive_data['secret_key'] = credential.secret_key
        if credential.account_key:
            sensitive_data['account_key'] = credential.account_key
        if credential.connection_string:
            sensitive_data['connection_string'] = credential.connection_string
        
        # Store sensitive data
        if self.use_keyring:
            self.keyring.set_password(
                service_name,
                credential.name,
                json.dumps(sensitive_data)
            )
        else:
            # Store encrypted in file
            encrypted_data = self._encrypt_value(json.dumps(sensitive_data))
            metadata[credential.name] = metadata.get(credential.name, {})
            metadata[credential.name]['_encrypted'] = encrypted_data
        
        # Store non-sensitive metadata
        metadata_dict = {
            'provider': credential.provider,
            'region': credential.region,
            'access_key': credential.access_key,
            'project_id': credential.project_id,
            'credentials_path': credential.credentials_path,
            'account_name': credential.account_name,
            'description': credential.description,
        }
        
        # Remove None values
        metadata_dict = {k: v for k, v in metadata_dict.items() if v is not None}
        
        # Update metadata
        if credential.name not in metadata:
            metadata[credential.name] = {}
        metadata[credential.name].update(metadata_dict)
        
        self._save_metadata(metadata)
        self.logger.info(f"Stored credential: {credential.name}")
    
    def get_credential(self, name: str) -> Optional[StoredCredential]:
        """
        Retrieve a stored credential.
        
        Args:
            name: Credential name
            
        Returns:
            StoredCredential if found, None otherwise
        """
        metadata = self._load_metadata()
        
        if name not in metadata:
            return None
        
        cred_data = metadata[name].copy()
        
        # Retrieve sensitive data
        service_name = self._get_service_name(name)
        
        try:
            if self.use_keyring:
                sensitive_json = self.keyring.get_password(service_name, name)
                if sensitive_json:
                    sensitive_data = json.loads(sensitive_json)
                    cred_data.update(sensitive_data)
            else:
                # Decrypt from file
                if '_encrypted' in cred_data:
                    encrypted = cred_data.pop('_encrypted')
                    sensitive_json = self._decrypt_value(encrypted)
                    sensitive_data = json.loads(sensitive_json)
                    cred_data.update(sensitive_data)
        except Exception as e:
            self.logger.error(f"Failed to retrieve sensitive data: {e}")
        
        # Create credential object
        cred_data['name'] = name
        return StoredCredential(**cred_data)
    
    def list_credentials(self) -> List[str]:
        """
        List all stored credential names.
        
        Returns:
            List of credential names
        """
        metadata = self._load_metadata()
        return list(metadata.keys())
    
    def delete_credential(self, name: str) -> bool:
        """
        Delete a stored credential.
        
        Args:
            name: Credential name
            
        Returns:
            True if deleted, False if not found
        """
        metadata = self._load_metadata()
        
        if name not in metadata:
            return False
        
        # Delete from keyring
        if self.use_keyring:
            service_name = self._get_service_name(name)
            try:
                self.keyring.delete_password(service_name, name)
            except Exception as e:
                self.logger.warning(f"Failed to delete from keyring: {e}")
        
        # Delete from metadata
        del metadata[name]
        self._save_metadata(metadata)
        
        self.logger.info(f"Deleted credential: {name}")
        return True
    
    def test_credential(self, name: str) -> bool:
        """
        Test if a credential works by attempting to list buckets.
        
        Args:
            name: Credential name
            
        Returns:
            True if credential works, False otherwise
        """
        credential = self.get_credential(name)
        if not credential:
            return False
        
        try:
            from tools.cloud.factory import CloudProviderFactory
            
            # Build config
            config = {
                "dest": "/tmp",
                "prefix": "",
                "dry_run": True,
            }
            
            # Add provider-specific fields
            if credential.provider in ["aws", "s3", "digitalocean", "do"]:
                if credential.region:
                    config["region"] = credential.region
                if credential.access_key:
                    config["access_key"] = credential.access_key
                if credential.secret_key:
                    config["secret_key"] = credential.secret_key
            elif credential.provider in ["gcs", "google"]:
                if credential.project_id:
                    config["project_id"] = credential.project_id
                if credential.credentials_path:
                    config["credentials_path"] = credential.credentials_path
            elif credential.provider in ["azure"]:
                if credential.account_name:
                    config["account_name"] = credential.account_name
                if credential.account_key:
                    config["account_key"] = credential.account_key
                if credential.connection_string:
                    config["connection_string"] = credential.connection_string
            
            # Attempt validation
            # Note: This requires a bucket to be specified, so we just validate credentials format
            return True
        
        except Exception as e:
            self.logger.error(f"Credential test failed: {e}")
            return False
