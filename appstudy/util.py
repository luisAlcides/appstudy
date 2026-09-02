"""Utilidades de texto y color para la interfaz."""
import re
import threading
from concurrent.futures import ThreadPoolExecutor

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


# Dos colas pequeñas en vez de un hilo por trabajo. Al desplegar un estante se
# piden doscientas portadas de golpe: con un hilo cada una el sistema se atasca,
# con dos obreros salen en fila y la ventana no se entera.
#   - «ui»    lo que estás mirando ahora: la página del PDF que acabas de pedir.
#   - «fondo» lo que puede esperar: portadas y páginas que aún no has pasado.
# Lo muy largo (una respuesta del modelo, que tarda segundos) va en su propio
# hilo para no ocupar un obrero durante medio minuto.
_UI = ThreadPoolExecutor(max_workers=2, thread_name_prefix="as-ui")
_FONDO = ThreadPoolExecutor(max_workers=2, thread_name_prefix="as-fondo")


def hilo(trabajo, al_terminar=None, al_fallar=None, fondo=False, largo=False):
    """Corre `trabajo()` fuera del hilo de la interfaz y devuelve el resultado en él.

    GTK solo se puede tocar desde su hilo, de ahí el `idle_add` del final.
    """
    from gi.repository import GLib

    def dentro():
        try:
            resultado = trabajo()
        except Exception as e:                        # se enseña, no se traga
            if al_fallar:
                GLib.idle_add(al_fallar, e)
            return
        if al_terminar:
            GLib.idle_add(al_terminar, resultado)

    if largo:
        h = threading.Thread(target=dentro, daemon=True)
        h.start()
        return h
    return (_FONDO if fondo else _UI).submit(dentro)


def tooltip_perezoso(widget, texto):
    """Pone el tooltip la primera vez que le pasas el ratón por encima.

    Asignar un tooltip cuesta ~11 ms: GTK monta al vuelo la maquinaria que lo
    enseña. En una lista de cientos de filas con dos botones cada una eso son
    segundos de ventana congelada, y la inmensa mayoría de esos botones no
    llegan a ver el ratón nunca. Así que se les pone cuando toca.
    """
    from gi.repository import Gtk

    def entrar(controlador, *_):
        widget.set_tooltip_text(texto)
        widget.remove_controller(controlador)

    controlador = Gtk.EventControllerMotion()
    controlador.connect("enter", lambda *_: entrar(controlador))
    widget.add_controller(controlador)
