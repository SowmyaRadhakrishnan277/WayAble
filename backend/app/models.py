from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class UserType(str, Enum):
    WHEELCHAIR = "wheelchair"
    LOW_VISION = "low_vision"


class SourceState(str, Enum):
    LIVE = "live"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"


class Coordinate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class RouteRequest(BaseModel):
    from_location: str = Field(min_length=2, max_length=180, examples=["Dogpatch Labs, Dublin"])
    to_location: str = Field(min_length=2, max_length=180, examples=["Trinity College Dublin"])
    user_type: UserType = Field(examples=[UserType.WHEELCHAIR])
    departure_time: datetime | None = Field(
        default=None,
        description="Reserved for real-time public-transport planning. Walking routes are not time-dependent.",
    )


class JourneyRequest(RouteRequest):
    include_public_transport: bool = Field(
        default=True,
        description="When NTA GTFS is configured, include eligible bus, Luas, DART and rail options.",
    )


class Location(BaseModel):
    label: str
    coordinate: Coordinate
    provider: str


class RouteGeometry(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[list[float]] = Field(
        description="GeoJSON positions in [longitude, latitude] order for a map renderer."
    )


class AccessibilityEvidence(BaseModel):
    category: str
    severity: Literal["positive", "caution", "blocker", "unknown"]
    message: str
    coordinate: Coordinate | None = None
    source: str = "OpenStreetMap"
    source_url: str | None = None
    observed_at: str | None = None
    raw_tags: dict[str, str] = Field(default_factory=dict)


class JourneyInstruction(BaseModel):
    sequence: int
    instruction: str
    distance_meters: int
    duration_seconds: int
    coordinate: Coordinate | None = None


class JourneyLeg(BaseModel):
    mode: Literal["walk", "transit"]
    start_label: str
    end_label: str
    distance_meters: int
    duration_seconds: int
    geometry: RouteGeometry
    instructions: list[JourneyInstruction]


class DataSource(BaseModel):
    id: str
    name: str
    state: SourceState
    purpose: str
    source_url: str
    updated_at: datetime | None = None


class AIReview(BaseModel):
    state: SourceState
    model: str | None = None
    confidence_adjustment: int = Field(ge=-10, le=10)
    explanation: str
    risk_flags: list[str] = Field(default_factory=list)


class RouteOption(BaseModel):
    id: str
    label: str
    status: Literal["recommended", "caution", "avoid"]
    confidence_score: int = Field(ge=0, le=100)
    rule_based_confidence_score: int | None = Field(default=None, ge=0, le=100)
    distance_meters: int
    duration_seconds: int
    geometry: RouteGeometry
    legs: list[JourneyLeg]
    accessibility_evidence: list[AccessibilityEvidence]
    evidence_summary: str
    ai_review: AIReview | None = None


class ProviderStatus(BaseModel):
    geocoding: Literal["live"] = "live"
    routing: Literal["live"] = "live"
    accessibility_data: SourceState
    public_transport: SourceState


class RouteResponse(BaseModel):
    user_type: UserType
    origin: Location
    destination: Location
    routes: list[RouteOption] = Field(max_length=2)
    provider_status: ProviderStatus
    data_sources: list[DataSource]
    warnings: list[str] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    detail: str
    code: str
