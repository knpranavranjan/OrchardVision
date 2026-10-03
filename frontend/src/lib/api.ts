/** Types and calls for the backend API. Field names match the backend exactly. */

export interface LatLon {
  lat: number
  lon: number
}

export type FlightMode =
  | 'standby'
  | 'takeoff'
  | 'auto'
  | 'hold'
  | 'guided'
  | 'manual'
  | 'rtl'
  | 'land'
  | 'unknown'

export interface VehicleState {
  time: string
  lat: number
  lon: number
  alt_rel_m: number
  alt_amsl_m: number | null
  vel_north_mps: number
  vel_east_mps: number
  vel_up_mps: number
  groundspeed_mps: number
  roll_deg: number
  pitch_deg: number
  heading_deg: number
  gimbal_pitch_deg: number
  battery_pct: number | null
  battery_v: number | null
  battery_a: number | null
  gps_fix: 'none' | '2d' | '3d' | 'dgps' | 'rtk_float' | 'rtk_fixed'
  satellites: number
  hdop: number | null
  mode: FlightMode
  mode_raw: string
  armed: boolean
  in_air: boolean
  mission_seq: number | null
  mission_count: number
  wp_dist_m: number | null
  home_lat: number | null
  home_lon: number | null
  rc_ok: boolean | null
  ekf_ok: boolean | null
  captures: number
}

export type Severity = 'info' | 'warning' | 'critical'

export interface VehicleEvent {
  time: string
  kind: string
  severity: Severity
  message: string
  data: Record<string, unknown>
}

export type FailsafeAction = 'rtl' | 'land' | 'hold'

export interface SafetyConfig {
  max_alt_m: number
  min_alt_m: number
  max_speed_mps: number
  rtl_alt_m: number
  battery_warn_pct: number
  battery_crit_pct: number
  battery_reserve_pct: number
  on_battery_critical: FailsafeAction
  on_link_loss: FailsafeAction
  on_gps_loss: FailsafeAction
  on_fence_breach: FailsafeAction
  fence_enabled: boolean
}

export interface CameraProfile {
  id: string
  name: string
  sensor_width_mm: number
  sensor_height_mm: number
  focal_length_mm: number
  image_width_px: number
  image_height_px: number
  image_mb: number
}

export interface VehicleProfile {
  name: string
  cruise_speed_mps: number
  max_speed_mps: number
  climb_rate_mps: number
  descent_rate_mps: number
  endurance_min: number
  turn_time_s: number
}

export interface SurveySpec {
  polygon: LatLon[]
  altitude_m: number
  speed_mps: number
  front_overlap: number
  side_overlap: number
  angle_deg: number
  gimbal_pitch_deg: number
  overshoot_m: number
}

export interface WaypointSpec {
  lat: number
  lon: number
  alt_m: number
  hold_s: number
  speed_mps: number | null
}

export interface MissionPlan {
  type: 'survey' | 'waypoints'
  home: LatLon
  takeoff_alt_m: number
  survey: SurveySpec | null
  waypoints: WaypointSpec[]
  waypoint_speed_mps: number
  waypoint_capture_distance_m: number
  waypoint_gimbal_pitch_deg: number
  geofence: LatLon[]
  end_action: 'rtl' | 'land'
  safety: SafetyConfig
  camera: CameraProfile
  vehicle: VehicleProfile
}

export interface MissionItem {
  seq: number
  kind: string
  lat: number | null
  lon: number | null
  alt_rel_m: number | null
  value: number
}

export interface MissionStats {
  area_ha: number
  distance_m: number
  time_s: number
  battery_pct: number
  photos: number
  storage_mb: number
  gsd_cm: number | null
  footprint_across_m: number | null
  footprint_along_m: number | null
  line_spacing_m: number | null
  trigger_distance_m: number | null
  lines: number
  max_alt_m: number
  item_count: number
  flights_needed: number
}

export type CheckStatus = 'pass' | 'warn' | 'fail' | 'pending'

export interface ValidationCheck {
  id: string
  label: string
  status: CheckStatus
  detail: string
}

export interface Segment {
  index: number
  first_line: number | null
  last_line: number | null
  item_count: number
  estimate: { distance_m: number; time_s: number; battery_pct: number; photos: number }
}

export interface Evaluation {
  items: MissionItem[]
  route: [number, number, number][]
  lines: [[number, number], [number, number]][]
  capture_points: [number, number][]
  stats: MissionStats
  segments: Segment[]
  validation: { ok: boolean; checks: ValidationCheck[] }
}

export interface MissionSummary {
  id: number
  name: string
  orchard_id: number | null
  type: 'survey' | 'waypoints'
  revision: number
  valid: boolean
  stats: MissionStats
  created_at: string
  updated_at: string
}

export type MissionDetail = MissionSummary & Evaluation & { plan: MissionPlan }

export interface Orchard {
  id: number
  name: string
  crop: string
  boundary: LatLon[]
  area_ha: number
  notes: string
  tree_model_version: string | null
  fruit_model_version: string | null
  models_ready: boolean
  models_detail: string
}

export type OrchardInput = Pick<
  Orchard,
  'name' | 'crop' | 'boundary' | 'notes' | 'tree_model_version' | 'fruit_model_version'
>

export interface CropProfile {
  crop: string
  name: string
  plant_architecture: string
  tree_spacing_m: number
  crown_diameter_m: number
  min_gsd_cm: Record<string, number>
  active: Record<string, string>
  viewpoint_template: { pass_type: string; provisional: boolean }
}

export interface ModelRow {
  crop: string
  kind: 'tree' | 'fruit'
  version: string
  framework: string
  status: 'active' | 'available' | 'missing' | 'checksum_mismatch'
  sha256: string
  metrics: Record<string, number>
  notes: string
}

export interface PreflightCheck {
  id: string
  group: string
  label: string
  status: CheckStatus
  detail: string
  manual: boolean
}

export interface Preflight {
  ready: boolean
  blocking: string[]
  checks: PreflightCheck[]
}

export interface ActiveMission {
  mission_id: number
  name: string
  revision: number
  segment: number
  segments: number
  item_count: number
  verified: boolean
  fence_uploaded: boolean
  fence_points: number
  safety_applied: boolean
  valid: boolean
  battery_pct: number
  safety: SafetyConfig
}

export interface SimOptions {
  home_lat: number
  home_lon: number
  speedup: number
  battery_start_pct: number
  endurance_min: number
  wind_mps: number
  wind_from_deg: number
  gps_noise_m: number
}

export type LinkStatus = 'disconnected' | 'connecting' | 'connected' | 'lost'

export interface VehicleSummary {
  link: LinkStatus
  kind: 'sim' | 'sitl' | 'pixhawk' | null
  description: string
  flying: boolean
  flight_id: number | null
  last_flight_id: number | null
  recording: boolean
  mission: ActiveMission | null
  preflight: { ready: boolean; blocking: string[] }
  sim: SimOptions | null
}

export interface MissionGeometry {
  route: [number, number, number][]
  geofence: [number, number][]
  area: [number, number][]
}

export interface VehicleSnapshot extends VehicleSummary {
  mission_geometry: MissionGeometry | null
  state: VehicleState | null
  events: VehicleEvent[]
}

export interface CommandResult {
  accepted: boolean
  message: string
}

export interface AppSettings {
  safety: SafetyConfig
  vehicle: VehicleProfile
  cameras: CameraProfile[]
  default_camera_id: string
  map_center: LatLon
  serial_baud: number
  sitl_url: string
  udp_url: string
}

export interface Health {
  status: 'ok' | 'degraded'
  version: string
  database: 'ok' | 'down'
  registry: { ok: boolean; crops: number }
  link: LinkStatus
}

export interface FlightSummary {
  id: number
  mission_id: number | null
  mission_name: string
  mission_revision: number | null
  segment: number | null
  vehicle_kind: string
  vehicle_description: string
  started_at: string
  ended_at: string | null
  status: 'in_progress' | 'completed' | 'aborted'
  summary: {
    distance_m?: number
    duration_s?: number
    max_alt_m?: number
    max_speed_mps?: number
    battery_start_pct?: number | null
    battery_end_pct?: number | null
    captures?: number
    failsafes?: string[]
    mission_completed?: boolean
  }
}

export interface TelemetryPoint {
  t: number
  lat: number
  lon: number
  alt: number
  hdg: number
  spd: number
  vz: number
  roll: number
  pitch: number
  batt: number | null
  sats: number
  mode: string
  seq: number | null
}

export interface FlightDetail extends FlightSummary {
  plan_snapshot: {
    route?: [number, number, number][]
    geofence?: [number, number][]
    area?: [number, number][]
    home?: [number, number] | null
  }
  telemetry: TelemetryPoint[]
  events: { t: number; time: string; kind: string; severity: Severity; message: string }[]
  captures: { index: number; t: number; lat: number; lon: number; alt: number; hdg: number }[]
}

export interface Place {
  name: string
  display_name: string
  lat: number
  lon: number
  kind: string
  locality: string
  state: string
  country: string
  postcode: string
  /** south, north, west, east */
  bounds: [number, number, number, number] | null
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'The ground station backend is not reachable.')
  }
  if (!response.ok) {
    let detail = response.statusText
    try {
      const data = await response.json()
      detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    } catch {
      /* keep the status text */
    }
    throw new ApiError(response.status, detail)
  }
  return (response.status === 204 ? undefined : await response.json()) as T
}

const get = <T>(path: string) => request<T>('GET', path)
const post = <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {})
const put = <T>(path: string, body: unknown) => request<T>('PUT', path, body)
const del = (path: string) => request<void>('DELETE', path)

export const api = {
  health: () => get<Health>('/api/health'),
  crops: () => get<CropProfile[]>('/api/crops'),
  models: () => get<ModelRow[]>('/api/models'),
  settings: () => get<AppSettings>('/api/settings'),
  saveSettings: (s: AppSettings) => put<AppSettings>('/api/settings', s),

  orchards: () => get<Orchard[]>('/api/orchards'),
  createOrchard: (o: OrchardInput) => post<Orchard>('/api/orchards', o),
  updateOrchard: (id: number, o: OrchardInput) => put<Orchard>(`/api/orchards/${id}`, o),
  deleteOrchard: (id: number) => del(`/api/orchards/${id}`),

  missions: () => get<MissionSummary[]>('/api/missions'),
  mission: (id: number) => get<MissionDetail>(`/api/missions/${id}`),
  previewMission: (plan: MissionPlan, orchard_id: number | null) =>
    post<Evaluation>('/api/missions/preview', { plan, orchard_id }),
  createMission: (name: string, orchard_id: number | null, plan: MissionPlan) =>
    post<MissionDetail>('/api/missions', { name, orchard_id, plan }),
  updateMission: (id: number, name: string, orchard_id: number | null, plan: MissionPlan) =>
    put<MissionDetail>(`/api/missions/${id}`, { name, orchard_id, plan }),
  deleteMission: (id: number) => del(`/api/missions/${id}`),

  ports: () => get<{ device: string; description: string }[]>('/api/vehicle/ports'),
  vehicleStatus: () => get<VehicleSnapshot>('/api/vehicle/status'),
  connect: (spec: {
    kind: 'sim' | 'sitl' | 'pixhawk'
    url?: string
    baud?: number
    sim?: Partial<SimOptions>
  }) => post<VehicleSnapshot>('/api/vehicle/connect', spec),
  disconnect: () => post<VehicleSnapshot>('/api/vehicle/disconnect'),
  preflight: () => get<Preflight>('/api/vehicle/preflight'),
  confirmCheck: (id: string, value: boolean) =>
    post<Preflight>('/api/vehicle/preflight/confirm', { id, value }),
  uploadMission: (id: number, segment = 0) =>
    post<{ ok: boolean; steps: { step: string; ok: boolean; message: string }[] }>(
      `/api/vehicle/mission/${id}/upload?segment=${segment}`,
    ),
  command: (command: string, args: Record<string, unknown> = {}) =>
    post<CommandResult>('/api/vehicle/command', { command, args }),
  simConditions: (c: {
    battery_pct?: number
    gps_ok?: boolean
    wind_mps?: number
    wind_from_deg?: number
    speedup?: number
    link_blackout_s?: number
  }) => post<VehicleSummary>('/api/vehicle/sim/conditions', c),

  searchPlaces: (query: string) => get<Place[]>(`/api/geocode/search?q=${encodeURIComponent(query)}`),
  placeAt: (lat: number, lon: number) => get<Place>(`/api/geocode/reverse?lat=${lat}&lon=${lon}`),

  flights: () => get<FlightSummary[]>('/api/flights'),
  flight: (id: number) => get<FlightDetail>(`/api/flights/${id}`),
  deleteFlight: (id: number) => del(`/api/flights/${id}`),
}
