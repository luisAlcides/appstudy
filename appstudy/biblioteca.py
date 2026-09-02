"""La pestaña Biblioteca: tus libros ordenados, y un lector de PDF dentro.

Dos páginas. **El estante**: arriba lo que estás leyendo, con portada y barra de
avance; debajo, tus carpetas convertidas en estantes que se despliegan. **El
lector**: el PDF página a página, con zoom y teclado, guardando por dónde vas.

Los libros no se copian ni se tocan: se leen donde están. De ellos, en la base
solo queda la ruta, la página por la que ibas y los minutos que llevas leídos.

Dibujar una página tarda ~150 ms, así que se hace en un hilo aparte y se guarda
en caché; la siguiente se va dibujando mientras lees esta, y así pasar de página
sale instantáneo.
"""
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gsk", "4.0")
from gi.repository import Adw, Gdk, GLib, Graphene, Gsk, Gtk  # noqa: E402

from . import db, ia, libros, reto, util  # noqa: E402

ANCHO_PORTADA = 108           # ancho de las portadas de «seguir leyendo»
MAX_POR_ESTANTE = 240         # libros que se pintan al desplegar una carpeta
ESCALAS = (0.35, 0.5, 0.67, 0.8, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0)
BLANCO = Gdk.RGBA()
BLANCO.parse("#ffffff")


def _progreso(guardado: dict) -> float:
    if not guardado or not guardado.get("paginas"):
        return 0.0
    return max(0.0, min(1.0, guardado.get("pagina", 1) / guardado["paginas"]))


class Biblioteca(Adw.Bin):
    def __init__(self, ventana, con):
        super().__init__()
        self.ventana = ventana
        self.con = con
        self.nav = Adw.NavigationView()
        self.set_child(self.nav)

        self.estante = []          # los libros que hay en el disco
        self.guardados = {}        # lo que la base sabe de ellos, por ruta

        self.buscar = Gtk.SearchEntry(placeholder_text="Buscar entre tus libros…",
                                      hexpand=True)
        self.buscar.connect("search-changed", lambda *_: self.pintar())

        cabecera = Gtk.Box(spacing=10)
        for lado, v in (("top", 12), ("bottom", 4), ("start", 16), ("end", 16)):
            getattr(cabecera, f"set_margin_{lado}")(v)
        cabecera.append(self.buscar)
        carpeta = Gtk.Button(icon_name="folder-open-symbolic",
                             tooltip_text="Elegir la carpeta de los libros")
        carpeta.connect("clicked", lambda *_: self.elegir_carpeta())
        cabecera.append(carpeta)

        self.columna = self.columna_vacia()
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        caja.append(cabecera)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        self.clamp = Adw.Clamp(maximum_size=1040)
        self.clamp.set_child(self.columna)
        scroll.set_child(self.clamp)
        caja.append(scroll)

        pagina = Adw.NavigationPage(title="Biblioteca", tag="estante")
        tv = Adw.ToolbarView()
        tv.set_content(caja)
        pagina.set_child(tv)
        self.nav.add(pagina)

    @staticmethod
    def columna_vacia():
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        for lado, v in (("top", 6), ("bottom", 28), ("start", 16), ("end", 16)):
            getattr(col, f"set_margin_{lado}")(v)
        return col

    # ==================================================== el estante

    def refrescar(self):
        """Relee el disco en segundo plano; la ventana sigue respondiendo."""
        self.nav.pop_to_tag("estante")
        self.guardados = db.books_todos(self.con)
        if self.estante:                       # ya hay algo: se pinta y se refresca
            self.pintar()
        else:
            self.esperando()
        raiz = libros.carpeta(self.con)
        util.hilo(lambda: libros.listar(raiz), self.recibir_estante,
                  lambda e: self.esperando(str(e)), fondo=True)

    def recibir_estante(self, estante):
        self.estante = estante
        self.pintar()

    def esperando(self, error=""):
        self.columna = self.columna_vacia()
        estado = Adw.StatusPage(title=error or "Mirando qué libros tienes…",
                                icon_name="folder-symbolic")
        estado.set_vexpand(True)
        self.columna.append(estado)
        self.clamp.set_child(self.columna)

    def pintar(self):
        """Rehace el estante sobre una columna suelta y la enchufa de una vez.

        Añadir doscientas filas a una columna ya enchufada obliga a GTK a
        recolocar en cada una: eso es medio segundo de ventana congelada.
        """
        self.columna = self.columna_vacia()
        filtro = self.buscar.get_text().strip().lower()

        if not self.estante:
            estado = Adw.StatusPage(
                title="Aquí no hay libros",
                description=f"Miré en {libros.carpeta(self.con)}. Elige otra carpeta "
                            "con el botón de arriba a la derecha. Se leen PDF, EPUB, "
                            "TXT y MD.",
                icon_name="folder-symbolic")
            estado.set_vexpand(True)
            self.columna.append(estado)
            self.clamp.set_child(self.columna)
            return

        if filtro:
            palabras = filtro.split()
            hallados = [l for l in self.estante
                        if all(p in f"{l['nombre']} {l['tema']}".lower() for p in palabras)]
            self.columna.append(self.titulillo(
                f"{len(hallados)} resultados para «{filtro}»"))
            lista = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                                css_classes=["boxed-list"])
            for i, l in enumerate(hallados[:120]):
                lista.append(self.fila_libro(l, portada=i < 40))
            if len(hallados) > 120:
                lista.append(Adw.ActionRow(
                    title=f"…y {len(hallados) - 120} más",
                    subtitle="Afina la búsqueda para verlos"))
            self.columna.append(lista)
            self.clamp.set_child(self.columna)
            return

        leyendo = [b for b in db.books_leyendo(self.con, 12)
                   if any(l["ruta"] == b["ruta"] for l in self.estante)]
        if leyendo:
            self.columna.append(self.titulillo("Seguir leyendo"))
            self.columna.append(self.tira(leyendo))

        temas = {}
        for l in self.estante:
            temas.setdefault(l["tema"], []).append(l)
        gigas = sum(l["tam"] for l in self.estante) / 1e9
        self.columna.append(self.titulillo(
            f"Tus estantes · {len(self.estante)} libros · {len(temas)} temas · "
            f"{gigas:.1f} GB"))

        grupo = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                            css_classes=["boxed-list"])
        for tema, del_tema in sorted(temas.items(), key=lambda x: x[0].lower()):
            grupo.append(self.estante_de(tema, del_tema))
        self.columna.append(grupo)
        self.clamp.set_child(self.columna)

    @staticmethod
    def titulillo(texto):
        return Gtk.Label(label=texto, xalign=0, css_classes=["title-4"])

    def estante_de(self, tema, del_tema):
        """Una carpeta. Sus libros se pintan al desplegarla, no antes."""
        empezados = sum(1 for l in del_tema
                        if self.guardados.get(l["ruta"], {}).get("abierto"))
        fila = Adw.ExpanderRow(title=util.as_label(tema))
        fila.set_subtitle(f"{len(del_tema)} libros" +
                          (f" · {empezados} empezados" if empezados else ""))
        fila.add_prefix(Gtk.Label(label="📚", css_classes=["as-deck-row-icon"]))
        hecho = {"si": False}

        def desplegar(*_):
            if hecho["si"] or not fila.get_expanded():
                return
            hecho["si"] = True
            for i, l in enumerate(del_tema[:MAX_POR_ESTANTE]):
                # Con estantes de cientos de libros, solo los primeros estrenan
                # portada: las demás filas van con icono y no cuestan nada.
                fila.add_row(self.fila_libro(l, portada=i < 40))

        fila.connect("notify::expanded", desplegar)
        return fila

    def fila_libro(self, libro, portada=True):
        guardado = self.guardados.get(libro["ruta"])
        fila = Adw.ActionRow(title=util.as_label(libro["nombre"]))
        fila.set_title_lines(2)
        detalle = f"{libro['ext'].upper()} · {libro['tam'] / 1e6:.1f} MB"
        if guardado and guardado["paginas"]:
            detalle += (f" · vas por la página {guardado['pagina']} de "
                        f"{guardado['paginas']} ({_progreso(guardado) * 100:.0f} %)")
        fila.set_subtitle(detalle)
        fila.set_activatable(True)
        fila.connect("activated", lambda *_: self.abrir(libro))

        if libro["ext"] == "pdf" and portada:
            miniatura = Gtk.Picture(width_request=34, height_request=46,
                                    content_fit=Gtk.ContentFit.CONTAIN)
            fila.add_prefix(miniatura)
            self.poner_portada(miniatura, libro["ruta"], 90)
        elif libro["ext"] == "pdf":
            fila.add_prefix(Gtk.Label(label="📕", css_classes=["as-deck-row-icon"]))
        else:
            fila.add_prefix(Gtk.Label(label="📗", css_classes=["as-deck-row-icon"]))

        if guardado and guardado["paginas"]:
            fila.add_suffix(Gtk.ProgressBar(
                fraction=_progreso(guardado), valign=Gtk.Align.CENTER,
                width_request=90, css_classes=["as-progress"]))
        fila.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        return fila

    def tira(self, leyendo):
        """La fila de portadas de «seguir leyendo»."""
        caja = Gtk.Box(spacing=14)
        caja.set_margin_bottom(4)
        for b in leyendo:
            libro = next((l for l in self.estante if l["ruta"] == b["ruta"]), None)
            tarjeta = Gtk.Button(css_classes=["card"],
                                 width_request=ANCHO_PORTADA + 24)
            dentro = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            for lado in ("top", "bottom", "start", "end"):
                getattr(dentro, f"set_margin_{lado}")(10)
            portada = Gtk.Picture(width_request=ANCHO_PORTADA, height_request=150,
                                  content_fit=Gtk.ContentFit.CONTAIN)
            dentro.append(portada)
            self.poner_portada(portada, b["ruta"], 220)
            nombre = Gtk.Label(
                label=util.as_label(b["titulo"]), use_markup=True, wrap=True,
                width_chars=14, max_width_chars=14, lines=2, xalign=0, ellipsize=3,
                css_classes=["caption-heading"])
            nombre.set_wrap_mode(2)                # parte también dentro de palabra
            dentro.append(nombre)
            dentro.append(Gtk.ProgressBar(fraction=_progreso(b),
                                          css_classes=["as-progress"]))
            dentro.append(Gtk.Label(
                label=f"pág. {b['pagina']} de {b['paginas'] or '?'}", xalign=0,
                css_classes=["caption", "as-dim"]))
            tarjeta.set_child(dentro)
            if libro:
                tarjeta.connect("clicked", lambda _b, l=libro: self.abrir(l))
            caja.append(tarjeta)
        scroll = Gtk.ScrolledWindow(vscrollbar_policy=Gtk.PolicyType.NEVER,
                                    propagate_natural_height=True)
        scroll.set_child(caja)
        return scroll

    @staticmethod
    def poner_portada(imagen, ruta, ancho):
        """Encarga la portada a la cola de fondo y la decodifica ahí también.

        `set_filename` decodificaría el PNG en el hilo de la interfaz; crear la
        textura en el obrero deja el hilo principal libre.
        """
        def cargar():
            png = libros.portada(ruta, ancho)
            return Gdk.Texture.new_from_filename(png) if png else None

        util.hilo(cargar, lambda t: imagen.set_paintable(t) if t else None,
                  lambda e: None, fondo=True)

    def elegir_carpeta(self):
        dlg = Gtk.FileDialog(title="¿Dónde tienes los libros?")
        dlg.select_folder(self.ventana, None, self.on_carpeta)

    def on_carpeta(self, dlg, resultado):
        try:
            elegida = dlg.select_folder_finish(resultado)
        except GLib.Error:
            return
        if elegida and elegida.get_path():
            libros.set_carpeta(self.con, elegida.get_path())
            self.refrescar()

    # ==================================================== abrir el lector

    def abrir(self, libro):
        if libro["ext"] != "pdf":
            self.ventana.notify_user("El lector abre PDF; de los otros formatos puedo "
                                     "sacar tarjetas, pero no pasarte las hojas")
            return
        lector = Lector(self, libro)
        self.nav.push(lector.pagina)


class Pagina(Gtk.Widget):
    """La hoja del PDF. Pide el tamaño que le digas (de ahí el zoom de verdad)
    y sabe pintarse invertida para leer de noche.

    Un `Gtk.Picture` encoge la imagen hasta que quepa, así que ampliar solo
    servía para verla más nítida, no más grande. Este widget declara su tamaño
    en `do_measure`, y entonces el ScrolledWindow hace su trabajo.
    """
    __gtype_name__ = "AppStudyPagina"

    def __init__(self):
        super().__init__()
        self.textura = None
        self.invertido = False
        self.ancho, self.alto = 600, 800
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.CENTER)

    def poner(self, textura, ancho, alto):
        self.textura = textura
        self.ancho, self.alto = max(50, int(ancho)), max(50, int(alto))
        self.queue_resize()

    def invertir(self, si):
        self.invertido = bool(si)
        self.queue_draw()

    def do_measure(self, orientacion, _para):
        v = self.ancho if orientacion == Gtk.Orientation.HORIZONTAL else self.alto
        return (v, v, -1, -1)

    def do_snapshot(self, snapshot):
        if self.textura is None:
            return
        rect = Graphene.Rect().init(0, 0, self.get_width(), self.get_height())
        if not self.invertido:
            snapshot.append_texture(self.textura, rect)
            return
        # |blanco − página| = página invertida, y lo hace la GPU
        snapshot.push_blend(Gsk.BlendMode.DIFFERENCE)
        snapshot.append_color(BLANCO, rect)
        snapshot.pop()
        snapshot.append_texture(self.textura, rect)
        snapshot.pop()


class Lector:
    """El PDF abierto: zoom real, búsqueda, marcadores, modo noche y tu avance."""

    def __init__(self, biblioteca, libro):
        self.bib = biblioteca
        self.con = biblioteca.con
        self.libro = libro
        self.desde = time.time()
        self.pendiente = None
        self.memoria = {}
        self.guardar_en = self.redibujar_en = None
        self.texto_libro = None            # se saca al buscar por primera vez

        total = libros.paginas(libro["ruta"])
        guardado = db.book_abrir(self.con, libro["ruta"], libro["nombre"],
                                 libro["tema"], total)
        self.total = total or guardado["paginas"] or 1
        self.n = min(max(1, guardado["pagina"]), self.total)
        self.marcas = db.book_marcas(self.con, libro["ruta"])
        self.tam_pt = libros.tamano_pagina(libro["ruta"])

        ajuste, escala = "ancho", 1.0       # cómo lo estabas leyendo
        try:
            modo, valor = (db.book_zoom(self.con, libro["ruta"]) or "ancho:1.0").split(":")
            ajuste, escala = modo, float(valor)
        except (ValueError, AttributeError):
            pass
        self.ajuste, self.escala = (ajuste if ajuste in ("ancho", "pagina", "manual")
                                    else "ancho"), escala

        self.hoja = Pagina()
        self.scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self.scroll.set_child(self.hoja)
        self.scroll.connect("notify::width", self.al_cambiar_tamano)
        self.scroll.connect("notify::height", self.al_cambiar_tamano)

        rueda = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.BOTH_AXES)
        rueda.connect("scroll", self.on_rueda)
        self.scroll.add_controller(rueda)

        cuerpo = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        cuerpo.append(self.barra_busqueda())
        cuerpo.append(self.scroll)
        cuerpo.append(self.barra())

        self.pagina = Adw.NavigationPage(title=util.plain(libro["nombre"])[:60])
        tv = Adw.ToolbarView()
        tv.add_top_bar(self.cabecera(guardado))
        tv.set_content(cuerpo)
        self.pagina.set_child(tv)
        self.pagina.connect("hidden", lambda *_: self.cerrar())

        teclas = Gtk.EventControllerKey()
        teclas.connect("key-pressed", self.on_key)
        self.pagina.add_controller(teclas)

        self.ir(self.n)

    # ---------------------------------------------------------- cabecera

    def cabecera(self, guardado):
        cab = Adw.HeaderBar()
        self.titulo = Adw.WindowTitle(title=util.plain(self.libro["nombre"])[:48],
                                      subtitle="")
        cab.set_title_widget(self.titulo)

        buscar = Gtk.ToggleButton(icon_name="system-search-symbolic")
        buscar.connect("toggled", lambda b: self.mostrar_busqueda(b.get_active()))
        util.tooltip_perezoso(buscar, "Buscar en el libro (Ctrl+F)")
        cab.pack_start(buscar)
        self.btn_buscar = buscar

        self.btn_marca = Gtk.ToggleButton(icon_name="bookmark-new-symbolic")
        self.btn_marca.connect("toggled", self.on_marcar)
        util.tooltip_perezoso(self.btn_marca, "Marcar esta página (M)")
        cab.pack_start(self.btn_marca)

        noche = Gtk.ToggleButton(icon_name="weather-clear-night-symbolic")
        noche.connect("toggled", lambda b: self.hoja.invertir(b.get_active()))
        util.tooltip_perezoso(noche, "Modo noche: invierte la página (N)")
        cab.pack_end(noche)

        fav = Gtk.ToggleButton(icon_name="starred-symbolic",
                               active=bool(guardado.get("favorito")))
        fav.connect("toggled", lambda b: db.book_favorito(self.con, self.libro["ruta"],
                                                          b.get_active()))
        util.tooltip_perezoso(fav, "Favorito")
        cab.pack_end(fav)

        menu = Gtk.MenuButton(icon_name="view-more-symbolic")
        menu.set_popover(self.menu_extra())
        cab.pack_end(menu)
        return cab

    def menu_extra(self):
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for lado in ("top", "bottom", "start", "end"):
            getattr(caja, f"set_margin_{lado}")(8)
        for etiqueta, accion in (
                ("Ajustar al ancho", lambda: self.poner_ajuste("ancho")),
                ("Ajustar a la página", lambda: self.poner_ajuste("pagina")),
                ("Tamaño real (100 %)", lambda: self.poner_ajuste("manual", 1.0)),
                ("Copiar el texto de esta página", self.copiar_texto),
                ("✦ Tarjetas de estas páginas", self.hacer_tarjetas)):
            b = Gtk.Button(label=etiqueta, css_classes=["flat"])
            b.get_child().set_xalign(0)
            b.connect("clicked", lambda _b, a=accion: a())
            caja.append(b)
        self.caja_marcas = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        caja.append(Gtk.Separator())
        caja.append(self.caja_marcas)
        pop = Gtk.Popover()
        pop.set_child(caja)
        pop.connect("show", lambda *_: self.pintar_marcas())
        return pop

    def pintar_marcas(self):
        while (c := self.caja_marcas.get_first_child()) is not None:
            self.caja_marcas.remove(c)
        if not self.marcas:
            self.caja_marcas.append(Gtk.Label(label="Sin marcadores", xalign=0,
                                              css_classes=["as-dim", "caption"]))
            return
        for pagina in self.marcas:
            b = Gtk.Button(label=f"🔖 Página {pagina}", css_classes=["flat"])
            b.get_child().set_xalign(0)
            b.connect("clicked", lambda _b, p=pagina: self.ir(p))
            self.caja_marcas.append(b)

    # ---------------------------------------------------------- búsqueda

    def barra_busqueda(self):
        self.revelador = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for lado, v in (("top", 8), ("bottom", 8), ("start", 12), ("end", 12)):
            getattr(caja, f"set_margin_{lado}")(v)
        self.entrada_buscar = Gtk.SearchEntry(
            placeholder_text="Buscar en todo el libro…", hexpand=True)
        self.entrada_buscar.connect("activate", lambda *_: self.buscar())
        self.entrada_buscar.connect("search-changed", lambda *_: self.buscar())
        caja.append(self.entrada_buscar)
        self.resultados = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                                      css_classes=["boxed-list"])
        scroll = Gtk.ScrolledWindow(propagate_natural_height=True, max_content_height=210)
        scroll.set_child(self.resultados)
        caja.append(scroll)
        self.revelador.set_child(caja)
        return self.revelador

    def mostrar_busqueda(self, ver):
        self.revelador.set_reveal_child(ver)
        if ver:
            self.entrada_buscar.grab_focus()
            if self.texto_libro is None:      # se saca una vez y se guarda
                ruta = self.libro["ruta"]
                # con saltos de página: es lo que dice en qué página está cada cosa
                util.hilo(lambda: libros.texto(ruta, saltos=True), self.recibir_texto,
                          lambda e: self.bib.ventana.notify_user(str(e)), fondo=True)

    def recibir_texto(self, texto):
        self.texto_libro = texto.split("\f")
        self.buscar()

    def buscar(self):
        aguja = self.entrada_buscar.get_text().strip()
        while (c := self.resultados.get_first_child()) is not None:
            self.resultados.remove(c)
        if len(aguja) < 3:
            return
        if self.texto_libro is None:
            self.resultados.append(Adw.ActionRow(title="Leyendo el libro…"))
            return
        clave = reto.normalizar(aguja)
        hallados = 0
        for i, pagina in enumerate(self.texto_libro, start=1):
            plano = reto.normalizar(pagina)
            donde = plano.find(clave)
            if donde < 0:
                continue
            trozo = " ".join(pagina.split())
            centro = max(0, int(donde * len(trozo) / max(1, len(plano))) - 40)
            fila = Adw.ActionRow(title=f"Página {i}")
            fila.set_subtitle(util.as_label("…" + trozo[centro:centro + 130] + "…"))
            fila.set_subtitle_lines(2)
            fila.set_activatable(True)
            fila.connect("activated", lambda _r, p=i: (self.ir(p),
                                                       self.btn_buscar.set_active(False)))
            self.resultados.append(fila)
            hallados += 1
            if hallados >= 60:
                break
        if not hallados:
            self.resultados.append(Adw.ActionRow(title=f"«{aguja}» no aparece en el libro"))

    # ------------------------------------------------------------- barra

    def barra(self):
        caja = Gtk.Box(spacing=8, css_classes=["toolbar"])
        for lado, v in (("top", 6), ("bottom", 8), ("start", 12), ("end", 12)):
            getattr(caja, f"set_margin_{lado}")(v)

        anterior = Gtk.Button(icon_name="go-previous-symbolic")
        anterior.connect("clicked", lambda *_: self.ir(self.n - 1))
        util.tooltip_perezoso(anterior, "Anterior (←)")
        caja.append(anterior)

        self.caja_pagina = Gtk.Entry(width_chars=4, xalign=0.5)
        self.caja_pagina.connect("activate", self.on_saltar)
        util.tooltip_perezoso(self.caja_pagina, "Ir a una página")
        caja.append(self.caja_pagina)
        caja.append(Gtk.Label(label=f"de {self.total}", css_classes=["as-dim"]))

        siguiente = Gtk.Button(icon_name="go-next-symbolic")
        siguiente.connect("clicked", lambda *_: self.ir(self.n + 1))
        util.tooltip_perezoso(siguiente, "Siguiente (→)")
        caja.append(siguiente)

        self.avance = Gtk.ProgressBar(hexpand=True, valign=Gtk.Align.CENTER,
                                      show_text=True, css_classes=["as-progress"])
        caja.append(self.avance)

        menos = Gtk.Button(icon_name="zoom-out-symbolic")
        menos.connect("clicked", lambda *_: self.zoom(-1))
        util.tooltip_perezoso(menos, "Alejar (−)")
        caja.append(menos)
        self.etiqueta_zoom = Gtk.Label(label="100 %", width_chars=5,
                                       css_classes=["as-dim", "caption"])
        caja.append(self.etiqueta_zoom)
        mas = Gtk.Button(icon_name="zoom-in-symbolic")
        mas.connect("clicked", lambda *_: self.zoom(1))
        util.tooltip_perezoso(mas, "Acercar (+)")
        caja.append(mas)

        ajustar = Gtk.Button(icon_name="zoom-fit-best-symbolic")
        ajustar.connect("clicked", lambda *_: self.poner_ajuste(
            "pagina" if self.ajuste != "pagina" else "ancho"))
        util.tooltip_perezoso(ajustar, "Ajustar a la página o al ancho (F)")
        caja.append(ajustar)
        return caja

    # ------------------------------------------------------------ zoom

    def medidas(self):
        """Cuántos puntos de ancho pide la página con el ajuste actual."""
        w_pt, h_pt = self.tam_pt
        hueco_w = max(200, self.scroll.get_width() - 26)
        hueco_h = max(200, self.scroll.get_height() - 26)
        if self.ajuste == "ancho":
            escala = hueco_w / w_pt
        elif self.ajuste == "pagina":
            escala = min(hueco_w / w_pt, hueco_h / h_pt)
        else:
            escala = self.escala
        escala = max(0.15, min(5.0, escala))
        return escala, int(w_pt * escala), int(h_pt * escala)

    def poner_ajuste(self, ajuste, escala=None):
        self.ajuste = ajuste
        if escala is not None:
            self.escala = escala
        self.ir(self.n, forzar=True)

    def zoom(self, paso):
        actual, _, _ = self.medidas()
        opciones = list(ESCALAS)
        if paso > 0:
            nueva = next((e for e in opciones if e > actual + 0.01), opciones[-1])
        else:
            nueva = next((e for e in reversed(opciones) if e < actual - 0.01), opciones[0])
        self.poner_ajuste("manual", nueva)

    def al_cambiar_tamano(self, *_):
        """Al cambiar el tamaño de la ventana se recalcula, pero sin agobiar."""
        if self.ajuste == "manual":
            return
        if self.redibujar_en:
            GLib.source_remove(self.redibujar_en)

        def rehacer():
            self.redibujar_en = None
            self.ir(self.n, forzar=True)
            return False

        self.redibujar_en = GLib.timeout_add(250, rehacer)

    # ------------------------------------------------------------ páginas

    def ir(self, n, forzar=False):
        n = max(1, min(int(n), self.total))
        escala, ancho, alto = self.medidas()
        self.n = n
        self.caja_pagina.set_text(str(n))
        self.avance.set_fraction(n / self.total)
        self.avance.set_text(f"{n / self.total * 100:.0f} %")
        self.titulo.set_subtitle(f"página {n} de {self.total}")
        self.etiqueta_zoom.set_text(f"{escala * 100:.0f} %")
        self.btn_marca.handler_block_by_func(self.on_marcar)
        self.btn_marca.set_active(n in self.marcas)
        self.btn_marca.handler_unblock_by_func(self.on_marcar)
        self.apuntar_luego(n)

        ruta = self.libro["ruta"]
        # En pantallas HiDPI se dibuja al doble para que no se vea borroso
        factor = self.hoja.get_scale_factor() or 1
        pedido = max(200, int(ancho * factor))
        self.pendiente = (n, pedido)
        if (n, pedido) in self.memoria and not forzar:
            self.mostrar(self.memoria[(n, pedido)], ancho, alto)
            self.adelantar(n, pedido)
            return
        util.hilo(lambda: (n, pedido, ancho, alto, self.cargar(ruta, n, pedido)),
                  self.pintar, self.fallo)

    @staticmethod
    def cargar(ruta, n, ancho):
        """Dibuja y decodifica la página fuera del hilo de la interfaz."""
        return Gdk.Texture.new_from_filename(libros.render(ruta, n, ancho))

    def pintar(self, datos):
        n, pedido, ancho, alto, textura = datos
        self.memoria[(n, pedido)] = textura
        if len(self.memoria) > 10:
            for clave in list(self.memoria)[:-6]:
                del self.memoria[clave]
        if self.pendiente != (n, pedido):
            return
        self.mostrar(textura, ancho, alto)
        self.adelantar(n, pedido)

    def mostrar(self, textura, ancho, alto):
        self.hoja.poner(textura, ancho, alto)
        self.scroll.get_vadjustment().set_value(0)

    def adelantar(self, n, pedido):
        if n >= self.total:
            return
        ruta = self.libro["ruta"]
        hasta = min(self.total, n + 3)
        util.hilo(lambda: libros.render_varias(ruta, n + 1, hasta, pedido),
                  None, lambda e: None, fondo=True)

    def fallo(self, e):
        self.bib.ventana.notify_user(str(e))

    def apuntar_luego(self, n):
        if self.guardar_en:
            GLib.source_remove(self.guardar_en)

        def guardar():
            self.guardar_en = None
            db.book_progreso(self.con, self.libro["ruta"], n)
            return False

        self.guardar_en = GLib.timeout_add(500, guardar)

    # ------------------------------------------------------------ acciones

    def on_marcar(self, boton):
        self.marcas = db.book_marcar(self.con, self.libro["ruta"], self.n)
        self.bib.ventana.notify_user(
            f"Página {self.n} marcada" if self.n in self.marcas else "Marcador quitado")

    def copiar_texto(self):
        ruta, n = self.libro["ruta"], self.n

        def copiar(texto):
            self.pagina.get_clipboard().set(texto.strip())
            self.bib.ventana.notify_user(f"Copiado el texto de la página {n}")

        util.hilo(lambda: libros.texto(ruta, n, n), copiar,
                  lambda e: self.bib.ventana.notify_user(str(e)))

    def on_saltar(self, entrada):
        try:
            self.ir(int(entrada.get_text().strip()))
        except ValueError:
            self.caja_pagina.set_text(str(self.n))

    def on_rueda(self, controlador, _dx, dy):
        """Ctrl+rueda hace zoom; al llegar al final de la hoja, pasa de página."""
        estado = controlador.get_current_event_state()
        if estado & Gdk.ModifierType.CONTROL_MASK:
            self.zoom(1 if dy < 0 else -1)
            return True
        ajuste = self.scroll.get_vadjustment()
        abajo = ajuste.get_value() >= ajuste.get_upper() - ajuste.get_page_size() - 1
        arriba = ajuste.get_value() <= 1
        if dy > 0 and abajo and self.n < self.total:
            self.ir(self.n + 1)
            return True
        if dy < 0 and arriba and self.n > 1:
            self.ir(self.n - 1)
            self.scroll.get_vadjustment().set_value(1e6)     # entra por abajo
            return True
        return False

    def on_key(self, _c, keyval, _code, estado):
        tecla = Gdk.keyval_name(keyval)
        if estado & Gdk.ModifierType.CONTROL_MASK and tecla in ("f", "F"):
            self.btn_buscar.set_active(not self.btn_buscar.get_active())
            return True
        if tecla in ("Left", "Page_Up", "BackSpace"):
            self.ir(self.n - 1)
            return True
        if tecla in ("Right", "Page_Down", "space"):
            self.ir(self.n + 1)
            return True
        if tecla in ("Home", "End"):
            self.ir(1 if tecla == "Home" else self.total)
            return True
        if tecla in ("plus", "equal", "KP_Add"):
            self.zoom(1)
            return True
        if tecla in ("minus", "KP_Subtract"):
            self.zoom(-1)
            return True
        if tecla in ("f", "F"):
            self.poner_ajuste("pagina" if self.ajuste != "pagina" else "ancho")
            return True
        if tecla in ("m", "M"):
            self.btn_marca.set_active(not self.btn_marca.get_active())
            return True
        if tecla in ("n", "N"):
            self.hoja.invertir(not self.hoja.invertido)
            return True
        return False

    def cerrar(self):
        """Al salir se guardan avance, minutos y cómo lo estabas leyendo."""
        for temporizador in ("guardar_en", "redibujar_en"):
            if getattr(self, temporizador):
                GLib.source_remove(getattr(self, temporizador))
                setattr(self, temporizador, None)
        self.memoria.clear()
        minutos = min(180.0, (time.time() - self.desde) / 60)
        db.book_progreso(self.con, self.libro["ruta"], self.n, minutos)
        db.book_zoom(self.con, self.libro["ruta"], f"{self.ajuste}:{self.escala:.2f}")
        self.bib.guardados = db.books_todos(self.con)
        self.bib.pintar()

    # ------------------------------------------------------------ tarjetas

    def hacer_tarjetas(self):
        """Tarjetas de lo que tienes delante: esta página y las dos siguientes."""
        if not ia.config(self.con)["activa"]:
            self.bib.ventana.notify_user("Activa la IA en Ajustes para sacar tarjetas")
            return
        desde, hasta = self.n, min(self.total, self.n + 2)
        self.bib.ventana.notify_user(f"Leyendo las páginas {desde}–{hasta}…")
        cfg = ia.config(self.con)
        libro = self.libro

        def trabajo():
            fragmento = libros.limpiar_texto(
                libros.texto(libro["ruta"], desde, hasta), 9000)
            if len(fragmento) < 400:
                raise libros.LibroError("Estas páginas casi no tienen texto.")
            return ia.generar_desde_texto(
                cfg, fragmento, f"{libro['nombre']} (págs. {desde}–{hasta})", 5)

        util.hilo(trabajo,
                  lambda tarjetas: self.bib.ventana.revisar_generadas(
                      tarjetas, libros.mazo_para(self.con, libro),
                      f"{libro['nombre']} · págs. {desde}–{hasta}", etiquetas="libro,ia"),
                  lambda e: self.bib.ventana.notify_user(f"No pude: {e}"),
                  largo=True)          # la IA tarda: hilo propio, no la cola
