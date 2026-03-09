"""Tests for password validators."""

from tools.password.models import PasswordPolicy
from tools.password.validators import PasswordValidator, PasswordHistoryValidator


def test_validate_strong_password_is_valid():
    policy = PasswordPolicy(min_length=12)
    validator = PasswordValidator(policy)

    result = validator.validate("Abcd!2345EfG")

    assert result.valid is True
    assert result.score > 0
    assert result.entropy_bits > 0


def test_validate_rejects_missing_required_types():
    policy = PasswordPolicy(require_uppercase=True, require_digits=True, require_special=True)
    validator = PasswordValidator(policy)

    result = validator.validate("onlylowercase")

    assert result.valid is False
    assert any("mayúsculas" in e for e in result.errors)
    assert any("números" in e for e in result.errors)
    assert any("especiales" in e for e in result.errors)


def test_validate_rejects_excluded_term():
    policy = PasswordPolicy(excluded_terms=["admin"])
    validator = PasswordValidator(policy)

    result = validator.validate("XyZadmin123!")

    assert result.valid is False
    assert any("término prohibido" in e for e in result.errors)


def test_crack_time_estimation_is_human_readable():
    validator = PasswordValidator()

    assert validator.estimate_crack_time(10)
    assert "años" in validator.estimate_crack_time(80) or "días" in validator.estimate_crack_time(80)


def test_password_history_validator_stub_behavior():
    history = PasswordHistoryValidator()

    ok, message = history.check_reuse("host1", "root", "Password1!", max_reuse=5)

    assert ok is True
    assert message is None
    assert history.get_password_age("host1", "root") is None
