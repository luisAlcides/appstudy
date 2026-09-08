"""Asistente de bienvenida: temas, ritmo, nivel y una primera sesión lista.

La primera vez que se abre AppStudy hay nueve mazos encendidos, mil quinientas
tarjetas y ningún objetivo. Eso no es un punto de partida, es una biblioteca.
Este asistente pregunta tres cosas —qué quieres estudiar, cuánto tiempo tienes
al día y por dónde empezar— y deja la aplicación configurada para esa persona:
los temas que no eligió apagados, un objetivo diario y un cupo de nuevas acordes
al tiempo real que tiene, y el popup abierto en su primera sesión.

La prueba de nivel es opcional y son tarjetas de verdad: las respuestas pasan
por el planificador como cualquier repaso, así que los ocho minutos que dedica a
la prueba ya cuentan como estudio y no como trámite.

Lo de aquí abajo, hasta la ventana, no sabe de GTK: son las decisiones, y se
prueban solas en tests/test_bienvenida.py.
"""
import json
import random

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from . import db, scheduler, sesiones  # noqa: E402

# Los minutos al día que se ofrecen. Más de tres cuartos de hora no se pregunta:
# quien estudia dos horas ya no necesita que le propongan un plan.
MINUTOS = (5, 15, 25, 45)

# Tarjetas por minuto. Sale del ritmo de los planes de sesión (sesiones.PLANES:
# 8 en 5 minutos, 20 en 15, 35 en 25), redondeado a la baja para que el objetivo
# se cumpla en un día normal y no solo en uno bueno.
POR_MINUTO = 1.4

# De cada tantas tarjetas del objetivo, una puede ser nueva. Una recién
# estrenada se lleva tres o cuatro repasos en su primera semana: si el cupo
# igualara al objetivo, en un mes el día entero sería deuda de los estrenos.
REPASOS_POR_NUEVA = 3

CLAVE_HECHA = "onboarding"
CLAVE_TEMA = "bienvenida_tema"
CLAVE_NIVEL = "bienvenida_nivel"

PREGUNTAS_PRUEBA = 8


# --------------------------------------------------------------------- ritmo

def ritmo(minutos: int) -> dict:
    """Objetivo diario y cupo de nuevas para quien tiene `minutos` al día."""
    objetivo = max(3, round(minutos * POR_MINUTO))
    nuevas = max(1, round(objetivo / REPASOS_POR_NUEVA))
    return {"objetivo": objetivo, "nuevas": nuevas}


def plan_desde_minutos(minutos: int) -> sesiones.Plan:
    """El plan de sesión más cercano al tiempo que dice tener.

    Para 45 minutos devuelve el de 25: es mejor terminar una sesión y decidir
    seguir que abandonar una a medias.
    """
    return min(sesiones.PLANES, key=lambda p: abs(p.minutos - minutos))


# ---------------------------------------------------------------- prueba de nivel

def nivel_sugerido(aciertos: int, total: int, niveles: list) -> int:
    """Por qué nivel empezar según cómo fue la prueba. 1 es el más básico.

    Sin prueba (o sin niveles) se empieza por el principio: es lo que menos daño
    hace. Aprobar raspando deja en el nivel intermedio, y acertar casi todo
    salta al último, que es donde esa persona va a aprender algo.
    """
    ultimo = max(1, len(niveles))
    if total <= 0:
        return 1
    proporcion = aciertos / total
    if proporcion < 0.40:
        return 1
    if proporcion < 0.75:
        return min(2, ultimo)
    return ultimo


def preguntas_de_prueba(con, deck_key: str, cuantas: int = PREGUNTAS_PRUEBA) -> list[dict]:
    """Tarjetas del mazo repartidas entre sus niveles, para tantear por dónde va.

    Reparte a partes iguales entre los niveles que tengan tarjetas y rellena con
    lo que haya si algún nivel se queda corto, de modo que un mazo con tres
    tarjetas devuelva esas tres y no falle. Se dejan fuera las lecciones, que no
    se preguntan, y las que ya se estudiaron: la prueba es para calibrar, y
    preguntar lo ya visto la sesgaría hacia arriba.
    """
    filas = [dict(r) for r in con.execute(
        """SELECT c.*, d.key AS deck_key, d.name AS deck_name, d.levels AS deck_levels,
                  s.due, s.interval, s.ease, s.reps, s.lapses, s.last,
                  s.stability, s.difficulty, s.leech
           FROM cards c JOIN decks d ON d.id=c.deck_id JOIN state s ON s.card_id=c.id
           WHERE d.key=? AND c.kind IN ('card', 'quiz') AND s.reps=0
             AND COALESCE(s.leech, 0)=0
           ORDER BY c.level, c.id""", (deck_key,))]
    if not filas:
        return []

    por_nivel: dict[int, list] = {}
    for f in filas:
        por_nivel.setdefault(f["level"], []).append(f)
    for grupo in por_nivel.values():
        random.shuffle(grupo)

    elegidas: list[dict] = []
    niveles = sorted(por_nivel)
    # Ronda a ronda, una de cada nivel: si un nivel se agota, las que faltan las
    # ponen los demás sin que haya que contar cupos por adelantado.
    while len(elegidas) < cuantas and any(por_nivel[n] for n in niveles):
        for n in niveles:
            if por_nivel[n] and len(elegidas) < cuantas:
                elegidas.append(por_nivel[n].pop())
    return elegidas


# ------------------------------------------------------------------ guardado

def ya_vista(con) -> bool:
    return bool(db.get_meta(con, CLAVE_HECHA))


def saltar(con):
    """Cierra el asistente sin tocar nada de lo que ya estuviera configurado."""
    db.set_meta(con, CLAVE_HECHA, "1")


def arranque(con) -> tuple[str | None, int | None]:
    """Tema y nivel con los que abrir la primera sesión, si hubo asistente."""
    tema = db.get_meta(con, CLAVE_TEMA) or None
    try:
        nivel = int(db.get_meta(con, CLAVE_NIVEL) or 0) or None
    except (TypeError, ValueError):
        nivel = None
    return tema, nivel


def aplicar(con, eleccion: dict):
    """Escribe en la base lo que se eligió en el asistente.

    `eleccion` lleva `temas` (claves de mazo), `principal`, `minutos` y `nivel`.
    Sin ningún tema marcado no se apaga nada: quedarse sin mazos activos deja el
    panel a cero y nada que estudiar, que es peor que tenerlos todos.
    """
    temas = [t for t in eleccion.get("temas", []) if t]
    if temas:
        marcas = ",".join("?" * len(temas))
        con.execute(f"UPDATE decks SET enabled=(key IN ({marcas}))", temas)

    r = ritmo(int(eleccion.get("minutos") or MINUTOS[1]))
    db.set_objetivo_diario(con, r["objetivo"])
    db.set_nuevas_por_dia(con, r["nuevas"])

    db.set_meta(con, CLAVE_TEMA, eleccion.get("principal") or "")
    db.set_meta(con, CLAVE_NIVEL, str(int(eleccion.get("nivel") or 1)))
    db.set_meta(con, CLAVE_HECHA, "1")
    con.commit()


# ------------------------------------------------------------------- ventana

class Asistente(Adw.Window):
    """Los cuatro pasos, en un carrusel que solo avanza cuando toca."""

    def __init__(self, parent, con, al_terminar=None):
        super().__init__(title="Te damos la bienvenida", transient_for=parent,
                         application=parent.get_application(), modal=True,
                         destroy_with_parent=True,
                         default_width=640, default_height=620)
        self.con = con
        self.al_terminar = al_terminar
        self.temas = {}                 # clave de mazo -> Gtk.CheckButton
        self.minutos = MINUTOS[1]
        self.nivel = 1
        self.prueba = []                # tarjetas de la prueba, si se hace
        self.prueba_idx = 0
        self.prueba_aciertos = 0
        self.prueba_visible = False     # ¿se está viendo la respuesta?

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)
        header = Adw.HeaderBar(show_end_title_buttons=False)
        self.titulo = Adw.WindowTitle(title="Te damos la bienvenida",
                                      subtitle="Paso 1 de 4")
        header.set_title_widget(self.titulo)
        saltar_btn = Gtk.Button(label="Saltar")
        saltar_btn.connect("clicked", lambda *_: self.saltar())
        header.pack_end(saltar_btn)
        root.append(header)

        self.carrusel = Gtk.Stack(vexpand=True, transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        root.append(self.carrusel)
        for nombre, constructor in (("temas", self.paso_temas),
                                    ("ritmo", self.paso_ritmo),
                                    ("nivel", self.paso_nivel),
                                    ("listo", self.paso_listo)):
            self.carrusel.add_named(constructor(), nombre)

        pie = Gtk.Box(spacing=10, margin_start=18, margin_end=18,
                      margin_top=6, margin_bottom=16)
        self.atras = Gtk.Button(label="Atrás", sensitive=False)
        self.atras.connect("clicked", lambda *_: self.ir(-1))
        pie.append(self.atras)
        pie.append(Gtk.Box(hexpand=True))
        self.siguiente = Gtk.Button(label="Siguiente",
                                    css_classes=["suggested-action"])
        self.siguiente.connect("clicked", lambda *_: self.ir(1))
        pie.append(self.siguiente)
        root.append(pie)

        self.pasos = ["temas", "ritmo", "nivel", "listo"]
        self.paso = 0
        self.actualizar_pie()

    # ------------------------------------------------------------ estructura

    @staticmethod
    def pagina(titulo, explicacion):
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                       margin_start=24, margin_end=24, margin_top=24, margin_bottom=8)
        caja.append(Gtk.Label(label=titulo, xalign=0, wrap=True,
                              css_classes=["title-2"]))
        caja.append(Gtk.Label(label=explicacion, xalign=0, wrap=True,
                              css_classes=["as-dim"]))
        return caja

    def ir(self, delta):
        if delta > 0 and not self.validar(self.pasos[self.paso]):
            return
        destino = self.paso + delta
        if destino >= len(self.pasos):
            return self.terminar()
        self.paso = max(0, destino)
        nombre = self.pasos[self.paso]
        self.entrar(nombre)
        self.carrusel.set_visible_child_name(nombre)
        self.actualizar_pie()

    def actualizar_pie(self):
        self.titulo.set_subtitle(f"Paso {self.paso + 1} de {len(self.pasos)}")
        self.atras.set_sensitive(self.paso > 0)
        ultimo = self.paso == len(self.pasos) - 1
        self.siguiente.set_label("Empezar mi primera sesión" if ultimo else "Siguiente")

    def validar(self, nombre) -> bool:
        if nombre == "temas" and not self.elegidos():
            self.titulo.set_subtitle("Elige al menos un tema")
            return False
        return True

    def entrar(self, nombre):
        if nombre == "nivel":
            self.preparar_nivel()
        elif nombre == "listo":
            self.pintar_resumen()

    # -------------------------------------------------------------- paso 1

    def paso_temas(self):
        caja = self.pagina(
            "¿Qué quieres estudiar?",
            "Marca los temas que te interesan ahora. Los demás se apagan para que "
            "el repaso no los mezcle; puedes volver a encenderlos cuando quieras "
            "en Ajustes › Temas.")
        lista = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                            css_classes=["boxed-list"])
        for d in db.deck_stats(self.con):
            if not d["total"]:
                continue
            fila = Adw.ActionRow(
                title=d["name"],
                subtitle=f"{d['total']} tarjetas · {d['nuevas'] or 0} sin estrenar")
            fila.add_prefix(Gtk.Label(label=d["icon"]))
            check = Gtk.CheckButton(valign=Gtk.Align.CENTER)
            check.connect("toggled", lambda *_: self.titulo.set_subtitle(
                f"Paso {self.paso + 1} de {len(self.pasos)}"))
            fila.add_suffix(check)
            fila.set_activatable_widget(check)
            self.temas[d["key"]] = check
            lista.append(fila)
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(lista)
        caja.append(scroll)
        return caja

    def elegidos(self) -> list[str]:
        return [k for k, c in self.temas.items() if c.get_active()]

    def principal(self) -> str:
        elegidos = self.elegidos()
        return elegidos[0] if elegidos else ""

    # -------------------------------------------------------------- paso 2

    def paso_ritmo(self):
        caja = self.pagina(
            "¿Cuánto tiempo tienes al día?",
            "Con eso se calcula tu objetivo diario y cuántas tarjetas nuevas dejar "
            "entrar. Un cupo de nuevas bajo es lo que evita que dentro de tres "
            "semanas te vuelvan todas juntas.")
        grupo = None
        for m in MINUTOS:
            r = ritmo(m)
            fila = Adw.ActionRow(
                title=f"{m} minutos al día",
                subtitle=f"objetivo de {r['objetivo']} repasos · hasta {r['nuevas']} "
                         "tarjetas nuevas al día")
            radio = Gtk.CheckButton(valign=Gtk.Align.CENTER, group=grupo)
            grupo = grupo or radio
            radio.set_active(m == self.minutos)
            radio.connect("toggled", self.on_minutos, m)
            fila.add_suffix(radio)
            fila.set_activatable_widget(radio)
            caja.append(self._en_lista(fila))
        return caja

    @staticmethod
    def _en_lista(fila):
        lista = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                            css_classes=["boxed-list"])
        lista.append(fila)
        return lista

    def on_minutos(self, radio, minutos):
        if radio.get_active():
            self.minutos = minutos

    # -------------------------------------------------------------- paso 3

    def paso_nivel(self):
        caja = self.pagina(
            "¿Por dónde empezamos?",
            "Puedes hacer una prueba corta con tarjetas de verdad —cuentan como "
            "repaso, no se pierden— o elegir el nivel a mano.")
        self.nivel_lista = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                                       css_classes=["boxed-list"])
        caja.append(self.nivel_lista)

        self.prueba_btn = Gtk.Button(label=f"Hacer la prueba ({PREGUNTAS_PRUEBA} preguntas)",
                                     halign=Gtk.Align.CENTER,
                                     css_classes=["pill"])
        self.prueba_btn.connect("clicked", lambda *_: self.empezar_prueba())
        caja.append(self.prueba_btn)

        self.prueba_caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                                   visible=False, vexpand=True)
        self.prueba_progreso = Gtk.Label(xalign=0, css_classes=["as-dim"])
        self.prueba_texto = Gtk.Label(xalign=0, wrap=True, vexpand=True,
                                      valign=Gtk.Align.CENTER,
                                      css_classes=["title-3"])
        self.prueba_caja.append(self.prueba_progreso)
        self.prueba_caja.append(self.prueba_texto)
        botones = Gtk.Box(spacing=10, homogeneous=True)
        self.ver_btn = Gtk.Button(label="Ver respuesta")
        self.ver_btn.connect("clicked", lambda *_: self.mostrar_respuesta())
        self.fallo_btn = Gtk.Button(label="No la sabía", visible=False)
        self.fallo_btn.connect("clicked", lambda *_: self.responder(False))
        self.acierto_btn = Gtk.Button(label="La sabía", visible=False,
                                      css_classes=["suggested-action"])
        self.acierto_btn.connect("clicked", lambda *_: self.responder(True))
        for b in (self.ver_btn, self.fallo_btn, self.acierto_btn):
            botones.append(b)
        self.prueba_caja.append(botones)
        # Arrepentirse a mitad no puede dejar encerrado: lo respondido hasta
        # aquí ya cuenta como repaso, solo se deja de calibrar el nivel.
        dejar = Gtk.Button(label="Dejar la prueba y elegir a mano",
                           halign=Gtk.Align.CENTER,
                           css_classes=["flat", "as-dim"])
        dejar.connect("clicked", lambda *_: self.dejar_prueba())
        self.prueba_caja.append(dejar)
        caja.append(self.prueba_caja)
        return caja

    def dejar_prueba(self):
        self.prueba_caja.set_visible(False)
        self.prueba_btn.set_visible(True)
        self.prueba_btn.set_sensitive(True)
        self.siguiente.set_sensitive(True)

    def niveles_del_tema(self) -> list:
        fila = self.con.execute("SELECT levels FROM decks WHERE key=?",
                                (self.principal(),)).fetchone()
        try:
            return json.loads(fila["levels"]) if fila else []
        except (ValueError, TypeError):
            return []

    def preparar_nivel(self):
        """Se rehace al entrar: los niveles dependen del tema que haya elegido."""
        while (c := self.nivel_lista.get_first_child()) is not None:
            self.nivel_lista.remove(c)
        niveles = self.niveles_del_tema() or ["Básico"]
        self.nivel = min(self.nivel, len(niveles))
        grupo = None
        self.nivel_radios = []
        for i, nombre in enumerate(niveles, start=1):
            fila = Adw.ActionRow(title=nombre)
            radio = Gtk.CheckButton(valign=Gtk.Align.CENTER, group=grupo)
            grupo = grupo or radio
            radio.set_active(i == self.nivel)
            radio.connect("toggled", self.on_nivel, i)
            fila.add_suffix(radio)
            fila.set_activatable_widget(radio)
            self.nivel_radios.append(radio)
            self.nivel_lista.append(fila)

    def on_nivel(self, radio, nivel):
        if radio.get_active():
            self.nivel = nivel

    def empezar_prueba(self):
        self.prueba = preguntas_de_prueba(self.con, self.principal(), PREGUNTAS_PRUEBA)
        if not self.prueba:
            self.prueba_btn.set_label("Este tema no tiene tarjetas sin estrenar")
            self.prueba_btn.set_sensitive(False)
            return
        self.prueba_idx = self.prueba_aciertos = 0
        self.prueba_btn.set_visible(False)
        self.prueba_caja.set_visible(True)
        self.siguiente.set_sensitive(False)
        self.pintar_pregunta()

    def pintar_pregunta(self):
        carta = self.prueba[self.prueba_idx]
        self.prueba_visible = False
        self.prueba_progreso.set_label(
            f"Pregunta {self.prueba_idx + 1} de {len(self.prueba)} · "
            f"{self.prueba_aciertos} acertadas")
        self.prueba_texto.set_label(carta["front"])
        self.ver_btn.set_visible(True)
        self.fallo_btn.set_visible(False)
        self.acierto_btn.set_visible(False)

    def mostrar_respuesta(self):
        carta = self.prueba[self.prueba_idx]
        respuesta = carta["back"] or self.opcion_correcta(carta)
        self.prueba_texto.set_label(f"{carta['front']}\n\n{respuesta}")
        self.prueba_visible = True
        self.ver_btn.set_visible(False)
        self.fallo_btn.set_visible(True)
        self.acierto_btn.set_visible(True)

    @staticmethod
    def opcion_correcta(carta) -> str:
        try:
            opciones = json.loads(carta["choices"] or "[]")
            return opciones[carta["answer"]]
        except (ValueError, TypeError, IndexError):
            return "(sin respuesta)"

    def responder(self, acerto: bool):
        """Califica de verdad: la prueba es estudio, no un cuestionario aparte."""
        carta = self.prueba[self.prueba_idx]
        scheduler.apply_review(self.con, carta["id"],
                               scheduler.GOOD if acerto else scheduler.AGAIN)
        self.prueba_aciertos += int(acerto)
        self.prueba_idx += 1
        if self.prueba_idx >= len(self.prueba):
            return self.terminar_prueba()
        self.pintar_pregunta()

    def terminar_prueba(self):
        niveles = self.niveles_del_tema() or ["Básico"]
        self.nivel = nivel_sugerido(self.prueba_aciertos, len(self.prueba), niveles)
        for i, radio in enumerate(self.nivel_radios, start=1):
            radio.set_active(i == self.nivel)
        self.prueba_caja.set_visible(False)
        self.prueba_btn.set_visible(True)
        self.prueba_btn.set_sensitive(False)
        self.prueba_btn.set_label(
            f"{self.prueba_aciertos} de {len(self.prueba)} · empezamos por "
            f"{niveles[self.nivel - 1]}")
        self.siguiente.set_sensitive(True)

    # -------------------------------------------------------------- paso 4

    def paso_listo(self):
        caja = self.pagina("Todo listo", "Esto es lo que queda configurado. "
                                         "Cualquier número se cambia después en Ajustes.")
        self.resumen = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                                   css_classes=["boxed-list"])
        caja.append(self.resumen)
        return caja

    def pintar_resumen(self):
        while (c := self.resumen.get_first_child()) is not None:
            self.resumen.remove(c)
        r = ritmo(self.minutos)
        plan = plan_desde_minutos(self.minutos)
        niveles = self.niveles_del_tema() or ["Básico"]
        nombres = {d["key"]: d["name"] for d in db.deck_stats(self.con)}
        elegidos = ", ".join(nombres.get(k, k) for k in self.elegidos())
        for titulo, sub in (
                ("Temas activos", elegidos),
                ("Tu ritmo", f"{self.minutos} minutos al día · objetivo de "
                             f"{r['objetivo']} repasos · hasta {r['nuevas']} nuevas"),
                ("Empiezas por", f"{niveles[self.nivel - 1]} de "
                                 f"{nombres.get(self.principal(), self.principal())}"),
                ("Primera sesión", f"{plan.nombre} · {plan.minutos} min · "
                                   f"hasta {plan.tarjetas} tarjetas")):
            fila = Adw.ActionRow(title=titulo, subtitle=sub)
            fila.set_subtitle_lines(2)
            self.resumen.append(fila)

    # -------------------------------------------------------------- cerrar

    def saltar(self):
        saltar(self.con)
        self.close()
        if self.al_terminar:
            self.al_terminar(None)

    def terminar(self):
        aplicar(self.con, {"temas": self.elegidos(), "principal": self.principal(),
                           "minutos": self.minutos, "nivel": self.nivel})
        arranque_ = {"deck_key": self.principal(), "level": self.nivel,
                     "session_plan": plan_desde_minutos(self.minutos)}
        self.close()
        if self.al_terminar:
            # Un respiro antes de abrir el popup: si se presenta mientras esta
            # ventana se está cerrando, GTK lo deja detrás de la principal.
            GLib.idle_add(self.al_terminar, arranque_)


def mostrar_si_toca(parent, con, al_terminar=None) -> bool:
    """Presenta el asistente si es el primer arranque. Devuelve si lo presentó."""
    if ya_vista(con):
        return False
    Asistente(parent, con, al_terminar).present()
    return True
