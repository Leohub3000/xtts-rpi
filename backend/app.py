from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import json
import os
import asyncio
import httpx

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Konfiguration ---

# Adresse des xtts-Service im Docker-Netzwerk (Servicename aus docker-compose.yml)
XTTS_URL = os.environ.get("XTTS_URL", "http://xtts:8010")

# Adresse, unter der DIESES Backend vom xtts-Container aus erreichbar ist,
# damit die Fortschritts-/Fertig-Callbacks ankommen
BACKEND_CALLBACK_URL = os.environ.get("BACKEND_CALLBACK_URL", "http://backend:8000")

OUTPUT_DIR = "/output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

VOICES_DIR = "/voices"

# Macht fertige .wav-Dateien unter /output/<dateiname> für das Frontend abrufbar
app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")

# Macht Stimm-Samples unter /voices/<dateiname> für die Vorschau abrufbar
if os.path.isdir(VOICES_DIR):
    app.mount("/voices", StaticFiles(directory=VOICES_DIR), name="voices")

jobs = {}
next_job_id = 1
JOB_FILE = "jobs.json"


def save_jobs():
    with open(JOB_FILE, "w", encoding="utf-8") as f:
        json.dump(list(jobs.values()), f, indent=4, ensure_ascii=False)


def load_jobs():
    global next_job_id

    if os.path.exists(JOB_FILE):
        with open(JOB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

            for job in data:
                # Ein Job, der beim letzten Absturz/Neustart noch aktiv war,
                # ist verwaist -> zurück in die Warteschlange
                if job.get("status") in ("Rendert", "Wird vorbereitet"):
                    job["status"] = "Wartet"
                    job["progress"] = 0

                job.setdefault("progress", 0)
                jobs[job["id"]] = job

        if jobs:
            next_job_id = max(jobs.keys()) + 1


load_jobs()


async def render_worker():
    """Schaut alle 2 Sekunden nach, ob ein Job wartet und aktuell nichts rendert.
    Das eigentliche Rendern läuft komplett im xtts-Service; der Fortschritt und
    das Ergebnis kommen über die /jobs/{id}/progress- und /jobs/{id}/done-Callbacks
    zurück. Diese Schleife blockiert also NICHT während des Renderns."""

    while True:
        already_rendering = any(
            j["status"] in ("Rendert", "Wird vorbereitet") for j in jobs.values()
        )

        if not already_rendering:
            for job_id, job in jobs.items():
                if job["status"] == "Wartet":
                    # "Wird vorbereitet": Job wurde an xtts geschickt, aber es kam
                    # noch kein Fortschritt zurück (Modell lädt evtl. noch, o.ä.)
                    job["status"] = "Wird vorbereitet"
                    job["progress"] = 0
                    save_jobs()

                    asyncio.create_task(dispatch_to_xtts(job))
                    break

        await asyncio.sleep(2)


async def dispatch_to_xtts(job):
    job_id = job["id"]

    payload = {
        "job_id": job_id,
        "text": job["text"],
        "speaker": job["speaker"],
        "language": job.get("language", "de"),
        "speed": job["speed"],
        "temperature": job["temperature"],
        "top_k": job.get("top_k", 50),
        "top_p": job.get("top_p", 0.85),
        "repetition_penalty": job.get("repetition_penalty", 5.0),
        "output_filename": job["output"],
        "callback_url": BACKEND_CALLBACK_URL,
    }

    while True:
        # Job könnte in der Zwischenzeit gelöscht worden sein -> abbrechen
        if job_id not in jobs:
            return

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(f"{XTTS_URL}/synthesize", json=payload)
                response.raise_for_status()
            return  # erfolgreich übergeben, xtts übernimmt jetzt und meldet sich per Callback

        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            # xtts ist (noch) nicht erreichbar, z.B. weil das Modell noch lädt.
            # Status bleibt bewusst "Wird vorbereitet" - kein Hin-und-Her mehr.
            print(f"xtts noch nicht erreichbar, versuche es in Kürze erneut: {e}")
            await asyncio.sleep(3)
            continue


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(render_worker())


class RenderJob(BaseModel):
    text: str
    speaker: str
    language: str = "de"
    speed: float = 0.85
    temperature: float = 0.6
    top_k: int = 50
    top_p: float = 0.85
    repetition_penalty: float = 5.0
    preset_name: str = "custom"
    chars: int = 0
    custom_filename: str | None = None


class ProgressUpdate(BaseModel):
    progress: int


class DoneUpdate(BaseModel):
    output: str


class ErrorUpdate(BaseModel):
    message: str = ""


@app.get("/")
def root():
    return {"status": "Backend läuft"}


@app.post("/render")
def render(job: RenderJob):
    global next_job_id

    text = job.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text darf nicht leer sein")

    job_id = next_job_id
    next_job_id += 1

    # Dateiname: custom oder auto (Sprecher_Preset_Timestamp)
    speaker_slug = job.speaker.replace(" ", "_")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if job.custom_filename:
        # Vom Benutzer eingegebenen Namen bereinigen und Timestamp anhängen
        base = job.custom_filename.removesuffix(".wav").strip()
        base = "".join(c for c in base if c.isalnum() or c in "_-. ")
        base = base.replace(" ", "_")
        output_filename = f"{base}_{timestamp}.wav"
    else:
        output_filename = f"{job_id}_{speaker_slug}_{job.preset_name}_{timestamp}.wav"

    jobs[job_id] = {
        "id": job_id,
        "status": "Wartet",
        "progress": 0,
        "text": job.text,
        "chars": job.chars if job.chars > 0 else len(job.text),
        "speaker": job.speaker,
        "language": job.language,
        "speed": job.speed,
        "temperature": job.temperature,
        "top_k": job.top_k,
        "top_p": job.top_p,
        "repetition_penalty": job.repetition_penalty,
        "preset_name": job.preset_name,
        "output": output_filename,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    save_jobs()

    print("Neuer Job:", job_id)

    return {"status": "angenommen", "job_id": job_id}


@app.get("/jobs")
def get_jobs():
    return list(jobs.values())


@app.delete("/jobs/{job_id}")
def delete_job(job_id: int):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job nicht gefunden")

    del jobs[job_id]
    save_jobs()

    return {"status": "gelöscht"}


@app.post("/jobs/{job_id}/hold")
def hold_job(job_id: int):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job nicht gefunden")

    if jobs[job_id]["status"] != "Wartet":
        raise HTTPException(
            status_code=400,
            detail="Nur wartende Jobs können angehalten werden",
        )

    jobs[job_id]["status"] = "Angehalten"
    save_jobs()

    return {"status": "ok"}


@app.post("/jobs/{job_id}/resume")
def resume_job(job_id: int):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job nicht gefunden")

    jobs[job_id]["status"] = "Wartet"
    save_jobs()

    return {"status": "ok"}


@app.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job nicht gefunden")

    jobs[job_id]["status"] = "Abgebrochen"
    save_jobs()

    return {"status": "ok"}


@app.post("/jobs/{job_id}/progress")
def job_progress(job_id: int, update: ProgressUpdate):
    """Wird vom xtts-Service während des Renderns aufgerufen."""
    if job_id not in jobs:
        return {"status": "ignoriert"}

    # Die erste echte Fortschrittsmeldung bedeutet: xtts rendert jetzt tatsächlich
    if jobs[job_id]["status"] == "Wird vorbereitet":
        jobs[job_id]["status"] = "Rendert"

    jobs[job_id]["progress"] = update.progress
    save_jobs()

    return {"status": "ok"}


@app.post("/jobs/{job_id}/done")
def job_done(job_id: int, update: DoneUpdate):
    """Wird vom xtts-Service aufgerufen, sobald der Job fertig gerendert ist."""
    if job_id not in jobs:
        return {"status": "ignoriert"}

    jobs[job_id]["status"] = "Fertig"
    jobs[job_id]["progress"] = 100
    jobs[job_id]["output"] = update.output
    save_jobs()

    print("Job fertig:", job_id)

    return {"status": "ok"}


@app.post("/jobs/{job_id}/error")
def job_error(job_id: int, update: ErrorUpdate):
    """Wird vom xtts-Service aufgerufen, wenn das Rendern fehlgeschlagen ist."""
    if job_id not in jobs:
        return {"status": "ignoriert"}

    jobs[job_id]["status"] = "Fehler"
    save_jobs()

    print(f"Job {job_id} fehlgeschlagen: {update.message}")

    return {"status": "ok"}
