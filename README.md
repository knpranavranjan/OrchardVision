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

| Needed | macOS | Windows |
|---|---|---|
| Docker Desktop (runs the database) | [docker.com](https://www.docker.com/products/docker-desktop/) | the same |
| uv (runs the Python backend; it fetches Python 3.12 itself) | `brew install uv` | [install guide](https://docs.astral.sh/uv/getting-started/installation/) |
| Node.js 20 or newer (runs the front end) | `brew install node` | [nodejs.org](https://nodejs.org) |
| Google Chrome | only for the browser checks | the same |

## Run it

```bash
git clone https://github.com/knpranavranjan/OrchardVision.git
cd OrchardVision
python3 run.py            # database, backend, front end, opens the browser
python3 run.py --sitl     # the same, plus the ArduPilot software autopilot
python3 run.py --stop     # stop the database and autopilot containers
```

On Windows type `python` instead of `python3`. Open Docker Desktop first and
wait until it is running. The first start downloads packages and takes a few
minutes; later starts take seconds. Press Ctrl+C in the terminal to stop.

Or by hand:

```bash
docker compose up -d db
cd backend && uv sync && uv run alembic upgrade head
uv run uvicorn app.main:app --port 8000          # terminal 1
cd frontend && npm install && npm run dev        # terminal 2, then open http://localhost:5173
```

### Notes for a Mac

- **Connecting a drone by USB or telemetry radio:** the port is named like
  `/dev/cu.usbmodem1101` or `/dev/cu.usbserial-0001` (on Windows it is `COM5`).
  The Connect dialog lists the ports it finds.
- **Apple Silicon (M1 and later):** the database and autopilot images are built
  for Intel, so Docker runs them through its emulation. In Docker Desktop keep
  "Use Rosetta for x86/amd64 emulation" switched on (Settings, General).
- **My location on the map:** allow location for your browser in System
  Settings, Privacy & Security, Location Services.

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
