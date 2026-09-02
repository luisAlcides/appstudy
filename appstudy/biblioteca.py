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
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from . import db, ia, libros, util  # noqa: E402

ANCHO_PORTADA = 108           # ancho de las portadas de «seguir leyendo»
MAX_POR_ESTANTE = 240         # libros que se pintan al desplegar una carpeta
ZOOMS = (700, 900, 1150, 1450, 1800, 2200)


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

        self.columna = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        for lado, v in (("top", 6), ("bottom", 28), ("start", 16), ("end", 16)):
            getattr(self.columna, f"set_margin_{lado}")(v)

        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        caja.append(cabecera)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        clamp = Adw.Clamp(maximum_size=1040)
        clamp.set_child(self.columna)
        scroll.set_child(clamp)
        caja.append(scroll)

        pagina = Adw.NavigationPage(title="Biblioteca", tag="estante")
        tv = Adw.ToolbarView()
        tv.set_content(caja)
        pagina.set_child(tv)
        self.nav.add(pagina)

    # ==================================================== el estante

    def refrescar(self):
        self.nav.pop_to_tag("estante")
        self.estante = libros.listar(libros.carpeta(self.con))
        self.guardados = db.books_todos(self.con)
        self.pintar()

    def pintar(self):
        """Rehace el estante: lo que sigues leyendo y tus carpetas."""
        while (c := self.columna.get_first_child()) is not None:
            self.columna.remove(c)
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
            return

        if filtro:
            palabras = filtro.split()
            hallados = [l for l in self.estante
                        if all(p in f"{l['nombre']} {l['tema']}".lower() for p in palabras)]
            self.columna.append(self.titulillo(
                f"{len(hallados)} resultados para «{filtro}»"))
            lista = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                                css_classes=["boxed-list"])
            for l in hallados[:200]:
                lista.append(self.fila_libro(l))
            self.columna.append(lista)
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
            for l in del_tema[:MAX_POR_ESTANTE]:
                fila.add_row(self.fila_libro(l))

        fila.connect("notify::expanded", desplegar)
        return fila

    def fila_libro(self, libro):
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

        if libro["ext"] == "pdf":
            miniatura = Gtk.Picture(width_request=34, height_request=46,
                                    content_fit=Gtk.ContentFit.CONTAIN)
            fila.add_prefix(miniatura)
            self.poner_portada(miniatura, libro["ruta"], 90)
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
        """Dibuja la portada aparte; la caché hace que la próxima vez vuele."""
        util.hilo(lambda: libros.portada(ruta, ancho),
                  lambda png: imagen.set_filename(png) if png else None,
                  lambda e: None)

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


class Lector:
    """El PDF abierto: una página cada vez, con zoom, teclado y avance guardado."""

    def __init__(self, biblioteca, libro):
        self.bib = biblioteca
        self.con = biblioteca.con
        self.libro = libro
        self.zoom = 2                      # índice dentro de ZOOMS
        self.desde = time.time()           # para contar los minutos leídos
        self.pendiente = None              # (página, ancho) que se está dibujando

        total = libros.paginas(libro["ruta"])
        guardado = db.book_abrir(self.con, libro["ruta"], libro["nombre"],
                                 libro["tema"], total)
        self.total = total or guardado["paginas"] or 1
        self.n = min(max(1, guardado["pagina"]), self.total)

        self.imagen = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, vexpand=True)
        self.scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self.scroll.set_child(self.imagen)

        cuerpo = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        cuerpo.append(self.scroll)
        cuerpo.append(self.barra())

        self.pagina = Adw.NavigationPage(title=util.plain(libro["nombre"])[:60])
        tv = Adw.ToolbarView()
        cab = Adw.HeaderBar()
        self.titulo = Adw.WindowTitle(title=util.plain(libro["nombre"])[:48], subtitle="")
        cab.set_title_widget(self.titulo)
        fav = Gtk.ToggleButton(icon_name="starred-symbolic", tooltip_text="Favorito",
                               active=bool(guardado.get("favorito")))
        fav.connect("toggled", lambda b: db.book_favorito(self.con, libro["ruta"],
                                                          b.get_active()))
        cab.pack_end(fav)
        tv.add_top_bar(cab)
        tv.set_content(cuerpo)
        self.pagina.set_child(tv)
        self.pagina.connect("hidden", lambda *_: self.cerrar())

        teclas = Gtk.EventControllerKey()
        teclas.connect("key-pressed", self.on_key)
        self.pagina.add_controller(teclas)

        self.ir(self.n)

    # ------------------------------------------------------------- barra

    def barra(self):
        caja = Gtk.Box(spacing=8, css_classes=["toolbar"])
        for lado, v in (("top", 6), ("bottom", 8), ("start", 12), ("end", 12)):
            getattr(caja, f"set_margin_{lado}")(v)

        anterior = Gtk.Button(icon_name="go-previous-symbolic",
                              tooltip_text="Anterior (←)")
        anterior.connect("clicked", lambda *_: self.ir(self.n - 1))
        caja.append(anterior)

        self.caja_pagina = Gtk.Entry(width_chars=4, xalign=0.5,
                                     tooltip_text="Ir a una página")
        self.caja_pagina.connect("activate", self.on_saltar)
        caja.append(self.caja_pagina)
        caja.append(Gtk.Label(label=f"de {self.total}", css_classes=["as-dim"]))

        siguiente = Gtk.Button(icon_name="go-next-symbolic",
                               tooltip_text="Siguiente (→)")
        siguiente.connect("clicked", lambda *_: self.ir(self.n + 1))
        caja.append(siguiente)

        self.avance = Gtk.ProgressBar(hexpand=True, valign=Gtk.Align.CENTER,
                                      show_text=True, css_classes=["as-progress"])
        caja.append(self.avance)

        menos = Gtk.Button(icon_name="zoom-out-symbolic", tooltip_text="Alejar (−)")
        menos.connect("clicked", lambda *_: self.cambiar_zoom(-1))
        caja.append(menos)
        mas = Gtk.Button(icon_name="zoom-in-symbolic", tooltip_text="Acercar (+)")
        mas.connect("clicked", lambda *_: self.cambiar_zoom(1))
        caja.append(mas)

        tarjetas = Gtk.Button(label="✦ Tarjetas",
                              tooltip_text="Sacar tarjetas de estas páginas con la IA")
        tarjetas.connect("clicked", lambda *_: self.hacer_tarjetas())
        caja.append(tarjetas)
        return caja

    # ------------------------------------------------------------ páginas

    def ir(self, n):
        n = max(1, min(int(n), self.total))
        self.n = n
        self.caja_pagina.set_text(str(n))
        self.avance.set_fraction(n / self.total)
        self.avance.set_text(f"{n / self.total * 100:.0f} %")
        self.titulo.set_subtitle(f"página {n} de {self.total}")
        db.book_progreso(self.con, self.libro["ruta"], n)

        ruta, ancho = self.libro["ruta"], ZOOMS[self.zoom]
        self.pendiente = (n, ancho)
        util.hilo(lambda: (n, ancho, libros.render(ruta, n, ancho)),
                  self.pintar, self.fallo)

    def pintar(self, datos):
        n, ancho, png = datos
        if self.pendiente != (n, ancho):
            return                       # llegó tarde: ya ibas por otra página
        self.imagen.set_filename(png)
        self.scroll.get_vadjustment().set_value(0)
        if n < self.total:               # la siguiente, mientras lees esta
            ruta = self.libro["ruta"]
            util.hilo(lambda: libros.render(ruta, n + 1, ancho),
                      lambda *_: None, lambda e: None)

    def fallo(self, e):
        self.bib.ventana.notify_user(str(e))

    def cambiar_zoom(self, paso):
        nuevo = max(0, min(len(ZOOMS) - 1, self.zoom + paso))
        if nuevo != self.zoom:
            self.zoom = nuevo
            self.ir(self.n)

    def on_saltar(self, entrada):
        try:
            self.ir(int(entrada.get_text().strip()))
        except ValueError:
            self.caja_pagina.set_text(str(self.n))

    def on_key(self, _c, keyval, _code, _estado):
        tecla = Gdk.keyval_name(keyval)
        saltos = {"Left": -1, "Page_Up": -1, "Up": -1,
                  "Right": 1, "Page_Down": 1, "Down": 1, "space": 1}
        if tecla in saltos:
            self.ir(self.n + saltos[tecla])
            return True
        if tecla in ("Home", "End"):
            self.ir(1 if tecla == "Home" else self.total)
            return True
        if tecla in ("plus", "equal", "KP_Add"):
            self.cambiar_zoom(1)
            return True
        if tecla in ("minus", "KP_Subtract"):
            self.cambiar_zoom(-1)
            return True
        return False

    def cerrar(self):
        """Al salir se anotan los minutos leídos y se repinta el estante."""
        minutos = min(180.0, (time.time() - self.desde) / 60)
        db.book_progreso(self.con, self.libro["ruta"], self.n, minutos)
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
                  lambda e: self.bib.ventana.notify_user(f"No pude: {e}"))
