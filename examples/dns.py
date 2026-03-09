#!/usr/bin/env python3
"""
Ejemplos de uso del módulo DNS Management.

Demuestra DNS replication checking, zone management, NS record fixing,
y gestión de servidores DNS (Bind, PowerDNS).
"""

from pathlib import Path
from tools.dns import DNSReplicator, ZoneManager, NSFixer, DNSInstaller


def example_check_replication():
    """Ejemplo básico de verificación de replicación DNS."""
    print("=" * 60)
    print("EJEMPLO 1: Verificación de Replicación DNS")
    print("=" * 60)
    
    replicator = DNSReplicator()
    
    domain = "example.com"
    record_type = "A"
    
    nameservers = [
        "ns1.example.com",
        "ns2.example.com",
        "ns3.example.com",
    ]
    
    print(f"\n→ Verificando replicación de {domain} ({record_type})...")
    results = replicator.check_replication(
        domain=domain,
        record_type=record_type,
        nameservers=nameservers,
    )
    
    print(f"\n✓ Resultados:")
    print(f"  Replicación: {'✓ OK' if results['replicated'] else '✗ FALLO'}")
    print(f"  Servidores verificados: {results['total_servers']}")
    print(f"  Servidores en sync: {results['synced_servers']}")
    
    print(f"\n  Respuestas por servidor:")
    for ns, response in results['responses'].items():
        print(f"    {ns}: {response}")


def example_check_all_record_types():
    """Ejemplo de verificación de múltiples tipos de registros."""
    print("\n" + "=" * 60)
    print("EJEMPLO 2: Verificar Múltiples Tipos de Registros")
    print("=" * 60)
    
    replicator = DNSReplicator()
    
    domain = "example.com"
    record_types = ["A", "AAAA", "MX", "TXT", "NS", "SOA"]
    
    print(f"\n→ Verificando {len(record_types)} tipos de registros...")
    
    for rtype in record_types:
        print(f"\n  {rtype} Records:")
        results = replicator.check_replication(
            domain=domain,
            record_type=rtype,
        )
        
        if results['replicated']:
            print(f"    ✓ Replicado correctamente")
            print(f"    Valor: {results['canonical_response']}")
        else:
            print(f"    ✗ Inconsistencia detectada")
            print(f"    Diferencias encontradas entre nameservers")


def example_zone_management():
    """Ejemplo de gestión de zonas DNS."""
    print("\n" + "=" * 60)
    print("EJEMPLO 3: Gestión de Zonas DNS")
    print("=" * 60)
    
    manager = ZoneManager(
        server="ns1.example.com",
        server_type="bind",  # o "powerdns"
        config_dir="/etc/bind",
    )
    
    # Listar zonas
    print(f"\n→ Listando zonas configuradas...")
    zones = manager.list_zones()
    
    print(f"\n✓ Zonas encontradas ({len(zones)}):")
    for zone in zones:
        print(f"  • {zone['name']}")
        print(f"    Type: {zone['type']}")
        print(f"    Serial: {zone['serial']}")
        print(f"    Records: {zone['record_count']}")


def example_create_zone():
    """Ejemplo de creación de zona DNS."""
    print("\n" + "=" * 60)
    print("EJEMPLO 4: Crear Zona DNS")
    print("=" * 60)
    
    manager = ZoneManager(
        server="ns1.example.com",
        server_type="bind",
        config_dir="/etc/bind",
    )
    
    zone_name = "newdomain.com"
    
    print(f"\n→ Creando zona {zone_name}...")
    success = manager.create_zone(
        zone_name=zone_name,
        zone_type="master",
        admin_email="admin@newdomain.com",
        nameservers=["ns1.example.com", "ns2.example.com"],
        default_ttl=3600,
    )
    
    if success:
        print(f"✓ Zona creada exitosamente")
        print(f"  Archivo: /etc/bind/zones/db.{zone_name}")
        print(f"  Serial: {manager.get_zone_serial(zone_name)}")
    else:
        print(f"✗ Error al crear zona")


def example_add_records():
    """Ejemplo de añadir registros a una zona."""
    print("\n" + "=" * 60)
    print("EJEMPLO 5: Añadir Registros DNS")
    print("=" * 60)
    
    manager = ZoneManager(
        server="ns1.example.com",
        server_type="bind",
        config_dir="/etc/bind",
    )
    
    zone_name = "example.com"
    
    # Añadir registro A
    print(f"\n→ Añadiendo registro A...")
    manager.add_record(
        zone=zone_name,
        name="www",
        record_type="A",
        value="192.168.1.100",
        ttl=3600,
    )
    print(f"✓ www.{zone_name} → 192.168.1.100")
    
    # Añadir registro MX
    print(f"\n→ Añadiendo registro MX...")
    manager.add_record(
        zone=zone_name,
        name="@",
        record_type="MX",
        value="mail.example.com",
        priority=10,
        ttl=3600,
    )
    print(f"✓ MX record added")
    
    # Añadir registro TXT (SPF)
    print(f"\n→ Añadiendo registro TXT (SPF)...")
    manager.add_record(
        zone=zone_name,
        name="@",
        record_type="TXT",
        value='"v=spf1 mx include:_spf.google.com ~all"',
        ttl=3600,
    )
    print(f"✓ SPF record added")


def example_update_serial():
    """Ejemplo de actualización de serial de zona."""
    print("\n" + "=" * 60)
    print("EJEMPLO 6: Actualizar Serial de Zona")
    print("=" * 60)
    
    manager = ZoneManager(
        server="ns1.example.com",
        server_type="bind",
        config_dir="/etc/bind",
    )
    
    zone_name = "example.com"
    
    print(f"\n→ Serial actual de {zone_name}...")
    old_serial = manager.get_zone_serial(zone_name)
    print(f"  Serial actual: {old_serial}")
    
    print(f"\n→ Incrementando serial...")
    new_serial = manager.increment_serial(zone_name)
    print(f"  Nuevo serial: {new_serial}")
    
    print(f"\n→ Recargando zona...")
    manager.reload_zone(zone_name)
    print(f"✓ Zona recargada")


def example_fix_ns_records():
    """Ejemplo de corrección de registros NS."""
    print("\n" + "=" * 60)
    print("EJEMPLO 7: Corregir Registros NS")
    print("=" * 60)
    
    fixer = NSFixer()
    
    domain = "example.com"
    
    print(f"\n→ Verificando registros NS para {domain}...")
    current_ns = fixer.get_ns_records(domain)
    
    print(f"\n  NS records actuales:")
    for ns in current_ns:
        print(f"    • {ns}")
    
    # Registros NS correctos
    correct_ns = [
        "ns1.example.com",
        "ns2.example.com",
        "ns3.example.com",
    ]
    
    print(f"\n→ Comparando con configuración correcta...")
    issues = fixer.find_ns_issues(domain, correct_ns)
    
    if not issues:
        print(f"✓ NS records correctos")
    else:
        print(f"✗ Problemas encontrados:")
        for issue in issues:
            print(f"    • {issue['type']}: {issue['description']}")
        
        print(f"\n→ Corrigiendo NS records...")
        success = fixer.fix_ns_records(domain, correct_ns)
        
        if success:
            print(f"✓ NS records corregidos")
        else:
            print(f"✗ Error al corregir NS records")


def example_dns_propagation_check():
    """Ejemplo de verificación de propagación DNS."""
    print("\n" + "=" * 60)
    print("EJEMPLO 8: Verificar Propagación DNS")
    print("=" * 60)
    
    replicator = DNSReplicator()
    
    domain = "newdomain.com"
    record_type = "A"
    expected_value = "192.168.1.100"
    
    # Lista de resolvers públicos para verificar propagación
    public_resolvers = [
        "8.8.8.8",          # Google
        "1.1.1.1",          # Cloudflare
        "208.67.222.222",   # OpenDNS
        "9.9.9.9",          # Quad9
    ]
    
    print(f"\n→ Verificando propagación de {domain}...")
    print(f"  Valor esperado: {expected_value}")
    
    results = []
    for resolver in public_resolvers:
        print(f"\n  Consultando {resolver}...")
        value = replicator.query_resolver(
            domain=domain,
            record_type=record_type,
            resolver=resolver,
        )
        
        propagated = (value == expected_value)
        results.append({
            "resolver": resolver,
            "value": value,
            "propagated": propagated,
        })
        
        status = "✓" if propagated else "✗"
        print(f"    {status} {value}")
    
    propagated_count = sum(1 for r in results if r['propagated'])
    print(f"\n✓ Propagación: {propagated_count}/{len(public_resolvers)} resolvers")


def example_install_bind():
    """Ejemplo de instalación de Bind DNS server."""
    print("\n" + "=" * 60)
    print("EJEMPLO 9: Instalar Bind DNS Server")
    print("=" * 60)
    
    installer = DNSInstaller(server_type="bind")
    
    print(f"\n→ Instalando Bind...")
    print(f"  • Instalando paquetes")
    print(f"  • Configurando archivos base")
    print(f"  • Creando directorio de zonas")
    print(f"  • Configurando logging")
    
    success = installer.install(
        config_dir="/etc/bind",
        zones_dir="/etc/bind/zones",
        enable_dnssec=True,
        enable_recursion=False,
    )
    
    if success:
        print(f"\n✓ Bind instalado correctamente")
        print(f"  Config: /etc/bind/named.conf")
        print(f"  Zones: /etc/bind/zones/")
        print(f"  Service: sudo systemctl start bind9")
    else:
        print(f"\n✗ Error en instalación")


def example_install_powerdns():
    """Ejemplo de instalación de PowerDNS server."""
    print("\n" + "=" * 60)
    print("EJEMPLO 10: Instalar PowerDNS Server")
    print("=" * 60)
    
    installer = DNSInstaller(server_type="powerdns")
    
    print(f"\n→ Instalando PowerDNS...")
    print(f"  • Instalando paquetes")
    print(f"  • Configurando MySQL backend")
    print(f"  • Creando base de datos")
    print(f"  • Configurando API")
    
    success = installer.install(
        backend="mysql",
        db_host="localhost",
        db_name="powerdns",
        db_user="pdns",
        db_password="secure_password",
        enable_api=True,
        api_key="random_api_key_here",
    )
    
    if success:
        print(f"\n✓ PowerDNS instalado correctamente")
        print(f"  Config: /etc/powerdns/pdns.conf")
        print(f"  Database: powerdns @ localhost")
        print(f"  API: http://localhost:8081")
        print(f"  Service: sudo systemctl start pdns")
    else:
        print(f"\n✗ Error en instalación")


def example_zone_transfer():
    """Ejemplo de transferencia de zona (AXFR)."""
    print("\n" + "=" * 60)
    print("EJEMPLO 11: Transferencia de Zona (AXFR)")
    print("=" * 60)
    
    manager = ZoneManager(
        server="ns1.example.com",
        server_type="bind",
    )
    
    zone_name = "example.com"
    slave_server = "ns2.example.com"
    
    print(f"\n→ Configurando transferencia de zona...")
    print(f"  Master: ns1.example.com")
    print(f"  Slave: {slave_server}")
    
    success = manager.configure_zone_transfer(
        zone=zone_name,
        slave_servers=[slave_server],
        also_notify=True,
    )
    
    if success:
        print(f"\n✓ Transferencia configurada")
        print(f"  Slave puede solicitar AXFR")
        print(f"  Notificaciones automáticas habilitadas")
    else:
        print(f"\n✗ Error al configurar transferencia")


def example_dnssec_setup():
    """Ejemplo de configuración de DNSSEC."""
    print("\n" + "=" * 60)
    print("EJEMPLO 12: Configurar DNSSEC")
    print("=" * 60)
    
    manager = ZoneManager(
        server="ns1.example.com",
        server_type="bind",
    )
    
    zone_name = "example.com"
    
    print(f"\n→ Habilitando DNSSEC para {zone_name}...")
    
    success = manager.enable_dnssec(
        zone=zone_name,
        algorithm="RSASHA256",
        key_size=2048,
    )
    
    if success:
        print(f"\n✓ DNSSEC habilitado")
        print(f"  Algoritmo: RSASHA256")
        print(f"  Key size: 2048 bits")
        
        # Obtener DS records para registrar en el registrar
        ds_records = manager.get_ds_records(zone_name)
        
        print(f"\n  DS Records para registrar:")
        for ds in ds_records:
            print(f"    {ds}")
    else:
        print(f"\n✗ Error al habilitar DNSSEC")


def example_zone_validation():
    """Ejemplo de validación de zona DNS."""
    print("\n" + "=" * 60)
    print("EJEMPLO 13: Validar Zona DNS")
    print("=" * 60)
    
    manager = ZoneManager(
        server="ns1.example.com",
        server_type="bind",
    )
    
    zone_name = "example.com"
    
    print(f"\n→ Validando zona {zone_name}...")
    validation = manager.validate_zone(zone_name)
    
    print(f"\n✓ Resultados de validación:")
    print(f"  Sintaxis: {'✓ OK' if validation['syntax_ok'] else '✗ ERRORES'}")
    print(f"  Total registros: {validation['total_records']}")
    
    if validation['warnings']:
        print(f"\n  ⚠️  Advertencias:")
        for warning in validation['warnings']:
            print(f"    • {warning}")
    
    if validation['errors']:
        print(f"\n  ✗ Errores:")
        for error in validation['errors']:
            print(f"    • {error}")
    else:
        print(f"\n  ✓ Sin errores")


def main():
    """Ejecutar todos los ejemplos."""
    print("\n" + "=" * 80)
    print(" " * 20 + "DNS MANAGEMENT - EJEMPLOS")
    print("=" * 80)
    
    try:
        print("\nNOTA: Los ejemplos están preparados pero comentados.")
        print("Requieren configuración de:")
        print("  • Servidor DNS (Bind o PowerDNS)")
        print("  • Permisos de administrador")
        print("  • Zonas DNS configuradas")
        
        # Descomentar para ejecutar con configuración real:
        # example_check_replication()
        # example_check_all_record_types()
        # example_zone_management()
        # example_create_zone()
        # example_add_records()
        # example_update_serial()
        # example_fix_ns_records()
        # example_dns_propagation_check()
        # example_install_bind()
        # example_install_powerdns()
        # example_zone_transfer()
        # example_dnssec_setup()
        # example_zone_validation()
        
        print("\n" + "=" * 80)
        print("✓ Documentación de ejemplos lista")
        print("=" * 80)
        
        print("\nPara ejecutar:")
        print("  1. Configurar servidor DNS y permisos")
        print("  2. Descomentar ejemplos deseados")
        print("  3. Ejecutar: python examples/dns.py")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
