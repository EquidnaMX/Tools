"""
Comandos CLI para autenticación LDAP.
"""

import click
from pathlib import Path
from tools.ldap import (
    LDAPClientInstaller,
    LDAPConfig,
    PAMConfig,
    InstallationMode,
    SudoersManager,
    SudoersRule,
)


@click.group()
def ldap():
    """Comandos de autenticación LDAP."""
    pass


def _local_group_installer(dry_run: bool = False) -> LDAPClientInstaller:
    """Crea instalador local para gestión de grupos PAM."""
    return LDAPClientInstaller(
        ldap_config=LDAPConfig(uri="ldap://localhost", base_dn="dc=local,dc=domain"),
        dry_run=dry_run,
    )


def _sudoers_manager(dry_run: bool = False) -> SudoersManager:
    """Crea gestor de sudoers."""
    return SudoersManager(dry_run=dry_run)


@ldap.command(name="configure-client")
@click.option(
    "--ldap-uri",
    required=True,
    help="URI del servidor LDAP (ldap://host o ldaps://host)",
)
@click.option(
    "--base-dn",
    required=True,
    help="Base DN (ejemplo: dc=example,dc=com)",
)
@click.option(
    "--bind-dn",
    help="Bind DN para autenticación (opcional)",
)
@click.option(
    "--bind-password",
    help="Password para bind DN (opcional)",
)
@click.option(
    "--allowed-groups",
    "-g",
    multiple=True,
    default=["server-admin", "desarrollo"],
    help="Grupos LDAP permitidos (puede especificarse múltiples veces)",
)
@click.option(
    "--mode",
    type=click.Choice(["nslcd", "sssd"], case_sensitive=False),
    default="nslcd",
    help="Modo de instalación (default: nslcd)",
)
@click.option(
    "--use-tls/--no-tls",
    default=True,
    help="Usar TLS/STARTTLS (default: True)",
)
@click.option(
    "--create-homedir/--no-create-homedir",
    default=True,
    help="Crear home directories automáticamente (default: True)",
)
@click.option(
    "--password-hash",
    type=click.Choice(["yescrypt", "sha512", "md5"]),
    default="yescrypt",
    help="Algoritmo de hash de contraseñas (default: yescrypt)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Simular instalación sin ejecutar comandos",
)
@click.option(
    "--output-script",
    type=click.Path(),
    help="Generar script bash en vez de instalar",
)
def configure_client(
    ldap_uri,
    base_dn,
    bind_dn,
    bind_password,
    allowed_groups,
    mode,
    use_tls,
    create_homedir,
    password_hash,
    dry_run,
    output_script,
):
    """
    Configura un cliente Linux para autenticarse con LDAP.

    Instala y configura PAM, NSLCD/SSSD y NSSwitch para permitir
    autenticación de usuarios LDAP. Crea backups automáticos de
    todos los archivos modificados.

    Ejemplos:

        # Configuración básica con NSLCD
        tools ldap configure-client \\
            --ldap-uri ldap://ldap.example.com \\
            --base-dn dc=example,dc=com

        # Con autenticación y grupos específicos
        tools ldap configure-client \\
            --ldap-uri ldaps://ldap.example.com \\
            --base-dn dc=example,dc=com \\
            --bind-dn cn=readonly,dc=example,dc=com \\
            --bind-password secret123 \\
            -g admins -g developers

        # Usando SSSD en vez de NSLCD
        tools ldap configure-client \\
            --ldap-uri ldap://ldap.example.com \\
            --base-dn dc=example,dc=com \\
            --mode sssd

        # Generar script bash
        tools ldap configure-client \\
            --ldap-uri ldap://ldap.example.com \\
            --base-dn dc=example,dc=com \\
            --output-script configure_ldap.sh

        # Simular sin ejecutar
        tools ldap configure-client \\
            --ldap-uri ldap://ldap.example.com \\
            --base-dn dc=example,dc=com \\
            --dry-run
    """
    # Configurar LDAP
    ldap_config = LDAPConfig(
        uri=ldap_uri,
        base_dn=base_dn,
        bind_dn=bind_dn,
        bind_password=bind_password,
        use_tls=use_tls,
    )

    # Configurar PAM
    pam_config = PAMConfig(
        allowed_groups=list(allowed_groups),
        create_home_dir=create_homedir,
        password_hash=password_hash,
    )

    # Crear instalador
    install_mode = InstallationMode.NSLCD if mode == "nslcd" else InstallationMode.SSSD
    installer = LDAPClientInstaller(
        ldap_config=ldap_config,
        pam_config=pam_config,
        mode=install_mode,
        dry_run=dry_run,
    )

    # Generar script o instalar
    if output_script:
        click.echo(f"Generando script: {output_script}")
        script_content = installer.generate_script()

        with open(output_script, "w") as f:
            f.write(script_content)

        import os
        os.chmod(output_script, 0o755)

        click.secho(f"✓ Script generado: {output_script}", fg="green", bold=True)
        click.echo(f"\nPara ejecutar:")
        click.echo(f"  sudo ./{output_script}")
        return

    # Instalar
    click.echo("Configurando cliente LDAP...")
    click.echo(f"  LDAP URI: {ldap_uri}")
    click.echo(f"  Base DN: {base_dn}")
    click.echo(f"  Modo: {mode.upper()}")
    click.echo(f"  Grupos permitidos: {', '.join(allowed_groups)}")

    if dry_run:
        click.secho("\n[MODO DRY-RUN] - No se ejecutarán comandos reales\n", fg="yellow", bold=True)

    result = installer.install()

    # Mostrar resultado
    click.echo("\n" + "=" * 60)

    if result.success:
        click.secho("✓ Instalación completada exitosamente", fg="green", bold=True)
    else:
        click.secho("✗ Instalación falló", fg="red", bold=True)

    click.echo(f"\nMensaje: {result.message}")

    if result.steps_completed:
        click.echo(f"\nPasos completados ({len(result.steps_completed)}):")
        for step in result.steps_completed:
            click.secho(f"  ✓ {step}", fg="green")

    if result.steps_failed:
        click.echo(f"\nPasos fallidos ({len(result.steps_failed)}):")
        for step in result.steps_failed:
            click.secho(f"  ✗ {step}", fg="red")

    if result.backups_created:
        click.echo(f"\nBackups creados ({len(result.backups_created)}):")
        for backup in result.backups_created[:5]:  # Mostrar solo los primeros 5
            click.echo(f"  • {backup}")
        if len(result.backups_created) > 5:
            click.echo(f"  ... y {len(result.backups_created) - 5} más")

    click.echo("=" * 60)

    if not result.success:
        raise click.Abort()


@ldap.command(name="test-connection")
@click.option(
    "--ldap-uri",
    required=True,
    help="URI del servidor LDAP",
)
@click.option(
    "--base-dn",
    required=True,
    help="Base DN",
)
@click.option(
    "--bind-dn",
    help="Bind DN (opcional)",
)
@click.option(
    "--bind-password",
    help="Password para bind DN (opcional)",
)
def test_connection(ldap_uri, base_dn, bind_dn, bind_password):
    """
    Prueba la conexión al servidor LDAP.

    Verifica que se puede conectar al servidor LDAP y realizar
    búsquedas básicas.

    Ejemplo:

        tools ldap test-connection \\
            --ldap-uri ldap://ldap.example.com \\
            --base-dn dc=example,dc=com
    """
    click.echo("Probando conexión a LDAP...")
    click.echo(f"  URI: {ldap_uri}")
    click.echo(f"  Base DN: {base_dn}")

    try:
        import ldap

        # Conectar
        conn = ldap.initialize(ldap_uri)
        conn.set_option(ldap.OPT_REFERRALS, 0)

        # Bind
        if bind_dn:
            conn.simple_bind_s(bind_dn, bind_password or "")
        else:
            conn.simple_bind_s("", "")

        # Búsqueda simple
        result = conn.search_s(base_dn, ldap.SCOPE_BASE)

        click.secho("\n✓ Conexión exitosa!", fg="green", bold=True)

        if result:
            click.echo("\nInformación del servidor:")
            for dn, attrs in result:
                click.echo(f"  DN: {dn}")
                for key, values in attrs.items():
                    click.echo(f"    {key.decode()}: {values[0].decode()}")

        conn.unbind_s()

    except ImportError:
        click.secho(
            "\n✗ python-ldap no está instalado",
            fg="red",
            bold=True,
        )
        click.echo("\nInstalar con: pip install python-ldap")
        raise click.Abort()

    except Exception as e:
        click.secho(f"\n✗ Error de conexión: {e}", fg="red", bold=True)
        raise click.Abort()


@ldap.command(name="generate-config")
@click.option(
    "--output",
    "-o",
    default="ldap_config.yaml",
    help="Archivo de salida (default: ldap_config.yaml)",
)
def generate_config(output):
    """
    Genera un archivo de configuración de ejemplo.

    Crea un archivo YAML con todas las opciones disponibles
    para configurar el cliente LDAP.

    Ejemplo:

        tools ldap generate-config -o mi_ldap.yaml
    """
    import yaml

    config = {
        "ldap": {
            "uri": "ldap://ldap.example.com",
            "base_dn": "dc=example,dc=com",
            "bind_dn": "cn=readonly,dc=example,dc=com",
            "bind_password": "change-me",
            "use_tls": True,
            "tls_reqcert": "demand",
            "tls_cacert_file": "/etc/ssl/certs/ca-certificates.crt",
        },
        "pam": {
            "allowed_groups": ["server-admin", "desarrollo", "sysadmins"],
            "create_home_dir": True,
            "umask": "0077",
            "password_hash": "yescrypt",
        },
        "installation": {
            "mode": "nslcd",  # o "sssd"
            "dry_run": False,
        },
    }

    with open(output, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    click.secho(f"✓ Configuración generada: {output}", fg="green", bold=True)
    click.echo("\nEdita el archivo y usa con:")
    click.echo(f"  tools ldap configure-from-file -f {output}")


@ldap.group(name="groups")
def groups():
    """Gestiona grupos LDAP permitidos en PAM (common-auth)."""
    pass


@groups.command(name="list")
@click.option(
    "--pam-auth-file",
    default="/etc/pam.d/common-auth",
    show_default=True,
    help="Ruta del archivo common-auth",
)
def list_groups(pam_auth_file):
    """Lista grupos permitidos actualmente."""
    installer = _local_group_installer(dry_run=False)
    groups_found = installer.list_allowed_groups(pam_auth_file=pam_auth_file)

    if not groups_found:
        click.secho("No se encontraron grupos LDAP configurados.", fg="yellow")
        return

    click.secho("Grupos LDAP permitidos:", fg="green", bold=True)
    for group in groups_found:
        click.echo(f"- {group}")


@groups.command(name="add")
@click.argument("group")
@click.option(
    "--pam-auth-file",
    default="/etc/pam.d/common-auth",
    show_default=True,
    help="Ruta del archivo common-auth",
)
@click.option("--dry-run", is_flag=True, help="Simular sin escribir cambios")
def add_group(group, pam_auth_file, dry_run):
    """Agrega un grupo permitido a common-auth."""
    installer = _local_group_installer(dry_run=dry_run)
    ok, message = installer.add_allowed_group(group=group, pam_auth_file=pam_auth_file)

    if ok:
        click.secho(f"✓ {message}", fg="green", bold=True)
        return

    click.secho(f"✗ {message}", fg="red", bold=True)
    raise click.Abort()


@groups.command(name="remove")
@click.argument("group")
@click.option(
    "--pam-auth-file",
    default="/etc/pam.d/common-auth",
    show_default=True,
    help="Ruta del archivo common-auth",
)
@click.option("--dry-run", is_flag=True, help="Simular sin escribir cambios")
def remove_group(group, pam_auth_file, dry_run):
    """Quita un grupo permitido de common-auth."""
    installer = _local_group_installer(dry_run=dry_run)
    ok, message = installer.remove_allowed_group(group=group, pam_auth_file=pam_auth_file)

    if ok:
        click.secho(f"✓ {message}", fg="green", bold=True)
        return

    click.secho(f"✗ {message}", fg="red", bold=True)
    raise click.Abort()


@ldap.group(name="sudoers")
def sudoers():
    """Gestiona reglas en /etc/sudoers.d para grupos LDAP."""
    pass


@sudoers.command(name="create")
@click.option("--name", required=True, help="Nombre de archivo en sudoers.d (ej: hela-admin)")
@click.option("--group", required=True, help="Grupo LDAP (con o sin prefijo %)")
@click.option("--run-as", default="root", show_default=True, help="Usuarios run-as, ej: root:www-data")
@click.option("--commands", default="ALL", show_default=True, help="Comandos permitidos/restringidos")
@click.option(
    "--sudoers-dir",
    default="/etc/sudoers.d",
    show_default=True,
    help="Directorio sudoers.d destino",
)
@click.option("--validate", is_flag=True, help="Validar con visudo antes de escribir")
@click.option("--visudo-path", default="visudo", show_default=True, help="Ruta/comando visudo")
@click.option("--dry-run", is_flag=True, help="Simular sin escribir cambios")
def create_sudoers_rule(name, group, run_as, commands, sudoers_dir, validate, visudo_path, dry_run):
    """Crea regla sudoers para un grupo LDAP."""
    manager = _sudoers_manager(dry_run=dry_run)
    rule = SudoersRule(group=group, run_as=run_as, commands=commands)
    ok, message = manager.create_rule_file(
        file_name=name,
        rule=rule,
        sudoers_dir=sudoers_dir,
        validate=validate,
        visudo_path=visudo_path,
    )

    if ok:
        click.secho(f"✓ {message}", fg="green", bold=True)
        return

    click.secho(f"✗ {message}", fg="red", bold=True)
    raise click.Abort()


@sudoers.command(name="list")
@click.option(
    "--sudoers-dir",
    default="/etc/sudoers.d",
    show_default=True,
    help="Directorio sudoers.d a inspeccionar",
)
def list_sudoers_rules(sudoers_dir):
    """Lista archivos de reglas sudoers existentes."""
    manager = _sudoers_manager(dry_run=False)
    files = manager.list_rule_files(sudoers_dir=sudoers_dir)

    if not files:
        click.secho("No hay reglas en sudoers.d.", fg="yellow")
        return

    click.secho("Reglas sudoers disponibles:", fg="green", bold=True)
    for entry in files:
        click.echo(f"- {entry}")


@sudoers.command(name="show")
@click.argument("name")
@click.option(
    "--sudoers-dir",
    default="/etc/sudoers.d",
    show_default=True,
    help="Directorio sudoers.d",
)
def show_sudoers_rule(name, sudoers_dir):
    """Muestra contenido de una regla sudoers."""
    manager = _sudoers_manager(dry_run=False)
    ok, message = manager.show_rule_file(file_name=name, sudoers_dir=sudoers_dir)

    if ok:
        click.echo(message)
        return

    click.secho(f"✗ {message}", fg="red", bold=True)
    raise click.Abort()


@sudoers.command(name="remove")
@click.argument("name")
@click.option(
    "--sudoers-dir",
    default="/etc/sudoers.d",
    show_default=True,
    help="Directorio sudoers.d",
)
@click.option("--dry-run", is_flag=True, help="Simular sin borrar")
def remove_sudoers_rule(name, sudoers_dir, dry_run):
    """Elimina una regla sudoers por nombre de archivo."""
    manager = _sudoers_manager(dry_run=dry_run)
    ok, message = manager.remove_rule_file(file_name=name, sudoers_dir=sudoers_dir)

    if ok:
        click.secho(f"✓ {message}", fg="green", bold=True)
        return

    click.secho(f"✗ {message}", fg="red", bold=True)
    raise click.Abort()


@sudoers.command(name="apply-file")
@click.option("--file", "config_file", required=True, type=click.Path(exists=True), help="Archivo YAML de reglas")
@click.option(
    "--sudoers-dir",
    default="/etc/sudoers.d",
    show_default=True,
    help="Directorio sudoers.d destino",
)
@click.option("--validate", is_flag=True, help="Validar cada regla con visudo")
@click.option("--visudo-path", default="visudo", show_default=True, help="Ruta/comando visudo")
@click.option("--dry-run", is_flag=True, help="Simular sin escribir cambios")
def apply_sudoers_file(config_file, sudoers_dir, validate, visudo_path, dry_run):
    """Aplica múltiples reglas sudoers desde un archivo YAML."""
    import yaml

    with open(config_file, "r", encoding="utf-8") as f:
        payload = yaml.safe_load(f) or {}

    rules = payload.get("sudoers_rules", [])
    if not isinstance(rules, list) or not rules:
        click.secho("✗ El archivo no contiene 'sudoers_rules' válidas.", fg="red", bold=True)
        raise click.Abort()

    manager = _sudoers_manager(dry_run=dry_run)
    created = 0
    failed = 0

    for item in rules:
        name = item.get("name")
        group = item.get("group")
        run_as = item.get("run_as", "root")
        commands = item.get("commands", "ALL")

        if not name or not group:
            failed += 1
            click.secho("✗ Regla inválida: se requiere 'name' y 'group'", fg="red")
            continue

        rule = SudoersRule(group=group, run_as=run_as, commands=commands)
        ok, message = manager.create_rule_file(
            file_name=name,
            rule=rule,
            sudoers_dir=sudoers_dir,
            validate=validate,
            visudo_path=visudo_path,
        )

        if ok:
            created += 1
            click.secho(f"✓ {name}: {message}", fg="green")
        else:
            failed += 1
            click.secho(f"✗ {name}: {message}", fg="red")

    click.echo("\nResumen:")
    click.echo(f"  Reglas procesadas: {len(rules)}")
    click.echo(f"  Exitosas: {created}")
    click.echo(f"  Fallidas: {failed}")

    if failed > 0:
        raise click.Abort()


@sudoers.command(name="generate-template")
@click.option("--output", "output_file", default="ldap_sudoers.yml", show_default=True, help="Archivo YAML de salida")
def generate_sudoers_template(output_file):
    """Genera plantilla YAML para reglas sudoers en lote."""
    import yaml

    payload = {
        "sudoers_rules": [
            {
                "name": "hela-admin",
                "group": "hela-admin",
                "run_as": "root:www-data",
                "commands": "ALL, !/usr/bin/passwd",
            },
            {
                "name": "devops-readonly",
                "group": "devops",
                "run_as": "root",
                "commands": "/usr/bin/systemctl status *, /usr/bin/journalctl *",
            },
        ]
    }

    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(payload, f, default_flow_style=False, sort_keys=False)

    click.secho(f"✓ Plantilla generada: {output_file}", fg="green", bold=True)
    click.echo("\nAplicar con:")
    click.echo(f"  tools ldap sudoers apply-file --file {output_file} --validate")
