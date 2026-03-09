#!/usr/bin/env python3
"""
Ejemplos de uso del módulo Remote Management.

Demuestra SSH execution, file distribution, network scanning,
y gestión de múltiples hosts en paralelo.
"""

from pathlib import Path
from tools.remote import SSHExecutor, FileDistributor, NetworkScanner


def example_basic_ssh_execution():
    """Ejemplo básico de ejecución SSH."""
    print("=" * 60)
    print("EJEMPLO 1: Ejecución SSH Básica")
    print("=" * 60)
    
    executor = SSHExecutor(
        hosts=["192.168.1.10"],
        user="admin",
        key_file=Path.home() / ".ssh" / "id_rsa",
    )
    
    print("\n→ Ejecutando comando 'uptime'...")
    results = executor.execute("uptime")
    
    for host, result in results.items():
        print(f"\nHost: {host}")
        print(f"  Código: {result['return_code']}")
        print(f"  Output: {result['stdout']}")
        if result['stderr']:
            print(f"  Error: {result['stderr']}")


def example_parallel_execution():
    """Ejemplo de ejecución paralela en múltiples hosts."""
    print("\n" + "=" * 60)
    print("EJEMPLO 2: Ejecución Paralela Multi-Host")
    print("=" * 60)
    
    hosts = [
        "web1.example.com",
        "web2.example.com",
        "web3.example.com",
        "db1.example.com",
    ]
    
    executor = SSHExecutor(
        hosts=hosts,
        user="deploy",
        key_file=Path.home() / ".ssh" / "deploy_key",
        parallel=True,
        timeout=30,
    )
    
    print(f"\n→ Ejecutando 'df -h' en {len(hosts)} hosts en paralelo...")
    results = executor.execute("df -h")
    
    print("\n✓ Resultados:")
    for host, result in results.items():
        status = "✓ OK" if result['return_code'] == 0 else "✗ FALLO"
        print(f"  {host}: {status}")
        if result['return_code'] == 0:
            print(f"    Output: {result['stdout'][:100]}...")


def example_sudo_execution():
    """Ejemplo de ejecución con sudo."""
    print("\n" + "=" * 60)
    print("EJEMPLO 3: Ejecución con Sudo")
    print("=" * 60)
    
    executor = SSHExecutor(
        hosts=["server1.example.com"],
        user="deploy",
        key_file=Path.home() / ".ssh" / "deploy_key",
        sudo=True,
    )
    
    print("\n→ Ejecutando 'systemctl status nginx' con sudo...")
    results = executor.execute("systemctl status nginx")
    
    for host, result in results.items():
        print(f"\nHost: {host}")
        if result['return_code'] == 0:
            print("  ✓ Nginx running")
            print(f"  {result['stdout'][:200]}...")
        else:
            print("  ✗ Nginx not running or error")
            print(f"  {result['stderr']}")


def example_password_authentication():
    """Ejemplo de autenticación con password."""
    print("\n" + "=" * 60)
    print("EJEMPLO 4: Autenticación con Password")
    print("=" * 60)
    
    executor = SSHExecutor(
        hosts=["192.168.1.20"],
        user="admin",
        password="mypassword",  # Mejor usar getpass() en producción
    )
    
    print("\n→ Ejecutando comando con password auth...")
    results = executor.execute("hostname")
    
    for host, result in results.items():
        print(f"\nHost: {host}")
        print(f"  Hostname: {result['stdout'].strip()}")


def example_file_distribution():
    """Ejemplo de distribución de archivos."""
    print("\n" + "=" * 60)
    print("EJEMPLO 5: Distribución de Archivos")
    print("=" * 60)
    
    distributor = FileDistributor(
        hosts=["web1.example.com", "web2.example.com"],
        user="deploy",
        key_file=Path.home() / ".ssh" / "deploy_key",
    )
    
    local_file = Path.home() / "configs" / "nginx.conf"
    remote_path = "/etc/nginx/nginx.conf"
    
    print(f"\n→ Distribuyendo {local_file.name} a 2 hosts...")
    results = distributor.distribute(
        local_file,
        remote_path,
        verify=True,  # Verificar checksum
        backup=True,  # Backup del archivo existente
    )
    
    print("\n✓ Resultados:")
    for host, result in results.items():
        status = "✓ OK" if result['success'] else "✗ FALLO"
        print(f"  {host}: {status}")
        if result['success']:
            print(f"    Transferido: {result['size']:,} bytes")
            print(f"    Checksum: {result['checksum'][:16]}...")
        else:
            print(f"    Error: {result['error']}")


def example_directory_distribution():
    """Ejemplo de distribución de directorios."""
    print("\n" + "=" * 60)
    print("EJEMPLO 6: Distribución de Directorios")
    print("=" * 60)
    
    distributor = FileDistributor(
        hosts=["app1.example.com", "app2.example.com", "app3.example.com"],
        user="deploy",
        key_file=Path.home() / ".ssh" / "deploy_key",
        parallel=True,
    )
    
    local_dir = Path.home() / "releases" / "app-v2.1.0"
    remote_dir = "/opt/app"
    
    print(f"\n→ Distribuyendo directorio a 3 hosts en paralelo...")
    results = distributor.distribute_directory(
        local_dir,
        remote_dir,
        exclude_patterns=["*.log", "*.tmp", "__pycache__"],
    )
    
    print("\n✓ Resultados:")
    for host, result in results.items():
        print(f"  {host}:")
        print(f"    Archivos: {result['files_transferred']}")
        print(f"    Tamaño: {result['total_size']:,} bytes")
        print(f"    Duración: {result['duration_seconds']:.2f}s")


def example_network_scan():
    """Ejemplo de escaneo de red."""
    print("\n" + "=" * 60)
    print("EJEMPLO 7: Escaneo de Red")
    print("=" * 60)
    
    scanner = NetworkScanner()
    
    # Escanear subnet
    print("\n→ Escaneando subnet 192.168.1.0/24...")
    hosts = scanner.scan_subnet(
        subnet="192.168.1.0/24",
        ports=[22, 80, 443],
        timeout=2,
    )
    
    print(f"\n✓ Encontrados {len(hosts)} hosts activos:")
    for host_info in hosts:
        print(f"\n  IP: {host_info['ip']}")
        print(f"  MAC: {host_info.get('mac', 'N/A')}")
        print(f"  Hostname: {host_info.get('hostname', 'N/A')}")
        print(f"  Puertos abiertos: {host_info['open_ports']}")


def example_port_scan():
    """Ejemplo de escaneo de puertos."""
    print("\n" + "=" * 60)
    print("EJEMPLO 8: Escaneo de Puertos")
    print("=" * 60)
    
    scanner = NetworkScanner()
    
    target = "example.com"
    ports = [21, 22, 80, 443, 3306, 5432, 6379, 8080]
    
    print(f"\n→ Escaneando puertos en {target}...")
    results = scanner.scan_ports(target, ports, timeout=3)
    
    print(f"\n✓ Resultados para {target}:")
    open_ports = [p for p, status in results.items() if status == "open"]
    closed_ports = [p for p, status in results.items() if status == "closed"]
    filtered_ports = [p for p, status in results.items() if status == "filtered"]
    
    if open_ports:
        print(f"  Abiertos: {open_ports}")
    if closed_ports:
        print(f"  Cerrados: {closed_ports}")
    if filtered_ports:
        print(f"  Filtrados: {filtered_ports}")


def example_batch_commands():
    """Ejemplo de comandos batch con script."""
    print("\n" + "=" * 60)
    print("EJEMPLO 9: Comandos Batch")
    print("=" * 60)
    
    executor = SSHExecutor(
        hosts=["server1.example.com", "server2.example.com"],
        user="admin",
        key_file=Path.home() / ".ssh" / "admin_key",
        parallel=True,
    )
    
    # Script con múltiples comandos
    script = """
    echo "Starting deployment..."
    cd /opt/app
    git pull origin main
    pip install -r requirements.txt
    systemctl restart app
    systemctl status app
    echo "Deployment complete"
    """
    
    print("\n→ Ejecutando script de deployment...")
    results = executor.execute_script(script, sudo=True)
    
    print("\n✓ Resultados:")
    for host, result in results.items():
        status = "✓ OK" if result['return_code'] == 0 else "✗ FALLO"
        print(f"  {host}: {status}")


def example_interactive_sudo():
    """Ejemplo de manejo de prompts interactivos."""
    print("\n" + "=" * 60)
    print("EJEMPLO 10: Sudo Interactivo")
    print("=" * 60)
    
    executor = SSHExecutor(
        hosts=["server1.example.com"],
        user="deploy",
        key_file=Path.home() / ".ssh" / "deploy_key",
        sudo=True,
        sudo_password="deploy_password",  # Usar getpass() en producción
    )
    
    print("\n→ Ejecutando comando que requiere sudo password...")
    results = executor.execute("apt-get update")
    
    for host, result in results.items():
        print(f"\nHost: {host}")
        if result['return_code'] == 0:
            print("  ✓ Update successful")
        else:
            print("  ✗ Update failed")
            print(f"  Error: {result['stderr']}")


def example_output_formatting():
    """Ejemplo de formateo de output."""
    print("\n" + "=" * 60)
    print("EJEMPLO 11: Formateo de Output")
    print("=" * 60)
    
    executor = SSHExecutor(
        hosts=["web1.example.com", "web2.example.com", "db1.example.com"],
        user="monitor",
        key_file=Path.home() / ".ssh" / "monitor_key",
        parallel=True,
    )
    
    print("\n→ Obteniendo métricas de sistema...")
    results = executor.execute("uptime")
    
    # Formatear como tabla
    print("\n✓ Resultados (formato tabla):")
    print(f"{'Host':<25} {'Status':<10} {'Load Average'}")
    print("-" * 60)
    
    for host, result in results.items():
        status = "OK" if result['return_code'] == 0 else "FAIL"
        load = result['stdout'].split('load average:')[-1].strip() if status == "OK" else "N/A"
        print(f"{host:<25} {status:<10} {load}")


def example_error_handling():
    """Ejemplo de manejo de errores."""
    print("\n" + "=" * 60)
    print("EJEMPLO 12: Manejo de Errores")
    print("=" * 60)
    
    executor = SSHExecutor(
        hosts=["good-host.com", "bad-host.com", "offline-host.com"],
        user="admin",
        key_file=Path.home() / ".ssh" / "id_rsa",
        timeout=10,
        retry=3,  # Reintentar 3 veces
    )
    
    print("\n→ Ejecutando con retry automático...")
    results = executor.execute("echo 'test'")
    
    print("\n✓ Resultados:")
    successful = []
    failed = []
    
    for host, result in results.items():
        if result['return_code'] == 0:
            successful.append(host)
        else:
            failed.append(host)
            print(f"  ✗ {host}: {result.get('error', 'Unknown error')}")
    
    print(f"\nResumen:")
    print(f"  Exitosos: {len(successful)}/{len(results)}")
    print(f"  Fallidos: {len(failed)}/{len(results)}")


def main():
    """Ejecutar todos los ejemplos."""
    print("\n" + "=" * 80)
    print(" " * 20 + "REMOTE MANAGEMENT - EJEMPLOS")
    print("=" * 80)
    
    try:
        # Ejemplos que no requieren conexiones reales
        print("\nNOTA: Los ejemplos están preparados pero comentados.")
        print("Requieren configuración de:")
        print("  • Hosts SSH válidos")
        print("  • Claves SSH configuradas")
        print("  • Permisos de usuario apropiados")
        
        # Descomentar para ejecutar con configuración real:
        # example_basic_ssh_execution()
        # example_parallel_execution()
        # example_sudo_execution()
        # example_password_authentication()
        # example_file_distribution()
        # example_directory_distribution()
        # example_network_scan()
        # example_port_scan()
        # example_batch_commands()
        # example_interactive_sudo()
        # example_output_formatting()
        # example_error_handling()
        
        print("\n" + "=" * 80)
        print("✓ Documentación de ejemplos lista")
        print("=" * 80)
        
        print("\nPara ejecutar:")
        print("  1. Configurar hosts y credenciales SSH")
        print("  2. Descomentar ejemplos deseados")
        print("  3. Ejecutar: python examples/remote.py")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
