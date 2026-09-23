"""La bitácora del taller en pantalla: contar el caso, revisar sus tarjetas.

Tres páginas en un mismo diálogo:

  * **Contar**: una línea (o dictada al micrófono) y Enter. Se guarda al
    instante y el diálogo se cierra: te pueden volver a llamar en cualquier
    momento, así que no se espera a la IA.
  * **Revisar**: las tarjetas que propuso la IA, todas marcadas; quitas las
    malas, corriges el mazo si hace falta y Enter.
  * **Caso**: el registro de una visita, con sus tarjetas y, si la IA no pudo,
    el porqué y un botón para reintentar.

La lógica está en `bitacora`; aquí solo hay widgets.
"""
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from . import bitacora, db, util  # noqa: E402


def generar(ventana, caso_id: int):
    """Lanza la IA para un caso y avisa con un toast cuando haya tarjetas.

    La aplicación se retiene mientras tanto: si cierras la ventana antes de que
    el modelo termine, las tarjetas no se pierden por el camino.
    """
    app = ventana.get_application()

    def soltar():
        if app:
            app.release()

    def listo(caso):
        soltar()
        n = len(caso["propuestas"])
        toast = Adw.Toast(title=f"🛠️ {n} tarjetas de {caso['equipo'] or 'tu caso'} listas",
                          button_label="Revisar", timeout=8)
        toast.connect("button-clicked", lambda *_: abrir(ventana, caso["id"]))
        ventana.toast.add_toast(toast)

    def mal(error):
        soltar()
        ventana.notify_user(f"La nota está guardada; las tarjetas, pendientes: {error}")

    if bitacora.lanzar(ventana.con, caso_id, listo, mal):
        if app:
            app.hold()
        return True
    return False


def abrir(ventana, caso_id: int | None = None):
    """Abre la bitácora: la captura, o directamente un caso concreto."""
    anterior = getattr(ventana, "_bitacora_dialog", None)
    if anterior is not None:
        anterior.close()
    dlg = BitacoraDialog(ventana, caso_id)
    ventana._bitacora_dialog = dlg
    dlg.connect("closed", lambda *_: setattr(ventana, "_bitacora_dialog", None))
    dlg.present(ventana)
    return dlg


class BitacoraDialog(Adw.Dialog):
    def __init__(self, ventana, caso_id=None):
        super().__init__(title="Bitácora del taller")
        self.ventana = ventana
        self.con = ventana.con
        self.grabador = None
        self.set_content_width(600)
        self.set_content_height(620)
        self.nav = Adw.NavigationView()
        self.set_child(self.nav)
        self.nav.add(self.pagina_contar())
        if caso_id is not None:
            c = bitacora.caso(self.con, int(caso_id))
            if c:
                self.nav.push(self.pagina_revisar(c) if c["estado"] == "propuesto"
                              else self.pagina_caso(c))
        self.connect("closed", lambda *_: self.parar_micro())

    # ------------------------------------------------------------ contar

    def pagina_contar(self):
        page = Adw.PreferencesPage()
        grupo = Adw.PreferencesGroup(
            title="¿Qué equipo llegó y qué tenía?",
            description="Una línea basta: «CAT 320D, fuga en el cilindro del brazo, "
                        "se cambió el sello». Enter y sigues con lo tuyo; las "
                        "tarjetas del concepto de fondo te esperan después.")
        self.entrada = Adw.EntryRow(title="Equipo y falla", show_apply_button=False)
        self.entrada.connect("entry-activated", lambda *_: self.guardar())
        self.micro = Gtk.Button(icon_name="audio-input-microphone-symbolic",
                                valign=Gtk.Align.CENTER, css_classes=["flat"],
                                tooltip_text="Dictar la nota")
        self.micro.connect("clicked", lambda *_: self.alternar_micro())
        self.entrada.add_suffix(self.micro)
        grupo.add(self.entrada)
        page.add(grupo)

        revisar = bitacora.por_revisar(self.con)
        if revisar:
            g = Adw.PreferencesGroup(title="Tarjetas por revisar")
            for c in revisar:
                g.add(self.fila_caso(c, f"{len(c['propuestas'])} tarjetas propuestas"))
            page.add(g)
        recientes = [c for c in bitacora.casos(self.con, 8) if c["estado"] != "propuesto"]
        if recientes:
            g = Adw.PreferencesGroup(title="Últimos casos",
                                     description="Ctrl+K busca en todos por equipo o falla.")
            for c in recientes:
                g.add(self.fila_caso(c))
            page.add(g)

        guardar = Gtk.Button(label="Guardar", css_classes=["suggested-action"])
        guardar.connect("clicked", lambda *_: self.guardar())
        header = Adw.HeaderBar()
        header.pack_end(guardar)
        tv = Adw.ToolbarView()
        tv.add_top_bar(header)
        tv.set_content(page)
        GLib.timeout_add(150, lambda: (self.entrada.grab_focus(), False)[1])
        return Adw.NavigationPage(title="Bitácora del taller", child=tv)

    def fila_caso(self, c, detalle=None):
        estado = {"pendiente": "⏳ esperando a la IA", "generando": "⏳ pensando tarjetas…",
                  "listo": "✓"}.get(c["estado"], "")
        fila = Adw.ActionRow(title=GLib.markup_escape_text(bitacora.titulo(c)),
                             subtitle=GLib.markup_escape_text(detalle or c["texto"][:90]),
                             activatable=True)
        if estado and not detalle:
            fila.add_suffix(Gtk.Label(label=estado, css_classes=["dim-label"]))
        fila.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
        fila.connect("activated", lambda *_: self.ir_a(c["id"]))
        return fila

    def ir_a(self, caso_id):
        c = bitacora.caso(self.con, caso_id)
        if c:
            self.nav.push(self.pagina_revisar(c) if c["estado"] == "propuesto"
                          else self.pagina_caso(c))

    def guardar(self):
        texto = self.entrada.get_text().strip()
        if not texto:
            self.entrada.grab_focus()
            return
        self.parar_micro()
        caso = bitacora.registrar(self.con, texto)
        self.close()
        lanzado = generar(self.ventana, caso["id"])
        self.ventana.notify_user(
            f"🛠️ {caso['equipo'] or 'Caso'} guardado"
            + (" · pensando tarjetas…" if lanzado else " · las tarjetas, cuando haya IA"))

    # ------------------------------------------------------------ micrófono

    def alternar_micro(self):
        from . import voz_rec
        if self.grabador and self.grabador.esta_grabando():
            ruta = self.parar_micro()
            if not ruta:
                return
            self.micro.set_sensitive(False)
            self.entrada.set_title("Escuchando lo que dijiste…")

            def fin(dicho):
                self.micro.set_sensitive(True)
                self.entrada.set_title("Equipo y falla")
                if dicho:
                    previo = self.entrada.get_text().strip()
                    self.entrada.set_text(f"{previo} {dicho}".strip())
                    self.entrada.set_position(-1)
                self.entrada.grab_focus()

            def fallo(e):
                self.micro.set_sensitive(True)
                self.entrada.set_title("Equipo y falla")
                self.ventana.notify_user(f"No pude transcribir: {e}")

            util.hilo(lambda: voz_rec.transcribir_audio(ruta, idioma="es"), fin, fallo,
                      largo=True, vivo=self.entrada)
            return
        if not voz_rec.tiene_reconocimiento_voz("es"):
            self.ventana.notify_user("No hay reconocimiento de voz instalado (Vosk o Whisper)")
            return
        self.grabador = self.grabador or voz_rec.GrabadorMicrofono()
        if not self.grabador.iniciar():
            self.ventana.notify_user("No encontré cómo grabar: falta arecord o pw-record")
            return
        self.micro.set_icon_name("media-playback-stop-symbolic")
        self.micro.add_css_class("destructive-action")
        self.micro.set_tooltip_text("Terminar de dictar")
        self.entrada.set_title("Grabando… pulsa ■ al terminar")

    def parar_micro(self):
        if not (self.grabador and self.grabador.esta_grabando()):
            return None
        ruta = self.grabador.detener()
        self.micro.set_icon_name("audio-input-microphone-symbolic")
        self.micro.remove_css_class("destructive-action")
        self.micro.set_tooltip_text("Dictar la nota")
        self.entrada.set_title("Equipo y falla")
        return ruta

    # ------------------------------------------------------------ revisar

    def pagina_revisar(self, c):
        page = Adw.PreferencesPage()
        cabecera = Adw.PreferencesGroup(title=GLib.markup_escape_text(bitacora.titulo(c)),
                                        description=GLib.markup_escape_text(c["texto"]))
        mazos = db.deck_stats(self.con)
        claves = [m["key"] for m in mazos]
        combo = Adw.ComboRow(title="Mazo", model=Gtk.StringList.new(
            [f"{m['icon']} {m['name']}" for m in mazos]))
        if c["deck_key"] in claves:
            combo.set_selected(claves.index(c["deck_key"]))
        cabecera.add(combo)
        page.add(cabecera)

        grupo = Adw.PreferencesGroup(
            title="Tarjetas propuestas",
            description="Quita las que no te sirvan. Las que guardes entran primero "
                        "en tus próximos repasos.")
        marcas = []
        for t in c["propuestas"]:
            check = Gtk.CheckButton(active=True, valign=Gtk.Align.CENTER)
            fila = Adw.ActionRow(title=GLib.markup_escape_text(util.plain(t["front"])),
                                 subtitle=GLib.markup_escape_text(util.plain(t["back"])),
                                 activatable_widget=check, title_lines=0, subtitle_lines=0)
            fila.add_prefix(check)
            grupo.add(fila)
            marcas.append((check, t))
        page.add(grupo)

        guardar = Gtk.Button(css_classes=["suggested-action"])

        def contar(*_):
            n = sum(ch.get_active() for ch, _ in marcas)
            guardar.set_label(f"Guardar {n}" if n else "Solo el registro")
        for ch, _ in marcas:
            ch.connect("toggled", contar)
        contar()

        self.revision = {"caso": c, "marcas": marcas, "combo": combo, "claves": claves}
        guardar.connect("clicked", lambda *_: self.aceptar_revision())

        header = Adw.HeaderBar()
        header.pack_end(guardar)
        tv = Adw.ToolbarView()
        tv.add_top_bar(header)
        tv.set_content(page)
        teclas = Gtk.EventControllerKey()
        teclas.connect("key-pressed", lambda _c, k, *_: (self.aceptar_revision(), True)[1]
                       if Gdk.keyval_name(k) in ("Return", "KP_Enter") else False)
        tv.add_controller(teclas)
        return Adw.NavigationPage(title="Revisar tarjetas", child=tv)

    def aceptar_revision(self) -> list[int]:
        r = self.revision
        elegidas = [t for ch, t in r["marcas"] if ch.get_active()]
        mazo = r["claves"][r["combo"].get_selected()] if r["claves"] else None
        ids = bitacora.aceptar(self.con, r["caso"]["id"], elegidas, deck_key=mazo)
        self.close()
        self.ventana.notify_user(
            f"🛠️ {len(ids)} tarjetas nuevas de {r['caso']['equipo']}" if ids
            else "🛠️ Caso guardado en la bitácora, sin tarjetas")
        if hasattr(self.ventana, "refresh"):
            self.ventana.refresh()
        return ids

    # ------------------------------------------------------------ un caso

    def pagina_caso(self, c):
        page = Adw.PreferencesPage()
        grupo = Adw.PreferencesGroup(title=GLib.markup_escape_text(bitacora.titulo(c)))
        texto = Gtk.Label(label=GLib.markup_escape_text(c["texto"]), wrap=True, xalign=0,
                          selectable=True, css_classes=["body"])
        grupo.add(texto)
        page.add(grupo)

        if c["estado"] in ("pendiente", "generando"):
            g = Adw.PreferencesGroup(title="Tarjetas")
            fila = Adw.ActionRow(
                title="Pensando tarjetas…" if c["estado"] == "generando"
                else "Aún sin tarjetas",
                subtitle=GLib.markup_escape_text(c["motivo"] or "La IA las sacará en cuanto pueda."))
            if c["estado"] == "pendiente":
                otra = Gtk.Button(label="Reintentar", valign=Gtk.Align.CENTER)

                def reintentar(*_):
                    self.close()
                    if generar(self.ventana, c["id"]):
                        self.ventana.notify_user("🛠️ Pensando tarjetas…")
                    else:
                        motivo = (bitacora.caso(self.con, c["id"]) or {}).get("motivo")
                        self.ventana.notify_user(motivo or "Ya se está generando")
                otra.connect("clicked", reintentar)
                fila.add_suffix(otra)
            g.add(fila)
            page.add(g)
        else:
            tarjetas = bitacora.tarjetas_de(self.con, c["id"])
            g = Adw.PreferencesGroup(
                title="Tarjetas que salieron de aquí",
                description="" if tarjetas else "Lo guardaste solo como registro.")
            for t in tarjetas:
                fila = Adw.ActionRow(title=GLib.markup_escape_text(util.plain(t["front"])),
                                     subtitle=GLib.markup_escape_text(util.plain(t["back"])[:120]),
                                     activatable=True)
                fila.connect("activated", lambda *_, i=t["id"]: (
                    self.close(), self.ventana.card_editor(i)))
                g.add(fila)
            page.add(g)

        borrar = Gtk.Button(label="Borrar caso", css_classes=["destructive-action"])

        def confirmar(*_):
            d = Adw.AlertDialog(heading="¿Borrar este caso?",
                                body="Se quita de la bitácora. Las tarjetas que salieron "
                                     "de él se quedan en tu mazo.")
            d.add_response("no", "Cancelar")
            d.add_response("si", "Borrar")
            d.set_response_appearance("si", Adw.ResponseAppearance.DESTRUCTIVE)
            d.connect("response", lambda _d, r: (
                bitacora.borrar(self.con, c["id"]), self.close()) if r == "si" else None)
            d.present(self)
        borrar.connect("clicked", confirmar)

        header = Adw.HeaderBar()
        header.pack_end(borrar)
        tv = Adw.ToolbarView()
        tv.add_top_bar(header)
        tv.set_content(page)
        return Adw.NavigationPage(title=c["equipo"] or "Caso", child=tv)
