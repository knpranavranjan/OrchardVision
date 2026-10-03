"""The ground station through its API: the way the browser uses it."""

import time

import pytest

from tests.helpers import HOME, rect, survey_plan

pytestmark = pytest.mark.db


def wait_for(client, condition, timeout=30.0, what="condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = client.get("/api/vehicle/status").json()
        if condition(status):
            return status
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for {what}: {status.get('state')}")


def make_orchard(client, **extra):
    body = {
        "name": "Papaya Farm 01",
        "crop": "papaya",
        "boundary": [p.model_dump() for p in rect(0, 0, 120, 80)],
        **extra,
    }
    r = client.post("/api/orchards", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def make_mission(client, orchard_id=None, plan=None, name="Block A survey"):
    plan = plan or survey_plan()
    r = client.post(
        "/api/missions",
        json={"name": name, "orchard_id": orchard_id, "plan": plan.model_dump(mode="json")},
    )
    assert r.status_code == 201, r.text
    return r.json()


def connect_sim(client, speedup=20.0):
    r = client.post(
        "/api/vehicle/connect",
        json={
            "kind": "sim",
            "sim": {"home_lat": HOME.lat, "home_lon": HOME.lon, "speedup": speedup},
        },
    )
    assert r.status_code == 200, r.text
    return wait_for(client, lambda s: s["state"] is not None, what="first telemetry")


def command(client, name, **args):
    return client.post("/api/vehicle/command", json={"command": name, "args": args}).json()


def test_health_and_registry(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["database"] == "ok" and body["link"] == "disconnected"
    assert [c["crop"] for c in client.get("/api/crops").json()] == ["papaya"]
    assert {m["status"] for m in client.get("/api/models").json()} == {"active"}


def test_orchard_crud_and_model_selection(client):
    o = make_orchard(client)
    assert o["area_ha"] == pytest.approx(0.96, abs=0.001)
    assert o["models_ready"] and "tree stub-0" in o["models_detail"]

    # Pin a model version; an unknown one is refused.
    body = {**o, "tree_model_version": "stub-0", "name": "Renamed"}
    updated = client.put(f"/api/orchards/{o['id']}", json=body).json()
    assert updated["name"] == "Renamed" and updated["tree_model_version"] == "stub-0"
    bad = client.put(f"/api/orchards/{o['id']}", json={**body, "fruit_model_version": "v99"})
    assert bad.status_code == 422
    assert client.post("/api/orchards", json={**body, "crop": "durian"}).status_code == 422

    assert any(x["id"] == o["id"] for x in client.get("/api/orchards").json())
    assert client.delete(f"/api/orchards/{o['id']}").status_code == 204
    assert client.get(f"/api/orchards/{o['id']}").status_code == 404


def test_mission_preview_save_revise_export(client):
    o = make_orchard(client)
    plan = survey_plan()
    preview = client.post(
        "/api/missions/preview",
        json={"orchard_id": o["id"], "plan": plan.model_dump(mode="json")},
    ).json()
    assert preview["stats"]["lines"] == 9 and preview["validation"]["ok"]
    assert len(preview["capture_points"]) == preview["stats"]["photos"] == 117
    assert {c["id"] for c in preview["validation"]["checks"]} >= {
        "fence",
        "battery",
        "gsd",
        "models",
    }

    m = make_mission(client, o["id"], plan)
    assert m["revision"] == 1 and m["valid"]

    # Renaming alone keeps the revision; changing the plan bumps it.
    same = client.put(
        f"/api/missions/{m['id']}",
        json={"name": "Renamed", "orchard_id": o["id"], "plan": m["plan"]},
    ).json()
    assert same["revision"] == 1
    plan.survey.altitude_m = 30
    plan.takeoff_alt_m = 30
    changed = client.put(
        f"/api/missions/{m['id']}",
        json={"name": "Renamed", "orchard_id": o["id"], "plan": plan.model_dump(mode="json")},
    ).json()
    assert changed["revision"] == 2 and changed["stats"]["gsd_cm"] > m["stats"]["gsd_cm"]

    for fmt, marker in (
        ("qgc", '"fileType": "Plan"'),
        ("waypoints", "QGC WPL 110"),
        ("kml", "<kml"),
    ):
        r = client.get(f"/api/missions/{m['id']}/export/{fmt}")
        assert r.status_code == 200 and marker in r.text
        assert "attachment" in r.headers["content-disposition"]
    assert client.get(f"/api/missions/{m['id']}/export/pdf").status_code == 404


def test_commands_need_a_vehicle(client):
    assert command(client, "arm") == {"accepted": False, "message": "No vehicle connected"}
    pre = client.get("/api/vehicle/preflight").json()
    assert not pre["ready"] and "Drone connected" in pre["blocking"]
    assert client.post("/api/vehicle/mission/1/upload").status_code == 409


def test_invalid_mission_is_not_uploaded(client):
    plan = survey_plan()
    plan.geofence = []
    m = make_mission(client, plan=plan)
    assert not m["valid"]
    connect_sim(client)
    r = client.post(f"/api/vehicle/mission/{m['id']}/upload")
    assert r.status_code == 409 and "Geofence" in r.json()["detail"]
    client.post("/api/vehicle/disconnect")


def test_full_flight_is_flown_and_recorded(client):
    o = make_orchard(client)
    m = make_mission(client, o["id"])
    connect_sim(client)

    # Before upload: flyable by hand, but starting a mission is refused.
    pre = client.get("/api/vehicle/preflight").json()
    assert pre["ready"], pre["blocking"]
    assert not command(client, "start")["accepted"]

    up = client.post(f"/api/vehicle/mission/{m['id']}/upload").json()
    assert up["ok"], up
    assert [s["step"] for s in up["steps"]] == [
        "Emergency settings", "Geofence", "Mission items", "Read-back",
    ]  # fmt: skip
    status = client.get("/api/vehicle/status").json()
    assert status["mission"]["verified"] and status["mission"]["fence_points"] == 4
    assert len(status["mission_geometry"]["route"]) > 10

    pre = client.get("/api/vehicle/preflight").json()
    by_id = {c["id"]: c for c in pre["checks"]}
    assert pre["ready"], pre["blocking"]
    for id_ in ("link", "heartbeat", "gps", "gps_quality", "battery", "home", "mission_valid",
                "mission_verified", "fence", "failsafes", "models", "storage", "recording"):  # fmt: skip
        assert by_id[id_]["status"] == "pass", by_id[id_]

    assert command(client, "arm")["accepted"]
    assert command(client, "start")["accepted"]
    flying = wait_for(client, lambda s: s["flying"] and s["state"]["mode"] == "auto", what="AUTO")
    assert flying["flight_id"] is None or isinstance(flying["flight_id"], int)

    # Live channel carries telemetry while it flies.
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "hello"
        snapshot = ws.receive_json()
        assert snapshot["type"] == "snapshot" and snapshot["data"]["link"] == "connected"
        kinds = set()
        for _ in range(60):
            kinds.add(ws.receive_json()["type"])
            if {"telemetry", "status"} <= kinds:
                break
        assert {"telemetry", "status"} <= kinds

    done = wait_for(client, lambda s: not s["flying"], timeout=90, what="landing")
    assert done["state"]["armed"] is False and done["last_flight_id"]
    assert client.post("/api/vehicle/disconnect").status_code == 200

    # The record
    flights = client.get("/api/flights").json()
    f = next(x for x in flights if x["id"] == done["last_flight_id"])
    assert f["status"] == "completed" and f["mission_name"] == "Block A survey"
    assert f["mission_revision"] == 1 and f["vehicle_kind"] == "sim"
    s = f["summary"]
    assert s["mission_completed"] and s["failsafes"] == []
    # Surveyed at 25 m, then climbed to the 30 m return height to come home.
    assert s["max_alt_m"] == pytest.approx(30, abs=1.0)
    assert 650 < s["distance_m"] < 900
    assert abs(s["captures"] - m["stats"]["photos"]) <= 9

    detail = client.get(f"/api/flights/{f['id']}").json()
    assert len(detail["captures"]) == s["captures"]
    assert len(detail["telemetry"]) > 20  # two a second of wall time; this flight ran at 20x
    assert detail["telemetry"][0]["t"] == 0 and detail["telemetry"][-1]["alt"] < 0.5
    assert max(p["alt"] for p in detail["telemetry"]) == pytest.approx(30, abs=1.0)
    messages = [e["message"] for e in detail["events"]]
    assert "Armed" in messages and "Mission complete" in messages
    assert len(detail["plan_snapshot"]["route"]) > 10

    csv = client.get(f"/api/flights/{f['id']}/captures.csv").text.splitlines()
    assert csv[0].startswith("index,time_utc,lat,lon") and len(csv) == s["captures"] + 1

    assert client.delete(f"/api/flights/{f['id']}").status_code == 204


def test_manual_flight_and_failure_rehearsal(client):
    connect_sim(client)
    assert command(client, "arm")["accepted"]
    assert command(client, "takeoff", alt_m=12)["accepted"]
    wait_for(client, lambda s: s["state"]["mode"] == "hold", what="takeoff")
    assert client.post("/api/vehicle/disconnect").status_code == 409  # not while flying

    # Stick input over the live channel moves it north.
    with client.websocket_connect("/ws") as ws:
        for _ in range(12):
            ws.send_json(
                {"type": "manual", "data": {"forward": 99, "right": 0, "up": 0, "yaw_rate": 0}}
            )
            time.sleep(0.05)
    moved = wait_for(client, lambda s: s["state"]["lat"] > HOME.lat + 0.00005, what="movement")
    assert moved["state"]["groundspeed_mps"] <= 5.01 or moved["state"]["mode"] != "manual"

    # Fly-to, then a rehearsed GPS failure forces a landing and marks the flight aborted.
    assert command(client, "goto", lat=HOME.lat + 0.0003, lon=HOME.lon, alt_m=12)["accepted"]
    r = client.post("/api/vehicle/sim/conditions", json={"gps_ok": False})
    assert r.status_code == 200
    done = wait_for(client, lambda s: not s["flying"], timeout=60, what="forced landing")
    client.post("/api/vehicle/disconnect")
    f = client.get(f"/api/flights/{done['last_flight_id']}").json()
    assert f["status"] == "aborted" and f["mission_name"] == "Manual flight"
    assert any("GPS lost" in x for x in f["summary"]["failsafes"])


def test_conditions_and_confirmations_reach_an_open_browser(client):
    """Changing things while a browser is listening must broadcast, not fail."""
    connect_sim(client)
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "hello"
        assert ws.receive_json()["type"] == "snapshot"
        r = client.post("/api/vehicle/sim/conditions", json={"wind_mps": 6, "wind_from_deg": 270})
        assert r.status_code == 200 and r.json()["sim"]["wind_mps"] == 6
        seen = []
        for _ in range(40):
            message = ws.receive_json()
            if message["type"] == "event":
                seen.append(message["data"]["message"])
                break
        assert any("Simulator conditions changed" in m for m in seen)
    assert (
        client.post(
            "/api/vehicle/preflight/confirm", json={"id": "nope", "value": True}
        ).status_code
        == 404
    )
    client.post("/api/vehicle/disconnect")


def test_arm_is_blocked_until_preflight_passes(client):
    connect_sim(client)
    client.post("/api/vehicle/sim/conditions", json={"battery_pct": 25})
    time.sleep(0.3)
    result = command(client, "arm")
    assert not result["accepted"] and "Battery" in result["message"]
    forced = command(client, "arm", override=True)
    assert forced["accepted"]
    events = client.get("/api/vehicle/status").json()["events"]
    assert any("overridden" in e["message"] for e in events)
    command(client, "disarm")
    client.post("/api/vehicle/disconnect")


def test_settings_round_trip(client):
    s = client.get("/api/settings").json()
    assert s["default_camera_id"] == "rpi-gs-6mm" and len(s["cameras"]) == 3
    s["safety"]["max_alt_m"] = 45
    assert client.put("/api/settings", json=s).json()["safety"]["max_alt_m"] == 45
    assert client.get("/api/settings").json()["safety"]["max_alt_m"] == 45
    s["default_camera_id"] = "nope"
    assert client.put("/api/settings", json=s).status_code == 422


def test_works_without_a_database(offline_client):
    c = offline_client
    assert c.get("/api/health").json()["database"] == "down"
    assert c.get("/api/orchards").status_code == 503
    # Flying still works; the flight is simply not recorded.
    connect_sim(c)
    pre = c.get("/api/vehicle/preflight").json()
    assert pre["ready"]
    assert command(c, "arm")["accepted"] and command(c, "takeoff", alt_m=8)["accepted"]
    wait_for(c, lambda s: s["state"]["mode"] == "hold", what="takeoff")
    assert command(c, "land")["accepted"]
    wait_for(c, lambda s: not s["flying"], timeout=40, what="landing")
    rec = {x["id"]: x for x in c.get("/api/vehicle/preflight").json()["checks"]}["recording"]
    assert rec["status"] == "warn"
    c.post("/api/vehicle/disconnect")
