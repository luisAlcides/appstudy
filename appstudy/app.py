"""Aplicación AppStudy: una sola instancia atiende el popup y la ventana principal."""
import os
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import db, hotkey, seed  # noqa: E402
from .main_window import MainWindow  # noqa: E402
from .popup import PopupWindow  # noqa: E402

APP_ID = "io.github.appstudy.AppStudy"


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

    # ------------------------------------------------------------------ arranque

    def do_startup(self):
        Adw.Application.do_startup(self)
        self.con = db.connect()
        seed.ensure_seeded(self.con)
        self.load_css()

        for nombre, cb in (("quit", lambda *_: self.quit()),
                           ("popup", lambda *_: self.show_popup()),
                           ("main", lambda *_: self.show_main_window())):
            a = Gio.SimpleAction.new(nombre, None)
            a.connect("activate", cb)
            self.add_action(a)
        self.set_accels_for_action("app.quit", ["<Control>q"])

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
        if opts.get("popup"):
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

    def on_main_closed(self, *_):
        self.main_window = None
        return False

    # ------------------------------------------------------------------ utilidad

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
    return AppStudy().run(sys.argv)
