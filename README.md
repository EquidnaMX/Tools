# Tools - Admin Toolkit v2.7.0

[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-411%20passing-brightgreen.svg)](tests/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code style](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Toolkit profesional de administración de sistemas con CLI unificado para gestión remota, cloud storage multi-proveedor, auditoría de mail, DNS management y utilidades de sistema.

**Features principales:**

- 🚀 CLI unificado con 7 módulos integrados
- ☁️ Multi-cloud storage (AWS, Azure, GCP, DigitalOcean, B2, MinIO)
- 🔒 Optimizaciones avanzadas (cache, compression, encryption, bandwidth limiting)
- 🔐 Gestión segura de credenciales con keyring
- 🧪 417 tests totales (416 passed, 1 skipped)
- 📦 Arquitectura Python OOP moderna y extensible

## � Quick Start

```bash
# 1. Clonar el repositorio
git clone https://github.com/gruelasjr/Tools.git
cd Tools

# 2. Crear entorno virtual e instalar dependencias
python -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

# 3. Instalar el paquete en modo desarrollo
pip install -e .

# 4. Usar el CLI
tools --help
tools cloud sync --profile production_backups
tools remote exec "uptime" --hosts 192.168.1.10
tools mail audit --domain example.com
```

## 📁 Estructura del Proyecto

```
Tools/                          # Toolkit completo v2.7.0
├── tools/                      # 🐍 Módulos Python principales
│   ├── cli/                   # CLI unificado
│   │   ├── main.py           # Entry point: `tools` or `python -m tools.cli.main`
│   │   ├── cloud_commands.py # tools cloud [sync|upload|list|delete|info|credentials]
│   │   ├── remote_commands.py # tools remote [exec|upload|scan]
│   │   ├── mail_commands.py  # tools mail [audit|check-domain|validate-dns]
│   │   ├── dns_commands.py   # tools dns [check-replication|fix-ns|install]
│   │   └── system_commands.py # tools system [timezone|files|pam]
│   │
│   ├── core/                  # 🔧 Utilidades compartidas
│   │   ├── logger.py         # Sistema de logging centralizado
│   │   ├── config.py         # Gestión de configuración
│   │   ├── reporter.py       # Reportes JSON/CSV/Table
│   │   └── exceptions.py     # Excepciones personalizadas
│   │
│   ├── cloud/                # ☁️ Multi-cloud storage (v2.7.0)
│   │   ├── providers.py      # CloudProvider base class
│   │   ├── aws_s3.py         # AWS S3 implementation
│   │   ├── azure_blob.py     # Azure Blob Storage
│   │   ├── google_cloud.py   # Google Cloud Storage
│   │   ├── digitalocean.py   # DigitalOcean Spaces
│   │   ├── backblaze.py      # Backblaze B2
│   │   ├── minio.py          # MinIO
│   │   ├── factory.py        # Provider factory
│   │   ├── cache.py          # 🆕 SQLite caching system
│   │   ├── compression.py    # 🆕 gzip/lz4 compression
│   │   ├── encryption.py     # 🆕 AES-256-GCM encryption
│   │   ├── bandwidth.py      # 🆕 Bandwidth limiting
│   │   ├── credentials.py    # 🆕 Credential management
│   │   ├── config_manager.py # YAML profile management
│   │   ├── README.md         # Documentación completa
│   │   ├── MIGRATION.md      # 🆕 Migration guide
│   │   └── CHANGELOG.md      # 🆕 Changelog v2.7.0
│   │
│   ├── remote/               # 🔗 Gestión remota SSH
│   │   ├── ssh_executor.py  # Ejecución SSH paralela
│   │   ├── file_distributor.py # Distribución de archivos
│   │   └── network_scanner.py  # Escaneo de redes
│   │
│   ├── mail/                 # 📧 Auditoría de mail server
│   │   ├── auditor.py        # Auditoría de servicios
│   │   ├── dns_validator.py  # Validación DNS (MX/SPF/DKIM/DMARC)
│   │   ├── domain_health.py  # Health checking de dominios
│   │   └── service_monitor.py # Monitoreo de servicios
│   │
│   ├── dns/                  # 🌐 Gestión DNS
│   │   ├── replication_checker.py # Verificación replicación
│   │   ├── ns_fixer.py       # Corrección de NS records
│   │   ├── installer.py      # Instalación BIND9/PowerDNS
│   │   └── zone_manager.py   # Gestión de zonas
│   │
│   ├── system/               # ⚙️ Utilidades de sistema
│   │   ├── timezone_manager.py # Timezone cross-platform
│   │   ├── file_manager.py   # File operations (cleanup, merge)
│   │   ├── pam_manager.py    # PAM configuration management
│   │   └── README.md         # Documentación completa
│   │
│   ├── backup/               # 💾 Backups locales con rotación
│   │   ├── manager.py        # Creación, restore y políticas de retención
│   │   └── __init__.py
│   │
│   └── __init__.py           # Package exports
│
├── tests/                      # 🧪 Suite de tests (417 tests totales)
│   ├── backup/                # Tests backup module
│   ├── cloud/                 # Tests cloud module
│   ├── remote/                # Tests remote module
│   ├── mail/                  # Tests mail module
│   ├── dns/                   # Tests DNS module
│   ├── system/                # Tests system module
│   └── __init__.py
│
├── examples/                   # 📚 Ejemplos de uso
│   ├── cloud.py               # Ejemplos cloud storage
│   ├── remote.py              # Ejemplos remote management
│   ├── mail.py                # Ejemplos mail auditing
│   ├── dns.py                 # Ejemplos DNS management
│   └── system.py              # Ejemplos system utilities
│
├── scripts/                    # 🛠️ Scripts auxiliares
│   ├── install.sh            # Script de instalación Linux/Mac
│   ├── install.ps1           # Script de instalación Windows
│   └── legacy-review/        # Scripts legacy para revisión
│
├── .github/                    # 🔄 CI/CD
│   └── workflows/
│       └── tests.yml         # GitHub Actions workflow
│
├── .flake8                   # Configuración linting
├── .gitignore                # Git ignore rules
├── pytest.ini                # Configuración pytest
├── pyproject.toml            # Proyecto Python
├── setup.py                  # Instalación del paquete
├── requirements-dev.txt      # Dependencias (dev + runtime)
├── README.md                 # Esta documentación
├── CHANGELOG.md              # Historial de cambios
├── ROADMAP.md                # Roadmap de desarrollo
├── LEGACY_VERIFICATION_REPORT.md  # Reporte de migración legacy
└── cloud_profiles.example.yml     # Ejemplo de perfiles cloud
```

## � Instalación

### Requisitos

- **Python 3.8+** (recomendado 3.10+)
- **pip** package manager
- **Sistema operativo:** Linux, macOS, Windows (con PowerShell)

### Dependencias del Sistema (Opcional)

Algunas funcionalidades requieren herramientas del sistema:

```bash
# Linux (Debian/Ubuntu)
sudo apt install ssh openssh-client dnsutils

# macOS (con Homebrew)
brew install openssh bind

# Windows (con chocolatey)
choco install openssh
```

### Instalación del Toolkit

#### Opción 1: Instalación en modo desarrollo (Recomendada)

```bash
# 1. Clonar repositorio
git clone https://github.com/gruelasjr/Tools.git
cd Tools

# 2. Crear entorno virtual
python -m venv .venv

# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1

# 3. Instalar dependencias
pip install -r requirements-dev.txt

# 4. Instalar paquete en modo editable
pip install -e .

# 5. Verificar instalación
tools --version
tools --help
```

#### Opción 2: Instalación con script automático

```bash
# Linux/macOS
./scripts/install.sh

# Windows PowerShell
.\scripts\install.ps1
```

#### Opción 3: Instalación directa (solo runtime)

```bash
pip install git+https://github.com/gruelasjr/Tools.git
```

### Verificación de Instalación

```bash
# Verificar que el comando 'tools' está disponible
tools --version
# Output: Tools Admin Toolkit v2.7.0

# Listar comandos disponibles
tools --help

# Ejecutar tests
pytest tests/ -v

# Verificar coverage
pytest --cov=tools --cov-report=html
```

### Workflow de Desarrollo

```bash
# Instalar dependencias de desarrollo
make install-dev

# Calidad de código
make lint
make format
make quality

# Pre-commit hooks
make pre-commit-install
make pre-commit
```

## 🎯 Uso del CLI

El toolkit proporciona un CLI unificado con 7 módulos principales:

### 1. ☁️ Cloud Storage (Multi-Provider)

**Proveedores soportados:** AWS S3, Azure Blob, Google Cloud Storage, DigitalOcean Spaces, Backblaze B2, MinIO

#### Sincronización (Download)

```bash
# Sync usando perfil YAML
tools cloud sync --profile production_backups

# Sync con argumentos directos
tools cloud sync \
  --provider aws \
  --bucket my-bucket \
  --region us-east-1 \
  --dest ./backup \
  --workers 24

# Sync con cache (evita re-descargar archivos sin cambios)
tools cloud sync --profile prod --use-cache

# Sync con compresión gzip
tools cloud sync --profile prod --compress --compression-type gzip

# Sync con encriptación AES-256
tools cloud sync --profile prod --encrypt --encryption-key $(openssl rand -hex 32)

# Sync con bandwidth limiting (500 KB/s)
tools cloud sync --profile prod --bandwidth-limit 500

# Modo espejo (elimina archivos locales huérfanos)
tools cloud sync --profile prod --delete --sync-direction download

# Simulación sin descargar
tools cloud sync --profile dev --dry-run
```

#### Upload (Subida de Archivos)

```bash
# Upload usando perfil
tools cloud upload ./backups --profile production_uploads

# Upload con argumentos directos
tools cloud upload ./data \
  --provider s3 \
  --bucket my-bucket \
  --region us-east-1 \
  --dest backups/daily

# Upload con multipart (archivos >100MB)
tools cloud upload ./large_files \
  --profile prod \
  --multipart-threshold 100

# Upload con compresión y encriptación
tools cloud upload ./sensitive_data \
  --profile secure \
  --compress \
  --encrypt \
  --encryption-key $ENCRYPTION_KEY

# Upload con ACL público
tools cloud upload ./public \
  --profile web_assets \
  --acl public-read
```

#### Gestión de Archivos Cloud

```bash
# Listar objetos en bucket
tools cloud list --profile prod
tools cloud list --profile prod --prefix backups/ --format json

# Información de bucket
tools cloud info --profile prod

# Eliminar objetos
tools cloud delete --profile prod --keys file1.txt file2.txt
tools cloud delete --profile prod --prefix old_backups/ --confirm

# Copiar entre buckets
tools cloud copy \
  --source-profile prod \
  --dest-profile staging \
  --keys important_data.zip
```

#### Gestión de Credenciales

```bash
# Ver providers disponibles y sus requisitos
tools cloud providers
tools cloud credentials aws

# Gestionar credenciales (almacenadas de forma segura en keyring)
tools credentials set aws_prod \
  --provider aws \
  --key AWS_ACCESS_KEY_ID=AKIA... \
  --key AWS_SECRET_ACCESS_KEY=...

tools credentials list
tools credentials get aws_prod
tools credentials delete aws_prod
tools credentials test aws_prod
```

#### Perfiles Cloud (YAML)

Crea `~/.tools/cloud_profiles.yml`:

```yaml
production_backups:
  description: "Production database backups"
  provider: aws
  bucket: prod-backups
  region: us-east-1
  dest: ~/backups/production
  workers: 24
  use_cache: true
  compress: true
  compression_type: lz4
  bandwidth_limit: 1000 # KB/s
  exclude:
    - "*.tmp"
    - "*.log"

secure_storage:
  description: "Encrypted sensitive data"
  provider: s3
  bucket: secure-vault
  region: us-west-2
  dest: ~/secure
  encrypt: true
  encryption_key: ${ENCRYPTION_KEY} # From environment
  multipart_threshold: 50 # MB
```

Ver documentación completa: [tools/cloud/README.md](tools/cloud/README.md)

---

### 2. 🔗 Remote Management (SSH)

#### Ejecución de Comandos

```bash
# Ejecutar comando en un host
tools remote exec "uptime" --hosts 192.168.1.10 --user admin

# Ejecución paralela en múltiples hosts
tools remote exec "df -h" \
  --hosts 192.168.1.10,192.168.1.11,192.168.1.12 \
  --user admin \
  --parallel

# Con clave SSH privada
tools remote exec "systemctl status nginx" \
  --hosts web1.example.com \
  --user deploy \
  --key ~/.ssh/deploy_key

# Guardar output en archivo
tools remote exec "ps aux" \
  --hosts server1,server2 \
  --output results.json \
  --format json
```

#### Distribución de Archivos

```bash
# Subir archivo a múltiples servidores
tools remote upload /local/app.tar.gz \
  --hosts 10.0.0.5,10.0.0.6,10.0.0.7 \
  --dest /opt/apps/ \
  --user deploy

# Con verificación checksums
tools remote upload ./config.yml \
  --hosts web1,web2,web3 \
  --dest /etc/myapp/ \
  --verify
```

#### Escaneo de Red

```bash
# Escanear rango de IPs
tools remote scan 192.168.1.0/24

# Escanear puertos específicos
tools remote scan 10.0.0.0/24 --ports 22,80,443

# Output en JSON
tools remote scan 172.16.0.0/16 --output scan_results.json
```

---

### 3. 📧 Mail Server Auditing

#### Auditoría Completa

```bash
# Auditoría de dominio mail
tools mail audit --domain example.com --server-ip 203.0.113.5

# Auditoría de servidor completo
tools mail audit-server \
  --server-ip 203.0.113.5 \
  --ptr-target mail.example.com \
  --domains example.com,example.net

# Con output JSON
tools mail audit --domain example.com --output audit_report.json
```

#### Validación DNS

```bash
# Validar registros DNS de dominio
tools mail validate-dns example.com

# Validar con DKIM selector específico
tools mail validate-dns example.com --dkim-selector default

# Verificar múltiples dominios
tools mail validate-dns example.com,example.net,example.org
```

#### Health Check de Dominios

```bash
# Verificar salud de dominio
tools mail check-domain example.com

# Check con timeout personalizado
tools mail check-domain example.com --timeout 10

# Verificar conectividad SMTP
tools mail check-domain example.com --check-smtp
```

---

### 4. 🌐 DNS Management

#### Verificación de Replicación

```bash
# Verificar replicación master-slave
tools dns check-replication \
  --master 10.0.0.1 \
  --slaves 10.0.0.2,10.0.0.3 \
  --zone example.com

# Con output detallado
tools dns check-replication \
  --master ns1.example.com \
  --slaves ns2.example.com,ns3.example.com \
  --zone example.com \
  --verbose
```

#### Corrección de NS Records

```bash
# Verificar y corregir NS records faltantes
tools dns fix-ns --zone example.com --nameservers ns1.example.com,ns2.example.com

# Modo dry-run (solo verificar)
tools dns fix-ns --zone example.com --dry-run
```

#### Instalación de Servidores DNS

```bash
# Instalar BIND9 slave
tools dns install bind9-slave \
  --master-ip 10.0.0.1 \
  --zone example.com

# Instalar PowerDNS master
tools dns install pdns-master \
  --db-host localhost \
  --db-name pdns
```

---

### 5. ⚙️ System Utilities

#### Gestión de Timezone

```bash
# Ver timezone actual
tools system timezone get

# Cambiar timezone
tools system timezone set America/Mexico_City

# Listar timezones disponibles
tools system timezone list

# Filtrar por región
tools system timezone list --filter America

# Información detallada
tools system timezone info
```

#### Operaciones con Archivos

```bash
# Limpiar archivos vacíos
tools system files clean-empty /var/log --dry-run
tools system files clean-empty /tmp --confirm

# Combinar archivos
tools system files merge ./logs output.log --exclude-empty

# Buscar archivos
tools system files find /home --pattern "*.log" --older-than 30

# Estadísticas de directorio
tools system files stats ./project
```

#### Gestión PAM (Pluggable Authentication Modules)

```bash
# Listar archivos PAM
tools system pam list

# Ver configuración de servicio
tools system pam show sshd

# Verificar módulo en servicio
tools system pam check sshd --module pam_faillock.so

# Backup de configuración
tools system pam backup --output ~/pam_backup

# Hardening de seguridad
tools system pam harden --profile strict --preview
tools system pam harden --profile moderate --apply
```

Ver documentación completa: [tools/system/README.md](tools/system/README.md)

---

### 6. 💾 Backup con Rotación

```bash
# Crear backup y mantener solo los 7 más nuevos
tools backup create ./data --backup-dir ./backups --name daily --keep 7

# Listar backups
tools backup list --backup-dir ./backups --prefix daily

# Aplicar rotación explícita
tools backup rotate --backup-dir ./backups --prefix daily --keep 7

# Restaurar backup
tools backup restore ./backups/daily_20260309_120000_000001.tar.gz --destination ./restore --overwrite
```

---

### 7. ⚙️ Configuration Management

```bash
# Listar perfiles disponibles
tools config list

# Ver perfil específico
tools config show production

# Validar configuración
tools config validate ~/.tools/cloud_profiles.yml
```

## 📖 Documentación Detallada

- [**tools/cloud/README.md**](tools/cloud/README.md) - Cloud storage multi-provider v2.7.0
- [**tools/cloud/CHANGELOG.md**](tools/cloud/CHANGELOG.md) - Historial de cambios cloud module
- [**tools/cloud/MIGRATION.md**](tools/cloud/MIGRATION.md) - Guía de migración entre versiones
- [**tools/system/README.md**](tools/system/README.md) - System utilities documentation
- [**ROADMAP.md**](ROADMAP.md) - Roadmap de desarrollo futuro
- [**CHANGELOG.md**](CHANGELOG.md) - Changelog general del proyecto
- [**LEGACY_VERIFICATION_REPORT.md**](LEGACY_VERIFICATION_REPORT.md) - Reporte de migración legacy→Python

## ✨ Características v2.7.0 (Marzo 2026)

### 🆕 Optimizaciones Avanzadas

#### 1. Sistema de Cache SQLite

- **Cache persistente** de metadatos de archivos cloud
- **Evita re-descargas** innecesarias (verifica checksums)
- **Estadísticas** de cache hits/misses
- **Uso:** `tools cloud sync --profile prod --use-cache`

#### 2. Compresión de Archivos

- **Algoritmos soportados:** gzip (estándar), lz4 (rápido)
- **Detección inteligente:** comprime solo si reduce tamaño >10%
- **Skip automático:** archivos ya comprimidos (.gz, .zip, .jpg, .mp4)
- **Uso:** `tools cloud sync --profile prod --compress --compression-type lz4`

#### 3. Encriptación AES-256-GCM

- **Encriptación autenticada** con AES-256-GCM
- **Generación automática** de claves encryption
- **Key derivation** con PBKDF2 desde passwords
- **Unique nonces** por archivo para seguridad
- **Uso:** `tools cloud sync --profile prod --encrypt --encryption-key $KEY`

#### 4. Bandwidth Limiting

- **Token bucket algorithm** para rate limiting preciso
- **Thread-safe** para operaciones paralelas
- **Configuración:** KB/s límite de transferencia
- **Uso:** `tools cloud sync --profile prod --bandwidth-limit 500`

#### 5. Multipart Uploads

- **Uploads eficientes** de archivos grandes (>100MB)
- **Upload paralelo** de chunks para velocidad
- **Threshold configurable** por perfil
- **Uso:** `tools cloud upload --profile prod --multipart-threshold 100`

#### 6. Gestión de Credenciales

- **Almacenamiento seguro** con keyring del sistema
- **Fallback encryption** con cryptography si keyring no disponible
- **Multi-provider:** soporta credenciales para todos los providers
- **CLI completo:** `tools credentials set/list/get/delete/test`

#### 7. Control de Dirección de Sync

- **SyncDirection enum:** DOWNLOAD, UPLOAD, BIDIRECTIONAL
- **Control granular** de eliminación de archivos huérfanos
- **Modo espejo seguro** con confirmación
- **Uso:** `tools cloud sync --profile prod --delete --sync-direction download`

### 🏗️ Arquitectura y Migración

#### Migración Legacy a Python OOP

- ✅ **5 directorios legacy eliminados** (cloud/, dns_tools/, mail_audit/, remote_management/, system_utils/)
- ✅ **20 scripts Bash → 30 módulos Python** con arquitectura OOP
- ✅ **Feature parity** 100% verificado para todos los módulos
- ✅ **3 scripts preservados** en `scripts/legacy-review/` para revisión

#### Multi-Cloud Support

- ✅ **6 providers cloud:** AWS S3, Azure Blob, Google Cloud Storage, DigitalOcean Spaces, Backblaze B2, MinIO
- ✅ **API unificada** con CloudProvider base class
- ✅ **Factory pattern** para creación dinámica de providers
- ✅ **Credential validation** per-provider

### 📊 Testing y Calidad

- ✅ **417 tests totales** (416 passed, 1 skipped)
- ✅ **Compatibilidad cloud retroactiva** para imports y APIs legacy
- ✅ **Flake8 clean** (0 violations)
- ✅ **Type hints** en funciones críticas
- ✅ **CI/CD ready** con GitHub Actions

## 🔐 Seguridad

- ✅ **Validación de entrada** en todos los módulos
- ✅ **Encriptación AES-256-GCM** para datos sensibles
- ✅ **Gestión segura de credenciales** con keyring del sistema
- ✅ **SSH key-based authentication** para remote management
- ✅ **Sanitización de comandos** contra inyección
- ✅ **PAM hardening** con perfiles de seguridad

## 🤝 Contribuciones

Repositorio personal de herramientas administrativas. Para mejoras o sugerencias:

1. Fork del repositorio
2. Crear feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit cambios (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Abrir Pull Request

## 🎯 Estado del Proyecto v2.7.0

### ✅ Completado (Production Ready)

#### Módulos Core

- ✅ **CLI Unificado** - 7 módulos principales integrados
- ✅ **Cloud Storage** - Multi-provider con 6 clouds soportados
- ✅ **Remote Management** - SSH execution, file distribution, network scanning
- ✅ **Mail Auditing** - Domain validation, DNS checks, health monitoring
- ✅ **DNS Management** - Replication checking, zone management, installers
- ✅ **System Utilities** - Timezone, file operations, PAM management

#### Features Avanzadas

- ✅ **Cache System** - SQLite persistent caching
- ✅ **Compression** - gzip/lz4 with smart detection
- ✅ **Encryption** - AES-256-GCM authenticated encryption
- ✅ **Bandwidth Limiting** - Token bucket rate limiting
- ✅ **Multipart Uploads** - Efficient large file handling
- ✅ **Credential Management** - Secure keyring storage

#### Testing y Calidad

- ✅ **417 Unit Tests** - 416 passed, 1 skipped
- ✅ **Cloud tests modernizados** - Sin shims/aliases legacy
- ✅ **Flake8 Clean** - Zero linting violations
- ✅ **Type Hints** - Better IDE support and type safety

#### Documentación

- ✅ **README.md** - Complete project documentation
- ✅ **module READMEs** - Per-module detailed docs
- ✅ **CHANGELOG.md** (cloud) - Change history
- ✅ **MIGRATION.md** (cloud) - Migration guides
- ✅ **ROADMAP.md** - Development roadmap

### 🚧 En Progreso (Opción C - Toolkit Enterprise)

#### Semana 1: Base Production-Ready

- ⏳ **CHANGELOG.md General** - Proyecto-wide changelog
- ⏳ **Ejemplos de Uso** - 5 example files (cloud, remote, mail, dns, system)
- ⏳ **API Documentation** - Sphinx/MkDocs auto-generated docs
- ✅ **Scripts de Instalación** - install.sh, install.ps1
- ✅ **CI/CD** - GitHub Actions workflow for tests
- ✅ **Makefile** - Common development tasks
- ✅ **Pre-commit Hooks** - Automated quality checks

#### Semana 2-3: Módulos Nuevos

- 📦 **tools/backup/** - Backup automation module
  - Local, S3, rsync destinations
  - Scheduling and rotation
  - Compression and encryption
  - CLI: `tools backup create/restore/list/schedule`

- 📊 **tools/monitoring/** - System monitoring module
  - System metrics (CPU, RAM, disk, network)
  - Health checks
  - Alerting (email, webhook)
  - CLI: `tools monitor start/status/alerts/metrics`

- 🗄️ **tools/database/** - Database management module
  - PostgreSQL, MySQL, MongoDB support
  - Backups, migrations, replication checks
  - CLI: `tools db backup/restore/migrate/check`

#### Semana 4: Módulos Finales

- 🐳 **tools/containers/** - Container utilities module
  - Docker/Podman management
  - Container lifecycle
  - Image management
  - CLI: `tools containers deploy/stop/logs/cleanup`

- 🔒 **tools/security/** - Security utilities module
  - SSL/TLS certificate management
  - Firewall configuration
  - Security auditing and vulnerability scanning
  - CLI: `tools security audit/certs/firewall/scan`

## 📅 Roadmap Completo

Ver [ROADMAP.md](ROADMAP.md) para detalles completos del plan de desarrollo.

## 📜 Licencia

MIT License - Ver [LICENSE](LICENSE) para detalles.

## 👤 Autor

**gruelasjr**

- GitHub: [@gruelasjr](https://github.com/gruel asjr)
- Repository: [Tools](https://github.com/gruelasjr/Tools)

---

**Versión:** 2.7.0
**Última actualización:** Marzo 8, 2026
**Estado:** Production-Ready (Base) + Enterprise Extensions (En Progreso)
