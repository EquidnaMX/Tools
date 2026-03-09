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
)


@click.group()
def ldap():
    """Comandos de autenticación LDAP."""
    pass


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
