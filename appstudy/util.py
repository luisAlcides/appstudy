"""Utilidades de texto y color para la interfaz."""
import re
import threading

import gi

gi.require_version("Pango", "1.0")
from gi.repository import GLib, Pango  # noqa: E402

from . import mates, sintaxis  # noqa: E402

# Etiquetas permitidas en el contenido de una tarjeta. <code> es un alias cómodo
# de <tt>, la que entiende Pango.
_TAG = re.compile(r"</?(?:b|i|tt|code|s|u|big|small|sub|sup|span)(?:\s[^<>]*)?/?>",
                  re.IGNORECASE)
# Un & que ya forma parte de una entidad válida se respeta; el resto se escapa.
_AMP_SUELTO = re.compile(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)")


def _escapar(segmento: str) -> str:
    return (_AMP_SUELTO.sub("&amp;", segmento)
            .replace("<", "&lt;").replace(">", "&gt;"))


# Un <code> de varias líneas dentro de una tarjeta es un bloque de código de
# verdad: se colorea. El de una sola línea es una palabra suelta y se deja.
_CODIGO = re.compile(r"<(code|tt)>(.*?)</\1>", re.S | re.I)
_MARCA_CODIGO = "\ue002{}\ue003"
_MARCA_CODIGO_RE = re.compile("\ue002(\\d+)\ue003")


def _tema_oscuro() -> bool:
    try:
        gi.require_version("Adw", "1")
        from gi.repository import Adw
        return Adw.StyleManager.get_default().get_dark()
    except (ValueError, ImportError, AttributeError):
        return False


def _apartar_codigo(texto: str):
    """Saca los bloques de código, ya coloreados, y deja marcas en su sitio."""
    piezas: list[str] = []

    def guarda(m):
        cuerpo = m.group(2)
        if "\n" not in cuerpo:
            return m.group(0)          # código en línea: se queda como estaba
        crudo = cuerpo
        for entidad, caracter in _ENTIDADES:
            crudo = crudo.replace(entidad, caracter)
        piezas.append("<tt>" + sintaxis.resaltar(crudo, oscuro=_tema_oscuro()) + "</tt>")
        return _MARCA_CODIGO.format(len(piezas) - 1)

    return _CODIGO.sub(guarda, texto), piezas


def to_markup(text: str) -> str:
    """Convierte el texto de una tarjeta a markup válido de Pango.

    Solo se respetan las etiquetas conocidas; todo lo demás se escapa. Así un
    texto con <code>&</code>, <code>&lt;</code> o <code>&gt;</code> sueltos se
    muestra tal cual en vez de romper el markup y aparecer con las etiquetas
    visibles.

    Las fórmulas en LaTeX ($E=mc^2$) y los bloques de código se apartan antes de
    escapar y se devuelven ya dibujados al final.
    """
    if not text:
        return ""
    text, codigos = _apartar_codigo(text)
    text, formulas = mates.extraer(text)
    partes, pos = [], 0
    for m in _TAG.finditer(text):
        partes.append(_escapar(text[pos:m.start()]))
        etiqueta = m.group(0)
        partes.append(etiqueta.replace("code", "tt").replace("CODE", "tt"))
        pos = m.end()
    partes.append(_escapar(text[pos:]))
    resultado = mates.restaurar("".join(partes), formulas)
    if codigos:
        resultado = _MARCA_CODIGO_RE.sub(lambda m: codigos[int(m.group(1))], resultado)
    try:
        Pango.parse_markup(resultado, -1, "\x00")
        return resultado
    except GLib.GError:
        # Si algo salió mal, texto plano: mejor sin adornos que sin texto
        return GLib.markup_escape_text(plain(text))


_ENTIDADES = (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'"), ("&amp;", "&"))


def plain(text: str) -> str:
    """Texto sin etiquetas ni entidades, para búsquedas y listados."""
    t = re.sub(r"<[^>]+>", "", text or "").replace("\n", " ").strip()
    for entidad, caracter in _ENTIDADES:
        t = t.replace(entidad, caracter)
    return t


def lines(text: str) -> list[str]:
    """Como plain(), pero respetando los saltos: una lista de líneas con texto.

    Muchas respuestas son una lista («cat — todo de golpe / less — paginado»);
    juntarlas en un párrafo las vuelve ilegibles.
    """
    t = re.sub(r"<[^>]+>", "", text or "")
    for entidad, caracter in _ENTIDADES:
        t = t.replace(entidad, caracter)
    return [linea.strip() for linea in t.splitlines() if linea.strip()]


def as_label(text: str) -> str:
    """Texto plano listo para un widget que interpreta markup (títulos de fila)."""
    return GLib.markup_escape_text(plain(text))


def shade(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def hilo(trabajo, al_terminar, al_fallar=None):
    """Corre `trabajo()` aparte y devuelve el resultado en el hilo de GTK.

    Dibujar una página de PDF o esperar a un modelo tarda cientos de
    milisegundos o segundos: hacerlo en el hilo de la interfaz congelaría la
    ventana. GTK solo se puede tocar desde su propio hilo, de ahí el idle_add.
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
