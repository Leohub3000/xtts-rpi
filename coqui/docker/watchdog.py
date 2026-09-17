import subprocess
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

COMPOSE_DIR = os.environ.get("COMPOSE_DIR", "/mnt/data/tts/coqui")

# Compose-Plugin an bekannten Pfaden suchen
_PLUGIN_CANDIDATES = [
    "/usr/libexec/docker/cli-plugins/docker-compose",
    "/usr/lib/docker/cli-plugins/docker-compose",
    "/usr/local/lib/docker/cli-plugins/docker-compose",
]

def _compose_cmd() -> list[str]:
    """Gibt den richtigen docker-compose Befehl zurück."""
    for path in _PLUGIN_CANDIDATES:
        if os.path.isfile(path):
            # Plugin direkt aufrufen (umgeht das fehlende CLI-Plugin-System)
            return [path]
    # Fallback: docker-compose als eigenständiges Programm
    return ["docker-compose"]


def run(args: list[str]) -> dict:
    cmd = _compose_cmd() + args
    try:
        result = subprocess.run(
            cmd,
            cwd=COMPOSE_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "Timeout"}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e)}


DOCKER = "/usr/bin/docker"


def container_status(name: str) -> str:
    try:
        result = subprocess.run(
            [DOCKER, "inspect", "--format", "{{.State.Status}}", name],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return "absent"


def _overall(backend: str, xtts: str) -> str:
    states = {backend, xtts}
    if states == {"running"}:
        return "running"
    if "running" not in states and states <= {"exited", "created", "absent"}:
        return "stopped"
    return "starting"


@app.get("/")
def root():
    plugin = _compose_cmd()
    return {"status": "Watchdog läuft", "compose_cmd": plugin}


@app.get("/engine/status")
def engine_status():
    backend = container_status("xtts_backend")
    xtts = container_status("xtts")
    return {
        "backend": backend,
        "xtts": xtts,
        "engine": _overall(backend, xtts),
    }


@app.post("/engine/start")
def engine_start():
    # Alte gestoppte Container direkt per docker rm entfernen
    # (docker compose rm ist unzuverlässig bei exited-Containern)
    for container in ["xtts", "xtts_backend"]:
        subprocess.run(
            [DOCKER, "rm", container],
            capture_output=True, timeout=10
        )
    # Dann neu starten ohne neu zu bauen
    r = run(["up", "-d", "--no-build", "xtts", "backend"])
    return {"ok": r["ok"], "detail": r["stderr"] or r["stdout"]}


@app.post("/engine/stop")
def engine_stop():
    r = run(["stop", "xtts", "backend"])
    return {"ok": r["ok"], "detail": r["stderr"] or r["stdout"]}
