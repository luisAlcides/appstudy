"""Ventana principal: panel, mazos, explorador de tarjetas y ajustes."""
import json
import sys
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk, Pango  # noqa: E402

from . import db, hotkey, pet, scheduler, util  # noqa: E402
from .reader import ChapterView  # noqa: E402


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app, con):
        super().__init__(application=app, title="AppStudy")
        self.con = con
        self.set_default_size(1040, 720)

        self.toast = Adw.ToastOverlay()
        self.set_content(self.toast)

        self.stack = Adw.ViewStack()
        self.stack.add_titled_with_icon(self.build_panel(), "panel", "Panel",
                                        "view-grid-symbolic")
        self.stack.add_titled_with_icon(self.build_reader(), "leer", "Leer",
                                        "view-paged-symbolic")
        self.stack.add_titled_with_icon(self.build_browser(), "tarjetas", "Tarjetas",
                                        "view-list-symbolic")
        self.stack.add_titled_with_icon(self.build_settings(), "ajustes", "Ajustes",
                                        "preferences-system-symbolic")
        # Refrescar las cuatro secciones cuesta más de un segundo (el explorador
        # rehace cientos de filas), así que solo se refresca la que se está
        # mirando; las demás quedan apuntadas y se ponen al día al abrirlas.
        self.sucias: set[str] = set()
        self.tanda = 0               # relleno por tandas del explorador
        self.pendientes: list = []
        self.stack.connect("notify::visible-child-name", lambda *_: self.on_switch())

        header = Adw.HeaderBar()
        switcher = Adw.ViewSwitcher(stack=self.stack,
                                    policy=Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)

        estudiar = Gtk.Button(css_classes=["suggested-action", "pill"])
        estudiar.set_child(Gtk.Box(spacing=6))
        estudiar.get_child().append(Gtk.Image.new_from_icon_name("media-playback-start-symbolic"))
        estudiar.get_child().append(Gtk.Label(label="Estudiar ahora"))
        estudiar.connect("clicked", lambda *_: app.show_popup())
        header.pack_start(estudiar)

        nueva = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="Nueva tarjeta")
        nueva.connect("clicked", lambda *_: self.card_editor())
        header.pack_end(nueva)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(header)
        box.append(self.stack)
        self.stack.set_vexpand(True)
        self.toast.set_child(box)

        self.refresh()

    def notify_user(self, texto):
        self.toast.add_toast(Adw.Toast(title=texto, timeout=3))

    # ------------------------------------------------------------------- panel

    def build_panel(self):
        scroll = Gtk.ScrolledWindow()
        outer = Adw.Clamp(maximum_size=900)
        self.panel_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.panel_box.set_margin_top(22)
        self.panel_box.set_margin_bottom(28)
        self.panel_box.set_margin_start(18)
        self.panel_box.set_margin_end(18)
        outer.set_child(self.panel_box)
        scroll.set_child(outer)
        return scroll

    def refresh_panel(self):
        box = self.panel_box
        while (c := box.get_first_child()) is not None:
            box.remove(c)

        t = db.totals(self.con)

        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                       css_classes=["as-card", "as-hero"])
        saludo = Gtk.Label(xalign=0, use_markup=True, wrap=True)
        pend = t["pendientes"] + min(t["nuevas"], 20)
        saludo.set_markup(
            f"<span size='x-large' weight='bold'>{self.saludo()}</span>\n"
            f"Tienes <b>{pend}</b> tarjetas listas para repasar."
            if pend else
            f"<span size='x-large' weight='bold'>{self.saludo()}</span>\n"
            "Todo al día. Puedes repasar de refuerzo cuando quieras.")
        hero.append(saludo)

        atajo = hotkey.current_binding("") or "sin configurar"
        pista = Gtk.Label(xalign=0, use_markup=True, css_classes=["as-dim"])
        pista.set_markup(
            f"Atajo global: <b>{hotkey.pretty(atajo) if atajo != 'sin configurar' else 'sin configurar'}</b>"
            " — pulsa en cualquier momento para que aparezca el popup.")
        pista.set_margin_top(4)
        hero.append(pista)
        box.append(hero)

        stats = Gtk.Box(spacing=12, homogeneous=True)
        lec = db.reading_totals(self.con)
        for valor, etiqueta in ((t["hoy"], "REPASOS HOY"), (t["racha"], "DÍAS DE RACHA"),
                                (t["pendientes"], "PENDIENTES"),
                                (f"{lec['leidos']}/{lec['total']}", "CAPÍTULOS"),
                                (t["dominadas"], "DOMINADAS")):
            stats.append(self.stat_tile(valor, etiqueta))
        box.append(stats)

        siguiente = self.next_unread()
        if siguiente:
            box.append(self.continue_reading_card(siguiente))

        box.append(self.section_title("Mazos"))
        lista = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                            css_classes=["boxed-list"])
        avance = db.level_progress(self.con)
        for d in db.deck_stats(self.con):
            lista.append(self.deck_row(d, avance.get(d["id"], [])))
        box.append(lista)

    def next_unread(self):
        """El primer capítulo sin leer, respetando el orden de básico a avanzado."""
        for c in db.chapters(self.con):
            if not c["leido"]:
                return c
        return None

    def continue_reading_card(self, cap):
        boton = Gtk.Button(css_classes=["card"])
        caja = Gtk.Box(spacing=14)
        caja.set_margin_top(14)
        caja.set_margin_bottom(14)
        caja.set_margin_start(16)
        caja.set_margin_end(16)
        caja.append(Gtk.Label(label=cap["deck_icon"], css_classes=["as-deck-row-icon"],
                              valign=Gtk.Align.CENTER))
        texto = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        texto.append(Gtk.Label(label="CONTINUAR LEYENDO", xalign=0,
                               css_classes=["as-stat-label"]))
        texto.append(Gtk.Label(label=util.as_label(cap["title"]), xalign=0, wrap=True,
                               use_markup=True, css_classes=["as-nav-title"]))
        texto.append(Gtk.Label(
            label=f"{cap['deck_name']} · "
                  f"{db.level_name(cap['deck_levels'], cap['level'])} · {cap['minutes']} min",
            xalign=0, css_classes=["caption", "as-dim"]))
        caja.append(texto)
        caja.append(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        boton.set_child(caja)
        boton.connect("clicked", lambda *_: self.abrir_lectura(cap))
        return boton

    def abrir_lectura(self, cap, buscar=None):
        """Abre un capítulo en la sección Leer; `buscar` lleva al párrafo exacto."""
        self.stack.set_visible_child_name("leer")
        self.nav.pop_to_tag("biblioteca")   # por si había otro capítulo abierto
        hermanos = db.chapters(self.con, cap["deck_id"])
        self.open_chapter(cap, hermanos, buscar)

    def saludo(self):
        h = time.localtime().tm_hour
        return "Buenos días" if h < 12 else "Buenas tardes" if h < 19 else "Buenas noches"

    def stat_tile(self, valor, etiqueta):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                    css_classes=["as-card"])
        b.set_margin_top(0)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        inner.set_margin_top(14)
        inner.set_margin_bottom(14)
        inner.append(Gtk.Label(label=str(valor), css_classes=["as-stat-value"]))
        inner.append(Gtk.Label(label=etiqueta, css_classes=["as-stat-label"]))
        b.append(inner)
        return b

    def section_title(self, texto):
        lab = Gtk.Label(label=texto, xalign=0, css_classes=["title-4"])
        lab.set_margin_top(8)
        return lab

    def deck_row(self, d, niveles):
        row = Adw.ActionRow(title=d["name"])
        total = d["total"] or 0
        reparto = " · ".join(f"{n['name']} {n['vistas']}/{n['total']}" for n in niveles)
        row.set_subtitle(
            f"{total} tarjetas · {d['pendientes'] or 0} pendientes · "
            f"{d['dominadas'] or 0} dominadas\n{reparto}")
        row.set_subtitle_lines(2)
        row.add_prefix(Gtk.Label(label=d["icon"], css_classes=["as-deck-row-icon"]))

        sw = Gtk.Switch(active=bool(d["enabled"]), valign=Gtk.Align.CENTER,
                        tooltip_text="Incluir este mazo en el popup")
        sw.connect("state-set", self.on_deck_toggle, d["id"])
        row.add_suffix(sw)

        b = Gtk.Button(icon_name="media-playback-start-symbolic", valign=Gtk.Align.CENTER,
                       css_classes=["flat"], tooltip_text=f"Estudiar solo {d['name']}")
        b.connect("clicked", lambda *_: self.get_application().show_popup(d["key"]))
        row.add_suffix(b)
        return row

    def on_deck_toggle(self, _sw, estado, deck_id):
        self.con.execute("UPDATE decks SET enabled=? WHERE id=?", (int(estado), deck_id))
        self.con.commit()
        return False

    # ------------------------------------------------------------------ lectura

    def build_reader(self):
        """Biblioteca de capítulos y, encima, el capítulo abierto."""
        self.nav = Adw.NavigationView()

        self.library_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        self.library_box.set_margin_top(20)
        self.library_box.set_margin_bottom(32)
        self.library_box.set_margin_start(16)
        self.library_box.set_margin_end(16)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        clamp = Adw.Clamp(maximum_size=860)
        clamp.set_child(self.library_box)
        scroll.set_child(clamp)

        pagina = Adw.NavigationPage(title="Biblioteca", tag="biblioteca")
        tv = Adw.ToolbarView()
        tv.set_content(scroll)
        pagina.set_child(tv)
        self.nav.add(pagina)
        return self.nav

    def refresh_reader(self):
        box = self.library_box
        while (c := box.get_first_child()) is not None:
            box.remove(c)

        todos = db.chapters(self.con)
        if not todos:
            estado = Adw.StatusPage(
                title="Todavía no hay lecturas",
                description="Pulsa «Recargar mazos incluidos» en Ajustes para importarlas.",
                icon_name="view-paged-symbolic")
            estado.set_vexpand(True)
            box.append(estado)
            return

        t = db.reading_totals(self.con)
        resumen = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                          css_classes=["as-card", "as-hero"])
        titulo = Gtk.Label(xalign=0, use_markup=True)
        titulo.set_markup(
            f"<span size='x-large' weight='bold'>Lecturas</span>\n"
            f"{t['leidos']} de {t['total']} capítulos leídos · "
            f"{t['minutos']} min de material")
        resumen.append(titulo)
        resumen.append(self.progress_bar(t["leidos"], max(t["total"], 1)))
        box.append(resumen)

        por_mazo: dict[int, list] = {}
        for c in todos:
            por_mazo.setdefault(c["deck_id"], []).append(c)

        for deck_id, capitulos in por_mazo.items():
            primero = capitulos[0]
            leidos = sum(1 for c in capitulos if c["leido"])
            cabecera = Gtk.Box(spacing=10)
            cabecera.set_margin_top(6)
            cabecera.append(Gtk.Label(label=primero["deck_icon"],
                                      css_classes=["as-deck-row-icon"]))
            titulo = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1, hexpand=True)
            titulo.append(Gtk.Label(label=primero["deck_name"], xalign=0,
                                    css_classes=["title-4"]))
            titulo.append(Gtk.Label(
                label=f"{leidos}/{len(capitulos)} capítulos · "
                      f"{sum(c['minutes'] for c in capitulos)} min",
                xalign=0, css_classes=["caption", "as-dim"]))
            cabecera.append(titulo)
            box.append(cabecera)

            lista = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                                css_classes=["boxed-list"])
            nivel_actual = None
            for cap in capitulos:
                nombre_nivel = db.level_name(cap["deck_levels"], cap["level"])
                if nombre_nivel != nivel_actual:
                    nivel_actual = nombre_nivel
                    encabezado = Adw.ActionRow(title=nombre_nivel.upper(),
                                               css_classes=["as-level-header"])
                    encabezado.set_activatable(False)
                    lista.append(encabezado)
                lista.append(self.chapter_row(cap, capitulos))
            box.append(lista)

    def chapter_row(self, cap, hermanos):
        row = Adw.ActionRow(title=util.as_label(cap["title"]))
        row.set_subtitle(f"{util.plain(cap['subtitle'])} · {cap['minutes']} min"
                         if cap["subtitle"] else f"{cap['minutes']} min")
        row.set_subtitle_lines(2)
        row.set_activatable(True)
        row.connect("activated", lambda *_: self.open_chapter(cap, hermanos))

        marca = Gtk.Image.new_from_icon_name(
            "object-select-symbolic" if cap["leido"] else "media-playback-start-symbolic")
        marca.add_css_class("success" if cap["leido"] else "dim-label")
        row.add_prefix(marca)
        row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        return row

    def open_chapter(self, cap, hermanos, buscar=None):
        vista = ChapterView(self.get_application(), self.con, dict(cap), hermanos, buscar)
        # Al saltar a otro capítulo se reemplaza la página en vez de apilarla:
        # así «volver» siempre lleva a la biblioteca, no al capítulo anterior.
        vista.on_navigate = lambda c: (self.nav.pop(), self.open_chapter(c, hermanos))

        vista.on_back = lambda: self.nav.pop()

        pagina = Adw.NavigationPage(title=util.plain(cap["title"])[:60])
        cabecera = Adw.HeaderBar()
        practicar = Gtk.Button(icon_name="media-playback-start-symbolic",
                               tooltip_text="Practicar este capítulo")
        practicar.connect("clicked", lambda *_: vista.practicar())
        cabecera.pack_end(practicar)
        tv = Adw.ToolbarView()
        tv.add_top_bar(cabecera)
        tv.set_content(vista)
        pagina.set_child(tv)

        pagina.connect("hidden", lambda *_: self.refresh_reader())
        self.nav.push(pagina)

    def progress_bar(self, hecho, total):
        barra = Gtk.ProgressBar()
        barra.set_fraction(hecho / total if total else 0)
        barra.add_css_class("as-progress")
        return barra

    # -------------------------------------------------------------- explorador

    def build_browser(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        barra = Gtk.Box(spacing=10)
        barra.set_margin_top(12)
        barra.set_margin_bottom(8)
        barra.set_margin_start(16)
        barra.set_margin_end(16)

        self.search = Gtk.SearchEntry(placeholder_text="Buscar en las tarjetas…",
                                      hexpand=True)
        self.search.connect("search-changed", lambda *_: self.refresh_browser())
        barra.append(self.search)

        self.deck_filter = Gtk.DropDown.new_from_strings(["Todos los mazos"])
        self.deck_filter.connect("notify::selected", lambda *_: self.on_deck_filter())
        barra.append(self.deck_filter)

        self.level_filter = Gtk.DropDown.new_from_strings(["Todos los niveles"])
        self.level_filter.connect("notify::selected", lambda *_: self.refresh_browser())
        barra.append(self.level_filter)
        box.append(barra)

        self.browser_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                                        css_classes=["boxed-list"])
        self.browser_list.set_margin_start(16)
        self.browser_list.set_margin_end(16)
        self.browser_list.set_margin_bottom(16)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        clamp = Adw.Clamp(maximum_size=1000)
        clamp.set_child(self.browser_list)
        scroll.set_child(clamp)
        box.append(scroll)
        return box

    def on_deck_filter(self):
        self.level_filter.set_selected(0)
        self.refresh_browser()

    def refresh_browser(self):
        decks = db.deck_stats(self.con)
        etiquetas = ["Todos los mazos"] + [f"{d['icon']} {d['name']}" for d in decks]
        modelo = self.deck_filter.get_model()
        if [modelo.get_string(i) for i in range(modelo.get_n_items())] != etiquetas:
            sel = self.deck_filter.get_selected()
            self.deck_filter.set_model(Gtk.StringList.new(etiquetas))
            self.deck_filter.set_selected(min(sel, len(etiquetas) - 1))

        idx = self.deck_filter.get_selected()
        deck = decks[idx - 1] if 0 < idx <= len(decks) else None
        deck_id = deck["id"] if deck else None
        texto = self.search.get_text().strip().lower()

        # El filtro de nivel solo tiene sentido con un mazo elegido: cada mazo
        # tiene sus propios nombres de nivel (Básico… o A2…).
        etiquetas_nivel = ["Todos los niveles"]
        if deck:
            etiquetas_nivel += json.loads(deck["levels"] or "[]")
        modelo_n = self.level_filter.get_model()
        if [modelo_n.get_string(i) for i in range(modelo_n.get_n_items())] != etiquetas_nivel:
            self.level_filter.set_model(Gtk.StringList.new(etiquetas_nivel))
            self.level_filter.set_selected(0)
        self.level_filter.set_sensitive(len(etiquetas_nivel) > 1)
        nivel = self.level_filter.get_selected()

        sql = """SELECT c.*, d.icon, d.name AS deck_name, d.levels AS deck_levels,
                        s.due, s.reps, s.interval
                 FROM cards c JOIN decks d ON d.id=c.deck_id JOIN state s ON s.card_id=c.id"""
        args, cond = [], []
        if deck_id:
            cond.append("c.deck_id=?")
            args.append(deck_id)
        if texto:
            cond.append("(LOWER(c.front) LIKE ? OR LOWER(c.back) LIKE ? OR LOWER(c.tags) LIKE ?)")
            args += [f"%{texto}%"] * 3
        if nivel:
            cond.append("c.level=?")
            args.append(nivel)
        if cond:
            sql += " WHERE " + " AND ".join(cond)
        sql += " ORDER BY d.pos, c.level, c.id LIMIT 500"
        filas = self.con.execute(sql, args).fetchall()

        while (c := self.browser_list.get_first_child()) is not None:
            self.browser_list.remove(c)

        if not filas:
            self.browser_list.append(Adw.ActionRow(
                title="Sin resultados",
                subtitle="Prueba otra búsqueda o crea una tarjeta nueva."))
            return

        # Cientos de filas de golpe congelan la ventana casi dos segundos, así
        # que se llena por tandas: la primera se ve al instante y el resto entra
        # en los ratos libres. Cada refresco estrena número de tanda para que un
        # relleno a medias se abandone si cambias el filtro mientras tanto.
        self.tanda += 1
        self.pendientes = list(filas)
        self.llenar_browser(self.tanda, 30)

    def llenar_browser(self, tanda, cuantas=60):
        if tanda != self.tanda:
            return False               # otro filtro mandó: este relleno ya no vale
        for f in self.pendientes[:cuantas]:
            self.browser_list.append(self.card_row(f))
        del self.pendientes[:cuantas]
        if self.pendientes:
            GLib.idle_add(self.llenar_browser, tanda)
        return False

    def card_row(self, f):
        row = Adw.ActionRow(title=util.as_label(f["front"])[:140])
        row.set_title_lines(2)
        estado = ("sin ver" if f["reps"] == 0
                  else f"repaso en {scheduler.due_label(f['due'])}")
        tipo = {"quiz": "Reto", "lesson": "Lección"}.get(f["kind"], "Tarjeta")
        row.set_subtitle(f"{f['icon']} {f['deck_name']} · "
                         f"{db.level_name(f['deck_levels'], f['level'])} · "
                         f"{tipo} · {estado}")
        row.set_activatable(True)
        row.connect("activated", lambda _r, cid=f["id"]: self.card_editor(cid))

        edit = Gtk.Button(icon_name="document-edit-symbolic", css_classes=["flat"],
                          valign=Gtk.Align.CENTER, tooltip_text="Editar")
        edit.connect("clicked", lambda _b, cid=f["id"]: self.card_editor(cid))
        row.add_suffix(edit)

        rm = Gtk.Button(icon_name="user-trash-symbolic",
                        css_classes=["flat", "error"], valign=Gtk.Align.CENTER,
                        tooltip_text="Eliminar")
        rm.connect("clicked", lambda _b, cid=f["id"]: self.confirm_delete(cid))
        row.add_suffix(rm)
        return row

    def confirm_delete(self, card_id):
        dlg = Adw.AlertDialog(heading="¿Eliminar la tarjeta?",
                              body="Se perderá también su historial de repasos.")
        dlg.add_response("cancel", "Cancelar")
        dlg.add_response("del", "Eliminar")
        dlg.set_response_appearance("del", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.connect("response", self.on_delete_response, card_id)
        dlg.present(self)

    def on_delete_response(self, _d, respuesta, card_id):
        if respuesta == "del":
            db.delete_card(self.con, card_id)
            self.notify_user("Tarjeta eliminada")
            self.refresh()

    # ------------------------------------------------------------------ editor

    def card_editor(self, card_id=None):
        decks = db.deck_stats(self.con)
        card = None
        if card_id:
            card = self.con.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()

        dlg = Adw.Dialog(title="Editar tarjeta" if card else "Nueva tarjeta")
        dlg.set_content_width(620)
        dlg.set_content_height(640)

        page = Adw.PreferencesPage()
        g1 = Adw.PreferencesGroup(title="Clasificación")

        deck_dd = Adw.ComboRow(title="Mazo",
                               model=Gtk.StringList.new([f"{d['icon']} {d['name']}" for d in decks]))
        if card:
            deck_dd.set_selected(next(i for i, d in enumerate(decks) if d["id"] == card["deck_id"]))
        g1.add(deck_dd)

        tipos = ["Tarjeta (pregunta y respuesta)", "Reto (opción múltiple)", "Lección (solo enseñar)"]
        kinds = ["card", "quiz", "lesson"]
        kind_dd = Adw.ComboRow(title="Tipo", model=Gtk.StringList.new(tipos))
        if card:
            kind_dd.set_selected(kinds.index(card["kind"]) if card["kind"] in kinds else 0)
        g1.add(kind_dd)

        nivel_dd = Adw.ComboRow(title="Nivel",
                               subtitle="Las tarjetas nuevas aparecen de básico a avanzado")
        def poblar_niveles(seleccion=None):
            deck = decks[deck_dd.get_selected()]
            etiquetas = json.loads(deck["levels"] or "[]") or ["Único"]
            nivel_dd.set_model(Gtk.StringList.new(etiquetas))
            nivel_dd.set_selected(min(seleccion or 0, len(etiquetas) - 1))
        poblar_niveles((card["level"] - 1) if card else 0)
        deck_dd.connect("notify::selected", lambda *_: poblar_niveles())
        g1.add(nivel_dd)

        tags = Adw.EntryRow(title="Etiquetas (separadas por coma)")
        tags.set_text(card["tags"] if card else "")
        g1.add(tags)
        page.add(g1)

        g2 = Adw.PreferencesGroup(title="Contenido",
                                  description="Puedes usar <b>negrita</b>, <i>cursiva</i> y <tt>código</tt>.")
        front_view, front_frame = self.text_area(card["front"] if card else "", 90)
        g2.add(self.labeled("Pregunta / enunciado", front_frame))
        back_view, back_frame = self.text_area(card["back"] if card else "", 150)
        g2.add(self.labeled("Respuesta / explicación", back_frame))
        hint = Adw.EntryRow(title="Pista (opcional)")
        hint.set_text(card["hint"] if card else "")
        g2.add(hint)
        page.add(g2)

        g3 = Adw.PreferencesGroup(
            title="Opciones del reto",
            description="Solo para tipo «Reto». La primera opción es la correcta salvo que "
                        "cambies el número.")
        opciones = []
        actuales = json.loads(card["choices"]) if card and card["choices"] else []
        for i in range(4):
            e = Adw.EntryRow(title=f"Opción {i + 1}")
            e.set_text(actuales[i] if i < len(actuales) else "")
            opciones.append(e)
            g3.add(e)
        correcta = Adw.SpinRow.new_with_range(1, 4, 1)
        correcta.set_title("Opción correcta")
        correcta.set_value((card["answer"] + 1) if card and card["answer"] >= 0 else 1)
        g3.add(correcta)
        page.add(g3)

        g3.set_visible(kind_dd.get_selected() == 1)
        kind_dd.connect("notify::selected",
                        lambda *_: g3.set_visible(kind_dd.get_selected() == 1))

        guardar = Gtk.Button(label="Guardar", css_classes=["suggested-action"])
        guardar.connect("clicked", lambda *_: self.save_card(
            dlg, card, decks[deck_dd.get_selected()], kinds[kind_dd.get_selected()],
            front_view, back_view, hint.get_text(), tags.get_text(),
            [o.get_text() for o in opciones], int(correcta.get_value()) - 1,
            nivel_dd.get_selected() + 1))

        header = Adw.HeaderBar()
        header.pack_end(guardar)
        tv = Adw.ToolbarView()
        tv.add_top_bar(header)
        tv.set_content(page)
        dlg.set_child(tv)
        dlg.present(self)

    def labeled(self, titulo, widget):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.append(Gtk.Label(label=titulo.upper(), xalign=0, css_classes=["as-stat-label"]))
        box.append(widget)
        box.set_margin_bottom(6)
        return box

    def text_area(self, texto, alto):
        view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=8,
                            bottom_margin=8, left_margin=8, right_margin=8)
        view.get_buffer().set_text(texto or "")
        frame = Gtk.ScrolledWindow(min_content_height=alto, css_classes=["card"])
        frame.set_child(view)
        return view, frame

    @staticmethod
    def buffer_text(view):
        b = view.get_buffer()
        return b.get_text(b.get_start_iter(), b.get_end_iter(), False).strip()

    def save_card(self, dlg, card, deck, kind, front_view, back_view, hint, tags,
                  opciones, correcta, nivel):
        front = self.buffer_text(front_view)
        back = self.buffer_text(back_view)
        if not front:
            self.notify_user("La pregunta no puede quedar vacía")
            return
        choices = [o.strip() for o in opciones if o.strip()] if kind == "quiz" else None
        if kind == "quiz" and len(choices or []) < 2:
            self.notify_user("Un reto necesita al menos dos opciones")
            return
        if kind == "quiz" and correcta >= len(choices):
            self.notify_user("La opción correcta no existe")
            return

        if card:
            self.con.execute(
                """UPDATE cards SET deck_id=?, kind=?, front=?, back=?, hint=?,
                                    choices=?, answer=?, tags=?, level=? WHERE id=?""",
                (deck["id"], kind, front, back, hint,
                 json.dumps(choices, ensure_ascii=False) if choices else "",
                 correcta if kind == "quiz" else -1, tags, nivel, card["id"]))
            self.con.commit()
        else:
            db.add_card(self.con, deck["id"], deck["key"], kind, front, back, hint,
                        choices, correcta if kind == "quiz" else -1, tags, level=nivel)
            self.con.commit()
        dlg.close()
        self.notify_user("Tarjeta guardada")
        self.refresh()

    # ----------------------------------------------------------------- ajustes

    def build_settings(self):
        page = Adw.PreferencesPage()

        g = Adw.PreferencesGroup(
            title="Atajo global",
            description="La combinación que hace aparecer el popup desde cualquier aplicación.")
        self.hotkey_row = Adw.ActionRow(title="Combinación actual")
        cambiar = Gtk.Button(label="Cambiar…", valign=Gtk.Align.CENTER)
        cambiar.connect("clicked", lambda *_: self.capture_hotkey())
        self.hotkey_row.add_suffix(cambiar)
        g.add(self.hotkey_row)

        quitar = Adw.ActionRow(title="Quitar el atajo",
                               subtitle="Elimina el registro del escritorio")
        b = Gtk.Button(label="Quitar", valign=Gtk.Align.CENTER, css_classes=["destructive-action"])
        b.connect("clicked", lambda *_: self.remove_hotkey())
        quitar.add_suffix(b)
        g.add(quitar)
        page.add(g)

        gp = Adw.PreferencesGroup(
            title=f"{pet.NOMBRE}, la mascota",
            description="Una criatura que vive encima de todo en el escritorio: te "
                        "recuerda estudiar y te enseña una tarjeta sin abrir nada.")

        soltar = Adw.ActionRow(
            title=f"Soltar a {pet.NOMBRE} ahora",
            subtitle="Clic para que te enseñe algo · clic derecho para su menú")
        sb = Gtk.Button(label="Soltar", valign=Gtk.Align.CENTER,
                        css_classes=["suggested-action"])
        sb.connect("clicked", lambda *_: self.launch_pet())
        soltar.add_suffix(sb)
        gp.add(soltar)

        self.pet_auto = Adw.SwitchRow(
            title="Aparecer al iniciar sesión",
            subtitle="Deja la mascota en el escritorio desde que entras")
        self.pet_auto.connect("notify::active", self.on_pet_autostart)
        gp.add(self.pet_auto)

        self.pet_every = Adw.SpinRow.new_with_range(5, 240, 5)
        self.pet_every.set_title("Cada cuántos minutos te habla")
        self.pet_every.set_subtitle("Solo insiste si tienes algo pendiente")
        self.pet_every.connect("notify::value", self.on_pet_every)
        gp.add(self.pet_every)
        page.add(gp)

        gpr = Adw.PreferencesGroup(
            title="Progreso",
            description="Para empezar de cero un día que no cuenta, o una racha que no es tuya.")
        self.pet_size = Adw.SpinRow.new_with_range(50, 250, 10)
        self.pet_size.set_title(f"Tamaño de {pet.NOMBRE}")
        self.pet_size.set_subtitle("En porcentaje; también desde su menú, con Más grande / Más pequeño")
        self.pet_size.connect("notify::value", self.on_pet_size)
        gpr.add(self.pet_size)
        self.hoy_row = Adw.ActionRow(title="Borrar lo estudiado hoy")
        hb = Gtk.Button(label="Borrar", valign=Gtk.Align.CENTER, css_classes=["destructive-action"])
        hb.connect("clicked", lambda *_: self.confirm_undo_today())
        self.hoy_row.add_suffix(hb)
        gpr.add(self.hoy_row)
        self.racha_row = Adw.ActionRow(title="Reiniciar la racha")
        rr = Gtk.Button(label="Reiniciar", valign=Gtk.Align.CENTER)
        rr.connect("clicked", lambda *_: self.confirm_reset_streak())
        self.racha_row.add_suffix(rr)
        gpr.add(self.racha_row)
        page.add(gpr)

        g2 = Adw.PreferencesGroup(title="Contenido")
        recargar = Adw.ActionRow(
            title="Recargar contenido incluido",
            subtitle="Reimporta tarjetas y capítulos de fábrica sin borrar tu "
                     "progreso · Ctrl+R o F5 en cualquier ventana")
        rb = Gtk.Button(label="Recargar", valign=Gtk.Align.CENTER)
        rb.connect("clicked", lambda *_: self.reload_content())
        recargar.add_suffix(rb)
        g2.add(recargar)

        self.db_row = Adw.ActionRow(title="Base de datos", subtitle=str(db.DB_PATH))
        self.db_row.set_subtitle_selectable(True)
        g2.add(self.db_row)
        page.add(g2)

        g3 = Adw.PreferencesGroup(title="Atajos dentro del popup")
        for tecla, desc in (("Ctrl+R", "Recargar el contenido (también F5)"),
                            ("Espacio", "Mostrar la respuesta"),
                            ("1 – 4", "Responder un reto o calificar el repaso"),
                            ("N", "Saltar a otra tarjeta"),
                            ("A", "Abrir esta ventana"),
                            ("Esc", "Cerrar el popup")):
            r = Adw.ActionRow(title=desc)
            r.add_prefix(Gtk.Label(label=tecla, css_classes=["as-kbd"],
                                   valign=Gtk.Align.CENTER))
            g3.add(r)
        page.add(g3)
        return page

    def launch_pet(self):
        self.get_application().launch_pet()
        self.notify_user(f"{pet.NOMBRE} ya anda por el escritorio")

    def on_pet_autostart(self, fila, _p):
        self.notify_user(pet.set_autostart(fila.get_active()))

    def on_pet_every(self, fila, _p):
        db.set_meta(self.con, "pet_every", int(fila.get_value()))

    def on_pet_size(self, fila, _p):
        # La mascota lo lee cada pocos segundos y se redimensiona sola
        db.set_meta(self.con, "pet_scale", round(fila.get_value() / 100, 2))

    def confirm_undo_today(self):
        n = db.totals(self.con)["hoy"]
        if not n:
            self.notify_user("Hoy no hay nada que borrar")
            return
        dlg = Adw.AlertDialog(
            heading=f"¿Borrar los {n} repasos de hoy?",
            body="Cada tarjeta vuelve a estar como antes de hoy: mismos intervalos, "
                 "misma fecha de repaso. La racha se recalcula.")
        dlg.add_response("cancel", "Cancelar")
        dlg.add_response("undo", "Borrar")
        dlg.set_response_appearance("undo", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.connect("response", self.on_undo_today)
        dlg.present(self)

    def on_undo_today(self, _d, respuesta):
        if respuesta == "undo":
            n = scheduler.undo_recent(self.con)
            self.notify_user(f"Borrados {n} repasos · el día empieza de cero")
            self.refresh()

    def confirm_reset_streak(self):
        dlg = Adw.AlertDialog(
            heading="¿Reiniciar la racha?",
            body="Vuelve a cero y empieza a contar con el próximo repaso. "
                 "Las tarjetas y su historial no se tocan.")
        dlg.add_response("cancel", "Cancelar")
        dlg.add_response("reset", "Reiniciar")
        dlg.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.connect("response", self.on_reset_streak)
        dlg.present(self)

    def on_reset_streak(self, _d, respuesta):
        if respuesta == "reset":
            db.reset_streak(self.con)
            self.notify_user("Racha reiniciada")
            self.refresh()

    def refresh_settings(self):
        b = hotkey.current_binding("")
        entorno = hotkey.desktop()
        if b:
            self.hotkey_row.set_subtitle(hotkey.pretty(b))
        elif entorno == "gnome":
            self.hotkey_row.set_subtitle("Sin configurar — pulsa «Cambiar…»")
        else:
            self.hotkey_row.set_subtitle(
                f"Escritorio «{entorno}»: configúralo manualmente con el comando "
                f"{self.get_application().launch_command()}")

        self.pet_auto.handler_block_by_func(self.on_pet_autostart)
        self.pet_auto.set_active(pet.autostart_enabled())
        self.pet_auto.handler_unblock_by_func(self.on_pet_autostart)
        self.pet_every.handler_block_by_func(self.on_pet_every)
        self.pet_every.set_value(float(db.get_meta(self.con, "pet_every",
                                                   pet.DEFAULT_EVERY_MIN)))
        self.pet_every.handler_unblock_by_func(self.on_pet_every)
        self.pet_size.handler_block_by_func(self.on_pet_size)
        self.pet_size.set_value(float(db.get_meta(self.con, "pet_scale", 1.0)) * 100)
        self.pet_size.handler_unblock_by_func(self.on_pet_size)
        t = db.totals(self.con)
        self.hoy_row.set_subtitle(f"{t['hoy']} repasos en las últimas 24 h; las tarjetas "
                                  "vuelven a como estaban")
        self.racha_row.set_subtitle(f"Ahora: {t['racha']} días seguidos. Vuelve a cero "
                                    "sin tocar las tarjetas")

    def capture_hotkey(self):
        dlg = Adw.Dialog(title="Nuevo atajo")
        dlg.set_content_width(460)
        dlg.set_content_height(330)
        estado = Adw.StatusPage(
            title="Pulsa la combinación",
            description="Debe incluir Ctrl, Alt o Super. Esc para cancelar.",
            icon_name="preferences-desktop-keyboard-shortcuts-symbolic")
        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())
        tv.set_content(estado)
        dlg.set_child(tv)

        ctrl = Gtk.EventControllerKey()
        ctrl.connect("key-pressed", self.on_hotkey_key, dlg, estado)
        dlg.add_controller(ctrl)
        dlg.present(self)

    def on_hotkey_key(self, _c, keyval, _code, state, dlg, estado):
        from gi.repository import Gdk
        if keyval == Gdk.KEY_Escape:
            dlg.close()
            return True
        if Gdk.keyval_name(keyval) in (
                "Control_L", "Control_R", "Alt_L", "Alt_R", "Shift_L", "Shift_R",
                "Super_L", "Super_R", "ISO_Level3_Shift"):
            return True

        mods = []
        if state & Gdk.ModifierType.CONTROL_MASK:
            mods.append("<Control>")
        if state & Gdk.ModifierType.ALT_MASK:
            mods.append("<Alt>")
        if state & Gdk.ModifierType.SUPER_MASK:
            mods.append("<Super>")
        if state & Gdk.ModifierType.SHIFT_MASK:
            mods.append("<Shift>")
        if not mods:
            estado.set_description("Esa tecla sola no sirve: añade Ctrl, Alt o Super.")
            return True

        # <Super><Shift>e — gsettings espera los modificadores en este orden
        orden = ["<Control>", "<Alt>", "<Super>", "<Shift>"]
        binding = "".join(m for m in orden if m in mods) + Gdk.keyval_name(keyval)
        ok, mensaje = hotkey.install(self.get_application().launch_command(), binding)
        dlg.close()
        self.notify_user(mensaje)
        self.refresh()
        return True

    def remove_hotkey(self):
        hotkey.uninstall()
        self.notify_user("Atajo eliminado")
        self.refresh()

    def reload_content(self):
        # Lo mismo que Ctrl+R o `appstudy --reload`
        self.get_application().reload_content()

    # ----------------------------------------------------------------- general

    SECCIONES = ("panel", "leer", "tarjetas", "ajustes")

    def refrescar_seccion(self, nombre):
        {"panel": self.refresh_panel, "leer": self.refresh_reader,
         "tarjetas": self.refresh_browser, "ajustes": self.refresh_settings}[nombre]()

    def on_switch(self):
        """Al cambiar de pestaña, se pone al día solo si quedó pendiente."""
        nombre = self.stack.get_visible_child_name()
        if nombre in self.sucias:
            self.sucias.discard(nombre)
            self.refrescar_seccion(nombre)

    def refresh(self):
        """Los datos han cambiado: se rehace lo que se ve y se apunta el resto."""
        visible = self.stack.get_visible_child_name() or "panel"
        self.sucias = set(self.SECCIONES) - {visible}
        self.refrescar_seccion(visible)
