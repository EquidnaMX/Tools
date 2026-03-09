#!/usr/bin/env python3
"""
Ejemplos de uso del módulo Mail Auditing.

Demuestra auditorías de mail servers, validación DNS (SPF, DKIM, DMARC),
domain health checking, y gestión de quotas.
"""

from pathlib import Path
from tools.mail import MailAuditor, DNSValidator, DomainHealthChecker


def example_basic_mail_audit():
    """Ejemplo básico de auditoría de mail server."""
    print("=" * 60)
    print("EJEMPLO 1: Auditoría Básica de Mail Server")
    print("=" * 60)
    
    auditor = MailAuditor(
        host="mail.example.com",
        user="admin",
        password="admin_password",  # Usar getpass() en producción
    )
    
    print(f"\n→ Auditando mail.example.com...")
    report = auditor.audit()
    
    print(f"\n✓ Reporte de Auditoría:")
    print(f"  Server: {report['server']}")
    print(f"  Version: {report['version']}")
    print(f"  Total Mailboxes: {report['total_mailboxes']}")
    print(f"  Total Messages: {report['total_messages']:,}")
    print(f"  Disk Usage: {report['disk_usage_gb']:.2f} GB")
    print(f"  Quotas Exceeded: {report['quotas_exceeded']}")


def example_dns_validation():
    """Ejemplo de validación DNS (SPF, DKIM, DMARC)."""
    print("\n" + "=" * 60)
    print("EJEMPLO 2: Validación DNS")
    print("=" * 60)
    
    validator = DNSValidator()
    
    domain = "example.com"
    
    print(f"\n→ Validando DNS para {domain}...")
    results = validator.validate(domain)
    
    # SPF
    print(f"\n📧 SPF Record:")
    if results['spf']['exists']:
        print(f"  ✓ Record encontrado: {results['spf']['record']}")
        print(f"  Valid: {'✓ Yes' if results['spf']['valid'] else '✗ No'}")
    else:
        print(f"  ✗ No SPF record found")
    
    # DKIM
    print(f"\n🔑 DKIM Record:")
    if results['dkim']['exists']:
        print(f"  ✓ Record encontrado")
        print(f"  Selector: {results['dkim']['selector']}")
        print(f"  Valid: {'✓ Yes' if results['dkim']['valid'] else '✗ No'}")
    else:
        print(f"  ✗ No DKIM record found")
    
    # DMARC
    print(f"\n🛡️ DMARC Record:")
    if results['dmarc']['exists']:
        print(f"  ✓ Record encontrado: {results['dmarc']['record']}")
        print(f"  Policy: {results['dmarc']['policy']}")
        print(f"  Valid: {'✓ Yes' if results['dmarc']['valid'] else '✗ No'}")
    else:
        print(f"  ✗ No DMARC record found")


def example_domain_health_check():
    """Ejemplo de health check completo de dominio."""
    print("\n" + "=" * 60)
    print("EJEMPLO 3: Health Check de Dominio")
    print("=" * 60)
    
    checker = DomainHealthChecker()
    
    domain = "example.com"
    
    print(f"\n→ Verificando salud de {domain}...")
    health = checker.check(domain)
    
    print(f"\n✓ Resultados:")
    print(f"  Score general: {health['score']}/100")
    
    print(f"\n  MX Records:")
    for mx in health['mx_records']:
        print(f"    • {mx['host']} (priority: {mx['priority']})")
    
    print(f"\n  Mail Server Tests:")
    for test, result in health['tests'].items():
        status = "✓" if result['passed'] else "✗"
        print(f"    {status} {test}: {result['message']}")
    
    print(f"\n  Recommendations:")
    for rec in health['recommendations']:
        print(f"    • {rec}")


def example_quota_management():
    """Ejemplo de gestión de quotas."""
    print("\n" + "=" * 60)
    print("EJEMPLO 4: Gestión de Quotas")
    print("=" * 60)
    
    auditor = MailAuditor(
        host="mail.example.com",
        user="admin",
        password="admin_password",
    )
    
    print(f"\n→ Obteniendo información de quotas...")
    quota_report = auditor.get_quota_report()
    
    print(f"\n✓ Reporte de Quotas:")
    print(f"  Total usuarios: {quota_report['total_users']}")
    print(f"  Usuarios con quota excedida: {quota_report['over_quota']}")
    
    print(f"\n  Top 10 usuarios por uso:")
    for user in quota_report['top_users'][:10]:
        usage_pct = (user['usage'] / user['quota']) * 100
        print(f"    {user['email']:<30} {user['usage']:>10,} / {user['quota']:>10,} MB ({usage_pct:>5.1f}%)")
    
    print(f"\n  Usuarios que necesitan atención:")
    for user in quota_report['attention_needed']:
        print(f"    ⚠️  {user['email']}: {user['reason']}")


def example_mailbox_analysis():
    """Ejemplo de análisis de mailboxes."""
    print("\n" + "=" * 60)
    print("EJEMPLO 5: Análisis de Mailboxes")
    print("=" * 60)
    
    auditor = MailAuditor(
        host="mail.example.com",
        user="admin",
        password="admin_password",
    )
    
    print(f"\n→ Analizando mailboxes...")
    analysis = auditor.analyze_mailboxes()
    
    print(f"\n✓ Análisis:")
    print(f"  Total mailboxes: {analysis['total']}")
    print(f"  Activos (últimos 30 días): {analysis['active']}")
    print(f"  Inactivos: {analysis['inactive']}")
    print(f"  Vacíos: {analysis['empty']}")
    
    print(f"\n  Distribución por tamaño:")
    for range_name, count in analysis['size_distribution'].items():
        print(f"    {range_name}: {count} mailboxes")
    
    print(f"\n  Mailboxes más grandes:")
    for mb in analysis['largest_mailboxes'][:5]:
        print(f"    {mb['email']:<30} {mb['size_mb']:>10,.1f} MB ({mb['message_count']:>8,} msgs)")


def example_spam_check():
    """Ejemplo de verificación antispam."""
    print("\n" + "=" * 60)
    print("EJEMPLO 6: Verificación Antispam")
    print("=" * 60)
    
    auditor = MailAuditor(
        host="mail.example.com",
        user="admin",
        password="admin_password",
    )
    
    print(f"\n→ Verificando configuración antispam...")
    spam_config = auditor.check_antispam()
    
    print(f"\n✓ Configuración Antispam:")
    print(f"  SpamAssassin: {'✓ Enabled' if spam_config['spamassassin']['enabled'] else '✗ Disabled'}")
    if spam_config['spamassassin']['enabled']:
        print(f"    Version: {spam_config['spamassassin']['version']}")
        print(f"    Required score: {spam_config['spamassassin']['required_score']}")
    
    print(f"  Greylisting: {'✓ Enabled' if spam_config['greylisting']['enabled'] else '✗ Disabled'}")
    print(f"  Blacklists: {len(spam_config['blacklists'])} configurados")
    
    print(f"\n  Estadísticas (últimos 7 días):")
    print(f"    Emails procesados: {spam_config['stats']['total']:,}")
    print(f"    Marcados como spam: {spam_config['stats']['spam']:,} ({spam_config['stats']['spam_percent']:.1f}%)")
    print(f"    Bloqueados: {spam_config['stats']['blocked']:,}")


def example_blacklist_check():
    """Ejemplo de verificación en blacklists."""
    print("\n" + "=" * 60)
    print("EJEMPLO 7: Verificación en Blacklists")
    print("=" * 60)
    
    checker = DomainHealthChecker()
    
    domain = "example.com"
    
    print(f"\n→ Verificando {domain} en blacklists...")
    blacklist_results = checker.check_blacklists(domain)
    
    print(f"\n✓ Resultados ({len(blacklist_results)} listas verificadas):")
    
    listed_count = sum(1 for r in blacklist_results if r['listed'])
    
    if listed_count == 0:
        print(f"  ✓ No encontrado en ninguna blacklist")
    else:
        print(f"  ⚠️  Encontrado en {listed_count} blacklists:")
        for bl in blacklist_results:
            if bl['listed']:
                print(f"    ✗ {bl['name']}: {bl['reason']}")


def example_tls_check():
    """Ejemplo de verificación TLS/SSL."""
    print("\n" + "=" * 60)
    print("EJEMPLO 8: Verificación TLS/SSL")
    print("=" * 60)
    
    checker = DomainHealthChecker()
    
    domain = "mail.example.com"
    
    print(f"\n→ Verificando TLS para {domain}...")
    tls_info = checker.check_tls(domain, port=25)
    
    print(f"\n✓ Información TLS:")
    print(f"  TLS disponible: {'✓ Yes' if tls_info['available'] else '✗ No'}")
    if tls_info['available']:
        print(f"  Version: {tls_info['version']}")
        print(f"  Cipher: {tls_info['cipher']}")
        print(f"  Certificate:")
        print(f"    Subject: {tls_info['cert']['subject']}")
        print(f"    Issuer: {tls_info['cert']['issuer']}")
        print(f"    Valid from: {tls_info['cert']['valid_from']}")
        print(f"    Valid until: {tls_info['cert']['valid_until']}")
        print(f"    Days remaining: {tls_info['cert']['days_remaining']}")
        
        if tls_info['cert']['days_remaining'] < 30:
            print(f"    ⚠️  Certificate expires soon!")


def example_imap_audit():
    """Ejemplo de auditoría IMAP."""
    print("\n" + "=" * 60)
    print("EJEMPLO 9: Auditoría IMAP")
    print("=" * 60)
    
    auditor = MailAuditor(
        host="mail.example.com",
        protocol="imap",
        port=993,
        user="admin",
        password="admin_password",
        use_ssl=True,
    )
    
    print(f"\n→ Auditando servidor IMAP...")
    imap_report = auditor.audit_imap()
    
    print(f"\n✓ Reporte IMAP:")
    print(f"  Server: {imap_report['server']}")
    print(f"  Capabilities: {', '.join(imap_report['capabilities'])}")
    print(f"  Total folders: {imap_report['total_folders']}")
    
    print(f"\n  Folders con más mensajes:")
    for folder in imap_report['top_folders'][:10]:
        print(f"    {folder['name']:<30} {folder['message_count']:>8,} msgs ({folder['size_mb']:>8.1f} MB)")


def example_pop3_audit():
    """Ejemplo de auditoría POP3."""
    print("\n" + "=" * 60)
    print("EJEMPLO 10: Auditoría POP3")
    print("=" * 60)
    
    auditor = MailAuditor(
        host="mail.example.com",
        protocol="pop3",
        port=995,
        user="admin",
        password="admin_password",
        use_ssl=True,
    )
    
    print(f"\n→ Auditando servidor POP3...")
    pop3_report = auditor.audit_pop3()
    
    print(f"\n✓ Reporte POP3:")
    print(f"  Server: {pop3_report['server']}")
    print(f"  Total messages: {pop3_report['total_messages']:,}")
    print(f"  Total size: {pop3_report['total_size_mb']:.2f} MB")
    print(f"  SSL/TLS: {'✓ Enabled' if pop3_report['ssl_enabled'] else '✗ Disabled'}")


def example_generate_report():
    """Ejemplo de generación de reporte completo."""
    print("\n" + "=" * 60)
    print("EJEMPLO 11: Reporte Completo")
    print("=" * 60)
    
    domain = "example.com"
    
    print(f"\n→ Generando reporte completo para {domain}...")
    
    # Validar DNS
    validator = DNSValidator()
    dns_results = validator.validate(domain)
    
    # Health check
    checker = DomainHealthChecker()
    health = checker.check(domain)
    
    # Auditoría mail server
    auditor = MailAuditor(
        host=f"mail.{domain}",
        user="admin",
        password="admin_password",
    )
    audit = auditor.audit()
    
    # Generar reporte
    report = {
        "domain": domain,
        "timestamp": "2026-03-08 20:00:00",
        "dns": dns_results,
        "health": health,
        "audit": audit,
    }
    
    # Guardar reporte
    output_file = Path.home() / "mail_reports" / f"{domain}_report.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    import json
    with output_file.open('w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n✓ Reporte generado:")
    print(f"  Archivo: {output_file}")
    print(f"  Tamaño: {output_file.stat().st_size:,} bytes")
    print(f"  DNS Score: {health['score']}/100")
    print(f"  Total Mailboxes: {audit['total_mailboxes']}")


def main():
    """Ejecutar todos los ejemplos."""
    print("\n" + "=" * 80)
    print(" " * 20 + "MAIL AUDITING - EJEMPLOS")
    print("=" * 80)
    
    try:
        print("\nNOTA: Los ejemplos están preparados pero comentados.")
        print("Requieren configuración de:")
        print("  • Mail server accesible")
        print("  • Credenciales de administrador")
        print("  • Dominio con DNS configurado")
        
        # Descomentar para ejecutar con configuración real:
        # example_basic_mail_audit()
        # example_dns_validation()
        # example_domain_health_check()
        # example_quota_management()
        # example_mailbox_analysis()
        # example_spam_check()
        # example_blacklist_check()
        # example_tls_check()
        # example_imap_audit()
        # example_pop3_audit()
        # example_generate_report()
        
        print("\n" + "=" * 80)
        print("✓ Documentación de ejemplos lista")
        print("=" * 80)
        
        print("\nPara ejecutar:")
        print("  1. Configurar mail server y credenciales")
        print("  2. Descomentar ejemplos deseados")
        print("  3. Ejecutar: python examples/mail.py")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
