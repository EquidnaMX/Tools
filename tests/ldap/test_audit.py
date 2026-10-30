"""Static inspection against disposable configuration roots."""

from tools.ldap.audit import audit_client


def test_nslcd_cleartext_detected_without_leaking_secret(tmp_path):
    etc = tmp_path / "etc"
    etc.mkdir()
    path = etc / "nslcd.conf"
    content = "uri ldap://old.test\nbindpw very-private\n"
    path.write_text(content)
    report = audit_client(tmp_path)
    assert not report["success"]
    assert "very-private" not in str(report)
    assert path.read_text() == content


def test_sssd_tls_and_ca(tmp_path):
    directory = tmp_path / "etc/sssd"
    directory.mkdir(parents=True)
    (tmp_path / "etc/ca.pem").write_text("test fixture, not a real CA")
    (directory / "sssd.conf").write_text(
        "[domain/LDAP]\nldap_uri=ldaps://new.test\nldap_tls_reqcert=demand\nldap_tls_cacert=/etc/ca.pem\n"
    )
    report = audit_client(tmp_path)
    assert report["success"]
    assert any(c["check"].endswith(":tls") and c["status"] == "pass" for c in report["checks"])
    assert any(c["status"] == "review" for c in report["checks"])


def test_disabled_ssh_pam_reported(tmp_path):
    directory = tmp_path / "etc/ssh"
    directory.mkdir(parents=True)
    (directory / "sshd_config").write_text("UsePAM no\n")
    assert not audit_client(tmp_path)["success"]


def test_missing_backend_is_not_a_success(tmp_path):
    assert not audit_client(tmp_path)["success"]
