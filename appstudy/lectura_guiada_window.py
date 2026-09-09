"""Lectura por secciones con acompañamiento y tiempo de recuerdo final."""
import json
import math

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from . import util
from .lectura_guiada import SesionGuiada, secciones


class LecturaGuiadaWindow(Adw.Window):
    def __init__(self, parent, chapter):
        super().__init__(title="Lectura guiada", transient_for=parent, modal=True,
                         default_width=820, default_height=700)
        self.partes = secciones(json.loads(chapter["body"] or "[]"),
                               util.plain(chapter["title"]))
        self.sesion = None
        self.timer = None
        self.indice = -1
        self.sugerido = -1
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.append(Adw.HeaderBar())
        self.set_content(root)
        self.estado = Gtk.Label(label=util.plain(chapter["title"]), wrap=True,
                                css_classes=["title-2"])
        root.append(self.estado)
        self.config = Gtk.Box(spacing=10, halign=Gtk.Align.CENTER)
        self.config.append(Gtk.Label(label="Minutos de lectura:"))
        self.minutos = Gtk.SpinButton.new_with_range(1, 180, 1)
        self.minutos.set_value(max(1, min(180, chapter.get("minutes") or 10)))
        self.config.append(self.minutos)
        iniciar = Gtk.Button(label="Comenzar", css_classes=["suggested-action"])
        iniciar.set_sensitive(bool(self.partes))
        iniciar.connect("clicked", self.comenzar)
        self.config.append(iniciar)
        root.append(self.config)
        self.guia = Gtk.Label(wrap=True, label=(
            "Elige tu tiempo. Te indicaré qué sección leer y cuándo pasar a la siguiente. "
            "El último 15 % será para recordar lo aprendido. Puedes pausar o cambiar de sección. "
            "Al salir, la sesión termina; no se guarda." if self.partes else
            "Este capítulo no tiene contenido para una lectura guiada."))
        self.guia.set_margin_start(24)
        self.guia.set_margin_end(24)
        root.append(self.guia)
        self.progreso = Gtk.ProgressBar()
        root.append(self.progreso)
        self.scroll = Gtk.ScrolledWindow(vexpand=True,
                                         hscrollbar_policy=Gtk.PolicyType.NEVER)
        root.append(self.scroll)
        self.controles = Gtk.Box(spacing=10, halign=Gtk.Align.CENTER,
                                margin_bottom=16, visible=False)
        self.anterior = Gtk.Button(label="Anterior")
        self.anterior.connect("clicked", lambda *_: self.mostrar(self.indice - 1))
        self.controles.append(self.anterior)
        self.pausa = Gtk.Button(label="Pausar")
        self.pausa.connect("clicked", self.alternar)
        self.controles.append(self.pausa)
        self.siguiente = Gtk.Button(label="Siguiente")
        self.siguiente.connect("clicked", lambda *_: self.mostrar(self.indice + 1))
        self.controles.append(self.siguiente)
        root.append(self.controles)
        self.connect("close-request", self.cerrar)
        self.connect("unmap", self.ocultar)

    def comenzar(self, *_):
        self.sesion = SesionGuiada(self.partes, self.minutos.get_value_as_int())
        self.config.set_visible(False)
        self.controles.set_visible(True)
        self.sesion.iniciar()
        self.mostrar(0)
        self.actualizar()
        self.timer = GLib.timeout_add(250, self.actualizar)

    def mostrar(self, indice):
        from .reader import render_body
        self.indice = max(0, min(len(self.partes), indice))
        if self.indice == len(self.partes):
            body = [{"h": "Recuerda lo aprendido"},
                    {"p": "Sin mirar el texto, explica la idea principal con tus palabras."},
                    {"list": ["¿Qué ejemplo te ayudó a entenderla?",
                              "¿Cómo aplicarías lo que leíste?",
                              "¿Qué duda te queda? Vuelve a esa sección para aclararla."]}]
        else:
            body = self.partes[self.indice]["body"]
        contenido, _ = render_body(body)
        contenido.set_margin_start(24)
        contenido.set_margin_end(24)
        contenido.set_margin_bottom(24)
        clamp = Adw.Clamp(maximum_size=740)
        clamp.set_child(contenido)
        self.scroll.set_child(clamp)
        self.scroll.get_vadjustment().set_value(0)
        self.anterior.set_sensitive(self.indice > 0)
        self.siguiente.set_sensitive(self.indice < len(self.partes))

    def actualizar(self):
        sesion = self.sesion
        restante = math.ceil(sesion.duracion - sesion.transcurrido)
        self.progreso.set_fraction(sesion.transcurrido / sesion.duracion)
        self.estado.set_label(f"{restante // 60:02d}:{restante % 60:02d} restantes" +
                              (" · En pausa" if sesion.inicio is None else ""))
        indice = sesion.indice
        if indice != self.sugerido:
            self.sugerido = indice
            if indice < len(self.partes):
                titulo = self.partes[indice]["titulo"]
                self.guia.set_label(f"Ahora: sección {indice + 1} de {len(self.partes)} · {titulo}. "
                                    "Lee con calma y busca la idea principal. "
                                    "Usa Siguiente cuando estés listo; puedes seguir a tu ritmo.")
            else:
                self.guia.set_label("Es momento de recordar. Avanza hasta «Recuerda lo aprendido» "
                                    "y explica las ideas principales sin mirar el texto.")
        if sesion.terminado:
            sesion.pausar()
            self.estado.set_label(f"Sesión de {self.minutos.get_value_as_int()} minutos completada")
            self.guia.set_label("Terminó el tiempo. Repasa mentalmente la idea principal y un ejemplo. "
                                "Puedes volver a las secciones que necesites. "
                                "El capítulo no se ha marcado como leído automáticamente.")
            self.pausa.set_sensitive(False)
            self.timer = None
            return False
        return True

    def alternar(self, *_):
        if self.sesion.inicio is None:
            self.sesion.iniciar()
        else:
            self.sesion.pausar()
        self.pausa.set_label("Reanudar" if self.sesion.inicio is None else "Pausar")
        self.actualizar()

    def ocultar(self, *_):
        if self.sesion and not self.sesion.terminado:
            self.sesion.pausar()
            self.pausa.set_label("Reanudar")

    def cerrar(self, *_):
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None
        if self.sesion:
            self.sesion.pausar()
        return False
