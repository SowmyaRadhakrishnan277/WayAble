from app.models import UserType
from app.service import assess_features, build_option


def test_steps_create_an_avoid_route_for_wheelchair_users():
    evidence = assess_features(
        [{"type": "node", "id": 12, "lat": 53.34, "lon": -6.25, "tags": {"highway": "steps"}}],
        UserType.WHEELCHAIR,
    )
    route = build_option(
        0,
        {"distance": 200, "duration": 180, "geometry": {"coordinates": [[-6.25, 53.34], [-6.251, 53.341]]}},
        evidence,
        UserType.WHEELCHAIR,
    )
    assert route.status == "avoid"
    assert route.confidence_score < 45


def test_tactile_paving_is_profile_specific_positive_evidence():
    evidence = assess_features(
        [{"type": "node", "id": 13, "lat": 53.34, "lon": -6.25, "tags": {"tactile_paving": "yes"}}],
        UserType.LOW_VISION,
    )
    assert evidence[0].category == "tactile_paving"
    assert evidence[0].severity == "positive"
