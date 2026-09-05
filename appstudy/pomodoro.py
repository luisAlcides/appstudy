"""Temporizador Pomodoro integrado con micro-repasos de estudio.

Gestiona bloques de concentración de 25 minutos. Al sonar la alarma, convierte
el descanso en una pausa activa de aprendizaje lanzando un mini-repaso de 5 tarjetas
para fijar la memoria antes de descansar o retomar el trabajo.
"""
from __future__ import annotations

import time
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

from . import db, scheduler, sonido

ESTADO_INACTIVO = "inactivo"
ESTADO_TRABAJO = "trabajo"
ESTADO_DESCANSO = "descanso"
ESTADO_PAUSA = "pausa"


class PomodoroControl:
    """Lógica del temporizador Pomodoro."""

    def __init__(self, con, mins_trabajo: int = 25, mins_descanso: int = 5,
                 tarjetas_mini_repaso: int = 5, on_tick=None, on_fin_trabajo=None):
        self.con = con
        self.duracion_trabajo = mins_trabajo * 60
        self.duracion_descanso = mins_descanso * 60
        self.tarjetas_mini_repaso = tarjetas_mini_repaso

        self.restante = self.duracion_trabajo
        self.estado = ESTADO_INACTIVO
        self.on_tick = on_tick
        self.on_fin_trabajo = on_fin_trabajo
        self.timer_id = None

    def iniciar(self):
        if self.estado == ESTADO_INACTIVO:
            self.restante = self.duracion_trabajo
            self.estado = ESTADO_TRABAJO
        elif self.estado == ESTADO_PAUSA:
            self.estado = ESTADO_TRABAJO

        if self.timer_id is None:
            self.timer_id = GLib.timeout_add_seconds(1, self._tick)
        self._notificar()

    def pausar(self):
        if self.estado in (ESTADO_TRABAJO, ESTADO_DESCANSO):
            self.estado = ESTADO_PAUSA
            if self.timer_id:
                GLib.source_remove(self.timer_id)
                self.timer_id = None
            self._notificar()

    def alternar(self):
        if self.estado == ESTADO_TRABAJO:
            self.pausar()
        else:
            self.iniciar()

    def reiniciar(self):
        if self.timer_id:
            GLib.source_remove(self.timer_id)
            self.timer_id = None
        self.estado = ESTADO_INACTIVO
        self.restante = self.duracion_trabajo
        self._notificar()

    def _tick(self) -> bool:
        if self.estado not in (ESTADO_TRABAJO, ESTADO_DESCANSO):
            self.timer_id = None
            return False

        self.restante -= 1
        self._notificar()

        if self.restante <= 0:
            if self.estado == ESTADO_TRABAJO:
                self._al_completar_trabajo()
            else:
                self._al_completar_descanso()
            self.timer_id = None
            return False

        return True

    def _al_completar_trabajo(self):
        try:
            sonido.tocar("victoria")
        except Exception:
            pass

        # Pausar el reproductor de cursos si está activo
        try:
            from . import reproductor
            reproductor.pausar_reproductor_activo()
        except Exception:
            pass

        self.estado = ESTADO_DESCANSO
        self.restante = self.duracion_descanso
        self._notificar()

        if self.on_fin_trabajo:
            try:
                self.on_fin_trabajo()
            except Exception:
                pass

    def _al_completar_descanso(self):
        try:
            sonido.tocar("subida")
        except Exception:
            pass
        self.estado = ESTADO_INACTIVO
        self.restante = self.duracion_trabajo
        self._notificar()

    def _notificar(self):
        if self.on_tick:
            total = self.duracion_trabajo if self.estado != ESTADO_DESCANSO else self.duracion_descanso
            self.on_tick(self.restante, total, self.estado)


class PomodoroWidget(Gtk.Box):
    """Widget compacto para anclar en el panel o barra superior de AppStudy."""

    def __init__(self, app, con):
        super().__init__(spacing=8, valign=Gtk.Align.CENTER)
        self.app = app
        self.con = con

        self.ctrl = PomodoroControl(
            con,
            mins_trabajo=25,
            mins_descanso=5,
            tarjetas_mini_repaso=5,
            on_tick=self.actualizar_vista,
            on_fin_trabajo=self.lanzar_repaso_pomodoro,
        )

        self.btn_toggle = Gtk.Button(css_classes=["flat", "pill"])
        self.btn_toggle.connect("clicked", lambda *_: self.ctrl.alternar())

        caja_b = Gtk.Box(spacing=6)
        self.lbl_icono = Gtk.Label(label="🍅")
        caja_b.append(self.lbl_icono)
        self.lbl_tiempo = Gtk.Label(label="25:00", css_classes=["caption"])
        caja_b.append(self.lbl_tiempo)
        self.btn_toggle.set_child(caja_b)
        self.append(self.btn_toggle)

        self.btn_reset = Gtk.Button(icon_name="view-refresh-symbolic",
                                    tooltip_text="Reiniciar Pomodoro",
                                    css_classes=["flat", "circular"])
        self.btn_reset.connect("clicked", lambda *_: self.ctrl.reiniciar())
        self.append(self.btn_reset)

        self.actualizar_vista(25 * 60, 25 * 60, ESTADO_INACTIVO)

    def actualizar_vista(self, restante: int, total: int, estado: str):
        mins = max(0, restante) // 60
        segs = max(0, restante) % 60
        texto = f"{mins:02d}:{segs:02d}"
        self.lbl_tiempo.set_label(texto)

        if estado == ESTADO_TRABAJO:
            self.lbl_icono.set_label("🍅")
            self.btn_toggle.set_tooltip_text("Pausar Pomodoro de concentración")
            self.btn_toggle.add_css_class("suggested-action")
        elif estado == ESTADO_DESCANSO:
            self.lbl_icono.set_label("☕")
            self.btn_toggle.set_tooltip_text("Descanso (o mini-repaso de 5 tarjetas)")
            self.btn_toggle.set_css_classes(["flat", "pill", "success"])
        else:
            self.lbl_icono.set_label("🍅")
            self.btn_toggle.set_tooltip_text("Iniciar bloque de 25 minutos")
            self.btn_toggle.set_css_classes(["flat", "pill"])

    def lanzar_repaso_pomodoro(self):
        """Lanza el mini-repaso de 5 tarjetas tras completar los 25 minutos."""
        try:
            from . import reproductor
            reproductor.pausar_reproductor_activo()
        except Exception:
            pass

        if hasattr(self.app, "show_popup"):
            from . import sesiones
            plan = sesiones.SessionPlan(
                nombre="Descanso Pomodoro",
                minutos=5,
                tarjetas=5,
                factor_tiempo=1.0
            )
            self.app.show_popup(session_plan=plan)
