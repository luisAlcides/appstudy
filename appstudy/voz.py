"""Síntesis de voz (TTS) para AppStudy y Bit.

Permite leer tarjetas, citas y respuestas de IA en voz alta bajo demanda o de
forma automática, sincronizando el movimiento de la boca de Bit con la locución.

Utiliza el motor neuronal de alta calidad Piper si está instalado localmente,
lo que produce una voz humana, cálida y natural (no robótica). Si no está,
recurre a `spd-say` (speech-dispatcher) o la biblioteca `speechd` del sistema.
"""
import os
import re
import shutil
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
    if idioma and str(idioma).lower().startswith("en"):
        return PIPER_MODEL_EN.is_file()
    return PIPER_MODEL_ES.is_file() or PIPER_MODEL.is_file()


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
    # Espacios duplicados y saltos de línea
    t = re.sub(r"\s+", " ", t).strip()
    # Limpiar espacios previos a signos de puntuación
    t = re.sub(r"\s+([,.:;!?])", r"\1", t)
    return t


def duracion_estimada(texto: str, velocidad: int = 0) -> float:
    """Estima la duración en segundos para sincronizar la animación de la boca."""
    limpio = limpiar_para_voz(texto)
    palabras = len(limpio.split())
    if palabras == 0:
        return 0.0
    factor = max(0.5, min(2.0, 1.0 + (velocidad / 100.0)))
    segundos = (palabras / 2.5) / factor + 0.5
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
        "neuronal": tiene_motor_neuronal(),
    }


def guardar(con, activo=None, auto=None, volumen=None, velocidad=None, tono=None, idioma=None):
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
        self._hablando = False
        self._spd_cmd = shutil.which("spd-say")

    def esta_hablando(self) -> bool:
        with self._lock:
            if self._proc is not None:
                if self._proc.poll() is None:
                    return True
                self._proc = None
            return self._hablando

    def detener(self):
        with self._lock:
            self._hablando = False
            if self._proc_piper is not None:
                try:
                    self._proc_piper.terminate()
                except OSError:
                    pass
                self._proc_piper = None
            if self._proc is not None:
                try:
                    self._proc.terminate()
                except OSError:
                    pass
                self._proc = None
            if self._spd_cmd:
                try:
                    subprocess.Popen(
                        [self._spd_cmd, "-S"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except Exception:
                    pass

    def reproducir(self, texto: str, cfg: dict, duracion: float, on_done=None):
        self.detener()
        idioma = cfg.get("idioma", "es")
        if tiene_motor_neuronal(idioma):
            self._reproducir_piper(texto, cfg, duracion, on_done)
        elif self._spd_cmd:
            self._reproducir_spdsay(texto, cfg, duracion, on_done)
        else:
            self._reproducir_speechd(texto, cfg, duracion, on_done)

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
        length_scale = round(1.0 / factor, 3)

        idioma = cfg.get("idioma", "es")
        if idioma and str(idioma).lower().startswith("en") and PIPER_MODEL_EN.is_file():
            modelo = PIPER_MODEL_EN
        elif PIPER_MODEL_ES.is_file():
            modelo = PIPER_MODEL_ES
        else:
            modelo = PIPER_MODEL

        cmd_piper = [
            str(PIPER_BIN),
            "--model", str(modelo),
            "--length_scale", str(length_scale),
            "--output-raw",
        ]

        if player == "paplay":
            vol_pa = str(int(max(0, min(100, vol)) * 655.36))
            cmd_player = ["paplay", "--raw", "--rate", "22050", "--channels", "1", "--volume", vol_pa]
        elif player == "pw-play":
            vol_pw = str(round(max(0.0, min(1.0, vol / 100.0)), 2))
            cmd_player = ["pw-play", "--rate", "22050", "--channels", "1", "--volume", vol_pw, "-"]
        else:
            cmd_player = ["aplay", "-q", "-r", "22050", "-f", "S16_LE", "-t", "raw"]

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
                    p_player = subprocess.Popen(
                        cmd_player,
                        stdin=p_piper.stdout,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    p_piper.stdout.close()
                    self._proc = p_player
                    self._proc_piper = p_piper
                except Exception:
                    self._hablando = False
                    self._proc = None
                    self._proc_piper = None
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
    _reproductor.reproducir(limpio, cfg, duracion, on_done)
    return duracion


def detener():
    """Detiene cualquier reproducción de voz en curso."""
    _reproductor.detener()


def esta_hablando() -> bool:
    """Indica si actualmente se está reproduciendo voz."""
    return _reproductor.esta_hablando()
