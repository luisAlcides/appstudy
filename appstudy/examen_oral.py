"""Examen oral con Bit: te pregunta hablando y te califica lo que respondes.

La diferencia con el examen escrito de `examen.py` es lo que mide. Allí eliges
una opción; aquí tienes que explicarlo con tus palabras, que es lo que se pide
en un taller cuando alguien pregunta por qué falla un alternador. Se apoya en
la tarjeta como verdad de referencia, así que la nota es de tu temario y no de
lo que el modelo crea recordar.

El módulo es solo el motor —elegir tarjetas, llevar la cuenta, cerrar el acta—
y no sabe nada de ventanas: la parte hablada la pone `pet.py`, que ya tiene el
micrófono y la voz.
"""
import re
import time
import unicodedata

from . import db, ia, util

# Cuántas preguntas trae un examen de una sentada. Con más, la nota deja de
# subir y lo que baja es la atención.
PREGUNTAS_POR_DEFECTO = 5

# A partir de aquí se da por sabida la pregunta. No es el 50 %: en un oral
# responder a medias es no responder, y el 60 aprueba raspado.
APROBADO = 60


def tarjetas_para_examen(con, deck_key: str | None = None, level: int | None = None,
                         cuantas: int = PREGUNTAS_POR_DEFECTO) -> list:
    """Elige de qué te va a preguntar: lo que ya estudiaste alguna vez.

    Se descartan las que nunca has visto —examinarte de lo que no has abierto
    no mide nada— y se prefieren las que llevas más tiempo sin repasar, que son
    justo de las que menos te acuerdas.
    """
    where = ["d.enabled=1", "s.reps > 0"]
    args: list = []
    if deck_key:
        where.append("d.key=?")
        args.append(deck_key)
    if level:
        where.append("c.level=?")
        args.append(level)
    filas = con.execute(
        f"""SELECT c.*, d.key AS deck_key, d.name AS deck_name, s.reps, s.last
            FROM cards c JOIN decks d ON d.id=c.deck_id JOIN state s ON s.card_id=c.id
            WHERE {' AND '.join(where)}
            ORDER BY s.last ASC LIMIT ?""", (*args, max(1, cuantas) * 4)).fetchall()
    tarjetas = [dict(f) for f in filas]
    return tarjetas[:max(1, cuantas)]


# Formas de decir «no lo sé». Un modelo pequeño califica con la manga muy
# ancha: a un «ni idea» le ponía un 60 y aprobaba, porque leía la referencia y
# se le pegaba lo que ahí decía. Esto no se le pregunta al modelo.
NO_RESPUESTAS = (
    "no se", "no lo se", "ni idea", "no me acuerdo", "no recuerdo", "nada",
    "paso", "no tengo ni idea", "no sabria decir", "no sabria", "sin idea",
    "no estoy seguro", "no se nada", "no me se esa", "siguiente",
)


def es_no_respuesta(texto: str) -> bool:
    """Cierto si lo dicho es un «no lo sé» y no un intento de responder."""
    limpio = "".join(c for c in unicodedata.normalize("NFD", (texto or "").lower())
                     if unicodedata.category(c) != "Mn")
    limpio = re.sub(r"[^a-z0-9 ]+", " ", limpio)
    limpio = re.sub(r"\s+", " ", limpio).strip()
    if not limpio:
        return True
    if limpio in NO_RESPUESTAS:
        return True
    # «pues no me acuerdo la verdad»: se admite algo de relleno alrededor
    return len(limpio.split()) <= 6 and any(
        limpio.startswith(n) or limpio.endswith(n) for n in NO_RESPUESTAS)


class ExamenOral:
    """Lleva la cuenta de un examen: por dónde va, qué se preguntó y qué notas.

    No habla ni escucha: quien lo usa le pasa lo que el estudiante respondió y
    recibe la calificación. Así se puede probar entero sin micrófono.
    """

    def __init__(self, con, cfg_ia: dict, tarjetas: list):
        self.con = con
        self.cfg_ia = cfg_ia
        self.tarjetas = list(tarjetas)
        self.indice = 0
        self.pregunta_actual = ""
        self.resultados: list[dict] = []

    # ------------------------------------------------------------- estado

    def terminado(self) -> bool:
        return self.indice >= len(self.tarjetas)

    @property
    def total(self) -> int:
        return len(self.tarjetas)

    @property
    def tarjeta(self) -> dict | None:
        return None if self.terminado() else self.tarjetas[self.indice]

    def marcador(self) -> str:
        return f"Pregunta {min(self.indice + 1, self.total)} de {self.total}"

    # ------------------------------------------------------------- examen

    def siguiente_pregunta(self) -> str:
        """La pregunta hablada de la tarjeta en turno."""
        card = self.tarjeta
        if card is None:
            return ""
        try:
            self.pregunta_actual = ia.preguntar_de_viva_voz(
                self.cfg_ia, card, [r["pregunta"] for r in self.resultados])
        except Exception:
            # Sin IA o si falla, se pregunta el frente tal cual: peor examen,
            # pero examen al fin y al cabo.
            self.pregunta_actual = util.plain(card["front"])
        return self.pregunta_actual

    def responder(self, respuesta: str) -> dict:
        """Califica lo respondido y avanza. Devuelve el resultado de esta pregunta."""
        card = self.tarjeta
        if card is None:
            return {}
        respuesta = (respuesta or "").strip()
        if es_no_respuesta(respuesta):
            fallo = {"nota": 0,
                     "veredicto": "No te he oído responder; esta se queda a cero.",
                     "falto": util.plain(card["back"])[:120]}
        else:
            try:
                fallo = ia.calificar_respuesta(self.cfg_ia, card,
                                               self.pregunta_actual, respuesta)
            except Exception:
                fallo = {"nota": 0, "veredicto": "No he podido calificar esta respuesta.",
                         "falto": ""}
        resultado = {**fallo, "card_id": card["id"], "pregunta": self.pregunta_actual,
                     "respuesta": respuesta, "deck_name": card.get("deck_name", ""),
                     "front": util.plain(card["front"])}
        self.resultados.append(resultado)
        self.indice += 1
        return resultado

    # -------------------------------------------------------------- acta

    def nota_media(self) -> int:
        if not self.resultados:
            return 0
        return round(sum(r["nota"] for r in self.resultados) / len(self.resultados))

    def flojas(self) -> list[dict]:
        """Las preguntas que no llegaron al aprobado, de peor a mejor."""
        return sorted((r for r in self.resultados if r["nota"] < APROBADO),
                      key=lambda r: r["nota"])

    def acta(self) -> dict:
        """El resumen final: nota, cuántas aprobaste y qué repasar."""
        media = self.nota_media()
        aprobadas = sum(1 for r in self.resultados if r["nota"] >= APROBADO)
        if media >= 90:
            juicio = "Te lo sabes. Poco que añadir."
        elif media >= APROBADO:
            juicio = "Aprobado, con cosas que pulir."
        elif media >= 40:
            juicio = "A medias: lo tienes leído, no explicado."
        else:
            juicio = "Toca volver sobre esto antes de examinarte de verdad."
        return {"nota": media, "aprobadas": aprobadas, "total": len(self.resultados),
                "juicio": juicio, "flojas": self.flojas(), "resultados": list(self.resultados)}

    def guardar(self):
        """Deja el acta en la base, para verla luego en las estadísticas."""
        acta = self.acta()
        historial = db.get_meta(self.con, "examenes_orales", "") or ""
        lineas = [l for l in historial.split("\n") if l.strip()][-19:]
        lineas.append(f"{int(time.time())}|{acta['nota']}|{acta['aprobadas']}/{acta['total']}")
        db.set_meta(self.con, "examenes_orales", "\n".join(lineas))
        return acta


def historial(con) -> list[dict]:
    """Los últimos exámenes orales: fecha, nota y aciertos."""
    crudo = db.get_meta(con, "examenes_orales", "") or ""
    salida = []
    for linea in crudo.split("\n"):
        partes = linea.strip().split("|")
        if len(partes) != 3:
            continue
        try:
            salida.append({"ts": float(partes[0]), "nota": int(partes[1]),
                           "aciertos": partes[2]})
        except ValueError:
            continue
    return salida
