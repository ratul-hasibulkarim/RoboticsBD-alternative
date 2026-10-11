"""Minimal Typesense HTTP client on the shared ApiClient (timeouts, retries, circuit breaker)."""

from __future__ import annotations

import json
from typing import Any

from common.http import ApiClient


class TypesenseClient:
    def __init__(self, base_url: str, api_key: str, *, api: ApiClient | None = None) -> None:
        self.api = api or ApiClient(base_url, headers={"X-TYPESENSE-API-KEY": api_key}, max_retries=1)

    async def aclose(self) -> None:
        await self.api.aclose()

    async def ensure_collection(self, schema: dict[str, Any]) -> bool:
        resp = await self.api.request("GET", f"/collections/{schema['name']}")
        if resp.status_code == 200:
            return False
        resp = await self.api.request("POST", "/collections", json=schema)
        resp.raise_for_status()
        return True

    async def upsert_synonyms(self, collection: str, synonyms: dict[str, list[str]]) -> None:
        for root, syns in synonyms.items():
            sid = root.replace(" ", "-")
            resp = await self.api.request(
                "PUT", f"/collections/{collection}/synonyms/{sid}", json={"synonyms": [root, *syns]}
            )
            resp.raise_for_status()

    async def import_documents(self, collection: str, docs: list[dict[str, Any]]) -> int:
        if not docs:
            return 0
        body = "\n".join(json.dumps(d) for d in docs)
        resp = await self.api.request(
            "POST",
            f"/collections/{collection}/documents/import",
            params={"action": "upsert"},
            content=body.encode(),
            headers={"Content-Type": "text/plain"},
        )
        resp.raise_for_status()
        results = [json.loads(line) for line in resp.text.splitlines() if line.strip()]
        failed = [r for r in results if not r.get("success")]
        if failed:
            raise RuntimeError(f"typesense import failed for {len(failed)} docs: {failed[:3]}")
        return len(results)

    async def delete_document(self, collection: str, doc_id: str) -> None:
        resp = await self.api.request("DELETE", f"/collections/{collection}/documents/{doc_id}")
        if resp.status_code not in (200, 404):
            resp.raise_for_status()

    async def multi_search(self, searches: list[dict[str, Any]], common: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = await self.api.request(
            "POST", "/multi_search", params=common or {}, json={"searches": searches}
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data
