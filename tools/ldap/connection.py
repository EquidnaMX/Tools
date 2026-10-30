"""LDAP connection validation shared by plans and connection probes."""

from urllib.parse import urlsplit


def validate_endpoint(uri):
    try:
        parsed = urlsplit(uri)
        if (not uri.startswith(("ldap://", "ldaps://")) or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                or any(c.isspace() for c in uri) or any(c in uri for c in "\0\r\n")):
            raise ValueError("Expected ldap://host[:port] or ldaps://host[:port], without credentials or query")
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError("Invalid LDAP port")
        return parsed
    except (TypeError, AttributeError) as exc:
        raise ValueError("Invalid LDAP URI") from exc


def probe_connection(config):
    """Verify TLS before bind, perform a base search and always release the connection.

    Network behavior is isolated here for deterministic protocol-order tests.
    A successful probe does not establish PAM/NSS or SSH authentication health.
    """
    import ldap

    endpoint = validate_endpoint(config.uri)
    if config.bind_dn and not config.bind_password:
        raise ValueError("A nonempty bind password is required")
    if config.bind_password and not config.bind_dn:
        raise ValueError("bind_dn is required with a password")
    if config.bind_dn and endpoint.scheme == "ldap" and not config.use_tls:
        raise ValueError("Refusing a password bind over unencrypted LDAP")
    connection = ldap.initialize(config.uri)
    try:
        connection.set_option(ldap.OPT_REFERRALS, 0)
        connection.set_option(ldap.OPT_NETWORK_TIMEOUT, config.search_timeout)
        connection.set_option(ldap.OPT_TIMEOUT, config.search_timeout)
        if config.use_tls or endpoint.scheme == "ldaps":
            connection.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_DEMAND)
            if config.tls_cacert_file:
                connection.set_option(ldap.OPT_X_TLS_CACERTFILE, config.tls_cacert_file)
            connection.set_option(ldap.OPT_X_TLS_NEWCTX, 0)
            if endpoint.scheme == "ldap":
                connection.start_tls_s()
        connection.simple_bind_s(config.bind_dn or "", config.bind_password or "")
        result = connection.search_s(config.base_dn, ldap.SCOPE_BASE)
        if not any(dn is not None for dn, _attrs in result):
            raise ValueError("LDAP base entry was not returned")
        return {"uri": config.uri, "base_dn": config.base_dn,
                "encrypted": config.use_tls or endpoint.scheme == "ldaps", "base_found": True}
    finally:
        try:
            connection.unbind_s()
        except ldap.LDAPError:
            pass
