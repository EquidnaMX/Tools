#!/usr/bin/env python3
"""
Script para ejecutar tests y generar reporte.
"""
import sys
import pytest

# Ejecutar tests con coverage
result = pytest.main([
    'tests/',
    '--cov=tools',
    '--cov-report=term',
    '--cov-report=html',
    '-v',
    '--tb=short',
    '--maxfail=10'
])

print(f"\n{'=' * 80}")
print(f"RESULTADO FINAL: {'✓ PASSED' if result == 0 else '✗ FAILED'}")
print(f"Exit code: {result}")
print(f"{'=' * 80}\n")

sys.exit(result)
