"""Prove encryption-before-bind, certificate verification and cleanup order."""

import sys
from types import SimpleNamespace

import pytest

from tools.ldap.client_installer import LDAPClientInstaller, LDAPConfig
from tools.ldap.connection import probe_connection, validate_endpoint


@pytest.fixture
def protocol(monkeypatch):
    events = []

    class Connection:
        def set_option(self, key, value):
            events.append((key, value))

        def start_tls_s(self):
            events.append("tls")

        def simple_bind_s(self, dn, password):
            events.append("bind")

        def search_s(self, base, scope):
            events.append("search")
            return [(base, {})]

        def unbind_s(self):
            events.append("unbind")

    connection = Connection()
    module = SimpleNamespace(initialize=lambda uri: connection, LDAPError=RuntimeError,
                             OPT_REFERRALS="referrals", OPT_NETWORK_TIMEOUT="network_timeout",
                             OPT_TIMEOUT="timeout", OPT_X_TLS_REQUIRE_CERT="verify",
                             OPT_X_TLS_DEMAND="demand", OPT_X_TLS_CACERTFILE="ca",
                             OPT_X_TLS_NEWCTX="newctx", SCOPE_BASE=0)
    monkeypatch.setitem(sys.modules, "ldap", module)
    return events, connection


@pytest.mark.parametrize("uri,starttls", [("ldap://example.test", True), ("ldaps://example.test", False)])
def test_tls_bind_order_and_cleanup(protocol, uri, starttls):
    events, _ = protocol
    report = probe_connection(LDAPConfig(uri, "dc=test", "cn=reader", "secret"))
    assert report["encrypted"]
    assert ("verify", "demand") in events
    assert ("network_timeout", 30) in events
    assert ("timeout", 30) in events
    assert ("tls" in events) is starttls
    if starttls:
        assert events.index("tls") < events.index("bind")
    assert events[-1] == "unbind"


def test_tls_failure_never_binds_and_releases_connection(protocol):
    events, connection = protocol

    def fail():
        raise RuntimeError("untrusted certificate")

    connection.start_tls_s = fail
    with pytest.raises(RuntimeError):
        probe_connection(LDAPConfig("ldap://example.test", "dc=test", "cn=reader", "secret"))
    assert "bind" not in events
    assert events[-1] == "unbind"


@pytest.mark.parametrize("uri", [
    "ldap://user:password@example.test", "ldap://example.test:0", "ldap://example.test:65536",
    "ldap://example.test/dc=other", "ldap://example.test?query", "http://example.test",
    "ldap://example.test#fragment", "ldap://", "ldap://example.test:bad",
])
def test_invalid_endpoints(uri):
    with pytest.raises(ValueError):
        validate_endpoint(uri)


def test_plain_password_bind_and_empty_password_refused(protocol):
    for config in [LDAPConfig("ldap://example.test", "dc=test", "cn=reader", "secret", use_tls=False),
                   LDAPConfig("ldap://example.test", "dc=test", "cn=reader", "")]:
        with pytest.raises(ValueError):
            probe_connection(config)
        result = LDAPClientInstaller(config, dry_run=True).install()
        assert not result.success


def test_search_failure_releases_connection(protocol):
    events, connection = protocol
    connection.search_s = lambda *args: []
    with pytest.raises(ValueError, match="base entry"):
        probe_connection(LDAPConfig("ldaps://example.test", "dc=test"))
    assert events[-1] == "unbind"


def test_configuration_repr_does_not_expose_password():
    assert "private-password" not in repr(LDAPConfig("ldaps://example.test", "dc=test", "cn=r", "private-password"))
