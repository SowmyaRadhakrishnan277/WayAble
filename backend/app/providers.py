"""Small, replaceable adapters for map providers used by the routing service."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from dataclasses import dataclass
from hashlib import sha256
from json import dumps
from typing import Any

import httpx

from .cache import AsyncTTLCache
from .models import DataSource, SourceState


class ProviderError(Exception):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class LocationNotFoundError(ProviderError):
    def __init__(self, location: str) -> None:
        super().__init__(f"No Irish location was found for '{location}'.", status_code=404)


@dataclass(frozen=True)
class ProviderSettings:
    nominatim_base_url: str = os.getenv("NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org")
    osrm_base_url: str = os.getenv("OSRM_BASE_URL", "https://routing.openstreetmap.de/routed-foot")
    osrm_route_profile: str = os.getenv("OSRM_ROUTE_PROFILE", "driving")
    overpass_base_url: str = os.getenv("OVERPASS_BASE_URL", "https://overpass-api.de/api/interpreter")
    user_agent: str = os.getenv("WAYABLE_USER_AGENT", "WayAble/0.1 (local-development)")
    nta_api_key: str | None = os.getenv("NTA_API_KEY")
    nta_gtfs_url: str | None = os.getenv("NTA_GTFS_STATIC_URL")
    nta_gtfs_realtime_url: str | None = os.getenv("NTA_GTFS_REALTIME_URL")
    irish_rail_lift_url: str | None = os.getenv("IRISH_RAIL_LIFT_STATUS_URL")


class OpenStreetMapProvider:
    """Geocodes, routes and reads tagged accessibility evidence from OSM services."""

    def __init__(
        self,
        settings: ProviderSettings | None = None,
        client: httpx.AsyncClient | None = None,
        cache: AsyncTTLCache | None = None,
    ) -> None:
        self.settings = settings or ProviderSettings()
        self._client = client
        self._cache = cache or AsyncTTLCache()

    def set_client(self, client: httpx.AsyncClient | None) -> None:
        self._client = client

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        headers = {"User-Agent": self.settings.user_agent, **kwargs.pop("headers", {})}
        try:
            if self._client:
                response = await self._client.request(method, url, headers=headers, timeout=20, **kwargs)
            else:
                async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
                    response = await client.request(method, url, timeout=20, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as error:
            raise ProviderError(f"Map provider returned HTTP {error.response.status_code}.") from error
        except httpx.HTTPError as error:
            raise ProviderError("Map provider could not be reached.") from error

    async def geocode(self, query: str) -> dict[str, Any]:
        normalized = " ".join(query.casefold().split())

        async def load() -> dict[str, Any]:
            response = await self._request(
                "GET",
                f"{self.settings.nominatim_base_url}/search",
                params={"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "ie", "addressdetails": 1},
            )
            places = response.json()
            if not places:
                raise LocationNotFoundError(query)
            place = places[0]
            return {"label": place["display_name"], "latitude": float(place["lat"]), "longitude": float(place["lon"])}

        return await self._cache.get_or_load(f"geocode:{normalized}", 86_400, load)

    async def routes(self, origin: dict[str, Any], destination: dict[str, Any]) -> list[dict[str, Any]]:
        coordinates = f"{origin['longitude']},{origin['latitude']};{destination['longitude']},{destination['latitude']}"

        async def load() -> list[dict[str, Any]]:
            response = await self._request(
                "GET",
                f"{self.settings.osrm_base_url}/route/v1/{self.settings.osrm_route_profile}/{coordinates}",
                params={"alternatives": "true", "overview": "full", "geometries": "geojson", "steps": "true"},
            )
            payload = response.json()
            if payload.get("code") != "Ok" or not payload.get("routes"):
                raise ProviderError("No walking route could be found between those locations.", status_code=404)
            return payload["routes"][:2]

        return await self._cache.get_or_load(f"route:{coordinates}", 600, load)

    async def accessibility_features(self, coordinates: list[list[float]]) -> tuple[list[dict[str, Any]], bool]:
        # Sampling keeps the query modest while still checking evidence along the route.
        samples = _sample_coordinates(coordinates, limit=12)
        nodes = "\n".join(
            f"node(around:18,{latitude},{longitude})[~\"^(wheelchair|kerb|tactile_paving|barrier|surface|smoothness|highway)$\"~\".+\"];"
            for longitude, latitude in samples
        )
        ways = "\n".join(
            f"way(around:18,{latitude},{longitude})[~\"^(wheelchair|kerb|tactile_paving|barrier|surface|smoothness|highway)$\"~\".+\"];"
            for longitude, latitude in samples
        )
        query = f"[out:json][timeout:20];(\n{nodes}\n{ways}\n);out center tags;"
        key = f"access:{sha256(dumps(samples, separators=(',', ':')).encode()).hexdigest()}"

        async def load() -> tuple[list[dict[str, Any]], bool]:
            try:
                response = await self._request("POST", self.settings.overpass_base_url, data={"data": query})
                return response.json().get("elements", []), True
            except ProviderError:
                # A route remains useful even when community-sourced evidence cannot be fetched.
                return [], False

        return await self._cache.get_or_load(key, 900, load)

    def data_sources(self, accessibility_data_available: bool) -> list[DataSource]:
        now = datetime.now(timezone.utc)
        transit_ready = bool(self.settings.nta_api_key and self.settings.nta_gtfs_url)
        realtime_ready = transit_ready and bool(self.settings.nta_gtfs_realtime_url)
        rail_ready = bool(self.settings.irish_rail_lift_url)
        return [
            DataSource(
                id="osm",
                name="OpenStreetMap",
                state=SourceState.LIVE,
                purpose="Street network, crossings, kerbs, barriers, surfaces and tactile-paving evidence.",
                source_url="https://www.openstreetmap.org/copyright",
                updated_at=now,
            ),
            DataSource(
                id="nominatim",
                name="Nominatim",
                state=SourceState.LIVE,
                purpose="Place search and geocoding.",
                source_url="https://operations.osmfoundation.org/policies/nominatim/",
                updated_at=now,
            ),
            DataSource(
                id="osrm-foot",
                name="OpenStreetMap pedestrian routing",
                state=SourceState.LIVE,
                purpose="Walking route geometry and turn-by-turn route steps.",
                source_url="https://routing.openstreetmap.de/",
                updated_at=now,
            ),
            DataSource(
                id="overpass",
                name="Overpass API",
                state=SourceState.LIVE if accessibility_data_available else SourceState.UNAVAILABLE,
                purpose="Targeted accessibility-tag lookup along each route corridor.",
                source_url="https://overpass-api.de/",
                updated_at=now if accessibility_data_available else None,
            ),
            DataSource(
                id="nta-gtfs",
                name="NTA GTFS",
                state=SourceState.NOT_CONFIGURED if not transit_ready else SourceState.LIVE,
                purpose="Static bus, Luas, DART and rail timetable and wheelchair-accessibility data.",
                source_url="https://developer.nationaltransport.ie/",
            ),
            DataSource(
                id="nta-gtfs-realtime",
                name="NTA GTFS-Realtime",
                state=SourceState.NOT_CONFIGURED if not realtime_ready else SourceState.LIVE,
                purpose="Live arrivals, service disruption and vehicle information for shortlisted transit journeys.",
                source_url="https://developer.nationaltransport.ie/",
            ),
            DataSource(
                id="irish-rail-lifts",
                name="Irish Rail lift alerts",
                state=SourceState.NOT_CONFIGURED if not rail_ready else SourceState.LIVE,
                purpose="Lift and escalator operational alerts for routes using affected rail stations.",
                source_url="https://www.irishrail.ie/en-ie/travel-information/accessibility-onboard-trains/lifts-and-escalators-reports",
            ),
        ]


def _sample_coordinates(coordinates: list[list[float]], limit: int) -> list[list[float]]:
    if len(coordinates) <= limit:
        return coordinates
    step = (len(coordinates) - 1) / (limit - 1)
    return [coordinates[round(index * step)] for index in range(limit)]
