"""Local-first guarantee: the `ci explain` / classify path performs no network I/O.

PatchRail's headline positioning is "CI failure triage local-first". These tests
enforce that promise at runtime with CPython audit hooks (PEP 578): if the
classify/explain code path ever attempts an outbound connection or DNS lookup,
the audit event is recorded and the test fails. Unlike patching ``socket`` to
raise (which application code could swallow in a ``try/except``), an audit hook
cannot be suppressed by the code under test.
"""

from __future__ import annotations

import socket
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from patchrail.ci import classify_ci_log
from patchrail.cli import main

# Audit events raised by CPython for any outbound network activity.
_OUTBOUND_NET_EVENTS = frozenset(
    {
        "socket.connect",
        "socket.getaddrinfo",
        "socket.gethostbyname",
        "socket.gethostbyaddr",
        "urllib.Request",
        "http.client.connect",
    }
)


class _NetworkAuditGuard:
    """Records outbound-network audit events while armed.

    Audit hooks cannot be removed once installed, so a single guard is created at
    import time and gated by ``armed`` to stay inert outside the watched windows
    (and harmless to the rest of the suite).
    """

    def __init__(self) -> None:
        self.armed = False
        self.events: list[tuple[str, str]] = []
        sys.addaudithook(self._hook)

    def _hook(self, event: str, args: tuple) -> None:
        if self.armed and event in _OUTBOUND_NET_EVENTS:
            self.events.append((event, repr(args)[:200]))


_GUARD = _NetworkAuditGuard()


@contextmanager
def _watch_network() -> Iterator[_NetworkAuditGuard]:
    _GUARD.events.clear()
    _GUARD.armed = True
    try:
        yield _GUARD
    finally:
        _GUARD.armed = False


_EXAMPLE_LOG = (
    Path(__file__).resolve().parents[1] / "examples" / "ci-triage" / "dependency-failure.log"
)


def test_guard_detects_real_outbound_connection() -> None:
    """Meta-test: the guard has teeth.

    Without this, a broken guard would let every local-first assertion below pass
    vacuously. We attempt a real (loopback) connection and require it be seen.
    """
    with _watch_network() as guard:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.05)
        try:
            sock.connect_ex(("127.0.0.1", 9))  # discard port; nothing is sent
        finally:
            sock.close()
    assert guard.events, "network guard failed to observe an outbound connection"


def test_classify_ci_log_makes_no_network_calls() -> None:
    raw = _EXAMPLE_LOG.read_text(encoding="utf-8")
    with _watch_network() as guard:
        result = classify_ci_log(raw)
    assert result["failure_class"] == "python_dependency_resolution"
    assert guard.events == [], f"classify_ci_log touched the network: {guard.events}"


def test_ci_explain_cli_makes_no_network_calls(capsys) -> None:
    argv = ["ci", "explain", "--log", str(_EXAMPLE_LOG), "--format", "markdown"]
    with _watch_network() as guard:
        rc = main(argv)
    out = capsys.readouterr().out
    assert rc == 0
    assert "python_dependency_resolution" in out
    assert guard.events == [], f"`ci explain` touched the network: {guard.events}"


def test_ci_classify_cli_makes_no_network_calls(capsys) -> None:
    argv = ["ci", "classify", "--log", str(_EXAMPLE_LOG), "--format", "json"]
    with _watch_network() as guard:
        rc = main(argv)
    out = capsys.readouterr().out
    assert rc == 0
    assert "python_dependency_resolution" in out
    assert guard.events == [], f"`ci classify` touched the network: {guard.events}"
