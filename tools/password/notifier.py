"""
Notifications for password change events

Sends email and webhook notifications for password change operations.
"""

import smtplib
import asyncio
from typing import List
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from .models import NotificationConfig, OperationStatus

try:
    import aiohttp
except ImportError:  # pragma: no cover - optional dependency
    aiohttp = None


class EmailNotifier:
    """Send email notifications"""
    
    def __init__(self, config: NotificationConfig):
        """Initialize email notifier"""
        self.config = config
    
    def send_notification(
        self,
        results: dict,  # {host: PasswordChangeResult}
        subject: str = "Password Change Notification",
        include_results: bool = True
    ) -> bool:
        """
        Send email notification
        
        Args:
        - results: Dictionary of host: PasswordChangeResult
        - subject: Email subject
        - include_results: Include detailed results in email
        """
        if not self.config.email_enabled or not self.config.recipient_emails:
            return False
        
        try:
            # Build email body
            self._build_email_body(results, include_results)
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.config.from_address
            msg['To'] = ', '.join(self.config.recipient_emails)
            
            # Add HTML version
            html_body = self._build_html_body(results, include_results)
            msg.attach(MIMEText(html_body, 'html'))
            
            # Send email
            with smtplib.SMTP(self.config.smtp_server, self.config.smtp_port) as server:
                if self.config.smtp_use_tls:
                    server.starttls()
                
                if self.config.smtp_username and self.config.smtp_password:
                    server.login(self.config.smtp_username, self.config.smtp_password)
                
                server.sendmail(
                    self.config.from_address,
                    self.config.recipient_emails,
                    msg.as_string()
                )
            
            return True
        
        except Exception as e:
            print(f"Error sending email notification: {e}")
            return False
    
    def _build_email_body(self, results: dict, include_details: bool) -> str:
        """Build plain text email body"""
        body = f"""
Password Change Report
Generated: {datetime.utcnow().isoformat()}

SUMMARY
-------
"""
        
        # Count results
        success_count = sum(1 for r in results.values() if r.status == OperationStatus.SUCCESS)
        failed_count = sum(1 for r in results.values() if r.status == OperationStatus.FAILED)
        total_count = len(results)
        
        body += f"""
Total Operations: {total_count}
Successful: {success_count}
Failed: {failed_count}
Success Rate: {(success_count/total_count*100):.1f}%
"""
        
        if include_details:
            body += "\nDETAILS\n-------\n"
            for host, result in results.items():
                status_icon = "✓" if result.status == OperationStatus.SUCCESS else "✗"
                body += f"""\n[{status_icon}] {host} - {result.username}
    Status: {result.status.value}
    Duration: {result.duration:.1f}s
    Verified: {'Yes' if result.verified else 'No'}
"""
                if result.error:
                    body += f"    Error: {result.error}\n"
        
        return body
    
    def _build_html_body(self, results: dict, include_details: bool) -> str:
        """Build HTML email body"""
        success_count = sum(1 for r in results.values() if r.status == OperationStatus.SUCCESS)
        failed_count = sum(1 for r in results.values() if r.status == OperationStatus.FAILED)
        total_count = len(results)
        
        html = f"""
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background-color: #f0f0f0; padding: 10px; border-radius: 5px; }}
        .summary {{ margin: 20px 0; }}
        .success {{ color: green; }}
        .failed {{ color: red; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
        th {{ background-color: #4CAF50; color: white; }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Password Change Report</h1>
        <p>Generated: {datetime.utcnow().isoformat()}</p>
    </div>
    
    <div class="summary">
        <h2>Summary</h2>
        <ul>
            <li>Total Operations: {total_count}</li>
            <li><span class="success">Successful: {success_count}</span></li>
            <li><span class="failed">Failed: {failed_count}</span></li>
            <li>Success Rate: {(success_count/total_count*100):.1f}%</li>
        </ul>
    </div>
"""
        
        if include_details:
            html += """
    <h2>Details</h2>
    <table>
        <tr>
            <th>Host</th>
            <th>User</th>
            <th>Status</th>
            <th>Duration</th>
            <th>Verified</th>
            <th>Error</th>
        </tr>
"""
            
            for host, result in results.items():
                status_class = 'success' if result.status == OperationStatus.SUCCESS else 'failed'
                html += f"""
        <tr>
            <td>{host}</td>
            <td>{result.username}</td>
            <td class="{status_class}">{result.status.value}</td>
            <td>{result.duration:.1f}s</td>
            <td>{'✓' if result.verified else '✗'}</td>
            <td>{result.error or '—'}</td>
        </tr>
"""
            
            html += """
    </table>
"""
        
        html += """
</body>
</html>
"""
        
        return html


class WebhookNotifier:
    """Send webhook notifications"""
    
    def __init__(self, config: NotificationConfig):
        """Initialize webhook notifier"""
        self.config = config
    
    async def send_notification(
        self,
        results: dict,
        title: str = "Password Change Operation"
    ) -> bool:
        """
        Send webhook notifications asynchronously
        
        Args:
        - results: Dictionary of host: PasswordChangeResult
        - title: Notification title
        """
        if not self.config.webhook_enabled or not self.config.webhook_urls:
            return False
        
        payload = self._build_payload(results, title)
        
        tasks = [
            self._send_webhook(url, payload)
            for url in self.config.webhook_urls
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Return True if at least one succeeded
        return any(r is True for r in results)
    
    async def _send_webhook(self, url: str, payload: dict) -> bool:
        """Send single webhook request"""
        if aiohttp is None:
            print("Webhook notifications require aiohttp")
            return False

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(seconds=self.config.webhook_timeout_seconds),
                    headers={'Content-Type': 'application/json'}
                ) as response:
                    return 200 <= response.status < 300
        
        except asyncio.TimeoutError:
            print(f"Webhook timeout: {url}")
            return False
        except Exception as e:
            print(f"Webhook error ({url}): {e}")
            return False
    
    def _build_payload(self, results: dict, title: str) -> dict:
        """Build webhook payload"""
        success_count = sum(1 for r in results.values() if r.status == OperationStatus.SUCCESS)
        failed_count = sum(1 for r in results.values() if r.status == OperationStatus.FAILED)
        total_count = len(results)
        
        payload = {
            'title': title,
            'timestamp': datetime.utcnow().isoformat(),
            'summary': {
                'total_operations': total_count,
                'successful': success_count,
                'failed': failed_count,
                'success_rate': f'{(success_count/total_count*100):.1f}%'
            },
            'details': []
        }
        
        for host, result in results.items():
            payload['details'].append({
                'host': host,
                'username': result.username,
                'status': result.status.value,
                'duration': result.duration,
                'verified': result.verified,
                'error': result.error
            })
        
        return payload


class NotificationManager:
    """Manage all notifications"""
    
    def __init__(self, config: NotificationConfig):
        """Initialize notification manager"""
        self.config = config
        self.email = EmailNotifier(config)
        self.webhook = WebhookNotifier(config)
    
    async def notify_operation_completed(
        self,
        results: dict,
        success: bool = True,
        operation_type: str = "password_change"
    ) -> List[str]:
        """
        Send notifications for operation completion
        
        Returns:
        - List of notification methods used
        """
        notifications_sent = []
        
        # Determine if we should notify
        should_notify = (
            (success and self.config.notify_on_success) or
            (not success and self.config.notify_on_failure)
        )
        
        if not should_notify:
            return notifications_sent
        
        # Determine title
        if operation_type == "rotation":
            title = "Scheduled Password Rotation"
        elif success:
            title = "Password Change Successful"
        else:
            title = "Password Change Failed"
        
        # Send email
        if self.config.email_enabled:
            try:
                if self.email.send_notification(
                    results,
                    subject=title,
                    include_results=self.config.include_results_in_email
                ):
                    notifications_sent.append("email")
            except Exception as e:
                print(f"Email notification error: {e}")
        
        # Send webhooks
        if self.config.webhook_enabled:
            try:
                if await self.webhook.send_notification(results, title=title):
                    notifications_sent.append("webhook")
            except Exception as e:
                print(f"Webhook notification error: {e}")
        
        return notifications_sent
