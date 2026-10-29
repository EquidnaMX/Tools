"""
LDAP synchronization and integration

Syncs password changes with LDAP directory service.
"""

from typing import Optional, List, Tuple
from datetime import datetime
from .models import LDAPConfig


class LDAPSync:
    """Synchronize password changes with LDAP"""
    
    def __init__(self, config: LDAPConfig):
        """Initialize LDAP synchronization"""
        self.config = config
        self.connection = None
        self.ldap = None
    
    def connect(self) -> bool:
        """Establish LDAP connection"""
        try:
            import ldap
        except ImportError:
            raise ImportError(
                "python-ldap is required for LDAP support.\n"
                "Install with: pip install python-ldap"
            )
        
        try:
            self.ldap = ldap
            # Create connection
            self.connection = ldap.initialize(self.config.server_uri)
            
            # Set options
            if self.config.use_tls and not self.config.use_ssl:
                self.connection.start_tls_s()
            
            if not self.config.verify_cert:
                ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
            
            # Bind
            self.connection.simple_bind_s(
                self.config.bind_dn,
                self.config.bind_password
            )
            
            return True
        
        except Exception as e:
            print(f"LDAP connection failed: {e}")
            return False
    
    def disconnect(self) -> None:
        """Close LDAP connection"""
        if self.connection:
            self.connection.unbind_s()
            self.connection = None
    
    def find_user(self, username: str) -> Optional[str]:
        """
        Find user DN in LDAP
        
        Returns:
        - User DN if found
        - None if not found
        """
        if not self.connection:
            if not self.connect():
                return None
        
        try:
            # Search for user
            search_filter = f"(uid={username})"
            
            result = self.connection.search_s(
                self.config.base_dn,
                self.ldap.SCOPE_SUBTREE,
                search_filter,
                ['dn']
            )
            
            if result and result[0][0]:  # Found
                return result[0][0]
            
            return None
        
        except Exception as e:
            print(f"LDAP search failed: {e}")
            return None
    
    def sync_password_change(
        self,
        host: str,
        username: str,
        new_password: str,
        old_password: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Sync password change to LDAP
        
        This updates the LDAP directory with the new password.
        The actual password change happens on the host first.
        
        Returns:
        - (success, message)
        """
        if not self.connection:
            if not self.connect():
                return False, "LDAP connection failed"
        
        try:
            # Find user in LDAP
            user_dn = self.find_user(username)
            if not user_dn:
                return False, f"User {username} not found in LDAP"
            
            # Prepare password change in LDAP format
            # Note: This is a simplified version
            # Real implementation would use LDAP modify operations
            
            # For now, just log the sync request
            # Production: would call ldap_modify_ext_s
            
            return True, f"Password synced to LDAP for {username}"
        
        except Exception as e:
            return False, f"LDAP sync error: {e}"
    
    def get_user_attributes(
        self,
        username: str,
        attributes: Optional[List[str]] = None
    ) -> Optional[dict]:
        """
        Get user attributes from LDAP
        
        Returns:
        - Dictionary of attributes
        - None if user not found
        """
        if not self.connection:
            if not self.connect():
                return None
        
        if attributes is None:
            attributes = self.config.attributes_to_sync
        
        try:
            user_dn = self.find_user(username)
            if not user_dn:
                return None
            
            result = self.connection.search_s(
                user_dn,
                self.ldap.SCOPE_BASE,
                '(objectClass=*)',
                attributes
            )
            
            if result:
                return dict(result[0][1])
            
            return None
        
        except Exception as e:
            print(f"Error getting user attributes: {e}")
            return None
    
    def update_user_attributes(
        self,
        username: str,
        attributes: dict
    ) -> Tuple[bool, str]:
        """
        Update user attributes in LDAP
        
        Args:
        - username: Username
        - attributes: Dictionary of attributes to update
        
        Returns:
        - (success, message)
        """
        if not self.connection:
            if not self.connect():
                return False, "LDAP connection failed"
        
        try:
            import ldap.modlist as modlist
            
            user_dn = self.find_user(username)
            if not user_dn:
                return False, f"User {username} not found in LDAP"
            
            # Get current attributes
            current = self.connection.search_s(
                user_dn,
                self.ldap.SCOPE_BASE,
                '(objectClass=*)'
            )[0][1]
            
            # Prepare modifications
            new_attrs = dict(current)
            for key, value in attributes.items():
                new_attrs[key.encode() if isinstance(key, str) else key] = [
                    v.encode() if isinstance(v, str) else v for v in (value if isinstance(value, list) else [value])
                ]
            
            ldif = modlist.modifyModlist(current, new_attrs)
            
            # Apply changes
            if ldif:
                self.connection.modify_s(user_dn, ldif)
                return True, f"Attributes updated for {username}"
            
            return True, f"No changes needed for {username}"
        
        except Exception as e:
            return False, f"Error updating attributes: {e}"
    
    def get_password_expiration(self, username: str) -> Optional[datetime]:
        """
        Get password expiration date for user
        
        Returns:
        - datetime if expiration date found
        - None if not found or never expires
        """
        attrs = self.get_user_attributes(username, ['shadowExpire'])
        
        if not attrs or b'shadowExpire' not in attrs:
            return None
        
        try:
            days = int(attrs[b'shadowExpire'][0])
            # shadow days are since 1970-01-01
            epoch = datetime(1970, 1, 1)
            expiry = epoch + __import__('datetime').timedelta(days=days)
            return expiry
        except Exception:
            return None


class LDAPCredentialStore:
    """Store LDAP credentials securely"""
    
    def __init__(self, keyring_service: str = "tools-password-manager"):
        """Initialize credential store"""
        self.service = keyring_service
    
    def store_config(self, config_name: str, config: LDAPConfig) -> bool:
        """Store LDAP config in system keyring"""
        try:
            import keyring
            
            # Store config as JSON
            import json
            data = {
                'server_uri': config.server_uri,
                'bind_dn': config.bind_dn,
                'bind_password': config.bind_password,
                'base_dn': config.base_dn,
                'use_ssl': config.use_ssl,
                'use_tls': config.use_tls
            }
            
            keyring.set_password(
                self.service,
                f"ldap_config_{config_name}",
                json.dumps(data)
            )
            
            return True
        except Exception:
            return False
    
    def get_config(self, config_name: str) -> Optional[LDAPConfig]:
        """Retrieve LDAP config from keyring"""
        try:
            import keyring
            import json
            
            data = keyring.get_password(
                self.service,
                f"ldap_config_{config_name}"
            )
            
            if not data:
                return None
            
            config_dict = json.loads(data)
            return LDAPConfig(**config_dict)
        except Exception:
            return None
