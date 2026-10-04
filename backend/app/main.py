"""Postman-ready HTTP API for WayAble accessibility-aware route planning."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .ai_reviewer import AIRouteReviewer
from .journey import JourneyService
from .models import ErrorResponse, JourneyRequest, Location, ProviderStatus, RouteRequest, RouteResponse, SourceState
from .providers import LocationNotFoundError, OpenStreetMapProvider, ProviderError
from .service import RouteService
from .transit import NtaTransitProvider


def create_app(provider: OpenStreetMapProvider | None = None) -> FastAPI:
    owns_provider = provider is None
    map_provider = provider or OpenStreetMapProvider()
    transit_provider = NtaTransitProvider(settings=map_provider.settings) if owns_provider else None
    service = RouteService(map_provider)
    journey_service = JourneyService(map_provider, transit_provider) if transit_provider else None
    ai_reviewer = AIRouteReviewer()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        shared_client = httpx.AsyncClient(follow_redirects=True, timeout=20) if owns_provider else None
        if shared_client:
            map_provider.set_client(shared_client)
            if transit_provider:
                transit_provider.set_client(shared_client)
        try:
            yield
        finally:
            if shared_client:
                await shared_client.aclose()
                map_provider.set_client(None)
                if transit_provider:
                    transit_provider.set_client(None)

    app = FastAPI(
        title="WayAble Routing API",
        version="0.1.0",
        description="Returns accessibility-aware walking route alternatives for wheelchair and low-vision users.",
        lifespan=lifespan,
    )
    origins = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in origins],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/api/v1/routes",
        response_model=RouteResponse,
        responses={404: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    )
    async def routes(request: RouteRequest) -> RouteResponse:
        try:
            origin_data = await map_provider.geocode(request.from_location)
            destination_data = await map_provider.geocode(request.to_location)
            route_options, accessibility_data_available = await service.plan(origin_data, destination_data, request.user_type)
            route_options, ai_state = await ai_reviewer.review_routes(route_options, request.user_type)
        except LocationNotFoundError as error:
            return JSONResponse(status_code=404, content=ErrorResponse(detail=str(error), code="location_not_found").model_dump())
        except ProviderError as error:
            return JSONResponse(status_code=error.status_code, content=ErrorResponse(detail=str(error), code="provider_error").model_dump())

        warnings = [
            "OpenStreetMap accessibility tags are community-maintained. Missing evidence is shown as unknown, not accessible.",
            "Check live conditions before travel; this API is not a safety-critical navigation service.",
        ]
        if len(route_options) < 2:
            warnings.append("Only one distinct walking route was returned by the routing provider.")
        if not accessibility_data_available:
            warnings.append("Accessibility evidence could not be retrieved for at least one route; confidence is limited.")
        if request.departure_time:
            warnings.append("Departure time will affect public-transport routes when the NTA multimodal adapter is configured; it does not change walking routes.")

        data_sources = map_provider.data_sources(accessibility_data_available) if hasattr(map_provider, "data_sources") else []
        data_sources.append(ai_reviewer.data_source(ai_state))

        return RouteResponse(
            user_type=request.user_type,
            origin=Location(label=origin_data["label"], coordinate={"latitude": origin_data["latitude"], "longitude": origin_data["longitude"]}, provider="OpenStreetMap Nominatim"),
            destination=Location(label=destination_data["label"], coordinate={"latitude": destination_data["latitude"], "longitude": destination_data["longitude"]}, provider="OpenStreetMap Nominatim"),
            routes=route_options,
            provider_status=ProviderStatus(
                accessibility_data=SourceState.LIVE if accessibility_data_available else SourceState.UNAVAILABLE,
                public_transport=SourceState.NOT_CONFIGURED,
            ),
            data_sources=data_sources,
            warnings=warnings,
        )

    @app.post(
        "/api/v1/journeys",
        response_model=RouteResponse,
        responses={404: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    )
    async def journeys(request: JourneyRequest) -> RouteResponse:
        try:
            origin_data = await map_provider.geocode(request.from_location)
            destination_data = await map_provider.geocode(request.to_location)
            walking_routes, walking_accessibility_available = await service.plan(
                origin_data, destination_data, request.user_type
            )
            transit_routes = []
            transit_state = SourceState.NOT_CONFIGURED
            realtime_state = SourceState.NOT_CONFIGURED
            transit_accessibility_available = True
            if request.include_public_transport and journey_service:
                transit_routes, transit_accessibility_available, transit_state, realtime = await journey_service.plan(
                    origin_data,
                    destination_data,
                    request.departure_time or datetime.now(timezone.utc),
                    request.user_type,
                )
                realtime_state = realtime.state
        except LocationNotFoundError as error:
            return JSONResponse(status_code=404, content=ErrorResponse(detail=str(error), code="location_not_found").model_dump())
        except ProviderError as error:
            return JSONResponse(status_code=error.status_code, content=ErrorResponse(detail=str(error), code="provider_error").model_dump())

        all_routes = walking_routes + transit_routes
        all_routes.sort(key=lambda option: ({"recommended": 0, "caution": 1, "avoid": 2}[option.status], -option.confidence_score, option.duration_seconds))
        all_routes, ai_state = await ai_reviewer.review_routes(all_routes[:2], request.user_type)
        all_routes.sort(key=lambda option: ({"recommended": 0, "caution": 1, "avoid": 2}[option.status], -option.confidence_score, option.duration_seconds))
        accessibility_available = walking_accessibility_available and transit_accessibility_available
        sources = map_provider.data_sources(accessibility_available)
        sources = [
            source.model_copy(update={"state": transit_state}) if source.id == "nta-gtfs" else
            source.model_copy(update={"state": realtime_state}) if source.id == "nta-gtfs-realtime" else source
            for source in sources
        ]
        sources.append(ai_reviewer.data_source(ai_state))
        warnings = [
            "Missing accessibility evidence is shown as unknown, not accessible.",
            "Check live conditions before travel; this API is not a safety-critical navigation service.",
        ]
        if transit_state == SourceState.NOT_CONFIGURED and request.include_public_transport:
            warnings.append("Public-transport options need NTA_GTFS_STATIC_URL and NTA_API_KEY before they can be planned.")
        elif request.include_public_transport and not transit_routes:
            warnings.append("No direct transit journey matched the current access profile and timetable window.")
        if realtime_state == SourceState.UNAVAILABLE:
            warnings.append("NTA GTFS-Realtime could not be reached; transit times are based on the static timetable.")
        if not accessibility_available:
            warnings.append("Accessibility evidence could not be retrieved for at least one route; confidence is limited.")

        return RouteResponse(
            user_type=request.user_type,
            origin=Location(label=origin_data["label"], coordinate={"latitude": origin_data["latitude"], "longitude": origin_data["longitude"]}, provider="OpenStreetMap Nominatim"),
            destination=Location(label=destination_data["label"], coordinate={"latitude": destination_data["latitude"], "longitude": destination_data["longitude"]}, provider="OpenStreetMap Nominatim"),
            routes=all_routes,
            provider_status=ProviderStatus(
                accessibility_data=SourceState.LIVE if accessibility_available else SourceState.UNAVAILABLE,
                public_transport=transit_state,
            ),
            data_sources=sources,
            warnings=warnings,
        )

    return app


app = create_app()
