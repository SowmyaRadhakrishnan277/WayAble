"""Combines walking access legs with dynamic GTFS transit candidates."""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo

from .models import AccessibilityEvidence, Coordinate, JourneyInstruction, JourneyLeg, RouteGeometry, RouteOption, SourceState, UserType
from .providers import ProviderError
from .service import assess_features, build_walking_legs, status_rank
from .transit import NtaTransitProvider, RealtimeState, TransitCandidate, _distance_meters


class JourneyService:
    def __init__(self, map_provider: Any, transit_provider: NtaTransitProvider) -> None:
        self.map_provider = map_provider
        self.transit_provider = transit_provider

    async def plan(
        self, origin: dict[str, Any], destination: dict[str, Any], departure_time, user_type: UserType
    ) -> tuple[list[RouteOption], bool, SourceState, RealtimeState]:
        candidates, gtfs_state, realtime = await self.transit_provider.find_direct_candidates(
            origin, destination, departure_time, user_type
        )
        options: list[RouteOption] = []
        accessibility_data_available = True
        local_time = departure_time.astimezone(ZoneInfo("Europe/Dublin"))
        requested_departure_seconds = local_time.hour * 3600 + local_time.minute * 60 + local_time.second

        for candidate in candidates[:2]:
            option, candidate_accessibility_available = await self._build_option(
                origin, destination, candidate, user_type, realtime, requested_departure_seconds
            )
            accessibility_data_available = accessibility_data_available and candidate_accessibility_available
            if option:
                options.append(option)

        options.sort(key=lambda option: (status_rank(option.status), -option.confidence_score, option.duration_seconds))
        for index, option in enumerate(options, start=1):
            option.id = f"transit-route-{index}"
            option.label = {
                "recommended": "Recommended transit journey",
                "caution": "Transit journey with access details to check",
                "avoid": "Transit journey with a recorded access barrier",
            }[option.status]
        return options, accessibility_data_available, gtfs_state, realtime

    async def _build_option(
        self,
        origin: dict[str, Any],
        destination: dict[str, Any],
        candidate: TransitCandidate,
        user_type: UserType,
        realtime: RealtimeState,
        requested_departure_seconds: int,
    ) -> tuple[RouteOption | None, bool]:
        try:
            approach_routes = await self.map_provider.routes(origin, _stop_location(candidate.start_stop))
            egress_routes = await self.map_provider.routes(_stop_location(candidate.end_stop), destination)
        except ProviderError:
            return None, False
        if not approach_routes or not egress_routes:
            return None, False
        approach, egress = approach_routes[0], egress_routes[0]

        approach_features, approach_available = await self.map_provider.accessibility_features(approach["geometry"]["coordinates"])
        egress_features, egress_available = await self.map_provider.accessibility_features(egress["geometry"]["coordinates"])
        evidence = assess_features(approach_features, user_type) + assess_features(egress_features, user_type)
        if not approach_available or not egress_available:
            evidence.append(
                AccessibilityEvidence(
                    category="accessibility_data",
                    severity="unknown",
                    message="Accessibility evidence could not be retrieved for a walking leg; check conditions before travel.",
                    source="Overpass API",
                    source_url="https://overpass-api.de/",
                )
            )
        evidence.extend(_transit_evidence(candidate, user_type, realtime))

        blockers = sum(item.severity == "blocker" for item in evidence)
        cautions = sum(item.severity == "caution" for item in evidence)
        positives = sum(item.severity == "positive" for item in evidence)
        unknowns = sum(item.severity == "unknown" for item in evidence)
        confidence = max(5, min(100, 55 + min(24, positives * 5) - cautions * 8 - blockers * 30 - unknowns * 6))
        status = "avoid" if blockers else "caution" if cautions or unknowns else "recommended"

        wait_seconds = max(0, candidate.scheduled_departure_seconds + candidate.delay_seconds - requested_departure_seconds)
        transit_seconds = max(0, candidate.scheduled_arrival_seconds - candidate.scheduled_departure_seconds + candidate.delay_seconds)
        transit_distance = _distance_meters(
            candidate.start_stop.latitude,
            candidate.start_stop.longitude,
            candidate.end_stop.latitude,
            candidate.end_stop.longitude,
        )
        transit_geometry = RouteGeometry(coordinates=candidate.geometry)
        transit_leg = JourneyLeg(
            mode="transit",
            start_label=candidate.start_stop.name,
            end_label=candidate.end_stop.name,
            distance_meters=transit_distance,
            duration_seconds=transit_seconds,
            geometry=transit_geometry,
            instructions=[
                JourneyInstruction(
                    sequence=1,
                    instruction=f"Board {candidate.route_label} at {candidate.start_stop.name}.",
                    distance_meters=0,
                    duration_seconds=wait_seconds,
                    coordinate=Coordinate(latitude=candidate.start_stop.latitude, longitude=candidate.start_stop.longitude),
                ),
                JourneyInstruction(
                    sequence=2,
                    instruction=f"Travel to {candidate.end_stop.name} and alight.",
                    distance_meters=transit_distance,
                    duration_seconds=transit_seconds,
                    coordinate=Coordinate(latitude=candidate.end_stop.latitude, longitude=candidate.end_stop.longitude),
                ),
            ],
        )
        legs = build_walking_legs(approach, origin["label"], candidate.start_stop.name) + [transit_leg] + build_walking_legs(
            egress, candidate.end_stop.name, destination["label"]
        )
        geometry = RouteGeometry(coordinates=_join_geometries(legs))
        summary = _summary(user_type, positives, cautions, blockers, unknowns)
        return (
            RouteOption(
                id="transit-route",
                label="Transit journey",
                status=status,
                confidence_score=confidence,
                rule_based_confidence_score=confidence,
                distance_meters=round(approach["distance"] + transit_distance + egress["distance"]),
                duration_seconds=round(approach["duration"] + wait_seconds + transit_seconds + egress["duration"]),
                geometry=geometry,
                legs=legs,
                accessibility_evidence=evidence,
                evidence_summary=summary,
            ),
            approach_available and egress_available,
        )


def _stop_location(stop) -> dict[str, Any]:
    return {"label": stop.name, "latitude": stop.latitude, "longitude": stop.longitude}


def _transit_evidence(candidate: TransitCandidate, user_type: UserType, realtime: RealtimeState) -> list[AccessibilityEvidence]:
    source_url = "https://developer.nationaltransport.ie/"
    if user_type == UserType.WHEELCHAIR:
        if candidate.access_is_unknown:
            return [
                AccessibilityEvidence(
                    category="transit_access",
                    severity="unknown",
                    message="NTA GTFS does not provide complete wheelchair-access information for this trip or its stops.",
                    source="NTA GTFS",
                    source_url=source_url,
                )
            ]
        return [
            AccessibilityEvidence(
                category="transit_access",
                severity="positive",
                message="NTA GTFS marks the selected trip and its boarding/alighting stops as wheelchair-accessible.",
                source="NTA GTFS",
                source_url=source_url,
            )
        ]
    evidence = [
        AccessibilityEvidence(
            category="transit_wayfinding",
            severity="unknown",
            message="GTFS does not confirm low-vision wayfinding information for this transit leg.",
            source="NTA GTFS",
            source_url=source_url,
        )
    ]
    if realtime.state == SourceState.UNAVAILABLE:
        evidence.append(
            AccessibilityEvidence(
                category="realtime_status",
                severity="unknown",
                message="Live NTA transit updates were unavailable when this journey was planned.",
                source="NTA GTFS-Realtime",
                source_url=source_url,
            )
        )
    return evidence


def _join_geometries(legs: list[JourneyLeg]) -> list[list[float]]:
    combined: list[list[float]] = []
    for leg in legs:
        for coordinate in leg.geometry.coordinates:
            if not combined or coordinate != combined[-1]:
                combined.append(coordinate)
    return combined


def _summary(user_type: UserType, positives: int, cautions: int, blockers: int, unknowns: int) -> str:
    profile = "wheelchair" if user_type == UserType.WHEELCHAIR else "low-vision"
    if blockers:
        return f"Not recommended for the {profile} profile: access blockers were found on a walking leg."
    if cautions or unknowns:
        return f"Use caution for the {profile} profile: some access evidence is incomplete or needs checking."
    return f"Verified accessibility evidence was found for this {profile} journey."
