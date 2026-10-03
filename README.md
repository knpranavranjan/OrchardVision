# OrchardVision

A ground-control and orchard-intelligence platform. It plans a drone survey of
an orchard, flies it on a virtual or real drone, and (in later sections) turns
the footage into a tree map and a fruit count. Papaya is the first crop.

**Built so far: the ground station.** See
[docs/GROUND_STATION.md](docs/GROUND_STATION.md) for what it does, how to connect
a drone, and what has and has not been tested.

- Plan and contracts: [docs/PLAN.md](docs/PLAN.md)
- Illustrated walkthrough: [docs/OrchardVision_Plan.pdf](docs/OrchardVision_Plan.pdf)
- Prior work: [docs/PRIOR_WORK.md](docs/PRIOR_WORK.md)
- Tools and costs: [docs/TOOLS_AND_COSTS.md](docs/TOOLS_AND_COSTS.md)
- Screenshots: [docs/screens/](docs/screens/)

## Layout

```
backend/     FastAPI: drone link, simulator, mission engine, flight records, API
frontend/    React + TypeScript: Fly, Plan, Orchards, Flights, Simulate, Models, Settings
models/      Crop profiles and model versions (the model registry)
contracts/   Test vectors shared by backend and frontend
sitl/        Container for the ArduPilot software autopilot
docs/        Plan, research, ground-station guide, screenshots
```

## Requirements

Docker Desktop, [uv](https://docs.astral.sh/uv/), Node.js 20 or newer, and
Google Chrome for the browser checks.

## Run it

```powershell
.\start.ps1          # database, backend, front end, opens the browser
.\start.ps1 -Sitl    # the same, plus the ArduPilot software autopilot
```

Or by hand:

```powershell
docker compose up -d db
cd backend;  uv sync;  uv run alembic upgrade head
uv run uvicorn app.main:app --port 8000          # terminal 1
cd frontend; npm install; npm run dev            # terminal 2, then open http://localhost:5173
```

First steps in the browser: open **Orchards** and draw one, open **Plan** and
build a survey over it, then press **Rehearse in the simulator**.

## Check it

```powershell
cd backend
uv run pytest                 # everything except the real-autopilot test
uv run pytest -m sitl         # flies ArduPilot SITL; needs the sitl container; about 4 minutes
uv run ruff check .

cd ../frontend
npm test                      # unit tests
npm run lint
npm run build
node e2e/ground-station.mjs   # the whole flow in a real browser, with screenshots
node e2e/sitl.mjs             # the browser flying ArduPilot SITL; about 5 minutes
node e2e/map-tools.mjs        # my location and address search; needs internet
```

The `e2e` scripts need the database, the backend and the dev server running.

## Configuration

Defaults work without any file. To override, copy `.env.example` to `.env`.
Every setting starts with `OV_`.
