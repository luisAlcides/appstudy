"""La pantalla de Novedades: lo que ha llegado solo y espera tu visto bueno.

Cada elemento enseña de dónde sale, con qué licencia y por qué se te propone,
antes de que decidas. Aprobar contenido a ciegas sería lo mismo que no
aprobarlo.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from . import bandeja, catalogo, cosecha, db, util  # noqa: E402

MAX_VISTA_PREVIA = 1500


class FilaNovedad(Adw.PreferencesGroup):
    """Un documento en espera, con sus tarjetas propuestas."""

    def __init__(self, pagina, fila):
        super().__init__()
        self.pagina, self.fila, self.casillas = pagina, fila, []
        f = catalogo._POR_ID.get(fila["provider"])
        self.motivo = fila["motivo"] or "Propuesto por la cosecha del día"
        self.licencia = fila["license"] or "Consultar la fuente"
        self.set_title(util.as_label(fila["title"]))
        self.set_description(
            f"{f['nombre'] if f else fila['provider']} · {fila['deck_name']} · "
            f"{self.motivo}\n{self.licencia}")

        texto = Adw.ExpanderRow(title="Ver el texto")
        cuerpo = Gtk.Label(label=fila["text"][:MAX_VISTA_PREVIA], wrap=True, xalign=0,
                           margin_top=8, margin_bottom=8, margin_start=12, margin_end=12,
                           selectable=True)
        texto.add_row(cuerpo)
        self.add(texto)

        import json
        propuestas = json.loads(fila["cards"] or "[]")
        for t in propuestas:
            row = Adw.ActionRow(title=util.as_label(t.get("front", "")),
                                subtitle=util.as_label(t.get("back", "")))
            casilla = Gtk.CheckButton(active=True, valign=Gtk.Align.CENTER)
            row.add_prefix(casilla)
            self.casillas.append(casilla)
            self.add(row)
        if not propuestas:
            self.add(Adw.ActionRow(
                title="Sin tarjetas propuestas",
                subtitle="Enciende la IA local en Ajustes y sácalas desde el capítulo"))

        botones = Gtk.Box(spacing=8, halign=Gtk.Align.END, margin_top=8)
        descartar = Gtk.Button(label="Descartar")
        descartar.connect("clicked", lambda *_: self.descartar())
        aceptar = Gtk.Button(label="Aceptar", css_classes=["suggested-action"])
        aceptar.connect("clicked", lambda *_: self.aceptar())
        botones.append(descartar)
        botones.append(aceptar)
        self.add(botones)

    def aceptar(self):
        elegidas = [i for i, c in enumerate(self.casillas) if c.get_active()]
        try:
            capitulo = bandeja.aceptar(self.pagina.con, self.fila["id"], cards=elegidas)
        except Exception as e:
            self.pagina.notificar(f"No se pudo aceptar: {e}")
            return
        self.pagina.notificar(f"«{capitulo['title']}» añadido a {self.fila['deck_name']}")
        self.pagina.recargar()

    def descartar(self):
        bandeja.descartar(self.pagina.con, self.fila["id"])
        self.pagina.recargar()


class PaginaBandeja(Gtk.Box):
    """La sección entera: la lista, el mensaje de vacío y «Buscar ahora»."""

    def __init__(self, con, notificar=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                         margin_top=18, margin_bottom=18,
                         margin_start=18, margin_end=18)
        self.con = con
        self.notificar = notificar or (lambda _t: None)
        self.filas = []

        cabecera = Gtk.Box(spacing=8)
        cabecera.append(Gtk.Label(label="Contenido nuevo esperando tu visto bueno",
                                  xalign=0, hexpand=True, css_classes=["heading"]))
        self.boton_buscar = Gtk.Button(label="Buscar ahora")
        self.boton_buscar.connect("clicked", lambda *_: self.buscar_ahora())
        cabecera.append(self.boton_buscar)
        self.append(cabecera)

        self.vacio = Adw.StatusPage(
            title="No hay nada pendiente",
            description="Al abrir la aplicación se busca una lectura nueva al día. "
                        "Puedes apagarlo en Ajustes › Fuentes.",
            icon_name="folder-download-symbolic", vexpand=True)
        self.append(self.vacio)

        self.lista = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        scroll = Gtk.ScrolledWindow(vexpand=True, child=self.lista)
        self.scroll = scroll
        self.append(scroll)
        self.recargar()

    def recargar(self):
        for fila in self.filas:
            self.lista.remove(fila)
        self.filas = [FilaNovedad(self, f) for f in bandeja.pendientes(self.con)]
        for fila in self.filas:
            self.lista.append(fila)
        self.vacio.set_visible(not self.filas)
        self.scroll.set_visible(bool(self.filas))

    def buscar_ahora(self):
        """A mano, ignorando la ración del día: para probarlo cuando quieras."""
        self.boton_buscar.set_sensitive(False)

        def trabajo():
            otra = db.connect()          # una conexión de SQLite es de su hilo
            try:
                return len(cosecha.cosechar(otra))
            finally:
                otra.close()

        def listo(cuantos):
            self.boton_buscar.set_sensitive(True)
            self.notificar(f"{cuantos} novedad(es)" if cuantos
                           else "No se encontró nada nuevo esta vez")
            self.recargar()

        def fallo(error):
            self.boton_buscar.set_sensitive(True)
            self.notificar(f"No se pudo buscar: {error}")

        util.hilo(trabajo, listo, fallo, largo=True)
