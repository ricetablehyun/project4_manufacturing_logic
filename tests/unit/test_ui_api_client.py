from datetime import datetime

import httpx
import pytest

from production_control.ui.api_client import ApiClientError, ProductionControlApiClient


def test_ui_client_uses_expected_read_endpoints_and_as_of_query():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/forecast":
            return httpx.Response(200, json={"plan_id": "PLAN-1"})
        if request.url.path == "/lots":
            return httpx.Response(200, json=[])
        if request.url.path == "/inspection-gates":
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    as_of = datetime.fromisoformat("2026-10-05T10:00:00+09:00")

    with ProductionControlApiClient(
        base_url="http://api.test/",
        transport=transport,
    ) as client:
        assert client.get_forecast(as_of=as_of)["plan_id"] == "PLAN-1"
        assert client.list_lots() == []
        assert client.list_inspection_gates(lot_id="LOT-101") == []

    assert [request.url.path for request in requests] == [
        "/forecast",
        "/lots",
        "/inspection-gates",
    ]
    assert requests[0].url.params["as_of"] == "2026-10-05T10:00:00+09:00"
    assert requests[2].url.params["lot_id"] == "LOT-101"


def test_ui_client_rejects_unexpected_collection_payload():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"not": "a list"})
    )

    with ProductionControlApiClient(base_url="http://api.test", transport=transport) as client:
        with pytest.raises(ApiClientError, match="/lots returned an unexpected payload"):
            client.list_lots()


def test_ui_client_surfaces_api_error_detail_and_status_code():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(409, json={"detail": "forecast snapshot is stale"})
    )

    with ProductionControlApiClient(base_url="http://api.test", transport=transport) as client:
        with pytest.raises(ApiClientError, match="forecast snapshot is stale") as caught:
            client.get_forecast()

    assert caught.value.status_code == 409
