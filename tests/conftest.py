"""pytest global configuration and fixtures.

Includes:
- N2: Offline test guard blocking outbound non-loopback connections
  while preserving asyncio socketpair and loopback connections.
"""

from __future__ import annotations

import socket
from typing import Any

import pytest

_ORIGINAL_CONNECT = socket.socket.connect
_ORIGINAL_CREATE_CONNECTION = socket.create_connection

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def _is_loopback(host: Any) -> bool:
    if isinstance(host, str):
        return host in _LOOPBACK_HOSTS
    return False


def _guarded_connect(self: socket.socket, address: Any) -> None:
    host = address[0] if isinstance(address, tuple) and address else address
    if not _is_loopback(host):
        raise RuntimeError(
            f"Network access forbidden in unit tests: attempted connection to {address}"
        )
    _ORIGINAL_CONNECT(self, address)


def _guarded_create_connection(address: Any, *args: Any, **kwargs: Any) -> socket.socket:
    host = address[0] if isinstance(address, tuple) and address else address
    if not _is_loopback(host):
        raise RuntimeError(
            f"Network access forbidden in unit tests: attempted create_connection to {address}"
        )
    return _ORIGINAL_CREATE_CONNECTION(address, *args, **kwargs)


@pytest.fixture(autouse=True)
def offline_guard(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Block outbound socket connections unless test is marked with @pytest.mark.integration."""
    if request.node.get_closest_marker("integration"):
        return

    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    monkeypatch.setattr(socket, "create_connection", _guarded_create_connection)
