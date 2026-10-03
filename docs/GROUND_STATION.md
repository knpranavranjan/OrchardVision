# OrchardVision Ground Station

Built and verified on 3 October 2026. This is the first of three sections:
ground station (this), model training and integration (next), 3D simulation (after).

## 1. What it is

A browser application that connects to a drone, plans a flight over an orchard,
checks that it is safe to fly, flies it by hand or automatically, and records
everything. The same screens drive three kinds of vehicle:

| Vehicle | What it is | Tested |
|---|---|---|
| Built-in simulator | A virtual drone inside OrchardVision | Yes, automatically and in the browser |
| Software autopilot (SITL) | The real ArduPilot Copter flight code running on this computer | Yes, a full mission from the browser |
| Real drone | A Pixhawk running ArduPilot Copter, over USB, telemetry radio or network | **Not yet. No hardware has been connected.** |

The link to a real drone is the same code that flew the software autopilot; only
the address differs. That is strong evidence, not proof. The first real
connection must be done with the propellers removed.

## 2. The screens

| Screen | What you do there |
|---|---|
| **Fly** | Live map, instruments, pre-flight checklist, commands, manual control, event log |
| **Plan** | Draw the survey area and geofence, set the survey, see the estimate and validation, save, upload |
| **Orchards** | Create orchards, draw boundaries, choose the crop and its models |
| **Flights** | Every recorded flight, with map, charts, events, replay and a capture log |
| **Simulate** | Rehearse a saved mission on the virtual drone, with a chosen failure |
| **Models** | The crop profiles and model versions, and which orchard uses which |
| **Settings** | Safety limits, emergency actions, drone and camera profiles, connection defaults |

Screenshots of each are in [screens/](screens/).

### Map tools, on every map

Three buttons sit above the zoom controls.

| Button | What it does |
|---|---|
| **Search** | Type an address or place and press Enter. Matches are listed; choosing one moves the map there, drops a pin and shows its full address, type and coordinates, with a copy button. Typing `latitude, longitude` goes straight there. |
| **Show my location** | Asks the browser for this device's position, moves the map there, marks it with a blue dot and an accuracy circle, and shows the address. |
| **Layers** | Switches between satellite and street map. |

On the Plan screen the place card has a **Set the take-off point here** button,
so you can find your field, set home, and draw the survey around it.

Two things to know:

- **Address search needs internet.** The backend looks the text up with
  OpenStreetMap's Nominatim service, so what you type is sent to that service.
  It searches only when you press Enter, at most once a second, and caches
  results. Typed coordinates never leave the computer.
- **"My location" is only as good as the device.** A desktop or laptop without
  GPS gets its position from the network, which can be kilometres off. The card
  states the accuracy and warns when it is poor. In the field, use a device with
  GPS, or search for the address.

## 3. What you asked for, and where it is

| Requirement | Where | Status |
|---|---|---|
| Connect my drone | Connection dialog (top left): simulator, software autopilot, USB or radio, network | Built; real hardware untested |
| Mark the area for flying | Plan: draw the survey area and the geofence on the map | Built |
| Autonomous flying | Plan a mission, upload, hold Arm, hold Start | Built; flown on simulator and ArduPilot SITL |
| Manual flying | Fly → Manual: hold a direction button or use the keyboard; also "Fly to point" | Built as assisted flying (see section 7) |
| Model selection | Orchards: crop, and a tree and fruit model version per orchard | Built; only placeholder models exist |
| Flight control | Fly: Arm, Take off, Start, Pause, Resume, Hold, Return home, Land | Built |
| Simulation planner | Simulate: mission, speed, battery, wind, failure and when it happens | Built |
| Everything recorded | Flights: telemetry, events, photo positions, summary, replay, CSV | Built |

### The pre-flight checklist

Every item is computed from live data except the four operator items.

| Your list | Check in the software | How it is decided |
|---|---|---|
| Drone connected | Drone connected | The link is up |
| Flight controller connected | Flight controller responding | Telemetry arrived in the last three seconds |
| GPS available | GPS position | A 3D fix or better |
| GPS accuracy | GPS accuracy | At least 8 satellites and HDOP of 2.0 or less |
| Battery | Battery | Above the warning level, and enough for this mission plus the reserve |
| RC connection | Remote control | The autopilot reports a receiver signal |
| Telemetry connection | Telemetry rate | At least two updates a second |
| Camera connected | Camera | **A warning on a real drone:** camera status is not read over the link yet |
| Storage available | Storage | Free disk space is at least twice what the mission's photos need |
| AI model loaded | AI models | The orchard's tree and fruit models exist and pass their checksums |
| Home position | Home position | The autopilot has set home |
| Geofence configured | Geofence | The fence is on the vehicle |
| Mission validated | Mission validated, Mission on the vehicle | Validation passed; the upload was read back and matched |
| Weather / manual check | Weather, Airspace and permission, Airframe and propellers, Safety pilot | Confirmed by the operator; cleared after every flight |
| Emergency settings | Emergency settings | The failsafe settings were confirmed by the vehicle |
| (added) | Position estimator | The autopilot's estimator is healthy |
| (added) | Flight recording | The database is reachable |

Arming is refused until every item passes. An operator can override; the
override is written into the flight record.

## 4. How a flight works

1. **Connect.** The backend opens the link and waits for a heartbeat. Telemetry
   is turned into one common record and pushed to the browser five times a second.
2. **Plan.** You draw an area. The mission engine works out the photo footprint
   from the camera profile, lays parallel lines so photos overlap, and compiles a
   flat list of items: take off, go to point, camera on, camera off, return.
3. **Validate.** Area and fence geometry, every route point inside the fence,
   height and speed limits, image detail against the crop's requirement, camera
   interval, time and battery against the reserve, storage, item count, models.
   A mission too long for one battery is split into flights.
4. **Upload.** Emergency settings, then the geofence, then the items. The items
   are read back from the vehicle and compared one by one.
5. **Pre-flight.** The checklist above.
6. **Arm and start.** Both are hold-to-confirm buttons, so a stray click cannot
   start the motors.
7. **Fly.** The autopilot navigates by itself. The ground station shows the
   planned route, the actual track, each photo position and mission progress.
   Pause, Return home and Land are single clicks, because safety actions must be fast.
8. **Land.** On disarm the flight record closes with its summary.

## 5. Safety design

- **The autopilot is the safety authority.** Geofence and failsafe actions are
  uploaded to it and it carries them out even if the link is down.
- **Read-back before flight.** A mission that does not read back identical
  cannot be started.
- **Link watchdog.** No telemetry for three seconds marks the link lost, with an
  alarm in the status bar and a critical entry in the log.
- **Ground battery failsafe.** ArduPilot's own battery failsafe is set by voltage,
  which this software does not configure. So while the link is up, the ground
  station also commands the battery action when the reported charge reaches the
  critical level. Set the autopilot's voltage failsafe as well, in QGroundControl
  or Mission Planner.
- **Manual input stops by itself.** Stick input is sent five times a second while
  a button is held. When it stops, the vehicle stops and holds.
- **Disconnect is refused in the air.**
- **Works without the database.** Flying continues; the checklist warns that the
  flight will not be recorded.

## 6. Connecting a real drone

Requirements: a Pixhawk-class flight controller running **ArduPilot Copter**,
already set up and tuned with QGroundControl or Mission Planner (frame type,
sensor calibration, radio calibration, battery monitor, camera trigger).

1. Remove the propellers.
2. Plug in the USB cable or the telemetry radio.
3. Open the connection dialog, choose **Drone by USB or radio**, pick the port.
   Use 115200 for USB and 57600 for a SiK radio.
4. Check that height, attitude, GPS and battery on the Fly screen match reality.
   Tilt the drone by hand and watch the horizon move the right way.
5. Upload a small mission and confirm the read-back passes.
6. Arm with the propellers still off and check the motors respond; disarm.
7. Only then fit the propellers, outdoors, with a pilot holding the remote control.

For a companion computer or Wi-Fi bridge, choose **Drone by network**. The
default address listens on UDP port 14550.

## 7. Known limits

| Limit | What it means |
|---|---|
| No real hardware tested | Everything real-drone is verified only against ArduPilot SITL |
| ArduPilot Copter only | PX4 is not supported |
| Camera status not read | The checklist can only warn; photo events appear only if the autopilot sends camera feedback, which needs the camera configured in ArduPilot. In the SITL run no photos were logged for this reason |
| No live video | Not in this version |
| Manual control is assisted | Velocity commands in the autopilot's guided mode, not raw stick input. No joystick support. The remote control remains the true manual backup |
| Battery failsafe thresholds | Set on the autopilot separately (see section 5) |
| Map needs internet the first time | Tiles are not yet packaged for offline use |
| Mission split | Each flight is uploaded separately; resuming mid-line after a battery swap is not built |
| No rally points, no terrain following | Heights are relative to the take-off point |
| No user accounts | It is a single-operator application on one computer |
| Fruit-observation missions | Need the tree map, which arrives with the model section |
| Simulator physics are simple | It tests logic and procedure, not flight dynamics; use SITL for that |
| Vehicle setup | Firmware, calibration and tuning stay in QGroundControl or Mission Planner |
| 21st.dev sketches not used | The 21st CLI was not signed in, so the interface was designed directly from the ui-ux-pro-max design system |

## 8. How it was verified

| Check | Result |
|---|---|
| Backend tests | 63 pass: coordinates, geometry, survey planner, compiler, validation, exports, simulator, registry, API, flight recording, operation without a database |
| Front-end tests | 18 pass; type check, lint and build clean |
| Browser run, simulator | Creates an orchard by clicking the map, plans a survey, rehearses it, holds Arm and Start, pauses, flies by hand, restarts, lands, opens the record. No browser errors |
| Browser run, ArduPilot SITL | Connects through the dialog, uploads with read-back, confirms operator checks, arms, flies the survey, returns, lands, records |
| Direct MAVLink test | Upload, read-back comparison, fence, settings, arm, mission, pause, resume, landing, all against ArduPilot SITL |

Things found and fixed along the way: ArduPilot 4.7 renamed the return-height
setting; ArduPilot stays in AUTO for a mission's final return rather than
switching mode; the map library needs its worker file served separately; fast
simulations recorded too few track points until the simulator got its own clock.

## 9. Architecture

```
Browser (React)  ── REST ──►  FastAPI backend
       ▲                          │
       └──── WebSocket ───────────┤  flight manager: link, checklist, upload, commands, recorder
                                  │
                              VehicleLink ──► built-in simulator
                                  │      └──► MAVLink ──► ArduPilot SITL or Pixhawk
                              PostgreSQL: orchards, missions, flights, telemetry, events, captures
```

- `backend/app/vehicle/link.py` — the one interface every drone implements
- `backend/app/vehicle/sim.py` — the built-in simulator
- `backend/app/vehicle/mavlink.py` — ArduPilot over MAVLink 2
- `backend/app/mission/` — plan format, survey planner, compiler, validation, exports
- `backend/app/flight/` — flight manager, pre-flight checklist, recorder
- `frontend/src/pages/` — the seven screens

## 10. Next sections

1. **Model training and integration.** Phase 0 field study, the papaya tree and
   fruit models, the image pipeline, tree mapping, the fruit-observation mission.
2. **Simulation.** The 3D virtual orchard with known fruit counts, the virtual
   camera, and scoring the counting pipeline against the truth.
