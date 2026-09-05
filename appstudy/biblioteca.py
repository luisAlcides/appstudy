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
from gi.repository import Adw, Gdk, GLib, Graphene, Gsk, Gtk, Pango  # noqa: E402

# WebKit solo hace falta para los EPUB, y no está en todas las máquinas: si
# falta, el resto de la biblioteca funciona igual y solo se avisa al abrir uno.
try:
    gi.require_version("WebKit", "6.0")
    from gi.repository import WebKit  # noqa: E402
    HAY_WEBKIT = True
except (ValueError, ImportError):      # pragma: sin WebKit instalado
    WebKit = None
    HAY_WEBKIT = False

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
        if libro["ext"] == "pdf":
            self.nav.push(Lector(self, libro).pagina)
            return
        if libro["ext"] == "epub":
            if not HAY_WEBKIT:
                self.ventana.notify_user(
                    "Para leer EPUB falta WebKitGTK: sudo apt install "
                    "gir1.2-webkit-6.0")
                return
            try:
                lector = LectorEpub(self, libro)
            except libros.LibroError as e:
                self.ventana.notify_user(str(e))
                return
            self.nav.push(lector.pagina)
            return
        self.ventana.notify_user("El lector abre PDF y EPUB; de los otros formatos "
                                 "puedo sacar tarjetas, pero no pasarte las hojas")

    def abrir_en_pagina(self, libro, pagina):
        """Abre un PDF en su página o un EPUB en su capítulo numerado."""
        if libro["ext"] == "pdf":
            lector = Lector(self, libro)
            self.nav.push(lector.pagina)
            GLib.idle_add(lector.ir, pagina)
            return
        if libro["ext"] == "epub" and HAY_WEBKIT:
            try:
                lector = LectorEpub(self, libro)
            except libros.LibroError as e:
                self.ventana.notify_user(str(e))
                return
            self.nav.push(lector.pagina)
            GLib.idle_add(lector.ir, pagina)
            return
        self.abrir(libro)


# Lo que se le inyecta al EPUB para que se lea bien: márgenes cómodos, imágenes
# que no se salgan y un ancho de línea que no obligue a mover la cabeza. No se
# tocan los colores salvo en modo noche: la maquetación del libro es suya.
CSS_EPUB = """
html { -webkit-text-size-adjust: none; }
body {
  max-width: 42em; margin: 0 auto; padding: 2.2em 1.6em 4em 1.6em;
  line-height: 1.65; font-size: %(tam)dpx;
}
img, svg, table { max-width: 100%%; height: auto; }
pre, code { white-space: pre-wrap; word-wrap: break-word; }
pre { overflow-x: auto; padding: .7em; border-radius: 6px; }
"""

CSS_EPUB_NOCHE = """
html, body { background: #1b1b1b !important; color: #ddd !important; }
* { background-color: transparent !important; border-color: #444 !important; }
a { color: #78aeed !important; }
pre, code { background: #262626 !important; }
img { filter: brightness(.85); }
"""


class LectorEpub:
    """Un EPUB abierto: capítulo a capítulo, con su índice y su modo noche.

    Un EPUB es HTML comprimido, así que lo que hace falta para leerlo bien es un
    navegador. Se descomprime una vez en la caché —para que las imágenes y las
    hojas de estilo resuelvan sus rutas relativas solas— y cada capítulo se
    carga como un archivo local. El progreso es en qué capítulo ibas.
    """

    TAMANOS = (14, 16, 18, 20, 23, 26)

    def __init__(self, biblioteca, libro):
        self.bib = biblioteca
        self.con = biblioteca.con
        self.libro = libro
        self.desde = time.time()
        self.guardar_en = None

        self.carpeta = libros.desplegar(libro["ruta"])
        self.capitulos = libros.capitulos_epub(libro["ruta"])
        self.total = len(self.capitulos)

        guardado = db.book_abrir(self.con, libro["ruta"], libro["nombre"],
                                 libro["tema"], self.total)
        self.n = min(max(1, guardado["pagina"]), self.total)
        self.marcas = db.book_marcas(self.con, libro["ruta"])

        try:
            self.tam = int(db.book_zoom(self.con, libro["ruta"]) or 0) or 18
        except (TypeError, ValueError):
            self.tam = 18
        self.noche = False

        self.vista = WebKit.WebView(vexpand=True, hexpand=True)
        ajustes = self.vista.get_settings()
        ajustes.set_enable_javascript(False)      # un libro no necesita ejecutar nada
        ajustes.set_enable_developer_extras(False)
        self.vista.connect("decide-policy", self.on_navegar)

        cuerpo = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        cuerpo.append(self.vista)
        cuerpo.append(self.barra())

        self.pagina = Adw.NavigationPage(title=util.plain(libro["nombre"])[:60])
        tv = Adw.ToolbarView()
        tv.add_top_bar(self.cabecera())
        tv.set_content(cuerpo)
        self.pagina.set_child(tv)
        self.pagina.connect("hidden", lambda *_: self.cerrar())

        teclas = Gtk.EventControllerKey()
        teclas.connect("key-pressed", self.on_key)
        self.pagina.add_controller(teclas)

        self.ir(self.n)

    # ------------------------------------------------------------ estructura

    def cabecera(self):
        cab = Adw.HeaderBar()
        self.titulo = Adw.WindowTitle(title=util.plain(self.libro["nombre"])[:48],
                                      subtitle="")
        cab.set_title_widget(self.titulo)

        indice = Gtk.MenuButton(icon_name="view-list-symbolic")
        util.tooltip_perezoso(indice, "Índice del libro")
        indice.set_popover(self.popover_indice())
        cab.pack_start(indice)

        self.btn_marca = Gtk.ToggleButton(icon_name="bookmark-new-symbolic")
        self.btn_marca.connect("toggled", self.on_marcar)
        util.tooltip_perezoso(self.btn_marca, "Marcador en este capítulo (M)")
        cab.pack_end(self.btn_marca)

        noche = Gtk.ToggleButton(icon_name="weather-clear-night-symbolic")
        noche.connect("toggled", lambda b: self.poner_noche(b.get_active()))
        util.tooltip_perezoso(noche, "Modo noche (N)")
        cab.pack_end(noche)

        tarjetas = Gtk.Button(label="✦ Tarjetas")
        util.tooltip_perezoso(tarjetas, "Generar tarjetas de este capítulo")
        tarjetas.connect("clicked", lambda *_: self.hacer_tarjetas())
        cab.pack_end(tarjetas)
        return cab

    def popover_indice(self):
        pop = Gtk.Popover()
        scroll = Gtk.ScrolledWindow()
        scroll.set_size_request(340, min(460, 44 * min(self.total, 10) + 20))
        lista = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                            css_classes=["boxed-list"])
        for i, cap in enumerate(self.capitulos, start=1):
            fila = Adw.ActionRow(title=util.as_label(cap["titulo"])[:80])
            fila.set_activatable(True)
            fila.connect("activated", lambda _f, k=i: (pop.popdown(), self.ir(k)))
            lista.append(fila)
        scroll.set_child(lista)
        pop.set_child(scroll)
        return pop

    def barra(self):
        caja = Gtk.Box(spacing=8, css_classes=["toolbar"])
        for lado, v in (("top", 6), ("bottom", 8), ("start", 12), ("end", 12)):
            getattr(caja, f"set_margin_{lado}")(v)

        anterior = Gtk.Button(icon_name="go-previous-symbolic")
        anterior.connect("clicked", lambda *_: self.ir(self.n - 1))
        util.tooltip_perezoso(anterior, "Capítulo anterior (←)")
        caja.append(anterior)

        self.etiqueta = Gtk.Label(label="", css_classes=["as-dim"], hexpand=True,
                                  ellipsize=Pango.EllipsizeMode.END, xalign=0)
        caja.append(self.etiqueta)

        siguiente = Gtk.Button(icon_name="go-next-symbolic")
        siguiente.connect("clicked", lambda *_: self.ir(self.n + 1))
        util.tooltip_perezoso(siguiente, "Capítulo siguiente (→)")
        caja.append(siguiente)

        self.avance = Gtk.ProgressBar(valign=Gtk.Align.CENTER, show_text=True,
                                      css_classes=["as-progress"])
        self.avance.set_size_request(140, -1)
        caja.append(self.avance)

        menos = Gtk.Button(icon_name="zoom-out-symbolic")
        menos.connect("clicked", lambda *_: self.letra(-1))
        util.tooltip_perezoso(menos, "Letra más pequeña (−)")
        caja.append(menos)
        mas = Gtk.Button(icon_name="zoom-in-symbolic")
        mas.connect("clicked", lambda *_: self.letra(1))
        util.tooltip_perezoso(mas, "Letra más grande (+)")
        caja.append(mas)
        return caja

    # -------------------------------------------------------------- contenido

    def estilo(self) -> str:
        css = CSS_EPUB % {"tam": self.tam}
        return css + (CSS_EPUB_NOCHE if self.noche else "")

    def aplicar_estilo(self):
        """Cambia la hoja de estilo del libro en caliente.

        Sin recargar: recargar competía con la carga del capítulo que estuviera
        en marcha y acababa enseñando el anterior. Las hojas de usuario de
        WebKit se aplican al documento que ya está delante, así que además no
        parpadea ni se pierde por dónde ibas.
        """
        gestor = self.vista.get_user_content_manager()
        gestor.remove_all_style_sheets()
        gestor.add_style_sheet(WebKit.UserStyleSheet(
            self.estilo(), WebKit.UserContentInjectedFrames.ALL_FRAMES,
            WebKit.UserStyleLevel.USER, None, None))

    def ir(self, n):
        n = max(1, min(int(n), self.total))
        self.n = n
        cap = self.capitulos[n - 1]
        destino = self.carpeta / cap["href"]
        if not destino.exists():
            self.bib.ventana.notify_user(f"Falta un capítulo del EPUB: {cap['href']}")
            return
        self.aplicar_estilo()
        self.vista.load_uri(destino.as_uri())
        self.titulo.set_subtitle(f"{n} de {self.total} · {cap['titulo'][:40]}")
        self.etiqueta.set_text(cap["titulo"])
        self.avance.set_fraction(n / self.total)
        self.avance.set_text(f"{n / self.total * 100:.0f} %")
        self.btn_marca.handler_block_by_func(self.on_marcar)
        self.btn_marca.set_active(n in self.marcas)
        self.btn_marca.handler_unblock_by_func(self.on_marcar)
        self.apuntar_luego(n)

    def poner_noche(self, si):
        self.noche = bool(si)
        self.aplicar_estilo()

    def letra(self, paso):
        opciones = list(self.TAMANOS)
        actual = min(opciones, key=lambda t: abs(t - self.tam))
        i = opciones.index(actual) + (1 if paso > 0 else -1)
        self.tam = opciones[max(0, min(len(opciones) - 1, i))]
        db.book_zoom(self.con, self.libro["ruta"], str(self.tam))
        self.aplicar_estilo()

    def on_navegar(self, _vista, decision, tipo):
        """Los enlaces dentro del libro se siguen; los de fuera, al navegador."""
        if tipo != WebKit.PolicyDecisionType.NAVIGATION_ACTION:
            return False
        uri = decision.get_navigation_action().get_request().get_uri()
        if uri.startswith("file://"):
            return False
        decision.ignore()
        Gtk.UriLauncher(uri=uri).launch(self.bib.ventana, None, None, None)
        return True

    def apuntar_luego(self, n):
        if self.guardar_en:
            GLib.source_remove(self.guardar_en)

        def guardar():
            self.guardar_en = None
            db.book_progreso(self.con, self.libro["ruta"], n)
            return False

        self.guardar_en = GLib.timeout_add(500, guardar)

    # --------------------------------------------------------------- acciones

    def on_marcar(self, _boton):
        self.marcas = db.book_marcar(self.con, self.libro["ruta"], self.n)
        self.bib.ventana.notify_user(
            f"Capítulo {self.n} marcado" if self.n in self.marcas
            else "Marcador quitado")

    def hacer_tarjetas(self):
        """Genera tarjetas del capítulo que tienes delante."""
        cap = self.capitulos[self.n - 1]
        destino = self.carpeta / cap["href"]
        try:
            crudo = destino.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            self.bib.ventana.notify_user(f"No pude leer el capítulo: {e}")
            return
        if not ia.config(self.con)["activa"]:
            self.bib.ventana.notify_user("Activa la IA en Ajustes para sacar tarjetas")
            return
        texto = libros.limpiar_texto(libros._html_a_texto(crudo), 9000)
        if len(texto) < 400:
            self.bib.ventana.notify_user("Este capítulo casi no tiene texto.")
            return
        cfg = ia.config(self.con)
        libro, titulo = self.libro, cap["titulo"]
        fuente = {"kind": "book", "ruta": libro["ruta"],
                  "page_start": self.n, "page_end": self.n,
                  "title": libro["nombre"]}
        self.bib.ventana.notify_user(f"Leyendo «{titulo[:40]}»…")

        util.hilo(
            lambda: ia.generar_desde_texto(cfg, texto, f"{libro['nombre']} · {titulo}", 5),
            lambda tarjetas: (self.bib.ventana.revisar_generadas(
                tarjetas, libros.mazo_para(self.con, libro),
                f"{libro['nombre']} · {titulo}", etiquetas="libro,ia",
                fuente=fuente),
                ia.hilo(lambda: ia.descargar(cfg))),
            lambda e: (self.bib.ventana.notify_user(f"No pude: {e}"),
                       ia.hilo(lambda: ia.descargar(cfg))),
            largo=True)          # la IA tarda: hilo propio, no la cola

    def on_key(self, _c, keyval, _code, estado):
        tecla = Gdk.keyval_name(keyval)
        if tecla in ("Left", "Page_Up", "BackSpace"):
            self.ir(self.n - 1)
            return True
        if tecla in ("Right", "Page_Down"):
            self.ir(self.n + 1)
            return True
        if tecla in ("Home", "End"):
            self.ir(1 if tecla == "Home" else self.total)
            return True
        if tecla in ("plus", "equal", "KP_Add"):
            self.letra(1)
            return True
        if tecla in ("minus", "KP_Subtract"):
            self.letra(-1)
            return True
        if tecla in ("m", "M"):
            self.btn_marca.set_active(not self.btn_marca.get_active())
            return True
        if tecla in ("n", "N"):
            self.poner_noche(not self.noche)
            return True
        return False

    def cerrar(self):
        if self.guardar_en:
            GLib.source_remove(self.guardar_en)
            self.guardar_en = None
        minutos = (time.time() - self.desde) / 60.0
        db.book_progreso(self.con, self.libro["ruta"], self.n, minutos)
        self.bib.refrescar()


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
        self.notas = []              # subrayados de esta página, en 0..1
        self.trazo = None            # el rectángulo que estás arrastrando ahora
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

    def poner_notas(self, notas):
        self.notas = list(notas)
        self.queue_draw()

    def poner_trazo(self, rect):
        self.trazo = rect
        self.queue_draw()

    def rect_en(self, x, y):
        """El subrayado que hay bajo ese punto del widget, o None."""
        w, h = self.get_width() or 1, self.get_height() or 1
        rx, ry = x / w, y / h
        # De atrás hacia delante: gana el último dibujado, que es el de encima
        for nota in reversed(self.notas):
            if nota["x0"] <= rx <= nota["x1"] and nota["y0"] <= ry <= nota["y1"]:
                return nota
        return None

    def do_measure(self, orientacion, _para):
        v = self.ancho if orientacion == Gtk.Orientation.HORIZONTAL else self.alto
        return (v, v, -1, -1)

    def do_snapshot(self, snapshot):
        if self.textura is None:
            return
        w, h = self.get_width(), self.get_height()
        rect = Graphene.Rect().init(0, 0, w, h)
        if not self.invertido:
            snapshot.append_texture(self.textura, rect)
        else:
            # |blanco − página| = página invertida, y lo hace la GPU
            snapshot.push_blend(Gsk.BlendMode.DIFFERENCE)
            snapshot.append_color(BLANCO, rect)
            snapshot.pop()
            snapshot.append_texture(self.textura, rect)
            snapshot.pop()

        # Los subrayados van encima, translúcidos: se lee el texto por debajo.
        # Se multiplica en vez de mezclar para que el papel blanco tome el color
        # y las letras negras sigan siendo negras, como un rotulador de verdad.
        for nota in self.notas:
            self._pintar_marca(snapshot, nota, w, h,
                               db.COLORES_NOTA.get(nota["color"],
                                                   db.COLORES_NOTA["amarillo"]),
                               0.34 if not nota.get("nota") else 0.46)
            if nota.get("nota"):
                # Una pestañita a la izquierda avisa de que hay algo escrito
                self._pestaña(snapshot, nota, w, h)
        if self.trazo:
            self._pintar_marca(snapshot, self.trazo, w, h,
                               db.COLORES_NOTA["amarillo"], 0.28)

    @staticmethod
    def _pintar_marca(snapshot, r, w, h, color, alfa):
        x0, x1 = sorted((r["x0"] * w, r["x1"] * w))
        y0, y1 = sorted((r["y0"] * h, r["y1"] * h))
        if x1 - x0 < 1 or y1 - y0 < 1:
            return
        snapshot.append_color(
            Gdk.RGBA(red=color[0], green=color[1], blue=color[2], alpha=alfa),
            Graphene.Rect().init(x0, y0, x1 - x0, y1 - y0))

    @staticmethod
    def _pestaña(snapshot, r, w, h):
        y0, y1 = sorted((r["y0"] * h, r["y1"] * h))
        x = max(0, r["x0"] * w - 6)
        snapshot.append_color(
            Gdk.RGBA(red=0.20, green=0.40, blue=0.85, alpha=0.95),
            Graphene.Rect().init(x, y0, 3, max(8, y1 - y0)))


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
        self.notas = []                  # los subrayados de la página actual
        self.subrayando = False          # el modo rotulador, con la tecla S
        self.color_nota = "amarillo"

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

        # Arrastrar sobre la hoja subraya, pero solo con el rotulador activado:
        # si no, cualquier arrastre despistado dejaría una marca.
        arrastre = Gtk.GestureDrag()
        arrastre.connect("drag-begin", self.on_arrastre_inicio)
        arrastre.connect("drag-update", self.on_arrastre)
        arrastre.connect("drag-end", self.on_arrastre_fin)
        self.hoja.add_controller(arrastre)

        toque = Gtk.GestureClick()
        toque.connect("released", self.on_clic_hoja)
        self.hoja.add_controller(toque)

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

        self.btn_subrayar = Gtk.ToggleButton(icon_name="edit-select-all-symbolic")
        self.btn_subrayar.connect("toggled", self.on_toggle_subrayar)
        util.tooltip_perezoso(self.btn_subrayar,
                              "Rotulador: arrastra sobre el texto (S)")
        caja.append(self.btn_subrayar)

        self.btn_notas = Gtk.MenuButton(icon_name="view-list-bullet-symbolic")
        self.btn_notas.set_popover(self.panel_notas())
        self.btn_notas.connect("notify::active", lambda *_: (
            self.btn_notas.set_popover(self.panel_notas())
            if self.btn_notas.get_active() else None))
        caja.append(self.btn_notas)
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
        self.cargar_notas()
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

    # ------------------------------------------------- subrayados y notas

    def cargar_notas(self):
        """Trae los subrayados de la página actual y los pinta en la hoja."""
        self.notas = db.notas_de(self.con, self.libro["ruta"], self.n)
        self.hoja.poner_notas(self.notas)
        if hasattr(self, "btn_subrayar"):
            total = db.notas_de(self.con, self.libro["ruta"])
            self.btn_notas.set_tooltip_text(
                f"{len(total)} subrayados en este libro" if total
                else "Todavía no has subrayado nada")

    def _relativo(self, x, y):
        w = self.hoja.get_width() or 1
        h = self.hoja.get_height() or 1
        return min(1.0, max(0.0, x / w)), min(1.0, max(0.0, y / h))

    def alternar_subrayado(self, activo=None):
        self.subrayando = (not self.subrayando) if activo is None else bool(activo)
        self.btn_subrayar.handler_block_by_func(self.on_toggle_subrayar)
        self.btn_subrayar.set_active(self.subrayando)
        self.btn_subrayar.handler_unblock_by_func(self.on_toggle_subrayar)
        self.hoja.set_cursor_from_name("crosshair" if self.subrayando else None)
        if self.subrayando:
            self.bib.ventana.notify_user(
                "Rotulador activado: arrastra sobre el texto. S para salir.")

    def on_toggle_subrayar(self, boton):
        self.alternar_subrayado(boton.get_active())

    def on_arrastre_inicio(self, gesto, x, y):
        if not self.subrayando:
            return
        self._ancla = self._relativo(x, y)

    def on_arrastre(self, gesto, dx, dy):
        if not self.subrayando or not getattr(self, "_ancla", None):
            return
        ok, x0, y0 = gesto.get_start_point()
        if not ok:
            return
        x1, y1 = self._relativo(x0 + dx, y0 + dy)
        self.hoja.poner_trazo({"x0": self._ancla[0], "y0": self._ancla[1],
                               "x1": x1, "y1": y1})

    def on_arrastre_fin(self, gesto, dx, dy):
        if not self.subrayando or not getattr(self, "_ancla", None):
            return
        self.hoja.poner_trazo(None)
        ancla, self._ancla = self._ancla, None
        ok, x0, y0 = gesto.get_start_point()
        if not ok:
            return
        x1, y1 = self._relativo(x0 + dx, y0 + dy)
        rect = (ancla[0], ancla[1], x1, y1)
        # Un arrastre de dos píxeles es un clic torpe, no un subrayado
        if abs(rect[2] - rect[0]) < 0.02 or abs(rect[3] - rect[1]) < 0.008:
            return
        texto = libros.texto_region(self.libro["ruta"], self.n, rect, self.tam_pt)
        nota_id = db.nota_add(self.con, self.libro["ruta"], self.n, rect,
                              texto=texto, color=self.color_nota)
        self.cargar_notas()
        aviso = Adw.Toast(title=util.plain(texto)[:70] if texto else "Subrayado",
                          timeout=4)
        aviso.set_button_label("Anotar")
        aviso.connect("button-clicked", lambda *_: self.abrir_nota(nota_id))
        self.bib.ventana.toast.add_toast(aviso)

    def on_clic_hoja(self, gesto, _n, x, y):
        """Tocar un subrayado abre su ficha; tocar el papel no hace nada."""
        if self.subrayando:
            return
        nota = self.hoja.rect_en(x, y)
        if nota:
            self.abrir_nota(nota["id"], ancla=(x, y))

    def abrir_nota(self, nota_id, ancla=None):
        """La ficha de un subrayado: lo que dice, tu comentario y qué hacer con él."""
        nota = next((n for n in db.notas_de(self.con, self.libro["ruta"])
                     if n["id"] == nota_id), None)
        if not nota:
            return
        pop = Gtk.Popover(autohide=True)
        pop.set_parent(self.hoja)
        if ancla:
            rect = Gdk.Rectangle()
            rect.x, rect.y, rect.width, rect.height = int(ancla[0]), int(ancla[1]), 1, 1
            pop.set_pointing_to(rect)
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for lado in ("top", "bottom", "start", "end"):
            getattr(caja, f"set_margin_{lado}")(12)
        caja.set_size_request(360, -1)

        if nota["texto"]:
            cita = Gtk.Label(label=f"«{util.plain(nota['texto'])[:400]}»",
                             wrap=True, xalign=0, css_classes=["as-dim"])
            caja.append(cita)
        else:
            caja.append(Gtk.Label(label="Sin texto debajo (una figura, o un escaneo)",
                                  xalign=0, css_classes=["as-dim"]))

        entrada = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD, top_margin=6,
                               bottom_margin=6, left_margin=8, right_margin=8)
        entrada.get_buffer().set_text(nota["nota"])
        marco = Gtk.Frame()
        marco.set_child(entrada)
        marco.set_size_request(-1, 90)
        caja.append(Gtk.Label(label="Tu nota", xalign=0, css_classes=["heading"]))
        caja.append(marco)

        colores = Gtk.Box(spacing=6)
        for nombre, rgb in db.COLORES_NOTA.items():
            b = Gtk.Button(css_classes=["circular"], width_request=26, height_request=26)
            css = Gtk.CssProvider()
            css.load_from_data(
                f"button {{ background: rgb({int(rgb[0]*255)},{int(rgb[1]*255)},"
                f"{int(rgb[2]*255)}); }}".encode())
            b.get_style_context().add_provider(css,
                                               Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            b.connect("clicked", lambda _b, c=nombre: self.cambiar_color(nota_id, c))
            colores.append(b)
        caja.append(colores)

        fila = Gtk.Box(spacing=6, homogeneous=True)
        tarjeta = Gtk.Button(label="✦ Hacer tarjeta")
        tarjeta.connect("clicked", lambda *_: (self.guardar_nota(nota_id, entrada),
                                               pop.popdown(),
                                               self.tarjeta_de_nota(nota_id)))
        fila.append(tarjeta)
        borrar = Gtk.Button(label="Borrar", css_classes=["destructive-action"])
        borrar.connect("clicked", lambda *_: (db.nota_borrar(self.con, nota_id),
                                              self.cargar_notas(), pop.popdown()))
        fila.append(borrar)
        guardar = Gtk.Button(label="Guardar", css_classes=["suggested-action"])
        guardar.connect("clicked", lambda *_: (self.guardar_nota(nota_id, entrada),
                                               pop.popdown()))
        fila.append(guardar)
        caja.append(fila)

        pop.set_child(caja)
        pop.connect("closed", lambda *_: pop.unparent())
        pop.popup()

    def guardar_nota(self, nota_id, vista):
        buf = vista.get_buffer()
        texto = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        db.nota_editar(self.con, nota_id, nota=texto.strip())
        self.cargar_notas()

    def cambiar_color(self, nota_id, color):
        self.color_nota = color
        db.nota_editar(self.con, nota_id, color=color)
        self.cargar_notas()

    def tarjeta_de_nota(self, nota_id):
        """Abre el editor con lo subrayado ya puesto: es el paso natural."""
        nota = next((n for n in db.notas_de(self.con, self.libro["ruta"])
                     if n["id"] == nota_id), None)
        if not nota:
            return
        mazo = libros.mazo_para(self.con, self.libro)
        self.bib.ventana.editor_desde_nota(nota, mazo, self.libro)

    def panel_notas(self):
        """La lista de todo lo subrayado en este libro, para repasarlo de un vistazo."""
        pop = Gtk.Popover()
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for lado in ("top", "bottom", "start", "end"):
            getattr(caja, f"set_margin_{lado}")(10)
        caja.set_size_request(430, -1)
        todas = db.notas_de(self.con, self.libro["ruta"])
        caja.append(Gtk.Label(
            label=f"{len(todas)} subrayados" if todas else "Todavía no has subrayado nada",
            xalign=0, css_classes=["heading"]))
        if not todas:
            caja.append(Gtk.Label(
                label="Pulsa S o el rotulador de arriba y arrastra sobre el texto.",
                xalign=0, wrap=True, css_classes=["as-dim"]))
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_size_request(-1, min(420, 60 + 66 * min(len(todas), 6)))
        lista = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                            css_classes=["boxed-list"])
        for nota in todas:
            resumen = util.plain(nota["texto"])[:90] or "(sin texto)"
            fila = Adw.ActionRow(title=util.as_label(resumen),
                                 subtitle=f"pág. {nota['pagina']}"
                                          + (f" · {util.plain(nota['nota'])[:60]}"
                                             if nota["nota"] else ""))
            fila.set_subtitle_lines(2)
            fila.set_activatable(True)
            fila.connect("activated",
                         lambda _f, n=nota: (pop.popdown(), self.ir(n["pagina"])))
            lista.append(fila)
        scroll.set_child(lista)
        caja.append(scroll)
        if todas:
            exportar = Gtk.Button(label="Copiar todo en Markdown")
            exportar.connect("clicked", lambda *_: self.copiar_notas(todas))
            caja.append(exportar)
        pop.set_child(caja)
        return pop

    def copiar_notas(self, notas):
        """Todo lo subrayado, en Markdown, listo para pegarlo donde quieras."""
        lineas = [f"# {util.plain(self.libro['nombre'])}", ""]
        for n in notas:
            lineas.append(f"**pág. {n['pagina']}** — {util.plain(n['texto']) or '(sin texto)'}")
            if n["nota"]:
                lineas.append(f"> {util.plain(n['nota'])}")
            lineas.append("")
        self.pagina.get_clipboard().set("\n".join(lineas))
        self.bib.ventana.notify_user(f"{len(notas)} subrayados copiados")

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
        if tecla in ("s", "S"):
            self.alternar_subrayado()
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
                  lambda tarjetas: (self.bib.ventana.revisar_generadas(
                      tarjetas, libros.mazo_para(self.con, libro),
                      f"{libro['nombre']} · págs. {desde}–{hasta}", etiquetas="libro,ia",
                      fuente={"kind": "book", "ruta": libro["ruta"],
                              "page_start": desde, "page_end": hasta,
                              "title": libro["nombre"]}),
                      ia.hilo(lambda: ia.descargar(cfg))),
                  lambda e: (self.bib.ventana.notify_user(f"No pude: {e}"),
                             ia.hilo(lambda: ia.descargar(cfg))),
                  largo=True)          # la IA tarda: hilo propio, no la cola
