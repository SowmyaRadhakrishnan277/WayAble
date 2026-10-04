"""Accessibility-specific ranking that sits on top of ordinary walking routes."""

from __future__ import annotations

from typing import Any

from .models import (
    AccessibilityEvidence,
    Coordinate,
    JourneyInstruction,
    JourneyLeg,
    RouteGeometry,
    RouteOption,
    UserType,
)


class RouteService:
    def __init__(self, provider: Any) -> None:
        self.provider = provider

    async def plan(self, origin: dict[str, Any], destination: dict[str, Any], user_type: UserType) -> tuple[list[RouteOption], bool]:
        raw_routes = await self.provider.routes(origin, destination)
        options: list[RouteOption] = []
        access_data_available = True

        for index, raw_route in enumerate(raw_routes):
            coordinates = raw_route["geometry"]["coordinates"]
            raw_features, provider_available = await self.provider.accessibility_features(coordinates)
            if not provider_available:
                access_data_available = False
            evidence = assess_features(raw_features, user_type)
            if not provider_available:
                evidence.append(
                    AccessibilityEvidence(
                        category="accessibility_data",
                        severity="unknown",
                        message="Accessibility evidence could not be retrieved for this route; check conditions before travel.",
                        source="Overpass API",
                        source_url="https://overpass-api.de/",
                    )
                )
            options.append(build_option(index, raw_route, evidence, user_type))

        options.sort(key=lambda option: (status_rank(option.status), -option.confidence_score, option.duration_seconds))
        for index, option in enumerate(options, start=1):
            option.id = f"route-{index}"
            option.label = {
                "recommended": "Recommended route" if index == 1 else "Step-free alternative",
                "caution": "Route with access details to check",
                "avoid": "Route with a recorded access barrier",
            }[option.status]
        return options[:2], access_data_available


def assess_features(features: list[dict[str, Any]], user_type: UserType) -> list[AccessibilityEvidence]:
    evidence: list[AccessibilityEvidence] = []
    seen: set[tuple[str, str, str | None]] = set()
    for feature in features:
        tags = {str(key): str(value) for key, value in feature.get("tags", {}).items()}
        coordinate = _feature_coordinate(feature)
        source_url = _osm_url(feature)
        candidates = _feature_evidence(tags, coordinate, source_url, user_type)
        for item in candidates:
            identity = (item.category, item.message, item.source_url)
            if identity not in seen:
                seen.add(identity)
                evidence.append(item)
    return evidence


def _feature_evidence(
    tags: dict[str, str], coordinate: Coordinate | None, source_url: str | None, user_type: UserType
) -> list[AccessibilityEvidence]:
    items: list[AccessibilityEvidence] = []

    def add(category: str, severity: str, message: str) -> None:
        items.append(
            AccessibilityEvidence(
                category=category,
                severity=severity,  # type: ignore[arg-type]
                message=message,
                coordinate=coordinate,
                source_url=source_url,
                raw_tags=tags,
            )
        )

    pedestrian_highways = {
        "crossing",
        "cycleway",
        "footway",
        "living_street",
        "path",
        "pedestrian",
        "residential",
        "service",
        "steps",
        "track",
        "unclassified",
    }
    # An amenity may be wheelchair-tagged without describing the path outside it.
    # Only use highway-tagged pedestrian features as route evidence; a nearby
    # accessible café must not make an uncertain route look accessible.
    route_feature = tags.get("highway") in pedestrian_highways
    crossing = tags.get("highway") == "crossing" or "crossing" in tags

    if tags.get("highway") == "steps" or (route_feature and tags.get("wheelchair") == "no"):
        add("steps", "blocker", "OpenStreetMap reports steps or wheelchair access is not available here.")
    if tags.get("barrier") in {"stile", "turnstile"}:
        add("barrier", "blocker", f"OpenStreetMap reports a {tags['barrier']} on or near this route.")
    if tags.get("kerb") in {"raised", "high"}:
        add("kerb", "caution", "A raised kerb is recorded near this route.")
    if route_feature and tags.get("wheelchair") in {"yes", "designated"}:
        add("wheelchair_access", "positive", "Wheelchair access is tagged for a nearby route feature.")
    if tags.get("kerb") in {"lowered", "flush", "rolled"}:
        add("kerb", "positive", "A lowered or flush kerb is recorded near this route.")
    if route_feature and tags.get("surface") in {"cobblestone", "sett", "gravel", "ground", "unpaved"}:
        add("surface", "caution", f"The surface is tagged as {tags['surface']}, which may be difficult to traverse.")

    if user_type == UserType.LOW_VISION:
        if (crossing or route_feature) and tags.get("tactile_paving") in {"yes", "incorrect"}:
            add("tactile_paving", "positive", "Tactile paving is recorded near this crossing or route feature.")
        if (crossing or route_feature) and tags.get("tactile_paving") == "no":
            add("tactile_paving", "caution", "No tactile paving is recorded for a nearby crossing or route feature.")
    return items


def build_option(index: int, raw_route: dict[str, Any], evidence: list[AccessibilityEvidence], user_type: UserType) -> RouteOption:
    blockers = sum(item.severity == "blocker" for item in evidence)
    cautions = sum(item.severity == "caution" for item in evidence)
    positives = sum(item.severity == "positive" for item in evidence)
    unknowns = sum(item.severity == "unknown" for item in evidence)
    tagged_evidence = len(evidence)

    known_evidence = tagged_evidence - unknowns
    confidence = 45 + min(30, known_evidence * 6) + min(15, positives * 4) - cautions * 8 - blockers * 30 - unknowns * 6
    confidence = max(5, min(100, confidence))
    status = "avoid" if blockers else "caution" if cautions or unknowns or positives < 2 else "recommended"
    summary = _summary(status, user_type, positives, cautions, blockers, unknowns, tagged_evidence)
    return RouteOption(
        id=f"route-{index + 1}",
        label="Route",
        status=status,
        confidence_score=confidence,
        distance_meters=round(raw_route["distance"]),
        duration_seconds=round(raw_route["duration"]),
        geometry=RouteGeometry(coordinates=raw_route["geometry"]["coordinates"]),
        legs=build_walking_legs(raw_route),
        accessibility_evidence=evidence,
        evidence_summary=summary,
    )


def build_walking_legs(
    raw_route: dict[str, Any], start_label: str = "Start", end_label: str = "Destination"
) -> list[JourneyLeg]:
    route_geometry = RouteGeometry(coordinates=raw_route["geometry"]["coordinates"])
    raw_legs = raw_route.get("legs", [])
    instructions: list[JourneyInstruction] = []

    for leg in raw_legs:
        for step in leg.get("steps", []):
            maneuver = step.get("maneuver", {})
            location = maneuver.get("location")
            coordinate = Coordinate(latitude=location[1], longitude=location[0]) if location else None
            instructions.append(
                JourneyInstruction(
                    sequence=len(instructions) + 1,
                    instruction=_instruction_text(step),
                    distance_meters=round(step.get("distance", 0)),
                    duration_seconds=round(step.get("duration", 0)),
                    coordinate=coordinate,
                )
            )

    if not instructions:
        instructions.append(
            JourneyInstruction(
                sequence=1,
                instruction="Follow the highlighted walking route to your destination.",
                distance_meters=round(raw_route["distance"]),
                duration_seconds=round(raw_route["duration"]),
                coordinate=None,
            )
        )

    return [
        JourneyLeg(
            mode="walk",
            start_label=start_label,
            end_label=end_label,
            distance_meters=round(raw_route["distance"]),
            duration_seconds=round(raw_route["duration"]),
            geometry=route_geometry,
            instructions=instructions,
        )
    ]


def _instruction_text(step: dict[str, Any]) -> str:
    maneuver = step.get("maneuver", {})
    maneuver_type = maneuver.get("type", "continue")
    modifier = maneuver.get("modifier", "")
    road_name = step.get("name") or "the path"

    if maneuver_type == "depart":
        return f"Start on {road_name}."
    if maneuver_type == "arrive":
        return "Arrive at your destination."
    if maneuver_type == "turn":
        return f"Turn {modifier} onto {road_name}.".replace("Turn  ", "Turn ")
    if maneuver_type == "roundabout":
        return f"Take the roundabout toward {road_name}."
    if maneuver_type in {"new name", "continue"}:
        return f"Continue on {road_name}."
    return f"Continue toward {road_name}."


def _summary(
    status: str, user_type: UserType, positives: int, cautions: int, blockers: int, unknowns: int, tagged_evidence: int
) -> str:
    profile = "wheelchair" if user_type == UserType.WHEELCHAIR else "low-vision"
    if blockers:
        return f"Not recommended for the {profile} profile: {blockers} blocking access signal(s) were found."
    if cautions:
        return f"Use caution for the {profile} profile: {cautions} possible access concern(s) were found."
    if unknowns:
        return f"Use caution for the {profile} profile: accessibility evidence is unavailable for this route."
    if tagged_evidence:
        return f"{positives} positive accessibility signal(s) were found for the {profile} profile."
    return "No nearby accessibility tags were returned; route suitability is unknown."


def status_rank(status: str) -> int:
    return {"recommended": 0, "caution": 1, "avoid": 2}[status]


def _feature_coordinate(feature: dict[str, Any]) -> Coordinate | None:
    if "lat" in feature and "lon" in feature:
        return Coordinate(latitude=feature["lat"], longitude=feature["lon"])
    center = feature.get("center")
    if center:
        return Coordinate(latitude=center["lat"], longitude=center["lon"])
    return None


def _osm_url(feature: dict[str, Any]) -> str | None:
    if feature.get("type") and feature.get("id"):
        return f"https://www.openstreetmap.org/{feature['type']}/{feature['id']}"
    return None
