"""The closed loop over a real TCP socket, not the in-process TestClient.

The repeated experiments use FastAPI's TestClient. This test runs the same
virtual terminal against the app served by uvicorn on localhost and talks to
it with httpx, so request encoding, the socket and response decoding are real.
It does not involve the Pico 2 WH hardware, which is not integrated.
"""

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI

from production_control.sim.harness import build_harness
from production_control.sim.manager import ApprovalPolicy
from production_control.sim.truth import TruthModel
from production_control.sim.worlds import F02_START, build_f02_world


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@contextmanager
def _serve(app: FastAPI) -> Iterator[str]:
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="off")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("uvicorn did not start")
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_approved_replan_changes_execution_over_a_real_socket(tmp_path: Path) -> None:
    clients: list[httpx.Client] = []
    servers = []

    def network_client(app: FastAPI) -> httpx.Client:
        context = _serve(app)
        base_url = context.__enter__()
        servers.append(context)
        client = httpx.Client(base_url=base_url, timeout=60)
        clients.append(client)
        return client

    database_path = build_f02_world(tmp_path / "w.db", baseline_lot_order=("LOT-102", "LOT-101"))
    harness = build_harness(
        database_path,
        truth=TruthModel(),
        start_time=F02_START,
        run_tag="NET",
        resend_every=4,
        client_factory=network_client,
    )
    try:
        result = harness.run(ApprovalPolicy.EDD)
    finally:
        for client in clients:
            client.close()
        for context in servers:
            context.__exit__(None, None, None)

    assert result.violations == []
    assert [item.candidate_id for item in result.approvals] == ["EDD"]
    tuning = sorted(
        (record for record in result.plant.records if record.process_code == "TUNING"),
        key=lambda record: record.started_at,
    )
    assert [record.lot_id for record in tuning] == ["LOT-101"] * 4 + ["LOT-102"] * 4
    assert result.calls.duplicate_events > 0
