"""Popup de estudio: aparece con el atajo global, muestra una tarjeta y se va."""
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gdk, Gio, Gtk  # noqa: E402

from . import db, scheduler, sonido, util  # noqa: E402

RATINGS = [
    (scheduler.AGAIN, "Otra vez", "1", "as-rate-again"),
    (scheduler.HARD, "Difícil", "2", "as-rate-hard"),
    (scheduler.GOOD, "Bien", "3", "as-rate-good"),
    (scheduler.EASY, "Fácil", "4", "as-rate-easy"),
]


class PopupWindow(Adw.Window):
    """Ventana flotante con una sola tarjeta. Todo se maneja con el teclado o ratón."""

    def __init__(self, app, con, deck_key=None, level=None, tags=None):
        super().__init__(application=app, title="AppStudy")
        self.con = con
        self.deck_key = deck_key
        self.level = level
        self.tags = tags
        self.card = None
        self.revealed = False
        self.answered = None          # índice elegido en un quiz
        self.shown_at = 0.0

        self.card_scale = self.card_escala_guardada()
        w = max(560, int(660 * self.card_scale))
        h = max(450, int(530 * self.card_scale))
        self.set_default_size(w, h)
        self.set_resizable(True)
        self.add_css_class("as-popup")

        self.card_css_provider = Gtk.CssProvider()
        disp = Gdk.Display.get_default()
        if disp:
            Gtk.StyleContext.add_provider_for_display(
                disp, self.card_css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 5)
        self.aplicar_escala_tarjeta()

        self.toast = Adw.ToastOverlay()
        self.set_content(self.toast)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toast.set_child(root)

        header = Adw.HeaderBar(css_classes=["flat"])
        self.title_widget = Adw.WindowTitle(title="AppStudy", subtitle="")
        header.set_title_widget(self.title_widget)

        skip = Gtk.Button(icon_name="media-skip-forward-symbolic",
                          tooltip_text="Otra tarjeta (N)")
        skip.connect("clicked", lambda *_: self.load_card())
        header.pack_start(skip)

        # Botones para cambiar tamaño de la tarjeta
        zoom_box = Gtk.Box(spacing=2)
        btn_out = Gtk.Button(icon_name="zoom-out-symbolic",
                             tooltip_text="Tarjeta más pequeña (Ctrl -)",
                             css_classes=["flat"])
        btn_out.connect("clicked", lambda *_: self.cambiar_tamano_tarjeta(-0.10))
        btn_in = Gtk.Button(icon_name="zoom-in-symbolic",
                            tooltip_text="Tarjeta más grande (Ctrl +)",
                            css_classes=["flat"])
        btn_in.connect("clicked", lambda *_: self.cambiar_tamano_tarjeta(0.10))
        zoom_box.append(btn_out)
        zoom_box.append(btn_in)
        header.pack_end(zoom_box)

        opener = Gtk.Button(icon_name="view-grid-symbolic",
                            tooltip_text="Abrir AppStudy completo (A)")
        opener.connect("clicked", lambda *_: self.open_main())
        header.pack_end(opener)
        root.append(header)

        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.body.set_margin_start(22)
        self.body.set_margin_end(22)
        self.body.set_margin_bottom(10)
        scroller = Gtk.ScrolledWindow(vexpand=True,
                                      hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_child(self.body)
        root.append(scroller)

        self.footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.footer.set_margin_start(22)
        self.footer.set_margin_end(22)
        self.footer.set_margin_bottom(18)
        self.footer.set_margin_top(4)
        root.append(self.footer)

        # Menú contextual de clic derecho
        self.menu_popover = Gtk.PopoverMenu.new_from_model(self.build_context_menu())
        self.menu_popover.set_parent(root)
        self.menu_popover.set_has_arrow(False)

        clic_derecho = Gtk.GestureClick(button=3)
        clic_derecho.connect("pressed", self.on_right_click)
        root.add_controller(clic_derecho)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.on_key)
        self.add_controller(keys)

        self.load_card()

    # ---------------------------------------------------------------- tamaño y escala

    def card_escala_guardada(self) -> float:
        try:
            return float(db.get_meta(self.con, "card_scale", 1.15))
        except (TypeError, ValueError):
            return 1.15

    def fijar_tamano_tarjeta(self, valor: float):
        nueva = round(max(0.70, min(2.50, valor)), 2)
        db.set_meta(self.con, "card_scale", nueva)
        self.card_scale = nueva
        self.aplicar_escala_tarjeta()
        self.render()

    def cambiar_tamano_tarjeta(self, paso: float):
        nueva = round(self.card_scale + paso, 2)
        self.fijar_tamano_tarjeta(nueva)

    def aplicar_escala_tarjeta(self):
        scale = getattr(self, "card_scale", 1.15)
        font_front = f"{1.50 * scale:.2f}rem"
        font_back = f"{1.08 * scale:.2f}rem"
        font_choice = f"{1.02 * scale:.2f}rem"
        font_chip = f"{0.84 * scale:.2f}rem"
        css_data = f"""
        .as-popup .as-front {{
            font-size: {font_front};
        }}
        .as-popup .as-back {{
            font-size: {font_back};
        }}
        .as-popup .as-choice {{
            font-size: {font_choice};
            padding: {int(12 * scale)}px {int(16 * scale)}px;
        }}
        .as-popup .as-chip {{
            font-size: {font_chip};
        }}
        """
        self.card_css_provider.load_from_data(css_data.encode())

    def build_context_menu(self):
        m = Gio.Menu()
        tamano = Gio.Menu()
        tamano.append("Tarjeta más grande (Ctrl +)", "win.card_bigger")
        tamano.append("Tarjeta más pequeña (Ctrl -)", "win.card_smaller")
        tamano.append("Tamaño: Normal (100%)", "win.card_size_100")
        tamano.append("Tamaño: Grande (125%)", "win.card_size_125")
        tamano.append("Tamaño: Muy grande (150%)", "win.card_size_150")
        m.append_section("Tamaño de visualización", tamano)
        acciones = Gio.Menu()
        acciones.append("Otra tarjeta (N)", "win.skip")
        acciones.append("Abrir AppStudy completo (A)", "win.open")
        m.append_section(None, acciones)

        for nombre, cb in (("card_bigger", lambda *_: self.cambiar_tamano_tarjeta(0.15)),
                           ("card_smaller", lambda *_: self.cambiar_tamano_tarjeta(-0.15)),
                           ("card_size_100", lambda *_: self.fijar_tamano_tarjeta(1.0)),
                           ("card_size_125", lambda *_: self.fijar_tamano_tarjeta(1.25)),
                           ("card_size_150", lambda *_: self.fijar_tamano_tarjeta(1.50)),
                           ("skip", lambda *_: self.load_card()),
                           ("open", lambda *_: self.open_main())):
            a = Gio.SimpleAction.new(nombre, None)
            a.connect("activate", cb)
            self.add_action(a)
        return m

    def on_right_click(self, _gesture, _n_press, x, y):
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        self.menu_popover.set_pointing_to(rect)
        self.menu_popover.popup()

    # ---------------------------------------------------------------- contenido

    def set_filter(self, deck_key=None, level=None, tags=None):
        """Reapunta el popup (por ejemplo al practicar un capítulo concreto)."""
        self.deck_key, self.level, self.tags = deck_key, level, tags
        self.load_card()

    def load_card(self):
        self.card = scheduler.next_card(self.con, self.deck_key, level=self.level,
                                        tags=self.tags)
        if self.card is None and (self.level or self.tags):
            # El capítulo ya no tiene tarjetas pendientes: se amplía al mazo entero
            self.level = self.tags = None
            self.card = scheduler.next_card(self.con, self.deck_key)
        self.revealed = False
        self.answered = None
        self.shown_at = time.time()
        self.render()

    def clear(self, box):
        while (child := box.get_first_child()) is not None:
            box.remove(child)

    def render(self):
        self.clear(self.body)
        self.clear(self.footer)

        if not self.card:
            self.title_widget.set_subtitle("")
            estado = Adw.StatusPage(
                title="No hay tarjetas",
                description="Activa un mazo o agrega tarjetas desde la ventana principal.",
                icon_name="dialog-information-symbolic")
            estado.set_vexpand(True)
            self.body.append(estado)
            b = Gtk.Button(label="Abrir AppStudy", css_classes=["suggested-action", "pill"],
                           halign=Gtk.Align.CENTER)
            b.connect("clicked", lambda *_: self.open_main())
            self.footer.append(b)
            return

        c = self.card
        self.title_widget.set_subtitle(
            f"{c['deck_icon']}  {c['deck_name']} · "
            f"{db.level_name(c['deck_levels'], c['level'])}")

        # Cabecera: mazo + tipo + estado de repaso
        top = Gtk.Box(spacing=8)
        top.set_margin_top(6)
        top.append(self.chip(f"{c['deck_icon']} {c['deck_name']}", c["deck_color"]))
        kind_label = {"quiz": "RETO", "lesson": "LECCIÓN"}.get(c["kind"], "REPASO")
        top.append(self.chip(kind_label, c["deck_color"], soft=True))
        top.append(self.chip(db.level_name(c["deck_levels"], c["level"]).upper(),
                             c["deck_color"], soft=True))
        top.append(Gtk.Box(hexpand=True))
        top.append(Gtk.Label(label=self.progress_text(), css_classes=["as-dim", "caption"]))
        self.body.append(top)

        # Pregunta / enunciado
        front = Gtk.Label(label=util.to_markup(c["front"]), use_markup=True, wrap=True,
                          xalign=0, css_classes=["as-front"], selectable=True)
        front.set_margin_top(6)
        self.body.append(front)

        if c["kind"] == "lesson":
            self.render_lesson()
        elif c["kind"] == "quiz" and c["choices"]:
            self.render_quiz()
        else:
            self.render_basic()

    def render_lesson(self):
        self.body.append(self.back_card(self.card["back"]))
        self.revealed = True
        self.rating_row(labels={scheduler.GOOD: "Entendido", scheduler.AGAIN: "Repasar pronto"})

    def render_basic(self):
        c = self.card
        if not self.revealed:
            if c["hint"]:
                exp = Gtk.Expander(label="Ver pista")
                lab = Gtk.Label(label=util.to_markup(c["hint"]), use_markup=True, wrap=True,
                                xalign=0, css_classes=["as-hint"])
                lab.set_margin_top(6)
                lab.set_margin_start(6)
                exp.set_child(lab)
                self.body.append(exp)
            btn = Gtk.Button(label="Mostrar respuesta", halign=Gtk.Align.CENTER,
                             css_classes=["suggested-action", "pill"])
            btn.connect("clicked", lambda *_: self.reveal())
            self.footer.append(btn)
            self.footer.append(self.hints("Espacio  mostrar respuesta   ·   N  otra   ·   Esc  cerrar"))
        else:
            self.body.append(self.back_card(c["back"]))
            self.rating_row()

    def render_quiz(self):
        import json
        c = self.card
        choices = json.loads(c["choices"])
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(8)
        for i, texto in enumerate(choices):
            b = Gtk.Button(css_classes=["as-choice"])
            row = Gtk.Box(spacing=12)
            row.append(Gtk.Label(label=str(i + 1), css_classes=["as-kbd"],
                                 valign=Gtk.Align.CENTER))
            row.append(Gtk.Label(label=util.to_markup(texto), use_markup=True, wrap=True,
                                 xalign=0, hexpand=True))
            b.set_child(row)
            if self.answered is not None:
                b.set_sensitive(False)
                if i == c["answer"]:
                    b.add_css_class("as-choice-right")
                elif i == self.answered:
                    b.add_css_class("as-choice-wrong")
            else:
                b.connect("clicked", lambda _b, idx=i: self.answer(idx))
            box.append(b)
        self.body.append(box)

        if self.answered is None:
            self.footer.append(self.hints("1-4  responder   ·   N  otra   ·   Esc  cerrar"))
            return

        ok = self.answered == c["answer"]
        veredicto = Gtk.Label(xalign=0, use_markup=True, wrap=True, css_classes=["as-back"])
        veredicto.set_markup(
            f"<b>{'✅ ¡Correcto!' if ok else '❌ Incorrecto'}</b>")
        self.body.append(veredicto)
        if c["back"]:
            self.body.append(self.back_card(c["back"], titulo="Por qué"))
        self.rating_row(prefill=scheduler.GOOD if ok else scheduler.AGAIN)

    # ------------------------------------------------------------------ piezas

    def chip(self, text, color, soft=False):
        lab = Gtk.Label(label=text, css_classes=["as-chip"])
        css = Gtk.CssProvider()
        bg = util.shade(color, 0.16 if soft else 0.22)
        fg = color if not soft else util.shade(color, 0.95)
        css.load_from_data(f"label {{ background:{bg}; color:{fg}; }}".encode())
        lab.get_style_context().add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        return lab

    def back_card(self, text, titulo=None):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.add_css_class("as-card")
        box.set_margin_top(6)
        box.set_margin_bottom(4)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        inner.set_margin_top(14)
        inner.set_margin_bottom(14)
        inner.set_margin_start(16)
        inner.set_margin_end(16)
        if titulo:
            inner.append(Gtk.Label(label=titulo.upper(), xalign=0,
                                   css_classes=["as-stat-label"]))
        inner.append(Gtk.Label(label=util.to_markup(text), use_markup=True, wrap=True,
                               xalign=0, css_classes=["as-back"], selectable=True))
        box.append(inner)
        return box

    def rating_row(self, labels=None, prefill=None):
        labels = labels or {}
        grid = Gtk.Box(spacing=8, homogeneous=True)
        for rating, texto, tecla, clase in RATINGS:
            if labels and rating not in labels:
                continue
            b = Gtk.Button(css_classes=["as-rate", clase])
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            inner.append(Gtk.Label(label=labels.get(rating, texto)))
            inner.append(Gtk.Label(
                label=self.preview(rating),
                css_classes=["caption", "as-dim"]))
            b.set_child(inner)
            if prefill == rating:
                b.add_css_class("suggested-action")
            b.connect("clicked", lambda _b, r=rating: self.rate(r))
            grid.append(b)
        self.footer.append(grid)
        self.footer.append(self.hints(
            "1 Otra vez · 2 Difícil · 3 Bien · 4 Fácil   ·   N otra   ·   Esc cerrar"
            if not labels else "3 Entendido · 1 Repasar pronto   ·   N otra   ·   Esc cerrar"))

    def preview(self, rating):
        st = scheduler.review(dict(self.card), rating)
        return scheduler.due_label(st["due"])

    def hints(self, text):
        lab = Gtk.Label(label=text, css_classes=["caption", "as-dim"],
                        halign=Gtk.Align.CENTER, wrap=True)
        lab.set_margin_top(4)
        return lab

    def progress_text(self):
        t = db.totals(self.con)
        return f"{t['hoy']} hoy · {t['pendientes']} pendientes · racha {t['racha']}d"

    # ------------------------------------------------------------------ acciones

    def reveal(self):
        if not self.card or self.revealed:
            return
        self.revealed = True
        self.render()

    def answer(self, idx):
        if self.answered is not None:
            return
        self.answered = idx
        self.revealed = True
        self.render()

    def rate(self, rating):
        if not self.card:
            return
        sonido.reproducir(sonido.config(self.con),
                          "acierto" if rating >= scheduler.GOOD else "fallo")
        ms = int((time.time() - self.shown_at) * 1000)
        st = scheduler.apply_review(self.con, self.card["id"], rating, ms)
        self.toast.add_toast(Adw.Toast(
            title=f"Guardado · próximo repaso en {scheduler.due_label(st['due'])}",
            timeout=2))
        GLib.timeout_add(180, self._next_after_rate)

    def _next_after_rate(self):
        self.load_card()
        return False

    def open_main(self):
        self.get_application().show_main_window()
        self.close()

    def on_key(self, _c, keyval, _code, state):
        k = Gdk.keyval_name(keyval)
        if k == "Escape":
            self.close()
            return True
        if (state & Gdk.ModifierType.CONTROL_MASK) and k in ("plus", "equal", "KP_Add"):
            self.cambiar_tamano_tarjeta(0.10)
            return True
        if (state & Gdk.ModifierType.CONTROL_MASK) and k in ("minus", "underscore", "KP_Subtract"):
            self.cambiar_tamano_tarjeta(-0.10)
            return True
        if (state & Gdk.ModifierType.CONTROL_MASK) and k in ("0", "KP_0"):
            self.fijar_tamano_tarjeta(1.15)
            return True
        if k in ("n", "N"):
            self.load_card()
            return True
        if k in ("a", "A"):
            self.open_main()
            return True
        if k == "space" and not self.revealed and self.card and self.card["kind"] == "card":
            self.reveal()
            return True
        if k in ("1", "2", "3", "4", "KP_1", "KP_2", "KP_3", "KP_4"):
            n = int(k[-1]) - 1
            if not self.card:
                return True
            if self.card["kind"] == "quiz" and self.answered is None:
                import json
                if n < len(json.loads(self.card["choices"])):
                    self.answer(n)
                return True
            if self.revealed:
                if self.card["kind"] == "lesson" and n not in (scheduler.AGAIN, scheduler.GOOD):
                    return True
                self.rate(n)
            return True
        return False
