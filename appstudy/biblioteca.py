"""La pestaña Biblioteca: tus libros, y cómo convertirlos en material de estudio.

Dos páginas: el estante (todos los libros de la carpeta, buscables) y el libro
abierto (sus secciones, con lo que se puede hacer con cada una). Los libros se
leen donde están; a la base solo pasa lo que apruebes.

Todo lo lento —abrir un PDF de 400 páginas, o pedirle tarjetas al modelo— va en
un hilo aparte, que si no la ventana se queda tiesa.
"""
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from . import ia, libros, util  # noqa: E402

POR_TANDA = 60          # filas que se añaden de golpe; hay más de mil libros


class Biblioteca(Adw.Bin):
    def __init__(self, ventana, con):
        super().__init__()
        self.nav = Adw.NavigationView()
        self.set_child(self.nav)
        self.push = self.nav.push
        self.pop = self.nav.pop
        self.add = self.nav.add

        self.ventana = ventana
        self.con = con
        self.estante = []           # lo último que se leyó del disco
        self.pendientes = []
        self.tanda = 0
        self.libro = None           # el libro abierto
        self.secciones = []

        self.lista = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                                 css_classes=["boxed-list"])
        for lado in ("start", "end", "bottom"):
            getattr(self.lista, f"set_margin_{lado}")(16)

        self.buscar = Gtk.SearchEntry(placeholder_text="Buscar entre tus libros…",
                                      hexpand=True)
        self.buscar.connect("search-changed", lambda *_: self.refrescar())

        cabecera = Gtk.Box(spacing=10)
        for lado, v in (("top", 12), ("bottom", 8), ("start", 16), ("end", 16)):
            getattr(cabecera, f"set_margin_{lado}")(v)
        cabecera.append(self.buscar)
        elegir = Gtk.Button(icon_name="folder-open-symbolic",
                            tooltip_text="Elegir la carpeta de los libros")
        elegir.connect("clicked", lambda *_: self.elegir_carpeta())
        cabecera.append(elegir)

        self.resumen = Gtk.Label(xalign=0, css_classes=["caption", "as-dim"])
        self.resumen.set_margin_start(18)
        self.resumen.set_margin_bottom(6)

        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        caja.append(cabecera)
        caja.append(self.resumen)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        clamp = Adw.Clamp(maximum_size=1000)
        clamp.set_child(self.lista)
        scroll.set_child(clamp)
        caja.append(scroll)

        pagina = Adw.NavigationPage(title="Biblioteca", tag="estante")
        tv = Adw.ToolbarView()
        tv.set_content(caja)
        pagina.set_child(tv)
        self.nav.add(pagina)

    # ------------------------------------------------------------- el estante

    def refrescar(self):
        """Relee la carpeta y pinta el estante, por tandas para no atascarse."""
        self.nav.pop_to_tag("estante")       # por si había un libro abierto
        raiz = libros.carpeta(self.con)
        self.estante = libros.listar(raiz, self.buscar.get_text().strip())
        while (c := self.lista.get_first_child()) is not None:
            self.lista.remove(c)

        if not raiz.is_dir():
            self.resumen.set_text(f"No encuentro la carpeta {raiz}")
            self.lista.append(Adw.ActionRow(
                title="Elige dónde tienes los libros",
                subtitle="Con el botón de la carpeta, arriba a la derecha"))
            return
        if not self.estante:
            self.resumen.set_text(str(raiz))
            self.lista.append(Adw.ActionRow(
                title="Sin resultados",
                subtitle="Prueba con otra búsqueda. Se leen PDF, EPUB, TXT y MD."))
            return

        temas = len({l["tema"] for l in self.estante})
        gigas = sum(l["tam"] for l in self.estante) / 1e9
        self.resumen.set_text(f"{len(self.estante)} libros · {temas} temas · "
                              f"{gigas:.1f} GB · {raiz}")
        self.tanda += 1
        self.pendientes = list(self.estante)
        self.llenar(self.tanda, 30)

    def llenar(self, tanda, cuantas=POR_TANDA):
        if tanda != self.tanda:
            return False                     # otra búsqueda mandó; este relleno sobra
        tema_previo = None
        for l in self.pendientes[:cuantas]:
            if l["tema"] != tema_previo:
                tema_previo = l["tema"]
                cab = Adw.ActionRow(title=util.as_label(l["tema"].upper()),
                                    css_classes=["as-level-header"])
                cab.set_activatable(False)
                self.lista.append(cab)
            self.lista.append(self.fila(l))
        del self.pendientes[:cuantas]
        if self.pendientes:
            GLib.idle_add(self.llenar, tanda)
        return False

    def fila(self, libro):
        row = Adw.ActionRow(title=util.as_label(libro["nombre"]))
        row.set_title_lines(2)
        row.set_subtitle(f"{libro['ext'].upper()} · {libro['tam'] / 1e6:.1f} MB")
        row.set_activatable(True)
        row.connect("activated", lambda *_: self.abrir(libro))
        row.add_prefix(Gtk.Label(label="📕" if libro["ext"] == "pdf" else "📗",
                                 css_classes=["as-deck-row-icon"]))
        row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        return row

    def elegir_carpeta(self):
        dlg = Gtk.FileDialog(title="¿Dónde tienes los libros?")
        dlg.select_folder(self.ventana, None, self.on_carpeta)

    def on_carpeta(self, dlg, resultado):
        try:
            carpeta = dlg.select_folder_finish(resultado)
        except GLib.Error:
            return
        if carpeta and carpeta.get_path():
            libros.set_carpeta(self.con, carpeta.get_path())
            self.refrescar()

    # -------------------------------------------------------------- el libro

    def abrir(self, libro):
        """Abre el libro: extrae el texto en segundo plano y enseña sus secciones."""
        self.libro = libro
        pagina = Adw.NavigationPage(title=util.plain(libro["nombre"])[:60])
        self.caja_libro = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        for lado, v in (("top", 18), ("bottom", 28), ("start", 20), ("end", 20)):
            getattr(self.caja_libro, f"set_margin_{lado}")(v)
        self.caja_libro.append(Gtk.Label(
            label=util.as_label(libro["nombre"]), use_markup=True, wrap=True, xalign=0,
            css_classes=["as-read-h1"]))
        self.cargando = Adw.StatusPage(title="Abriendo el libro…",
                                       description="Sacando el texto y buscando sus partes")
        self.cargando.set_vexpand(True)
        self.caja_libro.append(self.cargando)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        clamp = Adw.Clamp(maximum_size=880)
        clamp.set_child(self.caja_libro)
        scroll.set_child(clamp)
        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())
        tv.set_content(scroll)
        pagina.set_child(tv)
        self.nav.push(pagina)

        ruta = libro["ruta"]
        ia.hilo(lambda: self._leer(ruta), self.pintar_secciones, self.error_libro)

    @staticmethod
    def _leer(ruta):
        texto = libros.texto(ruta)
        return texto, libros.secciones(texto, libros.paginas(ruta))

    def error_libro(self, e):
        self.cargando.set_title("No pude abrirlo")
        self.cargando.set_description(str(e))

    def pintar_secciones(self, datos):
        texto, secciones = datos
        self.secciones = secciones
        self.caja_libro.remove(self.cargando)
        letras = sum(c.isalpha() for c in texto)
        self.caja_libro.append(Gtk.Label(
            label=f"{len(secciones)} partes · {letras // 1000} mil caracteres de texto",
            xalign=0, css_classes=["caption", "as-dim"]))
        self.caja_libro.append(Gtk.Label(
            label="De cada parte puedes sacar <b>tarjetas</b> (las revisas antes de "
                  "guardarlas) o guardarla como <b>capítulo de lectura</b>. Se guarda "
                  "en un mazo propio del tema del libro.",
            use_markup=True, wrap=True, xalign=0, css_classes=["as-read-p"]))

        lista = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                            css_classes=["boxed-list"])
        for s in secciones:
            fila = Adw.ActionRow(title=util.as_label(s["titulo"]))
            fila.set_subtitle(f"{s['hasta'] - s['desde'] + 1} páginas")
            tarjetas = Gtk.Button(label="✦ Tarjetas", valign=Gtk.Align.CENTER,
                                  css_classes=["suggested-action"],
                                  tooltip_text="Sacar tarjetas de esta parte con la IA")
            tarjetas.connect("clicked", lambda _b, s=s: self.hacer_tarjetas(s))
            fila.add_suffix(tarjetas)
            leer = Gtk.Button(label="📖 Leer", valign=Gtk.Align.CENTER,
                              tooltip_text="Guardarla como capítulo en Leer")
            leer.connect("clicked", lambda _b, s=s: self.hacer_lectura(s))
            fila.add_suffix(leer)
            lista.append(fila)
        self.caja_libro.append(lista)

    # ------------------------------------------------------------- acciones

    def _fragmento(self, seccion, maximo=9000):
        crudo = libros.texto(self.libro["ruta"], seccion["desde"], seccion["hasta"])
        return libros.limpiar_texto(crudo, maximo)

    def hacer_tarjetas(self, seccion):
        if not ia.config(self.con)["activa"]:
            self.ventana.notify_user("Activa la IA en Ajustes para sacar tarjetas")
            return
        self.ventana.notify_user(f"Leyendo «{seccion['titulo']}» y pensando tarjetas…")
        cfg = ia.config(self.con)
        libro, titulo = self.libro, seccion["titulo"]

        def trabajo():
            fragmento = self._fragmento(seccion)
            if len(fragmento) < 400:
                raise libros.LibroError("Esta parte casi no tiene texto: prueba con otra.")
            return ia.generar_desde_texto(cfg, fragmento, f"{libro['nombre']} · {titulo}", 5)

        ia.hilo(trabajo,
                lambda tarjetas: self.ventana.revisar_generadas(
                    tarjetas, libros.mazo_para(self.con, libro),
                    f"{libro['nombre']} · {titulo}", etiquetas="libro,ia"),
                lambda e: self.ventana.notify_user(f"No pude: {e}"))

    def hacer_lectura(self, seccion):
        self.ventana.notify_user(f"Guardando «{seccion['titulo']}» para leer…")
        libro = self.libro

        def trabajo():
            return self._fragmento(seccion, 30000)

        def guardar(cuerpo):
            if len(cuerpo) < 200:
                self.ventana.notify_user("Esa parte casi no tiene texto")
                return
            libros.guardar_lectura(self.con, libro, seccion, cuerpo)
            self.ventana.notify_user(f"«{seccion['titulo']}» ya está en Leer")
            self.ventana.refresh()

        ia.hilo(trabajo, guardar, lambda e: self.ventana.notify_user(f"No pude: {e}"))
