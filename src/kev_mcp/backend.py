"""Official TypeSafe SDK connection to a strict local Kev runtime."""

import asyncio
from typing import Any
from urllib.parse import urlsplit

import httpx
import httpx2
from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy, TypeSafeAPIError, TypeSafeError

from kev_mcp.schemas import validate_questions

CONTRACT = "kev-mcp-runtime-v1"


class Backend:
    def __init__(self, base_url: str, model: str, timeout: float = 120, api_key: str = "local"):
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "KEV_BASE_URL must be an HTTP(S) endpoint without credentials or query"
            )
        self.base_url = base_url.rstrip("/")
        self.model, self.timeout, self.api_key = model, timeout, api_key

    async def capabilities(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                response = await client.get(
                    f"{self.base_url}/kev/capabilities",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                response.raise_for_status()
                result = response.json()
        except (httpx.HTTPError, ValueError):
            raise ValueError(
                "Kev backend unavailable or missing strict runtime capabilities"
            ) from None
        if (
            not isinstance(result, dict)
            or result.get("contract") != CONTRACT
            or result.get("strict_input") is not True
            or not result.get("available")
        ):
            raise ValueError("Kev backend does not implement the required strict runtime contract")
        return result

    async def evaluate(self, state: str, questions: dict) -> dict[str, Any]:
        validated = validate_questions(questions)
        try:
            async with asyncio.timeout(self.timeout):
                await self.capabilities()
                async with AsyncTypeSafeClient(
                    base_url=self.base_url,
                    api_key=self.api_key,
                    model=self.model,
                    timeout=self.timeout,
                    retry=RetryPolicy(max_retries=0),
                    http_client=httpx2.AsyncClient(timeout=self.timeout, trust_env=False),
                ) as client:
                    response = await client.system_one(state=state, questions=validated)
                result = response.model_dump(mode="json")
                raw = response.raw_http_response.json()
                if not isinstance(raw.get("token_accounting"), dict) or not isinstance(
                    raw.get("runtime"), dict
                ):
                    raise ValueError("Kev response is missing input coverage or model identity")
                if raw["token_accounting"].get("state_truncated", False):
                    raise ValueError("Kev reported truncated state; refusing incomplete coverage")
                if set(result["answers"]) != set(validated):
                    raise ValueError("Kev response does not answer every submitted question")
                return result | {
                    key: raw[key]
                    for key in ("token_accounting", "runtime", "latency_ms", "memory")
                    if key in raw
                }
        except TimeoutError:
            raise ValueError(
                "Kev request timed out; execution may still be running; no automatic retry was made"
            ) from None
        except TypeSafeAPIError as exc:
            detail = exc.body.get("detail") if isinstance(exc.body, dict) else None
            if exc.status in {413, 422, 503} and isinstance(detail, str):
                raise ValueError(f"Kev HTTP {exc.status}: {detail}") from None
            raise ValueError(
                f"Kev HTTP {exc.status}; request failed without automatic retry"
            ) from None
        except TypeSafeError:
            raise ValueError(
                "Kev connection or response failed; execution status unknown; no automatic retry"
            ) from None
