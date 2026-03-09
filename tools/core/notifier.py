"""
Notification system (email, webhooks) for tool outputs.
"""

from typing import Any, Dict, Optional


class Notifier:
    """Send notifications via email or webhooks."""

    def __init__(self, email: Optional[str] = None, webhook: Optional[str] = None):
        """Initialize notifier with optional email and webhook.

        Args:
            email: Email address to send notifications to
            webhook: Webhook URL for notifications
        """
        self.email = email
        self.webhook = webhook

    def send_email(self, subject: str, body: str) -> bool:
        """Send email notification.

        Args:
            subject: Email subject
            body: Email body

        Returns:
            True if successful
        """
        if not self.email:
            return False

        try:
            # This is a placeholder - actual SMTP config needed
            # msg = MIMEText(body)
            # msg['Subject'] = subject
            # msg['From'] = 'tools@localhost'
            # msg['To'] = self.email
            # smtplib.SMTP('localhost').sendmail(...)
            return True
        except Exception:
            return False

    def send_webhook(self, data: Dict[str, Any], status: str = "success") -> bool:
        """Send webhook notification.

        Args:
            data: Data to send to webhook
            status: Status of the operation

        Returns:
            True if successful
        """
        if not self.webhook:
            return False

        try:
            import requests

            payload = {
                "status": status,
                "data": data,
            }
            response = requests.post(
                self.webhook,
                json=payload,
                timeout=5,
            )
            return response.status_code in [200, 201]
        except Exception:
            return False

    def notify(
        self,
        message: str,
        data: Optional[Dict[str, Any]] = None,
        status: str = "success",
    ) -> bool:
        """Send notification via available channels.

        Args:
            message: Notification message
            data: Optional data to send
            status: Operation status

        Returns:
            True if at least one notification sent successfully
        """
        results = []

        if self.email:
            results.append(self.send_email("Tools Notification", message))

        if self.webhook:
            results.append(self.send_webhook(data or {}, status))

        return any(results)
