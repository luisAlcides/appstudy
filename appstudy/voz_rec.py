"""Reconocimiento de voz local (STT) y juicio de pronunciación con Bit.

Permite que el usuario responda tarjetas en voz alta al micrófono. Un motor
local (Vosk o Whisper.cpp) transcribe lo pronunciado, calcula la similitud con
la respuesta esperada y, opcionalmente, la IA local de Bit evalúa la calidad
fonética y conceptual para dar retroalimentación inmediata.
"""
from __future__ import annotations

import array
import collections
import difflib
import json
import math
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


def transcribir_con_palabras(ruta_wav: str, idioma: str = "es") -> tuple[str, list]:
    """Transcribe y además devuelve la confianza de cada palabra.

    Vosk da una puntuación por palabra: es lo que permite distinguir entre
    decir otra cosa y decir lo correcto pero mal pronunciado. Con otros motores
    no hay confianzas y se devuelve la lista vacía.
    """
    if not os.path.isfile(ruta_wav):
        return "", []
    try:
        import vosk
        modelo = _obtener_modelo_vosk(idioma)
        if modelo is None:
            return transcribir_audio(ruta_wav, idioma=idioma), []
        wf = wave.open(ruta_wav, "rb")
        rec = vosk.KaldiRecognizer(modelo, wf.getframerate())
        rec.SetWords(True)
        palabras, textos = [], []

        def acumular(crudo):
            r = json.loads(crudo)
            if r.get("text"):
                textos.append(r["text"])
            for w in r.get("result", []):
                palabras.append({"palabra": w.get("word", ""),
                                 "conf": float(w.get("conf", 0.0))})

        while True:
            datos = wf.readframes(4000)
            if not datos:
                break
            if rec.AcceptWaveform(datos):
                acumular(rec.Result())
        acumular(rec.FinalResult())
        wf.close()
        return " ".join(textos).strip(), palabras
    except Exception:
        return transcribir_audio(ruta_wav, idioma=idioma), []


# Por debajo de esto se considera que la palabra salió dudosa, aunque el motor
# la reconociera: es el hueco entre «lo dijo» y «se le entendió».
CONF_BIEN = 0.80
CONF_FLOJA = 0.45


def _palabras(texto: str) -> list:
    return re.findall(r"[a-záéíóúñüA-ZÁÉÍÓÚÑÜ']+", (texto or "").lower())


def evaluar_pronunciacion(esperado: str, palabras: list, dicho: str = "") -> dict:
    """Compara palabra por palabra lo que se esperaba oír con lo que se oyó.

    No mide si la respuesta es correcta —de eso va `juzgar_respuesta`—, sino si
    se entiende al decirla: qué palabras salieron limpias, cuáles dudosas y
    cuáles no se reconocieron. Devuelve una nota de 0 a 100 y el detalle para
    pintarlo palabra a palabra.
    """
    objetivo = _palabras(voz.limpiar_para_voz(esperado))
    if not objetivo:
        return {"nota": 0, "detalle": [], "repasar": [], "veredicto": "Nada que comparar."}

    oidas = [p["palabra"].lower() for p in palabras] if palabras else _palabras(dicho)
    confianzas = [p.get("conf", 1.0) for p in palabras] if palabras else [1.0] * len(oidas)

    detalle = [{"palabra": p, "estado": "mal", "conf": 0.0} for p in objetivo]
    for bloque in difflib.SequenceMatcher(None, objetivo, oidas).get_matching_blocks():
        for k in range(bloque.size):
            conf = confianzas[bloque.b + k] if bloque.b + k < len(confianzas) else 1.0
            detalle[bloque.a + k] = {
                "palabra": objetivo[bloque.a + k],
                "estado": "bien" if conf >= CONF_BIEN else
                          ("floja" if conf >= CONF_FLOJA else "mal"),
                "conf": round(conf, 2),
            }

    puntos = {"bien": 1.0, "floja": 0.55, "mal": 0.0}
    nota = round(100 * sum(puntos[d["estado"]] for d in detalle) / len(detalle))
    repasar = [d["palabra"] for d in detalle if d["estado"] != "bien"]

    if nota >= 90:
        veredicto = "Se te entiende perfectamente."
    elif nota >= 70:
        veredicto = "Bien, aunque un par de palabras salieron dudosas."
    elif nota >= 40:
        veredicto = "Se entiende a medias: repite despacio las marcadas."
    else:
        veredicto = "No se te entendió; prueba otra vez más cerca del micrófono."
    return {"nota": nota, "detalle": detalle, "repasar": repasar, "veredicto": veredicto}


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


# --------------------------------------------------- conversación manos libres

RATE_ESCUCHA = 16000
BLOQUE = 4000  # muestras por lectura (~125 ms a 16 kHz)


class DetectorTurnos:
    """Decide cuándo has terminado de hablar, midiendo la energía del micrófono.

    Es lo que sustituye al botón de «he terminado»: mientras hablas acumula, y
    cuando llevas `silencio_fin` segundos callado da el turno por cerrado. El
    umbral no es fijo porque ningún micrófono ni ninguna habitación se parecen:
    se calcula sobre el ruido de fondo que va midiendo, y así funciona igual en
    un cuarto silencioso que con un ventilador al lado.
    """

    def __init__(self, rate: int = RATE_ESCUCHA, silencio_fin: float = 1.0,
                 minimo_habla: float = 0.4, maximo_turno: float = 30.0):
        self.rate = rate
        self.silencio_fin = silencio_fin
        self.minimo_habla = minimo_habla
        self.maximo_turno = maximo_turno
        self.reiniciar()

    def reiniciar(self):
        # El suelo de ruido es el mínimo de los últimos ~10 s. Un ventilador
        # constante entra entero en esa ventana y sube el suelo; una persona
        # hablando no, porque entre palabra y palabra deja huecos que lo bajan.
        self.ventana = collections.deque(maxlen=80)
        self.hablando = False
        self.seg_habla = 0.0
        self.seg_silencio = 0.0
        self.seg_total = 0.0

    @staticmethod
    def energia(bloque: bytes) -> float:
        """Valor eficaz (RMS) del bloque de audio PCM de 16 bits."""
        if len(bloque) < 2:
            return 0.0
        muestras = array.array("h")
        muestras.frombytes(bloque[:len(bloque) - (len(bloque) % 2)])
        if not muestras:
            return 0.0
        return math.sqrt(sum(m * m for m in muestras) / len(muestras))

    @property
    def ruido(self) -> float:
        return min(self.ventana) if self.ventana else 120.0

    @property
    def umbral(self) -> float:
        # Tres veces el ruido de fondo, con un mínimo para que un micrófono
        # mudo no dispare turnos fantasma.
        return max(300.0, self.ruido * 3.0)

    def procesar(self, bloque: bytes) -> str:
        """Devuelve 'silencio', 'hablando' o 'fin' según lo que lleve oído."""
        dur = (len(bloque) / 2) / self.rate
        self.seg_total += dur
        rms = self.energia(bloque)
        umbral = self.umbral
        self.ventana.append(rms)

        if rms > umbral:
            self.hablando = True
            self.seg_habla += dur
            self.seg_silencio = 0.0
            # Un turno no puede durar para siempre: si el micrófono lleva medio
            # minuto con energía (una charla de fondo, una tele), se corta y se
            # transcribe lo que haya en vez de no entregar nunca el turno.
            return "fin" if self.seg_total >= self.maximo_turno else "hablando"

        if not self.hablando:
            return "silencio"

        self.seg_silencio += dur
        if self.seg_silencio >= self.silencio_fin:
            return "fin" if self.seg_habla >= self.minimo_habla else "silencio"
        if self.seg_total >= self.maximo_turno:
            return "fin"
        return "hablando"


class EscuchaContinua:
    """Micrófono siempre abierto: entrega lo que dices, turno a turno.

    Mientras Bit habla se deja de escuchar, para no transcribir sus propias
    palabras saliendo por los altavoces.
    """

    def __init__(self, idioma: str = "es", al_estado=None, al_oir=None):
        self.idioma = idioma
        self.al_estado = al_estado          # 'escuchando' | 'hablando' | 'procesando'
        self.al_oir = al_oir                # recibe el texto de cada turno
        self._proc = None
        self._hilo = None
        self._activa = False
        self._pausada = False
        self.detector = DetectorTurnos()

    @staticmethod
    def _comando() -> list | None:
        if shutil.which("arecord"):
            return ["arecord", "-q", "-f", "S16_LE", "-r", str(RATE_ESCUCHA),
                    "-c", "1", "-t", "raw"]
        if shutil.which("pw-record"):
            return ["pw-record", "--rate", str(RATE_ESCUCHA), "--channels", "1",
                    "--format", "s16", "--raw", "-"]
        return None

    def esta_activa(self) -> bool:
        return self._activa

    def pausar(self):
        """Se deja de escuchar (Bit está hablando)."""
        self._pausada = True

    def reanudar(self):
        self.detector.reiniciar()
        self._pausada = False
        self._avisar("escuchando")

    def _avisar(self, estado: str):
        if self.al_estado:
            try:
                self.al_estado(estado)
            except Exception:
                pass

    def iniciar(self) -> bool:
        cmd = self._comando()
        if not cmd or self._activa:
            return False
        try:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                          stderr=subprocess.DEVNULL)
        except Exception:
            self._proc = None
            return False
        self._activa = True
        self._pausada = False
        self.detector.reiniciar()
        self._hilo = threading.Thread(target=self._escuchar, daemon=True)
        self._hilo.start()
        self._avisar("escuchando")
        return True

    def detener(self):
        self._activa = False
        proc, self._proc = self._proc, None
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=1.5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _escuchar(self):
        proc = self._proc
        acumulado = bytearray()
        # Se lee hasta que la tubería se cierre, no hasta que el proceso muera:
        # cuando termina la grabación puede quedar audio sin leer en el buffer.
        while self._activa and proc:
            try:
                bloque = proc.stdout.read(BLOQUE * 2)
            except Exception:
                break
            if not bloque:
                break
            if self._pausada:
                acumulado.clear()       # lo que sonó mientras hablaba Bit se tira
                self.detector.reiniciar()
                continue

            estado = self.detector.procesar(bloque)
            if estado in ("hablando", "fin"):
                acumulado.extend(bloque)
            if estado != "fin":
                continue

            audio = bytes(acumulado)
            acumulado.clear()
            self.detector.reiniciar()
            self.pausar()               # no se escucha mientras se piensa
            self._avisar("procesando")
            texto = self._transcribir(audio)
            if texto and self.al_oir:
                try:
                    self.al_oir(texto)
                except Exception:
                    pass
            elif self._activa:
                self.reanudar()         # no se entendió nada: seguimos a la escucha

    def _transcribir(self, pcm: bytes) -> str:
        """Pasa el turno grabado a texto con el motor que haya."""
        if not pcm:
            return ""
        fd, ruta = tempfile.mkstemp(suffix=".wav", prefix="appstudy_turno_")
        os.close(fd)
        try:
            with wave.open(ruta, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(RATE_ESCUCHA)
                wf.writeframes(pcm)
            return transcribir_audio(ruta, idioma=self.idioma)
        except Exception:
            return ""
        finally:
            try:
                os.unlink(ruta)
            except OSError:
                pass


# ------------------------------------------------------ palabra clave: «hola bit»

PALABRA_CLAVE = "hola bit"
# Vosk no siempre acierta con «bit» —suena a «vit», a «bip»—, así que se dan por
# buenas las confusiones habituales en vez de exigir la transcripción exacta.
# «hey» y «beat» se probaron y se quitaron: son tan comunes en audio
# cualquiera que despertaban a Bit sola con una frase de fondo.
INICIOS_CLAVE = ("hola", "ola", "oye")
NOMBRES_CLAVE = ("bit", "vit", "bip", "bid")
# Frases señuelo: con una gramática cerrada el motor mete a la fuerza lo que oye
# en la frase más parecida, así que «hola buenos días» acabaría siendo «hola bit».
# Dándole sitios donde caer, cada cosa va a su sitio y no salta la palabra clave.
SENUELOS_CLAVE = ("hola", "buenos días", "buenas tardes", "qué tal", "cómo estás",
                  "adiós", "hasta luego", "gracias", "sí", "no", "vale", "bueno")


def gramatica_clave() -> str:
    """La lista cerrada de frases que el reconocedor puede devolver."""
    frases = [f"{inicio} {nombre}" for inicio in INICIOS_CLAVE for nombre in NOMBRES_CLAVE]
    return json.dumps([*frases, *SENUELOS_CLAVE, "[unk]"], ensure_ascii=False)


def es_palabra_clave(texto: str) -> bool:
    """Cierto si en lo oído aparece un saludo seguido del nombre de Bit."""
    palabras = re.findall(r"[a-záéíóúñü]+", (texto or "").lower())
    return any(a in INICIOS_CLAVE and b in NOMBRES_CLAVE
               for a, b in zip(palabras, palabras[1:]))


class EscuchaPalabraClave:
    """Micrófono en reposo, esperando a que digas «hola bit».

    No transcribe lo que se habla en la habitación: el reconocedor solo puede
    devolver las frases de `gramatica_clave()`, así que todo lo demás sale como
    desconocido y se descarta. Nada de esto sale del equipo.
    """

    def __init__(self, idioma: str = "es", al_activar=None):
        self.idioma = idioma
        self.al_activar = al_activar
        self._proc = None
        self._hilo = None
        self._activa = False

    @staticmethod
    def disponible(idioma: str = "es") -> bool:
        try:
            import vosk  # noqa: F401
        except ImportError:
            return False
        return _obtener_modelo_vosk(idioma) is not None and bool(EscuchaContinua._comando())

    def esta_activa(self) -> bool:
        return self._activa

    def iniciar(self) -> bool:
        if self._activa or not self.disponible(self.idioma):
            return False
        cmd = EscuchaContinua._comando()
        if not cmd:
            return False
        try:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                          stderr=subprocess.DEVNULL)
        except Exception:
            self._proc = None
            return False
        self._activa = True
        self._hilo = threading.Thread(target=self._vigilar, daemon=True)
        self._hilo.start()
        return True

    def detener(self):
        self._activa = False
        proc, self._proc = self._proc, None
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=1.5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _vigilar(self):
        import vosk
        modelo = _obtener_modelo_vosk(self.idioma)
        if modelo is None:
            self._activa = False
            return
        rec = vosk.KaldiRecognizer(modelo, RATE_ESCUCHA, gramatica_clave())
        proc = self._proc
        while self._activa and proc:
            try:
                bloque = proc.stdout.read(BLOQUE * 2)
            except Exception:
                break
            if not bloque:
                break
            # Solo se miran los resultados cerrados, nunca los parciales: un
            # parcial pasa por «hola bit» a mitad de otra frase y despertaría a
            # Bit en medio de una conversación ajena.
            try:
                if not rec.AcceptWaveform(bloque):
                    continue
                texto = json.loads(rec.Result()).get("text", "")
            except Exception:
                continue
            if not es_palabra_clave(texto):
                continue
            rec.Reset()
            self._activa = False
            if self.al_activar:
                try:
                    self.al_activar()
                except Exception:
                    pass
            return
