"""Estudio a ciegas de un capítulo.

Permite realizar un test diagnóstico rápido (3 a 5 preguntas) antes de leer
un capítulo. Si el usuario ya domina los conceptos (≥ 80% de aciertos),
la aplicación le sugiere saltar la lectura para ahorrar tiempo en los básicos.
"""
from __future__ import annotations

import random
import time
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from . import cloze, db, reto, util


def tarjetas_para_test(con, chapter: dict, n: int = 5) -> list[dict]:
    """Selecciona hasta n tarjetas representativas del capítulo para el test diagnóstico."""
    if not chapter:
        return []
    deck_id = chapter.get("deck_id")
    if not deck_id:
        return []

    etiquetas = {t.strip().lower() for t in (chapter.get("tags") or "").split(",") if t.strip()}
    cap_level = chapter.get("level")

    filas = con.execute(
        """SELECT c.*, d.name AS deck_name, d.color AS deck_color, d.icon AS deck_icon
           FROM cards c JOIN decks d ON d.id=c.deck_id
           WHERE c.deck_id=?""",
        (deck_id,)).fetchall()

    candidatas = []
    for f in filas:
        c = dict(f)
        c_tags = {t.strip().lower() for t in (c.get("tags") or "").split(",") if t.strip()}
        puntos = 3.0 * len(etiquetas & c_tags)
        if cap_level and c.get("level") == cap_level:
            puntos += 2.0
        if puntos >= 2.0:
            candidatas.append((puntos, c))

    if not candidatas and filas:
        candidatas = [(1.0, dict(f)) for f in filas if f["level"] == cap_level] or [(1.0, dict(f)) for f in filas]

    candidatas.sort(key=lambda x: x[0], reverse=True)
    seleccion = [c for _, c in candidatas[:max(n * 2, 10)]]
    if len(seleccion) > n:
        random.seed(int(time.time() * 1000) % 10000)
        seleccion = random.sample(seleccion, n)
    return seleccion[:n]


class TestCiegasDialog(Adw.Window):
    """Ventana interactiva de evaluación diagnóstica antes de leer un capítulo."""

    def __init__(self, parent_window, con, chapter: dict, on_saltar=None, on_leer=None):
        super().__init__(modal=True, transient_for=parent_window)
        self.set_title(f"Test a ciegas · {chapter.get('title', '')}")
        self.set_default_size(520, 480)

        self.con = con
        self.chapter = chapter
        self.on_saltar = on_saltar
        self.on_leer = on_leer

        self.tarjetas = tarjetas_para_test(con, chapter, n=5)
        self.indice = 0
        self.aciertos = 0
        self.respuestas = []

        self.construir_ui()

    def construir_ui(self):
        self.box_principal = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        self.box_principal.append(header)

        if not self.tarjetas:
            aviso = Adw.StatusPage(
                icon_name="dialog-information-symbolic",
                title="Sin tarjetas suficientes",
                description="Este capítulo no cuenta con tarjetas asociadas para el test previo.",
            )
            btn = Gtk.Button(label="Comenzar lectura", css_classes=["suggested-action", "pill"])
            btn.connect("clicked", lambda *_: (self.close(), self.on_leer and self.on_leer()))
            aviso.set_child(btn)
            self.box_principal.append(aviso)
            self.set_content(self.box_principal)
            return

        self.barra_progreso = Gtk.ProgressBar(css_classes=["as-progress"])
        self.barra_progreso.set_margin_start(20)
        self.barra_progreso.set_margin_end(20)
        self.barra_progreso.set_margin_top(8)
        self.box_principal.append(self.barra_progreso)

        self.contenedor = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.contenedor.set_margin_top(20)
        self.contenedor.set_margin_bottom(24)
        self.contenedor.set_margin_start(24)
        self.contenedor.set_margin_end(24)
        self.contenedor.set_vexpand(True)
        self.box_principal.append(self.contenedor)

        self.set_content(self.box_principal)
        self.mostrar_pregunta_actual()

    def mostrar_pregunta_actual(self):
        while self.contenedor.get_first_child():
            self.contenedor.remove(self.contenedor.get_first_child())

        total = len(self.tarjetas)
        self.barra_progreso.set_fraction((self.indice) / float(total))

        c = self.tarjetas[self.indice]

        lbl_paso = Gtk.Label(
            label=f"Pregunta {self.indice + 1} de {total}",
            css_classes=["caption", "as-dim"],
            xalign=0,
        )
        self.contenedor.append(lbl_paso)

        card_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["as-card"])
        card_box.set_margin_top(6)
        card_box.set_margin_bottom(6)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        inner.set_margin_top(16)
        inner.set_margin_bottom(16)
        inner.set_margin_start(16)
        inner.set_margin_end(16)

        frente = (cloze.enmascarar(c["front"]) if cloze.tiene_huecos(c["front"])
                  else c["front"])
        lbl_front = Gtk.Label(
            label=util.to_markup(frente),
            use_markup=True,
            wrap=True,
            xalign=0,
            css_classes=["as-bubble-front"],
        )
        self.lbl_front = lbl_front
        inner.append(lbl_front)
        card_box.append(inner)
        self.contenedor.append(card_box)

        reto_dict = reto.preparar(self.con, c) if c.get("back") else None
        if reto_dict and reto_dict.get("formato") in ("opciones", "invertido") and reto_dict.get("opciones"):
            self.crear_opciones_quiz(reto_dict)
        else:
            self.crear_modo_revelar(c)

    def crear_opciones_quiz(self, reto_dict: dict):
        ops_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        ops_box.set_margin_top(10)
        ops_box.set_vexpand(True)

        correcta = reto_dict["correcta"]
        for idx, opcion in enumerate(reto_dict["opciones"]):
            btn = Gtk.Button(css_classes=["flat", "card"])
            caja_b = Gtk.Box(spacing=10)
            caja_b.set_margin_top(10)
            caja_b.set_margin_bottom(10)
            caja_b.set_margin_start(12)
            caja_b.set_margin_end(12)

            letra = chr(65 + idx)
            lbl_l = Gtk.Label(label=f"<b>{letra}</b>", use_markup=True, css_classes=["as-dim"])
            caja_b.append(lbl_l)
            caja_b.append(Gtk.Label(label=opcion, wrap=True, xalign=0))
            btn.set_child(caja_b)

            btn.connect("clicked", lambda *_, i=idx: self.responder(i == correcta))
            ops_box.append(btn)

        self.contenedor.append(ops_box)

    def crear_modo_revelar(self, card: dict):
        caja_rev = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        caja_rev.set_margin_top(12)
        caja_rev.set_vexpand(True)

        box_resp = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box_resp.set_visible(False)
        box_resp.append(Gtk.Separator())
        if cloze.tiene_huecos(card["front"]):
            falta = cloze.respuesta(card["front"])
            texto_resp = f"<b>{falta}</b>" + (f"\n\n{card['back']}" if card.get("back") else "")
        else:
            texto_resp = card.get("back", "")
        lbl_b = Gtk.Label(label=util.to_markup(texto_resp), use_markup=True, wrap=True, xalign=0)
        box_resp.append(lbl_b)
        caja_rev.append(box_resp)

        btn_ver = Gtk.Button(label="Ver respuesta", css_classes=["pill"])
        caja_rev.append(btn_ver)

        caja_voto = Gtk.Box(spacing=12, homogeneous=True)
        caja_voto.set_visible(False)

        btn_no = Gtk.Button(label="No la sabía ✗", css_classes=["destructive-action", "pill"])
        btn_no.connect("clicked", lambda *_: self.responder(False))
        caja_voto.append(btn_no)

        btn_si = Gtk.Button(label="La sabía ✓", css_classes=["suggested-action", "pill"])
        btn_si.connect("clicked", lambda *_: self.responder(True))
        caja_voto.append(btn_si)

        caja_rev.append(caja_voto)

        def al_ver(*_):
            if cloze.tiene_huecos(card["front"]) and getattr(self, "lbl_front", None):
                self.lbl_front.set_markup(util.to_markup(cloze.resaltado(card["front"])))
            box_resp.set_visible(True)
            caja_voto.set_visible(True)
            btn_ver.set_visible(False)

        btn_ver.connect("clicked", al_ver)
        self.contenedor.append(caja_rev)

    def responder(self, acierto: bool):
        if acierto:
            self.aciertos += 1
        self.respuestas.append(acierto)
        self.indice += 1

        if self.indice < len(self.tarjetas):
            self.mostrar_pregunta_actual()
        else:
            self.mostrar_resultado()

    def mostrar_resultado(self):
        while self.contenedor.get_first_child():
            self.contenedor.remove(self.contenedor.get_first_child())

        total = len(self.tarjetas)
        self.barra_progreso.set_fraction(1.0)
        pct = (self.aciertos / total) if total else 0.0
        dominado = pct >= 0.75

        res_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, halign=Gtk.Align.CENTER)
        res_box.set_valign(Gtk.Align.CENTER)
        res_box.set_vexpand(True)

        icono = "trophy-gold-symbolic" if dominado else "book-open-symbolic"
        img = Gtk.Image.new_from_icon_name(icono)
        img.set_pixel_size(64)
        if dominado:
            img.add_css_class("success")
        res_box.append(img)

        titulo = "¡Ya dominas este capítulo!" if dominado else "Te recomendamos leer el capítulo"
        lbl_titulo = Gtk.Label(label=f"<big><b>{titulo}</b></big>", use_markup=True, halign=Gtk.Align.CENTER)
        res_box.append(lbl_titulo)

        porcentaje_txt = f"{int(pct * 100)}%"
        desc = (f"Has acertado {self.aciertos} de {total} ({porcentaje_txt}).\n"
                "Tienes los conceptos claros: te sugerimos saltar la lectura para ahorrar tiempo."
                if dominado else
                f"Has acertado {self.aciertos} de {total} ({porcentaje_txt}).\n"
                "La lectura contiene explicaciones y ejemplos que afianzarán estos conceptos.")

        lbl_desc = Gtk.Label(label=desc, wrap=True, justify=Gtk.Justification.CENTER, max_width_chars=40)
        res_box.append(lbl_desc)

        botones = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        botones.set_margin_top(12)

        if dominado:
            btn_saltar = Gtk.Button(label="Saltar capítulo →", css_classes=["suggested-action", "pill"])
            btn_saltar.connect("clicked", lambda *_: self.ejecutar_saltar())
            botones.append(btn_saltar)

            btn_leer = Gtk.Button(label="Leer de todos modos", css_classes=["flat", "pill"])
            btn_leer.connect("clicked", lambda *_: (self.close(), self.on_leer and self.on_leer()))
            botones.append(btn_leer)
        else:
            btn_comenzar = Gtk.Button(label="Comenzar lectura", css_classes=["suggested-action", "pill"])
            btn_comenzar.connect("clicked", lambda *_: (self.close(), self.on_leer and self.on_leer()))
            botones.append(btn_comenzar)

        res_box.append(botones)
        self.contenedor.append(res_box)

    def ejecutar_saltar(self):
        if self.chapter and self.chapter.get("id"):
            db.mark_read(self.con, self.chapter["id"], leido=True)
        self.close()
        if self.on_saltar:
            self.on_saltar()
