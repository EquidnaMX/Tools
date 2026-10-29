# Cliente LDAP, PAM y reglas sudoers

Genera planes y scripts para Debian/Ubuntu con NSLCD o SSSD. No configura ningún servidor al importar el módulo.

## Estado y aplicación

La ejecución directa de `tools ldap configure-client` está deshabilitada: devuelve un error porque no existe un backend de aplicación validado. Tampoco acepta una instalación remota simulándola como local. Usar una de estas dos modalidades:

```bash
# Revisar el plan sin modificar archivos, paquetes ni servicios
tools ldap configure-client --ldap-uri ldap://ldap.example.com --base-dn dc=example,dc=com --dry-run

# Generar un script; revisarlo antes de ejecutarlo como root
tools ldap configure-client --ldap-uri ldap://ldap.example.com --base-dn dc=example,dc=com --output-script configure_ldap.sh
```

La vista previa oculta la contraseña de bind y no registra respaldos inexistentes. El script sí puede contener credenciales: se guarda con modo `0700`. La generación no prueba conectividad, certificados, autenticación LDAP real ni compatibilidad con las políticas particulares de un servidor.

El script reemplaza los archivos PAM comunes y NSS incluidos en el plan. Revisar antes las políticas existentes, MFA, cuentas de recuperación y mecanismos de resolución NSS; no asumir que un perfil genérico preserva todas las particularidades del entorno.

## Requisitos

- Debian/Ubuntu, Bash, apt-get y systemd para ejecutar un script revisado.
- Root, consola alternativa y una sesión administrativa independiente de LDAP para la aplicación.
- Un servidor LDAP con TLS y un certificado verificable antes de activar StartTLS.
- Python compatible y dependencias de Tools para generar planes o gestionar grupos.
- `visudo` instalado para publicar cualquier regla sudoers.

## Configuración

```bash
tools ldap configure-client \
  --ldap-uri ldaps://ldap.example.com:636 \
  --base-dn dc=example,dc=com \
  --mode sssd \
  --use-tls \
  -g server-admin -g desarrollo \
  --create-homedir \
  --dry-run
```

Opciones principales: `--bind-dn`, `--bind-password`, `--allowed-groups` / `-g`, `--mode nslcd|sssd`, `--use-tls/--no-tls`, `--create-homedir/--no-create-homedir`, `--password-hash`, `--dry-run`, `--output-script`.

TLS está habilitado por defecto. Para `ldap://` se genera StartTLS; para `ldaps://`, TLS directo. El certificado se comprueba con la política `demand` y el almacén CA configurado. El programa no emite certificados ni habilita TLS en el servidor LDAP.

Las credenciales y parámetros se conservan en el script y en su configuración de daemon. NSLCD usa `pam_ldap.so`, NSS `ldap` y `libnss-ldapd`; SSSD usa `pam_sss.so`, NSS `sss` y una configuración completa de dominio. Los valores multilínea y nombres de grupo que introduzcan operadores PAM se rechazan.

`--bind-password` sigue siendo un argumento de CLI: evitar historial y exposición de procesos para secretos reales; preferir la API Python con secretos obtenidos de un gestor. NSLCD y SSSD necesitan la contraseña de bind en su configuración local protegida, con modo `0600`.

## Grupos permitidos y migración

Las reglas se gestionan en `/etc/pam.d/common-account`, antes de cualquier regla o `@include` que pudiera conceder acceso. La autenticación no se modifica al agregar o quitar grupos.

```text
# LDAP allowed groups (managed by tools-admin) - start
account [success=1 default=ignore] pam_localuser.so
account requisite pam_succeed_if.so user ingroup desarrollo:server-admin
# LDAP allowed groups (managed by tools-admin) - end
```

La lista es OR. Una lista vacía deniega usuarios no locales. Las cuentas locales de recuperación omiten solo el filtro de grupos y siguen sujetas al resto de las comprobaciones de cuenta.

```bash
tools ldap groups list
tools ldap groups add devops
tools ldap groups remove desarrollo
tools ldap groups add qa --dry-run
tools ldap groups list --pam-account-file ./common-account
```

`--pam-auth-file` y el argumento Python `pam_auth_file` ya no se aceptan para editar grupos. Usar `--pam-account-file` / `pam_account_file`. No se transforma silenciosamente una pila `common-auth` heredada: revisar sus saltos numéricos y reglas antes de migrar. Un bloque administrado colocado después de otras reglas de cuenta o includes se rechaza para revisión manual.

Para proteger también SSH con llave y sudo con agente, el servicio debe invocar la fase PAM `account`. Comprobar `UsePAM` y las inclusiones reales del servicio. El bloque permite o deniega cuentas; no concede permisos sudo.

## Reglas sudoers

```bash
tools ldap sudoers create --name hela-admin --group hela-admin --run-as root:www-data --commands 'ALL, !/usr/bin/passwd'
tools ldap sudoers list
tools ldap sudoers show hela-admin
tools ldap sudoers remove hela-admin --dry-run
tools ldap sudoers generate-template --output ldap_sudoers.yml
tools ldap sudoers apply-file --file ldap_sudoers.yml --dry-run
```

`--sudoers-dir` permite un directorio alterno para pruebas. Los nombres deben contener únicamente letras, números, `_` o `-`; se rechazan rutas, puntos y enlaces simbólicos. Los campos de reglas son valores de una sola línea y el campo run-as se limita a listas de usuarios y grupos.

Cada escritura se prepara en un archivo temporal `0440`, se valida con `visudo -cf` y se publica mediante reemplazo atómico. La validación es obligatoria, incluso si un cliente Python pasa `validate=False`; `--validate` se conserva por compatibilidad. Si falta `visudo` o rechaza el contenido, no se sustituye la regla anterior.

Antes de sustituir o eliminar una regla se guarda una copia en `tools-sudoers-backups`, al lado del directorio de reglas y fuera de su inclusión activa. La aplicación YAML procesa reglas individualmente; no constituye una transacción de todo el lote.

## Respaldos y recuperación del script

El script crea `/var/backups/tools-ldap.XXXXXX`, con permisos privados y un archivo `manifest` que registra existencia previa, copia y ruta. Respalda la configuración y el estado activo de servicios antes de instalar paquetes o escribir archivos.

Ante error o interrupción, restaura las configuraciones, reinicia los servicios que estaban activos y detiene los que estaban inactivos. La recuperación no desinstala paquetes ni revierte los efectos de sus scripts de instalación. Mantener consola alternativa y conservar los respaldos hasta validar acceso y recuperación.

Para recuperación manual, revisar el manifiesto, restaurar las copias conservando metadatos y retirar solo los archivos nuevos de ese intento. Comprobar la configuración del daemon antes de reiniciarlo. No restaurar ciegamente sobre cambios posteriores.

## Comprobación

Otros comandos disponibles:

```bash
# Consulta de conectividad; requiere el cliente LDAP indicado por la herramienta
tools ldap test-connection --ldap-uri ldaps://ldap.example.com:636 --base-dn dc=example,dc=com
# Plantilla YAML local; configure-client aún no acepta --config
tools ldap generate-config -o ldap_config.yml
```

El verificador de conexión no sustituye la validación del plan ni demuestra que se hayan instalado PAM, NSS o servicios. La prueba de acceso a un servidor debe realizarse como una operación separada y autorizada.

```bash
python -m pytest tests/ldap tests/remote/test_ssh_executor.py tests/backup -q
```

Las pruebas incluyen PAM real mediante `pam_start_confdir` y archivos temporales en Linux: autenticación aceptada/rechazada, autorización por grupos e includes. También comprueban TLS/bind en los scripts, sintaxis Bash, recuperación de servicios con comandos simulados y validación real de sudoers cuando `visudo` está disponible.

La suite local no aplica scripts a servidores ni sustituye la validación de una migración real. Antes de desplegar: revisar el plan, comprobar TLS y NSS, ensayar en un entorno aislado y validar usuario permitido, denegado, recuperación local y reversión.
