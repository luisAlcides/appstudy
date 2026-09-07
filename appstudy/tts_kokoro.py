"""Sintetizador Kokoro: se ejecuta dentro del entorno aislado, no en la app.

AppStudy corre con el Python del sistema, que hoy es demasiado nuevo para las
ruedas de `onnxruntime`. Por eso Kokoro vive en su propio entorno
(`~/.local/share/appstudy/tts-venv`) y `voz.py` lo arranca como proceso aparte y
lo mantiene caliente: cargar el modelo cuesta medio segundo y no se puede pagar
en cada tarjeta.

Protocolo por la entrada/salida estándar. Una petición es una línea JSON:

    {"texto": "...", "voz": "em_santa", "idioma": "es", "velocidad": 1.0}

La respuesta es audio PCM de 16 bits, mono, 24 kHz, en tramas
`[uint32 tamaño][bytes]`, y una trama de tamaño 0 para cerrar la locución. Va
frase a frase según se genera, para que empiece a oírse cuanto antes.
"""
import json
import os
import re
import struct
import sys

BASE = os.path.expanduser("~/.local/share/appstudy/kokoro")
MODELO = os.path.join(BASE, "kokoro-v1.0.onnx")
VOCES = os.path.join(BASE, "voices-v1.0.bin")
SAMPLE_RATE = 24000
# El primer trozo se corta corto para que la voz arranque enseguida; los
# siguientes van más largos, que se generan más rápido que lo que dura oírlos.
PRIMER_TROZO = 90
MAX_CARACTERES = 220


def trozos(texto: str):
    """Parte el texto en frases y las agrupa en bloques de tamaño razonable."""
    frases = [f.strip() for f in re.split(r"(?<=[.!?:;])\s+", texto) if f.strip()]
    limite = PRIMER_TROZO
    bloque = ""
    for frase in frases:
        if bloque and len(bloque) + len(frase) + 1 > limite:
            yield bloque
            limite = MAX_CARACTERES
            bloque = frase
        else:
            bloque = f"{bloque} {frase}".strip()
    if bloque:
        yield bloque


def main() -> int:
    import numpy as np
    from kokoro_onnx import Kokoro

    kokoro = Kokoro(MODELO, VOCES)
    salida = sys.stdout.buffer

    def enviar(datos: bytes):
        salida.write(struct.pack("<I", len(datos)))
        if datos:
            salida.write(datos)
        salida.flush()

    for linea in sys.stdin:
        linea = linea.strip()
        if not linea:
            continue
        try:
            pet = json.loads(linea)
            texto = str(pet.get("texto", "")).strip()
            voz = str(pet.get("voz", "em_santa"))
            idioma = str(pet.get("idioma", "es"))
            velocidad = float(pet.get("velocidad", 1.0))
        except Exception:
            enviar(b"")
            continue

        lang = "en-us" if idioma.lower().startswith("en") else "es"
        try:
            for bloque in trozos(texto):
                audio, _sr = kokoro.create(bloque, voice=voz, speed=velocidad, lang=lang)
                pcm = np.clip(audio, -1.0, 1.0) * 32767.0
                enviar(pcm.astype("<i2").tobytes())
        except Exception:
            pass  # la app se queda sin audio y recurre a Piper
        try:
            enviar(b"")
        except BrokenPipeError:
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
