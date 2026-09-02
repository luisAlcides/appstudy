"""Aplicación AppStudy: una sola instancia atiende el popup y la ventana principal."""
import os
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import db, hotkey, ia, pet, respaldo, seed  # noqa: E402
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
        self.add_main_option("pet", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             f"Soltar a {pet.NOMBRE}, la mascota de escritorio", None)
        self.add_main_option("status", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             "Imprimir el estado en JSON (lo usa la extensión de GNOME)",
                             None)
        self.add_main_option("read-card", 0, GLib.OptionFlags.NONE, GLib.OptionArg.STRING,
                             "Abrir en Leer el capítulo que explica esa tarjeta", "ID")
        self.add_main_option("leeches", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             "Abrir la lista de tarjetas que se te atragantan", None)
        self.add_main_option("reload", ord("r"), GLib.OptionFlags.NONE,
                             GLib.OptionArg.NONE,
                             "Reimportar el contenido incluido y refrescar la ventana",
                             None)

    # ------------------------------------------------------------------ arranque

    def do_startup(self):
        Adw.Application.do_startup(self)
        self.con = db.connect()
        seed.ensure_seeded(self.con)
        # Un respaldo al día, al abrir. Si falla no se dice nada: no poder
        # respaldar no debe impedirte estudiar.
        if str(db.get_meta(self.con, "respaldo_auto", "1")) not in ("0", "False"):
            respaldo.auto_si_toca(self.con)
        self.load_css()
        Gtk.Window.set_default_icon_name(ICON_NAME)

        for nombre, cb in (("quit", lambda *_: self.quit()),
                           ("popup", lambda *_: self.show_popup()),
                           ("main", lambda *_: self.show_main_window()),
                           ("reload", lambda *_: self.reload_content()),
                           ("buscar", lambda *_: self.abrir_buscador())):
            a = Gio.SimpleAction.new(nombre, None)
            a.connect("activate", cb)
            self.add_action(a)
        self.set_accels_for_action("app.quit", ["<Control>q"])
        # Recargar: sirve en cualquier ventana de la aplicación, popup incluido
        self.set_accels_for_action("app.reload", ["<Control>r", "F5"])
        self.set_accels_for_action("app.buscar", ["<Control>k"])

    def abrir_buscador(self):
        """Ctrl+K desde donde sea: abre la ventana principal y el buscador."""
        self.show_main_window()
        if self.main_window:
            self.main_window.buscador_global()

    def do_shutdown(self):
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
        if opts.get("pet"):
            # No debería llegar aquí: main() lo atiende antes de arrancar GTK
            self.launch_pet()
            return 0
        if opts.get("reload"):
            cmdline.print_literal(self.reload_content() + "\n")
            return 0
        if "read-card" in opts:
            self.show_reading_for_card(opts["read-card"])
        elif opts.get("leeches"):
            self.show_main_window()
            if self.main_window:
                self.main_window.mostrar_sanguijuelas()
        elif opts.get("popup"):
            self.show_popup(opts.get("deck"))
        else:
            self.show_main_window()
        return 0

    # ------------------------------------------------------------------ ventanas

    def show_popup(self, deck_key=None, level=None, tags=None):
        if self.popup is not None:
            # El atajo pulsado de nuevo trae otra tarjeta en vez de abrir otra ventana
            self.popup.set_filter(deck_key, level, tags)
            self.popup.present()
            return
        self.popup = PopupWindow(self, self.con, deck_key, level, tags)
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
        cap = db.chapter_for_card(self.con, card) if card else None
        self.show_main_window()
        if cap:
            self.main_window.abrir_lectura(cap, buscar=f"{card['front']} {card['back']}")
        else:
            # Sin capítulo que lo explique, al menos se abre la biblioteca
            self.main_window.stack.set_visible_child_name("leer")

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
        env = os.environ.get("APPSTUDY_COMMAND")
        if env:
            return env
        script = Path(sys.argv[0]).resolve()
        if script.name.endswith(".py"):
            return f"{sys.executable} {script} --popup"
        return f"{script} --popup"


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
