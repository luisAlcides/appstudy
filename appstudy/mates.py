"""Fórmulas escritas en LaTeX, dibujadas con el propio texto.

No hace falta un motor de LaTeX ni generar imágenes: las fórmulas que salen al
estudiar caben en Unicode más los <sup>/<sub> de Pango, y así se pueden
seleccionar, copiar y ampliar como cualquier otro texto (y se ven igual en la
mascota, en el popup y en la lectura).

Se reconoce $en línea$ y $$en bloque$$. Para no estropear un texto que solo
lleva un precio o una variable del shell, una fórmula en línea solo se
interpreta si trae algo inequívocamente de LaTeX: una orden con barra, un
exponente o un subíndice.
"""
import re

# Letras y símbolos: lo que de verdad aparece estudiando
SIMBOLOS = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ",
    "sigma": "σ", "tau": "τ", "phi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π",
    "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
    "times": "×", "cdot": "·", "div": "÷", "pm": "±", "mp": "∓",
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠", "ne": "≠",
    "approx": "≈", "equiv": "≡", "propto": "∝", "sim": "∼",
    "infty": "∞", "partial": "∂", "nabla": "∇", "degree": "°", "deg": "°",
    "sum": "∑", "prod": "∏", "int": "∫", "iint": "∬", "oint": "∮",
    "rightarrow": "→", "to": "→", "leftarrow": "←", "gets": "←",
    "Rightarrow": "⇒", "Leftarrow": "⇐", "leftrightarrow": "↔", "mapsto": "↦",
    "in": "∈", "notin": "∉", "subset": "⊂", "subseteq": "⊆", "cup": "∪",
    "cap": "∩", "emptyset": "∅", "forall": "∀", "exists": "∃", "neg": "¬",
    "land": "∧", "lor": "∨", "therefore": "∴", "because": "∵",
    "ldots": "…", "dots": "…", "cdots": "⋯", "prime": "′", "ell": "ℓ",
    "hbar": "ℏ", "Re": "ℜ", "Im": "ℑ", "aleph": "ℵ", "percent": "%",
    "mid": "|", "vert": "|", "Vert": "‖", "lvert": "|", "rvert": "|",
    "lVert": "‖", "rVert": "‖", "langle": "⟨", "rangle": "⟩",
    "lceil": "⌈", "rceil": "⌉", "lfloor": "⌊", "rfloor": "⌋",
    "parallel": "∥", "perp": "⊥", "angle": "∠",
    # Variantes de letras griegas que se usan tanto como las normales
    "varphi": "φ", "varepsilon": "ε", "vartheta": "ϑ", "varrho": "ϱ",
    "varsigma": "ς", "varpi": "ϖ", "phi_alt": "ϕ",
    "cong": "≅", "circ": "∘", "bullet": "•", "ast": "∗", "star": "⋆",
    "quad": "  ", "qquad": "    ", "space": " ",
}

# Órdenes que solo son espaciado o adorno y se quitan
BORRAR = ("left", "right", "displaystyle", "textstyle", "limits", "nolimits", "!")

# Nombres de función: en LaTeX van en redonda, y aquí basta con quitar la barra
# (que es lo que el traductor hace por defecto con lo que no reconoce).
FUNCIONES = ("cos", "sin", "tan", "sec", "csc", "cot", "log", "ln", "exp",
             "max", "min", "lim", "det", "arg", "gcd", "sup", "inf")

ACENTOS = {"bar": "\u0304", "hat": "\u0302", "vec": "\u20d7", "dot": "\u0307",
           "tilde": "\u0303", "overline": "\u0304"}

_LLAVE = r"\{([^{}]*)\}"
_FRAC = re.compile(r"\\d?frac\s*" + _LLAVE + r"\s*" + _LLAVE)
_SQRT = re.compile(r"\\sqrt\s*" + _LLAVE)
_ACENTO = re.compile(r"\\(" + "|".join(ACENTOS) + r")\s*" + _LLAVE)
_TEXTO = re.compile(r"\\(?:text|mathrm|mathbf|mathit|operatorname|mbox)\s*" + _LLAVE)
_ORDEN = re.compile(r"\\([a-zA-Z]+)")
_SUP = re.compile(r"\^\{([^{}]*)\}|\^(\S)")
_SUB = re.compile(r"_\{([^{}]*)\}|_(\S)")

# $$bloque$$ y $línea$; la señal es lo que distingue una fórmula de un precio
BLOQUE = re.compile(r"\$\$(.+?)\$\$", re.S)
LINEA = re.compile(r"\$([^$\n]+?)\$")
SENAL = re.compile(r"\\[a-zA-Z]+|[\^_]")

# Marcas privadas de Unicode: sobreviven al escapado sin que nadie las escriba
MARCA = "\ue000{}\ue001"
_MARCA = re.compile("\ue000(\\d+)\ue001")


# Un trozo sin operadores sueltos (una variable, un número, P(B)…) no necesita
# paréntesis al bajarlo a una sola línea; «VP + FP» sí.
_SUELTO = re.compile(r"^[^-+/×·^\s]+$")


def _agrupa(parte: str) -> str:
    """Pone paréntesis si la parte de una fracción o raíz tiene más de un trozo."""
    p = parte.strip()
    if len(p) <= 1 or _SUELTO.match(p):
        return p
    if p.startswith("(") and p.endswith(")"):
        return p
    return f"({p})"


def a_markup(latex: str) -> str:
    """Convierte una fórmula de LaTeX (sin los $) en markup de Pango."""
    t = latex.strip()
    # 14{,}7 → 14,7. Esas llaves sueltas son solo para el espaciado de LaTeX y,
    # si se quedan, rompen la lectura de \frac (que no admite anidamiento).
    t = re.sub(r"\{([,.;:])\}", r"\1", t)
    for _ in range(4):        # de dentro hacia fuera, por si van anidadas
        t, n = _FRAC.subn(lambda m: f"{_agrupa(m.group(1))}/{_agrupa(m.group(2))}", t)
        t, m2 = _SQRT.subn(lambda m: f"√{_agrupa(m.group(1))}", t)
        t, m3 = _ACENTO.subn(lambda m: m.group(2) + ACENTOS[m.group(1)], t)
        t, m4 = _TEXTO.subn(lambda m: m.group(1), t)
        if not (n or m2 or m3 or m4):
            break
    t = t.replace("\\\\", "\n").replace("&", " ")     # saltos y alineación
    t = re.sub(r"\\[,;: ]", " ", t)
    t = _ORDEN.sub(_orden, t)
    # A partir de aquí ya es texto: se escapa antes de meter etiquetas propias
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = _SUP.sub(lambda m: f"<sup>{m.group(1) or m.group(2)}</sup>", t)
    t = _SUB.sub(lambda m: f"<sub>{m.group(1) or m.group(2)}</sub>", t)
    t = t.replace("{", "").replace("}", "")
    return f'<span font_family="serif">{t}</span>'


def _orden(m) -> str:
    """Traduce una orden con barra: símbolo, función, o el nombre a secas."""
    nombre = m.group(1)
    if nombre in SIMBOLOS:
        return SIMBOLOS[nombre]
    if nombre in BORRAR:
        return ""
    if nombre in FUNCIONES:
        # «cos φ» lleva un pelo de espacio; «cos(θ)» no
        siguiente = m.string[m.end():m.end() + 1]
        return nombre + ("\u2009" if siguiente.isalpha() or siguiente == "\\" else "")
    return nombre


def extraer(texto: str):
    """Saca las fórmulas del texto y deja marcas en su sitio.

    Devuelve (texto_con_marcas, formulas). Así el resto del texto se puede
    escapar sin tocar el markup de la fórmula.
    """
    formulas: list[str] = []

    def guarda(markup: str) -> str:
        formulas.append(markup)
        return MARCA.format(len(formulas) - 1)

    def bloque(m):
        return guarda(a_markup(m.group(1)))

    def linea(m):
        if not SENAL.search(m.group(1)):
            return m.group(0)          # ni fórmula ni intención: se deja tal cual
        return guarda(a_markup(m.group(1)))

    return LINEA.sub(linea, BLOQUE.sub(bloque, texto)), formulas


def restaurar(texto: str, formulas: list) -> str:
    if not formulas:
        return texto
    return _MARCA.sub(lambda m: formulas[int(m.group(1))], texto)


def hay_formula(texto: str) -> bool:
    return bool(texto) and ("$" in texto and (BLOQUE.search(texto) or LINEA.search(texto)))
