"""Tiny dependency-free client for the NetMon REST API (used by the lab and research scripts)."""

from __future__ import annotations

import contextlib
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class ApiError(RuntimeError):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status


class NetMonClient:
    def __init__(self, base_url: str, email: str, password: str, timeout: float = 15) -> None:
        if urllib.parse.urlsplit(base_url).scheme not in ("http", "https"):
            raise ValueError("the API URL must start with http:// or https://")
        self.base = base_url.rstrip("/") + "/api/v1"
        self.timeout = timeout
        form = urllib.parse.urlencode({"username": email, "password": password}).encode()
        req = urllib.request.Request(f"{self.base}/auth/login", data=form, method="POST")  # noqa: S310
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        self.token = self._send(req)["access_token"]

    def _send(self, req: urllib.request.Request) -> Any:
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
                body = resp.read()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            with contextlib.suppress(ValueError, AttributeError):
                detail = json.loads(detail).get("detail", detail)
            raise ApiError(exc.code, str(detail)) from None

    def request(self, method: str, path: str, body: Any = None, **params: Any) -> Any:
        clean = {k: v for k, v in params.items() if v is not None}
        query = urllib.parse.urlencode(clean, doseq=True)
        url = f"{self.base}{path}" + (f"?{query}" if query else "")
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)  # noqa: S310 - scheme checked
        req.add_header("Authorization", f"Bearer {self.token}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        return self._send(req)

    def get(self, path: str, **params: Any) -> Any:
        return self.request("GET", path, **params)

    def post(self, path: str, body: Any = None) -> Any:
        return self.request("POST", path, body if body is not None else {})

    def patch(self, path: str, body: Any) -> Any:
        return self.request("PATCH", path, body)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)

    def all_devices(self) -> list[dict[str, Any]]:
        return list(self.get("/devices", page_size=500)["items"])

    def find_device(self, name_or_id: str) -> dict[str, Any]:
        for device in self.all_devices():
            if str(device["id"]) == name_or_id or device["name"].lower() == name_or_id.lower():
                return device
        raise SystemExit(f"device {name_or_id!r} not found")
