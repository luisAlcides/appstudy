"""Lo que dice tu historial, en números.

La tabla `log` guarda cada repaso desde el primer día: qué tarjeta, qué nota,
cuándo y cuánto tardaste en contestar. Hasta ahora de todo eso solo se veían
cuatro cifras en el panel. Aquí se convierte en las series que dibuja la pestaña
de estadísticas y en el resumen que te cuenta la mascota.

No hay nada de GTK ni de Cairo: solo consultas y aritmética, para poder
comprobarlo sin abrir una ventana. Quien lo pinta es `graficas.py`.
"""
import time

from . import db, fsrs, scheduler

DIA = 86400.0


def _dia(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def _inicio_del_dia(ts: float) -> float:
    """Medianoche local del día al que pertenece `ts`."""
    partes = time.localtime(ts)
    return time.mktime((partes.tm_year, partes.tm_mon, partes.tm_mday,
                        0, 0, 0, 0, 0, -1))


# --------------------------------------------------------------- mapa de calor

def mapa_calor(con, dias: int = 364) -> dict:
    """Repasos por día del último año, como el cuadro de contribuciones.

    Devuelve las semanas ya cuadradas en columnas de lunes a domingo, que es lo
    que hace legible el dibujo: cada columna una semana, cada fila un día.
    """
    desde = _inicio_del_dia(time.time()) - (dias - 1) * DIA
    cuenta: dict[str, int] = {}
    for (ts,) in con.execute("SELECT ts FROM log WHERE ts>=? ORDER BY ts", (desde,)):
        clave = _dia(ts)
        cuenta[clave] = cuenta.get(clave, 0) + 1

    # Se empieza el lunes de la semana en la que cae el día más antiguo, para
    # que todas las columnas tengan siete casillas.
    primer_dia = time.localtime(desde)
    atras = primer_dia.tm_wday                      # 0 = lunes
    arranque = desde - atras * DIA

    celdas, hoy = [], _dia(time.time())
    t = arranque
    fin = _inicio_del_dia(time.time())
    while t <= fin + 0.5 * DIA:
        clave = _dia(t)
        celdas.append({"dia": clave, "n": cuenta.get(clave, 0),
                       "futuro": t > fin, "hoy": clave == hoy,
                       "ts": t})
        t += DIA

    semanas = [celdas[i:i + 7] for i in range(0, len(celdas), 7)]
    total = sum(c["n"] for c in celdas)
    activos = sum(1 for c in celdas if c["n"] > 0)
    return {"semanas": semanas, "maximo": max((c["n"] for c in celdas), default=0),
            "total": total, "dias_activos": activos,
            "mejor": max(celdas, key=lambda c: c["n"]) if total else None}


# ------------------------------------------------------------------ retención

def retencion_por_mazo(con, dias: int = 90) -> list[dict]:
    """Qué porcentaje aciertas en cada mazo, contando solo repasos de verdad.

    Una tarjeta que ves por primera vez no cuenta: todavía no había nada que
    recordar, así que meterla en la media solo la ensucia. Se miran los repasos
    de tarjetas que ya se habían estudiado antes.
    """
    desde = time.time() - dias * DIA
    filas = con.execute(
        """SELECT d.id, d.key, d.name, d.icon, d.color,
                  COUNT(*) AS repasos,
                  SUM(CASE WHEN l.rating > 0 THEN 1 ELSE 0 END) AS aciertos
           FROM log l
           JOIN cards c ON c.id = l.card_id
           JOIN decks d ON d.id = c.deck_id
           WHERE l.ts >= ?
             AND EXISTS (SELECT 1 FROM log a
                         WHERE a.card_id = l.card_id AND a.ts < l.ts)
           GROUP BY d.id ORDER BY d.pos, d.name""", (desde,)).fetchall()
    salida = []
    for f in filas:
        repasos = f["repasos"] or 0
        aciertos = f["aciertos"] or 0
        salida.append({
            "deck_id": f["id"], "key": f["key"], "name": f["name"],
            "icon": f["icon"], "color": f["color"],
            "repasos": repasos, "aciertos": aciertos,
            "retencion": (aciertos / repasos) if repasos else None,
        })
    return salida


def retencion_global(con, dias: int = 90) -> dict:
    """La retención de todos los mazos juntos, y la que tienes pedida."""
    mazos = retencion_por_mazo(con, dias)
    repasos = sum(m["repasos"] for m in mazos)
    aciertos = sum(m["aciertos"] for m in mazos)
    return {"repasos": repasos, "aciertos": aciertos,
            "retencion": (aciertos / repasos) if repasos else None,
            "objetivo": scheduler.config(con)["retencion"]}


# ----------------------------------------------------------- temas más débiles

def temas_debiles(con, dias: int = 90, limite: int = 6,
                  max_repasos: int = 5000) -> list[dict]:
    """Etiquetas que más cuestan, ponderando fallos y respuestas difíciles.

    Lee como máximo los últimos 5.000 repasos del período mediante ``idx_log_ts``.
    Después agrupa en una sola pasada en memoria, porque las etiquetas se guardan
    como una lista corta separada por comas. Las tarjetas sin etiqueta se agrupan
    por mazo para que nunca desaparezcan del diagnóstico.
    """
    desde = time.time() - max(1, dias) * DIA
    filas = con.execute(
        """SELECT l.rating, c.tags, d.key AS deck_key, d.name AS deck_name,
                  d.icon AS deck_icon, d.color AS deck_color
           FROM (SELECT card_id, rating, ts FROM log
                 WHERE ts >= ? ORDER BY ts DESC LIMIT ?) l
           JOIN cards c ON c.id = l.card_id
           JOIN decks d ON d.id = c.deck_id
           WHERE d.enabled = 1""", (desde, max(1, max_repasos))).fetchall()

    grupos: dict[tuple[str, str], dict] = {}
    for f in filas:
        tags = [t.strip() for t in (f["tags"] or "").split(",") if t.strip()]
        temas = [("tag", t.casefold(), t) for t in tags]
        if not temas:
            temas = [("deck", f["deck_key"], f["deck_name"])]
        for tipo, clave, nombre in temas:
            g = grupos.setdefault((tipo, clave), {
                "tema": nombre, "intentos": 0, "fallos": 0, "dificiles": 0,
                "puntos": 0, "deck_key": f["deck_key"] if tipo == "deck" else None,
                "tags": nombre if tipo == "tag" else None,
                "icon": "#" if tipo == "tag" else f["deck_icon"],
                "color": f["deck_color"],
            })
            g["intentos"] += 1
            if f["rating"] == scheduler.AGAIN:
                g["fallos"] += 1
                g["puntos"] += 2
            elif f["rating"] == scheduler.HARD:
                g["dificiles"] += 1
                g["puntos"] += 1

    salida = []
    for g in grupos.values():
        if not g["puntos"]:
            continue
        # El denominador amortigua muestras minúsculas: un único fallo no debe
        # desplazar a un tema que lleva semanas dando problemas.
        g["score"] = g["puntos"] / (g["intentos"] + 3)
        salida.append(g)
    salida.sort(key=lambda g: (-g["score"], -g["puntos"], -g["intentos"],
                               g["tema"].casefold()))
    return salida[:max(0, limite)]


# ------------------------------------------------------------- lo que se viene

def curva_vencimientos(con, dias: int = 30) -> list[dict]:
    """Cuántas tarjetas vencen cada día de aquí en adelante.

    Es la carga de trabajo que te espera. Sirve sobre todo para ver los picos
    antes de que lleguen, y para notar el efecto de cambiar la retención.
    """
    ahora = time.time()
    hoy = _inicio_del_dia(ahora)
    cubos = [0] * dias
    atrasadas = 0
    filas = con.execute(
        """SELECT s.due FROM state s
           JOIN cards c ON c.id = s.card_id
           JOIN decks d ON d.id = c.deck_id
           WHERE d.enabled = 1 AND s.reps > 0 AND COALESCE(s.leech, 0) = 0""")
    for (due,) in filas:
        if due <= ahora:
            atrasadas += 1
            continue
        indice = int((_inicio_del_dia(due) - hoy) // DIA)
        if 0 <= indice < dias:
            cubos[indice] += 1
    return [{"dia": _dia(hoy + i * DIA), "n": n,
             "atrasadas": atrasadas if i == 0 else 0,
             "total": n + (atrasadas if i == 0 else 0)}
            for i, n in enumerate(cubos)]


# --------------------------------------------------- cuánto tardas en contestar

def _mediana(valores: list) -> float:
    if not valores:
        return 0.0
    orden = sorted(valores)
    mitad = len(orden) // 2
    if len(orden) % 2:
        return float(orden[mitad])
    return (orden[mitad - 1] + orden[mitad]) / 2


# Por debajo de esto no diste tiempo ni a leer; por encima, te fuiste a por café.
MS_MINIMO = 400
MS_MAXIMO = 120_000


def tiempo_por_nivel(con, dias: int = 90) -> list[dict]:
    """Cuánto tardas en contestar, por nivel de dificultad del contenido.

    Se usa la mediana y no la media: basta con que dejes el popup abierto
    mientras contestas el teléfono para que una media deje de significar nada.
    """
    desde = time.time() - dias * DIA
    filas = con.execute(
        """SELECT c.level, l.ms, d.levels AS deck_levels
           FROM log l JOIN cards c ON c.id = l.card_id
           JOIN decks d ON d.id = c.deck_id
           WHERE l.ts >= ? AND l.ms BETWEEN ? AND ?""",
        (desde, MS_MINIMO, MS_MAXIMO)).fetchall()
    por_nivel: dict[int, list] = {}
    for f in filas:
        por_nivel.setdefault(f["level"], []).append(f["ms"])
    salida = []
    for nivel in sorted(por_nivel):
        muestras = por_nivel[nivel]
        salida.append({"level": nivel, "n": len(muestras),
                       "mediana_ms": _mediana(muestras),
                       "nombre": f"Nivel {nivel}"})
    return salida


def tiempo_por_nivel_de_mazo(con, deck_key: str | None = None, dias: int = 90):
    """Como el anterior, pero con los nombres de nivel de un mazo concreto."""
    if not deck_key:
        return tiempo_por_nivel(con, dias)
    fila = con.execute("SELECT id, levels FROM decks WHERE key=?", (deck_key,)).fetchone()
    if not fila:
        return []
    desde = time.time() - dias * DIA
    crudo = con.execute(
        """SELECT c.level, l.ms FROM log l JOIN cards c ON c.id = l.card_id
           WHERE c.deck_id = ? AND l.ts >= ? AND l.ms BETWEEN ? AND ?""",
        (fila["id"], desde, MS_MINIMO, MS_MAXIMO)).fetchall()
    por_nivel: dict[int, list] = {}
    for f in crudo:
        por_nivel.setdefault(f["level"], []).append(f["ms"])
    return [{"level": n, "n": len(v), "mediana_ms": _mediana(v),
             "nombre": db.level_name(fila["levels"], n)}
            for n, v in sorted(por_nivel.items())]


# ----------------------------------------------------------- reparto de estado

def reparto_madurez(con) -> list[dict]:
    """En qué punto están tus tarjetas: sin ver, aprendiendo, jóvenes, maduras."""
    ahora = time.time()
    fila = con.execute(
        """SELECT
             SUM(CASE WHEN s.reps = 0 THEN 1 ELSE 0 END) AS nuevas,
             SUM(CASE WHEN s.reps > 0 AND s.interval < 1 THEN 1 ELSE 0 END) AS aprendiendo,
             SUM(CASE WHEN s.interval >= 1 AND s.interval < 21 THEN 1 ELSE 0 END) AS jovenes,
             SUM(CASE WHEN s.interval >= 21 THEN 1 ELSE 0 END) AS maduras,
             SUM(CASE WHEN COALESCE(s.leech, 0) = 1 THEN 1 ELSE 0 END) AS atragantadas
           FROM state s JOIN cards c ON c.id = s.card_id
           JOIN decks d ON d.id = c.deck_id WHERE d.enabled = 1""").fetchone()
    del ahora
    return [
        {"clave": "nuevas", "nombre": "Sin estrenar", "n": fila["nuevas"] or 0,
         "color": "#9a9996"},
        {"clave": "aprendiendo", "nombre": "Aprendiendo", "n": fila["aprendiendo"] or 0,
         "color": "#e5a50a"},
        {"clave": "jovenes", "nombre": "Jóvenes", "n": fila["jovenes"] or 0,
         "color": "#3584e4"},
        {"clave": "maduras", "nombre": "Maduras", "n": fila["maduras"] or 0,
         "color": "#2ec27e"},
        {"clave": "atragantadas", "nombre": "Atragantadas",
         "n": fila["atragantadas"] or 0, "color": "#c01c28"},
    ]


def memoria_total(con) -> dict:
    """Cuánto has construido: la suma de estabilidades, en días y en años.

    Es la cifra que mejor resume el trabajo hecho, porque no cuenta repasos sino
    memoria: los días que aguantarían tus tarjetas si dejaras de estudiar hoy.
    """
    fila = con.execute(
        """SELECT SUM(s.stability) AS suma, AVG(s.stability) AS media,
                  AVG(s.difficulty) AS dificultad, COUNT(*) AS n
           FROM state s JOIN cards c ON c.id = s.card_id
           JOIN decks d ON d.id = c.deck_id
           WHERE d.enabled = 1 AND s.reps > 0""").fetchone()
    return {"dias": fila["suma"] or 0.0, "media": fila["media"] or 0.0,
            "dificultad": fila["dificultad"] or 0.0, "tarjetas": fila["n"] or 0}


def probabilidad_hoy(con) -> float | None:
    """Qué probabilidad media tienes ahora mismo de acordarte de lo estudiado.

    Es la retención real del momento, calculada con el modelo: para cada tarjeta,
    cuánto ha pasado desde su último repaso frente a lo que aguanta.
    """
    ahora = time.time()
    filas = con.execute(
        """SELECT s.stability, s.last FROM state s
           JOIN cards c ON c.id = s.card_id JOIN decks d ON d.id = c.deck_id
           WHERE d.enabled = 1 AND s.reps > 0 AND s.stability > 0 AND s.last > 0""")
    total, n = 0.0, 0
    for f in filas:
        total += fsrs.recuperabilidad((ahora - f["last"]) / DIA, f["stability"])
        n += 1
    return (total / n) if n else None


# ------------------------------------------------------- el diario de la semana

DIAS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def resumen_semanal(con, dias: int = 7) -> dict:
    """Lo que has hecho estos días, en datos listos para contarlo en una frase."""
    desde = _inicio_del_dia(time.time()) - (dias - 1) * DIA
    filas = con.execute(
        "SELECT ts, rating, ms FROM log WHERE ts >= ? ORDER BY ts", (desde,)).fetchall()

    por_dia: dict[str, int] = {}
    aciertos = minutos = 0
    for f in filas:
        clave = _dia(f["ts"])
        por_dia[clave] = por_dia.get(clave, 0) + 1
        if f["rating"] > scheduler.AGAIN:
            aciertos += 1
        if MS_MINIMO <= f["ms"] <= MS_MAXIMO:
            minutos += f["ms"] / 60000.0

    serie = []
    for atras in range(dias - 1, -1, -1):
        ts = _inicio_del_dia(time.time()) - atras * DIA
        clave = _dia(ts)
        serie.append({"dia": clave, "n": por_dia.get(clave, 0),
                      "nombre": DIAS_ES[time.localtime(ts).tm_wday], "ts": ts})

    total = len(filas)
    activos = sum(1 for d in serie if d["n"] > 0)
    mejor = max(serie, key=lambda d: d["n"]) if total else None

    # Comparación con los `dias` anteriores, que es lo que da sentido al número
    anterior = con.execute(
        "SELECT COUNT(*) FROM log WHERE ts >= ? AND ts < ?",
        (desde - dias * DIA, desde)).fetchone()[0]

    lecturas = con.execute(
        """SELECT COUNT(*) FROM reading WHERE leido = 1 AND ts >= ?""",
        (desde,)).fetchone()[0]

    return {
        "dias": dias, "total": total, "activos": activos,
        "aciertos": aciertos,
        "retencion": (aciertos / total) if total else None,
        "minutos": minutos, "serie": serie, "mejor": mejor,
        "anterior": anterior,
        "cambio": (total - anterior) / anterior if anterior else None,
        "capitulos": lecturas,
        "racha": db.streak(con),
    }


def contar_semana(con, dias: int = 7) -> str:
    """El resumen de la semana escrito para leerlo de un tirón.

    Es lo que sale en el globo de la mascota, así que va en dos o tres frases
    cortas y sin ningún número que no aporte.
    """
    r = resumen_semanal(con, dias)
    if not r["total"]:
        return ("Esta semana no hemos estudiado nada. No pasa nada: se empieza "
                "con una tarjeta.")

    partes = [f"Esta semana estudiaste <b>{r['activos']} "
              f"{'día' if r['activos'] == 1 else 'días'}</b> y "
              f"<b>{r['total']} {'tarjeta' if r['total'] == 1 else 'tarjetas'}</b>."]

    if r["mejor"] and r["mejor"]["n"]:
        partes.append(f"El mejor día fue el {r['mejor']['nombre']}, "
                      f"con {r['mejor']['n']}.")

    if r["retencion"] is not None:
        partes.append(f"Acertaste el {r['retencion'] * 100:.0f} %.")

    if r["cambio"] is not None:
        cambio = r["cambio"] * 100
        if cambio >= 15:
            partes.append(f"Un {cambio:.0f} % más que la semana pasada.")
        elif cambio <= -15:
            partes.append(f"Un {abs(cambio):.0f} % menos que la semana pasada.")
        else:
            partes.append("Más o menos como la semana pasada.")
    elif r["anterior"] == 0:
        partes.append("La semana pasada no hubo nada, así que vamos mejor.")

    if r["capitulos"]:
        partes.append(f"Y {r['capitulos']} "
                      f"{'capítulo leído' if r['capitulos'] == 1 else 'capítulos leídos'}.")

    if r["racha"] >= 3:
        partes.append(f"Llevas <b>{r['racha']} días seguidos</b>.")

    return " ".join(partes)
