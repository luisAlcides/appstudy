"""Modo Examen: simulacros de 20 o 40 preguntas sin calificar hasta el final.

Ofrece una experiencia de evaluación formal con nota global (sobre 10 y porcentaje)
y desglose detallado por nivel y tema. Especialmente optimizado para certificaciones
y niveles de inglés (A2, B1, B2, C1) y aplicable a cualquier mazo.
"""
from __future__ import annotations

import random
import time
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from . import cloze, db, reto, util


def generar_preguntas_examen(con, deck_id: int | None = None, level: int | None = None,
                             n: int = 20) -> list[dict]:
    """Genera n preguntas equilibradas para el simulacro de examen."""
    where = "1=1"
    args: list = []
    if deck_id:
        where += " AND c.deck_id=?"
        args.append(deck_id)
    if level:
        where += " AND c.level=?"
        args.append(level)

    filas = con.execute(
        f"""SELECT c.*, d.name AS deck_name, d.key AS deck_key, d.color AS deck_color,
                   d.icon AS deck_icon, d.levels AS deck_levels
            FROM cards c JOIN decks d ON d.id=c.deck_id
            WHERE {where} AND LENGTH(c.back) > 0""",
        args).fetchall()

    if not filas:
        return []

    candidatas = [dict(f) for f in filas]
    # Si hay suficientes preguntas de distintos niveles, equilibrar la muestra
    niveles = sorted({c["level"] for c in candidatas if c.get("level")})
    preguntas = []

    if len(niveles) > 1 and not level:
        por_nivel = n // len(niveles)
        for niv in niveles:
            grupo = [c for c in candidatas if c["level"] == niv]
            random.seed(int(time.time() * 1000) % 100000 + niv)
            preguntas.extend(random.sample(grupo, min(len(grupo), por_nivel)))

    faltan = n - len(preguntas)
    restantes = [c for c in candidatas if c["id"] not in {p["id"] for p in preguntas}]
    if faltan > 0 and restantes:
        random.seed(int(time.time() * 1000) % 99991)
        preguntas.extend(random.sample(restantes, min(len(restantes), faltan)))

    random.shuffle(preguntas)

    # Preparar opciones para cada pregunta
    items = []
    for c in preguntas[:n]:
        item = {
            "id": c["id"],
            "front": c["front"],
            "back": c["back"],
            "level": c["level"],
            "tags": c.get("tags") or "",
            "deck_name": c.get("deck_name") or "",
            "deck_levels": c.get("deck_levels") or "",
            "kind": c.get("kind") or "card",
        }
        # Intentar crear opciones de reto
        r = reto.preparar(con, c)
        if r and r.get("formato") in ("opciones", "invertido") and r.get("opciones"):
            item["opciones"] = list(r["opciones"])
            item["correcta"] = r["correcta"]
            item["pregunta"] = r.get("pregunta") or c["front"]
        else:
            # Generar distractores a partir de otras tarjetas del mismo mazo
            distractores = reto.distractores(con, c, 3)
            opciones = [util.plain(c["back"])] + [util.plain(d) for d in distractores]
            if len(opciones) < 2:
                opciones.append("Ninguna de las anteriores")
            random.shuffle(opciones)
            item["opciones"] = opciones
            item["correcta"] = opciones.index(util.plain(c["back"]))
            item["pregunta"] = c["front"]

        if cloze.tiene_huecos(item["pregunta"]):
            item["pregunta"] = cloze.enmascarar(item["pregunta"])

        items.append(item)

    return items


class ExamenSesion:
    """Gestiona el estado y la puntuación de un simulacro de examen."""

    def __init__(self, preguntas: list[dict]):
        self.preguntas = preguntas
        self.respuestas: dict[int, int | None] = {i: None for i in range(len(preguntas))}
        self.marcadas: set[int] = set()
        self.tiempo_inicio = time.time()
        self.tiempo_fin = 0.0

    def responder(self, idx: int, opcion_idx: int):
        self.respuestas[idx] = opcion_idx

    def alternar_marcada(self, idx: int) -> bool:
        if idx in self.marcadas:
            self.marcadas.remove(idx)
            return False
        self.marcadas.add(idx)
        return True

    def evaluar(self) -> dict:
        if not self.tiempo_fin:
            self.tiempo_fin = time.time()
        duracion = max(1.0, self.tiempo_fin - self.tiempo_inicio)

        total = len(self.preguntas)
        aciertos = 0
        por_nivel: dict[int, dict] = {}
        por_etiqueta: dict[str, dict] = {}
        falladas: list[dict] = []

        for idx, p in enumerate(self.preguntas):
            correcta = p["correcta"]
            resp = self.respuestas.get(idx)
            es_acierto = (resp is not None and resp == correcta)
            if es_acierto:
                aciertos += 1
            else:
                falladas.append({
                    "pregunta": p,
                    "indice": idx,
                    "elegida": p["opciones"][resp] if resp is not None else None,
                    "correcta": p["opciones"][correcta],
                })

            # Nivel
            lvl = p.get("level", 1)
            if lvl not in por_nivel:
                por_nivel[lvl] = {"total": 0, "aciertos": 0, "deck_levels": p.get("deck_levels")}
            por_nivel[lvl]["total"] += 1
            if es_acierto:
                por_nivel[lvl]["aciertos"] += 1

            # Etiquetas
            tags = [t.strip() for t in p.get("tags", "").split(",") if t.strip()]
            for t in tags[:2]:
                if t not in por_etiqueta:
                    por_etiqueta[t] = {"total": 0, "aciertos": 0}
                por_etiqueta[t]["total"] += 1
                if es_acierto:
                    por_etiqueta[t]["aciertos"] += 1

        pct = (aciertos / total * 100.0) if total else 0.0
        nota_10 = round((aciertos / total * 10.0) if total else 0.0, 1)

        return {
            "total": total,
            "aciertos": aciertos,
            "pct": round(pct, 1),
            "nota_10": nota_10,
            "aprobado": pct >= 65.0,
            "duracion": duracion,
            "por_nivel": por_nivel,
            "por_etiqueta": por_etiqueta,
            "falladas": falladas,
        }


class ExamenWindow(Adw.Window):
    """Interfaz gráfica del simulacro de examen."""

    def __init__(self, parent_window, con, deck_id: int | None = None, level: int | None = None,
                 n: int = 20, deck_nombre: str = "General", on_close_cb=None):
        super().__init__(modal=True, transient_for=parent_window)
        self.set_title(f"Simulacro de Examen · {deck_nombre}")
        self.set_default_size(780, 620)

        self.con = con
        self.on_close_cb = on_close_cb
        self.preguntas = generar_preguntas_examen(con, deck_id, level, n)
        self.sesion = ExamenSesion(self.preguntas)
        self.indice = 0
        self.timer_id = None

        self.construir_ui()
        self.iniciar_timer()

    def construir_ui(self):
        self.box_raiz = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Cabecera
        self.header = Adw.HeaderBar()
        self.lbl_timer = Gtk.Label(label="⏱ 00:00", css_classes=["caption", "as-dim"])
        self.header.pack_start(self.lbl_timer)

        self.btn_entregar = Gtk.Button(label="Entregar examen", css_classes=["suggested-action", "pill"])
        self.btn_entregar.connect("clicked", lambda *_: self.confirmar_entrega())
        self.header.pack_end(self.btn_entregar)

        self.box_raiz.append(self.header)

        if not self.preguntas:
            aviso = Adw.StatusPage(
                icon_name="dialog-information-symbolic",
                title="Sin preguntas disponibles",
                description="No hay suficientes tarjetas en este mazo para estructurar un examen.",
            )
            self.box_raiz.append(aviso)
            self.set_content(self.box_raiz)
            return

        # Barra de progreso superior
        self.progreso = Gtk.ProgressBar(css_classes=["as-progress"])
        self.box_raiz.append(self.progreso)

        # Zona central
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_vexpand(True)

        self.vista_examen = self.construir_vista_pregunta()
        self.stack.add_named(self.vista_examen, "pregunta")

        self.vista_resultado = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.stack.add_named(self.vista_resultado, "resultado")

        self.box_raiz.append(self.stack)

        # Barra de navegación inferior
        self.barra_inferior = Gtk.Box(spacing=10)
        self.barra_inferior.set_margin_start(20)
        self.barra_inferior.set_margin_end(20)
        self.barra_inferior.set_margin_bottom(16)
        self.barra_inferior.set_margin_top(12)

        self.btn_ant = Gtk.Button(label="← Anterior", css_classes=["pill"])
        self.btn_ant.connect("clicked", lambda *_: self.navegar(-1))
        self.barra_inferior.append(self.btn_ant)

        self.btn_marcar = Gtk.Button(label="🚩 Marcar para revisar", css_classes=["flat", "pill"])
        self.btn_marcar.connect("clicked", lambda *_: self.toggle_marcar())
        self.barra_inferior.append(self.btn_marcar)

        self.barra_inferior.append(Gtk.Box(hexpand=True))

        self.lbl_contador = Gtk.Label(label="", css_classes=["caption", "as-dim"])
        self.barra_inferior.append(self.lbl_contador)

        self.btn_sig = Gtk.Button(label="Siguiente →", css_classes=["pill"])
        self.btn_sig.connect("clicked", lambda *_: self.navegar(1))
        self.barra_inferior.append(self.btn_sig)

        self.box_raiz.append(self.barra_inferior)
        self.set_content(self.box_raiz)
        self.mostrar_pregunta(0)

    def construir_vista_pregunta(self) -> Gtk.Widget:
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.box_pregunta = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.box_pregunta.set_margin_top(20)
        self.box_pregunta.set_margin_bottom(20)
        self.box_pregunta.set_margin_start(24)
        self.box_pregunta.set_margin_end(24)
        scroll.set_child(self.box_pregunta)
        return scroll

    def iniciar_timer(self):
        def _tick():
            transcurrido = int(time.time() - self.sesion.tiempo_inicio)
            mins = transcurrido // 60
            segs = transcurrido % 60
            self.lbl_timer.set_label(f"⏱ {mins:02d}:{segs:02d}")
            return True
        self.timer_id = GLib.timeout_add_seconds(1, _tick)

    def mostrar_pregunta(self, idx: int):
        self.indice = max(0, min(len(self.preguntas) - 1, idx))
        total = len(self.preguntas)
        self.progreso.set_fraction((self.indice + 1) / float(total))
        self.lbl_contador.set_label(f"Pregunta {self.indice + 1} de {total}")
        self.btn_ant.set_sensitive(self.indice > 0)
        self.btn_sig.set_sensitive(self.indice < total - 1)

        marcada = self.indice in self.sesion.marcadas
        self.btn_marcar.set_label("🚩 Marcada" if marcada else "🏳 Marcar para revisar")
        self.btn_marcar.set_css_classes(["pill", "warning"] if marcada else ["flat", "pill"])

        # Reconstruir tarjeta y opciones
        while self.box_pregunta.get_first_child():
            self.box_pregunta.remove(self.box_pregunta.get_first_child())

        p = self.preguntas[self.indice]

        # Fila de etiquetas y nivel
        meta_fila = Gtk.Box(spacing=8)
        if p.get("deck_name"):
            meta_fila.append(Gtk.Label(label=p["deck_name"], css_classes=["as-chip-mazo"]))
        if p.get("level"):
            nom_nivel = db.level_name(p.get("deck_levels", ""), p["level"])
            meta_fila.append(Gtk.Label(label=f"Nivel {nom_nivel}", css_classes=["caption", "as-dim"]))
        self.box_pregunta.append(meta_fila)

        # Enunciado
        card_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["as-card"])
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        inner.set_margin_top(16)
        inner.set_margin_bottom(16)
        inner.set_margin_start(16)
        inner.set_margin_end(16)
        lbl_q = Gtk.Label(label=util.to_markup(p["pregunta"]), use_markup=True, wrap=True,
                          xalign=0, css_classes=["as-bubble-front"])
        inner.append(lbl_q)
        card_box.append(inner)
        self.box_pregunta.append(card_box)

        # Opciones A, B, C, D
        caja_ops = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        caja_ops.set_margin_top(8)

        seleccionada = self.sesion.respuestas.get(self.indice)
        for i, op in enumerate(p["opciones"]):
            btn = Gtk.Button(css_classes=["flat", "card"])
            if seleccionada == i:
                btn.add_css_class("suggested-action")
            caja_b = Gtk.Box(spacing=10)
            caja_b.set_margin_top(12)
            caja_b.set_margin_bottom(12)
            caja_b.set_margin_start(14)
            caja_b.set_margin_end(14)

            letra = chr(65 + i)
            lbl_l = Gtk.Label(label=f"<b>{letra}</b>", use_markup=True)
            caja_b.append(lbl_l)
            caja_b.append(Gtk.Label(label=op, wrap=True, xalign=0))
            btn.set_child(caja_b)

            btn.connect("clicked", lambda *_, opt_idx=i: self.elegir_opcion(opt_idx))
            caja_ops.append(btn)

        self.box_pregunta.append(caja_ops)

    def elegir_opcion(self, opt_idx: int):
        self.sesion.responder(self.indice, opt_idx)
        # Avanzar automáticamente a la siguiente si no es la última
        if self.indice < len(self.preguntas) - 1:
            self.navegar(1)
        else:
            self.mostrar_pregunta(self.indice)

    def navegar(self, paso: int):
        self.mostrar_pregunta(self.indice + paso)

    def toggle_marcar(self):
        marcada = self.sesion.alternar_marcada(self.indice)
        self.btn_marcar.set_label("🚩 Marcada" if marcada else "🏳 Marcar para revisar")
        self.btn_marcar.set_css_classes(["pill", "warning"] if marcada else ["flat", "pill"])

    def confirmar_entrega(self):
        sin_responder = sum(1 for v in self.sesion.respuestas.values() if v is None)
        msg = "¿Deseas finalizar y calificar el examen ahora?"
        if sin_responder > 0:
            msg = f"Aún tienes {sin_responder} pregunta{'s' if sin_responder > 1 else ''} sin responder. ¿Deseas entregar el examen?"

        dlg = Adw.AlertDialog(heading="Entregar examen", body=msg)
        dlg.add_response("cancelar", "Seguir revisando")
        dlg.add_response("entregar", "Entregar y calificar")
        dlg.set_response_appearance("entregar", Adw.ResponseAppearance.SUGGESTED)

        def _al_responder(_d, resp):
            if resp == "entregar":
                self.finalizar_examen()
        dlg.connect("response", _al_responder)
        dlg.present(self)

    def finalizar_examen(self):
        if self.timer_id:
            GLib.source_remove(self.timer_id)
            self.timer_id = None

        self.btn_entregar.set_visible(False)
        self.barra_inferior.set_visible(False)
        self.progreso.set_visible(False)

        res = self.sesion.evaluar()
        self.mostrar_resultados(res)
        self.stack.set_visible_child_name("resultado")

    def mostrar_resultados(self, res: dict):
        while self.vista_resultado.get_first_child():
            self.vista_resultado.remove(self.vista_resultado.get_first_child())

        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        caja.set_margin_top(24)
        caja.set_margin_bottom(24)
        caja.set_margin_start(24)
        caja.set_margin_end(24)

        # Tarjeta de Nota Global
        aprobado = res["aprobado"]
        caja_nota = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["as-card"])
        inner_nota = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, halign=Gtk.Align.CENTER)
        inner_nota.set_margin_top(20)
        inner_nota.set_margin_bottom(20)

        icono = "trophy-gold-symbolic" if aprobado else "dialog-warning-symbolic"
        img = Gtk.Image.new_from_icon_name(icono)
        img.set_pixel_size(48)
        if aprobado:
            img.add_css_class("success")
        inner_nota.append(img)

        lbl_puntos = Gtk.Label(label=f"<span size='xx-large'><b>{res['nota_10']} / 10</b></span>",
                               use_markup=True)
        inner_nota.append(lbl_puntos)

        estado = "¡Aprobado! 🎉" if aprobado else "Requiere repaso"
        lbl_estado = Gtk.Label(label=f"{estado} · {res['aciertos']} de {res['total']} ({res['pct']}%)",
                               css_classes=["as-dim"])
        inner_nota.append(lbl_estado)
        caja_nota.append(inner_nota)
        caja.append(caja_nota)

        # Desglose por niveles
        if res.get("por_nivel"):
            caja.append(Gtk.Label(label="Desglose por nivel:", xalign=0, css_classes=["heading"]))
            caja_niveles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            for lvl, datos in sorted(res["por_nivel"].items()):
                nom_lvl = db.level_name(datos.get("deck_levels", ""), lvl)
                pct_lvl = (datos["aciertos"] / datos["total"] * 100.0) if datos["total"] else 0
                fila = Gtk.Box(spacing=12)
                fila.append(Gtk.Label(label=f"Nivel {nom_lvl}", css_classes=["caption"], width_chars=12, xalign=0))
                pbar = Gtk.ProgressBar(fraction=pct_lvl / 100.0, hexpand=True, css_classes=["as-progress"])
                if pct_lvl >= 70:
                    pbar.add_css_class("success")
                fila.append(pbar)
                fila.append(Gtk.Label(label=f"{datos['aciertos']}/{datos['total']} ({int(pct_lvl)}%)",
                                      css_classes=["caption", "as-dim"]))
                caja_niveles.append(fila)
            caja.append(caja_niveles)

        # Preguntas falladas para repasar
        falladas = res.get("falladas", [])
        if falladas:
            caja.append(Gtk.Label(label=f"Preguntas a revisar ({len(falladas)}):", xalign=0, css_classes=["heading"]))
            caja_fallos = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            for f in falladas[:10]:
                c_f = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, css_classes=["as-card"])
                in_f = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                in_f.set_margin_top(10)
                in_f.set_margin_bottom(10)
                in_f.set_margin_start(12)
                in_f.set_margin_end(12)
                in_f.append(Gtk.Label(label=f"<b>{f['pregunta']['pregunta']}</b>", use_markup=True, wrap=True, xalign=0))
                if f["elegida"]:
                    in_f.append(Gtk.Label(label=f"❌ Dijiste: {f['elegida']}", css_classes=["as-dim"], xalign=0))
                else:
                    in_f.append(Gtk.Label(label="⚪ Sin responder", css_classes=["as-dim"], xalign=0))
                in_f.append(Gtk.Label(label=f"✅ Correcta: {f['correcta']}", css_classes=["success"], xalign=0))
                c_f.append(in_f)
                caja_fallos.append(c_f)
            caja.append(caja_fallos)

        # Botón de cierre
        btn_cerrar = Gtk.Button(label="Finalizar y cerrar", css_classes=["suggested-action", "pill"],
                                halign=Gtk.Align.CENTER)
        btn_cerrar.connect("clicked", lambda *_: (self.close(), self.on_close_cb and self.on_close_cb()))
        caja.append(btn_cerrar)

        scroll.set_child(caja)
        self.vista_resultado.append(scroll)
