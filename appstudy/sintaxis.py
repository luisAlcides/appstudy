"""Resaltado de código, traducido a markup de Pango.

Usa Pygments (`python3-pygments`), que ya viene en casi cualquier escritorio.
Si no está instalado, el código se enseña tal cual: nada se rompe, solo pierde
color.

Los bloques de las lecturas no siempre son código: muchos son tablas y dibujos
hechos con caracteres. Por eso el lenguaje solo se da por bueno cuando hay
señales claras; en la duda, no se colorea, que es mejor que colorear al azar.
"""
import re

try:
    from pygments import lex
    from pygments.lexers import get_lexer_by_name
    from pygments.token import Token
    from pygments.util import ClassNotFound
    HAY_PYGMENTS = True
except ImportError:                                   # pragma: sin pygments
    HAY_PYGMENTS = False

# Paletas propias, en el mismo tono cálido que el resto de AppStudy
CLARA = {
    "comentario": "#7a7266", "cadena": "#0a7d3c", "numero": "#1c6fb8",
    "clave": "#8250df", "funcion": "#9a5700", "interna": "#0550ae",
    "operador": "#b3593b", "error": "#cf222e",
}
OSCURA = {
    "comentario": "#9a9288", "cadena": "#7fc98a", "numero": "#8ec5ff",
    "clave": "#d2a8ff", "funcion": "#ffb37a", "interna": "#8ec5ff",
    "operador": "#ff9f8f", "error": "#ff8a80",
}

# Del tipo de token de Pygments al color; gana la primera que encaje
if HAY_PYGMENTS:
    FAMILIAS = (
        (Token.Comment, "comentario"),
        (Token.String, "cadena"),
        (Token.Number, "numero"),
        (Token.Keyword, "clave"),
        (Token.Name.Function, "funcion"),
        (Token.Name.Class, "funcion"),
        (Token.Name.Builtin, "interna"),
        (Token.Name.Tag, "clave"),
        (Token.Name.Attribute, "funcion"),
        (Token.Generic.Prompt, "comentario"),
        (Token.Operator.Word, "clave"),
        (Token.Operator, "operador"),
        (Token.Error, "error"),
    )
else:                                                 # pragma: sin pygments
    FAMILIAS = ()

# Señales de cada lenguaje. Se pide algo inequívoco, no un parecido.
_DIBUJO = re.compile(r"[←→↑↓┌┐└┘│─├┤╔╗╚╝║═▲▼]")
_SQL = re.compile(r"^\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|WITH)\b", re.M)
_PYTHON = re.compile(r"^\s*(import |from \s*\w+ import|def |class |@\w+|print\(|"
                     r"df\.|pd\.|np\.|plt\.)", re.M)
_SHELL = re.compile(
    r"^\s*[$#>]\s|"
    r"^\s*(sudo|apt|apt-get|ls|cd|cat|grep|awk|sed|find|chmod|chown|curl|wget|git|"
    r"tar|ps|kill|echo|mkdir|cp|mv|rm|df|du|top|htop|man|which|ssh|scp|rsync|"
    r"systemctl|journalctl|uname|head|tail|sort|uniq|wc|less|nano|vim|export|"
    r"pip|pip3|python3|docker|make)\b", re.M)
_JSON = re.compile(r'^\s*[\[{]\s*$|^\s*"[^"]+"\s*:', re.M)
_INI = re.compile(r"^\s*\[[A-Za-z][\w .-]*\]\s*$", re.M)   # unidades systemd, .desktop, .ini


def adivinar(codigo: str) -> str | None:
    """El lenguaje del bloque, o None si no está claro que sea código."""
    t = codigo.strip()
    if not t or _DIBUJO.search(t):
        return None                    # es un dibujo o una tabla, no código
    if _SQL.search(t):
        return "sql"
    if _PYTHON.search(t):
        return "python"
    if _SHELL.search(t):
        return "bash"
    if _JSON.search(t):
        return "json"
    if _INI.search(t):
        return "ini"
    return None


def _escapar(texto: str) -> str:
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _color(tipo, paleta):
    for familia, clave in FAMILIAS:
        if tipo in familia:
            return paleta[clave]
    return None


def resaltar(codigo: str, lang: str | None = None, oscuro: bool = False) -> str:
    """Devuelve el código como markup de Pango, con color si se sabe de qué es."""
    lenguaje = lang or adivinar(codigo)
    if not HAY_PYGMENTS or not lenguaje:
        return _escapar(codigo)
    try:
        lexer = get_lexer_by_name(lenguaje)
    except ClassNotFound:
        return _escapar(codigo)

    paleta = OSCURA if oscuro else CLARA
    partes = []
    for tipo, texto in lex(codigo, lexer):
        if not texto:
            continue
        color = _color(tipo, paleta)
        trozo = _escapar(texto)
        if color and trozo.strip():
            cursiva = tipo in Token.Comment
            trozo = (f'<span foreground="{color}">'
                     f'{"<i>" + trozo + "</i>" if cursiva else trozo}</span>')
        partes.append(trozo)
    return "".join(partes).rstrip("\n")
