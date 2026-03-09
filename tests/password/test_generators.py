"""Tests for password generators."""

import pytest

from tools.password.generators import PasswordGenerator, PasswordPatternGenerator


def test_generate_password_default_properties():
    gen = PasswordGenerator()
    password = gen.generate()

    assert len(password) == 16
    assert any(c.islower() for c in password)
    assert any(c.isupper() for c in password)
    assert any(c.isdigit() for c in password)
    assert any(c in gen.special_chars for c in password)


def test_generate_rejects_too_short_length():
    gen = PasswordGenerator()

    with pytest.raises(ValueError):
        gen.generate(length=6)


def test_generate_rejects_when_no_charset_selected():
    gen = PasswordGenerator()

    with pytest.raises(ValueError):
        gen.generate(
            include_uppercase=False,
            include_lowercase=False,
            include_digits=False,
            include_special=False,
        )


def test_generate_batch_count():
    gen = PasswordGenerator()
    batch = gen.generate_batch(4, length=12)

    assert len(batch) == 4
    assert all(len(p) == 12 for p in batch)


def test_pattern_generator_uses_pattern_tokens():
    pat = PasswordPatternGenerator()
    out = pat.generate_from_pattern("LUDS-*-")

    assert len(out) == 7
    assert out[0].islower()
    assert out[1].isupper()
    assert out[2].isdigit()


def test_entropy_estimation_positive_for_non_empty_password():
    gen = PasswordGenerator()

    assert gen.estimate_entropy("Abc123!xyz") > 0
