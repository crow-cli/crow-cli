"""Async client for the crow-memory HTTP service (httpx.AsyncClient)."""

from __future__ import annotations

import asyncio
import base64
from typing import Any

import httpx

from .types import (
    _RETRYABLE_STATUS,
    AgentRecord,
    ImageRecord,
    MemoryApiError,
    MessageRecord,
    PromptRecord,
    SessionInfo,
    default_memory_url,
)


class MemoryClient:
    """Async client for one crow-memory server.

    Retry policy (ported from the Rust SDK): connect errors, timeouts, and
    502/503/504 back off exponentially for up to `max_retries` attempts;
    every other error fails fast. Use as a context manager, or call
    `close()` explicitly.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 10.0,
        max_retries: int = 3,
    ):
        self.base_url = (base_url or default_memory_url()).rstrip("/")
        self._max_retries = max_retries
        self._http = httpx.AsyncClient(
            base_url=self.base_url, timeout=httpx.Timeout(timeout)
        )

    async def __aenter__(self) -> MemoryClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        await self._http.aclose()

    # -- plumbing --

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        delay = 0.2
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                resp = await self._http.request(method, path, json=json, params=params)
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_exc = e
                if attempt + 1 < self._max_retries:
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                raise MemoryApiError(0, f"cannot reach {self.base_url} ({type(e).__name__}: {e})") from e
            if resp.status_code in _RETRYABLE_STATUS and attempt + 1 < self._max_retries:
                await asyncio.sleep(delay)
                delay *= 2
                continue
            return resp
        raise MemoryApiError(0, f"unreachable: {last_exc}")

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.is_error:
            try:
                error = resp.json().get("error", resp.text)
            except Exception:
                error = resp.text
            raise MemoryApiError(resp.status_code, error)

    # -- prompts --

    async def health(self) -> None:
        resp = await self._request("GET", "/healthz")
        self._raise_for_status(resp)

    async def lookup_or_create_prompt(self, template: str, name: str) -> str:
        resp = await self._request(
            "POST", "/v1/prompts/lookup", json={"template": template, "name": name}
        )
        self._raise_for_status(resp)
        return resp.json()["prompt_id"]

    async def get_prompt(self, prompt_id: str) -> PromptRecord | None:
        resp = await self._request("GET", f"/v1/prompts/{prompt_id}")
        if resp.status_code == 404:
            return None
        self._raise_for_status(resp)
        return PromptRecord.model_validate(resp.json())

    # -- agents --

    async def create_agent(
        self,
        agent_id: str,
        session_id: str,
        agent_idx: int,
        cwd: str,
        prompt_id: str,
        prompt_args: Any,
        system_prompt: str,
        tool_definitions: Any,
        request_params: Any,
        model_identifier: str,
    ) -> None:
        resp = await self._request(
            "POST",
            "/v1/agents",
            json={
                "agent_id": agent_id,
                "session_id": session_id,
                "agent_idx": agent_idx,
                "cwd": cwd,
                "prompt_id": prompt_id,
                "prompt_args": prompt_args,
                "system_prompt": system_prompt,
                "tool_definitions": tool_definitions,
                "request_params": request_params,
                "model_identifier": model_identifier,
            },
        )
        self._raise_for_status(resp)

    async def get_agent(self, agent_id: str) -> AgentRecord | None:
        resp = await self._request("GET", f"/v1/agents/{agent_id}")
        if resp.status_code == 404:
            return None
        self._raise_for_status(resp)
        return AgentRecord.model_validate(resp.json())

    async def list_agents(self, session_id: str | None = None) -> list[AgentRecord]:
        params = {"session_id": session_id} if session_id else None
        resp = await self._request("GET", "/v1/agents", params=params)
        self._raise_for_status(resp)
        return [AgentRecord.model_validate(d) for d in resp.json()]

    async def get_max_agent_idx(self, session_id: str) -> int:
        resp = await self._request(
            "GET", "/v1/max-agent-idx", params={"session_id": session_id}
        )
        self._raise_for_status(resp)
        return resp.json()["max_idx"]

    # -- messages --

    async def add_message(
        self, agent_id: str, message: dict[str, Any], usage: dict[str, Any] | None = None
    ) -> int:
        body: dict[str, Any] = {"agent_id": agent_id, "message": message}
        if usage is not None:
            body["usage"] = usage
        resp = await self._request("POST", "/v1/messages", json=body)
        self._raise_for_status(resp)
        return resp.json()["id"]

    async def load_messages(self, agent_id: str, hydrate: bool = False) -> list[Any]:
        resp = await self._request(
            "GET",
            f"/v1/agents/{agent_id}/messages",
            params={"hydrate": str(hydrate).lower()},
        )
        self._raise_for_status(resp)
        return resp.json()

    async def query_messages_by_agent(
        self,
        agent_id: str,
        order_asc: bool = False,
        limit: int = 20,
        role: str | None = None,
        hydrate: bool = False,
    ) -> list[MessageRecord]:
        params: dict[str, Any] = {
            "order_asc": str(order_asc).lower(),
            "limit": limit,
            "hydrate": str(hydrate).lower(),
        }
        if role is not None:
            params["role"] = role
        resp = await self._request(
            "GET", f"/v1/agents/{agent_id}/messages/query", params=params
        )
        self._raise_for_status(resp)
        return [MessageRecord.model_validate(d) for d in resp.json()]

    async def search_messages(
        self, query: str, limit: int = 20, role: str | None = None
    ) -> list[MessageRecord]:
        body: dict[str, Any] = {"query": query, "limit": limit}
        if role is not None:
            body["role"] = role
        resp = await self._request("POST", "/v1/messages/search", json=body)
        self._raise_for_status(resp)
        return [MessageRecord.model_validate(d) for d in resp.json()]

    # -- sessions --

    async def list_sessions(self, limit: int = 50, offset: int = 0) -> list[SessionInfo]:
        resp = await self._request(
            "GET", "/v1/sessions", params={"limit": limit, "offset": offset}
        )
        self._raise_for_status(resp)
        return [SessionInfo.model_validate(d) for d in resp.json()]

    async def get_sessions_by_cwd(self, cwd: str) -> list[SessionInfo]:
        resp = await self._request("GET", "/v1/sessions/by-cwd", params={"cwd": cwd})
        self._raise_for_status(resp)
        return [SessionInfo.model_validate(d) for d in resp.json()]

    # -- images --

    async def add_image(self, image_id: str, mime: str, data: bytes, w: int, h: int) -> None:
        resp = await self._request(
            "PUT",
            f"/v1/images/{image_id}",
            json={"mime": mime, "data": base64.b64encode(data).decode(), "w": w, "h": h},
        )
        self._raise_for_status(resp)

    async def get_image(self, image_id: str) -> ImageRecord | None:
        resp = await self._request("GET", f"/v1/images/{image_id}")
        if resp.status_code == 404:
            return None
        self._raise_for_status(resp)
        d = resp.json()
        return ImageRecord(
            image_id=d["image_id"],
            mime=d["mime"],
            data=base64.b64decode(d["data"]),
            w=d["w"],
            h=d["h"],
            created_at=d.get("created_at", ""),
        )
