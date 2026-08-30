"""Utilidades de texto y color para la interfaz."""
import re

import gi

gi.require_version("Pango", "1.0")
from gi.repository import GLib, Pango  # noqa: E402

# Etiquetas permitidas en el contenido de una tarjeta. <code> es un alias cómodo
# de <tt>, la que entiende Pango.
_TAG = re.compile(r"</?(?:b|i|tt|code|s|u|big|small|sub|sup|span)(?:\s[^<>]*)?/?>",
                  re.IGNORECASE)
# Un & que ya forma parte de una entidad válida se respeta; el resto se escapa.
_AMP_SUELTO = re.compile(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)")


def _escapar(segmento: str) -> str:
    return (_AMP_SUELTO.sub("&amp;", segmento)
            .replace("<", "&lt;").replace(">", "&gt;"))


def to_markup(text: str) -> str:
    """Convierte el texto de una tarjeta a markup válido de Pango.

    Solo se respetan las etiquetas conocidas; todo lo demás se escapa. Así un
    texto con <code>&</code>, <code>&lt;</code> o <code>&gt;</code> sueltos se
    muestra tal cual en vez de romper el markup y aparecer con las etiquetas
    visibles.
    """
    if not text:
        return ""
    partes, pos = [], 0
    for m in _TAG.finditer(text):
        partes.append(_escapar(text[pos:m.start()]))
        etiqueta = m.group(0)
        partes.append(etiqueta.replace("code", "tt").replace("CODE", "tt"))
        pos = m.end()
    partes.append(_escapar(text[pos:]))
    resultado = "".join(partes)
    try:
        Pango.parse_markup(resultado, -1, "\x00")
        return resultado
    except GLib.GError:
        return GLib.markup_escape_text(text)


_ENTIDADES = (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'"), ("&amp;", "&"))


def plain(text: str) -> str:
    """Texto sin etiquetas ni entidades, para búsquedas y listados."""
    t = re.sub(r"<[^>]+>", "", text or "").replace("\n", " ").strip()
    for entidad, caracter in _ENTIDADES:
        t = t.replace(entidad, caracter)
    return t


def as_label(text: str) -> str:
    """Texto plano listo para un widget que interpreta markup (títulos de fila)."""
    return GLib.markup_escape_text(plain(text))


def shade(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"
