import os
import re
import shutil
import tempfile
import wave
from typing import List, Optional

import httpx
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from TTS.api import TTS

app = FastAPI()

MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
OUTPUT_DIR = "/output"

tts_model: Optional[TTS] = None


@app.on_event("startup")
def load_model():
    global tts_model
    print("Lade XTTS-Modell (kann beim ersten Start ein paar Minuten dauern)...")
    tts_model = TTS(MODEL_NAME)
    print("XTTS-Modell geladen.")


class SynthRequest(BaseModel):
    job_id: int
    text: str
    speaker: str
    language: str = "de"
    speed: float = 0.85
    temperature: float = 0.6
    top_k: int = 50
    top_p: float = 0.85
    repetition_penalty: float = 5.0
    output_filename: str
    callback_url: str


def split_sentences(text: str) -> List[str]:
    """Simple Satz-Trennung, damit wir nach jedem Satz einen Fortschritt melden können."""
    text = text.strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def concat_wavs(paths: List[str], output_path: str):
    """Fügt mehrere .wav-Dateien mit gleichem Format aneinander."""
    if len(paths) == 1:
        shutil.move(paths[0], output_path)
        return

    with wave.open(paths[0], "rb") as first:
        params = first.getparams()

    with wave.open(output_path, "wb") as out:
        out.setparams(params)
        for p in paths:
            with wave.open(p, "rb") as chunk:
                out.writeframes(chunk.readframes(chunk.getnframes()))
            os.remove(p)


def notify(callback_url: str, path: str, payload: dict):
    try:
        httpx.post(f"{callback_url}{path}", json=payload, timeout=10)
    except Exception as e:
        print(f"Callback an {callback_url}{path} fehlgeschlagen:", e)


def run_render(req: SynthRequest):
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        sentences = split_sentences(req.text) or [req.text]
        total_chars = sum(len(s) for s in sentences) or 1
        chars_done = 0
        chunk_paths = []

        print(f"Job {req.job_id}: {len(sentences)} Satz/Sätze zu rendern")

        for i, sentence in enumerate(sentences):
            chunk_path = os.path.join(tempfile.gettempdir(), f"job{req.job_id}_chunk{i}.wav")

            tts_model.tts_to_file(
                text=sentence,
                speaker=req.speaker,
                language=req.language,
                speed=req.speed,
                temperature=req.temperature,
                top_k=req.top_k,
                top_p=req.top_p,
                repetition_penalty=req.repetition_penalty,
                split_sentences=True,
                file_path=chunk_path,
            )

            chunk_paths.append(chunk_path)

            # Fortschritt nach Zeichenanzahl gewichten, nicht nach Satzanzahl -
            # ein langer Satz soll auch anteilig mehr zum Fortschritt beitragen
            chars_done += len(sentence)
            progress = round(chars_done / total_chars * 100)
            notify(req.callback_url, f"/jobs/{req.job_id}/progress", {"progress": progress})
            print(f"Job {req.job_id}: {progress}%")

        final_path = os.path.join(OUTPUT_DIR, req.output_filename)
        concat_wavs(chunk_paths, final_path)

        notify(
            req.callback_url,
            f"/jobs/{req.job_id}/done",
            {"output": f"/output/{req.output_filename}"},
        )
        print(f"Job {req.job_id}: fertig -> {final_path}")

    except Exception as e:
        print(f"Job {req.job_id}: FEHLGESCHLAGEN - {e}")
        notify(req.callback_url, f"/jobs/{req.job_id}/error", {"message": str(e)})


@app.post("/synthesize")
def synthesize(req: SynthRequest, background_tasks: BackgroundTasks):
    # Läuft im Hintergrund weiter, der HTTP-Request kehrt sofort zurück.
    # Fortschritt/Ergebnis kommen per Callback an das Backend zurück.
    background_tasks.add_task(run_render, req)
    return {"status": "angenommen"}


@app.get("/")
def root():
    return {"status": "xtts-service läuft", "modell_geladen": tts_model is not None}
