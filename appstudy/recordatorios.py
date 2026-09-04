"""Reglas baratas para decidir cuándo Bit puede interrumpir."""
from __future__ import annotations

import time

from . import db

DIAS = ("todos", "laborales", "fin_de_semana")
NOMBRES_DIAS = ("Todos los días", "Lunes a viernes", "Solo fines de semana")


def config(con) -> dict:
    try:
        dias = str(db.get_meta(con, "recordatorio_dias", "todos"))
        inicio = max(0, min(23, int(db.get_meta(con, "recordatorio_inicio", 8))))
        fin = max(0, min(24, int(db.get_meta(con, "recordatorio_fin", 22))))
    except (TypeError, ValueError):
        dias, inicio, fin = "todos", 8, 22
    return {"dias": dias if dias in DIAS else "todos", "inicio": inicio, "fin": fin}


def guardar(con, dias=None, inicio=None, fin=None):
    actual = config(con)
    if dias is not None:
        actual["dias"] = dias if dias in DIAS else "todos"
    if inicio is not None:
        actual["inicio"] = max(0, min(23, int(inicio)))
    if fin is not None:
        actual["fin"] = max(0, min(24, int(fin)))
    # Una sola transacción, para que Bit nunca lea media configuración nueva.
    con.executemany(
        "INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
        (("recordatorio_dias", actual["dias"]),
         ("recordatorio_inicio", str(actual["inicio"])),
         ("recordatorio_fin", str(actual["fin"]))))
    con.commit()


def permitido(cfg: dict, ahora: float | None = None) -> bool:
    local = time.localtime(time.time() if ahora is None else ahora)
    if cfg["dias"] == "laborales" and local.tm_wday >= 5:
        return False
    if cfg["dias"] == "fin_de_semana" and local.tm_wday < 5:
        return False
    inicio, fin, hora = cfg["inicio"], cfg["fin"], local.tm_hour
    if inicio == fin:
        return True                         # misma hora = todo el día
    if inicio < fin:
        return inicio <= hora < fin
    return hora >= inicio or hora < fin     # franja que cruza medianoche


def descripcion(cfg: dict) -> str:
    dias = NOMBRES_DIAS[DIAS.index(cfg["dias"])]
    if cfg["inicio"] == cfg["fin"]:
        return f"{dias} · cualquier hora"
    return f"{dias} · {cfg['inicio']:02d}:00–{cfg['fin']:02d}:00"
