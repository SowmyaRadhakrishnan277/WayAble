# WayAble Routing API

FastAPI backend for returning up to two accessibility-aware walking routes. It uses public OpenStreetMap services:

- Nominatim resolves the `from_location` and `to_location` inputs.
- A pedestrian OSRM deployment returns walking-route geometry in GeoJSON form.
- Overpass reads nearby OSM access tags (`wheelchair`, `kerb`, `tactile_paving`, `surface`, `smoothness`, and `highway=steps`) to calculate confidence.

The API does **not** handle sign-in yet and does not store user data. Every route returns both a map-ready GeoJSON `LineString` and ordered, coordinate-linked text instructions, so map and text-route modules consume the same journey object.

## Run locally

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
$env:PYTHONPATH = "backend"
uvicorn app.main:app --app-dir backend --reload --port 8000
```

Open `http://127.0.0.1:8000/docs` for interactive API documentation or use Postman.

For a ready-made client, import [WayAble.postman_collection.json](C:/Users/adity/.codex/BFI_project/backend/postman/WayAble.postman_collection.json) into Postman and send either route request.

## Postman request

`POST http://127.0.0.1:8000/api/v1/routes`

Header: `Content-Type: application/json`

```json
{
  "from_location": "Dogpatch Labs, Dublin",
  "to_location": "Trinity College Dublin",
  "user_type": "wheelchair"
}
```

Use `"low_vision"` for the other profile. The response has up to two ranked routes. A provider may only return one distinct route; the API reports that rather than duplicating a route.

Each route contains `legs[0].instructions` for a text journey view, while `geometry` and `legs[0].geometry` contain the route line for a map renderer. `data_sources` records source purpose, state, URL, and freshness. The API caches geocoding for 24 hours, route geometry for 10 minutes, and OSM accessibility corridor queries for 15 minutes to stay within public-provider limits.

## Transit Sources

The current endpoint is deliberately walking-only. It reports NTA GTFS, NTA GTFS-Realtime, and Irish Rail lift alerts as `not_configured` until valid provider credentials and machine-readable URLs are supplied in environment variables. This avoids returning transit guidance from incomplete or scraped data. The response already supports transit legs for the next multimodal adapter.

## Confidence rules

Confidence is evidence-based, not a guarantee. Known steps, `wheelchair=no`, and stiles are blockers; raised kerbs and rough surfaces are cautions; wheelchair tags, lowered kerbs, and tactile paving for low-vision users are positive evidence. A lack of OSM tags is explicitly treated as unknown.

`OSRM_BASE_URL` defaults to the public OpenStreetMap pedestrian routing deployment. The corresponding HTTP API conventionally uses the `driving` profile path segment even though that deployment is configured with a walking graph; leave `OSRM_ROUTE_PROFILE=driving` unless switching both settings to another compatible routing provider.

## Test

```powershell
$env:PYTHONPATH = "backend"
pytest backend\tests -q
```

Tests use a fake map provider, so they do not call external APIs.
