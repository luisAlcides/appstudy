"""Estado de AppStudy en JSON, para quien lo quiera leer desde fuera.

Lo usa la extensión del top bar de GNOME (`appstudy --status`), que no puede
abrir la base SQLite por su cuenta. No importa GTK a propósito: así responde en
milisegundos y sirve igual desde un script o desde la terminal.
"""
import json
import os
import signal
import sys
import time

from . import citas, db, scheduler


def pet_pid(con):
    """PID de la mascota si sigue viva, o None."""
    try:
        pid = int(db.get_meta(con, "pet_pid", 0) or 0)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    try:
        cmd = open(f"/proc/{pid}/cmdline", "rb").read().decode("utf-8", "replace")
    except OSError:
        return None
    return pid if "appstudy" in cmd and "--pet" in cmd else None


def snapshot(con) -> dict:
    t = db.totals(con)
    fila = con.execute(
        """SELECT MIN(s.due) AS due FROM state s
           JOIN cards c ON c.id=s.card_id JOIN decks d ON d.id=c.deck_id
           WHERE d.enabled=1 AND s.reps>0 AND s.due>?""", (time.time(),)).fetchone()
    frase, autor, obra = citas.aleatoria()
    return {
        **{k: int(t[k]) for k in ("total", "nuevas", "pendientes", "dominadas",
                                  "hoy", "racha", "sanguijuelas", "objetivo",
                                  "restan")},
        "proximo": scheduler.due_label(fila["due"]) if fila and fila["due"] else "",
        "mascota": pet_pid(con) is not None,
        "semana": [d["n"] for d in db.repasos_por_dia(con, 7)],
        "cita": {"frase": frase, "autor": autor, "obra": obra},
    }


def run_status(argv) -> int:
    con = db.connect()
    if "--pet-off" in argv:
        pid = pet_pid(con)
        if pid:
            os.kill(pid, signal.SIGTERM)
        print(json.dumps({"mascota": False}))
        return 0
    json.dump(snapshot(con), sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0
