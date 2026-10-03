#!/usr/bin/env python3
"""Start the whole OrchardVision ground station with one command.

    python run.py            database, backend, front end, opens the browser
    python run.py --sitl     the same, plus the ArduPilot software autopilot
    python run.py --stop     stop the database and autopilot containers

Works on macOS, Windows and Linux. Press Ctrl+C to stop the ground station.
Needs Docker Desktop, uv and Node.js; it tells you how to install any that are missing.
"""

import argparse
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND, FRONTEND = ROOT / "backend", ROOT / "frontend"
BACKEND_PORT, FRONTEND_PORT = 8000, 5173
APP_URL = f"http://localhost:{FRONTEND_PORT}"
HEALTH_URL = f"http://localhost:{BACKEND_PORT}/api/health"
WINDOWS = os.name == "nt"
MAC = platform.system() == "Darwin"

INSTALL = {
    "uv": "brew install uv" if MAC else "https://docs.astral.sh/uv/getting-started/installation/",
    "npm": "brew install node" if MAC else "https://nodejs.org (version 20 or newer)",
    "docker": "https://www.docker.com/products/docker-desktop/",
}


def say(message: str) -> None:
    print(f"[run] {message}", flush=True)


def tool(name: str) -> str:
    """Full path of a required program, or stop with how to install it."""
    path = shutil.which(name)
    if not path:
        sys.exit(f"[run] '{name}' is not installed. Install it with: {INSTALL[name]}")
    return path


def port_busy(port: int) -> bool:
    # "localhost" may be IPv4 or IPv6 depending on the program listening; try both.
    try:
        socket.create_connection(("localhost", port), timeout=0.5).close()
        return True
    except OSError:
        return False


def responds(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return r.status == 200
    except OSError:
        return False


def docker_ready() -> bool:
    docker = shutil.which("docker")
    if not docker:
        return False
    return subprocess.run([docker, "info"], capture_output=True).returncode == 0


def start_containers(sitl: bool) -> bool:
    """Bring up the database (and the autopilot if asked). False if Docker is not available."""
    if not docker_ready():
        hint = "Open Docker Desktop and wait until it says it is running" if shutil.which("docker") else (
            f"Install Docker Desktop: {INSTALL['docker']}"
        )
        say(f"Docker is not running. {hint}, then run this again.")
        say("Continuing without the database: you can fly the simulator, but nothing is saved.")
        return False
    say("Starting the database ...")
    subprocess.run(["docker", "compose", "up", "-d", "--wait", "db"], cwd=ROOT, check=True)
    if sitl:
        say("Starting the ArduPilot software autopilot (the first build takes a few minutes) ...")
        subprocess.run(
            ["docker", "compose", "--profile", "sitl", "up", "-d", "sitl"], cwd=ROOT, check=True
        )
    return True


def stop_containers() -> None:
    if docker_ready():
        subprocess.run(["docker", "compose", "--profile", "sitl", "stop"], cwd=ROOT, check=False)
    say("Containers stopped. Saved orchards, missions and flights are kept.")


def launch(name: str, command: list, cwd: Path) -> subprocess.Popen:
    """Start a long-running program and echo its output with a name in front."""
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {
        "start_new_session": True
    }
    process = subprocess.Popen(
        command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", env=os.environ | {"NO_COLOR": "1"}, **options,
    )  # fmt: skip

    def echo() -> None:
        for line in process.stdout:
            print(f"[{name}] {line.rstrip()}", flush=True)

    threading.Thread(target=echo, daemon=True).start()
    return process


def stop(process: subprocess.Popen) -> None:
    """Stop a program and anything it started (npm starts node, uv starts python)."""
    if process.poll() is not None:
        return
    if WINDOWS:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the OrchardVision ground station.")
    parser.add_argument("--sitl", action="store_true", help="also start the ArduPilot software autopilot")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    parser.add_argument("--stop", action="store_true", help="stop the containers and exit")
    args = parser.parse_args()
    # A terminal that cannot show a character should not stop the output.
    sys.stdout.reconfigure(errors="replace")

    if args.stop:
        stop_containers()
        return

    uv, npm = tool("uv"), tool("npm")
    for port, what in ((BACKEND_PORT, "backend"), (FRONTEND_PORT, "front end")):
        if port_busy(port):
            sys.exit(
                f"[run] Port {port} is already in use, so the {what} cannot start. "
                f"The ground station may already be running: open {APP_URL}, "
                "or close the other copy and run this again."
            )

    database = start_containers(args.sitl)

    say("Checking the backend's packages ...")
    subprocess.run([uv, "sync", "--quiet"], cwd=BACKEND, check=True)
    if database:
        say("Updating the database layout ...")
        subprocess.run([uv, "run", "alembic", "upgrade", "head"], cwd=BACKEND, check=True)
    if not (FRONTEND / "node_modules").is_dir():
        say("Installing the front end's packages (first run only) ...")
        subprocess.run([npm, "install"], cwd=FRONTEND, check=True)

    say("Starting the backend and the front end ...")
    backend = [uv, "run", "uvicorn", "app.main:app", "--port", str(BACKEND_PORT)]
    running = [
        launch("backend", backend, BACKEND),
        launch("frontend", [npm, "run", "dev", "--", "--port", str(FRONTEND_PORT), "--strictPort"], FRONTEND),
    ]
    try:
        deadline = time.time() + 90
        while not (responds(HEALTH_URL) and port_busy(FRONTEND_PORT)):
            if any(p.poll() is not None for p in running):
                sys.exit("[run] A part of the ground station stopped while starting. See the lines above.")
            if time.time() > deadline:
                sys.exit("[run] The ground station did not come up within 90 seconds. See the lines above.")
            time.sleep(0.5)
        say(f"Ground station is ready: {APP_URL}")
        if args.sitl:
            say("Software autopilot: connect to tcp:127.0.0.1:5760 from the Connect dialog.")
        say("Press Ctrl+C here to stop it.")
        if not args.no_browser:
            webbrowser.open(APP_URL)
        while all(p.poll() is None for p in running):
            time.sleep(0.5)
        say("A part of the ground station stopped. Shutting the rest down.")
    except KeyboardInterrupt:
        say("Stopping ...")
    finally:
        for process in running:
            stop(process)
    say("Stopped. The database keeps running in Docker; 'python run.py --stop' stops it too.")


if __name__ == "__main__":
    main()
