# Testing - Tools Admin Toolkit

Documentación del sistema de testing del proyecto.

## 📊 Cobertura Actual

- **Total de Tests:** 435 totales
- **Ultima ejecucion completa:** 434 passed, 1 skipped
- **Cobertura Global:** 43% (3321 líneas sin cubrir de 5870)
- **Framework:** pytest 7.4.3
- **Plugins:** pytest-cov, pytest-mock, pytest-asyncio
- **Tiempo de Ejecución:** ~5 minutos

### Cobertura por Módulo

**Excelente Coverage (>80%):**

- ✅ tools/remote/ssh_executor.py: **97%**
- ✅ tools/remote/network_scanner.py: **95%**
- ✅ tools/remote/file_distributor.py: **93%**
- ✅ tools/dns/installer.py: **95%**
- ✅ tools/dns/replication_checker.py: **93%**
- ✅ tools/mail/domain_health.py: **95%**
- ✅ tools/mail/dns_validator.py: **94%**
- ✅ tools/mail/service_monitor.py: **91%**
- ✅ tools/mail/auditor.py: **84%**
- ✅ tools/system/file_manager.py: **86%**
- ✅ tools/system/pam_manager.py: **87%**
- ✅ tools/core/exceptions.py: **100%**
- ✅ tools/dns/zone_manager.py: **100%**

**Cobertura Media (50-80%):**

- ⚠️ tools/dns/ns_fixer.py: **74%**
- ⚠️ tools/system/timezone_manager.py: **68%**
- ⚠️ tools/cloud/factory.py: **65%**
- ⚠️ tools/cli/dns_commands.py: **57%**
- ⚠️ tools/cli/main.py: **57%**
- ⚠️ tools/core/validator.py: **56%**

**Cobertura Baja (<50%):**

- ⚠️ tools/cli/cloud_commands.py: **17%** (1043 líneas sin cubrir)
- ⚠️ tools/cli/mail_commands.py: **19%**
- ⚠️ tools/cli/system_commands.py: **29%**
- ⚠️ tools/cloud/sync.py: **16%**
- ⚠️ tools/cloud/config_manager.py: **21%**
- ⚠️ tools/cloud/providers.py: **22%**
- ⚠️ tools/cloud/aws_s3.py: **38%**
- ⚠️ tools/cloud/azure_blob.py: **39%**
- ⚠️ tools/cloud/google_cloud.py: **36%**

**Sin Cobertura (0%):**

- ❌ tools/cloud/bandwidth.py: **0%** (funcionalidad avanzada)
- ❌ tools/cloud/cache.py: **0%** (funcionalidad avanzada)
- ❌ tools/cloud/compression.py: **0%** (funcionalidad avanzada)
- ❌ tools/cloud/credentials.py: **0%** (funcionalidad avanzada)
- ❌ tools/cloud/encryption.py: **0%** (funcionalidad avanzada)

## 🗂️ Estructura de Tests

```
tests/
├── backup/          # Backup module
│   ├── test_backup_commands.py
│   └── test_backup_manager.py
├── monitoring/      # Monitoring and alerting
│   ├── test_monitoring_commands.py
│   └── test_monitoring_manager.py
├── cloud/           # Cloud storage providers
│   ├── test_cloud_providers.py
│   ├── test_config_manager.py
│   ├── test_digitalocean_sync.py
│   ├── test_helpers.py
│   ├── test_sync_stats.py
│   └── test_upload_stats.py
├── dns/             # DNS management
│   ├── test_installer.py
│   ├── test_ns_fixer.py
│   ├── test_replication_checker.py
│   └── test_zone_manager.py
├── mail/            # Mail auditing
│   ├── test_auditor.py
│   ├── test_dns_validator.py
│   ├── test_domain_health.py
│   └── test_service_monitor.py
├── remote/          # Remote management
│   ├── test_file_distributor.py
│   ├── test_network_scanner.py
│   └── test_ssh_executor.py
└── system/          # System utilities
    ├── test_file_manager.py
    ├── test_pam_manager.py
    └── test_timezone_manager.py
```

## 🚀 Ejecutar Tests

### Todos los Tests

```bash
# Ejecución básica
pytest tests/

# Con cobertura
pytest tests/ --cov=tools --cov-report=html

# Verbose con cobertura
pytest tests/ --cov=tools --cov-report=term --cov-report=html -v

# Solo resumen
pytest tests/ -q

# Script personalizado (recomendado)
python run_tests.py
```

### Tests por Módulo

```bash
# Solo cloud
pytest tests/cloud/ -v

# Solo DNS
pytest tests/dns/ -v

# Solo mail
pytest tests/mail/ -v

# Solo remote
pytest tests/remote/ -v

# Solo system
pytest tests/system/ -v
```

### Tests Específicos

```bash
# Un archivo específico
pytest tests/cloud/test_cloud_providers.py -v

# Una clase específica
pytest tests/cloud/test_cloud_providers.py::TestS3Provider -v

# Un test específico
pytest tests/cloud/test_cloud_providers.py::TestS3Provider::test_init_with_credentials -v
```

## 📈 Opciones Útiles

### Debugging

```bash
# Con output de prints
pytest tests/ -s

# Con traceback completo
pytest tests/ --tb=long

# Detener en primer fallo
pytest tests/ -x

# Detener después de N fallos
pytest tests/ --maxfail=5

# Verbose extra
pytest tests/ -vv
```

### Filtrado

```bash
# Solo tests que coincidan con palabra clave
pytest tests/ -k "upload"

# Solo tests marcados (markers)
pytest tests/ -m "slow"

# Excluir ciertos tests
pytest tests/ -k "not slow"
```

### Output

```bash
# Quiet mode (solo resumen)
pytest tests/ -q

# JSON output
pytest tests/ --json-report --json-report-file=report.json

# JUnit XML (para CI/CD)
pytest tests/ --junit-xml=test-report.xml
```

## 📊 Reportes de Cobertura

### Generar Reporte HTML

```bash
pytest tests/ --cov=tools --cov-report=html
# Abre htmlcov/index.html en el navegador
```

### Reporte en Terminal

```bash
pytest tests/ --cov=tools --cov-report=term
```

### Verificar Cobertura Mínima

```bash
pytest tests/ --cov=tools --cov-fail-under=80
```

## 🔧 Configuración

La configuración de pytest está en [pytest.ini](../pytest.ini):

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -ra
    --strict-markers
    --strict-config
    --showlocals
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    integration: marks tests as integration tests
```

## 🏷️ Markers Disponibles

- `@pytest.mark.slow` - Tests lentos
- `@pytest.mark.integration` - Tests de integración
- `@pytest.mark.asyncio` - Tests asíncronos
- `@pytest.mark.parametrize` - Tests parametrizados

## 🔁 Migracion de Tests Cloud

Los tests cloud se migraron a rutas modernas y ya no dependen de capas legacy:

- Imports directos desde `tools.cloud.sync` y `tools.cloud.config_manager`
- Patching de `boto3.Session` via `tools.cloud.sync.boto3.Session`
- Sin alias ni shims legacy en el repositorio

## ✅ Buenas Prácticas

### Escribir Tests

```python
import pytest
from tools.cloud import S3Provider

class TestS3Provider:
    """Tests para S3Provider"""

    def setup_method(self):
        """Setup antes de cada test"""
        self.region = "us-east-1"
        self.bucket = "test-bucket"

    def test_init_with_credentials(self):
        """Verifica inicialización con credenciales"""
        provider = S3Provider(
            bucket=self.bucket,
            region=self.region,
            access_key="AKIA...",
            secret_key="secret..."
        )
        assert provider.bucket == self.bucket
        assert provider.region == self.region

    @pytest.mark.slow
    def test_upload_large_file(self):
        """Test de upload de archivo grande (lento)"""
        # ... test implementation
        pass
```

### Fixtures

```python
@pytest.fixture
def temp_file(tmp_path):
    """Crea un archivo temporal para testing"""
    file_path = tmp_path / "test.txt"
    file_path.write_text("test content")
    return file_path

def test_process_file(temp_file):
    """Usa fixture de archivo temporal"""
    result = process_file(temp_file)
    assert result.success
```

### Mocking

```python
from unittest.mock import Mock, patch

def test_api_call():
    """Mock de llamadas externas"""
    with patch('tools.cloud.boto3.client') as mock_client:
        mock_client.return_value.list_buckets.return_value = {
            'Buckets': [{'Name': 'test-bucket'}]
        }

        provider = S3Provider(bucket='test-bucket')
        buckets = provider.list_buckets()

        assert len(buckets) == 1
        assert buckets[0] == 'test-bucket'
```

## 🎯 Objetivos de Testing

### Completado ✅

- [x] 435 tests definidos en la suite
- [x] 434 tests pasando en la ultima ejecucion completa
- [x] Tests organizados por módulo
- [x] Configuración pytest completa
- [x] Fixtures para datos de prueba
- [x] Mocking para dependencias externas
- [x] Tests para módulo backup (5 tests)
- [x] Tests para módulo monitoring (18 tests)

### En Progreso 🔄

- [ ] Cobertura >80% verificada
- [ ] Reporte HTML de cobertura generado
- [ ] Tests de integración para v2.7.0 features
- [ ] CI/CD con GitHub Actions

### Planeado 📋

- [ ] Tests para módulo database
- [ ] Tests para módulo containers
- [ ] Tests para módulo security
- [ ] Performance benchmarks
- [ ] Tests end-to-end

## 📝 Convenciones

1. **Nombres de archivos:** `test_<module>.py`
2. **Nombres de clases:** `Test<ClassName>`
3. **Nombres de tests:** `test_<description_snake_case>`
4. **Docstrings:** Siempre incluir descripción del test
5. **Assertions:** Usar assertions descriptivas, no genéricas
6. **Cleanup:** Usar fixtures con yield para cleanup automático
7. **Isolation:** Cada test debe ser independiente

## 🔍 Troubleshooting

### Import Errors

```bash
# Verificar que tools esté instalado en modo desarrollo
pip install -e .

# Verificar PYTHONPATH
python -c "import tools; print(tools.__file__)"
```

### Tests Lentos

```bash
# Skip tests lentos
pytest tests/ -m "not slow"

# Solo tests rápidos
pytest tests/ -m "not slow and not integration"
```

### Fallos Intermitentes

```bash
# Ejecutar test múltiples veces
pytest tests/cloud/test_cloud_providers.py::test_flaky -x --count=10
```

## 📚 Referencias

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-cov Documentation](https://pytest-cov.readthedocs.io/)
- [pytest-mock Documentation](https://pytest-mock.readthedocs.io/)
- [Python Testing Best Practices](https://realpython.com/pytest-python-testing/)

---

**Última actualización:** Marzo 9, 2026  
**Total tests:** 417 (ultima corrida: 416 passed, 1 skipped)  
**Framework:** pytest 7.4.3  
**Status:** ✅ Suite completa ejecutable, ⏳ Cobertura en verificacion
