"""``/ping`` cog helper tests."""

from __future__ import annotations

from butler.bot.cogs.ping import format_ping_response


def test_format_ping_response_ready() -> None:
    out = format_ping_response(latency_ms=42, version="0.1.0", ready=True)
    assert out == "Pong. gateway=42ms, app=v0.1.0, ready=true"


def test_format_ping_response_not_ready() -> None:
    out = format_ping_response(latency_ms=0, version="0.0.0", ready=False)
    assert out == "Pong. gateway=0ms, app=v0.0.0, ready=false"


def test_format_ping_response_high_latency() -> None:
    out = format_ping_response(latency_ms=1234, version="9.9.9", ready=True)
    assert "gateway=1234ms" in out
    assert "app=v9.9.9" in out
