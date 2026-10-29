"""
Central password manager orchestrating all operations

Coordinates validators, generators, executors, auditors, LDAP sync, and notifications.
"""

import asyncio
import getpass
from typing import Dict, List, Optional, Tuple

from .models import (
    PasswordPolicy, PasswordChangeResult, OperationStatus, LDAPConfig,
    NotificationConfig, RotationPolicy, AuditEntry
)
from .validators import PasswordValidator, PasswordHistoryValidator
from .generators import PasswordGenerator
from .executor import RemotePasswordExecutor
from .auditor import AuditLogger
from .ldap_sync import LDAPSync
from .scheduler import PasswordRotationScheduler
from .notifier import NotificationManager


class PasswordManager:
    """
    Central password management system
    
    Coordinates:
    - Password validation and generation
    - Remote password changes with verification
    - LDAP synchronization
    - Audit logging
    - Notifications (email, webhooks)
    - Automatic rotation
    """
    
    def __init__(
        self,
        policy: Optional[PasswordPolicy] = None,
        ldap_config: Optional[LDAPConfig] = None,
        notification_config: Optional[NotificationConfig] = None,
        rotation_policy: Optional[RotationPolicy] = None
    ):
        """Initialize password manager"""
        
        # Policies
        self.policy = policy or PasswordPolicy()
        self.ldap_config = ldap_config
        self.notification_config = notification_config or NotificationConfig()
        self.rotation_policy = rotation_policy or RotationPolicy()
        
        # Components
        self.validator = PasswordValidator(self.policy)
        self.history_validator = PasswordHistoryValidator()
        self.generator = PasswordGenerator()
        self.executor = RemotePasswordExecutor()
        self.auditor = AuditLogger()
        self.ldap = LDAPSync(ldap_config) if ldap_config else None
        self.scheduler = PasswordRotationScheduler()
        self.notifier = NotificationManager(self.notification_config)
    
    def generate_password(
        self,
        length: int = 16,
        include_uppercase: bool = True,
        include_lowercase: bool = True,
        include_digits: bool = True,
        include_special: bool = True,
        exclude_ambiguous: bool = True
    ) -> str:
        """Generate secure password"""
        return self.generator.generate(
            length=length,
            include_uppercase=include_uppercase,
            include_lowercase=include_lowercase,
            include_digits=include_digits,
            include_special=include_special,
            exclude_ambiguous=exclude_ambiguous
        )
    
    def validate_password(self, password: str) -> Tuple[bool, dict]:
        """
        Validate password
        
        Returns:
        - (is_valid, validation_details)
        """
        result = self.validator.validate(password)
        
        return result.valid, {
            'valid': result.valid,
            'score': result.score,
            'errors': result.errors,
            'warnings': result.warnings,
            'entropy_bits': result.entropy_bits
        }
    
    async def change_password(
        self,
        hosts: List[str],
        username: str,
        old_password: Optional[str] = None,
        new_password: Optional[str] = None,
        auto_generate: bool = False,
        dry_run: bool = False,
        parallel_jobs: int = 3,
        verify: bool = True,
        ldap_sync: bool = True,
        notify: bool = True,
        reason: str = ""
    ) -> Dict[str, PasswordChangeResult]:
        """
        Change password on multiple hosts
        
        Args:
        - hosts: List of target hosts
        - username: Username to change
        - old_password: Current password (prompt if not provided)
        - new_password: New password (auto-generate if auto_generate=True)
        - dry_run: Simulate without executing
        - parallel_jobs: Number of parallel executions
        - verify: Verify change with SSH login
        - ldap_sync: Sync with LDAP
        - notify: Send notifications
        - reason: Reason for password change (logged in audit)
        
        Returns:
        - {host: PasswordChangeResult}
        """
        
        # Get operator info
        operator = self._get_operator_info()
        
        print(f"\n{'='*70}")
        print("PASSWORD CHANGE OPERATION")
        print(f"{'='*70}")
        print(f"Hosts: {len(hosts)} servidor(es)")
        for host in hosts:
            print(f"  - {host}")
        print(f"Usuario: {username}")
        print(f"Operador: {operator}")
        if reason:
            print(f"Razón: {reason}")
        print(f"Modo: {'DRY-RUN' if dry_run else 'EJECUCIÓN'}")
        print()
        
        # Get old password if not provided
        if old_password is None:
            old_password = self._get_password_securely(
                "Contraseña actual del usuario: "
            )
        
        # Get or generate new password
        if new_password is None:
            if auto_generate:
                new_password = self.generate_password()
                print(f"✓ Contraseña generada: {new_password}")
                valid, details = self.validate_password(new_password)
                print(f"  Fortaleza: {details['score']}/100 ({details['entropy_bits']:.1f} bits de entropía)")
            else:
                new_password = self._get_password_securely(
                    "Nueva contraseña: ",
                    confirm=True,
                    policy=self.policy
                )
        
        # Validate new password
        valid, details = self.validate_password(new_password)
        if not valid:
            print("❌ La contraseña no cumple la política:")
            for error in details['errors']:
                print(f"   - {error}")
            return {}
        
        # Confirmation
        if not self._confirm_operation(hosts, username, dry_run):
            print("❌ Operación cancelada por el usuario")
            return {}
        
        # Execute changes
        if dry_run:
            print("\n🧪 MODO DRY-RUN - Simulando cambios sin ejecutar...\n")
            results = {}
            for host in hosts:
                results[host] = PasswordChangeResult(
                    host=host,
                    username=username,
                    status=OperationStatus.SUCCESS,
                    duration=0.0,
                    verified=False
                )
        else:
            print(f"\n🔄 Ejecutando cambios en paralelo ({parallel_jobs} simultáneos)...\n")
            results = await self._execute_changes_parallel(
                hosts, username, old_password, new_password, parallel_jobs, verify
            )
        
        # LDAP sync
        if ldap_sync and self.ldap:
            print("\n🔄 Sincronizando con LDAP...")
            for host, result in results.items():
                if result.status == OperationStatus.SUCCESS:
                    success, msg = self.ldap.sync_password_change(
                        host, username, new_password, old_password
                    )
                    result.ldap_synced = success
                    if success:
                        print(f"  ✓ {host}: LDAP sincronizado")
                    else:
                        print(f"  ✗ {host}: Error LDAP - {msg}")
        
        # Audit logging
        print("\n📝 Registrando en auditoría...")
        for host, result in results.items():
            entry = AuditEntry(
                operation='change_success' if result.status == OperationStatus.SUCCESS else 'change_failed',
                operator=operator,
                host=host,
                username=username,
                status=result.status,
                duration=result.duration,
                verified=result.verified,
                method=result.method,
                ldap_synced=result.ldap_synced,
                result_message=result.error or "Cambio exitoso"
            )
            self.auditor.log_change(entry)
            result.audit_entry = entry.id
        
        # Notifications
        if notify:
            print("\n📧 Enviando notificaciones...")
            success_count = sum(1 for r in results.values() if r.status == OperationStatus.SUCCESS)
            all_success = success_count == len(results)
            
            notifications = asyncio.run(
                self.notifier.notify_operation_completed(
                    results,
                    success=all_success,
                    operation_type="password_change"
                )
            )
            if notifications:
                print(f"  ✓ Notificaciones enviadas: {', '.join(notifications)}")
        
        # Summary
        self._print_summary(results)
        
        return results
    
    async def _execute_changes_parallel(
        self,
        hosts: List[str],
        username: str,
        old_password: str,
        new_password: str,
        parallel_jobs: int,
        verify: bool
    ) -> Dict[str, PasswordChangeResult]:
        """Execute password changes in parallel"""
        
        results = {}
        semaphore = asyncio.Semaphore(parallel_jobs)
        
        async def change_on_host(host):
            async with semaphore:
                print(f"[{host}] Iniciando cambio de contraseña...")
                result = await self.executor.change_password_remote(
                    host=host,
                    username=username,
                    old_password=old_password,
                    new_password=new_password
                )
                
                if result.status == OperationStatus.SUCCESS and verify:
                    print(f"[{host}] Verificando cambio...")
                    result.verified = await self.executor.verify_password_change(
                        host, username, new_password
                    )
                
                status_icon = "✓" if result.status == OperationStatus.SUCCESS else "✗"
                print(f"[{host}] {status_icon} {result.status.value} ({result.duration:.1f}s)")
                
                results[host] = result
        
        tasks = [change_on_host(host) for host in hosts]
        await asyncio.gather(*tasks)
        
        return results
    
    def _get_password_securely(
        self,
        prompt: str,
        confirm: bool = False,
        policy: Optional[PasswordPolicy] = None
    ) -> str:
        """Get password securely from user input"""
        
        while True:
            password = getpass.getpass(prompt)
            
            if policy:
                validator = PasswordValidator(policy)
                result = validator.validate(password)
                if not result.valid:
                    print("❌ Contraseña no válida:")
                    for error in result.errors:
                        print(f"   - {error}")
                    continue
            
            if confirm:
                confirm_pwd = getpass.getpass("Confirmar contraseña: ")
                if password != confirm_pwd:
                    print("❌ Las contraseñas no coinciden")
                    continue
            
            return password
    
    def _confirm_operation(
        self,
        hosts: List[str],
        username: str,
        dry_run: bool
    ) -> bool:
        """Get user confirmation for operation"""
        
        if username == "root":
            print("\n⚠️  OPERACIÓN CRÍTICA")
            print(f"{'='*70}")
            print(f"Se cambiarán contraseñas del usuario: {username}")
            print(f"Servidores afectados ({len(hosts)}):")
            for host in hosts[:5]:  # Show first 5
                print(f"  - {host}")
            if len(hosts) > 5:
                print(f"  ... y {len(hosts) - 5} más")
            print(f"Modo: {'DRY-RUN (sin ejecutar cambios)' if dry_run else 'EJECUCIÓN'}")
            print()
            
            confirmation = f"sí, {'simular' if dry_run else f'cambiar {username}'}"
            response = input(f"¿Deseas proceder? (escribe '{confirmation}' para confirmar): ")
            
            return response.lower() == confirmation
        
        return True
    
    def _get_operator_info(self) -> str:
        """Get operator identification"""
        import os
        user = os.environ.get('USER') or os.environ.get('USERNAME') or 'unknown'
        return user
    
    def _print_summary(self, results: Dict[str, PasswordChangeResult]) -> None:
        """Print operation summary"""
        
        success = sum(1 for r in results.values() if r.status == OperationStatus.SUCCESS)
        failed = sum(1 for r in results.values() if r.status == OperationStatus.FAILED)
        timeout = sum(1 for r in results.values() if r.status == OperationStatus.TIMEOUT)
        
        print(f"\n{'='*70}")
        print("RESUMEN FINAL")
        print(f"{'='*70}")
        print(f"✓ Exitosos:  {success}/{len(results)}")
        print(f"✗ Fallidos:  {failed}/{len(results)}")
        print(f"⏳ Timeouts: {timeout}/{len(results)}")
        print(f"\nTasa de éxito: {(success/len(results)*100):.1f}%")
        print(f"{'='*70}\n")
    
    async def start_scheduler(self) -> None:
        """Start automatic password rotation scheduler"""
        
        async def rotation_callback(host: str, username: str) -> bool:
            """Callback for rotation"""
            print(f"🔄 Rotando contraseña para {username}@{host}")
            
            # Generate new password
            new_password = self.generate_password()
            
            # TODO: Obtener contraseña anterior (from vault/manager)
            old_password = "old_password"
            
            # Change password
            result = await self.executor.change_password_remote(
                host=host,
                username=username,
                old_password=old_password,
                new_password=new_password
            )
            
            return result.status == OperationStatus.SUCCESS
        
        await self.scheduler.schedule_rotation(
            self.rotation_policy,
            rotation_callback
        )
