"""
Backboard SDK — async REST client for the Backboard AI API.

Base URL: https://app.backboard.io/api
Auth:     X-API-Key header

Endpoints used:
  POST /assistants
  POST /assistants/{assistant_id}/threads
  POST /threads/{thread_id}/messages
"""

import asyncio
import httpx


BASE_URL = "https://app.backboard.io/api"

# Transient errors worth retrying (DNS blip, connection reset, timeout)
_RETRYABLE = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
)

async def _with_retry(coro_fn, retries: int = 3, delay: float = 1.5):
    last_exc = None
    for attempt in range(retries):
        try:
            return await coro_fn()
        except _RETRYABLE as e:
            last_exc = e
            if attempt < retries - 1:
                await asyncio.sleep(delay * (attempt + 1))
    raise last_exc


class AssistantResponse:
    def __init__(self, data: dict):
        self.assistant_id: str = data["assistant_id"]
        self._data = data


class ThreadResponse:
    def __init__(self, data: dict):
        self.thread_id: str = data["thread_id"]
        self._data = data


class MessageResponse:
    def __init__(self, data: dict):
        self.content: str = data["content"]
        self._data = data


class BackboardClient:
    def __init__(self, api_key: str = ""):
        self._headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json",
        }
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers=self._headers,
            timeout=120.0,
        )

    async def create_assistant(self, name: str, system_prompt: str) -> AssistantResponse:
        async def _call():
            resp = await self._client.post(
                "/assistants",
                json={"name": name, "system_prompt": system_prompt},
            )
            resp.raise_for_status()
            return AssistantResponse(resp.json())
        return await _with_retry(_call)

    async def create_thread(self, assistant_id: str) -> ThreadResponse:
        async def _call():
            resp = await self._client.post(
                f"/assistants/{assistant_id}/threads",
                json={},
            )
            resp.raise_for_status()
            return ThreadResponse(resp.json())
        return await _with_retry(_call)

    async def add_message(
        self,
        thread_id: str,
        content: str,
        llm_provider: str = "openai",
        model_name: str = "gpt-4o-mini",
        stream: bool = False,
    ) -> MessageResponse:
        async def _call():
            resp = await self._client.post(
                f"/threads/{thread_id}/messages",
                json={
                    "content": content,
                    "llm_provider": llm_provider,
                    "model_name": model_name,
                    "stream": stream,
                },
            )
            resp.raise_for_status()
            return MessageResponse(resp.json())
        return await _with_retry(_call)

    async def aclose(self):
        await self._client.aclose()
