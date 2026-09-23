"""Bitácora del taller: cada equipo que llega se vuelve algo que aprender.

Cuando vuelves de supervisar cuentas en una línea qué equipo era y qué tenía
(«CAT 320D, fuga en el cilindro del brazo, se cambió el sello»). Esa nota es un
**caso**: queda como registro consultable del taller y, de él, la IA local saca
tarjetas del *concepto de fondo* —por qué falla un sello de vástago, cómo se
distingue una fuga interna de una externa—, no del caso en sí.

El orden importa, porque en el taller te vuelven a llamar en cualquier momento:

  1. `registrar` guarda la nota **antes** de llamar a la IA. Pase lo que pase
     después, lo que contaste no se pierde.
  2. `tomar` → `ia.tarjetas_de_caso` → `proponer` (o `fallar`) corre en segundo
     plano, en la app o en Bit, el primero que llegue: `tomar` es atómico.
  3. `aceptar` guarda solo las que apruebes, con el caso como fuente.

Nada de aquí toca GTK ni la red: la llamada al modelo la hace quien lo use,
fuera del hilo de la interfaz, con lo que devuelve `preparar`.
"""
from __future__ import annotations

import json
import re
import time
import uuid

from . import db, ia, util

MAX_EQUIPO = 40
TOMADO_CADUCA = 600         # s; si quien lo tomó murió a medias, otro lo retoma
ESPERA_REINTENTO = 900      # s; tras un fallo de la IA no se insiste enseguida
CUANTAS = 4

# Marcas habituales de un taller de maquinaria amarilla, volquetes y
# vehículos. Con ellas se reconoce «CAT 320D» en mitad de una frase.
_MARCAS = {
    "cat": "CAT", "caterpillar": "Caterpillar", "komatsu": "Komatsu",
    "volvo": "Volvo", "john deere": "John Deere", "deere": "Deere", "jcb": "JCB",
    "case": "Case", "hitachi": "Hitachi", "liebherr": "Liebherr",
    "hyundai": "Hyundai", "doosan": "Doosan", "develon": "Develon",
    "bobcat": "Bobcat", "new holland": "New Holland", "kobelco": "Kobelco",
    "sany": "Sany", "xcmg": "XCMG", "liugong": "LiuGong", "sdlg": "SDLG",
    "scania": "Scania", "mercedes": "Mercedes", "mercedes-benz": "Mercedes-Benz",
    "man": "MAN", "iveco": "Iveco", "kenworth": "Kenworth",
    "freightliner": "Freightliner", "international": "International",
    "mack": "Mack", "hino": "Hino", "isuzu": "Isuzu", "shacman": "Shacman",
    "sinotruk": "Sinotruk", "howo": "HOWO", "dongfeng": "Dongfeng",
    "toyota": "Toyota", "nissan": "Nissan", "mitsubishi": "Mitsubishi",
    "ford": "Ford", "chevrolet": "Chevrolet", "hilux": "Toyota Hilux",
}
_MODELO = r"[A-Za-z]{0,4}[\d][\w\-\.]*|[A-Z]{2,}[\w\-]*"
_EQUIPO = re.compile(
    r"\b(" + "|".join(sorted((re.escape(m) for m in _MARCAS), key=len, reverse=True))
    + r")\b(?:\s+(" + _MODELO + r"))?", re.I)

# Palabras de vehículo de carretera: si pesan más que las de máquina, el caso
# va a Mecánica Automotriz; si no, a Maquinaria, que es el taller de verdad.
_AUTO = {"toyota", "nissan", "hilux", "ford", "chevrolet", "mitsubishi", "camioneta",
         "auto", "carro", "coche", "sedan", "pickup", "alternador", "obd", "obd2",
         "bujía", "bujia", "embrague", "catalizador", "inyector"}
_MAQUINA = {"cat", "caterpillar", "komatsu", "excavadora", "retro", "retroexcavadora",
            "cargador", "motoniveladora", "tractor", "oruga", "volquete", "bulldozer",
            "hidráulico", "hidraulico", "cilindro", "cucharón", "cucharon", "brazo",
            "pluma", "tren", "rodaje", "powershift", "mando", "final"}


def _modelo(palabra: str) -> str:
    """«320d» → «320D», «FMX» y «Hilux» tal cual; «con» o «excavadora», nada.

    Un código con cifras es un modelo seguro. Sin cifras, solo si lo escribiste
    con mayúscula: en minúscula tras la marca suele ser la frase que sigue.
    """
    if any(ch.isdigit() for ch in palabra):
        return palabra.upper()
    return palabra if palabra[:1].isupper() else ""


def equipo_de(texto: str) -> str:
    """El equipo del que habla la nota: «CAT 320D», o el primer trozo si no hay marca."""
    texto = " ".join(texto.split())
    m = _EQUIPO.search(texto)
    if m:
        marca = _MARCAS[m.group(1).lower()]
        return f"{marca} {_modelo(m.group(2) or '')}".strip()[:MAX_EQUIPO]
    primero = re.split(r"[,.;:\n]| - ", texto, maxsplit=1)[0].strip()
    return (primero[:MAX_EQUIPO - 1] + "…") if len(primero) > MAX_EQUIPO else primero


def mazo_para(con, texto: str) -> str:
    """Mazo al que van las tarjetas: Maquinaria salvo que suene a vehículo."""
    claves = [r["key"] for r in con.execute("SELECT key FROM decks ORDER BY pos, id")]
    if not claves:
        return ""
    palabras = set(re.findall(r"[a-záéíóúñü0-9]+", texto.lower()))
    auto, maquina = len(palabras & _AUTO), len(palabras & _MAQUINA)
    for clave in (("automotriz", "maquinaria") if auto > maquina
                  else ("maquinaria", "automotriz")):
        if clave in claves:
            return clave
    return claves[0]


# ------------------------------------------------------------------- casos

def _dict(fila) -> dict | None:
    if not fila:
        return None
    d = dict(fila)
    try:
        d["propuestas"] = json.loads(d.get("propuestas") or "[]")
    except json.JSONDecodeError:
        d["propuestas"] = []
    return d


def registrar(con, texto: str, deck_key: str | None = None) -> dict:
    """Guarda la nota tal cual, ya. Lo primero, antes que la IA."""
    texto = " ".join(str(texto or "").split())
    if not texto:
        raise ValueError("La nota está vacía.")
    cur = con.execute(
        "INSERT INTO casos(uid,texto,equipo,deck_key,created) VALUES(?,?,?,?,?)",
        (f"caso:{uuid.uuid4().hex}", texto, equipo_de(texto),
         deck_key or mazo_para(con, texto), time.time()))
    con.commit()
    return caso(con, cur.lastrowid)


def caso(con, caso_id: int) -> dict | None:
    return _dict(con.execute("SELECT * FROM casos WHERE id=?", (caso_id,)).fetchone())


def caso_por_uid(con, uid: str) -> dict | None:
    return _dict(con.execute("SELECT * FROM casos WHERE uid=?", (uid,)).fetchone())


def casos(con, limite: int = 200) -> list[dict]:
    """Los más recientes primero."""
    return [_dict(f) for f in con.execute(
        "SELECT * FROM casos ORDER BY created DESC, id DESC LIMIT ?", (limite,))]


def pendientes(con, reintento: bool = False, ahora: float | None = None) -> list[dict]:
    """Casos que aún esperan tarjetas y que alguien puede tomar ahora.

    Con `reintento`, lo que falló hace poco espera `ESPERA_REINTENTO`: si Ollama
    está apagado, no tiene sentido llamarlo cada quince segundos.
    """
    ahora = time.time() if ahora is None else ahora
    filas = con.execute(
        """SELECT * FROM casos
           WHERE (estado='pendiente' AND (? = 0 OR motivo='' OR intento<=?))
              OR (estado='generando' AND intento<=?)
           ORDER BY created""",
        (int(reintento), ahora - ESPERA_REINTENTO, ahora - TOMADO_CADUCA)).fetchall()
    return [_dict(f) for f in filas]


def por_revisar(con) -> list[dict]:
    return [_dict(f) for f in con.execute(
        "SELECT * FROM casos WHERE estado='propuesto' ORDER BY created")]


def tomar(con, caso_id: int, ahora: float | None = None) -> bool:
    """Se queda con el caso para generarle tarjetas. Falso si ya lo tiene otro."""
    ahora = time.time() if ahora is None else ahora
    cur = con.execute(
        """UPDATE casos SET estado='generando', intento=?
           WHERE id=? AND (estado='pendiente'
                           OR (estado='generando' AND intento<=?))""",
        (ahora, caso_id, ahora - TOMADO_CADUCA))
    con.commit()
    return cur.rowcount == 1


def preparar(con, caso_id: int) -> dict:
    """Lo que necesita el hilo de trabajo, leído aquí porque SQLite no cruza hilos."""
    c = caso(con, caso_id)
    fila = con.execute("SELECT name FROM decks WHERE key=?", (c["deck_key"],)).fetchone()
    return {"id": c["id"], "texto": c["texto"], "equipo": c["equipo"],
            "mazo": fila["name"] if fila else c["deck_key"],
            "contexto": ia.buscar_contexto(con, c["texto"], cuantas=4,
                                           deck_key=c["deck_key"] or None),
            "cfg": ia.config(con)}


def lanzar(con, caso_id: int, al_terminar=None, al_fallar=None) -> bool:
    """Genera las tarjetas del caso en segundo plano, si nadie lo está haciendo ya.

    Los resultados vuelven al hilo de la interfaz (ver `util.hilo`), que es el
    dueño de `con`: ahí se guardan y luego se llama a `al_terminar(caso)` o a
    `al_fallar(error)`. Falso si no se lanzó.
    """
    cfg = ia.config(con)
    if not cfg.get("activa"):
        fallar(con, caso_id, "La IA está desactivada. Actívala en Ajustes y lo retomo.")
        return False
    if not tomar(con, caso_id):
        return False
    t = preparar(con, caso_id)

    def listo(tarjetas):
        proponer(con, caso_id, tarjetas)
        if al_terminar:
            al_terminar(caso(con, caso_id))

    def mal(error):
        fallar(con, caso_id, str(error))
        if al_fallar:
            al_fallar(error)

    ia.hilo(lambda: ia.tarjetas_de_caso(t["cfg"], t["texto"], t["mazo"], t["contexto"],
                                        CUANTAS), listo, mal)
    return True


def proponer(con, caso_id: int, tarjetas: list[dict]):
    limpias = [{"front": str(t["front"]).strip(), "back": str(t["back"]).strip()}
               for t in tarjetas if str(t.get("front", "")).strip()]
    con.execute("UPDATE casos SET estado='propuesto', propuestas=?, motivo='' WHERE id=?",
                (json.dumps(limpias, ensure_ascii=False), caso_id))
    con.commit()


def fallar(con, caso_id: int, motivo: str):
    """La IA no pudo: el caso vuelve a esperar, con el porqué a la vista."""
    con.execute("UPDATE casos SET estado='pendiente', motivo=?, intento=? WHERE id=?",
                (str(motivo)[:300] or "Error desconocido", time.time(), caso_id))
    con.commit()


def aceptar(con, caso_id: int, elegidas: list[dict], deck_key: str | None = None) -> list[int]:
    """Guarda como tarjetas las que apruebes. Con ninguna, el caso queda de registro.

    `deck_key` corrige el mazo que se adivinó al registrar la nota."""
    c = caso(con, caso_id)
    if not c:
        return []
    if deck_key and deck_key != c["deck_key"]:
        con.execute("UPDATE casos SET deck_key=? WHERE id=?", (deck_key, caso_id))
        c["deck_key"] = deck_key
    mazo = con.execute("SELECT id, key, levels FROM decks WHERE key=?",
                       (c["deck_key"],)).fetchone()
    ids = []
    if mazo and elegidas:
        try:
            niveles = json.loads(mazo["levels"] or "[]")
        except json.JSONDecodeError:
            niveles = []
        nivel = 2 if len(niveles) >= 2 else 1       # lo del taller no es de básico
        etiquetas = ",".join(["bitacora", *([_etiqueta(c["equipo"])] if c["equipo"] else [])])
        fuente = {"kind": "caso", "chapter_uid": c["uid"], "title": titulo(c)}
        for t in elegidas:
            cid, _ = db.add_card(con, mazo["id"], mazo["key"], "card", t["front"],
                                 t["back"], tags=etiquetas, level=nivel)
            db.set_card_source(con, cid, fuente)
            ids.append(cid)
    con.execute("UPDATE casos SET estado='listo' WHERE id=?", (caso_id,))
    con.commit()
    return ids


def _etiqueta(equipo: str) -> str:
    """«CAT 320D» → «cat-320d», para practicar juntas las de un mismo equipo."""
    return re.sub(r"[^a-z0-9]+", "-", util.plain(equipo).lower()).strip("-")


def tarjetas_de(con, caso_id: int) -> list[dict]:
    c = caso(con, caso_id)
    if not c:
        return []
    return [dict(f) for f in con.execute(
        """SELECT c.* FROM cards c JOIN card_sources s ON s.card_id=c.id
           WHERE s.kind='caso' AND s.chapter_uid=? ORDER BY c.id""", (c["uid"],))]


def borrar(con, caso_id: int):
    """Quita el registro. Las tarjetas se quedan: ya son tuyas."""
    con.execute("DELETE FROM casos WHERE id=?", (caso_id,))
    con.commit()


def titulo(c: dict) -> str:
    """«CAT 320D · 23/09»: lo que se ve como fuente de sus tarjetas."""
    fecha = time.strftime("%d/%m", time.localtime(c["created"]))
    return f"{c['equipo'] or 'Caso del taller'} · {fecha}"
