# Password Management Tool

Herramienta profesional para gestionar cambios de contraseña en múltiples servidores Linux con sincronización LDAP, rotación automática y notificaciones por email/webhook.

## Features

✅ **Cambio multi-host**: Cambiar contraseñas en múltiples servidores en paralelo  
✅ **LDAP sync**: Sincronizar cambios con directorio LDAP automáticamente  
✅ **Rotación automática**: Programar rotaciones periódicas de contraseñas  
✅ **Notificaciones**: Alertas por email y webhooks  
✅ **Auditoría completa**: Registro detallado de todas las operaciones  
✅ **Generación segura**: Contraseñas criptográficamente seguras  
✅ **Validación de políticas**: Aplicar requisitos de complejidad  
✅ **Verificación**: Confirmar cambios mediante SSH  
✅ **Rollback**: Revertir cambios en caso de fallo

## Instalación

```bash
# Instalación básica
pip install -e .

# Con soporte LDAP
pip install -e ".[ldap]"

# Con todas las dependencias opcionales
pip install -e ".[all]"
```

## Uso Rápido

### Cambiar contraseña con generación automática

```bash
tools password change server1 server2 server3 -u admin -g

# Genera una contraseña segura automáticamente
# Ejecuta cambios en paralelo
# Verifica los cambios
# Sincroniza con LDAP
# Envía notificaciones
```

### Cambiar contraseña manualmente

```bash
tools password change server1 -u root -p old_password -n new_password --dry-run

# --dry-run: Simula sin ejecutar cambios
```

### Generar contraseña segura

```bash
tools password generate -l 20 --check

# -l 20: Contraseña de 20 caracteres
# --check: Muestra puntuación de seguridad y entropía
```

### Validar contraseña

```bash
tools password validate "MyP@ssw0rd123"

# Valida contra la política de contraseñas
# Muestra puntuación, entropía, errores/advertencias
```

### Ver historial de auditoría

```bash
tools password audit --host server1 --user root --status failed

# Filtra por host, usuario, estado
# Exporta a JSON, CSV o tabla
```

### Estado de rotaciones

```bash
tools password status

# Muestra rotaciones vencidas
# Próximas rotaciones en 7 días
# Estadísticas generales
```

## Configuración

### Generar archivo de configuración

```bash
tools password init-config -o password_config.yaml

# Genera plantilla con opciones principales
```

### Estructura de configuración

```yaml
# password_config.yaml

policy:
  min_length: 12
  max_length: 128
  require_uppercase: true
  require_lowercase: true
  require_digits: true
  require_special: true
  excluded_terms:
    - password
    - admin
    - root
  password_history: 5
  password_age_days: 90

ldap:
  enabled: true
  server_uri: "ldap://ldap.example.com"
  bind_dn: "cn=admin,dc=example,dc=com"
  base_dn: "dc=example,dc=com"
  use_tls: true

notifications:
  enabled: true
  smtp:
    server: "smtp.gmail.com"
    port: 587
    use_tls: true
    username: "noreply@example.com"
    email_recipients:
      - "admin@example.com"
  webhooks:
    - url: "https://hooks.example.com/password-changes"

rotation:
  enabled: false
  interval_days: 30
  schedule_hour: 2
  schedule_minute: 0
```

### Usar configuración personalizada

```bash
tools password change server1 -u admin -g --config password_config.yaml
```

## Uso Avanzado

### Python API

```python
import asyncio
from tools.password import PasswordManager, PasswordPolicy

# Crear manager con política personalizada
policy = PasswordPolicy(
    min_length=16,
    require_special=True
)

manager = PasswordManager(policy=policy)

# Cambiar contraseña
results = asyncio.run(
    manager.change_password(
        hosts=['server1', 'server2'],
        username='root',
        auto_generate=True,
        parallel_jobs=5,
        verify=True,
        ldap_sync=True,
        notify=True,
        reason="Rotación trimestral"
    )
)

# Procesar resultados
for host, result in results.items():
    if result.status.value == 'success':
        print(f"✓ {host}: {result.duration:.1f}s")
    else:
        print(f"✗ {host}: {result.error}")
```

### Validación y generación

```python
from tools.password import PasswordManager

manager = PasswordManager()

# Generar contraseña
password = manager.generate_password(length=20)
print(f"Contraseña: {password}")

# Validar
valid, details = manager.validate_password(password)
print(f"Válida: {valid}")
print(f"Puntuación: {details['score']}/100")
print(f"Entropía: {details['entropy_bits']:.1f} bits")
```

### Auditoría

```python
from datetime import datetime, timedelta

# Consultar cambios recientes
today = datetime.now().date()
week_ago = today - timedelta(days=7)

entries = manager.auditor.query_log(
    from_date=week_ago,
    to_date=today,
    host="server1"
)

print(f"Cambios en última semana: {len(entries)}")

# Exportar reportes
manager.auditor.export_report(
    format='html',
    from_date=week_ago,
    output_file='report.html'
)
```

## Seguridad

### Buenas prácticas

1. **Nunca almacenar contraseñas en disco**
   - Las contraseñas se transportan solo por SSH
   - Los registros de auditoría no guardan texto de contraseñas

2. **Usar LDAP cuando sea posible**
   - Centraliza gestión de identidades
   - La herramienta sincroniza automáticamente

3. **Politica de contraseñas fuerte**
   - Mínimo 12 caracteres
   - Números, mayúsculas, minúsculas, caracteres especiales
   - Evitar términos comunes

4. **Rotación periódica**
   - Configurar rotación automática cada 30-90 días
   - Auditar rotaciones fallidas

5. **Notificaciones**
   - Recibir alertas por email de cambios importantes
   - Webhooks para integración con SIEM/monitoreo

### Auditoría

Todos los cambios se registran con:

- Timestamp exacto
- Operador (usuario que ejecutó)
- Host y usuario afectado
- Estado (éxito/fallo)
- Método usado (chpasswd/passwd)
- Sincronización LDAP (sí/no)

Exportar reportes:

```bash
# JSON
tools password audit --format json --export report.json

# CSV para Excel
tools password audit --format csv --export report.csv

# HTML para navegador
tools password audit --format table --export report.html
```

## Troubleshooting

### Error de conexión SSH

```bash
# Verificar conectividad
ssh -v user@host

# Asegurar que SSH key está configurada
# o usar -p para ingresar contraseña
```

### Contraseña rechazada

```bash
# Validar contraseña contra política
tools password validate "mi_contraseña"

# Generar contraseña válida
tools password generate --check
```

### LDAP no sincroniza

```bash
# Verificar configuración
# Asegurar que bind_dn tiene permisos
# Comprobar conectividad LDAP

# En modo debug (requiere código)
```

### Las notificaciones no llegan

```bash
# Verificar SMTP
# - Revisar credenciales en config.yaml
# - Confirmar puerto (587 para TLS, 25 para plain)
# - Probar email manualmente

# Revisar logs
tools password audit --status failed
```

## Arquitectura

```
password/
├── models.py          # Estructuras de datos
├── validators.py      # Validación y políticas
├── generators.py      # Generación de contraseñas
├── executor.py        # Ejecución SSH remota
├── auditor.py         # Auditoría en SQLite
├── ldap_sync.py       # Sincronización LDAP
├── scheduler.py       # Rotación automática
├── notifier.py        # Email y webhooks
├── manager.py         # Orquestador principal
├── password_commands.py # CLI
└── __init__.py        # Exportes
```

## Dependencias

**Requeridas:**

- Python 3.8+
- asyncio
- sqlite3
- Click (CLI)

**Opcionales:**

- `python-ldap`: Soporte LDAP
- `aiohttp`: Webhooks async
- `keyring`: Almacenamiento seguro de credenciales
- `pyyaml`: Configuración YAML

## Licencia

Parte de Tools Suite v2.7.0+

## Soporte

Para reportar bugs o sugerencias:

- Criar issue en el repositorio
- Incluir output de `tools --version`
- Descripción del problema y pasos para reproducir
