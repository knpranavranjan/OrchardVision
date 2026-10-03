# OrchardVision — Prior Work and Differentiation

Searched 2 October 2026 through Consensus, PubMed and the open web (arXiv, IEEE
Xplore, MDPI, ScienceDirect, Springer, vendor sites). This is a scan, not a
systematic review: "none found" means none surfaced in these searches.

## 1. What has already been done

### 1.1 Tree detection and mapping from UAV images — mature

- Citrus trees counted and geolocated from multispectral UAV images, 37,353
  trees, F1 0.95 ([Osco 2020](https://consensus.app/papers/details/65725742de1a54b6a25d6a95e99b8106/?utm_source=claude_desktop)).
- Banana plants: 96.4% detected at 40 m, 85.1% at 50 m, 75.8% at 60 m; merging
  two altitudes reached 99% recall ([Neupane 2019](https://consensus.app/papers/details/5e25e4937abf527bbdb7abae010b5768/?utm_source=claude_desktop)).
- Palm trees detected and geolocated on board during flight: 0.2% count error,
  2.14 m average position error ([Mazinani 2026](https://consensus.app/papers/details/9df7e8f796505ff992babd62fbef886c/?utm_source=claude_desktop)).
- Citrus tree and row segmentation with a small U-Net, plus yield regression
  from vegetation indices ([Bakas 2025](https://consensus.app/papers/details/2b843e80ff6f575195c6fbb70bb6d593/?utm_source=claude_desktop)).
- Pomelo trees with YOLOv5 ([Xiong 2024](https://consensus.app/papers/details/fe105c26f3205942b2a92b6ae7ce3d49/?utm_source=claude_desktop)).
- **Papaya trees specifically:** scale-space filtering on UAV images
  ([Jiang 2017](https://www.researchgate.net/publication/318415591_Papaya_Tree_Detection_with_UAV_Images_Using_a_GPU-Accelerated_Scale-Space_Filtering_Method));
  crown area and plant number from very-high-resolution UAV images
  ([Agronomy 2024](https://doi.org/10.3390/agronomy14030636)); a UAV dataset of
  intercropped durian and papaya trees, 2,872 labelled papaya tree images
  (InterDuPa-UAV, PubMed, [DOI](https://doi.org/10.1016/j.dib.2025.111843)).

### 1.2 Fruit counting from UAV images — done for canopy-surface fruit

- Apple: fruit counted per tree on an orthomosaic, R² 0.86 against visible
  fruit; because only part of the fruit is visible from above, total count
  needed a regression, R² 0.80 (PubMed, [DOI](https://doi.org/10.3389/fpls.2020.01086)).
- Citrus: 20 trees over three seasons, yield error 4.53% per tree after an LSTM
  model ([Apolo-Apolo 2020](https://consensus.app/papers/details/7d15a27dba6d527aa8e2559011a02a6d/?utm_source=claude_desktop)).
- Longan: UAV video of the canopy, detected count regressed against manual
  count, about 3% error (PubMed, [DOI](https://doi.org/10.3389/fpls.2023.1132909)).
- Orange: public UAV dataset at 14 m, 301,232 annotated fruit
  (PubMed, [DOI](https://doi.org/10.1016/j.dib.2026.112733)).
- Apple from monocular UAV video with motion-compensated DeepSORT: counting
  accuracy 85.6% to 93.5% ([Agriculture 2026](https://www.mdpi.com/2077-0472/16/19/2109)).
- **Closest to our fruit pass:** a UAV flying through the canopy rather than
  above it, with a simulation framework used to optimise the trajectory
  ([Yang 2024](https://arxiv.org/abs/2409.18293)).

### 1.3 Avoiding double counts — mostly ground vehicles

- Mango, ground vehicle with LiDAR tree masks and triangulation: 1.36% per-tree
  error without calibration ([Stein 2016](https://consensus.app/papers/details/37e68a1a2ac056eabb19ed63dc58e53b/?utm_source=claude_desktop)).
- Mango video tracking saw 62% of harvested fruit; two still views saw 40%
  ([Wang 2019](https://consensus.app/papers/details/3e39242ec59552fb8acd62ed4712ca69/?utm_source=claude_desktop)).
- Orange: tracking with 3D relocalisation plus a yield regressor, R² 0.85,
  usable once 30% of fruit is tracked; public tracking dataset MOrangeT
  ([Santos 2024](https://consensus.app/papers/details/7505a1f09c2c5482a2f7628ec0c41fc8/?utm_source=claude_desktop)).
- Apple video with ByteTrack, 7.47% error ([Gené-Mola 2023](https://consensus.app/papers/details/dfcbc0d7e5b05784954614a2ba03b3f3/?utm_source=claude_desktop));
  stereo with georeferenced 3D positions, RMSE 6.24%
  ([Wei 2025](https://consensus.app/papers/details/9dabacd1b91b5ae6b64df223c0313766/?utm_source=claude_desktop)).
- Counting in 3D from posed images with no tracker at all
  ([FruitNeRF 2024](https://consensus.app/papers/details/b58db284c63b5e6aae50a47ed973e5b0/?utm_source=claude_desktop),
  [FruitNeRF++](https://arxiv.org/abs/2505.19863)).

### 1.4 Hidden fruit and calibration

- Per-tree correction models reached R² 0.98 within a season but did no better
  than a plain manual factor in the next season
  ([Koirala 2021](https://consensus.app/papers/details/6e47e62d24445e11999aa93b41c079f2/?utm_source=claude_desktop)).
- Across nine mango orchards, raw multi-view counts averaged 11% error and
  calibrated counts 17%; calibration used 18 hand-counted trees stratified by
  vigour ([Anderson 2021](https://consensus.app/papers/details/f5e3868925755bf3b7eef0798bbe81ce/?utm_source=claude_desktop)).
- Manual sampling needs 20 to 156 trees for a 90% interval at 10% error,
  depending on orchard variability ([Anderson 2021, review](https://doi.org/10.3390/agronomy11071409)).
- A 2026 review concludes ground platforms suit fine fruit counting and UAVs
  suit regional mapping, and names occlusion-aware perception as the open
  problem (PubMed, [DOI](https://doi.org/10.3389/fpls.2026.1879872)).

### 1.5 Papaya fruit

- On-tree papaya detection by maturity stage from ground photos, mAP 0.95
  ([Prabhu 2025](https://consensus.app/papers/details/5075c45250985749a4ae1f735793fafb/?utm_source=claude_desktop)).
- A 1,840-image dataset of papaya fruit bunches from Bangladeshi fields
  ([Springer 2026](https://link.springer.com/article/10.1007/s11042-026-21350-2)).
- Fruit disease detection, 17,949 images, academic use only
  ([Yolo-Papaya](https://github.com/jhony2507/Sisfrutos-Papaya)).
- Most other papaya vision work is leaf disease classification
  (for example PubMed, [DOI](https://doi.org/10.1038/s41598-025-25374-w)).
- **None found:** papaya fruit counted per tree from a UAV, with multi-view
  association, or with an uncertainty estimate.

### 1.6 Simulation and ground control

- Agricultural UAV simulator with orchard scenes, PX4 control and camera
  streams ([Droneulator 2026](https://arxiv.org/abs/2605.23386)).
- SITL plus Gazebo digital twins to optimise survey flight plans
  ([Drones 2025](https://doi.org/10.3390/drones9060407)).
- AirSim and Unreal apple orchard for adaptive path planning
  ([arXiv 2402.04894](https://arxiv.org/abs/2402.04894)).
- Web-based open-source ground station ([IEEE 2024](https://ieeexplore.ieee.org/document/10556987/));
  automated planning added to QGroundControl ([Sensors 2018](https://pmc.ncbi.nlm.nih.gov/articles/PMC6068744/)).
- **None found:** a simulator whose captures feed the production analysis
  pipeline and score the fruit estimate against ground truth.

### 1.7 Commercial products

- Aerobotics: drone imagery to per-tree health, count and canopy data.
- Outfield: drone surveys counting blossom and apples.
- Green Atlas Cartographer: ground vehicle with LiDAR and cameras, per-tree
  fruit count typically within 5%.
- All are closed, target temperate or citrus crops, and none surfaced for papaya.
  ([Good Fruit Grower](https://goodfruit.com/down-to-earth-with-drones/),
  [Cambridge](https://www.eng.cam.ac.uk/news/predicting-fruit-harvest-drones-and-artificial-intelligence),
  [Green Atlas](https://www.innov8.ag/products/greenatlas/),
  [HIN](https://www.hin.com.au/networks/profitable-stonefruit-research/Towards-Precision-Management-in-Summerfruit))

## 2. How differentiated OrchardVision is

| Part of OrchardVision | Status in the literature | Differentiated? |
|---|---|---|
| Tree detection and mapping from nadir UAV images | Mature, including papaya | No |
| YOLO-style fruit detection | Mature, including papaya from the ground | No |
| Video tracking to avoid double counts | Mature on ground vehicles, emerging on UAVs | No |
| Survey mission planning, geofence, telemetry | QGroundControl and Mission Planner do it | No |
| UAV and orchard simulation | Several research simulators | No |
| Papaya fruit count per tree from a UAV | None found | **Yes** |
| Tree map automatically generating a per-tree fruit observation mission | One nearby paper (through-canopy flight) | **Partly** |
| Per-tree count with a stated interval, checked for coverage | Papers report R² and percentage error, rarely intervals | **Yes** |
| One mission and one pipeline across simulator, SITL and real drone, scored against ground truth | Pieces exist separately | **Yes, as engineering** |

The individual components are known. The contribution is papaya, the closed
loop from tree map to fruit mission, and honest uncertainty. Papaya also has a
structural advantage the mango and citrus work lacks: one unbranched trunk with
fruit in a column below the crown, so side views meet little foliage and the
main occlusion is fruit behind fruit and the far side of the trunk.

## 3. Improvements adopted in plan v1.1

1. Phase 0 viewpoint study with a camera on a pole, before any mission design.
2. Fruit pass records video with a pose log; association is done in 3D.
3. Raw and calibrated counts are both reported; calibration is per survey.
4. Standard metrics for every stage, shared by simulation and field tests.
5. Tree identity uses row-pattern registration, not GPS alone.
6. Nadir altitude is a tested parameter, not a fixed 25 m.
7. The planner is narrowed to three mission types.
8. Public datasets are used for pretraining and benchmarking.
9. Ground-captured video is accepted as a fallback for the fruit pass.
