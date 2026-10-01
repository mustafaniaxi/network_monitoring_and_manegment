"""Outbound alert notifications: generic/Slack/Discord-compatible webhook and SMTP e-mail."""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage
from typing import Any

import httpx

from netmon.core.config import Settings
from netmon.models import AlertSeverity
from netmon.services.alerting.engine import AlertTransition

log = logging.getLogger(__name__)


def transition_payload(t: AlertTransition) -> dict[str, Any]:
    alert = t.alert
    text = alert.message if t.kind == "opened" else (alert.resolution_note or alert.message)
    return {
        "event": f"alert.{t.kind}",
        "text": text,  # Slack / Mattermost / Rocket.Chat
        "content": text,  # Discord
        "alert": {
            "id": alert.id,
            "device_id": alert.device_id,
            "device": t.device_name,
            "title": alert.title,
            "metric": alert.metric.value,
            "severity": alert.severity.value,
            "status": alert.status.value,
            "value": alert.value,
            "threshold": alert.threshold,
            "triggered_at": alert.triggered_at.isoformat(),
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
        },
    }


class Notifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.min_rank = AlertSeverity(settings.alert_min_severity).rank
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def enabled(self) -> bool:
        return bool(
            self.settings.alert_webhook_url or (self.settings.smtp_host and self.settings.smtp_to)
        )

    def dispatch(self, transitions: list[AlertTransition]) -> None:
        """Fire-and-forget delivery so slow endpoints never stall the poller."""
        if not self.enabled:
            return
        for t in transitions:
            if t.alert.severity.rank < self.min_rank:
                continue
            task = asyncio.create_task(self._deliver(transition_payload(t)))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _deliver(self, payload: dict[str, Any]) -> None:
        if self.settings.alert_webhook_url:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(self.settings.alert_webhook_url, json=payload)
                    resp.raise_for_status()
            except httpx.HTTPError as exc:
                log.warning("webhook notification failed: %s", exc)
        if self.settings.smtp_host and self.settings.smtp_to:
            try:
                await asyncio.to_thread(self._send_email, payload)
            except (OSError, smtplib.SMTPException) as exc:
                log.warning("e-mail notification failed: %s", exc)

    def _send_email(self, payload: dict[str, Any]) -> None:
        s = self.settings
        alert = payload["alert"]
        msg = EmailMessage()
        msg["Subject"] = f"[NetMon][{alert['severity'].upper()}] {payload['text']}"
        msg["From"] = s.smtp_from
        msg["To"] = ", ".join(s.smtp_to)
        msg.set_content(
            "\n".join(
                [
                    payload["text"],
                    "",
                    f"Device:    {alert['device']}",
                    f"Rule:      {alert['title']}",
                    f"Severity:  {alert['severity']}",
                    f"Value:     {alert['value']}",
                    f"Threshold: {alert['threshold']}",
                    f"Triggered: {alert['triggered_at']}",
                    f"Resolved:  {alert['resolved_at'] or '-'}",
                ]
            )
        )
        assert s.smtp_host is not None
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            if s.smtp_starttls:
                smtp.starttls()
            if s.smtp_username and s.smtp_password:
                smtp.login(s.smtp_username, s.smtp_password.get_secret_value())
            smtp.send_message(msg)

    async def aclose(self) -> None:
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=5)
