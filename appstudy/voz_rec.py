"""Reconocimiento de voz local (STT) y juicio de pronunciación con Bit.

Permite que el usuario responda tarjetas en voz alta al micrófono. Un motor
local (Vosk o Whisper.cpp) transcribe lo pronunciado, calcula la similitud con
la respuesta esperada y, opcionalmente, la IA local de Bit evalúa la calidad
fonética y conceptual para dar retroalimentación inmediata.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path

from . import ia, util, voz

VOSK_DIR = Path.home() / ".local" / "share" / "appstudy" / "vosk"
VOSK_MODEL_ES = VOSK_DIR / "vosk-model-small-es-0.42"
VOSK_MODEL_EN = VOSK_DIR / "vosk-model-small-en-us-0.15"

_vosk_modelos: dict[str, object] = {}
_lock_vosk = threading.Lock()


def tiene_reconocimiento_voz(idioma: str = "es") -> bool:
    """Indica si el reconocimiento de voz local está disponible."""
    try:
        import vosk
    except ImportError:
        return bool(shutil.which("whisper-cli") or shutil.which("whisper"))

    ruta = VOSK_MODEL_EN if str(idioma).lower().startswith("en") else VOSK_MODEL_ES
    if ruta.is_dir():
        return True
    return bool(shutil.which("whisper-cli") or shutil.which("whisper"))


def _obtener_modelo_vosk(idioma: str = "es"):
    import vosk
    vosk.SetLogLevel(-1)
    es_en = str(idioma).lower().startswith("en")
    clave = "en" if es_en else "es"
    ruta = VOSK_MODEL_EN if es_en else VOSK_MODEL_ES

    with _lock_vosk:
        if clave in _vosk_modelos:
            return _vosk_modelos[clave]
        if ruta.is_dir():
            try:
                mod = vosk.Model(str(ruta))
                _vosk_modelos[clave] = mod
                return mod
            except Exception:
                return None
    return None


def transcribir_audio(ruta_wav: str, idioma: str = "es") -> str:
    """Transcribe un archivo de audio WAV localmente."""
    if not os.path.isfile(ruta_wav):
        return ""

    # 1. Intentar con Vosk si está disponible
    try:
        import vosk
        modelo = _obtener_modelo_vosk(idioma)
        if modelo:
            wf = wave.open(ruta_wav, "rb")
            rec = vosk.KaldiRecognizer(modelo, wf.getframerate())
            rec.SetWords(True)

            textos = []
            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                if rec.AcceptWaveform(data):
                    res = json.loads(rec.Result())
                    if res.get("text"):
                        textos.append(res["text"])

            final = json.loads(rec.FinalResult())
            if final.get("text"):
                textos.append(final["text"])
            wf.close()
            return " ".join(textos).strip()
    except Exception:
        pass

    # 2. Intentar con whisper-cli si existe
    whisper_bin = shutil.which("whisper-cli") or shutil.which("whisper")
    if whisper_bin:
        try:
            r = subprocess.run(
                [whisper_bin, "-l", ("en" if str(idioma).lower().startswith("en") else "es"),
                 "-f", ruta_wav, "--output-txt"],
                capture_output=True, text=True, timeout=20
            )
            return r.stdout.strip()
        except Exception:
            pass

    return ""


def juzgar_respuesta(dicho: str, esperada: str, card: dict | None = None,
                     cfg_ia: dict | None = None) -> dict:
    """Compara lo dicho por el usuario con la respuesta esperada y juzga el acierto."""
    dicho_limpio = voz.limpiar_para_voz(dicho).lower().strip()
    esperada_limpia = voz.limpiar_para_voz(esperada).lower().strip()

    if not dicho_limpio:
        return {
            "acierto": False,
            "similitud": 0.0,
            "feedback": "No se detectó ninguna voz clara. Intenta acercarte más al micrófono.",
            "dicho": "",
            "esperado": esperada_limpia,
        }

    # Coincidencia difusa
    similitud = difflib.SequenceMatcher(None, dicho_limpio, esperada_limpia).ratio()

    # Si contiene las palabras clave esenciales
    palabras_dichas = set(re.findall(r"\b\w+\b", dicho_limpio))
    palabras_esp = set(re.findall(r"\b\w+\b", esperada_limpia))
    comunes = len(palabras_dichas & palabras_esp)
    solapamiento = comunes / max(1, len(palabras_esp))

    es_acierto = (similitud >= 0.65 or solapamiento >= 0.70)

    # Evaluación asistida con IA si está configurada
    feedback = ""
    if cfg_ia and cfg_ia.get("activa"):
        try:
            pregunta = card.get("front", "") if card else ""
            prompt = (f"El estudiante respondió verbalmente: \"{dicho}\".\n"
                      f"La respuesta de referencia es: \"{esperada}\" (Pregunta: \"{pregunta}\").\n"
                      "Evalúa en UNA SOLA frase breve y natural si es correcta y comenta la pronunciación o precisión.")
            feedback = ia.completar(cfg_ia, prompt, timeout=10)
        except Exception:
            pass

    if not feedback:
        if es_acierto:
            feedback = f"¡Muy bien pronunciado! Coincide con «{esperada_limpia}» ({int(similitud * 100)}%)."
        else:
            feedback = f"Dijiste «{dicho_limpio}». La respuesta esperada era «{esperada_limpia}»."

    return {
        "acierto": es_acierto,
        "similitud": round(similitud, 2),
        "feedback": feedback,
        "dicho": dicho_limpio,
        "esperado": esperada_limpia,
    }


class GrabadorMicrofono:
    """Controla la grabación desde el micrófono del sistema."""

    def __init__(self):
        self._proc = None
        self._wav_path = None
        self._grabando = False

    def esta_grabando(self) -> bool:
        return self._grabando

    def iniciar(self) -> str | None:
        self.detener()
        fd, self._wav_path = tempfile.mkstemp(suffix=".wav", prefix="appstudy_rec_")
        os.close(fd)

        cmd = None
        if shutil.which("arecord"):
            cmd = ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", "-t", "wav", self._wav_path]
        elif shutil.which("pw-record"):
            cmd = ["pw-record", "--rate", "16000", "--channels", "1", self._wav_path]

        if not cmd:
            return None

        try:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._grabando = True
            return self._wav_path
        except Exception:
            self._grabando = False
            return None

    def detener(self) -> str | None:
        self._grabando = False
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=1.5)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None
        return self._wav_path
