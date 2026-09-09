"""Agenda, ruta y cuaderno personal del plan de desarrollo."""
from datetime import date
import math
import sqlite3

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from . import db, potencial as plan


def texto(label, titulo=False):
    return Gtk.Label(label=label, wrap=True, xalign=0,
                     css_classes=["title-2"] if titulo else [])


def boton(label, callback):
    b = Gtk.Button(label=label, halign=Gtk.Align.START)
    b.connect("clicked", callback)
    return b


def campo(box, nombre, valor=""):
    box.append(texto(nombre))
    vista = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR,
                         top_margin=8, bottom_margin=8, left_margin=8, right_margin=8)
    vista.get_buffer().set_text(valor)
    scroll = Gtk.ScrolledWindow(min_content_height=85,
                                hscrollbar_policy=Gtk.PolicyType.NEVER)
    scroll.set_child(vista)
    box.append(scroll)
    return vista.get_buffer()


def contenido(buffer):
    return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)


class PotencialWindow(Adw.Window):
    def __init__(self, parent):
        super().__init__(title="Mi plan 2026–2028", transient_for=parent,
                         modal=True, default_width=900, default_height=760)
        self.parent = parent
        self.con = parent.con
        self.hoy = date.today()
        self.timer = None
        self.reloj = None
        self.editor_id = None
        self.editor_tipo = None
        self.buffers = {}
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(Adw.HeaderBar())
        self.set_content(root)
        self.stack = Adw.ViewStack(vexpand=True)
        root.append(Adw.ViewSwitcher(stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE))
        root.append(self.stack)
        self.estado = texto("Guardado local por cuenta; incluido en respaldos. No se sincroniza entre equipos.")
        self.estado.set_margin_start(18)
        self.estado.set_margin_bottom(12)
        root.append(self.estado)
        self.hoy_box = self.pagina("hoy", "Hoy", "go-home-symbolic")
        self.ruta_box = self.pagina("ruta", "Ruta", "mark-location-symbolic")
        self.cuaderno_box = self.pagina("cuaderno", "Cuaderno", "document-edit-symbolic")
        self.revision_box = self.pagina("revision", "Semana", "view-calendar-symbolic")
        self.reloj_box = self.pagina("razonar", "20 → 10 → 5", "preferences-system-time-symbolic")
        self.build_hoy()
        self.build_ruta()
        self.build_cuaderno()
        self.build_revision()
        self.build_reloj()
        self.connect("close-request", self.cerrar)
        self.connect("unmap", self.ocultar)

    def pagina(self, key, titulo, icono):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                      margin_start=22, margin_end=22, margin_top=20, margin_bottom=24)
        clamp = Adw.Clamp(maximum_size=780)
        clamp.set_child(box)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(clamp)
        self.stack.add_titled_with_icon(scroll, key, titulo, icono)
        return box

    def guardar(self, operacion):
        try:
            resultado = operacion()
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.estado.set_label(f"No se pudo guardar: {exc}")
            return False
        self.estado.set_label("Guardado en este equipo.")
        return resultado if resultado is not None else True

    def build_hoy(self):
        box = self.hoy_box
        box.append(texto("Ingeniería + Datos + IA + Negocio + Inglés + Comunicación", True))
        box.append(texto("Mide lo que puedes resolver y construir. Las casillas son tu registro personal, no una evaluación automática."))
        self.presupuesto = Gtk.DropDown.new_from_strings(["60 minutos entre semana", "90 minutos entre semana"])
        self.presupuesto.set_selected(0 if plan.leer(self.con, "minutos", 90) == 60 else 1)
        box.append(self.presupuesto)
        self.fase = Gtk.DropDown.new_from_strings(["Fase según la fecha"] + [f["nombre"] for f in plan.FASES])
        seleccion = plan.leer(self.con, "fase", None)
        self.fase.set_selected(0 if seleccion is None else seleccion + 1)
        box.append(self.fase)
        self.agenda_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.append(self.agenda_box)
        self.presupuesto.connect("notify::selected", self.cambiar_preferencias)
        self.fase.connect("notify::selected", self.cambiar_preferencias)
        self.refrescar_agenda()
        box.append(boton("Abrir lectura guiada · 20 min", self.abrir_lectura))
        box.append(boton("Escribir lo que recuerdo", lambda *_: self.nueva_entrada("lectura")))
        box.append(boton("Practicar inglés", self.ingles))
        box.append(boton("Abrir lecturas del área prioritaria", self.abrir_area))
        box.append(texto("Sábado: 2 horas en total, con 85 min de proyecto. Domingo: 45 min de lectura y revisión; después descanso. "
                         "La lectura y el inglés ya están incluidos en el presupuesto. Puedes adaptar el ritmo sin sumar más cursos."))
        box.append(texto("Concentración: empieza con 20 minutos. Cuando resulte cómodo, elige 30 y luego 40 en el lector guiado, "
                         "reduciendo otros bloques para mantener el total. Las páginas son una referencia, no una cuota."))

    def seleccion_fase(self):
        return self.fase.get_selected() - 1 if self.fase.get_selected() else None

    def cambiar_preferencias(self, *_):
        self.guardar(lambda: plan.guardar(self.con, "minutos", 60 if self.presupuesto.get_selected() == 0 else 90))
        self.guardar(lambda: plan.guardar(self.con, "fase", self.seleccion_fase()))
        self.refrescar_agenda()

    def refrescar_agenda(self):
        self.hoy = date.today()
        box = self.agenda_box
        while (child := box.get_first_child()) is not None:
            box.remove(child)
        fase = plan.FASES[plan.fase_actual(self.hoy, self.seleccion_fase())]
        box.append(texto(f"{self.hoy.isoformat()} · {fase['nombre']}", True))
        if self.hoy.isoformat() > plan.FASES[-1]["fin"]:
            box.append(texto("El calendario del plan ha terminado. Revisa tus evidencias y elige una fase para continuar."))
        elif self.hoy.isoformat() < plan.FASES[0]["inicio"]:
            box.append(texto("El plan comienza en septiembre de 2026. Puedes empezar a practicar los fundamentos."))
        tareas = plan.agenda(self.hoy, 60 if self.presupuesto.get_selected() == 0 else 90, self.seleccion_fase())
        box.append(texto(f"Hoy: {sum(t[2] for t in tareas)} minutos en total"))
        guardado = plan.leer(self.con, "dia:" + self.hoy.isoformat(), {})
        for key, titulo, minutos in tareas:
            fila = Gtk.Box(spacing=10)
            check = Gtk.CheckButton(valign=Gtk.Align.START)
            check.set_active(guardado.get(key, False))
            fecha = self.hoy
            check.connect("toggled", lambda b, k=key, d=fecha: self.guardar(
                lambda: plan.registrar_dia(self.con, d, k, b.get_active())))
            fila.append(check)
            fila.append(texto(f"{minutos} min · {titulo}"))
            box.append(fila)

    def abrir_lectura(self, *_):
        from . import lectura_diaria
        from .lectura_guiada_window import LecturaGuiadaWindow
        cap = lectura_diaria.del_dia(self.con)
        if cap is None:
            self.estado.set_label("No hay lecturas disponibles. Añade contenido o activa un mazo en AppStudy.")
            return
        ventana = LecturaGuiadaWindow(self, dict(cap))
        ventana.minutos.set_value(20)
        ventana.present()

    def ingles(self, *_):
        existe = self.con.execute("SELECT 1 FROM decks WHERE key='ingles' AND enabled=1").fetchone()
        if existe:
            self.parent.get_application().show_popup("ingles")
        else:
            self.estado.set_label("Activa el mazo de inglés para practicar. También puedes escuchar y escribir fuera de la aplicación.")

    def abrir_area(self, *_):
        if not self.guardar_editor():
            self.stack.set_visible_child_name("cuaderno")
            return
        fase = plan.FASES[plan.fase_actual(elegida=self.seleccion_fase())]
        caps = [c for c in db.chapters(self.con) if c["deck_key"] == fase["mazo"]]
        if not caps:
            self.estado.set_label("No hay capítulos de esta área. Puedes añadirlos desde Leer o Biblioteca.")
            return
        cap = next((c for c in caps if not c["leido"]), caps[0])
        self.parent.abrir_lectura(cap)
        self.close()

    def build_ruta(self):
        box = self.ruta_box
        box.append(texto("2026: pensar · 2027: analizar · 2028: construir sistemas inteligentes", True))
        box.append(texto("La fecha propone la fase; no certifica dominio. Cada evidencia debe explicar qué hiciste y cómo lo comprobaste."))
        for i, fase in enumerate(plan.FASES):
            box.append(texto(f"{i + 1}. {fase['nombre']}", True))
            box.append(texto(f"{fase['inicio']} → {fase['fin']}\n{fase['temas']}\nEntrega: {fase['entrega']}"))
        box.append(texto("Evidencias cada tres meses", True))
        for fecha, titulo, criterio in plan.HITOS:
            box.append(texto(f"{fecha} · {titulo}\n{criterio}"))
            valor = plan.leer(self.con, "hito:" + fecha, "")
            entry = Gtk.Entry(placeholder_text="Evidencia: archivo/enlace y qué demuestra", text=valor)
            box.append(entry)
            estado = texto("Evidencia registrada" if valor else "Pendiente")
            box.append(estado)
            def guardar_hito(*_, f=fecha, e=entry, s=estado):
                if self.guardar(lambda: plan.guardar(self.con, "hito:" + f, e.get_text().strip())):
                    s.set_label("Evidencia registrada" if e.get_text().strip() else "Pendiente")
            box.append(boton("Guardar evidencia", guardar_hito))

    def build_cuaderno(self):
        box = self.cuaderno_box
        box.append(texto("Cuaderno de razonamiento y resultados", True))
        for tipo, label in (("problema", "Nuevo problema"), ("lectura", "Nueva reflexión de lectura"),
                            ("evidencia", "Nuevo resultado de proyecto")):
            box.append(boton(label, lambda *_, t=tipo: self.nueva_entrada(t)))
        self.editor = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.append(self.editor)
        box.append(texto("Entradas guardadas · pulsa para editar", True))
        self.historial = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.append(self.historial)
        self.refrescar_historial()

    def nueva_entrada(self, tipo):
        if self.buffers and not self.guardar_editor():
            return
        self.cargar_editor(tipo, {}, None)
        self.stack.set_visible_child_name("cuaderno")

    def cargar_editor(self, tipo, valores, identidad):
        while (child := self.editor.get_first_child()) is not None:
            self.editor.remove(child)
        self.editor_id, self.editor_tipo = identidad, tipo
        self.buffers = {nombre: campo(self.editor, nombre, valores.get(nombre, ""))
                        for nombre in plan.CAMPOS[tipo]}
        self.editor.append(boton("Guardar entrada", lambda *_: self.guardar_editor()))

    def guardar_editor(self):
        if not self.buffers:
            return True
        valores = {nombre: contenido(b) for nombre, b in self.buffers.items()}
        if not any(v.strip() for v in valores.values()) and self.editor_id is None:
            return True
        identidad = self.guardar(lambda: plan.guardar_entrada(
            self.con, self.editor_tipo, valores, self.editor_id))
        if identidad is False:
            return False
        self.editor_id = identidad
        self.refrescar_historial()
        return True

    def refrescar_historial(self):
        while (child := self.historial.get_first_child()) is not None:
            self.historial.remove(child)
        entradas = sorted(plan.entradas(self.con), key=lambda e: e["ts"], reverse=True)
        if not entradas:
            self.historial.append(texto("Aún no hay entradas. Empieza por un problema real o la lectura de hoy."))
        for entrada in entradas:
            titulo = next(iter(entrada["campos"].values())).strip().splitlines()[0][:90]
            def abrir(*_, e=entrada):
                if self.guardar_editor():
                    # Guardar puede actualizar la entrada seleccionada; releer evita cargar una copia vieja.
                    actual = plan.leer(self.con, "entrada:" + e["id"])
                    self.cargar_editor(actual["tipo"], actual["campos"], actual["id"])
            self.historial.append(boton(f"{entrada['fecha']} · {entrada['tipo']} · {titulo}", abrir))

    def build_revision(self):
        box = self.revision_box
        self.fecha_semana = date.today()
        self.semana_clave = plan.semana(self.fecha_semana)
        box.append(texto(f"Semana del {self.semana_clave}", True))
        box.append(texto("Cada domingo: puntúa de 0 a 5 lo que practicaste. Es una autoevaluación, no una medida de dominio. "
                         "Explica qué puedes hacer ahora y qué construirás la próxima semana."))
        actual = plan.leer(self.con, "semana:" + self.semana_clave, {})
        self.notas = {}
        for area in plan.AREAS:
            fila = Gtk.Box(spacing=12)
            label = texto(area)
            label.set_hexpand(True)
            fila.append(label)
            spin = Gtk.SpinButton.new_with_range(0, 5, 1)
            spin.set_value(actual.get("notas", {}).get(area, 0))
            self.notas[area] = spin
            fila.append(spin)
            box.append(fila)
        self.reflexion = campo(box, "Qué puedo hacer ahora / evidencia / siguiente paso", actual.get("reflexion", ""))
        box.append(boton("Guardar revisión semanal", self.guardar_semana))
        self.historial_semanal = texto("")
        box.append(self.historial_semanal)
        self.refrescar_semanas()

    def guardar_semana(self, *_):
        if self.guardar(lambda: plan.guardar_revision(self.con, self.fecha_semana,
                {a: s.get_value_as_int() for a, s in self.notas.items()}, contenido(self.reflexion))):
            self.refrescar_semanas()

    def refrescar_semanas(self):
        filas = self.con.execute("SELECT k FROM meta WHERE k LIKE 'potencial:semana:%' ORDER BY k DESC LIMIT 13")
        lineas = []
        for fila in filas:
            key = fila["k"].removeprefix("potencial:")
            datos = plan.leer(self.con, key)
            lineas.append(key.removeprefix("semana:") + "\n" +
                          " · ".join(f"{a}: {v}/5" for a, v in datos["notas"].items()) +
                          "\n" + datos["reflexion"])
        self.historial_semanal.set_label("Últimas 13 revisiones\n\n" + "\n\n".join(lineas))

    def build_reloj(self):
        box = self.reloj_box
        box.append(texto("Piensa → consulta → explica", True))
        box.append(texto("Un bloque completo dura 35 minutos. Úsalo dentro de tu práctica o proyecto, sin añadirlo al horario. "
                         "En días de 60 minutos, sustituye otros bloques para respetar el total. "
                         "El temporizador no bloquea otras aplicaciones ni consulta la IA por ti. Cada etapa espera tu confirmación para continuar."))
        self.reloj_estado = texto("20:00 · Tú solo", True)
        box.append(self.reloj_estado)
        self.reloj_guia = texto(plan.RelojRazonamiento.ETAPAS[0][2])
        box.append(self.reloj_guia)
        self.reloj_boton = boton("Comenzar", self.alternar_reloj)
        box.append(self.reloj_boton)
        self.continuar = boton("Continuar a la siguiente etapa", self.siguiente_etapa)
        self.continuar.set_sensitive(False)
        box.append(self.continuar)
        self.nuevo_reloj = boton("Nueva sesión", self.reiniciar_reloj)
        self.nuevo_reloj.set_sensitive(False)
        box.append(self.nuevo_reloj)
        box.append(boton("Escribir mi razonamiento", lambda *_: self.nueva_entrada("problema")))

    def alternar_reloj(self, *_):
        if self.reloj is None:
            self.reloj = plan.RelojRazonamiento()
        if self.reloj.inicio is None:
            self.reloj.iniciar()
        else:
            self.reloj.pausar()
        self.tick()
        if self.timer is None and self.reloj.restante > 0:
            self.timer = GLib.timeout_add(250, self.tick)

    def tick(self):
        r = self.reloj
        segundos = math.ceil(r.restante)
        self.reloj_estado.set_label(f"{segundos // 60:02d}:{segundos % 60:02d} · {r.ETAPAS[r.etapa][1]}" +
                                    (" · En pausa" if r.inicio is None and segundos else ""))
        self.reloj_guia.set_label(r.ETAPAS[r.etapa][2])
        self.reloj_boton.set_label("Reanudar" if r.inicio is None else "Pausar")
        self.reloj_boton.set_sensitive(segundos > 0)
        self.continuar.set_sensitive(segundos == 0 and r.etapa < 2)
        if segundos == 0:
            r.pausar()
            self.reloj_guia.set_label("Etapa terminada. Continúa cuando estés listo." if r.etapa < 2 else
                                      "Sesión terminada. Guarda tu explicación y qué aprendiste en el cuaderno.")
            self.nuevo_reloj.set_sensitive(r.etapa == 2)
            self.timer = None
            return False
        return True

    def siguiente_etapa(self, *_):
        if self.reloj.siguiente():
            self.alternar_reloj()

    def reiniciar_reloj(self, *_):
        self.reloj = None
        self.nuevo_reloj.set_sensitive(False)
        self.alternar_reloj()

    def ocultar(self, *_):
        if self.reloj:
            self.reloj.pausar()

    def cerrar(self, *_):
        if not self.guardar_editor():
            self.stack.set_visible_child_name("cuaderno")
            return True
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None
        if self.reloj:
            self.reloj.pausar()
        return False
