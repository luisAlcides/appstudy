"""Popup de estudio: aparece con el atajo global, muestra una tarjeta y se va."""
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gdk, Gio, Gtk  # noqa: E402

from . import cloze, db, scheduler, sonido, util  # noqa: E402

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
        self.hint_revealed = False
        self.answered = None          # índice elegido en un quiz
        self.hueco = None             # qué hueco se tapa en una tarjeta cloze
        self.shown_at = 0.0
        self.recent_ids = []

        self.card_scale = self.card_escala_guardada()
        w = max(580, int(680 * self.card_scale))
        h = max(480, int(560 * self.card_scale))
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
        self.body.set_margin_start(20)
        self.body.set_margin_end(20)
        self.body.set_margin_bottom(10)
        scroller = Gtk.ScrolledWindow(vexpand=True,
                                      hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_child(self.body)
        root.append(scroller)

        self.footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.footer.set_margin_start(20)
        self.footer.set_margin_end(20)
        self.footer.set_margin_bottom(16)
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
        font_front = f"{1.48 * scale:.2f}rem"
        font_back = f"{1.06 * scale:.2f}rem"
        font_choice = f"{1.00 * scale:.2f}rem"
        font_chip = f"{0.80 * scale:.2f}rem"
        css_data = f"""
        .as-popup .as-front {{
            font-size: {font_front};
        }}
        .as-popup .as-back {{
            font-size: {font_back};
        }}
        .as-popup .as-choice-btn {{
            font-size: {font_choice};
            padding: {int(11 * scale)}px {int(15 * scale)}px;
        }}
        .as-popup .as-chip, .as-popup .as-badge {{
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
        acciones.append("Deshacer el último repaso (Z)", "win.undo")
        acciones.append("Tarjetas que se me atragantan", "win.leeches")
        acciones.append("Abrir AppStudy completo (A)", "win.open")
        m.append_section(None, acciones)

        # Las acciones van en un grupo propio insertado como «win». Adw.Window no
        # es un GActionMap (solo Gtk.ApplicationWindow lo es), así que llamar a
        # self.add_action aquí levanta un AttributeError y el popup no llega a
        # abrirse.
        grupo = Gio.SimpleActionGroup()
        for nombre, cb in (("card_bigger", lambda *_: self.cambiar_tamano_tarjeta(0.15)),
                           ("card_smaller", lambda *_: self.cambiar_tamano_tarjeta(-0.15)),
                           ("card_size_100", lambda *_: self.fijar_tamano_tarjeta(1.0)),
                           ("card_size_125", lambda *_: self.fijar_tamano_tarjeta(1.25)),
                           ("card_size_150", lambda *_: self.fijar_tamano_tarjeta(1.50)),
                           ("skip", lambda *_: self.load_card()),
                           ("undo", lambda *_: self.deshacer()),
                           ("leeches", lambda *_: self.abrir_sanguijuelas()),
                           ("open", lambda *_: self.open_main())):
            a = Gio.SimpleAction.new(nombre, None)
            a.connect("activate", cb)
            grupo.add_action(a)
        self.insert_action_group("win", grupo)
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
        self.recent_ids = []
        self.load_card()

    def load_card(self):
        current_id = self.card["id"] if self.card else None
        if not hasattr(self, "recent_ids"):
            self.recent_ids = []
        if current_id and current_id not in self.recent_ids:
            self.recent_ids.append(current_id)
            if len(self.recent_ids) > 30:
                self.recent_ids.pop(0)

        self.card = scheduler.next_card(self.con, self.deck_key, level=self.level,
                                        tags=self.tags, exclude_ids=self.recent_ids,
                                        exclude_id=current_id)
        if self.card is None and (self.level or self.tags):
            # El capítulo ya no tiene tarjetas pendientes: se amplía al mazo entero
            self.level = self.tags = None
            self.card = scheduler.next_card(self.con, self.deck_key,
                                            exclude_ids=self.recent_ids,
                                            exclude_id=current_id)
        if self.card is None:
            # Si se excluyeron todas las del mazo, vaciamos el historial reciente y reintentamos
            self.recent_ids = [current_id] if current_id else []
            self.card = scheduler.next_card(self.con, self.deck_key, exclude_id=current_id)

        self.revealed = False
        self.hint_revealed = False
        self.answered = None
        self.hueco = (cloze.elegir(self.card["front"])
                      if self.card and self.es_cloze() else None)
        self.shown_at = time.time()
        self.render()

    def es_cloze(self) -> bool:
        return bool(self.card) and self.card["kind"] == "cloze" \
            and cloze.tiene_huecos(self.card["front"])

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
        self.title_widget.set_title(f"{c['deck_icon']} {c['deck_name']}")
        self.title_widget.set_subtitle(
            f"{db.level_name(c['deck_levels'], c['level'])} · {self.progress_text()}")

        # Estructura de la tarjeta moderna
        card_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["as-flashcard"])

        # Franja superior de color de mazo
        accent = Gtk.Box(css_classes=["as-flashcard-accent"])
        css_acc = Gtk.CssProvider()
        css_acc.load_from_data(f"box {{ background-color: {c['deck_color']}; }}".encode())
        accent.get_style_context().add_provider(css_acc, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        card_box.append(accent)

        # Contenido interior de la tarjeta
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                        css_classes=["as-flashcard-inner"])

        # Metadatos / Badges
        meta = Gtk.Box(spacing=8, css_classes=["as-card-meta"])
        meta.append(self.chip(f"{c['deck_icon']} {c['deck_name']}", c["deck_color"]))
        kind_label = {"quiz": "RETO", "lesson": "LECCIÓN",
                      "cloze": "HUECOS"}.get(c["kind"], "TARJETA")
        meta.append(self.chip(kind_label, c["deck_color"], soft=True))
        meta.append(self.chip(db.level_name(c["deck_levels"], c["level"]).upper(),
                              c["deck_color"], soft=True))

        meta.append(Gtk.Box(hexpand=True))

        # Estado de la tarjeta (nueva / repaso)
        status_text = "✨ Nueva" if c["reps"] == 0 else (
            "⚡ Repaso" if c["due"] <= time.time() else f"🔄 En {scheduler.due_label(c['due'])}")
        meta.append(Gtk.Label(label=status_text, css_classes=["as-badge-status"]))
        inner.append(meta)

        # Pregunta / Enunciado. En una cloze se enseña con el hueco tapado
        # hasta que la revelas; entonces sale entera con la respuesta en negrita.
        if self.es_cloze():
            texto = (cloze.resaltado(c["front"], self.hueco) if self.revealed
                     else cloze.enmascarar(c["front"], self.hueco))
        else:
            texto = c["front"]
        front = Gtk.Label(label=util.to_markup(texto), use_markup=True, wrap=True,
                          xalign=0, css_classes=["as-front"], selectable=True)
        inner.append(front)

        # Pista si existe
        if c.get("hint"):
            hint_wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            if not getattr(self, "hint_revealed", False):
                h_btn = Gtk.Button(label="💡 Ver pista", halign=Gtk.Align.START,
                                   css_classes=["as-hint-btn", "flat"])
                h_btn.connect("clicked", lambda *_: self.toggle_hint())
                hint_wrap.append(h_btn)
            else:
                h_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3,
                                css_classes=["as-hint-box"])
                h_box.append(Gtk.Label(label="💡 PISTA", xalign=0, css_classes=["as-hint-title"]))
                h_box.append(Gtk.Label(label=util.to_markup(c["hint"]), use_markup=True,
                                       wrap=True, xalign=0, css_classes=["as-hint-text"]))
                hint_wrap.append(h_box)
            inner.append(hint_wrap)

        if self.es_cloze():
            self.render_cloze_body(inner)
        elif c["kind"] == "lesson":
            self.render_lesson_body(inner)
        elif c["kind"] == "quiz" and c["choices"]:
            self.render_quiz_body(inner)
        else:
            self.render_basic_body(inner)

        card_box.append(inner)
        self.body.append(card_box)

    def toggle_hint(self):
        self.hint_revealed = True
        self.render()

    def render_cloze_body(self, inner):
        """Tarjeta de huecos: se tapa uno, lo dices de memoria y lo compruebas."""
        c = self.card
        total = cloze.cuantos(c["front"])
        if not self.revealed:
            ayuda = cloze.pista(c["front"], self.hueco)
            if ayuda:
                inner.append(Gtk.Label(label=f"💡 {ayuda}", xalign=0, wrap=True,
                                       css_classes=["as-hint-text"]))
            if total > 1:
                inner.append(Gtk.Label(
                    label=f"Hueco {self.hueco + 1} de {total}", xalign=0,
                    css_classes=["as-answer-title"]))
            btn = Gtk.Button(label="Mostrar la respuesta",
                             css_classes=["suggested-action", "pill"],
                             halign=Gtk.Align.CENTER)
            btn.connect("clicked", lambda *_: self.reveal())
            self.footer.append(btn)
            self.footer.append(self.hints_bar([("Espacio", "Mostrar la respuesta"),
                                               ("N", "Otra tarjeta"),
                                               ("Esc", "Cerrar")]))
            return
        inner.append(Gtk.Separator(css_classes=["as-flashcard-divider"]))
        falta = cloze.respuesta(c["front"], self.hueco)
        inner.append(self.answer_box(f"<b>{falta}</b>" + (f"\n\n{c['back']}" if c["back"]
                                                          else ""),
                                     titulo="Lo que faltaba"))
        self.rating_row()

    def render_lesson_body(self, inner):
        inner.append(Gtk.Separator(css_classes=["as-flashcard-divider"]))
        inner.append(self.answer_box(self.card["back"], titulo="Contenido de la lección"))
        self.revealed = True
        self.rating_row(labels={scheduler.GOOD: "Entendido", scheduler.AGAIN: "Repasar pronto"})

    def render_basic_body(self, inner):
        c = self.card
        if not self.revealed:
            btn = Gtk.Button(css_classes=["suggested-action", "pill"], halign=Gtk.Align.CENTER)
            btn_box = Gtk.Box(spacing=8)
            btn_box.append(Gtk.Image.new_from_icon_name("view-reveal-symbolic"))
            btn_box.append(Gtk.Label(label="Mostrar respuesta", css_classes=["heading"]))
            btn.set_child(btn_box)
            btn.connect("clicked", lambda *_: self.reveal())
            self.footer.append(btn)
            self.footer.append(self.hints_bar([("Espacio", "Mostrar respuesta"),
                                               ("N", "Otra tarjeta"),
                                               ("Esc", "Cerrar")]))
        else:
            inner.append(Gtk.Separator(css_classes=["as-flashcard-divider"]))
            inner.append(self.answer_box(c["back"], titulo="Respuesta"))
            self.rating_row()

    def render_quiz_body(self, inner):
        import json
        c = self.card
        choices = json.loads(c["choices"])
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(6)

        for i, texto in enumerate(choices):
            b = Gtk.Button(css_classes=["as-choice-btn"])
            row = Gtk.Box(spacing=12)
            row.append(Gtk.Label(label=str(i + 1), css_classes=["as-choice-num"],
                                 valign=Gtk.Align.CENTER))
            row.append(Gtk.Label(label=util.to_markup(texto), use_markup=True, wrap=True,
                                 xalign=0, hexpand=True))

            if self.answered is not None:
                b.set_sensitive(False)
                if i == c["answer"]:
                    b.add_css_class("as-choice-right")
                    row.append(Gtk.Label(label="✅", valign=Gtk.Align.CENTER))
                elif i == self.answered:
                    b.add_css_class("as-choice-wrong")
                    row.append(Gtk.Label(label="❌", valign=Gtk.Align.CENTER))
            else:
                b.connect("clicked", lambda _b, idx=i: self.answer(idx))

            b.set_child(row)
            box.append(b)
        inner.append(box)

        if self.answered is None:
            self.footer.append(self.hints_bar([("1-4", "Responder opción"),
                                               ("N", "Otra tarjeta"),
                                               ("Esc", "Cerrar")]))
            return

        ok = self.answered == c["answer"]
        veredicto = Gtk.Box(spacing=8, css_classes=["as-verdict",
                            "as-verdict-ok" if ok else "as-verdict-wrong"])
        veredicto.set_margin_top(4)
        veredicto.append(Gtk.Label(label="🎉 ¡Respuesta correcta!" if ok else
                                   f"❌ Respuesta incorrecta. La opción correcta era la {c['answer'] + 1}.",
                                   xalign=0, use_markup=True))
        inner.append(veredicto)

        if c["back"]:
            inner.append(self.answer_box(c["back"], titulo="Explicación del reto"))
        self.rating_row(prefill=scheduler.GOOD if ok else scheduler.AGAIN)

    # ------------------------------------------------------------------ piezas

    def chip(self, text, color, soft=False):
        lab = Gtk.Label(label=text, css_classes=["as-chip"])
        css = Gtk.CssProvider()
        bg = util.shade(color, 0.16 if soft else 0.24)
        fg = color if not soft else util.shade(color, 0.95)
        css.load_from_data(f"label {{ background:{bg}; color:{fg}; }}".encode())
        lab.get_style_context().add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        return lab

    def answer_box(self, text, titulo="Respuesta"):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                      css_classes=["as-answer-box"])
        if titulo:
            box.append(Gtk.Label(label=titulo.upper(), xalign=0,
                                 css_classes=["as-answer-title"]))
        box.append(Gtk.Label(label=util.to_markup(text), use_markup=True, wrap=True,
                             xalign=0, css_classes=["as-back"], selectable=True))

        # Enlace a lectura si existe capítulo asociado
        cap = db.chapter_for_card(self.con, self.card) if self.card else None
        if cap:
            btn_link = Gtk.Button(css_classes=["as-chapter-link", "flat"],
                                  halign=Gtk.Align.START)
            btn_box = Gtk.Box(spacing=6)
            btn_box.append(Gtk.Label(label=f"📖 Leer en «{cap['title']}» →"))
            btn_link.set_child(btn_box)
            btn_link.connect("clicked", lambda *_: self.open_chapter_for_card(cap))
            box.append(btn_link)

        return box

    def open_chapter_for_card(self, cap):
        app = self.get_application()
        if hasattr(app, "show_reading_for_card") and self.card:
            app.show_reading_for_card(self.card["id"])
            self.close()
        elif hasattr(app, "show_main_window"):
            app.show_main_window()
            if hasattr(app, "main_window"):
                app.main_window.abrir_lectura(cap, buscar=f"{self.card['front']} {self.card['back']}")
            self.close()

    def rating_row(self, labels=None, prefill=None):
        labels = labels or {}
        grid = Gtk.Box(spacing=8, homogeneous=True)
        for rating, texto, tecla, clase in RATINGS:
            if labels and rating not in labels:
                continue
            b = Gtk.Button(css_classes=["as-rate-tile", clase])
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

            top_row = Gtk.Box(spacing=4, halign=Gtk.Align.CENTER)
            top_row.append(Gtk.Label(label=tecla, css_classes=["as-rate-num"]))
            top_row.append(Gtk.Label(label=labels.get(rating, texto),
                                     css_classes=["as-rate-title"]))
            inner.append(top_row)

            inner.append(Gtk.Label(
                label=self.preview(rating),
                css_classes=["as-rate-due"]))
            b.set_child(inner)
            if prefill == rating:
                b.add_css_class("suggested-action")
            b.connect("clicked", lambda _b, r=rating: self.rate(r))
            grid.append(b)
        self.footer.append(grid)
        self.footer.append(self.hints_bar([("1-4", "Calificar dificultad"),
                                           ("Z", "Deshacer el anterior"),
                                           ("N", "Otra tarjeta"),
                                           ("Esc", "Cerrar")]))

    def preview(self, rating):
        """Cuándo volvería la tarjeta con esa nota: lo que se lee en el botón.

        Usa tu retención y tus pesos, así que el número del botón es el mismo
        que se guardará al pulsarlo.
        """
        ajustes = scheduler.config(self.con)
        st = scheduler.review(dict(self.card), rating,
                              retencion=ajustes["retencion"], w=ajustes["w"])
        return scheduler.due_label(st["due"])

    def hints_bar(self, items):
        box = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER, css_classes=["as-footer-hints"])
        box.set_margin_top(4)
        for kbd, desc in items:
            item_box = Gtk.Box(spacing=4)
            item_box.append(Gtk.Label(label=kbd, css_classes=["as-kbd-badge"]))
            item_box.append(Gtk.Label(label=desc))
            box.append(item_box)
        return box

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
        if st.get("sanguijuela"):
            aviso = Adw.Toast(
                title=f"🩸 La has fallado {st['lapses']} veces · apartada por ahora",
                timeout=5)
            aviso.set_button_label("Ver")
            aviso.connect("button-clicked", lambda *_: self.abrir_sanguijuelas())
            self.toast.add_toast(aviso)
        else:
            deshacer = Adw.Toast(
                title=f"Guardado · próximo repaso en {scheduler.due_label(st['due'])}",
                timeout=3)
            deshacer.set_button_label("Deshacer")
            deshacer.connect("button-clicked", lambda *_: self.deshacer())
            self.toast.add_toast(deshacer)
        GLib.timeout_add(180, self._next_after_rate)

    def _next_after_rate(self):
        self.load_card()
        return False

    def deshacer(self):
        """Quita el último repaso y deja esa tarjeta como estaba. Es la tecla Z."""
        hecho = scheduler.undo_last(self.con)
        if not hecho:
            self.toast.add_toast(Adw.Toast(title="No hay ningún repaso que deshacer",
                                           timeout=2))
            return
        tarjeta = db.card_by_id(self.con, hecho["card_id"])
        nombre = scheduler.RATING_LABELS.get(hecho["rating"], "")
        self.toast.add_toast(Adw.Toast(
            title=f"Deshecho «{nombre}» · la tarjeta vuelve a estar como antes",
            timeout=3))
        # Se vuelve a enseñar la tarjeta recuperada, que es lo que esperas
        # al deshacer: la ves tal como estaba y la puedes calificar otra vez.
        if tarjeta:
            self.card = tarjeta
            self.recent_ids = [i for i in self.recent_ids if i != tarjeta["id"]]
        self.revealed = False
        self.hint_revealed = False
        self.answered = None
        self.hueco = (cloze.elegir(self.card["front"])
                      if self.card and self.es_cloze() else None)
        self.shown_at = time.time()
        self.render()

    def abrir_sanguijuelas(self):
        app = self.get_application()
        app.show_main_window()
        ventana = getattr(app, "main_window", None)
        if ventana and hasattr(ventana, "mostrar_sanguijuelas"):
            ventana.mostrar_sanguijuelas()
        self.close()

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
        if k in ("z", "Z"):
            self.deshacer()
            return True
        if k in ("a", "A"):
            self.open_main()
            return True
        if (k == "space" and not self.revealed and self.card
                and self.card["kind"] in ("card", "cloze")):
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
