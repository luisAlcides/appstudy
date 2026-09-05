"""Aplicación AppStudy: una sola instancia atiende el popup y la ventana principal."""
import os
import sys
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import db, hotkey, ia, nube, pet, respaldo, seed  # noqa: E402
from . import sincronizacion, util  # noqa: E402
from .main_window import MainWindow  # noqa: E402
from .popup import PopupWindow  # noqa: E402

APP_ID = "io.github.appstudy.AppStudy"
# El icono se llama igual que la aplicación: así el escritorio empareja la
# ventana con su lanzador (y con lo que hayas anclado al dock).
ICON_NAME = APP_ID


class AppStudy(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.con = None
        self.main_window = None
        self.popup = None
        self.add_main_option("popup", ord("p"), GLib.OptionFlags.NONE,
                             GLib.OptionArg.NONE, "Abrir el popup de estudio", None)
        self.add_main_option("deck", ord("d"), GLib.OptionFlags.NONE,
                             GLib.OptionArg.STRING, "Limitar a un mazo (clave)", "MAZO")
        self.add_main_option("install-hotkey", 0, GLib.OptionFlags.NONE,
                             GLib.OptionArg.STRING,
                             "Registrar el atajo global (ej. '<Super><Shift>e')", "ATAJO")
        self.add_main_option("install-capture-hotkey", 0, GLib.OptionFlags.NONE,
                             GLib.OptionArg.STRING,
                             "Registrar el atajo global de captura rápida", "ATAJO")
        self.add_main_option("capture", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             "Abrir la captura rápida de una tarjeta", None)
        self.add_main_option("pet", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             f"Soltar a {pet.NOMBRE}, la mascota de escritorio", None)
        self.add_main_option("status", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             "Imprimir el estado en JSON (lo usa la extensión de GNOME)",
                             None)
        self.add_main_option("read-card", 0, GLib.OptionFlags.NONE, GLib.OptionArg.STRING,
                             "Abrir en Leer el capítulo que explica esa tarjeta", "ID")
        self.add_main_option("leeches", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             "Abrir la lista de tarjetas que se te atragantan", None)
        self.add_main_option("ayuda", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             "Abrir la guía de uso", None)
        self.add_main_option("reload", ord("r"), GLib.OptionFlags.NONE,
                             GLib.OptionArg.NONE,
                             "Reimportar el contenido incluido y refrescar la ventana",
                             None)
        self.add_main_option("say", 0, GLib.OptionFlags.NONE,
                             GLib.OptionArg.STRING,
                             "Leer un texto en voz alta con la voz de Bit", "TEXTO")

    # ------------------------------------------------------------------ arranque

    def do_startup(self):
        Adw.Application.do_startup(self)
        self.abrir_base()
        ajustes_gtk = Gtk.Settings.get_default()
        if ajustes_gtk:
            reducido = str(db.get_meta(self.con, "reduced_motion", "0")).lower()
            ajustes_gtk.set_property("gtk-enable-animations", reducido not in ("1", "true"))
        # Un respaldo al día, al abrir. Si falla no se dice nada: no poder
        # respaldar no debe impedirte estudiar.
        if str(db.get_meta(self.con, "respaldo_auto", "1")) not in ("0", "False"):
            respaldo.auto_si_toca(self.con)
        self.load_css()
        Gtk.Window.set_default_icon_name(ICON_NAME)

        for nombre, cb in (("quit", lambda *_: self.quit()),
                           ("popup", lambda *_: self.show_popup()),
                           ("capture", lambda *_: self.show_capture()),
                           ("main", lambda *_: self.show_main_window()),
                           ("reload", lambda *_: self.reload_content()),
                           ("buscar", lambda *_: self.abrir_buscador()),
                           ("ayuda", lambda *_: self.abrir_ayuda())):
            a = Gio.SimpleAction.new(nombre, None)
            a.connect("activate", cb)
            self.add_action(a)
        self.set_accels_for_action("app.quit", ["<Control>q"])
        # Recargar: sirve en cualquier ventana de la aplicación, popup incluido
        self.set_accels_for_action("app.reload", ["<Control>r", "F5"])
        self.set_accels_for_action("app.buscar", ["<Control>k"])
        self.set_accels_for_action("app.capture", ["<Control><Shift>n"])
        self.set_accels_for_action("app.ayuda", ["F1"])

    def abrir_buscador(self):
        """Ctrl+K desde donde sea: abre la ventana principal y el buscador."""
        self.show_main_window()
        if self.main_window:
            self.main_window.buscador_global()

    def abrir_ayuda(self, key=None):
        """F1 desde donde sea: abre la ventana principal con la guía de uso."""
        self.show_main_window()
        if self.main_window:
            self.main_window.abrir_ayuda(key)

    def do_shutdown(self):
        self.publicar_en_la_nube()
        if self.con:
            cfg = ia.config(self.con)
            if cfg.get("activa"):
                ia.descargar(cfg)
        Adw.Application.do_shutdown(self)

    def load_css(self):
        css = Gtk.CssProvider()
        css.load_from_path(str(Path(__file__).parent / "style.css"))
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_command_line(self, cmdline):
        opts = cmdline.get_options_dict().end().unpack()
        if "install-hotkey" in opts:
            ok, mensaje = hotkey.install(self.launch_command(), opts["install-hotkey"])
            cmdline.print_literal(mensaje + "\n")
            return 0 if ok else 1
        if "install-capture-hotkey" in opts:
            ok, mensaje = hotkey.install(
                self.capture_command(), opts["install-capture-hotkey"],
                slot=hotkey.CAPTURE_SLOT, name=hotkey.CAPTURE_NAME)
            cmdline.print_literal(mensaje + "\n")
            return 0 if ok else 1
        if opts.get("pet"):
            # No debería llegar aquí: main() lo atiende antes de arrancar GTK
            self.launch_pet()
            return 0
        if opts.get("reload"):
            cmdline.print_literal(self.reload_content() + "\n")
            return 0
        if "say" in opts:
            from . import voz
            cfg = voz.config(self.con)
            voz.hablar(opts["say"], cfg)
            return 0
        if "read-card" in opts:
            self.show_reading_for_card(opts["read-card"])
        elif opts.get("leeches"):
            self.show_main_window()
            if self.main_window:
                self.main_window.mostrar_sanguijuelas()
        elif opts.get("ayuda"):
            self.abrir_ayuda()
        elif opts.get("capture"):
            self.show_capture()
        elif opts.get("popup"):
            self.show_popup(opts.get("deck"))
        else:
            self.show_main_window()
        return 0

    # ------------------------------------------------------------------ ventanas

    def show_popup(self, deck_key=None, level=None, tags=None, session_plan=None):
        if self.popup is not None:
            # El atajo pulsado de nuevo trae otra tarjeta en vez de abrir otra ventana
            if session_plan:
                self.popup.begin_session(session_plan, deck_key, level, tags)
            else:
                self.popup.set_filter(deck_key, level, tags)
            self.popup.present()
            return
        self.popup = PopupWindow(self, self.con, deck_key, level, tags, session_plan)
        self.popup.connect("close-request", self.on_popup_closed)
        self.popup.present()

    def on_popup_closed(self, *_):
        self.popup = None
        if self.main_window:
            self.main_window.refresh()
        return False

    def show_main_window(self):
        if self.main_window is None:
            self.main_window = MainWindow(self, self.con)
            self.main_window.connect("close-request", self.on_main_closed)
        self.main_window.refresh()
        self.main_window.present()

    def show_capture(self):
        self.show_main_window()
        if self.main_window:
            self.main_window.captura_rapida()

    def reload_content(self) -> str:
        """Reimporta los mazos y capítulos incluidos y pone al día lo que se ve.

        Es lo que hay detrás de Ctrl+R, de F5 y de `appstudy --reload`: si
        editaste un JSON de `content/`, esto lo mete en la base sin tocar tu
        progreso y refresca la ventana abierta.
        """
        _, nuevas, retiradas, capitulos = seed.load_all(self.con)
        detalle = f"{nuevas} tarjetas nuevas · {capitulos} capítulos"
        if retiradas:
            detalle += f" · {retiradas} retiradas"
        mensaje = f"Contenido actualizado · {detalle}"
        if self.main_window:
            self.main_window.refresh()
            self.main_window.notify_user(mensaje)
        if self.popup:
            self.popup.load_card()      # que la tarjeta a la vista ya sea la nueva
        return mensaje

    def show_reading_for_card(self, card_id):
        """Abre la lectura donde se explica una tarjeta (lo pide Bit desde el globo)."""
        try:
            card = db.card_by_id(self.con, int(card_id))
        except (TypeError, ValueError):
            card = None
        self.show_main_window()
        if card:
            self.main_window.abrir_fuente_tarjeta(card)
        else:
            self.main_window.stack.set_visible_child_name("leer")

    # -------------------------------------------------------------------- nube

    def abrir_base(self):
        """Conecta con la base de la cuenta que tenga la sesión guardada.

        La sesión sobrevive al cierre, así que al arrancar ya se sabe quién
        eres sin preguntar nada: se apunta la base a esa cuenta y se conecta.
        """
        quien = nube.usuario()
        if quien and db.cuenta_activa() != quien["user_id"]:
            db.adoptar_cuenta(quien["user_id"])
            db.usar_cuenta(quien["user_id"])
        self.con = db.connect()
        seed.ensure_seeded(self.con)
        if quien and nube.auto(self.con):
            self.sincronizar_nube_en_silencio()

    def cambiar_cuenta(self, uid: str):
        """Cambia la base local a la de otra cuenta y vuelve a abrir la ventana.

        Las ventanas y la mascota guardan la conexión que reciben al nacer, así
        que cambiar de base pasa por cerrarlas: es un momento, y evita que una
        lista siga enseñando las tarjetas de quien acaba de salir.
        """
        if db.cuenta_activa() == (uid or ""):
            return self.main_window
        if uid:
            db.adoptar_cuenta(uid)
        if self.popup is not None:
            self.popup.destroy()
            self.popup = None
        if self.main_window is not None:
            self.main_window.destroy()
            self.main_window = None
        self.con.close()
        db.usar_cuenta(uid)
        self.con = db.connect()
        seed.ensure_seeded(self.con)
        self.show_main_window()
        self.main_window.stack.set_visible_child_name("ajustes")
        return self.main_window

    def sincronizar_nube_en_silencio(self):
        """Fusiona con la nube al arrancar, sin avisos: si falla, se estudia igual."""
        def trabajo():
            otra = db.connect()           # una conexión de SQLite es de su hilo
            try:
                return sincronizacion.sincronizar_nube(otra)
            finally:
                otra.close()

        def listo(resultado):
            db.set_meta(self.con, "nube_last", int(time.time()))
            if self.main_window:
                self.main_window.refresh()

        util.hilo(trabajo, listo, lambda _e: None, largo=True)

    def publicar_en_la_nube(self):
        """Sube lo estudiado antes de cerrar. Nunca impide salir."""
        if not (self.con and nube.usuario() and nube.auto(self.con)):
            return
        try:
            sincronizacion.publicar_nube(self.con)
        except Exception:                 # sin red se sube en el próximo arranque
            pass

    def on_main_closed(self, *_):
        self.main_window = None
        return False

    # ------------------------------------------------------------------ utilidad

    def launch_pet(self):
        """Arranca la mascota en su propio proceso (necesita el backend X11)."""
        import subprocess
        env = {k: v for k, v in os.environ.items() if k != "GDK_BACKEND"}
        subprocess.Popen([pet.launcher(), "--pet"], env=env, start_new_session=True)

    def launch_command(self) -> str:
        """Comando absoluto que el atajo del escritorio debe ejecutar."""
        return f"{self.base_command()} --popup"

    def capture_command(self) -> str:
        return f"{self.base_command()} --capture"

    def base_command(self) -> str:
        env = os.environ.get("APPSTUDY_COMMAND")
        if env:
            return env.removesuffix(" --popup").removesuffix(" --capture")
        script = Path(sys.argv[0]).resolve()
        if script.name.endswith(".py"):
            return f"{sys.executable} {script}"
        return str(script)


def main():
    # La mascota vive en su propio proceso y con su propio backend gráfico, así
    # que se atiende antes de que GTK abra la pantalla.
    if "--status" in sys.argv or "--pet-off" in sys.argv:
        from .status import run_status
        return run_status(sys.argv)
    if "--pet" in sys.argv:
        from .pet import run_pet
        return run_pet(sys.argv)
    return AppStudy().run(sys.argv)
