"""Postman-ready HTTP API for WayAble accessibility-aware route planning."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .models import ErrorResponse, Location, ProviderStatus, RouteRequest, RouteResponse, SourceState
from .providers import LocationNotFoundError, OpenStreetMapProvider, ProviderError
from .service import RouteService


def create_app(provider: OpenStreetMapProvider | None = None) -> FastAPI:
    owns_provider = provider is None
    map_provider = provider or OpenStreetMapProvider()
    service = RouteService(map_provider)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        shared_client = httpx.AsyncClient(follow_redirects=True, timeout=20) if owns_provider else None
        if shared_client:
            map_provider.set_client(shared_client)
        try:
            yield
        finally:
            if shared_client:
                await shared_client.aclose()
                map_provider.set_client(None)

    app = FastAPI(
        title="WayAble Routing API",
        version="0.1.0",
        description="Returns accessibility-aware walking route alternatives for wheelchair and low-vision users.",
        lifespan=lifespan,
    )
    origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
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

    return app


app = create_app()
