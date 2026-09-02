"""Los sonidos de Bit, sintetizados aquí mismo.

No hay ni un archivo de audio en el repositorio: los WAV se generan con la
biblioteca estándar (`wave` + un poco de trigonometría) la primera vez que hacen
falta y se guardan junto a la base de datos. Así el proyecto no engorda, se
pueden retocar cambiando dos números, y el volumen se aplica al sintetizar, que
funciona igual con cualquier reproductor.

Se reproducen con GSound (asíncrono, sin abrir procesos); si no está, se recurre
a `paplay`, `pw-play` o `aplay`. Si no hay ninguno, la aplicación funciona igual
de bien, solo que en silencio.
"""
import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path

from . import db

FRECUENCIA = 44100
VERSION = 1                     # se sube al cambiar la síntesis, para regenerar

# Notas, en hercios: la escala con la que están escritos los sonidos
RE4, MI4, SOL4, LA4, DO5, RE5, MI5, SOL5, LA5, DO6, MI6 = (
    293.66, 329.63, 392.00, 440.00, 523.25, 587.33, 659.25,
    783.99, 880.00, 1046.50, 1318.51)

# Cada sonido es una lista de (frecuencia, duración, volumen relativo).
# Cortos y suaves: esto suena en un escritorio todo el día.
SONIDOS = {
    "aviso":    [(MI5, 0.10, 0.7), (LA5, 0.16, 0.6)],                 # «oye, que te toca»
    "acierto":  [(DO5, 0.07, 0.6), (MI5, 0.07, 0.6), (SOL5, 0.16, 0.7)],
    "fallo":    [(LA4, 0.10, 0.6), (MI4, 0.20, 0.5)],
    "globo":    [(SOL5, 0.05, 0.35)],                                 # se abre el globo
    "clic":     [(RE5, 0.04, 0.30)],
    "dormir":   [(LA4, 0.14, 0.4), (SOL4, 0.14, 0.35), (RE4, 0.26, 0.3)],
    "celebra":  [(DO5, 0.07, 0.6), (MI5, 0.07, 0.6), (SOL5, 0.07, 0.6),
                 (DO6, 0.09, 0.65), (MI6, 0.22, 0.6)],
    "listo":    [(SOL5, 0.06, 0.45), (DO6, 0.14, 0.45)],              # la IA terminó
}


def carpeta() -> Path:
    return db.DATA_DIR / "sonidos"


# ----------------------------------------------------------------- síntesis

def _onda(freq: float, dur: float, vol: float) -> list:
    """Una nota: seno con un poco de tercer armónico y caída exponencial.

    El armónico le quita frialdad al seno puro y la caída evita el chasquido
    del corte seco. Los 6 ms de entrada hacen lo mismo al principio.
    """
    n = int(FRECUENCIA * dur)
    entrada = int(FRECUENCIA * 0.006)
    muestras = []
    for i in range(n):
        t = i / FRECUENCIA
        cuerpo = (math.sin(math.tau * freq * t)
                  + 0.22 * math.sin(math.tau * freq * 3 * t)
                  + 0.10 * math.sin(math.tau * freq * 2 * t))
        envolvente = math.exp(-3.4 * t / dur)
        if i < entrada:
            envolvente *= i / entrada
        muestras.append(cuerpo / 1.32 * envolvente * vol)
    return muestras


def _escribir(ruta: Path, notas, volumen: float):
    muestras = []
    for freq, dur, vol in notas:
        muestras.extend(_onda(freq, dur, vol * volumen))
    datos = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, m)) * 32000))
                     for m in muestras)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(FRECUENCIA)
        w.writeframes(datos)


def archivo(nombre: str, volumen: float) -> Path | None:
    """La ruta del WAV, generándolo si hace falta. None si el sonido no existe."""
    if nombre not in SONIDOS:
        return None
    paso = max(1, min(10, round(volumen * 10)))          # el volumen, en diez pasos
    ruta = carpeta() / f"{nombre}-v{VERSION}-{paso}.wav"
    if not ruta.exists():
        _escribir(ruta, SONIDOS[nombre], paso / 10)
    return ruta


def generar_todos(volumen: float = 0.7) -> int:
    return sum(1 for n in SONIDOS if archivo(n, volumen))


# ------------------------------------------------------------- reproducción

_contexto = None
_reproductor = "?"


def _gsound():
    """El contexto de GSound, creado una sola vez. None si no está disponible."""
    global _contexto, _reproductor
    if _contexto is None:
        try:
            import gi
            gi.require_version("GSound", "1.0")
            from gi.repository import GSound
            ctx = GSound.Context()
            ctx.init()
            _contexto, _reproductor = ctx, "gsound"
        except Exception:                       # sin GSound se tira de comandos
            _contexto, _reproductor = False, next(
                (c for c in ("paplay", "pw-play", "aplay") if shutil.which(c)), None)
    return _contexto or None


# ------------------------------------------------------------------ ajustes

def config(con) -> dict:
    try:
        volumen = float(db.get_meta(con, "sonido_volumen", 0.7))
    except (TypeError, ValueError):
        volumen = 0.7
    return {"activo": db.get_meta(con, "sonido_activo", "1") == "1",
            "volumen": max(0.0, min(1.0, volumen))}


def guardar(con, activo=None, volumen=None):
    if activo is not None:
        db.set_meta(con, "sonido_activo", "1" if activo else "0")
    if volumen is not None:
        db.set_meta(con, "sonido_volumen", round(max(0.0, min(1.0, volumen)), 2))


def reproducir(cfg: dict, nombre: str):
    """Suena, si el sonido está activado. Nunca bloquea ni revienta.

    `cfg` es lo que devuelve `config(con)`: se lee una vez y se guarda, para no
    consultar la base cada vez que la mascota pega un salto.
    """
    if not cfg or not cfg.get("activo"):
        return
    ruta = archivo(nombre, cfg.get("volumen", 0.7))
    if ruta is None:
        return
    try:
        ctx = _gsound()
        if ctx is not None:
            ctx.play_simple({"media.filename": str(ruta)})     # asíncrono
        elif _reproductor:
            subprocess.Popen([_reproductor, str(ruta)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass            # un sonido que no suena no es motivo para romper nada
