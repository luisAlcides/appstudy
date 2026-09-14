"""El cuaderno de bitácora: dónde va a parar lo que falla por debajo.

Hay cosas que no pueden interrumpirte. Que el sintetizador de voz no arranque,
que la transcripción se quede en blanco, que la página del curso no acepte el
JavaScript que mide tu progreso: la aplicación sigue, porque pararla sería peor.
Pero «sigue» no puede querer decir «nadie se entera nunca». Cuando alguien
escribe que Bit no le habla, tiene que haber un sitio donde mirar.

Ese sitio es `~/.local/share/appstudy/appstudy.log`. En marcha normal solo
recoge avisos —lo que el usuario pidió y no ocurrió—; con la variable de entorno
`APPSTUDY_DEBUG` puesta recoge también el detalle de las limpiezas y los
procesos, que es lo que hace falta para seguir un fallo raro.

Mientras nadie llame a `configurar()` esto no escribe en ningún sitio: importar
`appstudy` desde una prueba o desde una herramienta no crea ficheros.
"""
import logging
import os
from logging.handlers import RotatingFileHandler

NOMBRE = "appstudy"
ARCHIVO = "appstudy.log"
MAX_BYTES = 1024 * 1024
COPIAS = 3

_raiz = logging.getLogger(NOMBRE)
_raiz.addHandler(logging.NullHandler())
_raiz.propagate = False
_configurado = False


def log(modulo: str) -> logging.Logger:
    """El cuaderno de un módulo. `registro.log(__name__)` y a escribir."""
    corto = modulo.rsplit(".", 1)[-1]
    return logging.getLogger(f"{NOMBRE}.{corto}")


def configurar(carpeta=None) -> logging.Logger:
    """Abre el cuaderno en disco. Se llama una vez, al arrancar la aplicación."""
    global _configurado
    if _configurado:
        return _raiz
    if carpeta is None:
        from . import db
        carpeta = db.DATA_DIR
    detalle = bool(os.environ.get("APPSTUDY_DEBUG"))
    _raiz.setLevel(logging.DEBUG if detalle else logging.WARNING)
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        manejador = RotatingFileHandler(carpeta / ARCHIVO, maxBytes=MAX_BYTES,
                                        backupCount=COPIAS, encoding="utf-8")
    except OSError:
        # Sin sitio donde escribir se sigue sin cuaderno: no arrancar por esto
        # sería exactamente el error que este módulo intenta evitar.
        return _raiz
    manejador.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s: %(message)s"))
    _raiz.addHandler(manejador)
    _configurado = True
    return _raiz
