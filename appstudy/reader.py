"""Modo lectura: capítulos que se leen de corrido, como un documento."""
import json

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from . import db, util  # noqa: E402


def render_body(body: list[dict]) -> Gtk.Widget:
    """Convierte los bloques de un capítulo en widgets con jerarquía tipográfica."""
    col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    for bloque in body:
        for tipo, contenido in bloque.items():
            w = _bloque(tipo, contenido)
            if w is not None:
                col.append(w)
    return col


def _label(texto, css, xalign=0.0, top=0, bottom=0):
    lab = Gtk.Label(label=util.to_markup(texto), use_markup=True, wrap=True,
                    xalign=xalign, css_classes=css, selectable=True)
    lab.set_wrap_mode(2)  # PANGO_WRAP_WORD_CHAR
    lab.set_margin_top(top)
    lab.set_margin_bottom(bottom)
    return lab


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
        vista = Gtk.Label(label=util.to_markup(contenido), use_markup=True, xalign=0,
                          selectable=True, css_classes=["as-read-code"])
        vista.set_margin_top(6)
        vista.set_margin_bottom(6)
        scroll = Gtk.ScrolledWindow(vscrollbar_policy=Gtk.PolicyType.NEVER,
                                    propagate_natural_height=True,
                                    css_classes=["as-read-codebox"])
        scroll.set_child(vista)
        scroll.set_margin_top(8)
        scroll.set_margin_bottom(12)
        return scroll
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
    return None


class ChapterView(Gtk.Box):
    """Un capítulo abierto: portada, cuerpo y pie con la navegación."""

    def __init__(self, app, con, chapter, hermanos):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.app = app
        self.con = con
        self.ch = chapter
        self.hermanos = hermanos           # todos los capítulos del mismo mazo
        self.on_navigate = None            # lo fija la ventana principal
        self.on_back = None

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

        self.columna.append(render_body(json.loads(ch["body"] or "[]")))
        self.columna.append(self.pie())

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
