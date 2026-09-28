"""HTTP client used by the Streamlit administrator UI."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

import httpx


class ApiClientError(RuntimeError):
    """Raised when the administrator UI cannot obtain a valid API response."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ProductionControlApiClient:
    """Small read-oriented client for the FastAPI boundary."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        normalized = base_url.rstrip("/")
        if not normalized:
            raise ValueError("base_url must not be empty")
        self._client = httpx.Client(
            base_url=normalized,
            timeout=timeout_seconds,
            transport=transport,
        )

    def __enter__(self) -> "ProductionControlApiClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _get_json(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> Any:
        try:
            response = self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise ApiClientError(f"API request failed: {exc}") from exc

        if response.is_error:
            detail: object
            try:
                payload = response.json()
                detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
            except ValueError:
                detail = response.text or response.reason_phrase
            raise ApiClientError(
                f"API returned {response.status_code}: {detail}",
                status_code=response.status_code,
            )

        try:
            return response.json()
        except ValueError as exc:
            raise ApiClientError("API returned invalid JSON") from exc

    def get_forecast(self, *, as_of: datetime | None = None) -> dict[str, Any]:
        params = {"as_of": as_of.isoformat()} if as_of is not None else None
        payload = self._get_json("/forecast", params=params)
        if not isinstance(payload, dict):
            raise ApiClientError("/forecast returned an unexpected payload")
        return payload

    def list_lots(self) -> list[dict[str, Any]]:
        payload = self._get_json("/lots")
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise ApiClientError("/lots returned an unexpected payload")
        return payload

    def list_inspection_gates(self, *, lot_id: str | None = None) -> list[dict[str, Any]]:
        params = {"lot_id": lot_id} if lot_id is not None else None
        payload = self._get_json("/inspection-gates", params=params)
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise ApiClientError("/inspection-gates returned an unexpected payload")
        return payload
