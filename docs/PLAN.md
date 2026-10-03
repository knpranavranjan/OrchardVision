# OrchardVision — Locked Plan v1.4

> **Build order changed on 3 October 2026.** The work is now done in three
> sections instead of phase by phase: (1) the complete ground station, built and
> verified, see [GROUND_STATION.md](GROUND_STATION.md); (2) model training and
> integration; (3) simulation with the 3D virtual orchard. The ground station
> covers what Phases 1 to 5 and 9 below describe (foundation, orchards, mission
> core, flight, capture records, the ArduPilot link), except image ingestion,
> which moves to section 2. The contracts in section 5 still apply.

Previous heading: Locked Plan v1.3

Status: locked 2 October 2026, with seven open decisions listed in section 9.
v1.3 adds changes 30 to 38: the multi-crop readiness audit and the 3D items.
Changes after this point go through a version bump of this file, not ad-hoc edits.

v1.1 added changes 17 to 25 in section 2, from the literature scan in
[PRIOR_WORK.md](PRIOR_WORK.md). v1.2 adds changes 26 to 29. The illustrated
walkthrough of this plan is [OrchardVision_Plan.pdf](OrchardVision_Plan.pdf),
built from [OrchardVision_Plan.html](OrchardVision_Plan.html).

## 1. What we are building

OrchardVision is a ground-control and orchard-intelligence platform. It plans a
UAV survey of an orchard, executes that plan on a virtual or a real drone, and
turns the captured images into a tree map and a fruit count with uncertainty.

Four principles hold for every phase:

1. **One mission, three modes.** The same mission revision is previewed,
   simulated and flown. Nothing is planned separately for the simulator.
2. **One vehicle interface.** The software talks to every drone, virtual or
   real, through a single `VehicleLink` interface shaped like MAVLink.
3. **One data pipeline.** A simulated capture and a real capture enter the same
   ingestion endpoint with the same record format.
4. **Crop is data.** Papaya, apple and orange differ only in registry entries
   and crop configuration, never in code paths.

## 2. Changes from the draft plan

| # | Change | Why |
|---|--------|-----|
| 1 | Add a `VehicleLink` interface in Phase 1, with three implementations: kinematic simulator, autopilot SITL, real Pixhawk | The draft deferred the hardware boundary to the end. Without it, the simulator and the Pixhawk path would be two different programs and "same mission" would not hold. |
| 2 | Run the real autopilot firmware in software (SITL) before any hardware | SITL executes missions, failsafes and geofences exactly as the Pixhawk will. The MAVLink code written for SITL is the code that talks to the Pixhawk; only the connection string changes. |
| 3 | The autopilot owns flight safety; OrchardVision configures, verifies and displays it | If the radio link drops, a web app cannot command anything. Failsafes, geofence and battery actions must live on the vehicle. |
| 4 | Split **Mission** (the plan) from **Flight** (one execution of it), and add **Survey** (a set of flights on one day) | The draft had no record of an execution. A mission too large for one battery becomes several flights; a fruit estimate belongs to a survey, not to a mission. |
| 5 | Two survey passes: a nadir pass for the tree map, then a low oblique pass for fruit | Papaya fruit hang on the trunk under the leaf crown and are mostly hidden from directly overhead. A 25 m nadir pass can map trees but cannot count fruit. The tree map from pass one generates the mission for pass two. |
| 6 | The simulator carries ground truth (tree IDs, fruit per tree, what each capture could see) | Rendered trees will not look like the images the models were trained on, so model accuracy cannot be judged in simulation. Ground truth lets the simulator score everything downstream of detection: association, tracking, counting. |
| 7 | Move the mission planner and simulator ahead of tree mapping | Tree mapping needs images with known camera poses. In the draft order nothing produced them until Phase 10. |
| 8 | Build a thin end-to-end slice first (Milestone A), then deepen each module | Contracts locked before anything exercises them are guesses. The slice proves them while they are still cheap to change. |
| 9 | Lock coordinate frames, units and time conventions as a contract | Missing from the draft, and the most common source of silent errors between planner, simulator, autopilot and georeferencing. |
| 10 | "Simulation" is an execution mode, not a mission type; crops are not navigation items | Both contradicted the plan's own principles (one mission for all modes; crop as data). |
| 11 | One Live Flight view for simulated and real flights, with a mode badge | Two views would drift apart. The simulator section keeps only the virtual world setup and replay. |
| 12 | Drop CesiumJS for V1; use MapLibre for the 2D map and Three.js for the 3D orchard | A two-hectare orchard needs a local 3D scene in metres, not a globe. Cesium adds weight, tokens and a second coordinate stack. |
| 13 | Add calibration data collection to statistical counting | The visibility model needs hand-counted trees to be fitted. Without them the hidden-fruit estimate has no basis. |
| 14 | Add a background worker and job table for AI processing | Inference must not block the API or the telemetry stream. |
| 15 | The ground station must work offline | Orchards rarely have internet. Database, map tiles and models all run on the field laptop. |
| 16 | V1 runs AI after the flight, not during it | Full-resolution images stay on the drone until landing. Live view shows capture count and positions only. |
| 17 | Phase 0 viewpoint study: photograph and film real papaya trees from candidate drone viewpoints with a camera on a pole, and hand-count the same trees | No published work counts papaya fruit from a UAV, so the viewing height, angle and number of sides that expose the fruit column are unknown. This is the project's main novelty and its main risk; it is settled with a pole before any mission code. |
| 18 | The fruit pass records video with a pose log, and fruit are associated in 3D using camera pose | Published trackers work on video at about ten frames a second; distance-triggered stills overlap too little. With known poses, fruit can be placed in 3D and merged across views, which is how the best per-tree results were obtained. |
| 19 | Every estimate reports both the raw multi-view count and the calibrated total | In field trials calibration did not always help: raw counts averaged 11% error and calibrated counts 17% across nine mango orchards. |
| 20 | Calibration is a first-class record, collected per orchard and per survey, on about 18 trees stratified by canopy size | Correction models fitted in one season failed to transfer to the next. |
| 21 | One metric set for all stages, in simulation and in the field: tree precision, recall and position error; tracking HOTA and IDF1; per-tree count error, bias and R²; interval coverage | Makes results comparable with published work and makes the phase gates measurable. |
| 22 | Tree identity is resolved by registering each survey to the row pattern of the stored tree map; GPS gives only the first guess | Onboard geolocation of trees with standard GPS has about two metres of error, the same as papaya spacing. |
| 23 | Nadir altitude is a tested parameter, starting from the crop's minimum ground sample distance | In banana, detection fell from 96% at 40 m to 76% at 60 m. |
| 24 | The planner covers three mission types: nadir survey, fruit observation and custom waypoints. Everything else is exported to QGroundControl | Corridor scans, points of interest and rally editing already exist in mature tools and add no value here. |
| 25 | Ingestion accepts ground-captured video with poses as an alternative source for the fruit pass | Most published per-tree fruit counts come from ground platforms. If low flight between rows proves unsafe, the analysis pipeline still runs. |
| 26 | The fruit pass has two coverage modes: full, and sampled. In sampled mode a stratified sample of trees is filmed and the tree map scales the result to the orchard | With rows 2.5 m apart, two hectares hold about 8 km of row. Filming both sides at 1 m/s is 2.2 hours with two side cameras and about 4.5 hours with one. |
| 27 | Shape completion of partly hidden fruit is a supporting step in Phase 11, used for size, centre position and separating overlapping fruit | A half-visible fruit is already counted as one, so completion does not find hidden fruit. It improves sizing and cross-view matching. |
| 28 | The estimate has explicit layers: raw unique count, fruit missed by chance (from how many passes saw each fruit), fruit never visible (from hand counts), then the range | Repeat-view statistics cannot see fruit buried from every direction, and calibration alone hides how much was actually observed. Each layer is reported. |
| 29 | A crop profile holds the fruit-pass geometry, estimator settings and calibration protocol as well as the models | Tree mapping transfers between crops; where fruit can be seen from does not. |
| 30 | The fruit-mission generator takes a viewpoint template, not a fixed papaya path: pass type (row side pass, over-row oblique, orbit), a list of heights, stand-off distance, tilt, sides | Mango needs side passes at two or three heights around a large canopy; apple needs passes along a flat wall; papaya needs one low pass. One generator, different templates. |
| 31 | Rows are stored records, and an orchard has a planting system: separate trees, or hedgerow or wall | Rows drive mission paths and survey-to-survey alignment for every crop. In hedgerows and apple walls individual trees cannot be separated. |
| 32 | Estimates attach to a counting unit, which is a tree or a row segment | Same reason: wall and hedgerow crops are counted per metre of row. |
| 33 | Fruit are stored as 3D points in the orchard frame; the rule that assigns a fruit to a unit comes from the crop profile (nearest trunk, crown outline, row segment) | "Nearest trunk" is right for papaya and wrong for touching canopies. |
| 34 | The estimator accepts per-unit covariates: crown area, height, canopy volume | In dense-canopy crops the hidden share depends on canopy size; published orange and mango models use tree size as a predictor. |
| 35 | Pass A is also processed into an orthomosaic and a surface height model | Gives tree height, crown width and canopy volume for change 34, better tree positions than GPS alone, and obstacle heights for validating low passes among tall trees. |
| 36 | Captures belong to a sensor stream with its own profile (colour camera now; depth, LiDAR or multispectral later) | Dense canopies are where depth and LiDAR earn their cost. The data model must not assume one colour camera. Nothing beyond colour is built in V1. |
| 37 | The simulator's plant generator is chosen by the crop profile's plant architecture: trunk column, round canopy, or wall. Only trunk column is built in V1 | Otherwise the virtual orchard would have to be rewritten for the second crop. |
| 38 | A schematic 3D view per counting unit: plant shape from the architecture, fruit at measured positions, observed and estimated fruit drawn differently. Photoreal reconstruction and LiDAR hardware are after-V1 options | Gives the interactive 3D tree from data already computed, for every crop, without per-tree GPU reconstruction. |

## 3. Architecture

```
                 BROWSER (React + TypeScript)
     Plan | Fly | Orchards | Analysis | Data | Reports | Settings
                        │ REST          ▲ WebSocket
                        ▼               │ (telemetry, events, job progress)
 ┌──────────────────── BACKEND (FastAPI) ────────────────────┐
 │ Orchard    Mission     Flight      Ingestion   Analysis   │
 │ service    engine      service     service     service    │
 │            (compile,   (owns the   (images +   (jobs)     │
 │            validate)   link)       captures)              │
 └──────┬─────────┬──────────┬───────────┬───────────┬───────┘
        │         │          │           │           │
        │         │    ┌─────▼──────┐    │     ┌─────▼──────┐
        │         │    │ VehicleLink│    │     │   Worker   │
        │         │    └─────┬──────┘    │     │ model      │
        │         │   ┌──────┼───────┐   │     │ registry + │
        │         │   ▼      ▼       ▼   │     │ pipelines  │
        │         │ Kinematic SITL Pixhawk     └─────┬──────┘
        │         │ simulator (MAVLink) (MAVLink)    │
        ▼         ▼          │           ▼           ▼
   PostgreSQL + PostGIS ◄────┴──── File storage (images, logs, weights)
```

The **mission engine** is pure logic: it turns intent into mission items and
validates them. It knows nothing about vehicles. The **flight service** owns the
link to one vehicle and is the only component that sends commands. The
**kinematic simulator** sits behind `VehicleLink` and plays the role of the
autopilot. The **3D scene** in the browser is a renderer of backend state, never
the source of it.

## 4. How it runs, end to end

**Connect.** The flight service opens a link: in-process for the kinematic
simulator, UDP for SITL, a serial telemetry radio or the companion computer's
network link for the Pixhawk. The vehicle sends a heartbeat once a second. The
backend requests telemetry streams, normalises every message into one
`VehicleState`, and broadcasts it to the browser over WebSocket about five times
a second. Three missed heartbeats mark the link as lost.

**Pre-flight.** The checklist is computed, not ticked by hand: GPS fix and
satellite count, battery, home position and estimator health come from
`VehicleState`; mission validated, model loaded and storage free come from the
software; weather and visual inspection are manual confirmations.

**Upload.** The mission revision is compiled to a flat item list and sent with
the MAVLink mission protocol. Geofence, rally points and failsafe parameters go
with it. The backend then reads everything back and compares it with what it
sent. A mismatch blocks the flight.

**Fly.** The operator arms and starts the mission; each command waits for an
acknowledgement. From here the autopilot navigates on its own. The backend does
not steer from waypoint to waypoint; it listens. Position updates draw the
actual track over the planned route, and "item reached" messages drive mission
progress.

**Capture.** The mission tells the autopilot to trigger the camera every N
metres along survey lines. Each trigger produces a capture record with time,
position, altitude, heading and gimbal angle. The record reaches the backend
live; the image itself arrives later.

**Intervene.** Pause, resume, return-to-launch and land are commands with
acknowledgement. If the link is lost, the autopilot applies the failsafe that
was uploaded. The RC pilot can take manual control at any time.

**Land and offload.** On disarm the flight is closed and its log stored. Images
come off the drone (instantly in simulation, by file copy from the companion
computer or SD card in the field). Ingestion matches each image to its capture
record, runs quality checks, stores it and queues processing jobs.

**Analyse.** The worker loads the tree and fruit models for the orchard's crop
from the registry. Tree segmentation runs on nadir images; detections are
projected to ground coordinates using the capture pose and matched to persistent
tree IDs. The tree map generates the fruit-observation mission. Fruit detections
from that pass are linked across views into tracks, and the estimator turns
observed fruit into a total per tree with a confidence interval.

**Report.** Results are written against the survey and appear in analytics and
exports.

In simulation the same sequence runs, with the kinematic simulator or SITL in
place of the Pixhawk and a render client in place of the camera.

## 5. Contracts

### 5.1 Conventions

- Stored positions: WGS84 latitude and longitude in degrees.
- Mission altitudes: metres above the home point. Terrain following is out of V1.
- Local geometry (survey lines, simulator, 3D scene): east-north-up metres from
  the orchard origin, with one shared conversion module on each side of the API.
- Heading: degrees clockwise from true north. Gimbal pitch: 0 is level, -90 is
  straight down.
- Time: UTC with millisecond precision. SI units everywhere.

### 5.2 Entities

```
Crop ── ModelVersion (tree | fruit, per crop, with status)
Orchard (crop, boundary, origin, planting system) ── Row ── Tree (persistent ID, position, height, crown width)
CountingUnit = a Tree, or a RowSegment in hedgerow and wall systems
SensorStream (kind, profile) ── Capture and VideoSegment
Fruit (3D point, size, unit, observed | estimated)
Mission ── MissionRevision (immutable once flown)
Survey (orchard, date) ── Flight (revision, vehicle kind, log)
Flight ── Capture (pose, footprint) ── Image
Image ── TreeDetection ── Tree
Image ── FruitDetection ── FruitTrack ── Tree
Flight ── VideoSegment (file, start time, pose log)
Survey ── CalibrationCount (tree, hand count, counter, date)
Survey ── TreeEstimate (raw count, calibrated total, interval, model versions)
Job (kind, target, state, error)
```

Every AI result stores the model version that produced it.

### 5.3 Mission format

A mission file has two layers. `plan` holds intent: home, survey blocks with
their parameters, hand-placed waypoints, geofence, rally points, safety settings
and the camera profile. `items` is the compiled flat list: takeoff, waypoint,
speed change, camera trigger start and stop, gimbal pitch, return or land.
Compilation is deterministic, validation runs on `items`, and only `items` is
uploaded. The file carries a schema version. Exports: QGroundControl plan,
MAVLink waypoint file, KML.

Survey geometry comes from the camera profile:

```
ground sample distance = sensor width × altitude / (focal length × image width)
line spacing           = footprint width  × (1 − side overlap)
trigger distance       = footprint height × (1 − front overlap)
```

Validation covers: boundary and fence geometry, every item inside the fence,
altitude and speed limits, ground sample distance against the crop's minimum,
estimated flight time and battery against the reserve, storage needed, a return
path from every point, and model availability. A mission that exceeds one
battery is split into flight segments that resume at a known item.

### 5.4 VehicleLink

```
connect / disconnect
state stream   VehicleState: time, position, altitudes, velocity, attitude,
               heading, battery, GPS fix and satellites, mode, armed,
               current mission item
event stream   capture, item reached, mode change, failsafe, status text
upload         mission items, geofence, rally points, parameters; read back
commands       arm, takeoff, start, pause, resume, return, land (acknowledged)
```

Implementations: `KinematicSim` (in-process, deterministic, used by tests),
`MavlinkLink` to SITL, and the same `MavlinkLink` to a Pixhawk.

### 5.5 Capture record

Capture ID, flight ID, time, position, altitude, heading, gimbal pitch, camera
profile, computed ground footprint. Simulated captures add ground truth: the
tree IDs in view and the fruit visible on each. Ingestion accepts a record plus
an optional image file and does not care which kind of vehicle produced them.

The fruit pass produces video. A video segment is ingested with its pose log,
and each frame's pose is interpolated from the log by time. A frame then has the
same fields as a capture record, so everything downstream treats stills and
video frames alike. A ground-captured video with a pose log enters the same way.

### 5.7 Metrics

| Stage | Metrics |
|-------|---------|
| Tree map | Precision, recall, position error in metres |
| Fruit detection | Precision, recall, F1, mean average precision |
| Fruit association | HOTA, IDF1, double-count rate, missed-count rate |
| Per-tree estimate | Mean absolute error, bias, R², percentage error |
| Uncertainty | Share of trees whose true count falls inside the stated interval |

Simulation scores these against generated ground truth; field tests score them
against calibration counts.

### 5.6 Model registry

```
models/<crop>/config.yaml        classes (fruit, cluster, maturity stages),
                                 plant architecture, tree spacing, canopy size,
                                 minimum ground sample distance,
                                 viewpoint template for the fruit pass,
                                 fruit-to-unit assignment rule,
                                 estimator settings and covariates,
                                 calibration protocol,
                                 optional size-to-weight relation
models/<crop>/tree/<version>/    weights + manifest (checksum, input size, metrics)
models/<crop>/fruit/<version>/   weights + manifest
```

Weights stay out of git. The registry is mirrored in the database so an orchard
resolves to crop, then to active model versions. A stub model exists for tests.

## 6. Product structure

```
Dashboard
Plan        nadir survey, fruit observation, custom waypoints, geofence, validation
Fly         live map, telemetry, pre-flight, commands  (same view for sim and real)
Orchards    list, create, boundary, tree map, tree detail  (crop is a field)
Analysis    surveys, tree detection, fruit detection, estimates, uncertainty, coverage
Simulation  virtual orchard setup, camera view, replay, ground-truth scoring
Data        images, flights and logs, missions, jobs
Models      registry, versions, status
Reports     survey, tree and fruit reports, exports
Settings    vehicle, camera profiles, link, safety defaults, maps, system
```

## 7. Phases

Each phase passes the same gate: build, test, demonstrate, document, commit, freeze.

| Phase | Builds | Exit test |
|-------|--------|-----------|
| 0 Viewpoint study (field, runs alongside Phases 1 to 5) | Pole-mounted camera on 15 to 20 papaya trees: heights, angles, one to four sides, stills and video; hand counts of the same trees | A table of fruit visible per viewpoint; the fruit-pass geometry is chosen from it |
| 1 Foundation | Repo, backend, frontend shell, database, WebSocket, logging, registry, conventions module, `VehicleLink` interface | Health check, a WebSocket echo, registry resolves a stub model, coordinate round-trip tests pass |
| 2 Orchards | Create and list orchards, draw boundary, crop and model association | Create a papaya orchard with a boundary; area is computed correctly |
| 3 Mission core | Mission format, survey generator, validation, planner view | Generate a survey over the orchard; overlap and battery checks give expected numbers |
| 4 Flight | Kinematic simulator, flight service, Live Flight view, flight records | The mission flies in simulation; actual track follows the plan; pause and return work |
| 5 Capture and ingestion | Capture records, ingestion, quality checks, job table and worker | Every trigger yields a stored capture; a job runs on each |
| **Milestone A** | Orchard to mission to simulated flight to captures to a ground-truth tree map on screen | Contracts in section 5 are re-reviewed and then frozen |
| 6 Papaya tree model | Existing model behind the registry, results view | Real images produce stored, visible segmentations |
| 7 Tree mapping | Georeferencing, persistent IDs, tree map, tree detail | Simulated survey recovers the virtual trees within a set position error |
| 8 Virtual orchard | 3D scene, tree placement with IDs, camera view, rendered frames into ingestion | Camera view matches the computed footprint |
| 9 SITL | `MavlinkLink`, upload and read-back, failsafe configuration | The Phase 3 mission flies unmodified on the autopilot firmware |
| **Milestone B** | The same mission revision runs on both simulators | |
| 10 Fruit pass | Fruit-observation mission generated from the tree map using the Phase 0 geometry, video ingestion, fruit detection | Each mapped tree is observed from the planned viewpoints; detection is scored on Phase 0 footage |
| 11 Multi-view association | Fruit placed in 3D from posed frames and merged into tracks | Scored against simulator ground truth and Phase 0 hand counts |
| 12 Statistical counting | Raw and calibrated estimates, intervals, calibration workflow | Intervals cover the true count at the stated rate in simulation and on Phase 0 trees |
| 13 Analytics | Orchard, tree and fruit statistics, coverage, maps | |
| 14 Reports | PDF, CSV, JSON, inventories | |
| 15 Polish | Visual effects, transitions, responsive layout | |
| 16 Integration | Full run from orchard creation to report | Software V1 complete |
| Hardware | Bench test with propellers off, hover test, then a field survey | |

No health or disease recommendations in V1.

## 8. Risks

- **Tree identity across flights.** Papaya spacing is about two metres, which is
  the same order as standard GPS error. Persistent IDs need either RTK or
  matching against the row pattern of the existing tree map.
- **Fruit visibility.** If the low oblique pass still hides most fruit, the
  estimate rests on the visibility model, which rests on calibration counts.
  Phase 0 measures this before any software depends on it.
- **Low flight between rows.** The fruit pass may need the drone a few metres
  above ground between trees two to three metres apart. That needs precise
  positioning and an RC pilot ready to take over; ground capture is the fallback.
- **Simulated images.** Real models will perform poorly on rendered frames.
  Simulation validates the system; only real images validate the models.
- **Other crops are harder than papaya.** Dense canopies hide far more fruit
  (mango video tracking saw 62% of the harvest), sloped orchards need terrain
  following (out of V1; mission items carry an altitude-reference field so it
  can be added), and netted apple orchards cannot be flown inside, which makes
  ground capture the route there.
- **Scope.** Ten navigation sections and sixteen phases. Milestone A is the
  guard: nothing is deepened until the thin slice works.
- **Image and capture matching.** Real cameras and autopilots drift in time.
  Matching relies on the autopilot's capture feedback, not on file timestamps.

## 9. Open decisions

1. **Autopilot firmware.** ArduPilot (recommended: mature survey and camera
   trigger support, straightforward SITL) or PX4. Decides the Phase 9 details.
2. **Existing papaya model and data.** Where they live, and whether the images
   are nadir or side views. Decides what Phase 6 can show.
3. **Positioning and camera.** RTK or standard GPS; fixed nadir camera or a
   gimbal. Decides the tree-identity approach and whether one drone can fly both
   passes.
4. **Development database.** Taken in Phase 1: PostgreSQL with PostGIS in
   Docker, the recommended option. See [PHASE_1.md](PHASE_1.md).
5. **Access to a papaya orchard for Phase 0.** Fifteen to twenty fruiting trees,
   a camera on a pole and a day of hand counting. Without it the fruit-pass
   design stays a guess.
6. **Fruit-pass coverage.** Sampled (recommended for whole orchards) or full
   (small blocks). Needed by Phase 10.
7. **Second crop for the paper test.** Before the contracts freeze at
   Milestone A, one dense-canopy crop (mango recommended) is written up as a
   profile and walked through every contract. No code is built for it.
