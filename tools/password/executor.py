"""
Remote password execution via SSH

Handles password changes on remote Linux systems with verification and rollback.
"""

import asyncio
import subprocess
import json
from typing import Optional, Tuple
from datetime import datetime
from .models import PasswordChangeResult, OperationStatus


class RemotePasswordExecutor:
    """Executes password changes on remote hosts via SSH"""
    
    def __init__(self, timeout: int = 30):
        """Initialize executor"""
        self.timeout = timeout
    
    async def change_password_remote(
        self,
        host: str,
        username: str,
        old_password: str,
        new_password: str,
        use_sudo: bool = False,
        method: str = "auto"
    ) -> PasswordChangeResult:
        """
        Change password on remote host
        
        Args:
        - host: Hostname or IP address
        - username: Username to change
        - old_password: Current password (for sudo if needed)
        - new_password: New password to set
        - use_sudo: Use sudo for non-root changes
        - method: 'passwd', 'chpasswd', or 'auto' (detect)
        
        Returns:
        - PasswordChangeResult with status and details
        """
        start_time = datetime.utcnow()
        
        try:
            # Detect method if auto
            if method == "auto":
                method = await self._detect_method(host, username, old_password)
            
            # Execute password change
            if method == "chpasswd":
                success, output, error = await self._change_with_chpasswd(
                    host, username, new_password, old_password, use_sudo
                )
            else:  # passwd
                success, output, error = await self._change_with_passwd(
                    host, username, old_password, new_password, use_sudo
                )
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            
            if not success:
                return PasswordChangeResult(
                    host=host,
                    username=username,
                    status=OperationStatus.FAILED,
                    duration=duration,
                    error=error,
                    method=method,
                    output=output
                )
            
            # Verify the change
            verified = await self.verify_password_change(
                host, username, new_password
            )
            
            return PasswordChangeResult(
                host=host,
                username=username,
                status=OperationStatus.SUCCESS,
                duration=duration,
                verified=verified,
                method=method,
                output=output
            )
        
        except asyncio.TimeoutError:
            duration = (datetime.utcnow() - start_time).total_seconds()
            return PasswordChangeResult(
                host=host,
                username=username,
                status=OperationStatus.TIMEOUT,
                duration=duration,
                error="Connection timeout",
                retry_available=True
            )
        
        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            return PasswordChangeResult(
                host=host,
                username=username,
                status=OperationStatus.FAILED,
                duration=duration,
                error=str(e)
            )
    
    async def _detect_method(
        self,
        host: str,
        username: str,
        password: str
    ) -> str:
        """Detect available password change method"""
        # Try chpasswd first (batch mode, more reliable)
        cmd = f"ssh {username}@{host} 'command -v chpasswd'"
        
        try:
            result = await asyncio.wait_for(
                asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                ),
                timeout=5
            )
            stdout, _ = await result.communicate()
            if stdout:
                return "chpasswd"
        except:
            pass
        
        return "passwd"
    
    async def _change_with_passwd(
        self,
        host: str,
        username: str,
        old_password: str,
        new_password: str,
        use_sudo: bool
    ) -> Tuple[bool, str, str]:
        """
        Change password using passwd command
        
        This is interactive:
        1. Prompt for old password
        2. Prompt for new password
        3. Prompt to confirm new password
        """
        # Build expect-like script for interactive passwd
        script = f"""
#!/bin/bash
set -e
(
  sleep 1
  echo "{old_password}"
  sleep 0.5
  echo "{new_password}"
  sleep 0.5
  echo "{new_password}"
  sleep 0.5
) | passwd {username}
"""
        
        cmd = f"ssh {username}@{host} 'bash -s'"
        
        try:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(script.encode()),
                timeout=self.timeout
            )
            
            success = process.returncode == 0
            
            # Parse output
            output = stdout.decode('utf-8', errors='ignore')
            error = stderr.decode('utf-8', errors='ignore')
            
            # Check for common success messages
            if "password updated successfully" in output.lower() or \
               "passwd:" in output:
                success = True
            
            return success, output, error
        
        except asyncio.TimeoutError:
            return False, "", "Timeout during password change"
        except Exception as e:
            return False, "", str(e)
    
    async def _change_with_chpasswd(
        self,
        host: str,
        username: str,
        new_password: str,
        old_password: str,
        use_sudo: bool
    ) -> Tuple[bool, str, str]:
        """
        Change password using chpasswd (batch mode)
        
        Requires root or sudo with NOPASSWD for chpasswd
        """
        # Build chpasswd command
        change_cmd = f"echo '{username}:{new_password}' | chpasswd"
        
        if use_sudo:
            full_cmd = f"ssh root@{host} '{change_cmd}'"
        else:
            full_cmd = f"ssh {username}@{host} 'sudo {change_cmd}'"
        
        try:
            process = await asyncio.create_subprocess_shell(
                full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout
            )
            
            success = process.returncode == 0
            
            output = stdout.decode('utf-8', errors='ignore')
            error = stderr.decode('utf-8', errors='ignore')
            
            return success, output, error
        
        except asyncio.TimeoutError:
            return False, "", "Timeout during password change"
        except Exception as e:
            return False, "", str(e)
    
    async def verify_password_change(
        self,
        host: str,
        username: str,
        password: str
    ) -> bool:
        """
        Verify password change by attempting SSH login
        
        Returns True if login succeeds with new password
        """
        # Try to SSH with new password
        cmd = f"sshpass -p '{password}' ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no {username}@{host} 'exit 0'"
        
        try:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            _, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=10
            )
            
            return process.returncode == 0
        
        except:
            return False
    
    async def rollback_password(
        self,
        host: str,
        username: str,
        previous_password: str
    ) -> bool:
        """
        Rollback to previous password in case of failure
        
        Returns True if rollback succeeded
        """
        result = await self._change_with_passwd(
            host, username, "dummy_old", previous_password, False
        )
        
        # Note: This is a simplified version in production,
        # would need more sophisticated handling
        return result[0]


class SSHExecutor:
    """Low-level SSH command executor"""
    
    @staticmethod
    async def execute(
        host: str,
        command: str,
        username: str = "root",
        password: Optional[str] = None,
        key_file: Optional[str] = None,
        timeout: int = 30
    ) -> Tuple[int, str, str]:
        """
        Execute command on remote host
        
        Args:
        - host: hostname or IP
        - command: command to execute
        - username: SSH user
        - password: SSH password (if sshpass available)
        - key_file: SSH private key path
        - timeout: command timeout in seconds
        
        Returns:
        - (returncode, stdout, stderr)
        """
        # Build SSH command
        ssh_opts = "-o ConnectTimeout=5 -o StrictHostKeyChecking=no"
        
        if key_file:
            ssh_cmd = f"ssh {ssh_opts} -i {key_file} {username}@{host} '{command}'"
        elif password:
            ssh_cmd = f"sshpass -p '{password}' ssh {ssh_opts} {username}@{host} '{command}'"
        else:
            ssh_cmd = f"ssh {ssh_opts} {username}@{host} '{command}'"
        
        try:
            process = await asyncio.create_subprocess_shell(
                ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            
            return (
                process.returncode,
                stdout.decode('utf-8', errors='ignore'),
                stderr.decode('utf-8', errors='ignore')
            )
        
        except asyncio.TimeoutError:
            return 124, "", "Command timeout"
        except Exception as e:
            return 1, "", str(e)
