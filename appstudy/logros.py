"""Logros: las marcas que se van pasando sin darse cuenta.

La idea es que sean **discretos**. No hay puntos, ni niveles, ni una pantalla
que te felicite cada dos por tres. Solo unas cuantas marcas de verdad —la
primera semana seguida, el primer mazo dominado, el primer capítulo de C1— que
Bit celebra una vez, con el salto y los corazones que ya sabe hacer, y que luego
se quedan en la pestaña de estadísticas por si quieres mirarlas.

Cada logro es una regla que se comprueba contra la base. Nada se guarda hasta
que se consigue: en `meta` queda la fecha, y con eso basta para saber cuáles
están y cuáles no. Así se pueden añadir logros nuevos sin migrar nada, y los que
ya tenías siguen ahí.

Sin GTK: la comprobación se puede probar sin abrir ninguna ventana.
"""
import json
import time

from . import db

CLAVE_META = "logros"

# Un mazo se considera dominado cuando esta parte de sus tarjetas es madura
PARTE_DOMINADO = 0.80
MINIMO_DOMINADO = 20        # con menos tarjetas «dominar» no significa nada


def _tarjetas_maduras(con, deck_id):
    fila = con.execute(
        """SELECT COUNT(*) AS total,
                  SUM(CASE WHEN s.interval >= 21 THEN 1 ELSE 0 END) AS maduras
           FROM cards c JOIN state s ON s.card_id = c.id
           WHERE c.deck_id = ?""", (deck_id,)).fetchone()
    return fila["total"] or 0, fila["maduras"] or 0


class Datos:
    """Lo que varias reglas necesitan, calculado una sola vez por comprobación.

    Se revisan los logros en cada calificación, y la racha sola cuesta unos
    milisegundos porque recorre todo el historial. Pedirla tres veces (siete,
    treinta y cien días) multiplicaba ese coste sin motivo.
    """

    def __init__(self, con):
        self.con = con
        self._cache = {}

    def _una_vez(self, clave, calcular):
        if clave not in self._cache:
            self._cache[clave] = calcular()
        return self._cache[clave]

    @property
    def racha(self) -> int:
        return self._una_vez("racha", lambda: db.streak(self.con))

    @property
    def repasos(self) -> int:
        return self._una_vez("repasos", lambda: self.con.execute(
            "SELECT COUNT(*) FROM log").fetchone()[0])

    @property
    def mejor_dia(self) -> int:
        """Las tarjetas del día más cargado de tu historial."""
        return self._una_vez("mejor_dia", lambda: self.con.execute(
            """SELECT COUNT(*) AS n FROM log
               GROUP BY date(ts, 'unixepoch', 'localtime')
               ORDER BY n DESC LIMIT 1""").fetchone()[0] if self.repasos else 0)


# --------------------------------------------------------------- las preguntas

def _racha(datos, dias):
    return datos.racha >= dias


def _repasos_totales(datos, cuantos):
    return datos.repasos >= cuantos


def _mazo_dominado(con, datos):
    """¿Hay algún mazo con la mayoría de sus tarjetas ya maduras?"""
    for d in con.execute("SELECT id, name FROM decks"):
        total, maduras = _tarjetas_maduras(con, d["id"])
        if total >= MINIMO_DOMINADO and maduras >= total * PARTE_DOMINADO:
            return d["name"]
    return None


def _capitulo_de_nivel(con, nivel):
    """¿Has terminado algún capítulo de ese nivel o más alto?"""
    fila = con.execute(
        """SELECT c.title FROM chapters c JOIN reading r ON r.chapter_id = c.id
           WHERE r.leido = 1 AND c.level >= ? LIMIT 1""", (nivel,)).fetchone()
    return fila["title"] if fila else None


# Un mazo con uno o dos capítulos se lee en un rato: no es «de cabo a rabo»
MINIMO_CAPITULOS = 3


def _todos_los_capitulos_de_un_mazo(con, datos):
    fila = con.execute(
        """SELECT d.name, COUNT(*) AS total,
                  SUM(COALESCE(r.leido, 0)) AS leidos
           FROM chapters c JOIN decks d ON d.id = c.deck_id
           LEFT JOIN reading r ON r.chapter_id = c.id
           GROUP BY d.id HAVING total >= ? AND leidos = total
           ORDER BY total DESC LIMIT 1""", (MINIMO_CAPITULOS,)).fetchone()
    return fila["name"] if fila else None


def _memoria_construida(con, dias):
    """La suma de estabilidades: cuánto aguantaría lo tuyo sin tocarlo."""
    fila = con.execute(
        "SELECT SUM(stability) AS suma FROM state WHERE reps > 0").fetchone()
    return (fila["suma"] or 0.0) >= dias


def _un_dia_de(datos, cuantas):
    """¿Algún día con al menos tantas tarjetas?"""
    return datos.mejor_dia >= cuantas


def _sin_atragantadas(con, datos):
    """Cien repasos hechos y ninguna tarjeta apartada: material bien escrito."""
    if datos.repasos < 100:
        return False
    return con.execute("SELECT COUNT(*) FROM state WHERE leech = 1").fetchone()[0] == 0


# Cada logro: clave, icono, título, la frase con la que Bit lo celebra, y la
# regla que devuelve algo verdadero cuando está conseguido (a veces un texto,
# que se cuela en el mensaje).
LOGROS = (
    {"clave": "primer_repaso", "icono": "🌱", "titulo": "El primer paso",
     "pista": "Califica tu primera tarjeta",
     "regla": lambda con, d: _repasos_totales(d, 1),
     "frase": "Primera tarjeta calificada. Por algo se empieza."},

    {"clave": "racha_7", "icono": "🔥", "titulo": "Una semana seguida",
     "pista": "Siete días seguidos estudiando",
     "regla": lambda con, d: _racha(d, 7),
     "frase": "¡Siete días seguidos! Ya no es un arranque, es una costumbre."},

    {"clave": "racha_30", "icono": "🏔️", "titulo": "Un mes seguido",
     "pista": "Treinta días seguidos estudiando",
     "regla": lambda con, d: _racha(d, 30),
     "frase": "Treinta días seguidos. Esto ya es parte de tu día."},

    {"clave": "racha_100", "icono": "💎", "titulo": "Cien días",
     "pista": "Cien días seguidos estudiando",
     "regla": lambda con, d: _racha(d, 100),
     "frase": "Cien días seguidos. Muy poca gente llega aquí."},

    {"clave": "dia_50", "icono": "⚡", "titulo": "Una buena sentada",
     "pista": "Cincuenta tarjetas en un mismo día",
     "regla": lambda con, d: _un_dia_de(d, 50),
     "frase": "Cincuenta tarjetas en un día. Vaya sesión."},

    {"clave": "repasos_1000", "icono": "📚", "titulo": "Mil repasos",
     "pista": "Mil tarjetas calificadas en total",
     "regla": lambda con, d: _repasos_totales(d, 1000),
     "frase": "Mil repasos. Eso ya no se olvida fácil."},

    {"clave": "mazo_dominado", "icono": "🏆", "titulo": "Mazo dominado",
     "pista": "El 80 % de un mazo con repasos de más de tres semanas",
     "regla": _mazo_dominado,
     "frase": "Has dominado {dato}. Casi todo ese mazo aguanta ya semanas."},

    {"clave": "memoria_año", "icono": "🧠", "titulo": "Un año de memoria",
     "pista": "Sumar 365 días de estabilidad entre todas tus tarjetas",
     "regla": lambda con, d: _memoria_construida(con, 365),
     "frase": "Sumando todas tus tarjetas, has construido un año de memoria."},

    {"clave": "capitulo_avanzado", "icono": "🎓", "titulo": "Nivel avanzado",
     "pista": "Terminar un capítulo del nivel más alto (C1 o Avanzado)",
     "regla": lambda con, d: _capitulo_de_nivel(con, 3),
     "frase": "Terminaste «{dato}», que es de lo más avanzado que hay aquí."},

    {"clave": "mazo_leido", "icono": "📖", "titulo": "De cabo a rabo",
     "pista": "Leer todos los capítulos de un mazo",
     "regla": _todos_los_capitulos_de_un_mazo,
     "frase": "Te has leído {dato} entero, capítulo a capítulo."},

    {"clave": "sin_atragantadas", "icono": "✨", "titulo": "Nada se atraganta",
     "pista": "Cien repasos sin ninguna tarjeta apartada",
     "regla": _sin_atragantadas,
     "frase": "Cien repasos y ni una tarjeta atragantada. Vas fino."},
)

POR_CLAVE = {le["clave"]: le for le in LOGROS}


# ------------------------------------------------------------ leer y consultar

def conseguidos(con) -> dict:
    """Los logros que ya tienes: {clave: {"ts": cuándo, "dato": texto}}."""
    crudo = db.get_meta(con, CLAVE_META, "")
    if not crudo:
        return {}
    try:
        datos = json.loads(crudo)
    except (ValueError, TypeError):
        return {}
    if not isinstance(datos, dict):
        return {}
    # Se ignoran las claves de logros que ya no existan
    return {k: v for k, v in datos.items() if k in POR_CLAVE and isinstance(v, dict)}


def _guardar(con, datos: dict):
    db.set_meta(con, CLAVE_META, json.dumps(datos, ensure_ascii=False))


def frase_de(logro, dato=None) -> str:
    return logro["frase"].format(dato=dato or "")


def revisar(con, celebrar: bool = True) -> list[dict]:
    """Comprueba qué logros nuevos hay. Devuelve los recién conseguidos.

    Con `celebrar=False` no se apunta nada: sirve para saber cómo va la cosa sin
    gastar la celebración, que solo tiene gracia la primera vez.
    """
    ya = conseguidos(con)
    datos = Datos(con)
    nuevos = []
    for logro in LOGROS:
        if logro["clave"] in ya:
            continue
        try:
            resultado = logro["regla"](con, datos)
        except Exception:          # un logro roto no puede impedirte estudiar
            continue
        if not resultado:
            continue
        dato = resultado if isinstance(resultado, str) else None
        nuevos.append({**logro, "dato": dato, "ts": time.time()})
        if celebrar:
            ya[logro["clave"]] = {"ts": time.time(), "dato": dato}
    if celebrar and nuevos:
        _guardar(con, ya)
    return nuevos


def listado(con) -> list[dict]:
    """Todos los logros, con si están conseguidos y desde cuándo."""
    ya = conseguidos(con)
    salida = []
    for logro in LOGROS:
        estado = ya.get(logro["clave"])
        salida.append({
            "clave": logro["clave"], "icono": logro["icono"],
            "titulo": logro["titulo"], "pista": logro["pista"],
            "conseguido": estado is not None,
            "ts": estado.get("ts") if estado else None,
            "dato": estado.get("dato") if estado else None,
        })
    return salida


def cuantos(con) -> tuple[int, int]:
    """(conseguidos, total), para enseñarlo en una línea."""
    return len(conseguidos(con)), len(LOGROS)


def olvidar(con):
    """Borra los logros conseguidos: se pueden volver a ganar."""
    db.set_meta(con, CLAVE_META, "")
