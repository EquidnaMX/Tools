"""
Password validators and policy enforcement

Validates passwords against policies, checks history, and evaluates strength.
"""

import re
import math
from typing import Optional, List, Tuple
from .models import PasswordPolicy, ValidationResult, ValidationSeverity


class PasswordValidator:
    """Validates passwords against policies and best practices"""
    
    def __init__(self, policy: PasswordPolicy = None):
        """Initialize validator with optional policy"""
        self.policy = policy or PasswordPolicy()
    
    def validate(self, password: str) -> ValidationResult:
        """
        Validate password against policy and standards
        
        Returns ValidationResult with:
        - valid: True if password passes all checks
        - score: 0-100 strength score
        - errors: List of validation failures
        - warnings: List of security concerns
        - entropy_bits: Estimated entropy in bits
        """
        result = ValidationResult(valid=True, score=0)
        
        # Run all validations
        self._check_length(password, result)
        self._check_character_types(password, result)
        self._check_excluded_terms(password, result)
        self._check_ambiguous_chars(password, result)
        self._check_patterns(password, result)
        self._check_common_passwords(password, result)
        
        # Calculate entropy and score
        result.entropy_bits = self._calculate_entropy(password)
        result.score = self._calculate_score(password, result)
        
        # Valid only if no critical errors
        result.valid = len(result.errors) == 0
        
        return result
    
    def _check_length(self, password: str, result: ValidationResult) -> None:
        """Check password length requirements"""
        length = len(password)
        
        if length < self.policy.min_length:
            result.errors.append(
                f"Contraseña muy corta: {length} caracteres (mínimo {self.policy.min_length})"
            )
        elif length < 10:
            result.warnings.append(
                f"Contraseña corta (solo {length} caracteres)"
            )
        
        if length > self.policy.max_length:
            result.errors.append(
                f"Contraseña muy larga: {length} caracteres (máximo {self.policy.max_length})"
            )
    
    def _check_character_types(self, password: str, result: ValidationResult) -> None:
        """Check for required character types"""
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in self.policy.special_chars for c in password)
        
        if self.policy.require_uppercase and not has_upper:
            result.errors.append("Se requieren letras mayúsculas")
        
        if self.policy.require_lowercase and not has_lower:
            result.errors.append("Se requieren letras minúsculas")
        
        if self.policy.require_digits and not has_digit:
            result.errors.append("Se requieren números")
        
        if self.policy.require_special and not has_special:
            result.errors.append(f"Se requieren caracteres especiales: {self.policy.special_chars}")
        
        # Warnings for mixed case sensitivity
        if has_upper and has_lower:
            result.info.append("✓ Mezcla de mayúsculas y minúsculas")
        
        if has_digit:
            result.info.append("✓ Contiene números")
        
        if has_special:
            result.info.append("✓ Contiene caracteres especiales")
    
    def _check_excluded_terms(self, password: str, result: ValidationResult) -> None:
        """Check for excluded/common terms"""
        password_lower = password.lower()
        
        for term in self.policy.excluded_terms:
            if term.lower() in password_lower:
                result.errors.append(f"Contraseña contiene término prohibido: {term}")
            elif len(term) > 3 and password_lower.startswith(term.lower()):
                result.warnings.append(f"Contraseña empieza con: {term}")
    
    def _check_ambiguous_chars(self, password: str, result: ValidationResult) -> None:
        """Check for ambiguous characters (0/O, l/1, etc)"""
        if not self.policy.exclude_ambiguous:
            return
        
        ambiguous = {'0': 'O', 'O': '0', 'l': '1', '1': 'l', 'I': 'l'}
        found_ambiguous = [c for c in password if c in ambiguous]
        
        if found_ambiguous:
            result.warnings.append(
                f"Contraseña contiene caracteres ambiguos que pueden confundir: {set(found_ambiguous)}"
            )
    
    def _check_patterns(self, password: str, result: ValidationResult) -> None:
        """Check for sequential and repeated patterns"""
        
        # Check for sequential patterns (abc, 123, etc)
        if self._has_sequential_pattern(password):
            result.warnings.append("Contraseña contiene patrones secuenciales (abc, 123, etc)")
        
        # Check for repeated characters
        if self._has_repeated_chars(password):
            result.warnings.append("Contraseña contiene caracteres repetidos consecutivos")
        
        # Check for keyboard patterns (qwerty, asdf, etc)
        if self._has_keyboard_pattern(password):
            result.warnings.append("Contraseña contiene patrón de teclado")
    
    def _has_sequential_pattern(self, password: str, length: int = 3) -> bool:
        """Check for sequential characters"""
        for i in range(len(password) - length + 1):
            substring = password[i:i + length]
            
            # Check if all ASCII codes are sequential
            if all(ord(substring[j + 1]) == ord(substring[j]) + 1 
                   for j in range(len(substring) - 1)):
                return True
        
        return False
    
    def _has_repeated_chars(self, password: str, length: int = 3) -> bool:
        """Check for repeated characters"""
        for i in range(len(password) - length + 1):
            if len(set(password[i:i + length])) == 1:
                return True
        return False
    
    def _has_keyboard_pattern(self, password: str) -> bool:
        """Check for keyboard patterns (qwerty, dvorak, etc)"""
        keyboard_patterns = [
            'qwerty', 'asdfgh', 'qazwsx', 'zxcvbn',
            '123456', '654321', '111111', '000000'
        ]
        
        password_lower = password.lower()
        for pattern in keyboard_patterns:
            if pattern in password_lower:
                return True
        
        return False
    
    def _check_common_passwords(self, password: str, result: ValidationResult) -> None:
        """Check against list of common passwords"""
        # Small list of very common passwords - in production, use a full dict
        common_passwords = {
            'password', 'password123', '12345678', 'qwerty', 'abc123',
            'monkey', 'letmein', 'trustno1', 'dragon', 'baseball'
        }
        
        if password.lower() in common_passwords:
            result.errors.append("Esta contraseña es muy común y está en listas de diccionario")
    
    def _calculate_entropy(self, password: str) -> float:
        """
        Calculate Shannon entropy of password
        
        Entropy (bits) = log2(charset_size ^ password_length)
        
        Common charset sizes:
        - lowercase only: 26
        - numbers: 10
        - lowercase + numbers: 36
        - lowercase + uppercase + numbers: 62
        - full ASCII: 94
        """
        charset_size = self._get_charset_size(password)
        
        if charset_size > 0:
            entropy = math.log2(charset_size ** len(password))
            return entropy
        
        return 0.0
    
    def _get_charset_size(self, password: str) -> int:
        """Determine effective charset size used in password."""
        charset = set()
        
        for char in password:
            if char.islower():
                charset.add('lowercase')
            elif char.isupper():
                charset.add('uppercase')
            elif char.isdigit():
                charset.add('digits')
            else:
                charset.add('special')
        
        # Map to character counts
        charset_size = 0
        if 'lowercase' in charset:
            charset_size += 26
        if 'uppercase' in charset:
            charset_size += 26
        if 'digits' in charset:
            charset_size += 10
        if 'special' in charset:
            charset_size += 32  # Approximate
        
        return charset_size
    
    def _calculate_score(self, password: str, result: ValidationResult) -> int:
        """
        Calculate password strength score (0-100)
        
        Based on:
        - Entropy (higher is better)
        - Length (longer is better)
        - Character diversity (more types is better)
        - Patterns (penalize for patterns)
        - Common passwords (0 if common)
        - Validation errors (0 if errors exist)
        """
        if result.errors:
            return 0
        
        score = 0
        
        # Entropy contribution (0-40 points)
        entropy_score = min(40, result.entropy_bits / 2)
        score += entropy_score
        
        # Length contribution (0-20 points)
        length = len(password)
        if length >= 20:
            score += 20
        elif length >= 16:
            score += 18
        elif length >= 14:
            score += 16
        elif length >= 12:
            score += 14
        else:
            score += (length / 12) * 14
        
        # Character diversity (0-20 points)
        char_types = sum([
            1 if any(c.isupper() for c in password) else 0,
            1 if any(c.islower() for c in password) else 0,
            1 if any(c.isdigit() for c in password) else 0,
            1 if any(c in self.policy.special_chars for c in password) else 0,
        ])
        score += (char_types / 4) * 20
        
        # Pattern penalties (0-20 points)
        pattern_penalty = 0
        if self._has_sequential_pattern(password):
            pattern_penalty += 5
        if self._has_repeated_chars(password):
            pattern_penalty += 5
        if self._has_keyboard_pattern(password):
            pattern_penalty += 5
        
        score = max(0, score - pattern_penalty)
        
        # Warning penalties
        score = max(0, score - len(result.warnings) * 2)
        
        return min(100, int(score))
    
    def estimate_crack_time(self, entropy_bits: float) -> str:
        """
        Estimate time to crack with brute force
        
        Assumptions:
        - 1 billion attempts per second
        - Average: need to try 50% of keyspace
        """
        attempts_per_second = 1e9
        keyspace = 2 ** entropy_bits
        avg_attempts = keyspace / 2
        seconds = avg_attempts / attempts_per_second
        
        if seconds < 1:
            return "< 1 segundo"
        elif seconds < 60:
            return f"{int(seconds)} segundos"
        elif seconds < 3600:
            return f"{int(seconds / 60)} minutos"
        elif seconds < 86400:
            return f"{int(seconds / 3600)} horas"
        elif seconds < 31536000:
            return f"{int(seconds / 86400)} días"
        else:
            years = seconds / 31536000
            if years > 1000000:
                return f"{years:.1e} años"
            return f"{int(years)} años"


class PasswordHistoryValidator:
    """Validates password history and reuse"""
    
    def __init__(self, history_db_path: Optional[str] = None):
        """Initialize with optional history database"""
        self.history_db_path = history_db_path
    
    def check_reuse(
        self,
        host: str,
        username: str,
        password: str,
        max_reuse: int = 5
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if password was previously used
        
        Returns:
        - (True, None) if password is OK to use
        - (False, message) if password was recently used
        """
        # In production: query password hash history
        # For now: stub implementation
        return (True, None)
    
    def get_password_age(
        self,
        host: str,
        username: str
    ) -> Optional[int]:
        """Get days since last password change"""
        # In production: query LDAP or /etc/shadow
        return None
