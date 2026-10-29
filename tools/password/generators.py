"""
Password generation with cryptographic security

Generates strong, random passwords using cryptographically secure methods.
"""

import secrets
import string
import math
from typing import List


class PasswordGenerator:
    """Generates cryptographically secure passwords"""

    def __init__(self):
        """Initialize character sets"""
        self.lowercase = string.ascii_lowercase
        self.uppercase = string.ascii_uppercase
        self.digits = string.digits
        self.special_chars = "!@#$%^&*-_+=[]{}|;:,.<>?"

        # Remove ambiguous characters if requested
        self.ambiguous = frozenset("0O1l5SBZ")

    def generate(
        self,
        length: int = 16,
        include_uppercase: bool = True,
        include_lowercase: bool = True,
        include_digits: bool = True,
        include_special: bool = True,
        exclude_ambiguous: bool = True,
    ) -> str:
        """
        Generate cryptographically secure password

        Args:
        - length: Password length (default 16)
        - include_*: Character type inclusion
        - exclude_ambiguous: Exclude 0/O/l/1 etc

        Returns:
        - Generated password

        Raises:
        - ValueError if no character types selected or length too short
        """
        # Build charset
        charset = ""

        if include_lowercase:
            charset += (
                self._filter_ambiguous(self.lowercase)
                if exclude_ambiguous
                else self.lowercase
            )
        if include_uppercase:
            charset += (
                self._filter_ambiguous(self.uppercase)
                if exclude_ambiguous
                else self.uppercase
            )
        if include_digits:
            charset += (
                self._filter_ambiguous(self.digits)
                if exclude_ambiguous
                else self.digits
            )
        if include_special:
            charset += self.special_chars

        if not charset:
            raise ValueError("No character types selected")

        if length < 8:
            raise ValueError("Password length must be at least 8")

        # Ensure at least one character from each required type
        password = []

        if include_lowercase:
            c = (
                self._filter_ambiguous(self.lowercase)
                if exclude_ambiguous
                else self.lowercase
            )
            password.append(secrets.choice(c))

        if include_uppercase:
            c = (
                self._filter_ambiguous(self.uppercase)
                if exclude_ambiguous
                else self.uppercase
            )
            password.append(secrets.choice(c))

        if include_digits:
            c = (
                self._filter_ambiguous(self.digits)
                if exclude_ambiguous
                else self.digits
            )
            password.append(secrets.choice(c))

        if include_special:
            password.append(secrets.choice(self.special_chars))

        # Fill remaining length with random characters
        for _ in range(length - len(password)):
            password.append(secrets.choice(charset))

        # Shuffle to avoid predictable patterns
        password_list = list(password)
        for i in range(len(password_list) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            password_list[i], password_list[j] = password_list[j], password_list[i]

        return "".join(password_list)

    def generate_batch(self, count: int, **kwargs) -> List[str]:
        """Generate multiple passwords at once"""
        return [self.generate(**kwargs) for _ in range(count)]

    def estimate_entropy(self, password: str) -> float:
        """
        Calculate Shannon entropy of password

        Entropy (bits) = log2(charset_size) * password_length

        More accurate than validator's method as it uses actual length
        """
        charset_size = 0

        # Count charset sizes
        if any(c in self.lowercase for c in password):
            charset_size = max(charset_size, 26)
        if any(c in self.uppercase for c in password):
            charset_size = max(charset_size, 52)
        if any(c in self.digits for c in password):
            charset_size = max(charset_size, 62)
        if any(c in self.special_chars for c in password):
            charset_size = 94

        if charset_size == 0:
            return 0.0

        entropy = math.log2(charset_size) * len(password)
        return entropy

    def _filter_ambiguous(self, charset: str) -> str:
        """Remove ambiguous characters from charset"""
        return "".join(c for c in charset if c not in self.ambiguous)


class PasswordPatternGenerator:
    """Generate passwords from patterns (for special use cases)"""

    def generate_from_pattern(self, pattern: str) -> str:
        """
        Generate password from pattern

        Pattern symbols:
        - L: lowercase letter
        - U: uppercase letter
        - D: digit
        - S: special character
        - *: any character

        Example: "UL3SL3" -> "Bd9!mF2"
        """
        gen = PasswordGenerator()
        result = []

        for char in pattern:
            if char == "L":
                result.append(secrets.choice(gen.lowercase))
            elif char == "U":
                result.append(secrets.choice(gen.uppercase))
            elif char == "D":
                result.append(secrets.choice(gen.digits))
            elif char == "S":
                result.append(secrets.choice(gen.special_chars))
            elif char == "*":
                all_chars = (
                    gen.lowercase + gen.uppercase + gen.digits + gen.special_chars
                )
                result.append(secrets.choice(all_chars))
            else:
                result.append(char)

        return "".join(result)
