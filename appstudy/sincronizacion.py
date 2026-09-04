"""Sincronización manual y sin servidor mediante una carpeta compartida.

Cada equipo escribe su propio archivo JSON. Al sincronizar se leen los demás,
se fusionan contenidos por UID y los repasos como eventos inmutables, y se
publica después el estado resultante. Esto evita que dos equipos escriban el
mismo archivo a la vez y funciona encima de Syncthing, Nextcloud o una memoria.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
import uuid
from pathlib import Path

from . import db

FORMATO = 1
MAX_ARCHIVOS = 32
MAX_BYTES = 50 * 1024 * 1024
MAX_ELEMENTOS = 250_000
_DISPOSITIVO = re.compile(r"^[a-f0-9]{32}$")


def _archivo_dispositivo() -> Path:
    return db.DATA_DIR / "device-id"


def dispositivo() -> str:
    """Identidad de esta instalación; vive fuera de la base y no se restaura."""
    ruta = _archivo_dispositivo()
    try:
        valor = ruta.read_text(encoding="ascii").strip().lower()
        if _DISPOSITIVO.fullmatch(valor):
            return valor
    except OSError:
        pass
    valor = uuid.uuid4().hex
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="ascii", dir=ruta.parent,
                                     prefix=".device-id-", delete=False) as f:
        f.write(valor + "\n")
        f.flush()
        os.fsync(f.fileno())
        temporal = Path(f.name)
    try:
        temporal.replace(ruta)
    except OSError:
        temporal.unlink(missing_ok=True)
        raise
    return valor


def _versiones_iniciales(con, ahora: float):
    """Da reloj a contenido anterior a esta función, una sola vez."""
    con.execute(
        """INSERT OR IGNORE INTO sync_changes(entity,uid,modified,deleted)
           SELECT 'card', uid, CASE WHEN created > 0 THEN created ELSE ? END, 0
           FROM cards WHERE builtin=0""", (ahora,))
    con.execute(
        """INSERT OR IGNORE INTO sync_changes(entity,uid,modified,deleted)
           SELECT 'chapter', uid, ?, 0 FROM chapters WHERE propio=1""", (ahora,))


def _filas(con, sql, args=()):
    return [dict(f) for f in con.execute(sql, args)]


def snapshot(con, equipo: str | None = None, ahora: float | None = None) -> dict:
    """Representación portable: nunca contiene IDs numéricos locales."""
    ahora = time.time() if ahora is None else float(ahora)
    equipo = equipo or dispositivo()
    if not _DISPOSITIVO.fullmatch(equipo):
        raise ValueError("Identificador de equipo no válido")
    _versiones_iniciales(con, ahora)

    decks = _filas(con, "SELECT key,name,icon,color,pos,levels FROM decks")
    cards = _filas(con,
        """SELECT c.uid,d.key AS deck_key,c.kind,c.front,c.back,c.hint,c.choices,
                  c.answer,c.tags,c.level,c.created
           FROM cards c JOIN decks d ON d.id=c.deck_id WHERE c.builtin=0""")
    chapters = _filas(con,
        """SELECT c.uid,d.key AS deck_key,c.level,c.pos,c.title,c.subtitle,
                  c.minutes,c.tags,c.body
           FROM chapters c JOIN decks d ON d.id=c.deck_id WHERE c.propio=1""")
    states = _filas(con,
        """SELECT c.uid,s.due,s.interval,s.ease,s.reps,s.lapses,s.last,
                  s.stability,s.difficulty,s.leech
           FROM state s JOIN cards c ON c.id=s.card_id WHERE s.reps>0 OR s.lapses>0""")
    logs = _filas(con,
        """SELECT c.uid,l.rating,l.ts,l.ms FROM log l
           JOIN cards c ON c.id=l.card_id ORDER BY l.ts,l.id""")
    reading = _filas(con,
        """SELECT c.uid,r.leido,r.avance,r.ts FROM reading r
           JOIN chapters c ON c.id=r.chapter_id WHERE r.ts>0 OR r.avance>0""")
    changes = _filas(con,
        "SELECT entity,uid,modified,deleted FROM sync_changes")
    return {"format": FORMATO, "device": equipo, "generated": ahora,
            "decks": decks, "cards": cards, "chapters": chapters,
            "states": states, "logs": logs, "reading": reading,
            "changes": changes}


def _guardar_snapshot(datos: dict, carpeta: Path) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / f"appstudy-{datos['device']}.sync.json"
    contenido = json.dumps(datos, ensure_ascii=False, separators=(",", ":"))
    if len(contenido.encode("utf-8")) > MAX_BYTES:
        raise ValueError("La sincronización supera el límite de 50 MB")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=carpeta,
                                     prefix=f".{destino.name}-", delete=False) as f:
        f.write(contenido)
        f.flush()
        os.fsync(f.fileno())
        temporal = Path(f.name)
    try:
        temporal.replace(destino)
    except OSError:
        temporal.unlink(missing_ok=True)
        raise
    return destino


def _leer(ruta: Path) -> dict:
    if not ruta.is_file() or ruta.stat().st_size > MAX_BYTES:
        raise ValueError("archivo demasiado grande o no regular")
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    if (not isinstance(datos, dict) or datos.get("format") != FORMATO
            or not _DISPOSITIVO.fullmatch(str(datos.get("device", "")))):
        raise ValueError("formato de sincronización no válido")
    for clave in ("decks", "cards", "chapters", "states", "logs", "reading", "changes"):
        if not isinstance(datos.get(clave), list) or len(datos[clave]) > MAX_ELEMENTOS:
            raise ValueError(f"sección {clave} no válida")
    return datos


def _huella_log(uid: str, rating, ts, ms) -> str:
    base = f"{uid}\0{int(rating)}\0{float(ts):.6f}\0{int(ms)}"
    return hashlib.sha256(base.encode()).hexdigest()


def _mazos(datos: list[dict]) -> dict[str, dict]:
    return {str(d.get("key", "")): d for d in datos if str(d.get("key", "")).strip()}


def _asegurar_mazo(con, key: str, remoto: dict | None) -> int:
    fila = con.execute("SELECT id FROM decks WHERE key=?", (key,)).fetchone()
    if fila:
        return fila["id"]
    remoto = remoto or {}
    con.execute(
        """INSERT INTO decks(key,name,icon,color,pos,levels) VALUES(?,?,?,?,?,?)""",
        (key, str(remoto.get("name") or key), str(remoto.get("icon") or "📚"),
         str(remoto.get("color") or "#3584e4"), int(remoto.get("pos") or 999),
         str(remoto.get("levels") or "[]")))
    return con.execute("SELECT id FROM decks WHERE key=?", (key,)).fetchone()["id"]


def _version_local(con, entity: str, uid: str) -> tuple[float, bool]:
    fila = con.execute(
        "SELECT modified,deleted FROM sync_changes WHERE entity=? AND uid=?",
        (entity, uid)).fetchone()
    return (float(fila["modified"]), bool(fila["deleted"])) if fila else (0.0, False)


def _aplicar_card(con, item: dict, mazo: dict | None):
    uid = str(item["uid"])
    key = str(item["deck_key"])
    did = _asegurar_mazo(con, key, mazo)
    con.execute(
        """INSERT INTO cards(deck_id,uid,kind,front,back,hint,choices,answer,tags,
                              level,builtin,created)
           VALUES(?,?,?,?,?,?,?,?,?,?,0,?)
           ON CONFLICT(uid) DO UPDATE SET deck_id=excluded.deck_id,kind=excluded.kind,
             front=excluded.front,back=excluded.back,hint=excluded.hint,
             choices=excluded.choices,answer=excluded.answer,tags=excluded.tags,
             level=excluded.level,builtin=0""",
        (did, uid, str(item.get("kind") or "card"), str(item.get("front") or ""),
         str(item.get("back") or ""), str(item.get("hint") or ""),
         str(item.get("choices") or ""), int(item.get("answer", -1)),
         str(item.get("tags") or ""), max(1, int(item.get("level") or 1)),
         float(item.get("created") or time.time())))
    cid = con.execute("SELECT id FROM cards WHERE uid=?", (uid,)).fetchone()["id"]
    con.execute("INSERT OR IGNORE INTO state(card_id,due) VALUES(?,0)", (cid,))


def _aplicar_chapter(con, item: dict, mazo: dict | None):
    uid = str(item["uid"])
    key = str(item["deck_key"])
    did = _asegurar_mazo(con, key, mazo)
    con.execute(
        """INSERT INTO chapters(deck_id,uid,level,pos,title,subtitle,minutes,tags,
                                 body,propio,fuente)
           VALUES(?,?,?,?,?,?,?,?,?,1,'')
           ON CONFLICT(uid) DO UPDATE SET deck_id=excluded.deck_id,
             level=excluded.level,pos=excluded.pos,title=excluded.title,
             subtitle=excluded.subtitle,minutes=excluded.minutes,tags=excluded.tags,
             body=excluded.body,propio=1""",
        (did, uid, max(1, int(item.get("level") or 1)), int(item.get("pos") or 0),
         str(item.get("title") or "Sin título"), str(item.get("subtitle") or ""),
         max(1, int(item.get("minutes") or 1)), str(item.get("tags") or ""),
         str(item.get("body") or "[]")))
    cid = con.execute("SELECT id FROM chapters WHERE uid=?", (uid,)).fetchone()["id"]
    con.execute("INSERT OR IGNORE INTO reading(chapter_id) VALUES(?)", (cid,))


def sincronizar(con, carpeta, equipo: str | None = None) -> dict:
    """Fusiona la carpeta con `con` y devuelve contadores para la interfaz."""
    carpeta = Path(carpeta)
    equipo = equipo or dispositivo()
    if not _DISPOSITIVO.fullmatch(equipo):
        raise ValueError("Identificador de equipo no válido")
    carpeta.mkdir(parents=True, exist_ok=True)
    ahora = time.time()
    _versiones_iniciales(con, ahora)
    con.commit()

    candidatas, ignorados = [], 0
    for ruta in carpeta.glob("appstudy-*.sync.json"):
        try:
            candidatas.append((ruta.stat().st_mtime, ruta))
        except OSError:
            ignorados += 1
    rutas = [r for _mtime, r in sorted(
        candidatas, key=lambda x: x[0], reverse=True)[:MAX_ARCHIVOS]]
    remotos = []
    for ruta in rutas:
        try:
            remotos.append(_leer(ruta))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            ignorados += 1

    otros_equipos = len({r["device"] for r in remotos if r["device"] != equipo})
    resultado = {"equipos": otros_equipos, "tarjetas": 0, "capitulos": 0,
                 "borrados": 0, "repasos": 0, "lecturas": 0,
                 "ignorados": ignorados}
    candidatos: dict[tuple[str, str], tuple[float, float, bool, dict | None, dict]] = {}
    estados: dict[str, tuple[float, float, dict]] = {}
    lecturas: dict[str, tuple[float, float, dict]] = {}

    for remoto in remotos:
        generado = float(remoto.get("generated") or 0)
        cards = {str(x.get("uid")): x for x in remoto["cards"] if x.get("uid")}
        chapters = {str(x.get("uid")): x for x in remoto["chapters"] if x.get("uid")}
        mazos = _mazos(remoto["decks"])
        for cambio in remoto["changes"]:
            entity, uid = str(cambio.get("entity", "")), str(cambio.get("uid", ""))
            if entity not in ("card", "chapter") or not uid:
                continue
            mod = float(cambio.get("modified") or 0)
            borrado = bool(cambio.get("deleted"))
            item = (cards if entity == "card" else chapters).get(uid)
            if not borrado and item is None:
                continue
            clave = (entity, uid)
            if (mod, generado) > candidatos.get(clave, (-1, -1, False, None, {}))[:2]:
                candidatos[clave] = (mod, generado, borrado, item, mazos)
        for st in remoto["states"]:
            uid = str(st.get("uid", "")); last = float(st.get("last") or 0)
            if uid and (last, generado) > estados.get(uid, (-1, -1, {}))[:2]:
                estados[uid] = (last, generado, st)
        for rd in remoto["reading"]:
            uid = str(rd.get("uid", "")); ts = float(rd.get("ts") or 0)
            if uid and (ts, generado) > lecturas.get(uid, (-1, -1, {}))[:2]:
                lecturas[uid] = (ts, generado, rd)

    try:
        con.execute("BEGIN IMMEDIATE")
        for (entity, uid), (mod, _gen, borrado, item, mazos) in candidatos.items():
            local_mod, _local_borrado = _version_local(con, entity, uid)
            if mod <= local_mod:
                continue
            tabla = "cards" if entity == "card" else "chapters"
            if borrado:
                con.execute(f"DELETE FROM {tabla} WHERE uid=?", (uid,))
                resultado["borrados"] += 1
            elif entity == "card":
                _aplicar_card(con, item, mazos.get(str(item.get("deck_key"))))
                resultado["tarjetas"] += 1
            else:
                _aplicar_chapter(con, item, mazos.get(str(item.get("deck_key"))))
                resultado["capitulos"] += 1
            db.touch_sync(con, entity, uid, borrado, mod)

        existentes = {_huella_log(f["uid"], f["rating"], f["ts"], f["ms"])
                      for f in con.execute(
                          """SELECT c.uid,l.rating,l.ts,l.ms FROM log l
                             JOIN cards c ON c.id=l.card_id""")}
        for remoto in remotos:
            for evento in remoto["logs"]:
                try:
                    uid = str(evento["uid"]); rating = int(evento["rating"])
                    ts = float(evento["ts"]); ms = max(0, int(evento.get("ms") or 0))
                except (KeyError, TypeError, ValueError):
                    continue
                if not (0 <= rating <= 3 and ts > 0):
                    continue
                fila = con.execute("SELECT id FROM cards WHERE uid=?", (uid,)).fetchone()
                huella = _huella_log(uid, rating, ts, ms)
                if not fila or huella in existentes:
                    continue
                con.execute("INSERT INTO log(card_id,rating,ts,ms) VALUES(?,?,?,?)",
                            (fila["id"], rating, ts, ms))
                existentes.add(huella)
                resultado["repasos"] += 1

        columnas = ("due", "interval", "ease", "reps", "lapses", "last",
                    "stability", "difficulty", "leech")
        for uid, (last, _gen, st) in estados.items():
            fila = con.execute(
                """SELECT s.card_id,s.last FROM state s JOIN cards c ON c.id=s.card_id
                   WHERE c.uid=?""", (uid,)).fetchone()
            if not fila or last <= float(fila["last"] or 0):
                continue
            valores = [st.get(k, 0) for k in columnas]
            con.execute(
                """UPDATE state SET due=?,interval=?,ease=?,reps=?,lapses=?,last=?,
                       stability=?,difficulty=?,leech=? WHERE card_id=?""",
                (*valores, fila["card_id"]))

        for uid, (ts, _gen, rd) in lecturas.items():
            fila = con.execute("SELECT id FROM chapters WHERE uid=?", (uid,)).fetchone()
            if not fila:
                continue
            actual = con.execute("SELECT ts FROM reading WHERE chapter_id=?",
                                 (fila["id"],)).fetchone()
            if actual and ts <= float(actual["ts"] or 0):
                continue
            con.execute(
                """INSERT INTO reading(chapter_id,leido,avance,ts) VALUES(?,?,?,?)
                   ON CONFLICT(chapter_id) DO UPDATE SET leido=excluded.leido,
                     avance=excluded.avance,ts=excluded.ts""",
                (fila["id"], int(bool(rd.get("leido"))),
                 min(1.0, max(0.0, float(rd.get("avance") or 0))), ts))
            resultado["lecturas"] += 1
        con.commit()
    except Exception:
        con.rollback()
        raise

    datos = snapshot(con, equipo)
    resultado["ruta"] = _guardar_snapshot(datos, carpeta)
    con.commit()
    return resultado
