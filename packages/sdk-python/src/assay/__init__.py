"""Assay Python SDK.

Two modes, one API shape:

**Embedded** — no server, no network. Reads PromptFiles straight off disk::

    from assay import Client

    assay = Client.local("./prompts")
    print(assay.run("support/refund-triage", {"message": "I want a refund"}).text)

**Remote** — talks to a ``/v1`` server::

    assay = Client("https://prompts.acme.internal", api_key="…")
    print(assay.run("support/refund-triage", {"message": "…"}).text)

Application code written against one mode runs unchanged against the other, which
means a prototype reading local files becomes a production deployment by changing a
single constructor call.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncIterator

__version__ = "1.0.0"
__all__ = ["Client", "RunResponse", "PromptRef", "MPLClientError"]


class MPLClientError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, detail: Any = None) -> None:
        super().__init__(message)
        self.status, self.detail = status, detail


@dataclass
class RunResponse:
    text: str
    model: str = ""
    provider: str = ""
    cost_usd: float = 0.0
    latency_ms: int = 0
    usage: dict[str, int] | None = None
    raw: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.text


@dataclass
class PromptRef:
    id: str
    name: str
    version: int
    status: str = "draft"
    tags: list[str] | None = None
    model: str | None = None
    variables: list[str] | None = None


class Client:
    """Talks to a ``/v1`` server, or to the local filesystem in embedded mode."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8001",
        *,
        api_key: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._local = None

    # -- constructors ------------------------------------------------------

    @classmethod
    def local(cls, workspace: str = ".") -> "Client":
        """Embedded mode. Requires ``assay-core``; makes no network calls."""
        from assay_core import Runtime, Workspace

        client = cls.__new__(cls)
        client.base_url = ""
        client.api_key = None
        client.timeout = 0.0
        ws = Workspace.find(workspace)
        client._local = (ws.store(), Runtime(workspace=ws))
        return client

    # -- transport ---------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs) -> Any:
        import httpx

        headers = {"X-Assay-Api-Version": "1"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            with httpx.Client(timeout=self.timeout) as http:
                response = http.request(method, f"{self.base_url}/v1{path}",
                                        headers=headers, **kwargs)
        except Exception as exc:
            raise MPLClientError(f"request failed: {exc}") from exc
        if response.status_code >= 400:
            detail = _safe_json(response)
            raise MPLClientError(
                f"{method} {path} → HTTP {response.status_code}",
                status=response.status_code, detail=detail,
            )
        return None if response.status_code == 204 else response.json()

    # -- API ---------------------------------------------------------------

    def list(self, *, prefix: str | None = None, tag: list[str] | None = None,
             status: str | None = None) -> list[PromptRef]:
        if self._local:
            store, _ = self._local
            refs = []
            for prompt_id in store.list(prefix=prefix):
                pf = store.get(prompt_id)
                if tag and not set(tag) & set(pf.tags):
                    continue
                if status and pf.status != status:
                    continue
                refs.append(PromptRef(pf.id, pf.name, pf.version, pf.status,
                                      pf.tags, pf.model_ref,
                                      sorted(pf.template_variables())))
            return refs
        params: dict[str, Any] = {}
        if prefix:
            params["prefix"] = prefix
        if tag:
            params["tag"] = tag
        if status:
            params["status"] = status
        return [PromptRef(**{k: v for k, v in item.items() if k in PromptRef.__annotations__})
                for item in self._request("GET", "/prompts", params=params)]

    def get(self, prompt_id: str, *, version: int | None = None) -> dict:
        if self._local:
            store, _ = self._local
            return store.get(prompt_id, version=version).to_dict()
        params = {"version": version} if version else {}
        return self._request("GET", f"/prompts/{prompt_id}", params=params)

    def render(self, prompt_id: str, variables: dict[str, Any] | None = None,
               *, model: str | None = None) -> dict:
        if self._local:
            store, runtime = self._local
            rendered = runtime.render(store.get(prompt_id), variables or {}, model=model)
            return {"model": rendered.model,
                    "messages": [m.to_dict() for m in rendered.messages]}
        return self._request("POST", f"/prompts/{prompt_id}/render",
                             json={"variables": variables or {}, "model": model})

    def run(self, prompt_id: str, variables: dict[str, Any] | None = None,
            *, model: str | None = None, params: dict[str, Any] | None = None) -> RunResponse:
        if self._local:
            store, runtime = self._local
            result = runtime.run(store.get(prompt_id), variables or {},
                                 model=model, params=params)
            return RunResponse(
                text=result.text, model=result.completion.model,
                provider=result.completion.provider, cost_usd=result.cost_usd,
                latency_ms=result.completion.latency_ms,
                usage=result.to_dict()["usage"], raw=result.to_dict(),
            )
        payload = self._request("POST", f"/prompts/{prompt_id}/run", json={
            "variables": variables or {}, "model": model, "params": params or {},
        })
        return RunResponse(
            text=payload.get("output", ""), model=payload.get("model", ""),
            provider=payload.get("provider", ""), cost_usd=payload.get("cost_usd", 0.0),
            latency_ms=payload.get("latency_ms", 0), usage=payload.get("usage"), raw=payload,
        )

    async def stream(
        self,
        prompt_id: str,
        variables: dict[str, Any] | None = None,
        *,
        model: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict]:
        """Yield text/tool-call deltas and one completed event with run evidence."""
        if self._local:
            store, runtime = self._local
            async for event in runtime.astream(
                store.get(prompt_id), variables or {}, model=model, params=params
            ):
                yield event.to_dict()
            return

        import json
        import httpx

        headers = {"X-Assay-Api-Version": "1", "Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as http:
                async with http.stream(
                    "POST",
                    f"{self.base_url}/v1/prompts/{prompt_id}/stream",
                    headers=headers,
                    json={"variables": variables or {}, "model": model, "params": params or {}},
                ) as response:
                    if response.status_code >= 400:
                        detail = (await response.aread()).decode("utf-8", errors="replace")[:500]
                        raise MPLClientError(
                            f"POST /prompts/{prompt_id}/stream → HTTP {response.status_code}",
                            status=response.status_code,
                            detail=detail,
                        )
                    async for raw_line in response.aiter_lines():
                        line = raw_line.strip()
                        if not line.startswith("data:"):
                            continue
                        data = line.removeprefix("data:").strip()
                        if data == "[DONE]":
                            return
                        event = json.loads(data)
                        if event.get("type") == "error":
                            raise MPLClientError(
                                "stream failed", detail=event.get("error")
                            )
                        yield event
        except MPLClientError:
            raise
        except Exception as exc:
            raise MPLClientError(f"stream request failed: {exc}") from exc

    def evaluate(
        self,
        prompt_id: str,
        *,
        model: str | None = None,
        max_workers: int = 1,
    ) -> dict:
        if (
            isinstance(max_workers, bool)
            or not isinstance(max_workers, int)
            or not 1 <= max_workers <= 32
        ):
            raise ValueError("max_workers must be between 1 and 32")
        if self._local:
            store, runtime = self._local
            prompt = store.get(prompt_id)
            if max_workers > 1:
                return asyncio.run(runtime.aevaluate(
                    prompt, model=model, max_concurrency=max_workers
                ))
            return runtime.evaluate(prompt, model=model)
        return self._request("POST", f"/prompts/{prompt_id}/evaluate",
                             params={"model": model, "max_workers": max_workers})

    def create(self, prompt_id: str, body: str, **fields) -> PromptRef:
        if self._local:
            from assay_core import PromptFile

            store, _ = self._local
            data = {"promptfile":  1, "id": prompt_id, "version": 1,
                    "name": fields.get("name") or prompt_id.rsplit("/", 1)[-1], **fields}
            pf = PromptFile(data=data, body=body)
            store.put(pf, message=fields.get("commit_message"))
            return PromptRef(pf.id, pf.name, pf.version, pf.status, pf.tags, pf.model_ref)
        payload = self._request("POST", "/prompts", json={"id": prompt_id, "body": body, **fields})
        return PromptRef(**{k: v for k, v in payload.items() if k in PromptRef.__annotations__})

    def models(self, *, provider: str | None = None) -> list[dict]:
        if self._local:
            from assay_core import ModelCatalog

            entries = ModelCatalog.default()
            models = entries.by_provider(provider) if provider else entries.all()
            return [{"ref": f"{m.provider}/{m.id}", "name": m.display_name,
                     "context_window": m.context_window} for m in models]
        return self._request("GET", "/models",
                             params={"provider": provider} if provider else {})["models"]

    def health(self) -> dict:
        if self._local:
            return {"status": "ok", "mode": "embedded"}
        return self._request("GET", "/health")


def _safe_json(response) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text[:500]
