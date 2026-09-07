"""Mapas de conexión: preguntar por las relaciones, no por las definiciones.

Una tarjeta pregunta piezas sueltas. Saber qué es un alternador y saber qué es
una batería no es saber por qué el motor se para cuando falla el alternador, y
eso último es lo que se usa en el taller. Aquí se juntan dos tarjetas del mismo
tema y se pregunta qué tienen que ver.

Emparejar bien es la mitad del ejercicio: dos tarjetas del mismo capítulo casi
siempre tienen algo que ver, dos de mazos distintos casi nunca. Por eso los
pares salen del mismo mazo y se prefieren las que comparten etiquetas o nivel.
"""
import random

from . import ia, util

PREGUNTAS_POR_DEFECTO = 3
APROBADO = 60


def _etiquetas(card: dict) -> set:
    return {t.strip().lower() for t in (card.get("tags") or "").replace(";", ",").split(",")
            if t.strip()}


def afinidad(uno: dict, otro: dict) -> int:
    """Cuánto prometen dos tarjetas como pareja. Más alto, mejor pregunta."""
    if uno["id"] == otro["id"] or uno["deck_id"] != otro["deck_id"]:
        return 0
    puntos = 1                                    # mismo mazo, algo es
    comunes = _etiquetas(uno) & _etiquetas(otro)
    puntos += 3 * len(comunes)
    if uno.get("level") == otro.get("level"):
        puntos += 2
    # Palabras largas compartidas entre los enunciados: suelen ser el término
    # técnico que las une, y es lo que hace que la pregunta tenga sentido.
    def palabras(c):
        texto = f"{util.plain(c['front'])} {util.plain(c['back'])}".lower()
        return {p for p in texto.split() if len(p) > 5}
    puntos += min(4, len(palabras(uno) & palabras(otro)))
    return puntos


def pares(con, deck_key: str | None = None, cuantos: int = PREGUNTAS_POR_DEFECTO) -> list:
    """Elige parejas de tarjetas ya estudiadas que den juego juntas."""
    where = ["d.enabled=1", "s.reps > 0"]
    args: list = []
    if deck_key:
        where.append("d.key=?")
        args.append(deck_key)
    filas = con.execute(
        f"""SELECT c.*, d.key AS deck_key, d.name AS deck_name
            FROM cards c JOIN decks d ON d.id=c.deck_id JOIN state s ON s.card_id=c.id
            WHERE {' AND '.join(where)}
            ORDER BY s.last DESC LIMIT 40""", args).fetchall()
    tarjetas = [dict(f) for f in filas]
    if len(tarjetas) < 2:
        return []

    candidatos = []
    for i, uno in enumerate(tarjetas):
        for otro in tarjetas[i + 1:]:
            punt = afinidad(uno, otro)
            if punt > 1:              # con solo compartir mazo no hay pregunta
                candidatos.append((punt, uno, otro))
    if not candidatos:
        return []

    candidatos.sort(key=lambda c: -c[0])
    # Del montón bueno se sortea, para que dos sesiones seguidas no sean iguales;
    # el resto queda detrás por orden de afinidad para completar la ronda si las
    # mejores parejas se pisan entre sí y se quedarían menos preguntas de las
    # pedidas.
    mejores = candidatos[:max(cuantos * 3, 6)]
    random.shuffle(mejores)
    orden = mejores + candidatos[len(mejores):]

    elegidos, usadas = [], set()
    for _, uno, otro in orden:
        if uno["id"] in usadas or otro["id"] in usadas:
            continue                   # que no se repita la misma tarjeta en la sesión
        elegidos.append((uno, otro))
        usadas.update({uno["id"], otro["id"]})
        if len(elegidos) >= cuantos:
            break
    return elegidos


class SesionConexiones:
    """Lleva la cuenta de una ronda de preguntas de relación."""

    def __init__(self, con, cfg_ia: dict, parejas: list):
        self.con = con
        self.cfg_ia = cfg_ia
        self.parejas = list(parejas)
        self.indice = 0
        self.pregunta_actual = ""
        self.resultados: list[dict] = []

    def terminado(self) -> bool:
        return self.indice >= len(self.parejas)

    @property
    def total(self) -> int:
        return len(self.parejas)

    @property
    def pareja(self):
        return None if self.terminado() else self.parejas[self.indice]

    def marcador(self) -> str:
        return f"Conexión {min(self.indice + 1, self.total)} de {self.total}"

    def siguiente_pregunta(self) -> str:
        pareja = self.pareja
        if pareja is None:
            return ""
        uno, otro = pareja
        try:
            self.pregunta_actual = ia.pregunta_de_conexion(self.cfg_ia, uno, otro)
        except Exception:
            # Sin IA se pregunta en crudo: peor redactado, mismo ejercicio.
            self.pregunta_actual = (f"¿Qué relación hay entre «{util.plain(uno['front'])}» "
                                    f"y «{util.plain(otro['front'])}»?")
        return self.pregunta_actual

    def responder(self, respuesta: str) -> dict:
        from .examen_oral import es_no_respuesta
        pareja = self.pareja
        if pareja is None:
            return {}
        uno, otro = pareja
        respuesta = (respuesta or "").strip()
        if es_no_respuesta(respuesta):
            fallo = {"nota": 0, "veredicto": "Esta te la dejas sin contestar.", "falto": ""}
        else:
            try:
                fallo = ia.calificar_conexion(self.cfg_ia, uno, otro,
                                              self.pregunta_actual, respuesta)
            except Exception:
                fallo = {"nota": 0, "veredicto": "No he podido calificar esta respuesta.",
                         "falto": ""}
        resultado = {**fallo, "pregunta": self.pregunta_actual, "respuesta": respuesta,
                     "entre": (util.plain(uno["front"]), util.plain(otro["front"]))}
        self.resultados.append(resultado)
        self.indice += 1
        return resultado

    def acta(self) -> dict:
        notas = [r["nota"] for r in self.resultados]
        media = round(sum(notas) / len(notas)) if notas else 0
        if media >= 80:
            juicio = "Ves cómo encaja todo, no solo las piezas."
        elif media >= APROBADO:
            juicio = "Relacionas lo principal; afina los porqués."
        else:
            juicio = "Te sabes las piezas sueltas, pero no cómo se tocan entre sí."
        return {"nota": media, "juicio": juicio, "total": len(self.resultados),
                "flojas": [r for r in self.resultados if r["nota"] < APROBADO]}
