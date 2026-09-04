"""Sesiones de estudio acotadas por tiempo y cantidad de tarjetas.

El estado vive solo en memoria: los repasos ya se guardan en ``log`` y no hace
falta duplicarlos en SQLite. Así el contador es barato y cerrar una sesión a
mitad no deja datos incompletos que migrar o reparar.
"""
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    minutos: int
    tarjetas: int
    nombre: str


PLANES = (
    Plan(5, 8, "Pausa corta"),
    Plan(15, 20, "Sesión diaria"),
    Plan(25, 35, "Concentración"),
)


class Sesion:
    """Progreso y resumen de una sesión, sin dependencias de interfaz o base."""

    def __init__(self, plan: Plan, ahora: float | None = None):
        self.plan = plan
        self.inicio = time.time() if ahora is None else float(ahora)
        self.limite = self.inicio + plan.minutos * 60
        self.meta = plan.tarjetas
        self.respuestas: list[dict] = []

    def registrar(self, tarjeta: dict, nota: int, ms: int, ahora: float | None = None):
        """Guarda únicamente lo necesario para el resumen de esta ventana."""
        self.respuestas.append({
            "card_id": tarjeta["id"],
            "deck": tarjeta.get("deck_name", "Sin mazo"),
            "tags": tarjeta.get("tags", ""),
            "nueva": int(tarjeta.get("reps", 0) == 0),
            "nota": int(nota),
            "ms": max(0, int(ms)),
            "ts": time.time() if ahora is None else float(ahora),
        })

    def deshacer_ultima(self, card_id: int | None = None):
        """Quita del resumen el repaso que también se deshizo en el planificador."""
        for i in range(len(self.respuestas) - 1, -1, -1):
            if card_id is None or self.respuestas[i]["card_id"] == card_id:
                return self.respuestas.pop(i)
        return None

    def restantes(self, ahora: float | None = None) -> int:
        ahora = time.time() if ahora is None else float(ahora)
        return max(0, int(self.limite - ahora))

    def terminada(self, ahora: float | None = None) -> bool:
        # Nunca se interrumpe una tarjeta a mitad ni se muestra un resumen vacío.
        return bool(self.respuestas) and (
            len(self.respuestas) >= self.meta or self.restantes(ahora) <= 0)

    def progreso(self, ahora: float | None = None) -> str:
        segundos = self.restantes(ahora)
        return (f"{len(self.respuestas)}/{self.meta} tarjetas · "
                f"{segundos // 60:02d}:{segundos % 60:02d}")

    def ampliar(self, minutos: int = 5, tarjetas: int = 8,
                ahora: float | None = None):
        ahora = time.time() if ahora is None else float(ahora)
        self.limite = max(self.limite, ahora) + max(1, minutos) * 60
        self.meta += max(1, tarjetas)

    def resumen(self) -> dict:
        total = len(self.respuestas)
        recordadas = sum(r["nota"] > 0 for r in self.respuestas)
        nuevas = sum(r["nueva"] for r in self.respuestas)
        tiempos = [r["ms"] for r in self.respuestas if 250 <= r["ms"] <= 30 * 60 * 1000]

        # Un fallo pesa 2 y una respuesta difícil 1. Se agrupa en una sola pasada;
        # el coste depende solo de las pocas tarjetas de esta sesión.
        debilidad: dict[str, dict[str, int]] = {}
        for r in self.respuestas:
            peso = 2 if r["nota"] == 0 else 1 if r["nota"] == 1 else 0
            if not peso:
                continue
            temas = [t.strip() for t in r["tags"].split(",") if t.strip()] or [r["deck"]]
            for tema in temas:
                dato = debilidad.setdefault(tema, {"puntos": 0, "apariciones": 0})
                dato["puntos"] += peso
                dato["apariciones"] += 1

        tema_debil = None
        if debilidad:
            tema_debil, dato = max(
                debilidad.items(), key=lambda x: (x[1]["puntos"], x[1]["apariciones"], x[0]))
            tema_debil = {"tema": tema_debil, **dato}

        if not total:
            consejo = "Empieza con una tarjeta: el resumen se construye mientras estudias."
        elif recordadas / total < 0.65:
            consejo = "Conviene una sesión corta de repaso antes de añadir material nuevo."
        elif tema_debil:
            consejo = f"El próximo repaso debería empezar por «{tema_debil['tema']}»."
        else:
            consejo = "Buen ritmo: puedes continuar o dejar que FSRS programe el siguiente repaso."

        return {
            "total": total,
            "recordadas": recordadas,
            "retencion": recordadas / total if total else None,
            "nuevas": nuevas,
            "mediana_ms": int(statistics.median(tiempos)) if tiempos else 0,
            "tema_debil": tema_debil,
            "consejo": consejo,
        }
