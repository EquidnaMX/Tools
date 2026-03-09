# LDAP Client Authentication Module

Módulo completo para configuración de autenticación LDAP remota en sistemas Linux mediante PAM (Pluggable Authentication Modules).

## 🎯 Características

- **Dual Mode Support**: NSLCD (NSS-LDAP Connection Daemon) y SSSD (System Security Services Daemon)
- **Configuración PAM completa**: common-auth, common-account, common-password, common-session, su
- **Control de acceso por grupos**: Restricción a grupos LDAP específicos
- **Backup automático**: Copia de seguridad con timestamp de todos los archivos modificados
- **Dry-run mode**: Simula cambios sin aplicarlos
- **Script generation**: Genera script bash standalone equivalente
- **TLS Support**: Conexiones seguras con certificados
- **Creación automática de home directories**: Con configuración de umask

## 📋 Requisitos

### Sistema Operativo
- Debian/Ubuntu Linux (otras distros require ajustes)
- Python 3.8+

### Dependencias Python
```bash
pip install pyyaml
pip install python-ldap  # Opcional: para test-connection
```

### Paquetes del Sistema
Se instalan automáticamente durante la configuración:

**Modo NSLCD:**
- libpam-ldapd
- nslcd
- nscd (cache)

**Modo SSSD:**
- sssd
- sssd-ldap
- libpam-sss
- libnss-sss

## 🚀 Uso Básico

### 1. Configuración Simple (NSLCD)

```bash
tools ldap configure-client \
  --ldap-uri ldap://ldap.example.com \
  --base-dn dc=example,dc=com \
  -g server-admin \
  -g desarrollo
```

Esto configurará:
- Cliente LDAP con NSLCD
- Autenticación PAM para usuarios LDAP
- Acceso restringido a grupos `server-admin` y `desarrollo`
- Creación automática de home directories

### 2. Configuración con SSSD y TLS

```bash
tools ldap configure-client \
  --ldap-uri ldaps://ldap.example.com:636 \
  --base-dn dc=example,dc=com \
  --bind-dn cn=readonly,dc=example,dc=com \
  --bind-password MySecretPassword \
  --mode sssd \
  --use-tls \
  --create-homedir
```

### 3. Modo Dry-Run (Simular sin Aplicar)

```bash
tools ldap configure-client \
  --ldap-uri ldap://ldap.example.com \
  --base-dn dc=example,dc=com \
  --dry-run
```

Muestra todos los cambios que se realizarían sin modificar el sistema.

### 4. Generar Script Bash Standalone

```bash
tools ldap configure-client \
  --ldap-uri ldap://ldap.example.com \
  --base-dn dc=example,dc=com \
  -g admins \
  --output-script /tmp/configure_ldap.sh

# Ejecutar en servidor remoto
chmod +x /tmp/configure_ldap.sh
sudo /tmp/configure_ldap.sh
```

### 5. Probar Conexión LDAP

```bash
tools ldap test-connection \
  --ldap-uri ldap://ldap.example.com \
  --base-dn dc=example,dc=com \
  --bind-dn cn=admin,dc=example,dc=com \
  --bind-password secret
```

### 6. Generar Archivo de Configuración YAML

```bash
# Generar template
tools ldap generate-config -o ldap_config.yml

# Editar el archivo
vim ldap_config.yml

# Usar el archivo (feature futura)
tools ldap configure-client --config ldap_config.yml
```

## 🔧 Opciones Avanzadas

### Todas las Opciones de configure-client

```
--ldap-uri TEXT              URI del servidor LDAP (requerido)
                             Ejemplos: ldap://ldap.example.com
                                      ldaps://ldap.example.com:636

--base-dn TEXT               Base DN de búsqueda (requerido)
                             Ejemplo: dc=example,dc=com

--bind-dn TEXT               DN para bind autenticado (opcional)
                             Ejemplo: cn=readonly,dc=example,dc=com

--bind-password TEXT         Password para bind DN (opcional)

-g, --allowed-group TEXT     Grupos LDAP permitidos (múltiple)
                             Por defecto: server-admin, desarrollo
                             Ejemplo: -g admins -g users -g operators

--mode [nslcd|sssd]          Modo de cliente LDAP (default: nslcd)

--use-tls / --no-tls         Habilitar/deshabilitar TLS (default: enabled)

--create-homedir / --no-create-homedir
                             Crear home directories automáticamente
                             (default: enabled)

--password-hash TEXT         Algoritmo de hash de password
                             Opciones: yescrypt, sha512, sha256
                             (default: yescrypt)

--dry-run                    Simular sin aplicar cambios

--output-script PATH         Generar script bash en vez de ejecutar
```

## 📖 NSLCD vs SSSD

### ¿Cuándo usar NSLCD?

- **Simplicidad**: Configuración más sencilla
- **Uso de recursos**: Menor consumo de memoria
- **Casos básicos**: Autenticación LDAP sin funcionalidades avanzadas

### ¿Cuándo usar SSSD?

- **Cache offline**: Los usuarios pueden autenticarse sin conexión al LDAP
- **Multiple domains**: Soporte para múltiples dominios/backends
- **Active Directory**: Mejor integración con AD
- **Smart card**: Soporte para autenticación con tarjetas inteligentes
- **Sudo rules**: Gestión de reglas sudo desde LDAP

## 🔄 Proceso de Instalación

El instalador realiza los siguientes pasos:

1. **Instalación de paquetes** (apt-get install)
2. **Backup de archivos** de configuración existentes
3. **Configuración de PAM**:
   - `/etc/pam.d/common-auth` - Autenticación
   - `/etc/pam.d/common-account` - Validación de cuenta
   - `/etc/pam.d/common-password` - Cambio de passwords
   - `/etc/pam.d/common-session` - Sesión y home directory
   - `/etc/pam.d/su` - Comando su
4. **Configuración de NSSwitch** (`/etc/nsswitch.conf`)
5. **Configuración NSLCD** (`/etc/nslcd.conf`) o **SSSD** (`/etc/sssd/sssd.conf`)
6. **Reinicio de servicios**:
   - NSLCD: `nslcd`, `nscd`
   - SSSD: `sssd`

## 💾 Backups

Todos los archivos modificados se respaldan automáticamente con el formato:

```
<archivo_original>.bak_YYYYMMDD_HHMMSS
```

Ejemplo:
```
/etc/pam.d/common-auth.bak_20260309_143022
/etc/nslcd.conf.bak_20260309_143022
```

Para restaurar:
```bash
sudo cp /etc/pam.d/common-auth.bak_20260309_143022 /etc/pam.d/common-auth
sudo systemctl restart nslcd nscd
```

## 🔐 Seguridad

### Grupos Permitidos

El control de acceso se implementa en `/etc/pam.d/common-auth` usando `pam_listfile`:

```
auth required pam_listfile.so onerr=fail item=group sense=allow file=/etc/security/ldap_groups
```

Donde `/etc/security/ldap_groups` contiene:
```
server-admin
desarrollo
```

### Permisos de Archivos

- `/etc/nslcd.conf`: `0600` (solo root)
- `/etc/sssd/sssd.conf`: `0600` (solo root)
- `/etc/security/ldap_groups`: `0644` (lectura todos)

### Passwords en Bind DN

⚠️ **Advertencia**: Si usas `--bind-dn` y `--bind-password`, el password se almacena en texto plano en:
- `/etc/nslcd.conf` (NSLCD)
- `/etc/sssd/sssd.conf` (SSSD)

**Recomendaciones:**
1. Usar una cuenta de solo lectura (readonly)
2. Permisos `0600` en archivos de config (aplicados automáticamente)
3. Considerar SSSD con Kerberos para entornos productivos

## 🧪 Testing

### Tests Unitarios

```bash
# Tests del módulo LDAP
pytest tests/ldap/ -v

# Tests del instalador
pytest tests/ldap/test_ldap_client_installer.py -v

# Tests CLI
pytest tests/ldap/test_ldap_commands.py -v
```

### Cobertura

```bash
pytest tests/ldap/ --cov=tools.ldap --cov-report=html
```

## 📝 Ejemplos de Configuración

### Ejemplo 1: Configuración Básica Corporativa

```bash
tools ldap configure-client \
  --ldap-uri ldap://ldap.corp.example.com \
  --base-dn dc=corp,dc=example,dc=com \
  -g sysadmins \
  -g developers \
  -g support \
  --mode nslcd \
  --create-homedir
```

### Ejemplo 2: SSSD con TLS y Bind Autenticado

```bash
tools ldap configure-client \
  --ldap-uri ldaps://ldap.secure.example.com:636 \
  --base-dn dc=secure,dc=example,dc=com \
  --bind-dn cn=service-account,ou=services,dc=secure,dc=example,dc=com \
  --bind-password $(cat ~/.ldap_bind_password) \
  --mode sssd \
  --use-tls \
  -g it-team \
  -g management
```

### Ejemplo 3: Generar Script para Deployment Automatizado

```bash
# Generar script
tools ldap configure-client \
  --ldap-uri ldap://ldap.example.com \
  --base-dn dc=example,dc=com \
  -g admins \
  --output-script deploy_ldap.sh

# Distribuir a múltiples servidores
for host in server1 server2 server3; do
  scp deploy_ldap.sh root@${host}:/tmp/
  ssh root@${host} "bash /tmp/deploy_ldap.sh"
done
```

## 🐛 Troubleshooting

### Error: Cannot connect to LDAP server

```bash
# Probar conexión manual
tools ldap test-connection \
  --ldap-uri ldap://ldap.example.com \
  --base-dn dc=example,dc=com

# Ver logs NSLCD
sudo journalctl -u nslcd -f

# Ver logs SSSD
sudo journalctl -u sssd -f
sudo tail -f /var/log/sssd/sssd.log
```

### Error: User can login but no home directory

- Verificar `/etc/pam.d/common-session` tiene `pam_mkhomedir`
- Verificar permisos en `/home`
- Revisar: `tools ldap configure-client ... --create-homedir`

### Error: All LDAP users can login (groups filter not working)

- Verificar `/etc/security/ldap_groups` existe y contiene los grupos
- Verificar permisos: `chmod 644 /etc/security/ldap_groups`
- Revisar `/etc/pam.d/common-auth` tiene la línea `pam_listfile`

### Error: Permission denied after configuration

- **Restaurar desde backup**:
  ```bash
  sudo cp /etc/pam.d/common-auth.bak_YYYYMMDD_HHMMSS /etc/pam.d/common-auth
  sudo systemctl restart nslcd nscd
  ```

## 🔗 Referencias

- [NSLCD Documentation](https://arthurdejong.org/nss-pam-ldapd/)
- [SSSD Documentation](https://sssd.io/)
- [PAM Configuration](https://linux.die.net/man/5/pam.conf)
- [NSSwitch Configuration](https://man7.org/linux/man-pages/man5/nsswitch.conf.5.html)

## 📜 Licencia

MIT License - Ver archivo LICENSE del proyecto principal.

## 👨‍💻 Autor

gruelasjr - Tools Admin Toolkit v2.9.0
