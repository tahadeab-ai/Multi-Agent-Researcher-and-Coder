"""Tests verifying the offline test guard (N2 requirement)."""

from __future__ import annotations

import asyncio
import socket

import pytest


def test_outbound_connection_blocked() -> None:
    """Outbound connection to public IP must be intercepted and raised."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(RuntimeError, match="Network access forbidden in unit tests"):
        s.connect(("8.8.8.8", 53))


@pytest.mark.asyncio
async def test_asyncio_socketpair_runs_under_guard() -> None:
    """Async test must successfully run under offline guard (loopback/socketpair preserved)."""
    await asyncio.sleep(0.01)
    assert True
