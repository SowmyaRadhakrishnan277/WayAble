# WayAble

WayAble is a Dublin-first accessibility-aware walking journey demo. The frontend uses the FastAPI routing service for live routes when configured, with a local fixture mode for offline demos.

## Run the complete app on macOS

Use two terminal windows from this project folder.

### 1. Start the backend

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
PYTHONPATH=backend python -m uvicorn app.main:app --app-dir backend --env-file backend/.env --reload --port 8000
```

Check `http://localhost:8000/health` or open `http://localhost:8000/docs` for the API.

The backend calls public Nominatim, pedestrian OSRM, and Overpass services. It caches responses and reports missing access tags as unknown. Replace the example contact in `WAYABLE_USER_AGENT` with a real contact because live route search queries public map services. AI review is optional and off by default. Enable it with `WAYABLE_AI_ENABLED=true` and either an `OPENAI_API_KEY` or a gateway `OPENAI_BASE_URL`. Never put the key in the frontend `.env` or commit `backend/.env`. NTA transit planning is optional and needs approved feed URLs and credentials; Irish Rail lift status is not configured in this sample.

### 2. Start the frontend

In another terminal:

```sh
cp .env.example .env
npm install
npm run dev
```

Open the Local URL printed by Vite, normally `http://localhost:5173/`. Restart Vite after changing `.env`.

To run without the backend, set `VITE_USE_MOCKS=true` in `.env`. Fixture routes and access facts are labeled as demo data.

## What is connected

- Route planning: the frontend calls `POST /api/v1/journeys`. It returns walking routes and adds direct transit options when NTA GTFS credentials and feed URLs are configured. `POST /api/v1/routes` remains available for walking-only searches.
- The frontend converts API response fields without upgrading unknown, caution, or mapped states to confirmed. Route tags near a path are evidence, not a safety guarantee.
- Optional AI review can add a bounded advisory confidence adjustment and explanation; it cannot change a route's blocker status and receives no place names, coordinates, or user identifiers.
- The live API currently scores the wheelchair or low-vision profile. Chair type, slope, and minimum-width settings are saved in the browser but are not yet sent to or scored by the API.
- Account sign-in, saved routes, and community reports remain browser-local demo features. The attached backend does not implement authentication, persistent storage, or report endpoints.

## Checks

```sh
npm run build
npm run contrast
```

Backend unit tests (after installing the requirements):

```sh
PYTHONPATH=backend python -m pytest backend/tests -q
```

This prototype is not safety-critical navigation. Check current conditions before travelling.
