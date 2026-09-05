"""Modo Escritura Libre con Corrección por IA Local.

Permite practicar redacción de párrafos, redacción formal y ensayos cortos a
partir de un tema del mazo (ideal para los retos de producción escrita de inglés
C1/B2, argumentación técnica o resolución de incidencias). La IA local evalúa
gramática, registro, vocabulario y propone una versión pulida.
"""
from __future__ import annotations

import random
import re
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from . import ia, util

TEMAS_PREDETERMINADOS = {
    "ingles": [
        {
            "titulo": "Formal Complaint & Service Level Agreement",
            "instrucciones": "Write a formal email (100–150 words) to a supplier regarding repeated delays in industrial equipment deliveries. Maintain a firm yet professional C1 tone.",
            "palabras_clave": ["further to", "breach of contract", "untenable", "prompt resolution", "mitigate"],
            "nivel": "C1",
            "min_palabras": 80,
        },
        {
            "titulo": "Balancing Opposing Technical Views",
            "instrucciones": "Discuss whether automated AI monitoring should completely replace manual safety inspections in heavy machinery. Present both perspectives and conclude with your stance.",
            "palabras_clave": ["on the one hand", "conversely", "inadvertently", "paramount", "safeguard"],
            "nivel": "C1",
            "min_palabras": 90,
        },
        {
            "titulo": "Explaining a Past Routine & Sudden Event",
            "instrucciones": "Describe a typical maintenance morning at the workshop when an unexpected mechanical breakdown suddenly occurred. Practice Past Simple vs. Past Continuous.",
            "palabras_clave": ["while", "suddenly", "used to", "was inspecting", "noticed"],
            "nivel": "B1",
            "min_palabras": 70,
        },
        {
            "titulo": "Negotiating Terms and Deadlines",
            "instrucciones": "Write a persuasive proposal suggesting a phased delivery schedule for a client who needs their vehicle fleet serviced urgently.",
            "palabras_clave": ["feasible", "compromise", "expedite", "mutual agreement", "timeline"],
            "nivel": "B2",
            "min_palabras": 85,
        },
    ],
    "linux": [
        {
            "titulo": "Informe de Incidencia: Servicio Caído y Recuperación",
            "instrucciones": "Redacta un reporte técnico explicando por qué se llenó el sistema de archivos raíz, qué proceso causó el bloqueo y cómo lo solucionaste con systemd y lsof.",
            "palabras_clave": ["inodos", "journalctl", "systemctl restart", "lsof", "partición"],
            "nivel": "Intermedio",
            "min_palabras": 70,
        },
        {
            "titulo": "Propuesta de Seguridad en Servidores SSH",
            "instrucciones": "Explica a un cliente o colega por qué es indispensable deshabilitar el acceso root por contraseña e implementar autenticación por llaves y fail2ban.",
            "palabras_clave": ["fuerza bruta", "ed25519", "sshd_config", "cortafuegos", "bastionado"],
            "nivel": "Avanzado",
            "min_palabras": 75,
        },
    ],
    "datos": [
        {
            "titulo": "Diagnóstico de Sobreajuste en Producción",
            "instrucciones": "Redacta un análisis técnico explicando la discrepancia entre las métricas de entrenamiento (AUC 0.99) y validación (AUC 0.65) en un modelo de predicción de fallas.",
            "palabras_clave": ["data leakage", "regularización", "validación cruzada", "sesgo", "generalización"],
            "nivel": "Avanzado",
            "min_palabras": 75,
        },
    ],
    "ia": [
        {
            "titulo": "Diseño de Arquitectura RAG con Evaluación",
            "instrucciones": "Describe cómo diseñarías un pipeline de preguntas y respuestas para manuales técnicos de maquinaria, minimizando alucinaciones y midiendo la precisión de respuesta.",
            "palabras_clave": ["embeddings", "chunking", "re-ranking", "context window", "evaluación"],
            "nivel": "Avanzado",
            "min_palabras": 80,
        },
    ],
}


def obtener_tema(con, deck_key: str | None = None) -> dict:
    """Selecciona o genera un tema de redacción."""
    key = deck_key or "ingles"
    lista = TEMAS_PREDETERMINADOS.get(key) or TEMAS_PREDETERMINADOS.get("ingles")
    return random.choice(lista)


def prompt_correccion_ia(tema: dict, texto: str) -> str:
    return f"""Actúa como un profesor y evaluador lingüístico experto.
El estudiante ha redactado el siguiente texto para la tarea:
Título: {tema['titulo']}
Instrucciones: {tema['instrucciones']}
Nivel objetivo: {tema.get('nivel', 'Avanzado')}

Texto del estudiante:
\"\"\"
{texto}
\"\"\"

Evalúa el texto respondiendo de forma clara y estructurada con estas secciones:
1. <b>Nivel estimado:</b> (indica si cumple con el nivel esperado: B1, B2 o C1).
2. <b>Gramática y ortografía:</b> lista las correcciones puntuales (explica brevemente el error y la forma correcta).
3. <b>Registro y estilo:</b> comenta si el tono y vocabulario son adecuados para la consigna.
4. <b>Versión mejorada:</b> reescribe el texto de forma natural y elegante manteniendo el mensaje original.

Sé conciso, constructivo y directo."""


class EscrituraWindow(Adw.Window):
    """Ventana interactiva de práctica de escritura libre con IA."""

    def __init__(self, parent_window, con, deck_key: str = "ingles"):
        super().__init__(modal=True, transient_for=parent_window)
        self.set_title("Modo Escritura Libre · Práctica con IA")
        self.set_default_size(760, 640)

        self.con = con
        self.deck_key = deck_key
        self.tema = obtener_tema(con, deck_key)
        self.construir_ui()

    def construir_ui(self):
        self.box_raiz = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        self.box_raiz.append(header)

        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_vexpand(True)

        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        caja.set_margin_top(18)
        caja.set_margin_bottom(24)
        caja.set_margin_start(24)
        caja.set_margin_end(24)

        # Tarjeta del tema
        self.card_tema = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["as-card"])
        inner_t = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        inner_t.set_margin_top(14)
        inner_t.set_margin_bottom(14)
        inner_t.set_margin_start(16)
        inner_t.set_margin_end(16)

        fila_t = Gtk.Box(spacing=8)
        self.lbl_nivel = Gtk.Label(label=f"Nivel {self.tema.get('nivel', 'C1')}", css_classes=["as-chip-mazo"])
        fila_t.append(self.lbl_nivel)
        fila_t.append(Gtk.Box(hexpand=True))

        btn_otro = Gtk.Button(label="🎲 Otro tema", css_classes=["flat", "pill"])
        btn_otro.connect("clicked", lambda *_: self.cambiar_tema())
        fila_t.append(btn_otro)
        inner_t.append(fila_t)

        self.lbl_titulo = Gtk.Label(label=f"<b>{self.tema['titulo']}</b>", use_markup=True, wrap=True, xalign=0)
        inner_t.append(self.lbl_titulo)

        self.lbl_instrucciones = Gtk.Label(label=self.tema["instrucciones"], wrap=True, xalign=0, css_classes=["as-dim"])
        inner_t.append(self.lbl_instrucciones)

        if self.tema.get("palabras_clave"):
            chips = Gtk.Box(spacing=6)
            chips.append(Gtk.Label(label="Sugerencias:", css_classes=["caption", "as-dim"]))
            for p in self.tema["palabras_clave"][:4]:
                chips.append(Gtk.Label(label=f"«{p}»", css_classes=["caption", "dim-label"]))
            inner_t.append(chips)

        self.card_tema.append(inner_t)
        caja.append(self.card_tema)

        # Área de texto
        caja.append(Gtk.Label(label="Tu redacción:", xalign=0, css_classes=["heading"]))

        frame_txt = Gtk.Frame()
        self.textview = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.textview.set_margin_top(10)
        self.textview.set_margin_bottom(10)
        self.textview.set_margin_start(12)
        self.textview.set_margin_end(12)
        self.textview.set_vexpand(True)
        self.textview.set_size_request(-1, 160)

        buf = self.textview.get_buffer()
        buf.connect("changed", lambda *_: self.actualizar_contador())

        frame_txt.set_child(self.textview)
        caja.append(frame_txt)

        # Barra de contador y botón
        fila_accion = Gtk.Box(spacing=12)
        self.lbl_conteo = Gtk.Label(label="0 palabras", css_classes=["caption", "as-dim"])
        fila_accion.append(self.lbl_conteo)
        fila_accion.append(Gtk.Box(hexpand=True))

        self.btn_corregir = Gtk.Button(label="✨ Corregir con IA", css_classes=["suggested-action", "pill"])
        self.btn_corregir.connect("clicked", lambda *_: self.iniciar_correccion())
        fila_accion.append(self.btn_corregir)
        caja.append(fila_accion)

        # Zona de resultado de la corrección
        self.caja_resultado = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.caja_resultado.set_visible(False)

        self.spinner = Gtk.Spinner()
        self.caja_resultado.append(self.spinner)

        self.lbl_feedback = Gtk.Label(wrap=True, xalign=0, selectable=True)
        self.caja_resultado.append(self.lbl_feedback)

        caja.append(self.caja_resultado)

        scroll.set_child(caja)
        self.box_raiz.append(scroll)
        self.set_content(self.box_raiz)

    def actualizar_contador(self):
        buf = self.textview.get_buffer()
        inicio, fin = buf.get_bounds()
        txt = buf.get_text(inicio, fin, True)
        palabras = len(re.findall(r"\b\w+\b", txt))
        min_p = self.tema.get("min_palabras", 80)
        self.lbl_conteo.set_label(f"{palabras} palabras (objetivo: {min_p}+)")

    def cambiar_tema(self):
        self.tema = obtener_tema(self.con, self.deck_key)
        self.lbl_nivel.set_label(f"Nivel {self.tema.get('nivel', 'C1')}")
        self.lbl_titulo.set_markup(f"<b>{self.tema['titulo']}</b>")
        self.lbl_instrucciones.set_text(self.tema["instrucciones"])
        self.caja_resultado.set_visible(False)
        self.actualizar_contador()

    def iniciar_correccion(self):
        buf = self.textview.get_buffer()
        inicio, fin = buf.get_bounds()
        txt = buf.get_text(inicio, fin, True).strip()
        if not txt:
            return

        cfg = ia.config(self.con)
        if not cfg.get("activa"):
            self.mostrar_feedback("<i>La IA local no está activada. Puedes activarla en Ajustes → Modelo de IA.</i>")
            return

        self.btn_corregir.set_sensitive(False)
        self.caja_resultado.set_visible(True)
        self.spinner.start()
        self.lbl_feedback.set_markup("<i>Consultando con el modelo local de IA…</i>")

        prompt = prompt_correccion_ia(self.tema, txt)

        def _tarea():
            try:
                res = ia.completar(cfg, prompt, sistema="Eres un evaluador lingüístico experto y conciso.")
                return res, None
            except Exception as e:
                return None, str(e)

        def _fin(res, err):
            self.spinner.stop()
            self.btn_corregir.set_sensitive(True)
            if err:
                self.mostrar_feedback(f"❌ Error al consultar la IA: {err}")
            else:
                self.mostrar_feedback(res)

        ia.hilo(_tarea, lambda r: _fin(r[0], r[1]), lambda e: _fin(None, str(e)))

    def mostrar_feedback(self, texto: str):
        self.caja_resultado.set_visible(True)
        self.spinner.stop()
        # Convertir a formato enriquecido legible
        formateado = util.to_markup(texto)
        self.lbl_feedback.set_markup(formateado)
