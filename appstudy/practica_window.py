"""Catálogo y resolución paso a paso de ejercicios prácticos."""
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from .practica import SesionPractica, catalogo
from . import util
from .reader import render_body


class PracticaWindow(Adw.Window):
    def __init__(self, parent, con):
        super().__init__(title="Ejercicios prácticos", transient_for=parent,
                         modal=True, default_width=780, default_height=720)
        self.con = con
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(Adw.HeaderBar())
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        clamp = Adw.Clamp(maximum_size=720)
        self.caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16,
                            margin_top=20, margin_bottom=24, margin_start=20, margin_end=20)
        clamp.set_child(self.caja)
        scroll.set_child(clamp)
        root.append(scroll)
        self.set_content(root)
        self.catalogo()

    def limpiar(self):
        while child := self.caja.get_first_child():
            self.caja.remove(child)

    def texto(self, texto, clase=None):
        label = Gtk.Label(label=util.to_markup(texto), use_markup=True,
                          xalign=0, wrap=True, selectable=True)
        label.set_wrap_mode(2)
        if clase:
            label.add_css_class(clase)
        self.caja.append(label)
        return label

    def bloques(self, bloques):
        widget, _ = render_body(bloques)
        self.caja.append(widget)

    def boton(self, texto, callback, sugerido=False):
        boton = Gtk.Button()
        boton.set_child(Gtk.Label(label=texto, wrap=True))
        if sugerido:
            boton.add_css_class("suggested-action")
        boton.connect("clicked", callback)
        self.caja.append(boton)
        return boton

    def catalogo(self, *_):
        self.limpiar()
        self.texto("Aprende resolviendo un caso", "title-1")
        self.texto("Elige una situación, razona cada paso y consulta pistas cuando las necesites. "
                   "Tu avance se guarda en este equipo. Puedes cerrar y continuar después.")
        for caso in catalogo():
            sesion = SesionPractica(self.con, caso)
            estado = ("Completado · ver solución" if sesion.terminada else
                      f"Continuar · {sesion.indice}/{len(caso['pasos'])} pasos" if sesion.estado
                      else "Comenzar")
            self.texto(caso["titulo"], "title-3")
            self.texto(f"{caso['tema']} · {caso['nivel']} · {caso['minutos']} min")
            self.boton(estado, lambda _, c=caso: self.abrir(c))

    def abrir(self, caso):
        self.sesion = SesionPractica(self.con, caso)
        self.mostrar()

    def mostrar(self, *_):
        self.limpiar()
        self.boton("← Volver a los ejercicios", self.catalogo)
        caso = self.sesion.caso
        self.texto(caso["titulo"], "title-1")
        if self.sesion.terminada:
            self.final()
            return
        self.bloques(caso.get("contexto_bloques", [{"p": caso["contexto"]}]))
        indice = self.sesion.indice
        paso = caso["pasos"][indice]
        dato = self.sesion.dato()
        self.texto(f"Paso {indice + 1} de {len(caso['pasos'])} · {paso['titulo']}", "title-3")
        self.texto(paso["pregunta"])
        if paso.get("formula"):
            self.bloques([{"math": paso["formula"]}])
        self.opciones = []
        self.entrada = None
        if paso.get("tipo") == "numero":
            self.texto("Escribe tu respuesta sin unidades. Se aceptan decimales con coma o punto y fracciones como 5/6.", "caption")
            self.entrada = Gtk.Entry(placeholder_text="Tu respuesta", max_length=100)
            if dato["intentos"]:
                self.entrada.set_text(dato["intentos"][-1])
            self.entrada.connect("activate", self.comprobar_numero)
            self.caja.append(self.entrada)
            self.comprobar = self.boton("Comprobar respuesta", self.comprobar_numero, True)
        for i, opcion in enumerate(paso.get("opciones", [])):
            boton = self.boton(opcion, lambda _, n=i: self.responder(n))
            boton.set_sensitive(i not in dato["intentos"])
            self.opciones.append(boton)
        self.feedback = self.texto("La respuesta anterior no es correcta. Revisa los datos o pide una pista."
                                   if dato["intentos"] else "Responde para comprobar este paso.")
        self.pistas = self.texto("\n\n".join(paso["pistas"][:dato["pistas"]]))
        self.pista_btn = self.boton("Dame una pista", self.pista)
        self.pista_btn.set_sensitive(dato["pistas"] < len(paso["pistas"]))
        self.siguiente = self.boton("Ver resumen" if indice + 1 == len(caso["pasos"])
                                   else "Siguiente paso", self.mostrar, True)
        self.siguiente.set_sensitive(False)

    def comprobar_numero(self, *_):
        if self.entrada.get_sensitive():
            self.responder(self.entrada.get_text())

    def responder(self, opcion):
        paso = self.sesion.caso["pasos"][self.sesion.indice]
        try:
            correcto = self.sesion.responder(opcion)
        except ValueError as exc:
            self.feedback.set_text(str(exc))
            return
        if correcto:
            self.feedback.set_markup(util.to_markup("Correcto. " + paso["explicacion"]))
            for boton in self.opciones:
                boton.set_sensitive(False)
            self.pista_btn.set_sensitive(False)
            self.siguiente.set_sensitive(True)
            if self.entrada is not None:
                self.entrada.set_sensitive(False)
                self.comprobar.set_sensitive(False)
        else:
            if self.entrada is None:
                self.opciones[opcion].set_sensitive(False)
            self.feedback.set_text("Todavía no es correcto. Revisa las operaciones o pide una pista.")

    def pista(self, *_):
        pistas = self.sesion.pista()
        self.pistas.set_markup(util.to_markup("\n\n".join(pistas)))
        self.pista_btn.set_sensitive(len(pistas) < len(self.sesion.caso["pasos"][self.sesion.indice]["pistas"]))

    def final(self):
        resumen = self.sesion.resumen()
        self.texto("Ejercicio completado", "title-2")
        self.texto(f"{resumen['resueltos']} pasos resueltos · {resumen['sin_ayuda']} al primer intento sin pistas "
                   f"· {resumen['pistas']} pistas consultadas")
        self.texto("Solución explicada", "title-3")
        for paso in self.sesion.caso["pasos"]:
            self.texto(paso["titulo"], "heading")
            self.texto(paso["explicacion"])
        self.bloques(self.sesion.caso.get("solucion_bloques", [{"p": self.sesion.caso["solucion"]}]))
        self.boton("Practicar de nuevo", self.reiniciar)

    def reiniciar(self, *_):
        self.sesion.reiniciar()
        self.mostrar()
