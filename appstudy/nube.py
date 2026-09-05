"""Cuenta en la nube: tu progreso vive en Supabase y te sigue a otro equipo.

Se habla con el proyecto por HTTPS, con `urllib` de la biblioteca estándar: no
añade dependencias ni hace falta un driver de Postgres. Son dos servicios:

  * **Auth** (`/auth/v1`) comprueba el correo y la contraseña y devuelve un
    *access token* que dura una hora y un *refresh token* de larga vida. El
    refresh se guarda en disco, así que se entra **una sola vez por equipo**:
    en los siguientes arranques se canjea por un token nuevo sin preguntar
    nada. Supabase rota el refresh en cada canje, por eso siempre se vuelve a
    guardar lo que devuelve.
  * **REST** (`/rest/v1`) guarda y lee los snapshots que arma
    `sincronizacion`. Las políticas RLS de la tabla atan cada fila a
    `auth.uid()`, así que la base solo devuelve lo tuyo aunque varias personas
    compartan el mismo proyecto. La separación entre usuarios la impone
    Postgres, no esta aplicación.

La conexión directa a Postgres del `.env` (`db_database`) **no se usa**: ese
host solo resuelve por IPv6 —no serviría en una red sin IPv6— y esa contraseña
es la del superusuario, que se salta RLS. Aquí basta la clave `anon`, que es
pública por diseño y no da acceso a nada sin haber entrado.

Todo lo de aquí habla por red, así que debe llamarse **fuera del hilo de la
interfaz** (ver `util.hilo`).
"""
from __future__ import annotations

import base64
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import db

ESPERA = 30             # segundos; una fusión sube y baja unos cuantos MB
ESPERA_CORTA = 10       # para lo que no vale la pena esperar, como cerrar sesión
# Todo lo que se hace al cerrar la aplicación cabe aquí. Es un presupuesto, no
# un tiempo por petición: con la red caída, salir tarda esto y no el doble.
LIMITE_CIERRE = 8.0
MAX_SUBIDA = 8 * 1024 * 1024
MARGEN = 120.0          # se renueva el token cuando le quedan menos segundos
TABLA = "sync_snapshots"

_UID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
# postgresql://…@db.<referencia>.supabase.co:5432/… → https://<referencia>.supabase.co
_HOST_PG = re.compile(r"@db\.([a-z0-9]{16,32})\.supabase\.(co|in)\b", re.I)
_CORREO = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")


class NubeError(RuntimeError):
    """Algo salió mal hablando con Supabase; el mensaje es para enseñarlo."""

    def __init__(self, mensaje: str, codigo: int = 0):
        super().__init__(mensaje)
        self.codigo = codigo


# ------------------------------------------------------------------- ajustes

def _archivos_env() -> list[Path]:
    """Dónde se busca el `.env`: primero el del repositorio, luego el instalado."""
    config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return [Path(__file__).resolve().parent.parent / ".env",
            config / "appstudy" / ".env"]


def _env() -> dict:
    valores: dict[str, str] = {}
    for ruta in _archivos_env():
        try:
            texto = ruta.read_text(encoding="utf-8")
        except OSError:
            continue
        for linea in texto.splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, _, valor = linea.partition("=")
            clave = clave.strip().removeprefix("export ").strip().lower()
            # El primer archivo que la define gana; así el .env del repositorio
            # manda sobre el instalado mientras estás desarrollando.
            valores.setdefault(clave, valor.strip().strip("'\""))
    return valores


def _valor(*nombres: str) -> str:
    """El primero de esos nombres que esté puesto. El entorno manda sobre el .env."""
    archivo = _env()
    for nombre in nombres:
        valor = (os.environ.get(nombre) or os.environ.get(nombre.upper())
                 or archivo.get(nombre.lower()) or "")
        if valor.strip():
            return valor.strip()
    return ""


def ajustes() -> dict:
    """URL del proyecto y clave pública. La URL se deduce del URI de Postgres."""
    url = _valor("SUPABASE_URL", "supabase_url")
    if not url:
        coincide = _HOST_PG.search(_valor("db_database", "DATABASE_URL", "SUPABASE_DB_URL"))
        url = f"https://{coincide.group(1)}.supabase.{coincide.group(2)}" if coincide else ""
    return {"url": url.rstrip("/"),
            "anon": _valor("SUPABASE_ANON_KEY", "SUPABASE_KEY", "SUPABASE_PUBLISHABLE_KEY")}


def _es_clave_secreta(clave: str) -> bool:
    """¿Es la clave que se salta RLS? Nunca debe salir de un servidor.

    Confundirla con la pública es fácil —están juntas en el panel— y sale
    caro: con ella, cualquiera que tenga el `.env` lee y escribe los datos de
    todos los usuarios. Se reconocen las dos formas que usa Supabase, la nueva
    (`sb_secret_…`) y la antigua, que es un JWT con `role: service_role`.
    """
    if clave.startswith("sb_secret_"):
        return True
    partes = clave.split(".")
    if len(partes) != 3:
        return False
    try:
        relleno = "=" * (-len(partes[1]) % 4)
        carga = json.loads(base64.urlsafe_b64decode(partes[1] + relleno))
    except (ValueError, TypeError):
        return False
    return str(carga.get("role", "")) == "service_role"


AVISO_SECRETA = (
    "La clave puesta en SUPABASE_ANON_KEY es la SECRETA, la que se salta las "
    "políticas RLS: con ella cualquiera que tenga el archivo vería los datos de "
    "todos los usuarios. Cámbiala por la pública (empieza por «sb_publishable_», "
    "o la JWT marcada «anon / public») en Project Settings → API Keys, y revoca "
    "la secreta que ya copiaste.")


def configurada() -> bool:
    cfg = ajustes()
    return bool(cfg["url"] and cfg["anon"] and not _es_clave_secreta(cfg["anon"]))


def que_falta() -> str:
    """Mensaje para la interfaz cuando el .env está a medias. Vacío si está listo."""
    cfg = ajustes()
    if cfg["anon"] and _es_clave_secreta(cfg["anon"]):
        return AVISO_SECRETA
    if cfg["url"] and cfg["anon"]:
        return ""
    faltan = [n for n, v in (("SUPABASE_URL", cfg["url"]),
                             ("SUPABASE_ANON_KEY", cfg["anon"])) if not v]
    return ("Añade " + " y ".join(faltan) + f" a {_archivos_env()[0]} · las dos están "
            "en el panel de Supabase, en Project Settings → API")


def auto(con) -> bool:
    """Si la sincronización automática está activada. De fábrica, sí."""
    return str(db.get_meta(con, "nube_auto", "1")) not in ("0", "False", "false")


# -------------------------------------------------------------------- sesión

def _archivo_sesion() -> Path:
    return db.DATA_DIR / "sesion.json"


def _guardar_sesion(datos: dict) -> dict:
    """Escribe la sesión solo para ti (0600) y de una pieza, como el device-id."""
    ruta = _archivo_sesion()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=ruta.parent,
                                     prefix=".sesion-", delete=False) as f:
        json.dump(datos, f)
        f.flush()
        os.fsync(f.fileno())
        temporal = Path(f.name)
    try:
        temporal.chmod(0o600)
        temporal.replace(ruta)
    except OSError:
        temporal.unlink(missing_ok=True)
        raise
    return datos


def sesion() -> dict | None:
    """La sesión guardada, o None si no has entrado nunca en este equipo."""
    try:
        datos = json.loads(_archivo_sesion().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(datos, dict) or not str(datos.get("refresh_token") or ""):
        return None
    if not _UID.fullmatch(str(datos.get("user_id", ""))):
        return None
    return datos


def usuario() -> dict | None:
    """Quién está dentro: `{"user_id", "email"}`. No toca la red."""
    ses = sesion()
    return {"user_id": ses["user_id"], "email": ses.get("email", "")} if ses else None


def olvidar_sesion():
    _archivo_sesion().unlink(missing_ok=True)


# ---------------------------------------------------------------------- HTTP

def _mensaje_http(error: urllib.error.HTTPError) -> str:
    """Traduce el error de Supabase a algo que se pueda leer en la ventana."""
    try:
        cuerpo = json.loads(error.read().decode() or "{}")
    except (ValueError, OSError):
        cuerpo = {}
    crudo = str(cuerpo.get("msg") or cuerpo.get("message")
                or cuerpo.get("error_description") or cuerpo.get("error") or "").strip()
    bajo = crudo.lower()
    # Un 401 con esto no es tu sesión: es la clave del proyecto, y decir
    # «vuelve a entrar» mandaría a escribir la contraseña para nada.
    if "api key" in bajo:
        return ("La clave SUPABASE_ANON_KEY no vale para este proyecto · cópiala de "
                "Project Settings → API, en «anon / public»")
    if "invalid login credentials" in bajo:
        return "Correo o contraseña incorrectos"
    if "already registered" in bajo or "already been registered" in bajo:
        return "Ese correo ya tiene cuenta: entra en vez de crearla"
    if "email not confirmed" in bajo:
        return "Confirma el correo que te mandó Supabase y vuelve a entrar"
    if "password should be" in bajo or "weak password" in bajo:
        return f"Contraseña demasiado débil: {crudo}"
    if str(cuerpo.get("code") or "") in ("PGRST205", "42P01") or "does not exist" in bajo:
        return (f"Falta la tabla {TABLA} en tu proyecto: ejecuta supabase/esquema.sql "
                "en el editor SQL de Supabase")
    if error.code == 401:
        return "Tu sesión ya no vale; vuelve a entrar"
    if error.code == 429:
        return "Supabase está limitando los intentos; espera un minuto"
    return crudo or f"Supabase respondió {error.code}: {error.reason}"


def _pedir(ruta: str, cuerpo=None, metodo: str | None = None, acceso: str | None = None,
           cabeceras: dict | None = None, espera: float = ESPERA):
    """Una llamada al proyecto. Devuelve el JSON o levanta NubeError."""
    cfg = ajustes()
    if not (cfg["url"] and cfg["anon"]) or _es_clave_secreta(cfg["anon"]):
        raise NubeError(que_falta())
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    # La clave anon va siempre; sin token de usuario, RLS no deja ver nada.
    cab = {"apikey": cfg["anon"], "Content-Type": "application/json",
           "Authorization": f"Bearer {acceso or cfg['anon']}"}
    cab.update(cabeceras or {})
    peticion = urllib.request.Request(
        cfg["url"] + ruta, data=datos,
        method=metodo or ("POST" if datos is not None else "GET"), headers=cab)
    try:
        with urllib.request.urlopen(peticion, timeout=espera) as r:
            crudo = r.read().decode()
        return json.loads(crudo) if crudo.strip() else {}
    except urllib.error.HTTPError as e:
        raise NubeError(_mensaje_http(e), e.code) from e
    except urllib.error.URLError as e:
        raise NubeError(f"No pude conectar con {cfg['url']}: {e.reason}") from e
    except TimeoutError as e:
        raise NubeError(f"Supabase no respondió en {espera:.0f} s") from e
    except ValueError as e:
        raise NubeError(f"Supabase devolvió algo que no entiendo: {e}") from e


# ------------------------------------------------------------ entrar y salir

def _desde_auth(respuesta: dict) -> dict:
    acceso = str(respuesta.get("access_token") or "")
    refresco = str(respuesta.get("refresh_token") or "")
    quien = respuesta.get("user") or {}
    uid = str(quien.get("id") or "")
    if not (acceso and refresco and _UID.fullmatch(uid)):
        raise NubeError("Supabase no devolvió una sesión utilizable")
    return _guardar_sesion({
        "user_id": uid, "email": str(quien.get("email") or ""),
        "access_token": acceso, "refresh_token": refresco,
        "expira": time.time() + float(respuesta.get("expires_in") or 3600)})


def _credenciales(email: str, password: str) -> tuple[str, str]:
    email = (email or "").strip()
    if not _CORREO.fullmatch(email):
        raise NubeError("Ese correo no tiene buena pinta")
    if len(password or "") < 6:
        raise NubeError("La contraseña necesita al menos 6 caracteres")
    return email, password


def entrar(email: str, password: str) -> dict:
    """Inicia sesión y la deja guardada. Devuelve `{"user_id", "email"}`."""
    email, password = _credenciales(email, password)
    datos = _desde_auth(_pedir("/auth/v1/token?grant_type=password",
                               {"email": email, "password": password}))
    return {"user_id": datos["user_id"], "email": datos["email"]}


def registrar(email: str, password: str) -> dict | None:
    """Crea la cuenta. Devuelve la sesión, o None si el proyecto pide confirmar."""
    email, password = _credenciales(email, password)
    respuesta = _pedir("/auth/v1/signup", {"email": email, "password": password})
    if not respuesta.get("access_token"):
        return None                      # hay que confirmar el correo primero
    datos = _desde_auth(respuesta)
    return {"user_id": datos["user_id"], "email": datos["email"]}


def token(espera: float = ESPERA) -> str:
    """Un access token válido, renovándolo con el refresh si ya caducó.

    Esto es lo que hace que entrar una vez baste: el refresh no caduca por
    tiempo de uso, así que en cada arranque se cambia por un token nuevo.
    """
    ses = sesion()
    if not ses:
        raise NubeError("No has iniciado sesión en la nube")
    if ses.get("access_token") and float(ses.get("expira") or 0) - MARGEN > time.time():
        return ses["access_token"]
    try:
        datos = _desde_auth(_pedir("/auth/v1/token?grant_type=refresh_token",
                                   {"refresh_token": ses["refresh_token"]},
                                   espera=espera))
    except NubeError as e:
        if e.codigo in (400, 401, 403):
            # El refresh ya no vale (lo revocaste o cambiaste la contraseña):
            # no tiene sentido conservarlo, y así la ventana ofrece entrar.
            olvidar_sesion()
            raise NubeError("Tu sesión caducó; vuelve a entrar", e.codigo) from e
        raise
    return datos["access_token"]


def revocar(acceso: str | None):
    """Le dice a Supabase que ese token ya no sirve. Habla por red: va en su hilo.

    Que falle no es grave —un access token dura una hora y caduca solo—, así que
    salir nunca depende de tener internet.
    """
    if not acceso:
        return
    try:
        _pedir("/auth/v1/logout", {}, acceso=acceso, espera=ESPERA_CORTA)
    except NubeError:
        pass


def salir():
    """Cierra la sesión aquí y avisa al servidor. Los datos locales se quedan."""
    ses = sesion() or {}
    olvidar_sesion()                     # lo local es inmediato; la red, después
    revocar(ses.get("access_token"))


# ----------------------------------------------------------------- snapshots

def descargar_snapshots() -> list[dict]:
    """Los snapshots de todos tus equipos. RLS garantiza que solo salgan los tuyos."""
    filas = _pedir(f"/rest/v1/{TABLA}?select=device,datos", acceso=token())
    if not isinstance(filas, list):
        raise NubeError("La tabla de sincronización devolvió algo inesperado")
    return [f["datos"] for f in filas
            if isinstance(f, dict) and isinstance(f.get("datos"), dict)]


def subir_snapshot(datos: dict, espera: float = ESPERA, acceso: str | None = None):
    """Publica el snapshot de este equipo, reemplazando el anterior.

    `acceso` sirve para quien ya pidió el token y lleva su propio presupuesto de
    tiempo, como la subida de al cerrar.
    """
    equipo = str(datos.get("device") or "")
    if not equipo:
        raise NubeError("El snapshot no dice de qué equipo viene")
    peso = len(json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode())
    if peso > MAX_SUBIDA:
        raise NubeError(
            f"Tu biblioteca ocupa {peso / 1024 / 1024:.1f} MB y el límite de subida "
            f"son {MAX_SUBIDA // 1024 // 1024} MB · usa la carpeta compartida")
    _pedir(f"/rest/v1/{TABLA}", {"device": equipo, "datos": datos},
           acceso=acceso or token(espera=espera),
           cabeceras={"Prefer": "resolution=merge-duplicates,return=minimal"},
           espera=espera)
