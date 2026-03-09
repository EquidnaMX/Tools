"""Tests for password notifications."""

import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from tools.password.models import NotificationConfig, PasswordChangeResult, OperationStatus
from tools.password.notifier import EmailNotifier, WebhookNotifier, NotificationManager


def _sample_results(status=OperationStatus.SUCCESS):
    return {
        "server1": PasswordChangeResult(
            host="server1",
            username="root",
            status=status,
            duration=1.0,
            verified=status == OperationStatus.SUCCESS,
        )
    }


def test_email_notifier_disabled_returns_false():
    cfg = NotificationConfig(email_enabled=False, recipient_emails=["admin@example.com"])
    notifier = EmailNotifier(cfg)

    assert notifier.send_notification(_sample_results()) is False


def test_email_notifier_sends_with_smtp_mock():
    cfg = NotificationConfig(
        email_enabled=True,
        smtp_server="smtp.example.com",
        smtp_port=587,
        smtp_use_tls=True,
        from_address="noreply@example.com",
        recipient_emails=["admin@example.com"],
    )
    notifier = EmailNotifier(cfg)

    smtp_instance = MagicMock()
    smtp_cm = MagicMock()
    smtp_cm.__enter__.return_value = smtp_instance
    smtp_cm.__exit__.return_value = False

    with patch("smtplib.SMTP", return_value=smtp_cm):
        sent = notifier.send_notification(_sample_results())

    assert sent is True
    assert smtp_instance.sendmail.called


def test_webhook_payload_contains_summary():
    cfg = NotificationConfig(webhook_enabled=True, webhook_urls=["https://example.com/hook"])
    notifier = WebhookNotifier(cfg)

    payload = notifier._build_payload(_sample_results(), "Password Change")

    assert payload["summary"]["total_operations"] == 1
    assert payload["details"][0]["host"] == "server1"


def test_webhook_send_returns_true_if_any_success():
    cfg = NotificationConfig(webhook_enabled=True, webhook_urls=["u1", "u2"])
    notifier = WebhookNotifier(cfg)

    with patch.object(notifier, "_send_webhook", new=AsyncMock(side_effect=[True, False])):
        result = asyncio.run(notifier.send_notification(_sample_results()))

    assert result is True


def test_notification_manager_routes_email_and_webhook():
    cfg = NotificationConfig(
        email_enabled=True,
        webhook_enabled=True,
        recipient_emails=["admin@example.com"],
        webhook_urls=["https://example.com/hook"],
        notify_on_success=True,
    )
    manager = NotificationManager(cfg)

    with patch.object(manager.email, "send_notification", return_value=True), \
         patch.object(manager.webhook, "send_notification", new=AsyncMock(return_value=True)):
        methods = asyncio.run(manager.notify_operation_completed(_sample_results(), success=True))

    assert "email" in methods
    assert "webhook" in methods
