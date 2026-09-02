"""Ventana principal: panel, mazos, explorador de tarjetas y ajustes."""
import json
import sys
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk, Pango  # noqa: E402

from . import cloze, db, estadisticas, fsrs, graficas, hotkey, ia  # noqa: E402
from . import libros, logros, pet, respaldo, scheduler  # noqa: E402
from . import sonido, util  # noqa: E402
from .biblioteca import Biblioteca  # noqa: E402

MAX_FILAS = 120        # tarjetas que se pintan a la vez en el explorador
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
        self.stack.add_titled_with_icon(self.build_stats(), "estadisticas",
                                        "Progreso", "org.gnome.Settings-time-symbolic")
        self.biblioteca = Biblioteca(self, self.con)
        self.stack.add_titled_with_icon(self.biblioteca, "biblioteca", "Biblioteca",
                                        "library-symbolic")
        self.stack.add_titled_with_icon(self.build_settings(), "ajustes", "Ajustes",
                                        "preferences-system-symbolic")
        # Refrescar las cuatro secciones cuesta más de un segundo (el explorador
        # rehace cientos de filas), así que solo se refresca la que se está
        # mirando; las demás quedan apuntadas y se ponen al día al abrirlas.
        self.sucias: set[str] = set()
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

        if t["objetivo"]:
            box.append(self.barra_objetivo(t))
        if t["sanguijuelas"]:
            box.append(self.aviso_sanguijuelas(t["sanguijuelas"]))

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

    def barra_objetivo(self, t):
        """Cuánto llevas de tu objetivo de hoy, con la barra llena o no."""
        hechos, meta = t["hoy"], t["objetivo"]
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                       css_classes=["as-card"])
        dentro = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for lado in ("top", "bottom", "start", "end"):
            getattr(dentro, f"set_margin_{lado}")(14)

        fila = Gtk.Box(spacing=8)
        cumplido = hechos >= meta
        fila.append(Gtk.Label(
            label="🎯 Objetivo de hoy" if not cumplido else "✅ Objetivo cumplido",
            xalign=0, css_classes=["heading"]))
        fila.append(Gtk.Box(hexpand=True))
        fila.append(Gtk.Label(label=f"{min(hechos, meta)} / {meta}",
                              css_classes=["as-dim"]))
        dentro.append(fila)

        barra = Gtk.ProgressBar(fraction=min(1.0, hechos / meta) if meta else 0.0)
        barra.add_css_class("as-goal-bar")
        if cumplido:
            barra.add_css_class("success")
        dentro.append(barra)

        if not cumplido:
            faltan = meta - hechos
            dentro.append(Gtk.Label(
                label=f"Te {'falta' if faltan == 1 else 'faltan'} {faltan} "
                      f"{'tarjeta' if faltan == 1 else 'tarjetas'}",
                xalign=0, css_classes=["as-dim"]))
        caja.append(dentro)
        return caja

    def aviso_sanguijuelas(self, cuantas):
        """Las tarjetas que se te atragantan, con un atajo para arreglarlas."""
        fila = Adw.ActionRow(
            title=f"🩸 {cuantas} "
                  f"{'tarjeta se te atraganta' if cuantas == 1 else 'tarjetas se te atragantan'}",
            subtitle="Las has fallado muchas veces seguidas y están apartadas. "
                     "Reescríbelas o pártelas en dos.")
        boton = Gtk.Button(label="Ver", valign=Gtk.Align.CENTER)
        boton.connect("clicked", lambda *_: self.mostrar_sanguijuelas())
        fila.add_suffix(boton)
        lista = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                            css_classes=["boxed-list"])
        lista.append(fila)
        return lista

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

        self.btn_ia = Gtk.Button(icon_name="starred-symbolic",
                                 tooltip_text="Generar tarjetas con la IA")
        self.btn_ia.connect("clicked", lambda *_: self.generar_con_ia())
        barra.append(self.btn_ia)
        box.append(barra)

        self.browser_list = self.lista_vacia()
        scroll = Gtk.ScrolledWindow(vexpand=True)
        self.browser_clamp = Adw.Clamp(maximum_size=1000)
        self.browser_clamp.set_child(self.browser_list)
        scroll.set_child(self.browser_clamp)
        box.append(scroll)
        return box

    @staticmethod
    def lista_vacia():
        lista = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                            css_classes=["boxed-list"])
        for lado in ("start", "end", "bottom"):
            getattr(lista, f"set_margin_{lado}")(16)
        return lista

    def on_deck_filter(self):
        self.level_filter.set_selected(0)
        self.refresh_browser()

    def refresh_browser(self):
        self.btn_ia.set_visible(ia.config(self.con)["activa"])
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
        sql += " ORDER BY d.pos, c.level, c.id LIMIT 501"
        filas = self.con.execute(sql, args).fetchall()

        # Se arma una lista NUEVA fuera del árbol de widgets: si se le van
        # añadiendo filas mientras está enchufada, GTK recoloca en cada una y la
        # pestaña se congela más de un segundo.
        nueva = self.lista_vacia()
        if not filas:
            nueva.append(Adw.ActionRow(
                title="Sin resultados",
                subtitle="Prueba otra búsqueda o crea una tarjeta nueva."))
            self.browser_list = nueva
            self.browser_clamp.set_child(nueva)
            return

        # GTK tarda ~3,5 ms en medir y colocar cada fila: con las 450 tarjetas
        # de golpe son casi dos segundos de pestaña congelada. Se enseñan las
        # primeras y el resto se encuentra buscando, que es como se usa.
        for f in filas[:MAX_FILAS]:
            nueva.append(self.card_row(f))
        if len(filas) > MAX_FILAS:
            resto = Adw.ActionRow(
                title=f"…y {len(filas) - MAX_FILAS} tarjetas más",
                subtitle="Búscalas por texto, o filtra por mazo y nivel")
            resto.add_prefix(Gtk.Image.new_from_icon_name("system-search-symbolic"))
            nueva.append(resto)
        self.browser_list = nueva
        self.browser_clamp.set_child(nueva)

    def card_row(self, f):
        row = Adw.ActionRow(title=util.as_label(f["front"])[:140])
        row.set_title_lines(2)
        estado = ("✨ sin ver" if f["reps"] == 0
                  else f"🔄 repaso en {scheduler.due_label(f['due'])}")
        tipo = {"quiz": "⚡ Reto", "lesson": "📖 Lección"}.get(f["kind"], "📝 Tarjeta")
        row.set_subtitle(f"{f['icon']} {f['deck_name']} · "
                         f"{db.level_name(f['deck_levels'], f['level'])} · "
                         f"{tipo} · {estado}")
        row.set_activatable(True)
        row.connect("activated", lambda _r, cid=f["id"]: self.card_editor(cid))

        edit = Gtk.Button(icon_name="document-edit-symbolic", css_classes=["flat"],
                          valign=Gtk.Align.CENTER)
        edit.connect("clicked", lambda _b, cid=f["id"]: self.card_editor(cid))
        util.tooltip_perezoso(edit, "Editar")
        row.add_suffix(edit)

        rm = Gtk.Button(icon_name="user-trash-symbolic",
                        css_classes=["flat", "error"], valign=Gtk.Align.CENTER)
        rm.connect("clicked", lambda _b, cid=f["id"]: self.confirm_delete(cid))
        util.tooltip_perezoso(rm, "Eliminar")
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

        tipos = ["Tarjeta (pregunta y respuesta)", "Reto (opción múltiple)",
                 "Lección (solo enseñar)", "Huecos (rellenar lo que falta)"]
        kinds = ["card", "quiz", "lesson", "cloze"]
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

        AYUDA_NORMAL = "Puedes usar <b>negrita</b>, <i>cursiva</i> y <tt>código</tt>."
        AYUDA_CLOZE = (AYUDA_NORMAL + " Marca entre dobles llaves lo que quieras tapar: "
                       "«El comando {{chmod}} cambia los permisos». Puedes poner "
                       "varios huecos, y una pista con {{755::en octal}}.")
        g2 = Adw.PreferencesGroup(title="Contenido", description=AYUDA_NORMAL)
        front_view, front_frame = self.text_area(card["front"] if card else "", 90)
        etiqueta_front = self.labeled("Pregunta / enunciado", front_frame)
        g2.add(etiqueta_front)
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

        def al_cambiar_tipo(*_):
            es_cloze = kinds[kind_dd.get_selected()] == "cloze"
            g3.set_visible(kind_dd.get_selected() == 1)
            g2.set_description(AYUDA_CLOZE if es_cloze else AYUDA_NORMAL)

        kind_dd.connect("notify::selected", al_cambiar_tipo)
        al_cambiar_tipo()

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
        if kind == "cloze" and not cloze.tiene_huecos(front):
            self.notify_user("Una tarjeta de huecos necesita al menos un {{hueco}}")
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

        self.snd_switch = Adw.SwitchRow(
            title="Sonidos",
            subtitle="Avisos, aciertos y fallos · también desde su menú, en Silencio")
        self.snd_switch.connect("notify::active", self.on_sonido)
        gp.add(self.snd_switch)

        self.snd_vol = Adw.SpinRow.new_with_range(0, 100, 10)
        self.snd_vol.set_title("Volumen")
        self.snd_vol.connect("notify::value", self.on_volumen)
        gp.add(self.snd_vol)

        self.pet_every = Adw.SpinRow.new_with_range(5, 240, 5)
        self.pet_every.set_title("Cada cuántos minutos te habla")
        self.pet_every.set_subtitle("Solo insiste si tienes algo pendiente")
        self.pet_every.connect("notify::value", self.on_pet_every)
        gp.add(self.pet_every)
        page.add(gp)

        gia = Adw.PreferencesGroup(
            title="Inteligencia artificial",
            description="Un modelo que corre en tu propia máquina con Ollama: puedes "
                        "preguntarle a Bit, pedirle que te explique una tarjeta de otra "
                        "manera y generar tarjetas nuevas. Ni tus datos ni tus preguntas "
                        "salen del equipo.")
        self.ia_switch = Adw.SwitchRow(title="Activar la IA")
        self.ia_switch.connect("notify::active", self.on_ia_toggle)
        gia.add(self.ia_switch)

        self.ia_url = Adw.EntryRow(title="Servidor")
        self.ia_url.connect("apply", self.on_ia_url)
        self.ia_url.set_show_apply_button(True)
        gia.add(self.ia_url)

        self.ia_modelo = Adw.EntryRow(title="Modelo")
        self.ia_modelo.connect("apply", self.on_ia_modelo)
        self.ia_modelo.set_show_apply_button(True)
        gia.add(self.ia_modelo)

        self.ia_estado = Adw.ActionRow(title="Estado", subtitle="Sin comprobar")
        self.ia_estado.set_subtitle_lines(3)
        probar = Gtk.Button(label="Probar conexión", valign=Gtk.Align.CENTER)
        probar.connect("clicked", lambda *_: self.probar_ia())
        self.ia_estado.add_suffix(probar)
        gia.add(self.ia_estado)

        self.ia_liberar_row = Adw.ActionRow(
            title="Pausar IA y liberar memoria",
            subtitle="Descarga el modelo de la RAM/GPU cuando no lo uses. Se vuelve a activar solo al usarlo.")
        liberar_btn = Gtk.Button(label="Pausar ahora", valign=Gtk.Align.CENTER)
        liberar_btn.connect("clicked", lambda *_: self.pausar_ia_manual())
        self.ia_liberar_row.add_suffix(liberar_btn)
        gia.add(self.ia_liberar_row)
        page.add(gia)

        glib_ = Adw.PreferencesGroup(
            title="Biblioteca",
            description="La carpeta donde tienes tus libros. Se leen donde están: "
                        "AppStudy no los copia ni los modifica.")
        self.libros_row = Adw.ActionRow(title="Carpeta")
        self.libros_row.set_subtitle_selectable(True)
        cambiar = Gtk.Button(label="Cambiar…", valign=Gtk.Align.CENTER)
        cambiar.connect("clicked", lambda *_: self.biblioteca.elegir_carpeta())
        self.libros_row.add_suffix(cambiar)
        glib_.add(self.libros_row)
        page.add(glib_)

        gpr = Adw.PreferencesGroup(
            title="Apariencia y progreso",
            description="Tamaño de elementos en pantalla y gestión del progreso.")
        self.card_size = Adw.SpinRow.new_with_range(70, 250, 5)
        self.card_size.set_title("Tamaño de las tarjetas (globo y popup)")
        self.card_size.set_subtitle("En porcentaje (115% por defecto); también desde el clic derecho en la tarjeta")
        self.card_size.connect("notify::value", self.on_card_size)
        gpr.add(self.card_size)
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

        gfsrs = Adw.PreferencesGroup(
            title="Cómo se programan los repasos",
            description="AppStudy usa FSRS: en vez de multiplicar el intervalo a "
                        "ojo, modela cuánto aguanta cada recuerdo y te la enseña "
                        "el día en que ibas a olvidarla.")

        self.retencion = Adw.SpinRow.new_with_range(70, 99, 1)
        self.retencion.set_title("Retención objetivo")
        self.retencion.set_subtitle(
            "Qué porcentaje quieres acordarte cuando una tarjeta vuelve. Más alto "
            "es saber más, a cambio de más repasos al día. 90 % es el equilibrio "
            "recomendado.")
        self.retencion.connect("notify::value", self.on_retencion)
        gfsrs.add(self.retencion)

        self.umbral_row = Adw.SpinRow.new_with_range(0, 30, 1)
        self.umbral_row.set_title("Apartar tras tantos fallos")
        self.umbral_row.set_subtitle(
            "Una tarjeta que fallas una y otra vez te come el tiempo sin quedarse. "
            "Al llegar a este número se aparta para que la reescribas. 0 lo desactiva.")
        self.umbral_row.connect("notify::value", self.on_umbral)
        gfsrs.add(self.umbral_row)

        self.sanguijuelas_row = Adw.ActionRow(title="Tarjetas atragantadas")
        ver_s = Gtk.Button(label="Ver…", valign=Gtk.Align.CENTER)
        ver_s.connect("clicked", lambda *_: self.mostrar_sanguijuelas())
        self.sanguijuelas_row.add_suffix(ver_s)
        gfsrs.add(self.sanguijuelas_row)

        self.calibrar_row = Adw.ActionRow(title="Calibrar con mi historial")
        self.calibrar_row.set_subtitle_lines(3)
        self.calibrar_btn = Gtk.Button(label="Calibrar", valign=Gtk.Align.CENTER)
        self.calibrar_btn.connect("clicked", lambda *_: self.calibrar_fsrs())
        self.calibrar_row.add_suffix(self.calibrar_btn)
        gfsrs.add(self.calibrar_row)
        page.add(gfsrs)

        gmeta = Adw.PreferencesGroup(
            title="Objetivo diario",
            description="Una meta pequeña y cumplible rinde más que una grande que "
                        "abandonas. Se ve en el panel y en la barra superior.")
        self.objetivo_row = Adw.SpinRow.new_with_range(0, 500, 5)
        self.objetivo_row.set_title("Tarjetas al día")
        self.objetivo_row.set_subtitle("0 para no ponerte objetivo")
        self.objetivo_row.connect("notify::value", self.on_objetivo)
        gmeta.add(self.objetivo_row)
        self.objetivo_estado = Adw.ActionRow(title="Esta semana")
        self.objetivo_estado.set_subtitle_lines(2)
        gmeta.add(self.objetivo_estado)
        page.add(gmeta)

        gres = Adw.PreferencesGroup(
            title="Respaldo",
            description="Todo tu progreso vive en un solo archivo. Una copia "
                        "consistente se hace en un segundo y te ahorra perder meses.")

        self.resp_crear_row = Adw.ActionRow(title="Crear un respaldo ahora")
        cb_ = Gtk.Button(label="Respaldar", valign=Gtk.Align.CENTER,
                         css_classes=["suggested-action"])
        cb_.connect("clicked", lambda *_: self.hacer_respaldo())
        self.resp_crear_row.add_suffix(cb_)
        gres.add(self.resp_crear_row)

        self.resp_auto = Adw.SwitchRow(
            title="Respaldo automático diario",
            subtitle="Al abrir la aplicación, si el último ya tiene más de un día")
        self.resp_auto.connect("notify::active", self.on_respaldo_auto)
        gres.add(self.resp_auto)

        self.resp_restaurar_row = Adw.ActionRow(
            title="Restaurar un respaldo",
            subtitle="Reemplaza tu progreso actual · antes se guarda una copia de seguridad")
        rb_ = Gtk.Button(label="Restaurar\u2026", valign=Gtk.Align.CENTER)
        rb_.connect("clicked", lambda *_: self.elegir_respaldo())
        self.resp_restaurar_row.add_suffix(rb_)
        gres.add(self.resp_restaurar_row)

        exportar = Adw.ActionRow(
            title="Guardar una copia donde tú digas",
            subtitle="Para llevártela a otro equipo o a un disco externo")
        eb_ = Gtk.Button(label="Exportar\u2026", valign=Gtk.Align.CENTER)
        eb_.connect("clicked", lambda *_: self.exportar_respaldo())
        exportar.add_suffix(eb_)
        gres.add(exportar)

        self.resp_carpeta_row = Adw.ActionRow(title="Carpeta de respaldos",
                                              subtitle=str(respaldo.CARPETA))
        self.resp_carpeta_row.set_subtitle_selectable(True)
        gres.add(self.resp_carpeta_row)
        page.add(gres)

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

    def on_sonido(self, fila, _p):
        sonido.guardar(self.con, activo=fila.get_active())
        if fila.get_active():
            sonido.reproducir(sonido.config(self.con), "acierto")   # para oírlo

    def on_volumen(self, fila, _p):
        sonido.guardar(self.con, volumen=fila.get_value() / 100)
        sonido.reproducir(sonido.config(self.con), "clic")

    def on_card_size(self, fila, _p):
        db.set_meta(self.con, "card_scale", round(fila.get_value() / 100, 2))

    def on_pet_size(self, fila, _p):
        # La mascota lo lee cada pocos segundos y se redimensiona sola
        db.set_meta(self.con, "pet_scale", round(fila.get_value() / 100, 2))

    def on_ia_toggle(self, fila, _p):
        activa = fila.get_active()
        ia.guardar(self.con, activa=activa)
        self.btn_ia.set_visible(activa)
        if activa:
            self.probar_ia()
        else:
            cfg = ia.config(self.con)
            ia.hilo(lambda: ia.descargar(cfg))

    def on_ia_url(self, fila):
        ia.guardar(self.con, url=fila.get_text().strip() or ia.URL_DEFECTO)
        self.probar_ia()

    def on_ia_modelo(self, fila):
        ia.guardar(self.con, modelo=fila.get_text().strip() or ia.MODELO_DEFECTO)
        self.probar_ia()

    def pausar_ia_manual(self):
        """Descarga el modelo de la memoria para que quede en reposo."""
        cfg = ia.config(self.con)
        def al_terminar(ok):
            self.notify_user("IA pausada y memoria liberada" if ok else "La IA ya estaba en reposo")
            self.probar_ia()
        ia.hilo(lambda: ia.descargar(cfg), al_terminar)

    def probar_ia(self):
        """Pregunta al servidor sin congelar la ventana."""
        self.ia_estado.set_subtitle("Comprobando…")
        cfg = ia.config(self.con)          # SQLite no se puede tocar desde otro hilo
        ia.hilo(lambda: ia.probar(cfg),
                lambda r: self.ia_estado.set_subtitle(("✓ " if r[0] else "✗ ") + r[1]),
                lambda e: self.ia_estado.set_subtitle(f"✗ {e}"))

    # -------------------------------------------------------- tarjetas con IA

    def generar_con_ia(self):
        """Pide un tema y propone tarjetas; tú eliges cuáles se guardan."""
        if not ia.config(self.con)["activa"]:
            self.notify_user("Activa la IA en Ajustes para generar tarjetas")
            return
        dlg = Adw.AlertDialog(heading="Generar tarjetas con la IA",
                              body="¿Sobre qué tema? El modelo propone y tú decides.")
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        tema = Gtk.Entry(placeholder_text="Ej.: sensores de presión en hidráulica")
        tema.set_activates_default(True)
        caja.append(tema)
        mazos = db.deck_stats(self.con)
        elegir = Gtk.DropDown.new_from_strings([f"{d['icon']} {d['name']}" for d in mazos])
        caja.append(self.labeled("Mazo donde guardarlas", elegir))
        cuantas = Gtk.SpinButton.new_with_range(1, 10, 1)
        cuantas.set_value(5)
        caja.append(self.labeled("Cuántas", cuantas))
        dlg.set_extra_child(caja)
        dlg.add_response("cancel", "Cancelar")
        dlg.add_response("go", "Generar")
        dlg.set_response_appearance("go", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("go")
        dlg.connect("response", self.on_generar, tema, elegir, cuantas, mazos)
        dlg.present(self)

    def on_generar(self, _d, respuesta, tema, elegir, cuantas, mazos):
        texto = tema.get_text().strip()
        if respuesta != "go" or not texto:
            return
        mazo = mazos[elegir.get_selected()]
        n = int(cuantas.get_value())
        self.notify_user(f"Pensando {n} tarjetas sobre «{texto}»…")
        cfg = ia.config(self.con)
        ia.hilo(lambda: ia.generar_tarjetas(cfg, texto, n),
                lambda tarjetas: (self.revisar_generadas(tarjetas, mazo, texto),
                                  ia.hilo(lambda: ia.descargar(cfg))),
                lambda e: (self.notify_user(f"No pude generar: {e}"),
                           ia.hilo(lambda: ia.descargar(cfg))))

    def revisar_generadas(self, tarjetas, mazo, tema, etiquetas="ia"):
        """Enseña lo que propuso el modelo con una casilla por tarjeta."""
        dlg = Adw.AlertDialog(
            heading=f"{len(tarjetas)} tarjetas sobre «{tema}»",
            body="Revísalas antes de guardar: la IA se equivoca, y una tarjeta mala "
                 "se estudia igual que una buena.")
        lista = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                            css_classes=["boxed-list"])
        casillas = []
        for t in tarjetas:
            fila = Adw.ActionRow(title=util.as_label(t["front"]),
                                 subtitle=util.as_label(t["back"]))
            fila.set_title_lines(2)
            fila.set_subtitle_lines(4)
            marca = Gtk.CheckButton(active=True, valign=Gtk.Align.CENTER)
            fila.add_prefix(marca)
            fila.set_activatable_widget(marca)
            lista.append(fila)
            casillas.append((marca, t))
        scroll = Gtk.ScrolledWindow(propagate_natural_height=True, max_content_height=420)
        scroll.set_child(lista)
        dlg.set_extra_child(scroll)
        dlg.add_response("cancel", "Descartar")
        dlg.add_response("save", "Guardar las marcadas")
        dlg.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dlg.connect("response", self.on_guardar_generadas, casillas, mazo, etiquetas)
        dlg.present(self)

    def on_guardar_generadas(self, _d, respuesta, casillas, mazo, etiquetas="ia"):
        cfg = ia.config(self.con)
        ia.hilo(lambda: ia.descargar(cfg))
        if respuesta != "save":
            return
        n = 0
        for marca, t in casillas:
            if not marca.get_active():
                continue
            db.add_card(self.con, mazo["id"], mazo["key"], "card", t["front"], t["back"],
                        tags=etiquetas, level=2)
            n += 1
        self.con.commit()
        self.notify_user(f"{n} tarjetas guardadas en {mazo['name']}" if n
                         else "No marcaste ninguna")
        self.refresh()

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

    # ------------------------------------------------------------ estadísticas

    def build_stats(self):
        scroll = Gtk.ScrolledWindow()
        self.stats_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18,
                                 margin_top=20, margin_bottom=24,
                                 margin_start=24, margin_end=24)
        scroll.set_child(self.stats_box)
        return scroll

    def refresh_stats(self):
        """Rehace la pestaña entera. Los datos se leen una vez y se reparten."""
        caja = self.stats_box
        while (hijo := caja.get_first_child()) is not None:
            caja.remove(hijo)

        t = db.totals(self.con)
        if not self.con.execute("SELECT COUNT(*) FROM log").fetchone()[0]:
            vacio = Adw.StatusPage(
                title="Todavía no hay nada que enseñar",
                description="En cuanto califiques unas cuantas tarjetas, aquí "
                            "aparecerá tu año en un mapa, cuánto aciertas en cada "
                            "mazo y lo que te espera las próximas semanas.",
                icon_name="org.gnome.Settings-time-symbolic", vexpand=True)
            boton = Gtk.Button(label="Estudiar ahora", halign=Gtk.Align.CENTER,
                               css_classes=["suggested-action", "pill"])
            boton.connect("clicked", lambda *_: self.get_application().show_popup())
            vacio.set_child(boton)
            caja.append(vacio)
            return

        memoria = estadisticas.memoria_total(self.con)
        probabilidad = estadisticas.probabilidad_hoy(self.con)
        global_ = estadisticas.retencion_global(self.con)

        if memoria["dias"] >= 365:
            valor_memoria = f"{memoria['dias'] / 365:.1f}".rstrip("0").rstrip(".")
            unidad_memoria = "AÑOS DE MEMORIA"
        else:
            valor_memoria = f"{memoria['dias']:.0f}"
            unidad_memoria = "DÍAS DE MEMORIA"

        cifras = Gtk.Box(spacing=12, homogeneous=True)
        for valor, etiqueta in (
                (valor_memoria, unidad_memoria),
                (f"{probabilidad * 100:.0f} %" if probabilidad is not None else "–",
                 "TE ACORDARÍAS AHORA"),
                (f"{global_['retencion'] * 100:.0f} %"
                 if global_["retencion"] is not None else "–", "ACIERTAS AL REPASAR"),
                (t["racha"], "DÍAS DE RACHA")):
            cifras.append(self.stat_tile(valor, etiqueta))
        caja.append(cifras)
        caja.append(Gtk.Label(
            label="«Memoria construida» es la suma de lo que aguantaría cada "
                  "tarjeta si dejaras de estudiar hoy.",
            xalign=0, wrap=True, css_classes=["as-dim"]))

        mapa = estadisticas.mapa_calor(self.con)
        caja.append(self.stats_card(
            f"Tu año · {mapa['total']} repasos en {mapa['dias_activos']} días",
            graficas.alto_mapa_calor(len(mapa["semanas"])),
            graficas.pintar_mapa_calor, lambda: mapa,
            pie=(f"El mejor día fueron {mapa['mejor']['n']} tarjetas."
                 if mapa.get("mejor") and mapa["mejor"]["n"] else None)))

        reparto = estadisticas.reparto_madurez(self.con)
        caja.append(self.stats_card(
            "En qué punto están tus tarjetas", 62,
            graficas.pintar_madurez, lambda: reparto,
            pie="Maduras son las que ya vuelven cada tres semanas o más."))

        mazos = estadisticas.retencion_por_mazo(self.con)
        medibles = [m for m in mazos if m["retencion"] is not None]
        caja.append(self.stats_card(
            "Cuánto aciertas en cada mazo",
            max(90, 30 * max(1, len(medibles)) + 30),
            graficas.pintar_retencion,
            lambda: {"mazos": mazos, "objetivo": global_["objetivo"]},
            pie="Solo cuentan los repasos de tarjetas que ya habías visto antes: "
                "la primera vez no había nada que recordar."))

        curva = estadisticas.curva_vencimientos(self.con, 30)
        pendientes = sum(d["total"] for d in curva)
        caja.append(self.stats_card(
            f"Lo que viene · {pendientes} repasos en 30 días", 150,
            graficas.pintar_vencimientos, lambda: curva,
            pie="En rojo, lo que ya está vencido. Subir la retención en Ajustes "
                "sube estas barras; bajarla las aplana."))

        tiempos = estadisticas.tiempo_por_nivel(self.con)
        caja.append(self.stats_card(
            "Cuánto tardas en contestar",
            max(80, 32 * max(1, len(tiempos)) + 20),
            graficas.pintar_tiempos, lambda: tiempos,
            pie="La mediana, no la media: basta con dejar el popup abierto una "
                "vez para que una media deje de significar nada."))

        caja.append(self.tarjeta_logros())

    def stats_card(self, titulo, alto, pintar, datos_fn, pie=None):
        """Un bloque con su título, el dibujo y una línea de explicación."""
        marco = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                        css_classes=["as-card"])
        dentro = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for lado in ("top", "bottom", "start", "end"):
            getattr(dentro, f"set_margin_{lado}")(16)
        dentro.append(Gtk.Label(label=titulo, xalign=0, css_classes=["heading"]))
        dentro.append(graficas.area(alto, pintar, datos_fn))
        if pie:
            dentro.append(Gtk.Label(label=pie, xalign=0, wrap=True,
                                    css_classes=["as-dim"]))
        marco.append(dentro)
        return marco

    def tarjeta_logros(self):
        """Los logros, los conseguidos primero y los que faltan en gris."""
        hechos, total = logros.cuantos(self.con)
        grupo = Adw.PreferencesGroup(
            title=f"Logros · {hechos} de {total}",
            description="No hay puntos ni niveles: solo unas cuantas marcas que "
                        "se pasan sin darse cuenta.")
        lista = logros.listado(self.con)
        for le in sorted(lista, key=lambda x: (not x["conseguido"], x["titulo"])):
            if le["conseguido"]:
                cuando = time.strftime("%d/%m/%Y", time.localtime(le["ts"]))
                subtitulo = f"Conseguido el {cuando}"
                if le["dato"]:
                    subtitulo += f" · {le['dato']}"
            else:
                subtitulo = le["pista"]
            fila = Adw.ActionRow(title=f"{le['icono']}  {le['titulo']}",
                                 subtitle=subtitulo)
            fila.set_subtitle_lines(2)
            # Los que faltan no se apagan: su pista es justo lo que quieres leer
            marca = Gtk.Label(label="✓" if le["conseguido"] else "○",
                              valign=Gtk.Align.CENTER,
                              css_classes=["success"] if le["conseguido"] else ["as-dim"])
            fila.add_suffix(marca)
            grupo.add(fila)
        return grupo

    # ------------------------------------------------------- repaso y objetivo

    def on_retencion(self, fila, _p):
        db.set_meta(self.con, "retencion", round(fila.get_value() / 100, 2))

    def on_umbral(self, fila, _p):
        db.set_meta(self.con, "umbral_sanguijuela", int(fila.get_value()))
        quedan = scheduler.recalcular_sanguijuelas(self.con)
        self.notify_user(f"{quedan} tarjetas apartadas con el umbral nuevo"
                         if quedan else "Ninguna tarjeta queda apartada")
        self.refresh()

    def on_objetivo(self, fila, _p):
        db.set_objetivo_diario(self.con, int(fila.get_value()))
        self.refresh()

    def historial_para_calibrar(self):
        """Los repasos agrupados por tarjeta, en orden, como los quiere FSRS."""
        por_tarjeta: dict[int, list] = {}
        for r in self.con.execute("SELECT card_id, rating, ts FROM log ORDER BY ts"):
            por_tarjeta.setdefault(r["card_id"], []).append((r["ts"], r["rating"]))
        # Una tarjeta con un solo repaso no dice nada: no hay nada que predecir
        return [h for h in por_tarjeta.values() if len(h) >= 2]

    def calibrar_fsrs(self):
        """Reajusta los pesos del modelo a tu propio historial, en segundo plano."""
        historial = self.historial_para_calibrar()
        repasos = sum(len(h) for h in historial)
        if repasos < fsrs.MINIMO_REPASOS:
            self.notify_user(
                f"Necesitas al menos {fsrs.MINIMO_REPASOS} repasos encadenados; "
                f"llevas {repasos}")
            return
        self.calibrar_btn.set_sensitive(False)
        self.calibrar_row.set_subtitle("Calculando… puede tardar un rato")
        actuales = scheduler.config(self.con)["w"]
        util.hilo(lambda: fsrs.calibrar(historial, actuales),
                  al_terminar=self.calibracion_lista,
                  al_fallar=self.calibracion_fallo, largo=True)

    def calibracion_lista(self, resultado):
        pesos, antes, despues = resultado
        self.calibrar_btn.set_sensitive(True)
        if despues >= antes:
            self.calibrar_row.set_subtitle(
                "Tu historial ya encaja con los pesos actuales: no hay nada que mejorar.")
            self.notify_user("Los pesos actuales ya son los mejores para ti")
            return
        db.set_meta(self.con, "fsrs_w", json.dumps([round(x, 6) for x in pesos]))
        mejora = (antes - despues) / antes * 100
        self.notify_user(f"Calibrado · la predicción mejora un {mejora:.1f} %")
        self.refresh_settings()

    def calibracion_fallo(self, error):
        self.calibrar_btn.set_sensitive(True)
        self.calibrar_row.set_subtitle(f"No se pudo calibrar: {error}")

    def restaurar_pesos(self):
        db.set_meta(self.con, "fsrs_w", "")
        self.notify_user("Vuelta a los pesos de fábrica")
        self.refresh_settings()

    # ----------------------------------------------------------- sanguijuelas

    def mostrar_sanguijuelas(self):
        """La lista de tarjetas atragantadas, para arreglarlas o devolverlas al ciclo."""
        dlg = Adw.Dialog(title="Tarjetas que se te atragantan")
        dlg.set_content_width(660)
        dlg.set_content_height(560)
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        caja.append(Adw.HeaderBar())
        scroll = Gtk.ScrolledWindow(vexpand=True)
        dentro = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                         margin_top=12, margin_bottom=12,
                         margin_start=12, margin_end=12)
        self._pintar_sanguijuelas(dentro, dlg)
        scroll.set_child(dentro)
        caja.append(scroll)
        dlg.set_child(caja)
        dlg.present(self)

    def _pintar_sanguijuelas(self, dentro, dlg):
        while (hijo := dentro.get_first_child()) is not None:
            dentro.remove(hijo)
        atragantadas = db.leeches(self.con)
        if not atragantadas:
            dentro.append(Adw.StatusPage(
                title="Ninguna se te atraganta",
                description="Aquí aparecen las tarjetas que fallas una y otra vez, "
                            "para que las reescribas en vez de seguir peleándote "
                            "con ellas.",
                icon_name="emblem-ok-symbolic", vexpand=True))
            return
        grupo = Adw.PreferencesGroup(
            title=f"{len(atragantadas)} apartadas",
            description="No salen a estudiar mientras estén aquí. Si una está mal "
                        "escrita o pregunta dos cosas a la vez, edítala o pártela; "
                        "si solo tuviste mala racha, devuélvela al ciclo.")
        for c in atragantadas:
            fila = Adw.ActionRow(
                title=util.as_label(c["front"])[:110],
                subtitle=f"{c['deck_icon']} {c['deck_name']} · "
                         f"{db.level_name(c['deck_levels'], c['level'])} · "
                         f"fallada {c['lapses']} veces")
            fila.set_subtitle_lines(2)
            editar = Gtk.Button(icon_name="document-edit-symbolic",
                                valign=Gtk.Align.CENTER, css_classes=["flat"])
            util.tooltip_perezoso(editar, "Editar la tarjeta")
            editar.connect("clicked", lambda _b, cid=c["id"]: self.card_editor(cid))
            volver = Gtk.Button(label="Al ciclo", valign=Gtk.Align.CENTER)
            util.tooltip_perezoso(volver, "Devolverla a estudio y borrar sus fallos")
            volver.connect("clicked",
                           lambda _b, cid=c["id"]: self.perdonar_sanguijuela(cid, dentro, dlg))
            fila.add_suffix(editar)
            fila.add_suffix(volver)
            grupo.add(fila)
        dentro.append(grupo)

    def perdonar_sanguijuela(self, card_id, dentro, dlg):
        scheduler.perdonar(self.con, card_id)
        self.notify_user("Vuelve al ciclo, con los fallos a cero")
        self._pintar_sanguijuelas(dentro, dlg)
        self.refresh()

    # ---------------------------------------------------------------- respaldo

    def hacer_respaldo(self):
        try:
            ruta = respaldo.crear(self.con, "manual")
        except Exception as e:                       # se enseña, no se traga
            self.notify_user(f"No se pudo respaldar: {e}")
            return
        self.notify_user(f"Respaldo guardado · {respaldo.tamano(ruta.stat().st_size)}")
        self.refresh_settings()

    def on_respaldo_auto(self, fila, _p):
        db.set_meta(self.con, "respaldo_auto", int(fila.get_active()))

    def exportar_respaldo(self):
        dlg = Gtk.FileDialog(title="Guardar una copia de tu progreso")
        dlg.set_initial_name(f"appstudy-{time.strftime('%Y%m%d')}.db")
        dlg.save(self, None, self.on_exportar)

    def on_exportar(self, dlg, resultado):
        try:
            destino = dlg.save_finish(resultado)
        except GLib.Error:
            return                                   # canceló
        if not destino or not destino.get_path():
            return
        try:
            respaldo.copiar(self.con, destino.get_path())
        except Exception as e:
            self.notify_user(f"No se pudo guardar: {e}")
            return
        self.notify_user(f"Copia guardada en {destino.get_path()}")

    def elegir_respaldo(self):
        """Lista los respaldos que hay, y deja traer uno de fuera."""
        disponibles = respaldo.listar()
        dlg = Adw.Dialog(title="Restaurar un respaldo")
        dlg.set_content_width(560)
        dlg.set_content_height(460)
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        caja.append(Adw.HeaderBar())
        scroll = Gtk.ScrolledWindow(vexpand=True)
        dentro = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                         margin_top=12, margin_bottom=12,
                         margin_start=12, margin_end=12)

        if disponibles:
            grupo = Adw.PreferencesGroup(
                title="Respaldos guardados",
                description="Al restaurar, tu progreso actual se guarda antes en "
                            "un respaldo nuevo.")
            for r in disponibles:
                fila = Adw.ActionRow(title=respaldo.cuando(r["ts"]),
                                     subtitle=respaldo.describir(r))
                boton = Gtk.Button(label="Restaurar", valign=Gtk.Align.CENTER)
                boton.connect("clicked",
                              lambda _b, ruta=r["ruta"]: self.confirm_restaurar(ruta, dlg))
                fila.add_suffix(boton)
                grupo.add(fila)
            dentro.append(grupo)
        else:
            dentro.append(Adw.StatusPage(
                title="Todavía no hay respaldos",
                description="Pulsa «Respaldar» en Ajustes, o activa el respaldo "
                            "automático diario.",
                icon_name="document-save-symbolic", vexpand=True))

        otro = Adw.PreferencesGroup()
        fila = Adw.ActionRow(title="Traer un archivo de fuera",
                             subtitle="Una copia que te llevaste a otro equipo o a un disco")
        boton = Gtk.Button(label="Abrir\u2026", valign=Gtk.Align.CENTER)
        boton.connect("clicked", lambda *_: self.importar_respaldo(dlg))
        fila.add_suffix(boton)
        otro.add(fila)
        dentro.append(otro)

        scroll.set_child(dentro)
        caja.append(scroll)
        dlg.set_child(caja)
        dlg.present(self)

    def importar_respaldo(self, padre=None):
        dlg = Gtk.FileDialog(title="Elige el respaldo")
        filtro = Gtk.FileFilter()
        filtro.set_name("Bases de AppStudy")
        filtro.add_pattern("*.db")
        filtros = Gio.ListStore.new(Gtk.FileFilter)
        filtros.append(filtro)
        dlg.set_filters(filtros)
        dlg.set_default_filter(filtro)
        dlg.open(self, None, lambda d, r: self.on_importar(d, r, padre))

    def on_importar(self, dlg, resultado, padre):
        try:
            elegido = dlg.open_finish(resultado)
        except GLib.Error:
            return
        if elegido and elegido.get_path():
            self.confirm_restaurar(elegido.get_path(), padre)

    def confirm_restaurar(self, ruta, padre=None):
        try:
            resumen = respaldo.revisar(ruta)
        except ValueError as e:
            self.notify_user(str(e))
            return
        dlg = Adw.AlertDialog(
            heading="¿Restaurar este respaldo?",
            body=f"Contiene {resumen}.\n\nTu progreso actual se reemplaza por el de "
                 "esta copia. Antes se guarda un respaldo de lo que tienes ahora, "
                 "por si te arrepientes.")
        dlg.add_response("cancel", "Cancelar")
        dlg.add_response("go", "Restaurar")
        dlg.set_response_appearance("go", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.connect("response", self.on_restaurar, ruta, padre)
        dlg.present(self)

    def on_restaurar(self, _d, respuesta, ruta, padre):
        if respuesta != "go":
            return
        try:
            red = respaldo.restaurar(self.con, ruta)
        except Exception as e:
            self.notify_user(f"No se pudo restaurar: {e}")
            return
        if padre:
            padre.close()
        self.notify_user(f"Progreso restaurado · lo anterior quedó en {red.name}")
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
        self.libros_row.set_subtitle(str(libros.carpeta(self.con)))

        snd = sonido.config(self.con)
        for fila, cb, valor in ((self.snd_switch, self.on_sonido, None),
                                (self.snd_vol, self.on_volumen, None)):
            fila.handler_block_by_func(cb)
        self.snd_switch.set_active(snd["activo"])
        self.snd_vol.set_value(round(snd["volumen"] * 100))
        for fila, cb in ((self.snd_switch, self.on_sonido), (self.snd_vol, self.on_volumen)):
            fila.handler_unblock_by_func(cb)

        self.card_size.handler_block_by_func(self.on_card_size)
        self.card_size.set_value(float(db.get_meta(self.con, "card_scale", 1.15)) * 100)
        self.card_size.handler_unblock_by_func(self.on_card_size)

        self.pet_size.handler_block_by_func(self.on_pet_size)
        self.pet_size.set_value(float(db.get_meta(self.con, "pet_scale", 1.0)) * 100)
        self.pet_size.handler_unblock_by_func(self.on_pet_size)
        c = ia.config(self.con)
        for fila, cb in ((self.ia_switch, self.on_ia_toggle), (self.ia_url, self.on_ia_url),
                         (self.ia_modelo, self.on_ia_modelo)):
            fila.handler_block_by_func(cb)
        self.ia_switch.set_active(c["activa"])
        self.ia_url.set_text(c["url"])
        self.ia_modelo.set_text(c["modelo"])
        for fila, cb in ((self.ia_switch, self.on_ia_toggle), (self.ia_url, self.on_ia_url),
                         (self.ia_modelo, self.on_ia_modelo)):
            fila.handler_unblock_by_func(cb)
        self.btn_ia.set_visible(c["activa"])

        t = db.totals(self.con)
        self.hoy_row.set_subtitle(f"{t['hoy']} repasos en las últimas 24 h; las tarjetas "
                                  "vuelven a como estaban")
        self.racha_row.set_subtitle(f"Ahora: {t['racha']} días seguidos. Vuelve a cero "
                                    "sin tocar las tarjetas")

        ajustes = scheduler.config(self.con)
        self.retencion.handler_block_by_func(self.on_retencion)
        self.retencion.set_value(round(ajustes["retencion"] * 100))
        self.retencion.handler_unblock_by_func(self.on_retencion)
        self.umbral_row.handler_block_by_func(self.on_umbral)
        self.umbral_row.set_value(ajustes["umbral"])
        self.umbral_row.handler_unblock_by_func(self.on_umbral)

        self.sanguijuelas_row.set_subtitle(
            f"{t['sanguijuelas']} apartadas ahora mismo" if t["sanguijuelas"]
            else "Ninguna, de momento")

        historial = self.historial_para_calibrar()
        repasos = sum(len(h) for h in historial)
        propios = bool(db.get_meta(self.con, "fsrs_w", ""))
        if repasos < fsrs.MINIMO_REPASOS:
            self.calibrar_row.set_subtitle(
                f"Con {repasos} de los {fsrs.MINIMO_REPASOS} repasos que hacen falta. "
                "Hasta entonces se usan los pesos de fábrica, que ya van bien.")
        elif propios:
            self.calibrar_row.set_subtitle(
                f"Ajustado a tus {repasos} repasos. Vuelve a calibrar de vez en "
                "cuando: cuanto más historial, mejor encaja.")
        else:
            self.calibrar_row.set_subtitle(
                f"Tienes {repasos} repasos: ya se puede ajustar el modelo a cómo "
                "memorizas tú. Tarda un rato y no puede empeorar lo que hay.")
        self.calibrar_btn.set_sensitive(repasos >= fsrs.MINIMO_REPASOS)

        self.objetivo_row.handler_block_by_func(self.on_objetivo)
        self.objetivo_row.set_value(t["objetivo"])
        self.objetivo_row.handler_unblock_by_func(self.on_objetivo)
        semana = db.repasos_por_dia(self.con, 7)
        if t["objetivo"]:
            cumplidos = sum(1 for d in semana if d["cumplido"])
            self.objetivo_estado.set_subtitle(
                f"{cumplidos} de 7 días cumplidos · "
                + " ".join("●" if d["cumplido"] else "○" for d in semana))
        else:
            self.objetivo_estado.set_subtitle(
                "Sin objetivo · " + " ".join(str(d["n"]) for d in semana)
                + " tarjetas en los últimos siete días")

        copias = respaldo.listar()
        if copias:
            self.resp_crear_row.set_subtitle(
                f"El último, {respaldo.cuando(copias[0]['ts'])} · "
                f"{len(copias)} guardados")
        else:
            self.resp_crear_row.set_subtitle("Todavía no has hecho ninguno")
        self.resp_restaurar_row.set_visible(True)
        self.resp_auto.handler_block_by_func(self.on_respaldo_auto)
        self.resp_auto.set_active(bool(int(db.get_meta(self.con, "respaldo_auto", 1))))
        self.resp_auto.handler_unblock_by_func(self.on_respaldo_auto)

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

    SECCIONES = ("panel", "leer", "tarjetas", "estadisticas",
                 "biblioteca", "ajustes")

    def refrescar_seccion(self, nombre):
        {"panel": self.refresh_panel, "leer": self.refresh_reader,
         "tarjetas": self.refresh_browser, "estadisticas": self.refresh_stats,
         "biblioteca": self.biblioteca.refrescar,
         "ajustes": self.refresh_settings}[nombre]()

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
