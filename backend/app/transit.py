"""Dynamic, cache-backed GTFS and GTFS-Realtime reader for NTA-configured feeds."""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from math import asin, cos, radians, sin, sqrt
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from .cache import AsyncTTLCache
from .models import SourceState, UserType
from .providers import ProviderError, ProviderSettings


@dataclass(frozen=True)
class TransitStop:
    id: str
    name: str
    latitude: float
    longitude: float
    wheelchair_boarding: str


@dataclass(frozen=True)
class StopTime:
    trip_id: str
    stop_id: str
    arrival_seconds: int
    departure_seconds: int
    sequence: int


@dataclass(frozen=True)
class Trip:
    id: str
    route_id: str
    service_id: str
    wheelchair_accessible: str
    shape_id: str


@dataclass(frozen=True)
class TransitCandidate:
    trip_id: str
    route_label: str
    start_stop: TransitStop
    end_stop: TransitStop
    scheduled_departure_seconds: int
    scheduled_arrival_seconds: int
    start_sequence: int
    end_sequence: int
    delay_seconds: int
    access_is_unknown: bool
    geometry: list[list[float]]


@dataclass(frozen=True)
class RealtimeState:
    state: SourceState
    delays: dict[str, int]
    cancelled_trip_ids: frozenset[str]


@dataclass
class GtfsFeed:
    stops: dict[str, TransitStop]
    trips: dict[str, Trip]
    route_labels: dict[str, str]
    stop_times_by_trip: dict[str, list[StopTime]]
    trip_ids_by_stop: dict[str, set[str]]
    calendars: dict[str, dict[str, str]]
    calendar_exceptions: dict[tuple[str, str], str]
    shapes_by_id: dict[str, list[list[float]]]


class NtaTransitProvider:
    """Reads a configured GTFS ZIP and short-lived GTFS-Realtime updates."""

    def __init__(
        self,
        settings: ProviderSettings | None = None,
        client: httpx.AsyncClient | None = None,
        cache: AsyncTTLCache | None = None,
    ) -> None:
        self.settings = settings or ProviderSettings()
        self._client = client
        self._cache = cache or AsyncTTLCache(max_entries=16)

    def set_client(self, client: httpx.AsyncClient | None) -> None:
        self._client = client

    @property
    def static_configured(self) -> bool:
        return bool(self.settings.nta_api_key and self.settings.nta_gtfs_url)

    @property
    def realtime_configured(self) -> bool:
        return self.static_configured and bool(self.settings.nta_gtfs_realtime_url)

    async def find_direct_candidates(
        self, origin: dict[str, Any], destination: dict[str, Any], departure_time: datetime, user_type: UserType
    ) -> tuple[list[TransitCandidate], SourceState, RealtimeState]:
        if not self.static_configured:
            return [], SourceState.NOT_CONFIGURED, RealtimeState(SourceState.NOT_CONFIGURED, {}, frozenset())

        feed = await self._load_feed()
        realtime = await self._load_realtime()
        local_time = departure_time.astimezone(ZoneInfo("Europe/Dublin"))
        departure_seconds = local_time.hour * 3600 + local_time.minute * 60 + local_time.second
        origin_stops = _nearest_stops(feed.stops.values(), origin["latitude"], origin["longitude"])
        destination_stops = _nearest_stops(feed.stops.values(), destination["latitude"], destination["longitude"])
        destination_ids = {stop.id for stop in destination_stops}
        candidates: list[TransitCandidate] = []
        seen: set[tuple[str, str, str]] = set()

        for start_stop in origin_stops:
            for trip_id in feed.trip_ids_by_stop.get(start_stop.id, set()):
                trip = feed.trips.get(trip_id)
                stop_times = feed.stop_times_by_trip.get(trip_id, [])
                if not trip or not stop_times or trip_id in realtime.cancelled_trip_ids:
                    continue
                if not _service_active(feed, trip.service_id, local_time.date()):
                    continue
                if user_type == UserType.WHEELCHAIR and trip.wheelchair_accessible == "2":
                    continue

                start_index = next((i for i, item in enumerate(stop_times) if item.stop_id == start_stop.id), None)
                if start_index is None:
                    continue
                start_time = stop_times[start_index]
                delay_seconds = realtime.delays.get(trip_id, 0)
                if start_time.departure_seconds + delay_seconds < departure_seconds:
                    continue

                for end_time in stop_times[start_index + 1 :]:
                    if end_time.stop_id not in destination_ids:
                        continue
                    end_stop = feed.stops[end_time.stop_id]
                    if user_type == UserType.WHEELCHAIR and "2" in {
                        start_stop.wheelchair_boarding,
                        end_stop.wheelchair_boarding,
                    }:
                        continue
                    key = (trip_id, start_stop.id, end_stop.id)
                    if key in seen:
                        continue
                    seen.add(key)
                    unknown = "" in {
                        trip.wheelchair_accessible,
                        start_stop.wheelchair_boarding,
                        end_stop.wheelchair_boarding,
                    } or "0" in {
                        trip.wheelchair_accessible,
                        start_stop.wheelchair_boarding,
                        end_stop.wheelchair_boarding,
                    }
                    candidates.append(
                        TransitCandidate(
                            trip_id=trip_id,
                            route_label=feed.route_labels.get(trip.route_id, trip.route_id),
                            start_stop=start_stop,
                            end_stop=end_stop,
                            scheduled_departure_seconds=start_time.departure_seconds,
                            scheduled_arrival_seconds=end_time.arrival_seconds,
                            start_sequence=start_time.sequence,
                            end_sequence=end_time.sequence,
                            delay_seconds=delay_seconds,
                            access_is_unknown=unknown,
                            geometry=_shape_segment(
                                feed.shapes_by_id.get(trip.shape_id, []), start_stop, end_stop
                            ),
                        )
                    )
                    break

        candidates.sort(
            key=lambda item: (
                item.scheduled_arrival_seconds + item.delay_seconds,
                item.access_is_unknown,
                item.scheduled_departure_seconds,
            )
        )
        return candidates[:4], SourceState.LIVE, realtime

    async def _load_feed(self) -> GtfsFeed:
        async def load() -> GtfsFeed:
            response = await self._request("GET", self.settings.nta_gtfs_url or "")
            return _parse_gtfs(response.content)

        return await self._cache.get_or_load("nta:gtfs:static", 3_600, load)

    async def _load_realtime(self) -> RealtimeState:
        if not self.realtime_configured:
            return RealtimeState(SourceState.NOT_CONFIGURED, {}, frozenset())

        async def load() -> RealtimeState:
            try:
                response = await self._request("GET", self.settings.nta_gtfs_realtime_url or "")
                return _parse_gtfs_realtime(response.content)
            except ProviderError:
                return RealtimeState(SourceState.UNAVAILABLE, {}, frozenset())

        return await self._cache.get_or_load("nta:gtfs:realtime", 30, load)

    async def _request(self, method: str, url: str) -> httpx.Response:
        headers = {"Ocp-Apim-Subscription-Key": self.settings.nta_api_key or ""}
        try:
            if self._client:
                response = await self._client.request(method, url, headers=headers)
            else:
                async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
                    response = await client.request(method, url, headers=headers)
            response.raise_for_status()
            return response
        except httpx.HTTPError as error:
            raise ProviderError("NTA data provider could not be reached.") from error


def _parse_gtfs(content: bytes) -> GtfsFeed:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        stops = {
            row["stop_id"]: TransitStop(
                id=row["stop_id"],
                name=row.get("stop_name") or row["stop_id"],
                latitude=float(row["stop_lat"]),
                longitude=float(row["stop_lon"]),
                wheelchair_boarding=(row.get("wheelchair_boarding") or ""),
            )
            for row in _rows(archive, "stops.txt")
            if row.get("stop_id") and row.get("stop_lat") and row.get("stop_lon")
        }
        trips = {
            row["trip_id"]: Trip(
                id=row["trip_id"],
                route_id=row.get("route_id") or "",
                service_id=row.get("service_id") or "",
                wheelchair_accessible=(row.get("wheelchair_accessible") or ""),
                shape_id=row.get("shape_id") or "",
            )
            for row in _rows(archive, "trips.txt")
            if row.get("trip_id")
        }
        route_labels = {
            row["route_id"]: " ".join(part for part in [row.get("route_short_name"), row.get("route_long_name")] if part)
            or row["route_id"]
            for row in _rows(archive, "routes.txt")
            if row.get("route_id")
        }
        stop_times_by_trip: dict[str, list[StopTime]] = {}
        trip_ids_by_stop: dict[str, set[str]] = {}
        for row in _rows(archive, "stop_times.txt"):
            trip_id, stop_id = row.get("trip_id"), row.get("stop_id")
            if not trip_id or not stop_id or trip_id not in trips or stop_id not in stops:
                continue
            item = StopTime(
                trip_id=trip_id,
                stop_id=stop_id,
                arrival_seconds=_time_to_seconds(row.get("arrival_time") or ""),
                departure_seconds=_time_to_seconds(row.get("departure_time") or ""),
                sequence=int(row.get("stop_sequence") or 0),
            )
            stop_times_by_trip.setdefault(trip_id, []).append(item)
            trip_ids_by_stop.setdefault(stop_id, set()).add(trip_id)
        for stop_times in stop_times_by_trip.values():
            stop_times.sort(key=lambda item: item.sequence)
        calendars = {row["service_id"]: row for row in _rows(archive, "calendar.txt") if row.get("service_id")}
        calendar_exceptions = {
            (row["service_id"], row["date"]): row.get("exception_type") or ""
            for row in _rows(archive, "calendar_dates.txt")
            if row.get("service_id") and row.get("date")
        }
        shapes_by_id = _parse_shapes(_rows(archive, "shapes.txt"))
    return GtfsFeed(stops, trips, route_labels, stop_times_by_trip, trip_ids_by_stop, calendars, calendar_exceptions, shapes_by_id)


def _rows(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    try:
        with archive.open(name) as file:
            return list(csv.DictReader(io.TextIOWrapper(file, encoding="utf-8-sig")))
    except KeyError:
        return []


def _parse_shapes(rows: list[dict[str, str]]) -> dict[str, list[list[float]]]:
    ordered: dict[str, list[tuple[int, list[float]]]] = {}
    for row in rows:
        shape_id = row.get("shape_id")
        latitude, longitude = row.get("shape_pt_lat"), row.get("shape_pt_lon")
        if not shape_id or not latitude or not longitude:
            continue
        ordered.setdefault(shape_id, []).append(
            (int(row.get("shape_pt_sequence") or 0), [float(longitude), float(latitude)])
        )
    return {shape_id: [point for _, point in sorted(points)] for shape_id, points in ordered.items()}


def _shape_segment(shape: list[list[float]], start_stop: TransitStop, end_stop: TransitStop) -> list[list[float]]:
    if not shape:
        return [[start_stop.longitude, start_stop.latitude], [end_stop.longitude, end_stop.latitude]]
    start_index = min(
        range(len(shape)),
        key=lambda index: _distance_meters(start_stop.latitude, start_stop.longitude, shape[index][1], shape[index][0]),
    )
    end_index = min(
        range(start_index, len(shape)),
        key=lambda index: _distance_meters(end_stop.latitude, end_stop.longitude, shape[index][1], shape[index][0]),
    )
    points = shape[start_index : end_index + 1]
    return [[start_stop.longitude, start_stop.latitude], *points, [end_stop.longitude, end_stop.latitude]]


def _parse_gtfs_realtime(content: bytes) -> RealtimeState:
    try:
        from google.transit import gtfs_realtime_pb2
    except ImportError:
        return RealtimeState(SourceState.UNAVAILABLE, {}, frozenset())

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(content)
    delays: dict[str, int] = {}
    cancelled: set[str] = set()
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        trip = entity.trip_update.trip
        trip_id = trip.trip_id
        if not trip_id:
            continue
        if trip.schedule_relationship == gtfs_realtime_pb2.TripDescriptor.CANCELED:
            cancelled.add(trip_id)
            continue
        delay_values = [
            value.delay
            for update in entity.trip_update.stop_time_update
            for value in (update.arrival, update.departure)
            if value.HasField("delay")
        ]
        if delay_values:
            delays[trip_id] = max(delay_values)
    return RealtimeState(SourceState.LIVE, delays, frozenset(cancelled))


def _nearest_stops(stops: Any, latitude: float, longitude: float, limit: int = 6) -> list[TransitStop]:
    return sorted(stops, key=lambda stop: _distance_meters(latitude, longitude, stop.latitude, stop.longitude))[:limit]


def _service_active(feed: GtfsFeed, service_id: str, service_date: date) -> bool:
    date_key = service_date.strftime("%Y%m%d")
    exception = feed.calendar_exceptions.get((service_id, date_key))
    if exception == "1":
        return True
    if exception == "2":
        return False
    calendar = feed.calendars.get(service_id)
    if not calendar:
        return True
    if not (calendar.get("start_date", "") <= date_key <= calendar.get("end_date", "99999999")):
        return False
    weekday = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")[service_date.weekday()]
    return calendar.get(weekday) == "1"


def _time_to_seconds(value: str) -> int:
    try:
        hours, minutes, seconds = (int(part) for part in value.split(":"))
        return hours * 3600 + minutes * 60 + seconds
    except ValueError:
        return 0


def _distance_meters(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> int:
    radius = 6_371_000
    delta_latitude = radians(latitude_b - latitude_a)
    delta_longitude = radians(longitude_b - longitude_a)
    value = sin(delta_latitude / 2) ** 2 + cos(radians(latitude_a)) * cos(radians(latitude_b)) * sin(delta_longitude / 2) ** 2
    return round(2 * radius * asin(sqrt(value)))
