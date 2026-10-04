"""Privacy-minimized LLM review that augments, but never replaces, safety rules."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from .cache import AsyncTTLCache
from .models import AIReview, DataSource, RouteOption, SourceState, UserType


@dataclass(frozen=True)
class AIReviewSettings:
    enabled: bool = os.getenv("WAYABLE_AI_ENABLED", "false").lower() == "true"
    api_key: str | None = os.getenv("OPENAI_API_KEY")
    base_url: str | None = os.getenv("OPENAI_BASE_URL")
    model: str = os.getenv("WAYABLE_AI_MODEL", "gpt-4o-mini")


class AIRouteReviewer:
    def __init__(self, settings: AIReviewSettings | None = None, cache: AsyncTTLCache | None = None) -> None:
        self.settings = settings or AIReviewSettings()
        self._cache = cache or AsyncTTLCache(max_entries=128)

    @property
    def configured(self) -> bool:
        # Netlify AI Gateway provides OPENAI_BASE_URL and handles provider credentials.
        return self.settings.enabled and bool(self.settings.api_key or self.settings.base_url)

    async def review_routes(self, routes: list[RouteOption], user_type: UserType) -> tuple[list[RouteOption], SourceState]:
        if not self.configured:
            for route in routes:
                route.ai_review = AIReview(
                    state=SourceState.NOT_CONFIGURED,
                    confidence_adjustment=0,
                    explanation="AI review is not configured; the displayed confidence uses verified rule-based evidence.",
                )
                route.rule_based_confidence_score = route.rule_based_confidence_score or route.confidence_score
            return routes, SourceState.NOT_CONFIGURED

        reviewed: list[RouteOption] = []
        failed = False
        for route in routes:
            try:
                review = await self._review_route(route, user_type)
                _apply_review(route, review)
            except Exception:
                failed = True
                route.ai_review = AIReview(
                    state=SourceState.UNAVAILABLE,
                    model=self.settings.model,
                    confidence_adjustment=0,
                    explanation="AI review was unavailable; the displayed confidence uses verified rule-based evidence.",
                )
                route.rule_based_confidence_score = route.rule_based_confidence_score or route.confidence_score
            reviewed.append(route)
        return reviewed, SourceState.UNAVAILABLE if failed else SourceState.LIVE

    async def _review_route(self, route: RouteOption, user_type: UserType) -> AIReview:
        payload = _review_payload(route, user_type)
        key = "ai:" + json.dumps(payload, sort_keys=True, separators=(",", ":"))

        async def load() -> AIReview:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=self.settings.api_key or "netlify-ai-gateway",
                base_url=self.settings.base_url,
            )
            try:
                completion = await client.chat.completions.create(
                    model=self.settings.model,
                    temperature=0,
                    response_format={"type": "json_object"},
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are WayAble's accessibility evidence reviewer. Never claim that a route is safe. "
                                "Use only the supplied facts. Return JSON with confidence_adjustment as an integer from -10 to 10, "
                                "explanation under 180 characters, and risk_flags as a list of short strings. "
                                "Missing evidence must lower confidence or be called unknown. Known blockers must never receive a positive adjustment."
                            ),
                        },
                        {"role": "user", "content": json.dumps(payload)},
                    ],
                )
            finally:
                await client.close()
            content = completion.choices[0].message.content or "{}"
            return _parse_review(content, self.settings.model)

        return await self._cache.get_or_load(key, 300, load)

    def data_source(self, state: SourceState) -> DataSource:
        return DataSource(
            id="ai-route-review",
            name="WayAble AI route review",
            state=state,
            purpose="Privacy-minimized explanation and bounded confidence adjustment from structured accessibility evidence.",
            source_url="https://platform.openai.com/docs/overview",
        )


def _review_payload(route: RouteOption, user_type: UserType) -> dict[str, Any]:
    # Deliberately exclude searched place names, coordinates, raw tags, and user identifiers.
    return {
        "access_profile": user_type.value,
        "rule_based_confidence": route.rule_based_confidence_score or route.confidence_score,
        "route_status": route.status,
        "duration_minutes": round(route.duration_seconds / 60),
        "evidence": [
            {"category": item.category, "severity": item.severity, "message": item.message}
            for item in route.accessibility_evidence
        ],
    }


def _parse_review(content: str, model: str) -> AIReview:
    parsed = json.loads(content)
    adjustment = parsed.get("confidence_adjustment", 0)
    if not isinstance(adjustment, int):
        adjustment = 0
    explanation = parsed.get("explanation", "AI reviewed the available route evidence.")
    flags = parsed.get("risk_flags", [])
    if not isinstance(explanation, str):
        explanation = "AI reviewed the available route evidence."
    if not isinstance(flags, list):
        flags = []
    return AIReview(
        state=SourceState.LIVE,
        model=model,
        confidence_adjustment=max(-10, min(10, adjustment)),
        explanation=explanation[:180],
        risk_flags=[str(flag)[:80] for flag in flags[:5]],
    )


def _apply_review(route: RouteOption, review: AIReview) -> None:
    baseline = route.rule_based_confidence_score or route.confidence_score
    blocker_count = sum(item.severity == "blocker" for item in route.accessibility_evidence)
    route.rule_based_confidence_score = baseline
    route.confidence_score = max(5, min(100, baseline + review.confidence_adjustment))
    if blocker_count:
        route.confidence_score = min(route.confidence_score, 35)
    route.ai_review = review
