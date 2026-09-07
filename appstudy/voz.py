"""Síntesis de voz (TTS) para AppStudy y Bit.

Permite leer tarjetas, citas y respuestas de IA en voz alta bajo demanda o de
forma automática, sincronizando el movimiento de la boca de Bit con la locución.

Utiliza el motor neuronal de alta calidad Piper si está instalado localmente,
lo que produce una voz humana, cálida y natural (no robótica). Si no está,
recurre a `spd-say` (speech-dispatcher) o la biblioteca `speechd` del sistema.

La calidad de la locución depende de tres cosas, y aquí se cuidan las tres:
la voz elegida (se prefiere el modelo de mayor calidad instalado), los
parámetros de inferencia de Piper (afinados para una dicción más clara que la
de fábrica) y el texto que se le entrega, que se limpia y se puntúa para que
la entonación y las pausas suenen a persona y no a lector de listas.
"""
import itertools
import json
import os
import re
import shutil
import struct
import subprocess
import threading
import time
from pathlib import Path

from . import db

PIPER_DIR = Path.home() / ".local" / "share" / "appstudy" / "piper"
PIPER_BIN = PIPER_DIR / "piper"
PIPER_MODEL_ES = PIPER_DIR / "es_ES-davefx-medium.onnx"
PIPER_MODEL_EN = PIPER_DIR / "en_US-lessac-medium.onnx"
PIPER_MODEL = PIPER_MODEL_ES  # retrocompatibilidad

# Orden de preferencia de las voces instaladas (mejor calidad primero). Se usa
# junto al descubrimiento automático de modelos: si el usuario instaló una voz
# "high", se prefiere sobre la "medium" aunque no esté en esta lista.
# El orden es de escucha, no de tamaño: sharvard (medium) suena más natural en
# español que las "high" disponibles, así que va primero.
VOCES_PREFERIDAS = {
    "es": ["es_ES-sharvard-medium", "es_MX-claude-high", "es_MX-ald-medium",
           "es_ES-davefx-medium"],
    "en": ["en_US-lessac-high", "en_US-ryan-high", "en_US-amy-medium",
           "en_US-lessac-medium"],
}
CALIDAD_ORDEN = {"high": 0, "medium": 1, "low": 2, "x_low": 3}

# Parámetros de inferencia afinados de oído para que la locución suene humana.
# Subir el ruido del generador y la variación de duración por fonema por encima
# de los valores de fábrica (0.667 y 0.8) es lo que quita el aire robótico:
# la entonación varía y el ritmo deja de ser regular como un metrónomo. Bajarlos
# da una dicción más "limpia" pero plana, que es justo lo que suena a máquina.
PIPER_NOISE_SCALE = 0.7
PIPER_NOISE_W = 0.9
# Un habla ligeramente más lenta que la nominal se percibe como más natural y
# se sigue mejor al estudiar. Es la base sobre la que actúa la velocidad.
PIPER_LENGTH_BASE = 1.06
PIPER_SILENCIO_FRASE = 0.35

KOKORO_DIR = Path.home() / ".local" / "share" / "appstudy" / "kokoro"
KOKORO_MODELO = KOKORO_DIR / "kokoro-v1.0.onnx"
KOKORO_VOCES_BIN = KOKORO_DIR / "voices-v1.0.bin"
KOKORO_PYTHON = Path.home() / ".local" / "share" / "appstudy" / "tts-venv" / "bin" / "python"
KOKORO_SCRIPT = Path(__file__).with_name("tts_kokoro.py")
KOKORO_SAMPLE_RATE = 24000

# Voces de Kokoro elegidas de oído. Cambiarlas es cambiar esta línea.
KOKORO_VOZ = {"es": "em_santa", "en": "af_heart"}
# Kokoro suena mejor un pelín por debajo de su velocidad nominal.
KOKORO_VELOCIDAD_BASE = 0.95
# Ritmo medido (palabras/segundo) para estimar la duración de la animación.
KOKORO_PALABRAS_SEG = 2.45

_cache_modelos: dict[str, Path | None] = {}
_cache_config_modelo: dict[str, dict] = {}


def _idioma_corto(idioma: str | None) -> str:
    return "en" if idioma and str(idioma).lower().startswith("en") else "es"


def _calidad_modelo(nombre: str) -> int:
    for sufijo, orden in CALIDAD_ORDEN.items():
        if nombre.endswith("-" + sufijo):
            return orden
    return 9


def modelo_para(idioma: str | None = None) -> Path | None:
    """Devuelve el mejor modelo Piper instalado para el idioma pedido.

    Prefiere las voces de la lista `VOCES_PREFERIDAS` y, si no hay ninguna,
    cualquier modelo del idioma correcto ordenado por calidad (high > medium).
    """
    lang = _idioma_corto(idioma)
    if lang in _cache_modelos:
        cacheado = _cache_modelos[lang]
        if cacheado is None or cacheado.is_file():
            return cacheado

    encontrado = None
    if PIPER_DIR.is_dir():
        disponibles = {m.stem: m for m in PIPER_DIR.glob("*.onnx") if m.is_file()}
        for nombre in VOCES_PREFERIDAS.get(lang, []):
            if nombre in disponibles:
                encontrado = disponibles[nombre]
                break
        if encontrado is None:
            candidatos = [m for n, m in disponibles.items() if n.lower().startswith(lang)]
            if candidatos:
                encontrado = sorted(candidatos, key=lambda m: (_calidad_modelo(m.stem), m.stem))[0]

    _cache_modelos[lang] = encontrado
    return encontrado


def tiene_kokoro() -> bool:
    """Indica si el motor Kokoro (entorno aislado + modelos) está instalado."""
    return (KOKORO_PYTHON.is_file() and os.access(KOKORO_PYTHON, os.X_OK)
            and KOKORO_MODELO.is_file() and KOKORO_VOCES_BIN.is_file()
            and KOKORO_SCRIPT.is_file())


class MotorKokoro:
    """Mantiene vivo el proceso de Kokoro y le pide locuciones de una en una.

    El proceso se conserva entre tarjetas porque cargar el modelo cuesta medio
    segundo. Las peticiones se serializan con un turno: mientras una locución se
    está generando, la siguiente espera a que la anterior termine de vaciarse.
    """

    def __init__(self):
        self._proc = None
        self._turno = threading.Lock()

    def _vivo(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _arrancar(self) -> bool:
        if self._vivo():
            return True
        self.parar()
        try:
            self._proc = subprocess.Popen(
                [str(KOKORO_PYTHON), str(KOKORO_SCRIPT)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            self._proc = None
            return False
        return True

    def parar(self):
        proc, self._proc = self._proc, None
        if proc is not None:
            try:
                proc.terminate()
            except OSError:
                pass

    def pedir(self, texto: str, voz: str, idioma: str, velocidad: float) -> bool:
        """Envía una petición. El turno queda tomado hasta llamar a `soltar`."""
        self._turno.acquire()
        if not self._arrancar():
            self._turno.release()
            return False
        peticion = json.dumps({"texto": texto, "voz": voz, "idioma": idioma,
                               "velocidad": velocidad}, ensure_ascii=False)
        try:
            self._proc.stdin.write((peticion + "\n").encode("utf-8"))
            self._proc.stdin.flush()
        except Exception:
            self.parar()
            self._turno.release()
            return False
        return True

    def tramas(self):
        """Devuelve los trozos de audio de la locución en curso, uno a uno."""
        proc = self._proc
        if proc is None:
            return
        while True:
            try:
                cabecera = proc.stdout.read(4)
                if len(cabecera) < 4:
                    self.parar()  # el ayudante murió: se reabrirá en la siguiente
                    return
                tam = struct.unpack("<I", cabecera)[0]
                if tam == 0:
                    return
                datos = proc.stdout.read(tam)
                if len(datos) < tam:
                    self.parar()
                    return
            except Exception:
                self.parar()
                return
            yield datos

    def soltar(self):
        try:
            self._turno.release()
        except RuntimeError:
            pass


_kokoro = MotorKokoro()


def config_modelo(modelo: Path) -> dict:
    """Lee el .json del modelo (frecuencia de muestreo y parámetros de voz)."""
    clave = str(modelo)
    if clave in _cache_config_modelo:
        return _cache_config_modelo[clave]
    datos = {"sample_rate": 22050, "noise_scale": PIPER_NOISE_SCALE,
             "noise_w": PIPER_NOISE_W}
    try:
        with open(str(modelo) + ".json", encoding="utf-8") as f:
            crudo = json.load(f)
        datos["sample_rate"] = int(crudo.get("audio", {}).get("sample_rate", 22050))
    except Exception:
        pass
    _cache_config_modelo[clave] = datos
    return datos

STOPWORDS_EN = {
    "the", "be", "to", "of", "and", "that", "have", "i", "it", "for", "not",
    "on", "with", "he", "as", "you", "do", "at", "this", "but", "his", "by", "from",
    "they", "we", "say", "her", "she", "or", "an", "will", "my", "one", "all", "would",
    "there", "their", "what", "so", "up", "out", "if", "about", "who", "get", "which",
    "go", "when", "make", "can", "like", "time", "just", "him", "know",
    "take", "people", "into", "year", "your", "good", "some", "could", "them", "see",
    "other", "than", "then", "now", "look", "only", "come", "its", "over", "think",
    "also", "back", "after", "use", "two", "how", "our", "work", "first", "well",
    "way", "even", "new", "want", "because", "any", "these", "give", "day", "most",
    "us", "is", "are", "was", "were", "been", "has", "had", "does", "did", "doing",
    "don't", "doesn't", "didn't", "won't", "can't", "should", "must", "might",
    "choose", "correct", "sentence", "meaning", "words", "fill", "blank", "listen",
    "answer", "question", "questions", "following", "where", "why"
}

STOPWORDS_ES = {
    "de", "la", "que", "el", "en", "y", "los", "del", "se", "las", "por", "un", "para",
    "con", "una", "su", "al", "lo", "como", "más", "pero", "sus", "le", "ya", "o",
    "este", "sí", "porque", "esta", "entre", "cuando", "muy", "sin", "sobre", "también",
    "hasta", "hay", "donde", "quien", "desde", "todo", "nos", "durante", "todos",
    "uno", "les", "ni", "contra", "otros", "ese", "eso", "ante", "ellos", "e", "esto",
    "mí", "antes", "algunos", "qué", "unos", "yo", "otro", "otras", "otra", "él", "tanto",
    "esa", "estos", "mucho", "quienes", "nada", "muchos", "cual", "poco", "ella", "estar",
    "estas", "algunas", "algo", "nosotros", "mi", "mis", "tú", "te", "ti", "tu", "tus",
    "es", "son", "fue", "era", "ser", "ha", "han", "hemos", "está", "están", "estaba"
}


def _val_tarjeta(card, clave: str, defecto: str = "") -> str:
    if not card:
        return defecto
    try:
        val = card[clave]
        return "" if val is None else str(val)
    except Exception:
        return defecto


def es_tarjeta_ingles(card: dict | None = None, texto: str = "") -> bool:
    """Determina si una tarjeta o texto corresponde al idioma inglés.

    Se usa para seleccionar automáticamente el modelo de voz en inglés en Piper o spd-say,
    evitando que las tarjetas de inglés se lean literalmente con fonética española.
    """
    palabras = re.findall(r"[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ']+", texto.lower()) if texto else []
    cuenta_en = sum(1 for p in palabras if p in STOPWORDS_EN)
    cuenta_es = sum(1 for p in palabras if p in STOPWORDS_ES)

    # Si el texto es predominantemente una explicación o frase en español, usar español
    if cuenta_es >= 4 and cuenta_es > cuenta_en * 2:
        return False

    if card:
        deck_key = _val_tarjeta(card, "deck_key").lower()
        deck_name = _val_tarjeta(card, "deck_name").lower()
        if deck_key in ("ingles", "english", "en") or "ingl" in deck_name or "english" in deck_name:
            return True
        tags = _val_tarjeta(card, "tags").lower()
        for t in re.split(r"[\s,;]+", tags):
            if t in ("ingles", "inglés", "english", "grammar", "vocabulary", "idioms", "en"):
                return True

    # Detección heurística en texto libre sin tarjeta
    if cuenta_en >= 2 and cuenta_en > cuenta_es:
        return True
    if cuenta_en >= 1 and cuenta_es == 0 and len(palabras) <= 4:
        return True

    return False


def detectar_idioma(card: dict | None = None, texto: str = "") -> str:
    """Devuelve 'en' si es inglés, 'es' si es español."""
    return "en" if es_tarjeta_ingles(card=card, texto=texto) else "es"


def tiene_motor_neuronal(idioma: str | None = None) -> bool:
    """Indica si el motor de voz neuronal (Piper) está disponible."""
    if not (PIPER_BIN.is_file() and os.access(PIPER_BIN, os.X_OK)):
        return False
    return modelo_para(idioma) is not None


def motor_actual() -> str:
    """Motor de voz que se usará: 'kokoro', 'piper', 'spd-say' o ''."""
    if tiene_kokoro():
        return "kokoro"
    if tiene_motor_neuronal():
        return "piper"
    return "spd-say" if shutil.which("spd-say") else ""


def voz_actual(idioma: str | None = None) -> str:
    """Nombre legible de la voz en uso (para mostrarla en Ajustes)."""
    if tiene_kokoro():
        return KOKORO_VOZ.get(_idioma_corto(idioma), "")
    modelo = modelo_para(idioma)
    return modelo.stem if modelo else ""


def limpiar_para_voz(texto: str) -> str:
    """Limpia etiquetas HTML, markdown, cloze y fórmulas para que suene natural."""
    if not texto:
        return ""
    # Cloze deletions: {{palabra}} o {{palabra::pista}} -> palabra
    from . import cloze
    if cloze.tiene_huecos(texto):
        texto = cloze.completo(texto)
    # Por si queda algún resto con prefijo Anki c1::
    t = re.sub(r"\{\{c\d+::(.*?)(?:::.*?)?\}\}", r"\1", texto)
    # Fórmulas matemáticas sencillas: $x^2$ -> x^2
    t = re.sub(r"\$\$?(.*?)\$\$?", r"\1", t)
    # URLs: enlace
    t = re.sub(r"https?://\S+", "enlace", t)
    # Pango markup / HTML tags: <b>, <i>, <span...>, etc.
    t = re.sub(r"<[^>]+>", "", t)
    # Bloques de código
    t = re.sub(r"```[\w]*\n?", " ", t)
    # Símbolos de markdown
    t = re.sub(r"[*_`#~]", "", t)
    # Emojis, símbolos y dingbats (incluye ✨, ⚡, etc.)
    t = re.sub(r"[\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff\u2b50-\u2b55\ufe00-\ufe0f]", "", t)
    # Caracteres de puntuación ornamental o viñetas
    t = re.sub(r"[•·—–―«»“”\"\'\(\)\[\]\{\}]", " ", t)
    # Viñetas de lista al principio de línea: no se leen
    t = re.sub(r"(?m)^[ \t]*[-+*]\s+", "", t)
    # Cada salto de línea es una frase: se le pone punto para que Piper haga la
    # pausa correspondiente en vez de leerlo todo de corrido.
    t = re.sub(r"[ \t]*\n+[ \t]*", ". ", t)
    t = re.sub(r"([,.:;!?¡¿])\.\s", r"\1 ", t)
    # Espacios duplicados
    t = re.sub(r"\s+", " ", t).strip()
    # Limpiar espacios previos a signos de puntuación
    t = re.sub(r"\s+([,.:;!?])", r"\1", t)
    # Puntuación repetida: alarga las pausas sin aportar nada
    t = re.sub(r"([.,:;!?])\1{1,}", r"\1", t)
    t = re.sub(r"^[.,:;]+\s*", "", t)
    return t


ABREVIATURAS_ES = [
    (r"\bp\.?\s?ej\.", "por ejemplo"),
    (r"\betc\.", "etcétera."),
    (r"\bEE\.?\s?UU\.?", "Estados Unidos"),
    (r"\bDr\.", "doctor"),
    (r"\bDra\.", "doctora"),
    (r"\bSr\.", "señor"),
    (r"\bSra\.", "señora"),
    (r"\bnúm\.", "número"),
]

ABREVIATURAS_EN = [
    (r"\be\.g\.", "for example"),
    (r"\bi\.e\.", "that is"),
    (r"\betc\.", "et cetera."),
    (r"\bvs\.?", "versus"),
    (r"\bMr\.", "mister"),
    (r"\bMrs\.", "missus"),
]

SIMBOLOS = {
    "es": [("%", " por ciento"), ("&", " y "), ("+", " más "), ("=", " igual a "),
           ("→", ", entonces, "), ("<", " menor que "), (">", " mayor que ")],
    "en": [("%", " percent"), ("&", " and "), ("+", " plus "), ("=", " equals "),
           ("→", ", then, "), ("<", " less than "), (">", " greater than ")],
}


def preparar_prosodia(texto: str, idioma: str = "es") -> str:
    """Ajusta el texto ya limpio para que la locución suene natural.

    Desarrolla abreviaturas y símbolos que los motores leen letra por letra y
    cierra la frase con un punto para que Piper module la entonación final.
    """
    if not texto:
        return ""
    lang = _idioma_corto(idioma)
    t = texto
    for patron, reemplazo in (ABREVIATURAS_EN if lang == "en" else ABREVIATURAS_ES):
        t = re.sub(patron, reemplazo, t, flags=re.IGNORECASE)
    for simbolo, palabra in SIMBOLOS[lang]:
        t = t.replace(simbolo, palabra)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s+([,.:;!?])", r"\1", t)
    if t and t[-1] not in ".!?:;":
        t += "."
    return t


def duracion_estimada(texto: str, velocidad: int = 0) -> float:
    """Estima la duración en segundos para sincronizar la animación de la boca."""
    limpio = limpiar_para_voz(texto)
    palabras = len(limpio.split())
    if palabras == 0:
        return 0.0
    factor = max(0.5, min(2.0, 1.0 + (velocidad / 100.0)))
    # Ritmos medidos de cada motor con sus parámetros; cada frase añade además
    # el silencio de cierre con el que se separan.
    palabras_seg = KOKORO_PALABRAS_SEG if tiene_kokoro() else 2.65
    frases = max(1, len(re.findall(r"[.!?]+(?:\s|$)", limpio)))
    segundos = (palabras / palabras_seg) / factor + 0.4 + (frases - 1) * PIPER_SILENCIO_FRASE
    return round(max(1.2, min(120.0, segundos)), 2)


def config(con) -> dict:
    """Configuración de voz guardada en la base de datos."""
    try:
        volumen = int(db.get_meta(con, "voz_volumen", 100))
    except (TypeError, ValueError):
        volumen = 100
    try:
        velocidad = int(db.get_meta(con, "voz_velocidad", 0))
    except (TypeError, ValueError):
        velocidad = 0
    try:
        tono = int(db.get_meta(con, "voz_tono", 0))
    except (TypeError, ValueError):
        tono = 0
    return {
        "activo": db.get_meta(con, "voz_activo", "1") == "1",
        "auto": db.get_meta(con, "voz_auto", "1") == "1",
        "volumen": max(0, min(100, volumen)),
        "velocidad": max(-50, min(50, velocidad)),
        "tono": max(-50, min(50, tono)),
        "idioma": str(db.get_meta(con, "voz_idioma", "es")),
        "clave": db.get_meta(con, "voz_clave", "1") == "1",
        "neuronal": tiene_motor_neuronal() or tiene_kokoro(),
        "motor": motor_actual(),
    }


def guardar(con, activo=None, auto=None, volumen=None, velocidad=None, tono=None,
            idioma=None, clave=None):
    """Guarda cambios en la configuración de voz."""
    if activo is not None:
        db.set_meta(con, "voz_activo", "1" if activo else "0")
    if auto is not None:
        db.set_meta(con, "voz_auto", "1" if auto else "0")
    if volumen is not None:
        db.set_meta(con, "voz_volumen", int(max(0, min(100, volumen))))
    if velocidad is not None:
        db.set_meta(con, "voz_velocidad", int(max(-50, min(50, velocidad))))
    if tono is not None:
        db.set_meta(con, "voz_tono", int(max(-50, min(50, tono))))
    if idioma is not None:
        db.set_meta(con, "voz_idioma", str(idioma))
    if clave is not None:
        db.set_meta(con, "voz_clave", "1" if clave else "0")


def _notificar_fin(cb):
    try:
        from gi.repository import GLib
        GLib.idle_add(cb)
    except Exception:
        try:
            cb()
        except Exception:
            pass


class ReproductorVoz:
    def __init__(self):
        self._lock = threading.Lock()
        self._proc = None
        self._proc_piper = None
        self._proc_filtro = None
        self._hablando = False
        self._spd_cmd = shutil.which("spd-say")
        self._sox_cmd = shutil.which("sox")
        self._token = 0

    def esta_hablando(self) -> bool:
        with self._lock:
            if self._proc is not None:
                if self._proc.poll() is None:
                    return True
                self._proc = None
            return self._hablando

    def detener(self):
        with self._lock:
            self._token += 1
            self._hablando = False
            for atributo in ("_proc_piper", "_proc_filtro"):
                proc = getattr(self, atributo, None)
                if proc is not None:
                    try:
                        proc.terminate()
                    except OSError:
                        pass
                    setattr(self, atributo, None)
            if self._proc is not None:
                try:
                    self._proc.terminate()
                except OSError:
                    pass
                self._proc = None

    def reproducir(self, texto: str, cfg: dict, duracion: float, on_done=None):
        self.detener()
        idioma = cfg.get("idioma", "es")
        if tiene_kokoro():
            self._reproducir_kokoro(texto, cfg, duracion, on_done)
        elif tiene_motor_neuronal(idioma):
            self._reproducir_piper(texto, cfg, duracion, on_done)
        elif self._spd_cmd:
            self._reproducir_spdsay(texto, cfg, duracion, on_done)
        else:
            self._reproducir_speechd(texto, cfg, duracion, on_done)

    def _player(self) -> str | None:
        return next((c for c in ("paplay", "pw-play", "aplay") if shutil.which(c)), None)

    def _tuberia(self, player: str, rate: str, vol: int, tono) -> tuple[list | None, list]:
        """Filtro de tono (si hay sox) y reproductor, ambos en PCM crudo."""
        tono = int(tono or 0)
        cmd_filtro = None
        if tono and self._sox_cmd:
            cents = str(int(max(-50, min(50, tono)) * 6))  # ±50 → ±3 semitonos
            crudo = ["-t", "raw", "-r", rate, "-e", "signed", "-b", "16", "-c", "1"]
            cmd_filtro = [self._sox_cmd, "-q", *crudo, "-", *crudo, "-", "pitch", cents]

        if player == "paplay":
            vol_pa = str(int(max(0, min(100, vol)) * 655.36))
            cmd_player = ["paplay", "--raw", "--rate", rate, "--channels", "1",
                          "--format", "s16le", "--volume", vol_pa]
        elif player == "pw-play":
            vol_pw = str(round(max(0.0, min(1.0, vol / 100.0)), 2))
            # Sin --raw, pw-play intenta leer una cabecera de archivo y falla.
            cmd_player = ["pw-play", "--raw", "--rate", rate, "--channels", "1",
                          "--format", "s16", "--volume", vol_pw, "-"]
        else:
            cmd_player = ["aplay", "-q", "-r", rate, "-c", "1", "-f", "S16_LE", "-t", "raw", "-"]
        return cmd_filtro, cmd_player

    def _reproducir_kokoro(self, texto: str, cfg: dict, duracion: float, on_done=None):
        player = self._player()
        vol = cfg.get("volumen", 100)
        if not player or vol <= 0:
            self._reproducir_piper(texto, cfg, duracion, on_done)
            return

        idioma = _idioma_corto(cfg.get("idioma", "es"))
        factor = max(0.5, min(2.0, 1.0 + (cfg.get("velocidad", 0) / 100.0)))
        velocidad = round(KOKORO_VELOCIDAD_BASE * factor, 3)
        rate = str(KOKORO_SAMPLE_RATE)
        cmd_filtro, cmd_player = self._tuberia(player, rate, vol, cfg.get("tono", 0))

        with self._lock:
            self._token += 1
            token = self._token
            # Se marca ya, antes de generar: quien pregunte si Bit está hablando
            # (el botón de altavoz, la boca) debe verlo desde el primer momento.
            self._hablando = True

        def _ejecutar():
            if not _kokoro.pedir(texto, KOKORO_VOZ.get(idioma, "em_santa"), idioma, velocidad):
                self._marcar_callado(token)
                self._reproducir_piper(texto, cfg, duracion, on_done)
                return
            try:
                self._reproducir_tramas(_kokoro.tramas(), cmd_filtro, cmd_player, token, on_done)
            finally:
                _kokoro.soltar()

        threading.Thread(target=_ejecutar, daemon=True).start()

    def _marcar_callado(self, token: int):
        """Baja la bandera de "hablando" salvo que ya haya otra locución en curso."""
        with self._lock:
            if token == self._token:
                self._hablando = False

    def _reproducir_tramas(self, tramas, cmd_filtro, cmd_player, token, on_done):
        """Vuelca el audio que va llegando del motor en la tubería de sonido.

        Si la locución se cancela mientras tanto, se dejan de escribir tramas
        pero se siguen consumiendo: así el motor termina limpio y sigue caliente
        para la siguiente tarjeta en vez de tener que rearrancarlo.
        """
        primera = next(iter(tramas), None)
        if primera is None:  # el motor no dio audio
            self._marcar_callado(token)
            if on_done:
                _notificar_fin(on_done)
            return

        with self._lock:
            vigente = token == self._token
        if not vigente:  # cancelada antes de sonar: se vacía el motor y ya está
            for _ in tramas:
                pass
            return

        with self._lock:
            try:
                p_filtro = None
                if cmd_filtro:
                    p_filtro = subprocess.Popen(cmd_filtro, stdin=subprocess.PIPE,
                                                stdout=subprocess.PIPE,
                                                stderr=subprocess.DEVNULL)
                    p_player = subprocess.Popen(cmd_player, stdin=p_filtro.stdout,
                                                stdout=subprocess.DEVNULL,
                                                stderr=subprocess.DEVNULL)
                    p_filtro.stdout.close()
                    entrada = p_filtro.stdin
                else:
                    p_player = subprocess.Popen(cmd_player, stdin=subprocess.PIPE,
                                                stdout=subprocess.DEVNULL,
                                                stderr=subprocess.DEVNULL)
                    entrada = p_player.stdin
                self._proc = p_player
                self._proc_filtro = p_filtro
            except Exception:
                if token == self._token:
                    self._hablando = False
                self._proc = None
                self._proc_filtro = None
                fallo = True
            else:
                fallo = False
        if fallo:
            for _ in tramas:
                pass
            return

        cancelada = False
        for datos in itertools.chain([primera], tramas):
            if cancelada or token != self._token:
                cancelada = True
                continue  # se sigue vaciando el motor, pero ya no suena
            try:
                entrada.write(datos)
                entrada.flush()
            except Exception:
                cancelada = True

        try:
            entrada.close()
        except Exception:
            pass
        if not cancelada:
            try:
                p_player.wait()
            except Exception:
                pass

        with self._lock:
            if self._proc is p_player:
                self._proc = None
                self._proc_filtro = None
                self._hablando = False
        if on_done and not cancelada:
            _notificar_fin(on_done)

    def _reproducir_piper(self, texto: str, cfg: dict, duracion: float, on_done=None):
        player = next((c for c in ("paplay", "pw-play", "aplay") if shutil.which(c)), None)
        if not player:
            if self._spd_cmd:
                self._reproducir_spdsay(texto, cfg, duracion, on_done)
            else:
                self._reproducir_speechd(texto, cfg, duracion, on_done)
            return

        vol = cfg.get("volumen", 100)
        if vol <= 0:
            return
        velocidad = cfg.get("velocidad", 0)
        factor = max(0.5, min(2.0, 1.0 + (velocidad / 100.0)))
        length_scale = round(PIPER_LENGTH_BASE / factor, 3)

        idioma = cfg.get("idioma", "es")
        modelo = modelo_para(idioma)
        if modelo is None:
            if self._spd_cmd:
                self._reproducir_spdsay(texto, cfg, duracion, on_done)
            return
        info = config_modelo(modelo)
        rate = str(info.get("sample_rate", 22050))

        cmd_piper = [
            str(PIPER_BIN),
            "--model", str(modelo),
            "--length_scale", str(length_scale),
            "--noise_scale", str(PIPER_NOISE_SCALE),
            "--noise_w", str(PIPER_NOISE_W),
            "--sentence_silence", str(PIPER_SILENCIO_FRASE),
            "--quiet",
            "--output_raw",  # audio a medida que se genera: empieza a sonar antes
        ]

        cmd_filtro, cmd_player = self._tuberia(player, rate, vol, cfg.get("tono", 0))

        def _ejecutar():
            with self._lock:
                self._hablando = True
                try:
                    p_piper = subprocess.Popen(
                        cmd_piper,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                    )
                    p_filtro = None
                    entrada = p_piper.stdout
                    if cmd_filtro:
                        p_filtro = subprocess.Popen(
                            cmd_filtro,
                            stdin=entrada,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL,
                        )
                        p_piper.stdout.close()
                        entrada = p_filtro.stdout
                    p_player = subprocess.Popen(
                        cmd_player,
                        stdin=entrada,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    entrada.close()
                    self._proc = p_player
                    self._proc_piper = p_piper
                    self._proc_filtro = p_filtro
                except Exception:
                    self._hablando = False
                    self._proc = None
                    self._proc_piper = None
                    self._proc_filtro = None
                    return

            try:
                p_piper.stdin.write(texto.encode("utf-8"))
                p_piper.stdin.close()
            except Exception:
                pass

            try:
                p_player.wait()
            except Exception:
                pass
            finally:
                with self._lock:
                    self._proc = None
                    self._proc_piper = None
                    self._proc_filtro = None
                    self._hablando = False
                if on_done:
                    _notificar_fin(on_done)

        t = threading.Thread(target=_ejecutar, daemon=True)
        t.start()

    def _reproducir_spdsay(self, texto: str, cfg: dict, duracion: float, on_done=None):
        vol = cfg.get("volumen", 100)
        if vol <= 0:
            return
        vol_spd = int((vol - 50) * 2)  # escala -100..100 de spd-say
        rate = cfg.get("velocidad", 0)
        pitch = cfg.get("tono", 0)
        idioma = cfg.get("idioma", "es")
        lang = "en" if str(idioma).lower().startswith("en") else "es"

        cmd = [
            self._spd_cmd,
            "-l", str(lang),
            "-r", str(rate),
            "-p", str(pitch),
            "-i", str(vol_spd),
            "-w",
            texto,
        ]

        def _ejecutar():
            with self._lock:
                self._hablando = True
                try:
                    self._proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except Exception:
                    self._hablando = False
                    self._proc = None
                    return
                proc = self._proc

            try:
                proc.wait()
            except Exception:
                pass
            finally:
                with self._lock:
                    if self._proc is proc:
                        self._proc = None
                    self._hablando = False
                if on_done:
                    _notificar_fin(on_done)

        t = threading.Thread(target=_ejecutar, daemon=True)
        t.start()

    def _reproducir_speechd(self, texto: str, cfg: dict, duracion: float, on_done=None):
        try:
            import speechd
            client = speechd.SSIPClient("appstudy")
            rate = cfg.get("velocidad", 0)
            pitch = cfg.get("tono", 0)
            idioma = cfg.get("idioma", "es")
            lang = "en" if str(idioma).lower().startswith("en") else "es"
            vol = cfg.get("volumen", 100)
            client.set_language(lang)
            client.set_rate(rate)
            client.set_pitch(pitch)
            client.set_volume(vol)
            client.speak(texto)

            def _esperar():
                with self._lock:
                    self._hablando = True
                time.sleep(duracion)
                with self._lock:
                    self._hablando = False
                try:
                    client.close()
                except Exception:
                    pass
                if on_done:
                    _notificar_fin(on_done)

            threading.Thread(target=_esperar, daemon=True).start()
        except Exception:
            pass


_reproductor = ReproductorVoz()


def hablar(texto: str, cfg: dict | None = None, on_done=None,
           card: dict | None = None, idioma: str | None = None) -> float:
    """Lee el texto en voz alta de forma asíncrona.

    Soporta selección automática de idioma (español o inglés) según la tarjeta o texto,
    evitando la lectura literal con fonética inapropiada.
    Devuelve la duración estimada en segundos para animar la boca de Bit.
    """
    if not texto:
        return 0.0
    cfg = dict(cfg) if cfg else {}
    if not cfg.get("activo", True):
        return 0.0
    limpio = limpiar_para_voz(texto)
    if not limpio:
        return 0.0

    if idioma:
        cfg["idioma"] = idioma
    elif not cfg.get("idioma") or cfg.get("idioma") == "es":
        if es_tarjeta_ingles(card=card, texto=limpio):
            cfg["idioma"] = "en"

    duracion = duracion_estimada(limpio, cfg.get("velocidad", 0))
    hablado = preparar_prosodia(limpio, cfg.get("idioma", "es"))
    _reproductor.reproducir(hablado, cfg, duracion, on_done)
    return duracion


def detener():
    """Detiene cualquier reproducción de voz en curso."""
    _reproductor.detener()


def esta_hablando() -> bool:
    """Indica si actualmente se está reproduciendo voz."""
    return _reproductor.esta_hablando()
