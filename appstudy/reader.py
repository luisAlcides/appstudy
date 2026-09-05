"""Modo lectura: capítulos que se leen de corrido, como un documento."""
import json
import re
import unicodedata

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from . import db, mates, sintaxis, util  # noqa: E402


def render_body(body: list[dict], buscar: str | None = None):
    """Convierte los bloques de un capítulo en widgets con jerarquía tipográfica.

    Si se pasa `buscar` (el texto de una tarjeta), se marca el bloque que mejor
    encaja y se devuelve para poder desplazarse hasta él.
    """
    col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    bloques = []
    for bloque in body:
        for tipo, contenido in bloque.items():
            w = _bloque(tipo, contenido)
            if w is not None:
                col.append(w)
                bloques.append((w, _texto(contenido)))
    diana = _mejor_bloque(bloques, buscar) if buscar else None
    if diana is not None:
        diana.add_css_class("as-read-hit")
    return col, diana


_PALABRA = re.compile(r"[a-z0-9ñ]{4,}")


def _str(contenido) -> str:
    """El texto de un bloque, venga suelto o dentro de un objeto con lenguaje."""
    if isinstance(contenido, dict):
        return (contenido.get("text") or contenido.get("code")
                or contenido.get("latex") or contenido.get("caption") or "")
    return str(contenido)


def _texto(contenido) -> str:
    if isinstance(contenido, list):
        return " ".join(util.plain(_str(x)) for x in contenido)
    return util.plain(_str(contenido))


def _clave(texto: str) -> set:
    """Palabras con significado, sin acentos: para comparar sin afinar de más."""
    t = unicodedata.normalize("NFD", (texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return set(_PALABRA.findall(t))


def _mejor_bloque(bloques, buscar):
    """El bloque que más palabras comparte con la tarjeta, si comparte bastantes."""
    quiero = _clave(buscar)
    if not quiero:
        return None
    mejor, puntos = None, 0.0
    for widget, texto in bloques:
        tengo = _clave(texto)
        if not tengo:
            continue
        # Cuenta lo que cubre de la tarjeta, con un empujón a los bloques cortos
        # para que gane el párrafo concreto y no el capítulo entero.
        comunes = len(quiero & tengo)
        p = comunes / len(quiero) + 0.15 * comunes / (len(tengo) ** 0.5)
        if p > puntos:
            mejor, puntos = widget, p
    return mejor if puntos >= 0.35 else None


def _label(texto, css, xalign=0.0, top=0, bottom=0):
    lab = Gtk.Label(label=util.to_markup(texto), use_markup=True, wrap=True,
                    xalign=xalign, css_classes=css, selectable=True)
    lab.set_wrap_mode(2)  # PANGO_WRAP_WORD_CHAR
    lab.set_margin_top(top)
    lab.set_margin_bottom(bottom)
    return lab


def _codigo(contenido):
    """Un bloque de código: resaltado si se sabe de qué lenguaje es."""
    texto = _str(contenido)
    lang = contenido.get("lang") if isinstance(contenido, dict) else None
    lang = lang or sintaxis.adivinar(texto)
    oscuro = Adw.StyleManager.get_default().get_dark()

    vista = Gtk.Label(label=sintaxis.resaltar(texto, lang, oscuro), use_markup=True,
                      xalign=0, selectable=True, css_classes=["as-read-code"])
    scroll = Gtk.ScrolledWindow(vscrollbar_policy=Gtk.PolicyType.NEVER,
                                propagate_natural_height=True)
    scroll.set_child(vista)

    caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                   css_classes=["as-read-codebox"])
    if lang:
        # El nombre del lenguaje, arriba a la derecha, como en un cuaderno
        etiqueta = Gtk.Label(label=lang, halign=Gtk.Align.END,
                             css_classes=["as-code-lang"])
        caja.append(etiqueta)
    caja.append(scroll)
    caja.set_margin_top(8)
    caja.set_margin_bottom(12)
    return caja


def _bloque(tipo, contenido):
    if tipo == "h":
        return _label(contenido, ["as-read-h2"], top=26, bottom=6)
    if tipo == "p":
        return _label(contenido, ["as-read-p"], top=6, bottom=6)
    if tipo == "list":
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        caja.set_margin_top(6)
        caja.set_margin_bottom(8)
        for item in contenido:
            fila = Gtk.Box(spacing=10)
            punto = Gtk.Label(label="•", css_classes=["as-read-bullet"],
                              valign=Gtk.Align.START)
            fila.append(punto)
            fila.append(_label(item, ["as-read-p"]))
            caja.append(fila)
        return caja
    if tipo == "steps":
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        caja.set_margin_top(6)
        caja.set_margin_bottom(8)
        for i, item in enumerate(contenido, start=1):
            fila = Gtk.Box(spacing=12)
            num = Gtk.Label(label=str(i), css_classes=["as-read-step"],
                            valign=Gtk.Align.START)
            fila.append(num)
            fila.append(_label(item, ["as-read-p"]))
            caja.append(fila)
        return caja
    if tipo == "code":
        return _codigo(contenido)
    if tipo == "math":
        # Una fórmula suelta, centrada y en grande
        lab = Gtk.Label(label=mates.a_markup(_str(contenido)), use_markup=True,
                        selectable=True, wrap=True, justify=Gtk.Justification.CENTER,
                        css_classes=["as-math"])
        lab.set_margin_top(14)
        lab.set_margin_bottom(16)
        return lab
    if tipo in ("note", "warn", "key"):
        icono = {"note": "💡", "warn": "⚠️", "key": "🔑"}[tipo]
        caja = Gtk.Box(spacing=12, css_classes=["as-callout", f"as-callout-{tipo}"])
        caja.set_margin_top(10)
        caja.set_margin_bottom(12)
        marca = Gtk.Label(label=icono, valign=Gtk.Align.START,
                          css_classes=["as-callout-icon"])
        marca.set_margin_start(14)
        marca.set_margin_top(14)
        caja.append(marca)
        texto = _label(contenido, ["as-read-p"], top=14, bottom=14)
        texto.set_margin_end(16)
        texto.set_hexpand(True)
        caja.append(texto)
        return caja
    if tipo == "quote":
        caja = Gtk.Box(css_classes=["as-quote"])
        caja.set_margin_top(10)
        caja.set_margin_bottom(12)
        texto = _label(contenido, ["as-read-quote"], top=10, bottom=10)
        texto.set_margin_start(16)
        texto.set_margin_end(16)
        caja.append(texto)
        return caja
    if tipo in ("img", "image"):
        return _imagen(contenido)
    return None


def _imagen(contenido):
    """Carga y muestra una imagen desde una URL externa de forma asíncrona.

    Descarga en segundo plano sin congelar la interfaz y guarda una copia
    en la caché local del usuario para no saturar la red ni la memoria.
    """
    import hashlib
    import urllib.request
    from pathlib import Path

    if isinstance(contenido, dict):
        url = contenido.get("url", "")
        caption = contenido.get("caption", "")
    else:
        url = str(contenido)
        caption = ""

    caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                   css_classes=["as-read-imgbox"])
    caja.set_margin_top(16)
    caja.set_margin_bottom(18)
    caja.set_halign(Gtk.Align.CENTER)
    caja.set_hexpand(True)

    pic = Gtk.Picture()
    pic.set_can_shrink(True)
    if hasattr(Gtk, "ContentFit"):
        pic.set_content_fit(Gtk.ContentFit.CONTAIN)
    pic.set_size_request(-1, 320)
    pic.set_visible(False)
    caja.append(pic)

    spinner = Gtk.Spinner()
    spinner.set_size_request(32, 32)
    spinner.set_halign(Gtk.Align.CENTER)
    spinner.set_margin_top(40)
    spinner.set_margin_bottom(40)
    caja.append(spinner)

    if caption:
        pie = Gtk.Label(label=util.to_markup(caption), use_markup=True, wrap=True,
                        xalign=0.5, justify=Gtk.Justification.CENTER,
                        css_classes=["as-dim", "caption"])
        pie.set_margin_top(6)
        caja.append(pie)

    cache_dir = Path(GLib.get_user_cache_dir()) / "appstudy" / "images"

    # Si ya está en la caché local, se monta al instante sin tocar la red
    if url and url.startswith("http"):
        h = hashlib.sha256(url.encode("utf-8")).hexdigest()
        archivo = cache_dir / f"{h}.bin"
        if archivo.exists():
            try:
                data = archivo.read_bytes()
                tex = Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))
                pic.set_paintable(tex)
                pic.set_visible(True)
                spinner.set_visible(False)
                return caja
            except Exception:
                pass

    spinner.start()

    def cargar():
        if not url or not url.startswith("http"):
            return None
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            h = hashlib.sha256(url.encode("utf-8")).hexdigest()
            archivo = cache_dir / f"{h}.bin"
            if archivo.exists():
                try:
                    return archivo.read_bytes()
                except Exception:
                    pass
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppStudy/1.0"}
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = resp.read()
                try:
                    archivo.write_bytes(data)
                except Exception:
                    pass
                return data
        except Exception:
            return None

    def al_terminar(datos):
        spinner.stop()
        spinner.set_visible(False)
        if not datos:
            aviso = Gtk.Label(label="⚠️ (Imagen disponible al conectarse a internet)",
                              css_classes=["as-dim", "caption"])
            caja.insert_child_after(aviso, pic)
            return
        try:
            tex = Gdk.Texture.new_from_bytes(GLib.Bytes.new(datos))
            pic.set_paintable(tex)
            pic.set_visible(True)
        except Exception:
            aviso = Gtk.Label(label="⚠️ (No se pudo procesar la imagen)",
                              css_classes=["as-dim", "caption"])
            caja.insert_child_after(aviso, pic)

    def al_fallar(_err):
        spinner.stop()
        spinner.set_visible(False)
        aviso = Gtk.Label(label="⚠️ (Imagen disponible al conectarse a internet)",
                          css_classes=["as-dim", "caption"])
        caja.insert_child_after(aviso, pic)

    util.hilo(cargar, al_terminar, al_fallar, fondo=True)
    return caja


class ChapterView(Gtk.Box):
    """Un capítulo abierto: portada, cuerpo y pie con la navegación."""

    def __init__(self, app, con, chapter, hermanos, buscar=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.app = app
        self.con = con
        self.ch = chapter
        self.hermanos = hermanos           # todos los capítulos del mismo mazo
        self.buscar = buscar               # texto de la tarjeta que trae aquí
        self.diana = None                  # el bloque que lo explica
        self.on_navigate = None            # lo fija la ventana principal
        self.on_back = None
        self.on_cards = None               # generar tarjetas desde este capítulo

        self.scroll = Gtk.ScrolledWindow(vexpand=True,
                                         hscrollbar_policy=Gtk.PolicyType.NEVER)
        clamp = Adw.Clamp(maximum_size=740, tightening_threshold=680)
        self.columna = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.columna.set_margin_start(24)
        self.columna.set_margin_end(24)
        self.columna.set_margin_top(8)
        self.columna.set_margin_bottom(40)
        clamp.set_child(self.columna)
        self.scroll.set_child(clamp)
        self.append(self.scroll)

        self.build()

        # Al llegar al final del scroll, el capítulo se da por leído
        self.scroll.get_vadjustment().connect("value-changed", self.on_scroll)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.on_key)
        self.add_controller(keys)

        if self.diana is not None:
            # Hay que esperar a que el capítulo tenga tamaño para saber a qué
            # altura quedó el bloque; se reintenta hasta que lo tenga.
            self.intentos = 0
            GLib.timeout_add(120, self.ir_a_la_diana)

    # ------------------------------------------------------------------ armado

    def build(self):
        ch = self.ch
        cab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        cab.set_margin_top(24)
        cab.set_margin_bottom(8)

        meta = Gtk.Box(spacing=8)
        meta.append(self.chip(f"{ch['deck_icon']} {ch['deck_name']}", ch["deck_color"]))
        meta.append(self.chip(db.level_name(ch["deck_levels"], ch["level"]).upper(),
                              ch["deck_color"], soft=True))
        meta.append(Gtk.Label(label=f"· {ch['minutes']} min de lectura",
                              css_classes=["as-dim", "caption"]))
        btn_ciegas = Gtk.Button(label="⚡ Test a ciegas",
                                tooltip_text="Comprueba si ya dominas este tema antes de leerlo",
                                css_classes=["flat", "pill", "caption"])
        btn_ciegas.connect("clicked", lambda *_: getattr(self, "on_ciegas", lambda: None)())
        meta.append(btn_ciegas)
        cab.append(meta)

        cab.append(Gtk.Label(label=util.to_markup(ch["title"]), use_markup=True, wrap=True,
                             xalign=0, css_classes=["as-read-h1"], selectable=True))
        if ch["subtitle"]:
            cab.append(Gtk.Label(label=util.to_markup(ch["subtitle"]), use_markup=True,
                                 wrap=True, xalign=0, css_classes=["as-read-sub"]))
        sep = Gtk.Separator()
        sep.set_margin_top(18)
        cab.append(sep)
        self.columna.append(cab)

        cuerpo, self.diana = render_body(json.loads(ch["body"] or "[]"), self.buscar)
        self.columna.append(cuerpo)
        self.columna.append(self.pie())

    def ir_a_la_diana(self):
        """Desplaza la lectura hasta el bloque que explica la tarjeta."""
        self.intentos += 1
        ajuste = self.scroll.get_vadjustment()
        ok, caja = self.diana.compute_bounds(self.columna)
        if not ok or ajuste.get_upper() <= ajuste.get_page_size():
            # Todavía sin repartir el espacio: se vuelve a intentar enseguida
            return self.intentos < 25
        destino = caja.origin.y - ajuste.get_page_size() * 0.28
        ajuste.set_value(max(0, min(destino, ajuste.get_upper() - ajuste.get_page_size())))
        return False

    def pie(self):
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        caja.set_margin_top(36)
        sep = Gtk.Separator()
        caja.append(sep)

        acciones = Gtk.Box(spacing=10, halign=Gtk.Align.CENTER)
        acciones.set_margin_top(16)

        self.btn_leido = Gtk.Button(css_classes=["pill"])
        self.actualizar_boton_leido()
        self.btn_leido.connect("clicked", lambda *_: self.alternar_leido())
        acciones.append(self.btn_leido)

        practicar = Gtk.Button(label="Practicar este capítulo",
                               css_classes=["suggested-action", "pill"])
        practicar.connect("clicked", lambda *_: self.practicar())
        acciones.append(practicar)
        tarjetas = Gtk.Button(label="✦ Sacar tarjetas", css_classes=["pill"])
        tarjetas.connect("clicked", lambda *_: self.generar_tarjetas())
        acciones.append(tarjetas)
        caja.append(acciones)

        anterior, siguiente = self.vecinos()
        nav = Gtk.Box(spacing=10, homogeneous=True)
        nav.set_margin_top(20)
        for etiqueta, cap, icono, alineacion in (
                ("Anterior", anterior, "go-previous-symbolic", Gtk.Align.START),
                ("Siguiente", siguiente, "go-next-symbolic", Gtk.Align.END)):
            if not cap:
                nav.append(Gtk.Box())
                continue
            b = Gtk.Button(css_classes=["card", "as-nav"])
            interior = Gtk.Box(spacing=12)
            interior.set_margin_top(12)
            interior.set_margin_bottom(12)
            interior.set_margin_start(14)
            interior.set_margin_end(14)
            texto = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
            texto.append(Gtk.Label(label=etiqueta.upper(), xalign=0 if alineacion == Gtk.Align.START else 1,
                                   css_classes=["as-stat-label"]))
            texto.append(Gtk.Label(label=util.plain(cap["title"]), wrap=True,
                                   xalign=0 if alineacion == Gtk.Align.START else 1,
                                   css_classes=["as-nav-title"]))
            if alineacion == Gtk.Align.START:
                interior.append(Gtk.Image.new_from_icon_name(icono))
                interior.append(texto)
            else:
                interior.append(texto)
                interior.append(Gtk.Image.new_from_icon_name(icono))
            b.set_child(interior)
            b.connect("clicked", lambda _b, c=cap: self.ir_a(c))
            nav.append(b)
        caja.append(nav)

        caja.append(Gtk.Label(
            label="← →  capítulo anterior o siguiente   ·   Espacio  avanzar   ·   Esc  volver",
            css_classes=["caption", "as-dim"], halign=Gtk.Align.CENTER))
        return caja

    def chip(self, texto, color, soft=False):
        lab = Gtk.Label(label=texto, css_classes=["as-chip"])
        css = Gtk.CssProvider()
        css.load_from_data(
            f"label {{ background:{util.shade(color, 0.16 if soft else 0.22)};"
            f" color:{color}; }}".encode())
        lab.get_style_context().add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        return lab

    # ----------------------------------------------------------------- acciones

    def vecinos(self):
        ids = [c["id"] for c in self.hermanos]
        if self.ch["id"] not in ids:
            return None, None
        i = ids.index(self.ch["id"])
        return (self.hermanos[i - 1] if i > 0 else None,
                self.hermanos[i + 1] if i + 1 < len(self.hermanos) else None)

    def ir_a(self, capitulo):
        if self.on_navigate:
            self.on_navigate(capitulo)

    def actualizar_boton_leido(self):
        leido = bool(self.ch.get("leido"))
        self.btn_leido.set_label("Leído ✓" if leido else "Marcar como leído")
        self.btn_leido.set_css_classes(["pill"] + (["success"] if leido else []))

    def alternar_leido(self, forzar=None):
        nuevo = (not self.ch.get("leido")) if forzar is None else forzar
        if bool(self.ch.get("leido")) == bool(nuevo):
            return
        db.mark_read(self.con, self.ch["id"], nuevo)
        self.ch["leido"] = int(nuevo)
        self.actualizar_boton_leido()

    def on_scroll(self, adj):
        if adj.get_upper() <= adj.get_page_size():
            return
        avance = (adj.get_value() + adj.get_page_size()) / adj.get_upper()
        if avance > 0.97:
            self.alternar_leido(True)

    def practicar(self):
        self.app.show_popup(self.ch["deck_key"], level=self.ch["level"],
                            tags=self.ch["tags"] or None)

    def generar_tarjetas(self):
        if self.on_cards:
            self.on_cards(self.ch)

    def on_key(self, _c, keyval, _code, _state):
        k = Gdk.keyval_name(keyval)
        if k == "Escape" and self.on_back:
            self.on_back()
            return True
        anterior, siguiente = self.vecinos()
        if k == "Left" and anterior:
            self.ir_a(anterior)
            return True
        if k == "Right" and siguiente:
            self.ir_a(siguiente)
            return True
        return False
