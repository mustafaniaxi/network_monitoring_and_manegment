from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from netmon.core.config import Settings
from netmon.db.base import utcnow
from netmon.models import Alert, AlertMetric, AlertSeverity, AlertStatus
from netmon.services.alerting.engine import AlertTransition
from netmon.services.alerting.notifiers import Notifier, transition_payload


def make_transition(severity: AlertSeverity = AlertSeverity.CRITICAL) -> AlertTransition:
    alert = Alert(
        id=5, device_id=1, metric=AlertMetric.DEVICE_DOWN, severity=severity,
        status=AlertStatus.ACTIVE, title="Device unreachable",
        message="ALERT: Database Server is unreachable.", triggered_at=utcnow(),
    )  # fmt: skip
    return AlertTransition("opened", alert, "Database Server")


def test_payload_is_chat_compatible():
    payload = transition_payload(make_transition())
    assert payload["event"] == "alert.opened"
    assert payload["text"] == payload["content"] == "ALERT: Database Server is unreachable."
    assert payload["alert"]["severity"] == "critical"


async def test_webhook_delivery_and_severity_filter(monkeypatch: pytest.MonkeyPatch):
    received: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(json.loads(request.content))
        return httpx.Response(204)

    real_client = httpx.AsyncClient

    def fake_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        return real_client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)
    settings = Settings(alert_webhook_url="https://hooks.example/netmon",
                        alert_min_severity="warning", secret_key=SecretStr("x" * 40))  # fmt: skip
    notifier = Notifier(settings)
    assert notifier.enabled
    notifier.dispatch([make_transition(AlertSeverity.INFO), make_transition()])
    await notifier.aclose()
    await asyncio.sleep(0)
    assert len(received) == 1
    assert received[0]["text"] == "ALERT: Database Server is unreachable."


async def test_notifier_disabled_without_targets():
    notifier = Notifier(Settings())
    assert not notifier.enabled
    notifier.dispatch([make_transition()])  # no-op, must not raise
    await notifier.aclose()
