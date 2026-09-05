"""Consulta de tarjetas recientes, sin controles de calificación."""
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk  # noqa: E402

from . import db, historial, util  # noqa: E402


class HistorialWindow(Adw.Window):
    def __init__(self, parent, con):
        super().__init__(title="Tarjetas recientes", transient_for=parent,
                         application=parent.get_application(), modal=True,
                         destroy_with_parent=True, default_width=620, default_height=620)
        self.con = con
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)
        header = Adw.HeaderBar()
        self.titulo = Adw.WindowTitle(title="Tarjetas recientes")
        header.set_title_widget(self.titulo)
        self.volver = Gtk.Button(icon_name="go-previous-symbolic",
                                 tooltip_text="Volver a la lista", visible=False)
        self.volver.connect("clicked", lambda *_: self.mostrar_lista())
        header.pack_start(self.volver)
        root.append(header)

        self.stack = Gtk.Stack(vexpand=True)
        root.append(self.stack)
        lista = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                        margin_start=18, margin_end=18, margin_top=12, margin_bottom=18)
        self.buscar = Gtk.SearchEntry(placeholder_text="Buscar por texto o mazo")
        self.buscar.connect("search-changed", lambda *_: self.actualizar())
        lista.append(self.buscar)
        lista.append(Gtk.Label(label="Últimas 100 tarjetas mostradas en este equipo.",
                                xalign=0, wrap=True, css_classes=["dim-label"]))
        self.filas = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                                 css_classes=["boxed-list"])
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(self.filas)
        lista.append(scroll)
        self.vacio = Gtk.Label(wrap=True, vexpand=True, css_classes=["dim-label"])
        lista.append(self.vacio)
        self.stack.add_named(lista, "lista")

        self.detalle = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16,
                              margin_start=20, margin_end=20, margin_top=16, margin_bottom=20)
        scroll_detalle = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll_detalle.set_child(self.detalle)
        self.stack.add_named(scroll_detalle, "detalle")
        teclas = Gtk.EventControllerKey()
        teclas.connect("key-pressed", self.on_key)
        self.add_controller(teclas)
        self.actualizar()

    @staticmethod
    def limpiar(box):
        while (child := box.get_first_child()) is not None:
            box.remove(child)

    def actualizar(self):
        self.limpiar(self.filas)
        tarjetas = historial.recientes(self.con, self.buscar.get_text())
        self.vacio.set_visible(not tarjetas)
        self.vacio.set_label("No hay tarjetas que coincidan con tu búsqueda." if
                             self.buscar.get_text().strip() else
                             "Aquí aparecerán las tarjetas que te muestre Bit o estudies a partir de ahora.")
        for card in tarjetas:
            frente, _ = historial.contenido(card)
            fila = Adw.ActionRow(title=util.plain(frente),
                                 subtitle=historial.subtitulo(card),
                                 title_lines=2, subtitle_lines=1, activatable=True,
                                 use_markup=False)
            fila.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
            fila.connect("activated", lambda _fila, cid=card["id"]: self.mostrar(cid))
            self.filas.append(fila)
        self.mostrar_lista()

    def mostrar_lista(self):
        self.stack.set_visible_child_name("lista")
        self.volver.set_visible(False)
        self.titulo.set_title("Tarjetas recientes")
        self.titulo.set_subtitle("")

    def mostrar(self, card_id):
        # Puede haberse borrado o editado desde otra ventana mientras consultabas.
        card = db.card_by_id(self.con, card_id)
        if card is None:
            self.actualizar()
            return
        self.limpiar(self.detalle)
        frente, respuesta = historial.contenido(card)
        self.titulo.set_title(card["deck_name"])
        self.titulo.set_subtitle("Consulta · no modifica tus repasos")
        tarjeta = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16,
                          css_classes=["as-flashcard", "as-flashcard-inner"])
        tarjeta.append(Gtk.Label(label=util.to_markup(frente), use_markup=True,
                                 wrap=True, selectable=True, xalign=0,
                                 css_classes=["as-front"]))
        if respuesta:
            tarjeta.append(Gtk.Separator())
            tarjeta.append(Gtk.Label(label=util.to_markup(respuesta), use_markup=True,
                                     wrap=True, selectable=True, xalign=0,
                                     css_classes=["as-back"]))
        if card["hint"]:
            tarjeta.append(Gtk.Label(label=util.to_markup(card["hint"]), use_markup=True,
                                     wrap=True, selectable=True, xalign=0,
                                     css_classes=["as-hint-text"]))
        self.detalle.append(tarjeta)
        self.stack.set_visible_child_name("detalle")
        self.volver.set_visible(True)

    def on_key(self, _controller, keyval, _keycode, _state):
        if keyval == Gdk.KEY_Escape:
            if self.stack.get_visible_child_name() == "detalle":
                self.mostrar_lista()
            else:
                self.close()
            return True
        return False
