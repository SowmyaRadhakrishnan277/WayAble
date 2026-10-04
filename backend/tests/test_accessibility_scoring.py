import pytest

from app.models import UserType
from app.service import RouteService, assess_features, build_option


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
        [{"type": "node", "id": 13, "lat": 53.34, "lon": -6.25, "tags": {"highway": "crossing", "tactile_paving": "yes"}}],
        UserType.LOW_VISION,
    )
    assert evidence[0].category == "tactile_paving"
    assert evidence[0].severity == "positive"


def test_accessible_amenity_near_route_is_not_route_access_evidence():
    evidence = assess_features(
        [
            {
                "type": "node",
                "id": 14,
                "lat": 53.34,
                "lon": -6.25,
                "tags": {"amenity": "cafe", "wheelchair": "yes", "foot": "yes"},
            }
        ],
        UserType.WHEELCHAIR,
    )
    assert evidence == []


def test_amenity_without_pedestrian_path_tag_cannot_make_route_avoid():
    evidence = assess_features(
        [
            {
                "type": "node",
                "id": 15,
                "lat": 53.34,
                "lon": -6.25,
                "tags": {"amenity": "bicycle_rental", "wheelchair": "no", "foot": "yes"},
            }
        ],
        UserType.WHEELCHAIR,
    )
    assert evidence == []


@pytest.mark.asyncio
async def test_unavailable_access_feed_keeps_route_cautious_and_unknown():
    class Provider:
        async def routes(self, _origin, _destination):
            return [{"distance": 300, "duration": 240, "geometry": {"coordinates": [[-6.25, 53.34], [-6.251, 53.341]]}}]

        async def accessibility_features(self, _coordinates):
            return [], False

    routes, available = await RouteService(Provider()).plan({}, {}, UserType.WHEELCHAIR)
    assert not available
    assert routes[0].status == "caution"
    assert routes[0].confidence_score < 45
    assert routes[0].accessibility_evidence[0].severity == "unknown"
    assert "unavailable" in routes[0].evidence_summary
