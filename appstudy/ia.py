"""Conexión con un modelo de lenguaje local para preguntarle cosas a Bit.

El modelo corre **en tu máquina**, servido por Ollama (`http://localhost:11434`),
así que ni tus tarjetas ni tus preguntas salen del equipo, no hay clave de API
que guardar y no cuesta dinero. Nada de esto entra en el repositorio: los pesos
viven en `~/.ollama` y la configuración, en la base de datos.

No añade dependencias: habla HTTP con `urllib`, de la biblioteca estándar. Y
como una respuesta tarda segundos, todo lo que llama aquí debe hacerlo **fuera
del hilo de la interfaz** (ver `hilo()`).

Por eso las funciones que hablan con el modelo reciben `cfg` —el diccionario que
devuelve `config(con)`— y no la conexión: una conexión de SQLite solo se puede
usar en el hilo que la creó. Se lee la configuración en el hilo de la interfaz y
se le pasa el resultado al de trabajo.
"""
import json
import re
import threading
import urllib.error
import urllib.request

from . import db, util

URL_DEFECTO = "http://localhost:11434"
MODELO_DEFECTO = "gemma4"
ESPERA = 120            # segundos; un modelo local puede tardar en arrancar

# Cómo se comporta Bit cuando le preguntas. Corto y al grano: la respuesta se
# lee en un globo de 30 caracteres de ancho, no en una pantalla completa.
SISTEMA = """Eres Bit, la mascota de AppStudy, una aplicación de estudio con \
repetición espaciada. Ayudas a un estudiante que repasa inglés, Linux, ciencia \
de datos, inteligencia artificial, maquinaria pesada, mecánica automotriz y \
electricidad.

Reglas:
- Responde en español, salvo que te pregunten en otro idioma o sobre inglés.
- Sé breve: dos o tres frases, o una lista corta. Lo estás diciendo en un globo pequeño.
- Ve al grano, sin presentarte ni pedir disculpas.
- Si te dan el contexto de una tarjeta, apóyate en él y no lo contradigas.
- Si no lo sabes, dilo en una frase. No inventes datos, cifras ni referencias.
- Puedes usar <b>negrita</b> y <i>cursiva</i>, nada más de HTML."""


# ------------------------------------------------------------------ ajustes

def config(con) -> dict:
    """Lo que hay configurado. Vive en la base, nunca en el repositorio."""
    return {
        "activa": db.get_meta(con, "ia_activa", "0") == "1",
        "url": db.get_meta(con, "ia_url", URL_DEFECTO) or URL_DEFECTO,
        "modelo": db.get_meta(con, "ia_modelo", MODELO_DEFECTO) or MODELO_DEFECTO,
    }


def guardar(con, activa=None, url=None, modelo=None):
    if activa is not None:
        db.set_meta(con, "ia_activa", "1" if activa else "0")
    if url is not None:
        db.set_meta(con, "ia_url", url.rstrip("/") or URL_DEFECTO)
    if modelo is not None:
        db.set_meta(con, "ia_modelo", modelo)


# -------------------------------------------------------------------- HTTP

def _pedir(url: str, ruta: str, cuerpo=None, espera=ESPERA):
    """Una llamada al servidor local. Devuelve el JSON o levanta IAError."""
    destino = f"{url.rstrip('/')}{ruta}"
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    peticion = urllib.request.Request(
        destino, data=datos, method="POST" if datos else "GET",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(peticion, timeout=espera) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise IAError(f"El servidor respondió {e.code}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise IAError(f"No pude conectar con {url}. ¿Está Ollama en marcha?") from e
    except (TimeoutError, json.JSONDecodeError) as e:
        raise IAError(f"El modelo no respondió a tiempo ({ESPERA} s).") from e


class IAError(RuntimeError):
    """Algo salió mal hablando con el modelo; el mensaje es para enseñarlo."""


def modelos(url: str = URL_DEFECTO) -> list:
    """Los modelos instalados en el servidor, del más reciente al más viejo."""
    datos = _pedir(url, "/api/tags", espera=8)
    return [m["name"] for m in datos.get("models", [])]


def elegir_modelo(instalados: list, preferido: str) -> str | None:
    """El preferido si está; si no, cualquier gemma; si no, el primero que haya."""
    if not instalados:
        return None
    for nombre in instalados:                       # coincidencia exacta o por familia
        if nombre == preferido or nombre.split(":")[0] == preferido.split(":")[0]:
            return nombre
    gemmas = [n for n in instalados if n.lower().startswith("gemma")]
    return (gemmas or instalados)[0]


def probar(cfg: dict) -> tuple:
    """(ok, mensaje) para el botón «Probar conexión» de Ajustes."""
    c = cfg
    try:
        instalados = modelos(c["url"])
    except IAError as e:
        return False, str(e)
    if not instalados:
        return False, "Ollama responde, pero no hay ningún modelo descargado."
    elegido = elegir_modelo(instalados, c["modelo"])
    if elegido != c["modelo"]:
        return True, (f"Conectado. No encontré «{c['modelo']}», así que usaré "
                      f"«{elegido}» (hay {len(instalados)} modelos).")
    return True, f"Conectado con «{elegido}»."


# --------------------------------------------------------------- contexto

_PALABRA = re.compile(r"[a-záéíóúüñ0-9]{4,}")
_VACIAS = {"para", "como", "cual", "cuales", "donde", "cuando", "porque", "sobre",
           "esto", "esta", "este", "entre", "hace", "hacer", "tiene", "sirve",
           "significa", "diferencia", "explica", "explicame", "dime", "quiero"}


def buscar_contexto(con, pregunta: str, cuantas: int = 3) -> str:
    """Tus propias tarjetas que hablan de lo que preguntas.

    Un modelo pequeño improvisa cuando no sabe; darle tu material lo ancla a lo
    que de verdad estás estudiando. Es búsqueda por palabras, no por embeddings:
    suficiente para un mazo de cientos de tarjetas y sin nada que instalar.
    """
    palabras = [p for p in _PALABRA.findall(pregunta.lower()) if p not in _VACIAS]
    if not palabras:
        return ""
    condicion = " OR ".join(["LOWER(front) LIKE ? OR LOWER(back) LIKE ?"] * len(palabras))
    args = [f"%{p}%" for p in palabras for _ in (0, 1)]
    filas = con.execute(
        f"SELECT front, back FROM cards WHERE {condicion} LIMIT 40", args).fetchall()
    if not filas:
        return ""
    marcadas = []
    for f in filas:
        texto = f"{f['front']} {f['back']}".lower()
        marcadas.append((sum(1 for p in palabras if p in texto), f))
    marcadas.sort(key=lambda x: -x[0])
    trozos = [f"- {util.plain(f['front'])} → {util.plain(f['back'])[:300]}"
              for _, f in marcadas[:cuantas]]
    return "\n".join(trozos)


# ------------------------------------------------------------------ hablar

def _mensaje(cfg, mensajes, formato=None, temperatura=0.4, trozo=None) -> str:
    """Manda la conversación al modelo y devuelve el texto completo.

    Si se pasa `trozo`, se llama con cada pedazo según llega: así la respuesta
    aparece escribiéndose en vez de salir de golpe tras diez segundos.
    """
    c = cfg
    if not c["activa"]:
        raise IAError("La IA está desactivada. Actívala en Ajustes.")
    modelo = elegir_modelo(modelos(c["url"]), c["modelo"])
    if not modelo:
        raise IAError("No hay ningún modelo descargado. Prueba: ollama pull gemma3")

    cuerpo = {"model": modelo, "messages": mensajes, "stream": trozo is not None,
              # keep_alive: cargar el modelo en la gráfica cuesta casi un minuto;
              # así se queda listo media hora y las siguientes salen al instante.
              "keep_alive": "30m",
              "options": {"temperature": temperatura, "num_predict": 700}}
    if formato:
        cuerpo["format"] = formato

    if trozo is None:
        datos = _pedir(c["url"], "/api/chat", cuerpo)
        return (datos.get("message") or {}).get("content", "").strip()

    partes = []
    peticion = urllib.request.Request(
        f"{c['url'].rstrip('/')}/api/chat", data=json.dumps(cuerpo).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(peticion, timeout=ESPERA) as r:
            for linea in r:                       # Ollama devuelve un JSON por línea
                if not linea.strip():
                    continue
                dato = json.loads(linea.decode())
                pedazo = (dato.get("message") or {}).get("content", "")
                if pedazo:
                    partes.append(pedazo)
                    trozo(pedazo)
                if dato.get("done"):
                    break
    except urllib.error.URLError as e:
        raise IAError(f"Se cortó la conexión con el modelo: {e}") from e
    return "".join(partes).strip()


def _limpiar(texto: str) -> str:
    """Quita lo que un modelo suele colar de más y deja markup que Pango entienda."""
    t = re.sub(r"^```[a-zA-Z]*\n?|```$", "", texto.strip()).strip()
    t = re.sub(r"</?(?!/?(b|i|tt|code|u|s)\b)[a-zA-Z][^>]*>", "", t)   # HTML de más
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)                     # markdown común
    t = re.sub(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])", r"<i>\1</i>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    return t.strip()


def preguntar(cfg, pregunta: str, contexto: str = "", trozo=None) -> str:
    """Una pregunta suelta, con el contexto de la tarjeta que estés viendo."""
    usuario = pregunta.strip()
    if contexto:
        usuario = f"Contexto de lo que estoy estudiando:\n{contexto}\n\nPregunta: {usuario}"
    return _limpiar(_mensaje(cfg, [{"role": "system", "content": SISTEMA},
                                   {"role": "user", "content": usuario}], trozo=trozo))


# Cuántos mensajes del historial se le mandan. Un modelo pequeño se atasca (y se
# vuelve lento) si le pasas media hora de charla: con los últimos seis idas y
# vueltas se acuerda de lo que importa.
MEMORIA_CHAT = 12


def conversar(cfg, historial: list, pregunta: str, contexto: str = "", trozo=None) -> str:
    """Un turno de conversación: el modelo ve lo que ya habéis hablado.

    `historial` es una lista de {"role": "user"|"assistant", "content": str}; el
    que llama se encarga de ir añadiendo los turnos.
    """
    sistema = SISTEMA
    if contexto:
        sistema += ("\n\nEl estudiante viene de esta tarjeta, tenla presente:\n"
                    + contexto)
    mensajes = [{"role": "system", "content": sistema},
                *historial[-MEMORIA_CHAT:],
                {"role": "user", "content": pregunta.strip()}]
    return _limpiar(_mensaje(cfg, mensajes, trozo=trozo, temperatura=0.5))


def explicar(cfg, card, trozo=None) -> str:
    """Explica una tarjeta de otra manera: con otras palabras y un ejemplo."""
    frente, dorso = util.plain(card["front"]), util.plain(card["back"])
    usuario = (f"Esta es una tarjeta que estoy repasando:\n\nPregunta: {frente}\n"
               f"Respuesta: {dorso}\n\nExplícamelo con otras palabras, más simple, "
               f"y añade un ejemplo concreto. Máximo cuatro frases.")
    return _limpiar(_mensaje(cfg, [{"role": "system", "content": SISTEMA},
                                   {"role": "user", "content": usuario}], trozo=trozo))


ESQUEMA_TARJETAS = {
    "type": "object",
    "properties": {
        "tarjetas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"front": {"type": "string"}, "back": {"type": "string"}},
                "required": ["front", "back"],
            },
        }
    },
    "required": ["tarjetas"],
}


def generar_tarjetas(cfg, tema: str, cuantas: int = 5, nivel: str = "intermedio") -> list:
    """Propone tarjetas nuevas sobre un tema. Tú decides si se guardan."""
    usuario = (
        f"Crea {cuantas} tarjetas de estudio de nivel {nivel} sobre: {tema}.\n\n"
        "Cada tarjeta: 'front' es una pregunta clara y concreta (una sola idea), "
        "'back' es la respuesta completa pero breve, de dos o tres frases. "
        "Nada de preguntas de sí/no ni de definiciones de diccionario: "
        "pregunta por lo que de verdad hay que entender o recordar. "
        "Responde solo con el JSON.")
    crudo = _mensaje(cfg, [{"role": "system", "content": SISTEMA},
                           {"role": "user", "content": usuario}],
                     formato=ESQUEMA_TARJETAS, temperatura=0.7)
    try:
        datos = json.loads(crudo)
    except json.JSONDecodeError:
        trozo = re.search(r"\{.*\}", crudo, re.S)     # por si envuelve el JSON en texto
        if not trozo:
            raise IAError("El modelo no devolvió tarjetas que pueda leer.") from None
        datos = json.loads(trozo.group(0))
    salida = []
    for t in datos.get("tarjetas", []):
        frente, dorso = str(t.get("front", "")).strip(), str(t.get("back", "")).strip()
        if frente and dorso:
            salida.append({"front": _limpiar(frente), "back": _limpiar(dorso)})
    if not salida:
        raise IAError("El modelo no propuso ninguna tarjeta.")
    return salida


def generar_desde_texto(cfg, fragmento: str, titulo: str, cuantas: int = 5) -> list:
    """Tarjetas sacadas de un trozo de libro: solo de lo que pone ahí.

    Es la diferencia entre estudiar tu biblioteca y estudiar lo que el modelo
    recuerde del mundo: aquí se le prohíbe expresamente salirse del texto.
    """
    usuario = (
        f"Este es un fragmento de «{titulo}»:\n\n---\n{fragmento}\n---\n\n"
        f"Escribe {cuantas} tarjetas de estudio **solo con lo que dice este "
        "fragmento**. Nada de conocimiento externo: si algo no está en el texto, "
        "no lo preguntes. 'front' es la pregunta, 'back' la respuesta en dos o "
        "tres frases. Pregunta por lo importante —procedimientos, cifras, "
        "definiciones, causas— y no por detalles de maquetación ni por el índice. "
        "Responde solo con el JSON.")
    crudo = _mensaje(cfg, [{"role": "system", "content": SISTEMA},
                           {"role": "user", "content": usuario}],
                     formato=ESQUEMA_TARJETAS, temperatura=0.4)
    try:
        datos = json.loads(crudo)
    except json.JSONDecodeError:
        trozo = re.search(r"\{.*\}", crudo, re.S)
        if not trozo:
            raise IAError("El modelo no devolvió tarjetas que pueda leer.") from None
        datos = json.loads(trozo.group(0))
    salida = []
    for t in datos.get("tarjetas", []):
        frente, dorso = str(t.get("front", "")).strip(), str(t.get("back", "")).strip()
        if frente and dorso:
            salida.append({"front": _limpiar(frente), "back": _limpiar(dorso)})
    if not salida:
        raise IAError("El modelo no sacó nada de este fragmento.")
    return salida


# -------------------------------------------------------------------- hilos

def hilo(trabajo, al_terminar, al_fallar=None):
    """Corre `trabajo()` en segundo plano y devuelve el resultado en el hilo de GTK.

    Una respuesta tarda segundos: hacerlo en el hilo principal congelaría la
    ventana (y la mascota dejaría de moverse a media frase).
    """
    from gi.repository import GLib

    def dentro():
        try:
            resultado = trabajo()
        except Exception as e:                        # se enseña, no se traga
            if al_fallar:
                GLib.idle_add(al_fallar, e)
            return
        GLib.idle_add(al_terminar, resultado)

    h = threading.Thread(target=dentro, daemon=True)
    h.start()
    return h
