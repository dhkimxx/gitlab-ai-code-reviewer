"""
Regression tests for the Ollama timeout configuration.

Background: production workers were observed stuck for 5–7 days inside
`llm.invoke()` against Ollama, with two TCP sockets in `tcp_recvmsg` waiting
forever. Root cause: `ChatOllama` does not have a `request_timeout` field —
the kwarg is silently dropped by the Pydantic model, so the underlying
httpx client is created with `timeout=None`. These tests pin both layers:

1. Unit-level: `_create_ollama_llm` must wire the timeout through
   `client_kwargs` (the only kwarg that `ChatOllama` actually forwards to
   the `ollama.Client`/httpx layer).

2. Behavioural: `llm.invoke(...)` against a server that never sends a
   response must raise within a bounded time, not hang forever.
"""
from __future__ import annotations

import socket
import threading
import time

import pytest

from src.infra.clients.llm import LLMClient, LLMClientConfig


def _ollama_config(base_url: str, timeout_seconds: float) -> LLMClientConfig:
    return LLMClientConfig(
        provider="ollama",
        model="dummy-model",
        timeout_seconds=timeout_seconds,
        max_retries=0,
        openai_api_key=None,
        google_api_key=None,
        ollama_base_url=base_url,
        openrouter_api_key=None,
        openrouter_base_url="",
    )


def test_create_ollama_llm_propagates_timeout_to_client_kwargs() -> None:
    """ChatOllama only honours timeout when supplied via `client_kwargs`."""
    cfg = _ollama_config("http://127.0.0.1:11434", timeout_seconds=12.5)
    client = LLMClient(cfg)
    llm = client._create_ollama_llm(temperature=0.5)

    client_kwargs = getattr(llm, "client_kwargs", None) or {}
    assert client_kwargs.get("timeout") == 12.5, (
        "timeout must reach ChatOllama.client_kwargs so it propagates to "
        f"the underlying ollama/httpx client. Got: {client_kwargs!r}"
    )


@pytest.fixture
def hanging_ollama_server():
    """TCP server that accepts connections but never sends a response.

    Mirrors the production failure mode where Ollama held the TCP socket
    open without producing a final/streamed response, leaving httpx blocked
    in `recv()` forever.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(16)
    port = sock.getsockname()[1]

    accepted: list[socket.socket] = []
    stop = threading.Event()

    def loop() -> None:
        sock.settimeout(0.1)
        while not stop.is_set():
            try:
                conn, _ = sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            accepted.append(conn)
            # Intentionally never write — let the client block on recv().

    thread = threading.Thread(target=loop, name="hanging-ollama", daemon=True)
    thread.start()

    yield f"http://127.0.0.1:{port}"

    stop.set()
    for conn in accepted:
        try:
            conn.close()
        except OSError:
            pass
    try:
        sock.close()
    except OSError:
        pass
    thread.join(timeout=1.0)


def test_ollama_invoke_against_hanging_server_raises_within_timeout(
    hanging_ollama_server: str,
) -> None:
    """`llm.invoke` must surface a timeout error instead of hanging forever.

    A small `timeout_seconds` is passed; if the timeout is not actually wired
    into the HTTP client, `invoke` will block indefinitely and the bounded
    `Thread.join` below will time out, failing the test.
    """
    cfg = _ollama_config(hanging_ollama_server, timeout_seconds=1.5)
    client = LLMClient(cfg)
    llm = client._create_ollama_llm(temperature=0.5)

    result: dict[str, object] = {"finished": False, "exc": None}

    def call() -> None:
        try:
            llm.invoke("ping")
        except BaseException as exc:  # noqa: BLE001 - capture anything
            result["exc"] = exc
        finally:
            result["finished"] = True

    started = time.monotonic()
    worker = threading.Thread(target=call, name="ollama-invoke", daemon=True)
    worker.start()
    # Generous upper bound: timeout=1.5s plus connection/init overhead.
    worker.join(timeout=8.0)
    elapsed = time.monotonic() - started

    assert result["finished"], (
        f"llm.invoke did not return within 8s (elapsed={elapsed:.1f}s). "
        "The HTTP timeout is not being applied — the client is hanging on recv()."
    )
    assert result["exc"] is not None, "Expected a timeout-related exception, got success."
