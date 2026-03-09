"""Tests for LDAP sync helpers."""

import sys
from unittest.mock import MagicMock, patch

from tools.password.ldap_sync import LDAPSync, LDAPCredentialStore
from tools.password.models import LDAPConfig


def _config():
    return LDAPConfig(
        server_uri="ldap://ldap.example.com",
        bind_dn="cn=admin,dc=example,dc=com",
        bind_password="secret",
        base_dn="dc=example,dc=com",
        use_tls=False,
        use_ssl=False,
    )


def test_find_user_returns_dn_with_mocked_connection():
    sync = LDAPSync(_config())
    sync.ldap = MagicMock(SCOPE_SUBTREE=2)
    sync.connection = MagicMock()
    sync.connection.search_s.return_value = [("uid=root,dc=example,dc=com", {})]

    dn = sync.find_user("root")

    assert dn == "uid=root,dc=example,dc=com"


def test_sync_password_change_user_not_found():
    sync = LDAPSync(_config())
    with patch.object(sync, "connect", return_value=True), \
         patch.object(sync, "find_user", return_value=None):
        ok, msg = sync.sync_password_change("server1", "ghost", "newpw")

    assert ok is False
    assert "not found" in msg


def test_sync_password_change_success_path():
    sync = LDAPSync(_config())
    with patch.object(sync, "connect", return_value=True), \
         patch.object(sync, "find_user", return_value="uid=root,dc=example,dc=com"):
        ok, msg = sync.sync_password_change("server1", "root", "newpw")

    assert ok is True
    assert "synced" in msg


def test_credential_store_roundtrip_with_mocked_keyring():
    store = LDAPCredentialStore()
    cfg = _config()

    fake_keyring = MagicMock()
    fake_keyring.get_password.return_value = '{"server_uri":"ldap://ldap.example.com","bind_dn":"cn=admin,dc=example,dc=com","bind_password":"secret","base_dn":"dc=example,dc=com","use_ssl":false,"use_tls":false}'

    with patch.dict(sys.modules, {"keyring": fake_keyring}):
        assert store.store_config("default", cfg) is True
        loaded = store.get_config("default")

    assert fake_keyring.set_password.called
    assert loaded is not None
    assert loaded.server_uri == cfg.server_uri
