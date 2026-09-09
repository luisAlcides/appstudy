"""Plan y reloj de lectura guiada, independientes de GTK."""
import math
import re
import time


def secciones(body, titulo):
    """Agrupa por encabezados sin perder bloques ni su orden."""
    resultado = []
    actual = {"titulo": titulo, "body": []}
    for bloque in body:
        for tipo, contenido in bloque.items():
            if tipo == "h" and actual["body"]:
                resultado.append(actual)
                actual = {"titulo": titulo, "body": []}
            if tipo == "h":
                actual["titulo"] = re.sub(r"<[^>]+>", "", str(contenido))
            actual["body"].append({tipo: contenido})
    if actual["body"]:
        resultado.append(actual)
    return resultado


def _peso(valor):
    if isinstance(valor, dict):
        return sum(_peso(v) for k, v in valor.items() if k not in ("url", "lang"))
    if isinstance(valor, list):
        return sum(map(_peso, valor))
    return len(re.sub(r"<[^>]+>", "", str(valor)).split())


class SesionGuiada:
    def __init__(self, partes, minutos, reloj=time.monotonic):
        if not partes or not math.isfinite(minutos) or not 1 <= minutos <= 180:
            raise ValueError("Elige una lectura con contenido y entre 1 y 180 minutos.")
        self.partes = partes
        self.duracion = minutos * 60
        self.reloj = reloj
        self.acumulado = 0.0
        self.inicio = None
        pesos = [max(1, _peso(p["body"])) for p in partes]
        self.limites = []
        limite = 0
        for peso in pesos:
            limite += self.duracion * .85 * peso / sum(pesos)
            self.limites.append(limite)

    @property
    def transcurrido(self):
        delta = self.reloj() - self.inicio if self.inicio is not None else 0
        return min(self.duracion, self.acumulado + max(0, delta))

    @property
    def terminado(self):
        return self.transcurrido >= self.duracion

    @property
    def indice(self):
        pasado = self.transcurrido
        return next((i for i, fin in enumerate(self.limites) if pasado < fin),
                    len(self.partes))

    def iniciar(self):
        if self.inicio is None and not self.terminado:
            self.inicio = self.reloj()

    def pausar(self):
        self.acumulado = self.transcurrido
        self.inicio = None

