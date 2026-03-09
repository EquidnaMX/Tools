# Changelog - Tools Admin Toolkit

Todos los cambios importantes de este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
y este proyecto adhiere a [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Para cambios específicos del módulo cloud, ver [tools/cloud/CHANGELOG.md](tools/cloud/CHANGELOG.md).

## [Unreleased]

### Changed - Limpieza Cloud Legacy

- Eliminada la capa temporal de compatibilidad legacy en cloud:
  - removidos `tools.cloud.config`, `tools.cloud.models`, `tools.cloud.helpers`
  - removido shim `download_do_space.py`
  - removido alias `CloudSync = DigitalOceanSync`
- Tests cloud migrados a imports y patch targets modernos (`tools.cloud.sync`, `tools.cloud.config_manager`).
- `sync()` ahora reporta credenciales inválidas con `RuntimeError` en lugar de `SystemExit`.

### Testing

- Suite completa validada: **411 passed, 1 skipped**.
- Suite cloud validada tras limpieza legacy: **118 passed**.

### ✅ Completado - Semana 1, Fase 1-2 (Opción C)

**Documentación (Fase 1):**

- ✅ README.md profesional v2.7.0 (611 líneas, badges, estructura completa)
- ✅ CHANGELOG.md general del proyecto (formato Keep a Changelog)
- ✅ Directorio examples/ con 5 archivos (46+ ejemplos de uso)
- ✅ tests/README.md - Documentación completa de testing (381 líneas)

**Testing y Calidad (Fase 2):**

- ✅ Suite de tests: 411 passed, 1 skipped
- ✅ Infraestructura pytest con plugins (pytest-cov, pytest-mock, pytest-asyncio)
- ✅ Script de ejecución: run_tests.py
- ✅ Reporte de cobertura: 43% total
  - Core modules (dns, mail, remote, system): 84-97% ⭐
  - CLI commands: 17-57%
  - Cloud advanced features: 0-39%
- ✅ Respaldos `.bak` legacy eliminados en limpieza de repositorio
- ✅ Tiempo de ejecución: 295s (~5 min)

### Planeado (Opción C - Semanas 1-4)

- Módulo `tools/backup/` - Backup automation
- Módulo `tools/monitoring/` - System monitoring
- Módulo `tools/database/` - Database management (PostgreSQL, MySQL, MongoDB)
- Módulo `tools/containers/` - Docker/Podman utilities
- Módulo `tools/security/` - Security auditing y certificate management
- GitHub Actions CI/CD workflow
- Installers (install.sh, install.ps1)
- Makefile y pre-commit hooks
- API documentation (Sphinx/MkDocs)

## [2.7.0] - 2026-03-08

### 🎉 Major Release: Advanced Optimizations

Versión mayor con 7 optimizaciones avanzadas para cloud storage y CLI empresarial.

### Added - Optimizaciones Cloud Storage

#### Sistema de Cache (SQLite)

- Cache persistente de metadatos de archivos
- Evita re-descargas innecesarias verificando checksums
- Estadísticas de cache hits/misses
- Comando: `--use-cache` en `tools cloud sync`

#### Compresión de Archivos

- Soporte gzip (estándar, mejor compresión)
- Soporte lz4 (ultra-rápido, menor compresión)
- Detección inteligente de archivos ya comprimidos
- Comandos: `--compress`, `--compression-type {gzip|lz4}`

#### Encriptación AES-256

- Encriptación AES-256-GCM con autenticación
- Generación de keys: `tools cloud generate-key`
- Rotación de keys automática
- Comandos: `--encrypt`, `--encryption-key`

#### Bandwidth Limiting

- Control de ancho de banda con token bucket algorithm
- Thread-safe para operaciones paralelas
- Límites configurables (KB/s, MB/s)
- Comando: `--bandwidth-limit 1000`

#### Multipart Uploads

- Uploads eficientes para archivos grandes
- Threshold configurable (default 100 MB)
- Retry automático de partes fallidas
- Comando: `--multipart-threshold 50`

#### Credential Management

- Almacenamiento seguro con keyring del sistema
- Fallback a cryptography si keyring no disponible
- Soporte para múltiples providers (AWS, Azure, GCP, DO, B2, MinIO)
- Comandos: `tools credentials {set|get|list|delete|test}`

#### Sync Direction Control

- Enum `SyncDirection`: DOWNLOAD, UPLOAD, BIDIRECTIONAL
- Control fino de sincronización
- Eliminación de archivos huérfanos según dirección
- Parámetro: `--direction {download|upload|bidirectional}`

### Added - Comandos Cloud Management

- `tools cloud list` - Listar archivos en bucket
- `tools cloud delete` - Eliminar archivos
- `tools cloud info` - Información de archivo
- `tools cloud copy` - Copiar entre buckets
- `tools cloud providers` - Ver providers disponibles y requisitos

### Added - Perfiles Cloud (YAML)

- Configuración mediante `~/.tools/cloud_profiles.yml`
- Perfiles reutilizables con todos los parámetros
- Variables de entorno en configuración
- Comando: `tools cloud sync --profile production`

### Changed

- **BREAKING**: Comando base cambió de `python -m tools.cli.main` a `tools`
- CLI más intuitivo y profesional
- Mejor logging con niveles trace/debug/info/warning/error
- Reportes en JSON, YAML, tabla, y simple text

### Testing

- ✅ 412 tests definidos en la suite
- ✅ Cobertura global reportada: 43% (ultima medicion documentada)
- ✅ Flake8 clean (0 violations)
- ✅ Type hints completos

### Documentation

- ✅ README.md completamente reescrito para v2.7.0
- ✅ ROADMAP.md con 3 opciones de completitud
- ✅ LEGACY_VERIFICATION_REPORT.md con análisis de migración

---

## [2.6.0] - 2026-03-07

### Added

- Migración completa de legacy directories a Python OOP
- Unificación de CLI bajo `tools` command
- Módulo `tools.system` completo desde bash scripts

### Changed

- Consolidación de 5 directorios legacy en `tools/` centralizado
- Eliminación de código bash redundante

### Removed

- `cloud/` legacy directory (→ `tools/cloud/`)
- `dns_tools/` legacy directory (→ `tools/dns/`)
- `mail_audit/` legacy directory (→ `tools/mail/`)
- `remote_management/` legacy directory (→ `tools/remote/`)
- `system_utils/` legacy directory (→ `tools/system/`)

### Migration

- 20+ bash scripts → 30+ Python modules (OOP)
- 100% feature parity verificada
- 3 scripts preservados en `scripts/legacy-review/` para revisión

---

## [2.5.0] - 2026-03-06

### Added

- Integración de cloud sync al CLI unificado
- Soporte para DigitalOcean Spaces
- Perfiles de configuración cloud

### Changed

- cloud sync ahora accesible vía `tools cloud sync`

---

## [2.4.0] - 2026-03-05

### Added - Cloud Storage Module

- Providers: AWS S3, Azure Blob, Google Cloud Storage
- Sincronización bidireccional
- Exclusión de archivos con patterns
- Workers paralelos configurables
- ACL (Access Control Lists) configurable

---

## [2.3.0] - 2026-03-04

### Added

- Módulo DNS Management (`tools dns`)
- DNS replication checking
- Zone file management
- NS record fixing
- Bind/PowerDNS installers

---

## [2.2.0] - 2026-03-03

### Added

- Módulo Mail Auditing (`tools mail`)
- Full mail server audits
- DNS validation (SPF, DKIM, DMARC)
- Domain health checking
- Quota management

---

## [2.1.0] - 2026-03-02

### Added

- Módulo Remote Management (`tools remote`)
- SSH execution (single/parallel hosts)
- File distribution con verificación
- Network scanning
- Interactive prompts para credenciales

---

## [2.0.0] - 2026-03-01

### Added 🎉 - CLI Unificado

- CLI framework completo con `tools` command
- Logging centralizado con niveles configurables
- Config management (YAML profiles)
- Multiple output formats (JSON, YAML, table, simple)

### Breaking Changes

- Nueva estructura de comandos: `tools <module> <action>`
- Configuración movida a `~/.tools/`
- Sintaxis anterior deprecada

---

## [1.2.0] - 2026-02-28

### Added

- System utilities module (`tools system`)
- Timezone configuration
- File operations (delete empty, merge)
- PAM management con hardening profiles

---

## [1.1.0] - 2026-02-27

### Added

- Testing framework con pytest
- Coverage reports
- Flake8 linting
- Black code formatting

---

## [1.0.0] - 2026-02-26

### Added 🎉 - Initial Release

- Estructura base del proyecto
- Scripts bash legacy iniciales:
  - `exec_ssh.sh` - Remote command execution
  - `download_space.py` - Cloud space download
  - `mail_audit.sh` - Mail server auditing
  - Helper scripts (timezone, files, hosts)

---

## Convenciones de Versionado

- **MAJOR** (X.0.0): Breaking changes, arquitectura nueva
- **MINOR** (x.X.0): Nuevas features, backwards compatible
- **PATCH** (x.x.X): Bug fixes, mejoras menores

## Tipos de Cambios

- `Added` - Nuevas características
- `Changed` - Cambios en funcionalidad existente
- `Deprecated` - Características que serán removidas
- `Removed` - Características removidas
- `Fixed` - Bug fixes
- `Security` - Vulnerabilidades corregidas

---

**Última actualización:** Marzo 8, 2026  
**Versión actual:** 2.7.0  
**Próxima versión planeada:** 3.0.0 (con 5 módulos nuevos - Opción C)
