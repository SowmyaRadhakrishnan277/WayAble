from app.ai_reviewer import _apply_review, _parse_review
from app.models import AIReview, RouteOption, SourceState


def route_with_blocker() -> RouteOption:
    return RouteOption(
        id="test-route",
        label="Route with a recorded access barrier",
        status="avoid",
        confidence_score=28,
        rule_based_confidence_score=28,
        distance_meters=500,
        duration_seconds=600,
        geometry={"type": "LineString", "coordinates": [[-6.25, 53.34], [-6.251, 53.341]]},
        legs=[],
        accessibility_evidence=[
            {
                "category": "steps",
                "severity": "blocker",
                "message": "Steps are mapped on or near this route.",
            }
        ],
        evidence_summary="Not recommended due to recorded steps.",
    )


def test_review_parser_bounds_adjustment_and_flags():
    review = _parse_review(
        '{"confidence_adjustment": 99, "explanation": "Check crossing details.", "risk_flags": ["Unknown crossing"]}',
        "test-model",
    )
    assert review.confidence_adjustment == 10
    assert review.explanation == "Check crossing details."
    assert review.risk_flags == ["Unknown crossing"]


def test_ai_review_cannot_raise_blocked_route_confidence_above_35():
    route = route_with_blocker()
    review = AIReview(
        state=SourceState.LIVE,
        model="test-model",
        confidence_adjustment=10,
        explanation="This is advisory only.",
        risk_flags=[],
    )
    _apply_review(route, review)
    assert route.status == "avoid"
    assert route.confidence_score <= 35
    assert route.rule_based_confidence_score == 28
