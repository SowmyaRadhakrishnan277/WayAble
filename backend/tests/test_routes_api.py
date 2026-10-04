import pytest
from fastapi.testclient import TestClient

from app.main import create_app


class FakeMapProvider:
    async def geocode(self, query):
        locations = {
            "Dogpatch Labs, Dublin": {"label": "Dogpatch Labs, Dublin", "latitude": 53.347, "longitude": -6.239},
            "Trinity College Dublin": {"label": "Trinity College Dublin", "latitude": 53.3438, "longitude": -6.2546},
        }
        return locations[query]

    async def routes(self, origin, destination):
        return [
            {
                "distance": 1200.2,
                "duration": 930.7,
                "geometry": {"coordinates": [[-6.239, 53.347], [-6.246, 53.345], [-6.2546, 53.3438]]},
            },
            {
                "distance": 1340.3,
                "duration": 1010.1,
                "geometry": {"coordinates": [[-6.239, 53.347], [-6.248, 53.349], [-6.2546, 53.3438]]},
            },
        ]

    async def accessibility_features(self, coordinates):
        if coordinates[1][1] == 53.345:
            return ([{"type": "node", "id": 1, "lat": 53.345, "lon": -6.246, "tags": {"wheelchair": "yes", "kerb": "lowered"}}], True)
        return ([{"type": "node", "id": 2, "lat": 53.349, "lon": -6.248, "tags": {"highway": "steps"}}], True)

    def data_sources(self, accessibility_data_available):
        return []


@pytest.fixture
def client():
    return TestClient(create_app(FakeMapProvider()))


def test_returns_two_ranked_routes_with_geojson(client):
    response = client.post(
        "/api/v1/routes",
        json={
            "from_location": "Dogpatch Labs, Dublin",
            "to_location": "Trinity College Dublin",
            "user_type": "wheelchair",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["routes"]) == 2
    assert payload["routes"][0]["status"] == "recommended"
    assert payload["routes"][0]["confidence_score"] > payload["routes"][1]["confidence_score"]
    assert payload["routes"][0]["geometry"]["type"] == "LineString"
    assert payload["routes"][0]["legs"][0]["instructions"][0]["instruction"]
    assert payload["routes"][1]["status"] == "avoid"
    assert payload["provider_status"]["public_transport"] == "not_configured"


def test_rejects_invalid_user_type(client):
    response = client.post(
        "/api/v1/routes",
        json={"from_location": "Dogpatch Labs, Dublin", "to_location": "Trinity College Dublin", "user_type": "pram"},
    )
    assert response.status_code == 422
