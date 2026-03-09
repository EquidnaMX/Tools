"""
Client-side encryption utilities for cloud transfers.

Provides AES-256-GCM encryption before upload and decryption after download
to protect data at rest in cloud storage.

Security features:
- AES-256-GCM authenticated encryption
- Unique IV (nonce) for each file
- HMAC authentication tag to prevent tampering
- PBKDF2 key derivation for password-based keys
"""

import io
import secrets
from pathlib import Path
from typing import BinaryIO, Tuple, Optional


class EncryptionError(Exception):
    """Raised when encryption or decryption fails."""
    pass


def _get_cipher(key_hex: str):
    """
    Get cipher instance from hex key.
    
    Args:
        key_hex: 64-character hex string (32 bytes)
        
    Returns:
        Cipher instance ready for encryption/decryption
        
    Raises:
        EncryptionError: If cryptography not installed or key invalid
    """
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        raise EncryptionError("cryptography package not installed. Run: pip install cryptography")
    
    try:
        key_bytes = bytes.fromhex(key_hex)
        if len(key_bytes) != 32:
            raise ValueError("Key must be 32 bytes (64 hex characters)")
        return AESGCM(key_bytes)
    except Exception as e:
        raise EncryptionError(f"Invalid encryption key: {e}")


def generate_key() -> str:
    """
    Generate a random 256-bit encryption key.
    
    Returns:
        64-character hex string representing 32-byte key
    """
    return secrets.token_hex(32)


def derive_key_from_password(password: str, salt: Optional[bytes] = None, iterations: int = 100000) -> Tuple[str, bytes]:
    """
    Derive encryption key from password using PBKDF2.
    
    Args:
        password: User password
        salt: Salt bytes (auto-generated if not provided)
        iterations: PBKDF2 iterations (default: 100,000)
        
    Returns:
        Tuple of (key_hex, salt_bytes)
        
    Raises:
        EncryptionError: If cryptography not installed
    """
    try:
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.backends import default_backend
    except ImportError:
        raise EncryptionError("cryptography package not installed. Run: pip install cryptography")
    
    if salt is None:
        salt = secrets.token_bytes(16)
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
        backend=default_backend()
    )
    
    key_bytes = kdf.derive(password.encode('utf-8'))
    return key_bytes.hex(), salt


def encrypt_file(input_path: Path, key_hex: str) -> Tuple[bytes, bytes]:
    """
    Encrypt file contents.
    
    Args:
        input_path: Path to file to encrypt
        key_hex: 64-character hex encryption key
        
    Returns:
        Tuple of (nonce, encrypted_data)
        
    Raises:
        EncryptionError: If encryption fails
    """
    cipher = _get_cipher(key_hex)
    
    try:
        with open(input_path, 'rb') as f:
            plaintext = f.read()
        
        # Generate random nonce (12 bytes for GCM)
        nonce = secrets.token_bytes(12)
        
        # Encrypt with authentication
        ciphertext = cipher.encrypt(nonce, plaintext, None)
        
        return nonce, ciphertext
    
    except Exception as e:
        raise EncryptionError(f"Failed to encrypt {input_path}: {e}")


def decrypt_file(encrypted_data: bytes, nonce: bytes, key_hex: str, output_path: Path) -> int:
    """
    Decrypt data to file.
    
    Args:
        encrypted_data: Encrypted data bytes
        nonce: Nonce used during encryption (12 bytes)
        key_hex: 64-character hex decryption key
        output_path: Path where to write decrypted file
        
    Returns:
        Number of bytes written
        
    Raises:
        EncryptionError: If decryption fails or authentication tag invalid
    """
    cipher = _get_cipher(key_hex)
    
    try:
        # Decrypt and verify authentication tag
        plaintext = cipher.decrypt(nonce, encrypted_data, None)
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(plaintext)
        
        return len(plaintext)
    
    except Exception as e:
        raise EncryptionError(f"Failed to decrypt to {output_path}: {e}")


def encrypt_stream(input_stream: BinaryIO, key_hex: str) -> Tuple[bytes, BinaryIO]:
    """
    Create encrypted stream from input stream.
    
    Args:
        input_stream: Input file-like object
        key_hex: 64-character hex encryption key
        
    Returns:
        Tuple of (nonce, encrypted_stream)
        
    Raises:
        EncryptionError: If encryption fails
    """
    cipher = _get_cipher(key_hex)
    
    try:
        plaintext = input_stream.read()
        nonce = secrets.token_bytes(12)
        ciphertext = cipher.encrypt(nonce, plaintext, None)
        
        return nonce, io.BytesIO(ciphertext)
    
    except Exception as e:
        raise EncryptionError(f"Failed to encrypt stream: {e}")


def decrypt_stream(encrypted_stream: BinaryIO, nonce: bytes, key_hex: str) -> BinaryIO:
    """
    Create decrypted stream from encrypted stream.
    
    Args:
        encrypted_stream: Encrypted file-like object
        nonce: Nonce used during encryption
        key_hex: 64-character hex decryption key
        
    Returns:
        Decrypted stream (BytesIO object)
        
    Raises:
        EncryptionError: If decryption fails
    """
    cipher = _get_cipher(key_hex)
    
    try:
        ciphertext = encrypted_stream.read()
        plaintext = cipher.decrypt(nonce, ciphertext, None)
        
        return io.BytesIO(plaintext)
    
    except Exception as e:
        raise EncryptionError(f"Failed to decrypt stream: {e}")


def encrypt_with_metadata(input_path: Path, key_hex: str) -> bytes:
    """
    Encrypt file with embedded metadata.
    
    Creates a container format:
    - 12 bytes: nonce
    - N bytes: encrypted data with authentication tag
    
    Args:
        input_path: Path to file to encrypt
        key_hex: 64-character hex encryption key
        
    Returns:
        Complete encrypted container (nonce + ciphertext)
    """
    nonce, ciphertext = encrypt_file(input_path, key_hex)
    return nonce + ciphertext


def decrypt_with_metadata(container: bytes, key_hex: str, output_path: Path) -> int:
    """
    Decrypt file from container format.
    
    Args:
        container: Complete encrypted container (nonce + ciphertext)
        key_hex: 64-character hex decryption key
        output_path: Path where to write decrypted file
        
    Returns:
        Number of bytes written
        
    Raises:
        EncryptionError: If container invalid or decryption fails
    """
    if len(container) < 12:
        raise EncryptionError("Invalid encrypted container: too short")
    
    nonce = container[:12]
    ciphertext = container[12:]
    
    return decrypt_file(ciphertext, nonce, key_hex, output_path)


def is_encrypted(data: bytes) -> bool:
    """
    Check if data appears to be encrypted with our format.
    
    This is a heuristic check based on entropy and structure.
    
    Args:
        data: Data to check
        
    Returns:
        True if data appears encrypted
    """
    # Too short to be our format
    if len(data) < 12:
        return False
    
    # Check entropy of first chunk (encrypted data should have high entropy)
    sample = data[:min(1024, len(data))]
    unique_bytes = len(set(sample))
    
    # Encrypted data typically has >90% unique bytes in sample
    return unique_bytes > len(sample) * 0.9
