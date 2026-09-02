"""Respaldo y restauración de la base de datos.

Todo tu progreso vive en un solo archivo SQLite, así que respaldar es copiarlo.
Pero copiarlo con `cp` mientras la aplicación escribe puede dejarte una copia a
medias (más aún con WAL, donde parte de lo reciente está en otro archivo). Por
eso aquí se usa la API de respaldo de SQLite, que hace una copia consistente de
una base abierta y en uso.

La restauración va al revés y sin reiniciar nada: se abre el archivo elegido y
se vuelca *dentro* de la conexión viva. Así las demás ventanas y la mascota, que
tienen su propia conexión al mismo archivo, siguen funcionando y ven los datos
nuevos.

No hay dependencias nuevas: sqlite3 y la biblioteca estándar.
"""
import re
import sqlite3
import time
from pathlib import Path

from . import db

CARPETA = db.DATA_DIR / "backups"
PREFIJO = "appstudy-"
SUFIJO = ".db"

# Cuántos respaldos automáticos se guardan. Con uno al día es algo más de un mes
# de historia; los manuales y los de «antes de restaurar» no se podan nunca.
MAXIMO_AUTO = 40
CADA = 86400.0        # un respaldo automático al día

# Las tablas sin las que un archivo no es una base de AppStudy
ESENCIALES = {"decks", "cards", "state", "log", "meta"}

_NOMBRE = re.compile(r"^appstudy-(\d{8}-\d{6})(?:-\d+)?-([a-z]+)\.db$")


def carpeta() -> Path:
    CARPETA.mkdir(parents=True, exist_ok=True)
    return CARPETA


def _libre(motivo: str) -> Path:
    """Una ruta que no exista todavía.

    El nombre lleva la hora al segundo, y dos respaldos pueden caer dentro del
    mismo: al restaurar se hace uno de seguridad justo antes de leer el que
    eliges, y si compartieran nombre el de seguridad machacaría al otro. Con un
    contador detrás eso no puede pasar.
    """
    sello = time.strftime("%Y%m%d-%H%M%S")
    ruta = carpeta() / f"{PREFIJO}{sello}-{motivo}{SUFIJO}"
    n = 2
    while ruta.exists():
        ruta = carpeta() / f"{PREFIJO}{sello}-{n}-{motivo}{SUFIJO}"
        n += 1
    return ruta


def copiar(con, destino: Path) -> Path:
    """Copia consistente de la base abierta `con` en `destino`."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    # A un archivo temporal primero: si algo falla a mitad no queda un respaldo
    # cortado con nombre de bueno, que es peor que no tener ninguno.
    parcial = destino.with_name(destino.name + ".parcial")
    otro = sqlite3.connect(parcial)
    try:
        con.backup(otro)
        otro.execute("VACUUM")          # sin el WAL ni el espacio libre: pesa menos
        otro.commit()
    finally:
        otro.close()
    parcial.replace(destino)
    return destino


def crear(con, motivo: str = "manual") -> Path:
    """Un respaldo nuevo en la carpeta de respaldos. Devuelve su ruta."""
    ruta = copiar(con, _libre(motivo))
    if motivo == "auto":
        podar()
    return ruta


def listar() -> list[dict]:
    """Los respaldos que hay, del más reciente al más antiguo."""
    if not CARPETA.exists():
        return []
    salida = []
    for f in CARPETA.glob(f"{PREFIJO}*{SUFIJO}"):
        m = _NOMBRE.match(f.name)
        if not m:
            continue
        try:
            cuando = time.mktime(time.strptime(m.group(1), "%Y%m%d-%H%M%S"))
        except ValueError:
            cuando = f.stat().st_mtime
        datos = f.stat()
        salida.append({"ruta": f, "ts": cuando, "motivo": m.group(2),
                       "bytes": datos.st_size, "mtime": datos.st_mtime})
    # El nombre solo llega al segundo, y dos respaldos pueden caer dentro del
    # mismo; la fecha del archivo desempata y el orden queda estable.
    return sorted(salida, key=lambda r: (r["ts"], r["mtime"]), reverse=True)


def ultimo(motivo: str | None = None) -> dict | None:
    for r in listar():
        if motivo is None or r["motivo"] == motivo:
            return r
    return None


def podar(maximo: int = MAXIMO_AUTO) -> int:
    """Deja solo los `maximo` respaldos automáticos más recientes."""
    autos = [r for r in listar() if r["motivo"] == "auto"]
    sobran = autos[maximo:]
    for r in sobran:
        r["ruta"].unlink(missing_ok=True)
    return len(sobran)


def auto_si_toca(con, cada: float = CADA) -> Path | None:
    """Un respaldo automático si el último ya tiene más de un día.

    Se llama al arrancar. Si falla no se avisa por pantalla: un respaldo que no
    sale no debe impedirte estudiar.
    """
    try:
        anterior = ultimo("auto")
        if anterior and time.time() - anterior["ts"] < cada:
            return None
        return crear(con, "auto")
    except (sqlite3.Error, OSError):
        return None


def revisar(ruta) -> str:
    """Comprueba que el archivo es una base de AppStudy. Devuelve un resumen.

    Lanza ValueError si no lo es: restaurar un archivo cualquiera encima de tu
    progreso sería la peor manera de perderlo.
    """
    ruta = Path(ruta)
    if not ruta.is_file():
        raise ValueError("Ese archivo no existe.")
    try:
        otro = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
        otro.row_factory = sqlite3.Row
    except sqlite3.Error as e:
        raise ValueError(f"No se puede abrir: {e}") from e
    try:
        try:
            tablas = {r[0] for r in otro.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        except sqlite3.DatabaseError as e:
            raise ValueError("No parece una base de datos SQLite.") from e
        faltan = ESENCIALES - tablas
        if faltan:
            raise ValueError("No es un respaldo de AppStudy: le faltan las tablas "
                             + ", ".join(sorted(faltan)) + ".")
        tarjetas = otro.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        repasos = otro.execute("SELECT COUNT(*) FROM log").fetchone()[0]
        fila = otro.execute("SELECT MAX(ts) FROM log").fetchone()
        ultimo_repaso = fila[0] if fila else None
    finally:
        otro.close()
    resumen = f"{tarjetas} tarjetas · {repasos} repasos"
    if ultimo_repaso:
        resumen += f" · el último, {time.strftime('%d/%m/%Y', time.localtime(ultimo_repaso))}"
    return resumen


def restaurar(con, ruta) -> Path:
    """Vuelca el respaldo `ruta` dentro de la base viva.

    Antes guarda un respaldo del estado actual, para que restaurar por error no
    sea el final. Devuelve la ruta de esa red de seguridad.
    """
    ruta = Path(ruta)
    revisar(ruta)                                   # lanza si no encaja
    red = crear(con, "antes")
    origen = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    try:
        origen.backup(con)                          # reemplaza el contenido vivo
    finally:
        origen.close()
    db.migrate(con)                                 # por si venía de una versión anterior
    con.commit()
    return red


def tamano(n: int) -> str:
    """El tamaño en algo que se pueda leer de un vistazo."""
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / 1024 / 1024:.1f} MB"


def cuando(ts: float) -> str:
    """La fecha de un respaldo, en relativo si es de hoy o de ayer."""
    ahora = time.time()
    hoy = time.strftime("%Y%m%d", time.localtime(ahora))
    dia = time.strftime("%Y%m%d", time.localtime(ts))
    hora = time.strftime("%H:%M", time.localtime(ts))
    if dia == hoy:
        return f"hoy a las {hora}"
    ayer = time.strftime("%Y%m%d", time.localtime(ahora - 86400))
    if dia == ayer:
        return f"ayer a las {hora}"
    return time.strftime("%d/%m/%Y a las %H:%M", time.localtime(ts))


MOTIVOS = {"auto": "automático", "manual": "a mano", "antes": "antes de restaurar"}


def describir(r: dict) -> str:
    return f"{cuando(r['ts'])} · {tamano(r['bytes'])} · {MOTIVOS.get(r['motivo'], r['motivo'])}"
