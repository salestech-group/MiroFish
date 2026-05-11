"""Ollama-backed cross-encoder reranker for Graphiti search.

Replaces the no-op ``_PassthroughReranker`` injected into Graphiti by default
with a real reranker that scores passages against a query through an Ollama
chat model exposed over its OpenAI-compatible ``/v1`` surface.

The class implements only ``CrossEncoderClient.rank`` (the sole abstract
member Graphiti requires) and is constructed by ``graphiti_adapter._get_graphiti``
when ``Config.RERANKER_PROVIDER == "ollama"``. It does not perform any
network I/O at construction time so the Flask app can boot even when the
Ollama daemon is unreachable; failures are handled inside ``rank`` and never
propagate, so graph search remains functional under degradation.
"""

import asyncio
import json
import re
from typing import List, Tuple

from openai import AsyncOpenAI
from graphiti_core.cross_encoder.client import CrossEncoderClient

from ..utils.logger import get_logger

logger = get_logger('mirofish.ollama_reranker')


_THINK_BLOCK = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)
_CODE_FENCE_START = re.compile(r"^```(?:json)?\s*\n?", re.IGNORECASE)
_CODE_FENCE_END = re.compile(r"\n?```\s*$")
_FIRST_FLOAT = re.compile(r"-?\d+(?:\.\d+)?")

_SYSTEM_PROMPT = (
    "You are a relevance grader. Given a user query and a single passage, "
    "rate how relevant the passage is to the query on a continuous scale "
    "from 0.0 (not relevant at all) to 1.0 (perfectly relevant). "
    "Respond with a single JSON object of the form {\"score\": <float>} "
    "and nothing else."
)


def _clip_unit(value: float) -> float:
    """Clamp ``value`` into the closed interval [0.0, 1.0]."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _parse_score(raw: str) -> float:
    """Parse a model response into a relevance score in [0.0, 1.0].

    Strips reasoning ``<think>`` blocks and markdown fences (the same
    defensive pattern used in ``utils/llm_client.py``), then attempts
    ``json.loads`` and reads ``score``. Falls back to extracting the first
    floating-point number from the cleaned text. Raises ``ValueError`` when
    no numeric value can be recovered.
    """
    text = _THINK_BLOCK.sub("", raw or "").strip()
    text = _CODE_FENCE_START.sub("", text)
    text = _CODE_FENCE_END.sub("", text).strip()

    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        parsed = None

    if isinstance(parsed, dict) and "score" in parsed:
        try:
            return _clip_unit(float(parsed["score"]))
        except (TypeError, ValueError):
            pass

    match = _FIRST_FLOAT.search(text)
    if match is not None:
        try:
            return _clip_unit(float(match.group(0)))
        except ValueError:
            pass

    raise ValueError(f"no numeric score in model response: {text!r}")


class OllamaReranker(CrossEncoderClient):
    """Cross-encoder reranker that scores passages via an Ollama chat model.

    Subclass of :class:`graphiti_core.cross_encoder.client.CrossEncoderClient`
    that implements ``rank`` by issuing one chat-completion request per
    passage through ``openai.AsyncOpenAI`` (which speaks the OpenAI-compatible
    surface exposed by Ollama on ``/v1``).

    Construction is side-effect-free: building the underlying ``AsyncOpenAI``
    client does not perform any network I/O, so ``_get_graphiti`` can wire
    this class up at startup even when the Ollama daemon is unavailable.
    Failures surface only at ``rank`` call time and are degraded to a
    passthrough-style result with a single ``WARNING`` log per failed call.
    """

    def __init__(self, *, model: str, base_url: str, api_key: str) -> None:
        """Configure the reranker.

        Args:
            model: Name of the Ollama chat model used to score passages
                (for example ``qwen2.5:3b``). The operator is expected to
                have run ``ollama pull <model>`` before reranking is exercised.
            base_url: OpenAI-compatible endpoint for the Ollama server, for
                example ``http://localhost:11434/v1``.
            api_key: API key forwarded to the OpenAI client. Ollama ignores
                the value but the SDK requires a non-empty string.
        """
        self._model = model
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)

    async def _score_passage(self, query: str, passage: str, index: int) -> float:
        """Score a single passage; deterministic low fallback on parse failure."""
        user_prompt = (
            f"Query:\n{query}\n\n"
            f"Passage:\n{passage}\n\n"
            "Reply with only the JSON object described in the system prompt."
        )
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=32,
        )
        raw = response.choices[0].message.content or ""
        try:
            return _parse_score(raw)
        except ValueError as exc:
            logger.debug(
                "Reranker parse failure (model=%s, passage_index=%d): %s",
                self._model, index, exc,
            )
            return -0.001 * (index + 1)

    async def rank(
        self,
        query: str,
        passages: List[str],
    ) -> List[Tuple[str, float]]:
        """Return ``(passage, score)`` tuples sorted by score descending.

        Empty ``passages`` returns ``[]`` without any model call. On a
        whole-call failure (connection refused, model 404, timeout, etc.)
        the method logs a single ``WARNING`` and returns the passages in
        their original order with synthetic descending scores so graph
        search keeps functioning. The method does not raise.
        """
        if not passages:
            return []

        try:
            scores = await asyncio.gather(
                *(self._score_passage(query, p, i) for i, p in enumerate(passages))
            )
        except Exception as exc:  # noqa: BLE001 — graceful degrade per design R5
            logger.warning(
                "Ollama reranker failed (model=%s, error=%s); falling back to passthrough order.",
                self._model, type(exc).__name__,
            )
            return [(p, 1.0 - 0.01 * i) for i, p in enumerate(passages)]

        scored = list(zip(passages, scores))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored
