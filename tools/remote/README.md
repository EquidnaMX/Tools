# Inventario y sincronización de llaves SSH

## Objetivo y alcance

Conciliar `~/.ssh/authorized_keys` de cada cuenta de una lista de servidores Linux
con un inventario autorizado. El inventario es completo: se añaden las llaves que
faltan y se revocan todas las que no aparecen en la lista de esa cuenta.
No modifica sudo, PAM, LDAP, sshd ni otras cuentas. No distribuye llaves privadas.

## Requisitos

- OpenSSH (`ssh` y `ssh-keygen`) en el equipo que ejecuta Tools.
- Python 3 en los servidores Linux y acceso SSH previo a cada cuenta destino.
- Identidades de servidores verificadas previamente en `known_hosts`.
- Acceso mediante agente SSH o `--identity` local; no pide contraseñas interactivas.
- El usuario destino debe ser propietario del home, `.ssh` y `authorized_keys`;
  ninguno puede permitir escritura a grupo u otros ni ser un enlace simbólico.
- Confirmar que sshd usa ese `AuthorizedKeysFile`. Archivos alternos,
  `AuthorizedKeysCommand`, certificados/CA y llaves externas requieren revisión aparte.

## Inventario

Ver `examples/ssh_keys_inventory.json`. `keys` relaciona nombres con archivos
públicos; las rutas relativas se resuelven desde el inventario. Cada entrada de
`servers` exige `host`, `user` y una lista `keys`; `port` es opcional (22).
No se permite repetir una misma combinación host/usuario/puerto.

Cada archivo contiene una sola llave pública OpenSSH, sin opciones de
`authorized_keys`. Se comprueba con `ssh-keygen` y se identifica por huella SHA256.
Si la misma llave ya existe con restricciones (`from=`, `command=`, `no-pty`, etc.),
se conserva la línea y sus restricciones. Cambiar comentarios no duplica llaves.
Las líneas desconocidas o malformadas detienen la escritura para revisión manual.

## Validación, plan y aplicación

```bash
# Solo validación local; no conecta a servidores.
tools remote keys validate ./keys/administrador.pub ./keys/recuperacion.pub

# Lectura remota sin escribir archivos.
tools remote keys audit --hosts-file ./inventory.json

# El mismo plan de altas y bajas; por defecto tampoco escribe.
tools remote keys sync --hosts-file ./inventory.json

# Ejecutar únicamente después de revisar el inventario y el plan.
tools remote keys sync --hosts-file ./inventory.json --identity ~/.ssh/id_ed25519 --apply
```

Los resultados son JSON por cuenta, con huellas deseadas, cantidad de faltantes,
sobrantes, huellas a revocar, cambios y ruta de respaldo. Una auditoría con
diferencias termina con código distinto de cero. Un fallo de un servidor no
impide informar sobre los demás. No hay transacción global entre servidores.

Una lista `keys: []` se puede auditar, pero aplicarla exige además `--allow-empty`.
Retirar la llave usada para conectar puede impedir futuras sesiones: conservar
una sesión de recuperación o consola y una llave de administración comprobada
en el inventario antes de aplicar revocaciones.

## Escritura, comprobación y recuperación

La aplicación bloquea `.ssh/.tools-keys.lock`, vuelve a comprobar el destino,
guarda el contenido previo en `authorized_keys.tools-backup-*` con modo `0600`
y publica el archivo nuevo mediante reemplazo atómico con modo `0600`.
Si crea `.ssh`, usa `0700`. Una segunda sincronización sin diferencias no
reescribe el archivo. El plan no crea directorios, respaldos ni bloqueos.

Tras escribir se verifica el contenido; ejecutar de nuevo `audit` debe reportar
cero diferencias. Esto comprueba la presencia de llaves, no que cada llave
funcione para iniciar sesión: confirmar una nueva sesión por cada identidad
necesaria antes de cerrar el acceso de recuperación. La herramienta no posee
las llaves privadas de todas las personas para hacer esa comprobación.

Para recuperar desde una sesión o consola disponible, identificar el respaldo
del informe y restaurarlo como `~/.ssh/authorized_keys`, manteniendo propietario
y modo `0600`. Si inicialmente no había archivo, el informe no contiene respaldo;
revisar antes de retirar el nuevo archivo. Los respaldos no se eliminan
automáticamente: conservarlos hasta completar la validación.

## Evidencia y límites

Pruebas locales con llaves reales generadas por `ssh-keygen`, homes temporales,
permisos POSIX, respaldos y ejecución del helper transmitido. La frontera SSH se
sustituye en las pruebas: no se han aplicado cambios ni probado accesos reales
contra los servidores del usuario. La revocación solo afecta el archivo indicado;
no invalida sesiones abiertas ni otros mecanismos de autenticación.

Referencia: [formato de authorized_keys y restricciones en OpenSSH](https://man.openbsd.org/sshd.8).
