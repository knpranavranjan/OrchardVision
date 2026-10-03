# OrchardVision — Tools and Cost Estimate (papaya, V1)

Prepared 2 October 2026. Prices are in Indian rupees from Indian retailer
listings found that day; rows marked "est." are estimates, not listings. Prices
vary a lot between sellers, so each row is a range.

## 1. Software tools — all free

| Purpose | Tool | Used in |
|---|---|---|
| Backend language and packaging | Python, uv | All phases |
| Web API and live channel | FastAPI, Uvicorn, WebSockets | Phase 1 |
| Database | PostgreSQL with PostGIS, in Docker Desktop | Phase 1 |
| Database access and migrations | SQLAlchemy, Alembic, GeoAlchemy2 | Phases 1–2 |
| Front end | Node.js, Vite, React, TypeScript | Phase 1 |
| 2D map | MapLibre GL | Phase 2 |
| 3D scene | Three.js | Phase 8 |
| Geometry | Shapely, pyproj | Phase 3 |
| Drone protocol | pymavlink | Phase 9 |
| Software autopilot | ArduPilot SITL, in Docker | Phase 9 |
| Drone setup and tuning | QGroundControl or Mission Planner | Hardware stage |
| Model training and inference | PyTorch, plus the framework of the existing papaya model | Phases 6, 10 |
| Stitched map and height model | OpenDroneMap, in Docker | Phase 7 |
| Image and video labelling | CVAT or Label Studio | Phases 0, 10 |
| Tests | pytest, Vitest, Playwright | All phases |
| Version control | Git, GitHub (free plan) | All phases |
| Reports | WeasyPrint or headless Chrome | Phase 14 |

Two things to know:

- **Ultralytics YOLO is AGPL-licensed.** If the fruit or tree model uses it and
  OrchardVision is ever sold as closed software, an Ultralytics commercial
  licence or a different detector is needed. For research and a student project
  it is free.
- **Map imagery has terms of use.** Satellite tiles for the planner come from a
  provider's free tier and must be cached for offline field use within its terms.

## 2. Computer — already owned

The development machine (Ryzen 9 9950X, 62 GB memory, RTX 5080 with 16 GB) is
more than enough for development, simulation, model training and 3D
reconstruction. No cloud GPU is needed.

A **field laptop** is needed later to run the ground station beside the drone.
Any recent laptop works, because the heavy analysis runs back on the desktop.

## 3. Hardware by stage

### Stage A: software development (Phases 1–9) — ₹0

Nothing to buy. Everything runs in simulation.

### Stage B: Phase 0 viewpoint study — about ₹3,000 to ₹8,000

| Item | Cost |
|---|---|
| Camera | A phone that records 4K video (already owned) |
| Telescopic pole, 3 to 5 m, with phone mount (est.) | ₹1,500–4,000 |
| Tree tags, measuring tape, size reference card, notebook (est.) | ₹1,000–2,000 |
| Travel and a day in the orchard | varies |

### Stage C: the drone (after Software V1)

| Item | Choice | Cost |
|---|---|---|
| Frame, motors, speed controllers, propellers | Holybro X500 V2 ARF kit | ₹33,500–44,000 |
| Flight controller, power module, standard GPS (est.) | Pixhawk 6C set | ₹20,000–28,000 |
| Telemetry radio | SiK 433 MHz | ₹3,900–6,500 |
| Remote control | RadioMaster Boxer ELRS | ₹14,900–18,000 |
| Remote control receiver (est.) | ELRS receiver | ₹1,500–2,500 |
| Batteries, three | 4S 5200 mAh | ₹14,500–21,000 |
| Charger and safety bag (est.) | Balance charger | ₹4,000–8,000 |
| On-board computer | Raspberry Pi 5, 8 GB | ₹7,000–8,500 |
| Storage, cooling, power regulator for the Pi (est.) | | ₹3,000 |
| Fruit-pass camera | Raspberry Pi Global Shutter Camera | ₹4,500–8,500 |
| Lens for it (est.) | 6 mm CS-mount | ₹2,000–3,500 |
| Overhead camera, optional (est.) | Raspberry Pi HQ Camera with lens | ₹7,000–10,000 |
| Camera mounts, spare propellers, connectors, landing pad (est.) | | ₹6,000–10,000 |
| **Drone total without RTK** | | **about ₹1.2–1.7 lakh** |

### Stage D: optional precise positioning

| Option | Items | Extra cost |
|---|---|---|
| RTK with a correction service | Here4 receiver on the drone, corrections over the internet | ₹25,000–42,000 |
| RTK with own base station | Here4 on the drone plus an H-RTK F9P base | ₹84,000–1.44 lakh |

Whether RTK is needed is decided by Phase 0: it is required for autonomous low
flight between rows, and not required if a higher, safer viewpoint sees the fruit.

### Field laptop, if none is available

About ₹45,000–70,000 (est.).

## 4. Totals

| Scenario | Total |
|---|---|
| Software V1 only, in simulation | ₹0 |
| Plus Phase 0 field study | ₹3,000–8,000 |
| Plus drone, standard GPS | about ₹1.25–1.8 lakh |
| Plus RTK with correction service | about ₹1.5–2.2 lakh |
| Plus RTK with own base station | about ₹2.1–3.2 lakh |

There are no required recurring costs. Everything runs on your own machines.

## 5. Why these camera choices

- **Global shutter for the fruit pass.** The whole frame is exposed at once, so
  video taken while moving past a trunk is not skewed. At 2 m with a 6 mm lens a
  pixel covers about 1.2 mm, so a 15 cm papaya is about 130 pixels long.
- **The same camera can do the overhead pass.** At 25 m a pixel covers about
  1.4 cm and a two-metre crown is about 140 pixels across, enough for tree
  detection. Each photo covers only about 20 m of ground, so there are more
  flight lines. The optional 12-megapixel camera covers more ground per photo.

## 6. Rules to check before flying (India)

- A drone between 250 g and 2 kg is in the micro class and must be registered on
  the Digital Sky platform for an identification number.
- Non-commercial micro-drone flying is reported as exempt from the remote pilot
  certificate; commercial use is not.
- Recognised research and academic bodies flying on their own premises in a
  green zone have further exemptions.
- A self-built drone raises type-certification questions. Confirm the current
  position with the DGCA rules or your institution before the hardware stage.

## 7. Sources

Recheck prices at purchase time.

- [Holybro X500 V2 ARF kit, IndiaMART](https://www.indiamart.com/proddetail/holybro-x500-v2-arf-kit-2854160549497.html)
- [Holybro X500 V2 ARF kit, MG Super Labs](https://www.mgsuperlabs.co.in/estore/Holybro-X500-V2-ARF-Kit)
- [Holybro X500 V2 ARF kit, Indian Hobby Center](https://www.indianhobbycenter.com/products/holybro-x500-v2-almost-ready-to-fly-arf-drone-kit)
- [Holybro H-RTK F9P base station, Robu](https://robu.in/product/holybro-h-rtk-f9p-base-station/)
- [Here4 multiband RTK, Zbotic](https://zbotic.in/product/here4-multiband-rtk-gnss-gps-module/)
- [Here4 multiband RTK, IndiaMART](https://www.indiamart.com/proddetail/here4-multiband-rtk-gps-receiver-2854743125555.html)
- [Raspberry Pi 5 price guide, ThinkRobotics](https://thinkrobotics.com/blogs/product-reviews-buying-guides/raspberry-pi-5-price-india-complete-cost-analysis-and-buying-guide)
- [Raspberry Pi Global Shutter Camera, Robocraze](https://robocraze.com/products/raspberry-pi-global-shutter-camera)
- [Raspberry Pi Global Shutter Camera, Silverline](https://www.silverlineelectronics.in/products/raspberry-pi-global-shutter-camera)
- [RadioMaster Boxer ELRS, ElectronicsComp](https://www.electronicscomp.com/radiomaster-boxer-24ghz-radio-controller-elrs-version)
- [RadioMaster Boxer ELRS, fpvstore](https://fpvstore.in/product/radiomaster-boxer-radio-controller-m2-elrs/)
- [SiK telemetry radio, Robocraze](https://robocraze.com/products/simplifly-sik-telemetry-radio-100-mw-433-mhz)
- [Holybro SiK telemetry radio V3, Zbotic](https://zbotic.in/product/holybro-sik-telemetry-radio-v3-500mw-433-mhz/)
- [Tattu 5200 mAh battery, IndiaMART](https://www.indiamart.com/proddetail/tattu-5200mah-drone-battery-2851627828573.html)
- [DGCA drone rules guide 2026, Zbotic](https://zbotic.in/dgca-drone-rules-india-2026-registration-license-guide/)
- [India drone laws 2026](https://drone-laws.com/drone-laws-in-india/)
