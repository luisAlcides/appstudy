"""La lectura del día: un capítulo al día, elegido una vez y sostenido.

El panel ya proponía qué leer, pero lo recalculaba en cada refresco: abrías la
aplicación por la tarde y te ofrecía otra cosa que por la mañana. Una tarea que
cambia sola no se termina nunca, así que aquí se elige **una** y se fija hasta
que la terminas o hasta que cambia el día.

Elegir sigue siendo cosa de `recomendaciones`; lo de este módulo es recordar la
elección, saber si ya está cumplida y llevar la cuenta de los días seguidos.
"""
import time

from . import db, recomendaciones

CLAVE_FECHA = "lectura_dia_fecha"
CLAVE_CAP = "lectura_dia_cap"


def _hoy(ahora: float | None = None) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ahora))


def _vigente(con, ahora=None) -> dict | None:
    """El capítulo ya fijado para hoy, si sigue existiendo y sirviendo."""
    if db.get_meta(con, CLAVE_FECHA) != _hoy(ahora):
        return None
    try:
        cap_id = int(db.get_meta(con, CLAVE_CAP) or 0)
    except (TypeError, ValueError):
        return None
    cap = db.chapter_by_id(con, cap_id) if cap_id else None
    if cap is None:
        return None
    # Un mazo apagado después de elegir deja de contar: no se puede pedir que
    # se lea de un tema que ya no se estudia.
    activo = con.execute("SELECT enabled FROM decks WHERE id=?",
                         (cap["deck_id"],)).fetchone()
    return cap if activo and activo["enabled"] else None


def del_dia(con, ahora: float | None = None) -> dict | None:
    """El capítulo de hoy. Lo elige la primera vez y luego lo devuelve igual.

    Devuelve `None` solo si no hay ningún capítulo que leer en los mazos
    activos. Una vez terminado sigue devolviéndose el mismo: el día ya está
    cumplido y hay que poder decirlo, no proponer otra tarea.
    """
    vigente = _vigente(con, ahora)
    if vigente is not None:
        return vigente

    cap = recomendaciones.recomendar(con, ahora=ahora)["capitulo"]
    if cap is None:
        return None
    db.set_meta(con, CLAVE_FECHA, _hoy(ahora))
    db.set_meta(con, CLAVE_CAP, cap["id"])
    return cap


def hecha(con, ahora: float | None = None) -> bool:
    """¿Está terminada la lectura de hoy?"""
    cap = _vigente(con, ahora)
    return bool(cap and cap.get("leido"))


def racha(con, ahora: float | None = None) -> int:
    """Días seguidos terminando alguna lectura, hasta hoy.

    Cuenta igual que la racha de repasos: los días los agrupa SQLite en hora
    local, y si hoy todavía no has leído pero ayer sí, la racha se mantiene —
    se rompe al terminar el día, no al empezarlo.
    """
    dias = {r["d"] for r in con.execute(
        """SELECT DISTINCT date(ts, 'unixepoch', 'localtime') AS d
           FROM reading WHERE leido=1 AND ts > 0""")}
    if not dias:
        return 0
    ahora = time.time() if ahora is None else ahora
    hoy, ayer = _hoy(ahora), _hoy(ahora - 86400)
    if hoy not in dias and ayer not in dias:
        return 0
    cuando = ahora if hoy in dias else ahora - 86400
    n = 0
    while _hoy(cuando) in dias:
        n += 1
        cuando -= 86400
    return n
