"""Reproductor web integrado para cursos online (Platzi y Udemy).

Permite visualizar clases y videos directamente en una ventana nativa de AppStudy
utilizando WebKitGTK con sesión persistente (cookies y credenciales guardadas).
Rastrea automáticamente el último video visto y la siguiente clase para que
puedas continuar tu aprendizaje con un solo clic o pidiéndoselo a Bit.

Incluye:
1. Generación automática de tarjetas con IA (Ctrl+N o botón "Crear tarjeta").
2. Repaso espaciado post-video con comprobación oral o quiz al terminar una clase.
3. Pausa automática al sonar el Pomodoro para estudiar tarjetas en el descanso.
"""
from __future__ import annotations

import json
import re
import threading
import urllib.parse
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
try:
    gi.require_version("WebKit", "6.0")
    from gi.repository import WebKit
    HAY_WEBKIT = True
except Exception:
    HAY_WEBKIT = False

from gi.repository import Adw, Gdk, GLib, Gtk

from . import db, ia, util, voz

PERFIL_DIR = Path.home() / ".local" / "share" / "appstudy" / "player_profile"
PLATZI_HOME = "https://platzi.com/home"
UDEMY_HOME = "https://www.udemy.com/home/my-courses/learning/"

_instancia_reproductor: CursosPlayerWindow | None = None
_sesion_webkit: WebKit.NetworkSession | None = None


def obtener_perfil_webkit():
    """Crea y devuelve la NetworkSession persistente para WebKit 6.0 con almacenamiento permanente."""
    global _sesion_webkit
    if _sesion_webkit is not None:
        return _sesion_webkit

    PERFIL_DIR.mkdir(parents=True, exist_ok=True)
    data_dir = str(PERFIL_DIR / "data")
    cache_dir = str(PERFIL_DIR / "cache")
    cookie_file = str(PERFIL_DIR / "cookies.sqlite")
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    Path(cache_dir).mkdir(parents=True, exist_ok=True)

    # Limpiar cookies de verificación fallida de Cloudflare si quedaron atascadas
    if Path(cookie_file).exists():
        try:
            import sqlite3
            with sqlite3.connect(cookie_file) as c:
                c.execute("DELETE FROM moz_cookies WHERE name LIKE '%cf_chl%'")
                c.commit()
        except Exception:
            pass

    session = WebKit.NetworkSession.new(data_dir, cache_dir)
    cm = session.get_cookie_manager()
    cm.set_persistent_storage(cookie_file, WebKit.CookiePersistentStorage.SQLITE)
    cm.set_accept_policy(WebKit.CookieAcceptPolicy.ALWAYS)
    _sesion_webkit = session
    return _sesion_webkit


def pausar_reproductor_activo():
    """Pausa el video en la ventana del reproductor si está abierta."""
    global _instancia_reproductor
    if _instancia_reproductor is not None:
        _instancia_reproductor.pausar_video()


def reanudar_reproductor_activo():
    """Reanuda el video en la ventana del reproductor si está abierta."""
    global _instancia_reproductor
    if _instancia_reproductor is not None:
        _instancia_reproductor.reanudar_video()


class CursosPlayerWindow(Adw.Window):
    """Ventana del reproductor web para Platzi y Udemy."""

    def __init__(self, con, parent_window=None):
        super().__init__(transient_for=parent_window)
        global _instancia_reproductor
        _instancia_reproductor = self

        self.con = con
        self.set_title("Reproductor de Cursos · Platzi & Udemy")
        self.set_default_size(1120, 740)

        self.connect("close-request", self._al_cerrar)

        # Controlador de atajos de teclado (Ctrl+N / Ctrl+T para crear tarjeta)
        ctrl_teclas = Gtk.EventControllerKey()
        ctrl_teclas.connect("key-pressed", self._on_key_pressed)
        self.add_controller(ctrl_teclas)

        # Contenedor vertical
        self.box_raiz = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(self.box_raiz)

        # Barra superior Adwaita
        self.header = Adw.HeaderBar()
        self.box_raiz.append(self.header)

        # Botones de navegación web
        self.box_nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.btn_atras = Gtk.Button(icon_name="go-previous-symbolic", tooltip_text="Atrás")
        self.btn_atras.connect("clicked", lambda _: self.web_view.go_back() if self.web_view else None)
        self.btn_adelante = Gtk.Button(icon_name="go-next-symbolic", tooltip_text="Adelante")
        self.btn_adelante.connect("clicked", lambda _: self.web_view.go_forward() if self.web_view else None)
        self.btn_recargar = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Recargar")
        self.btn_recargar.connect("clicked", lambda _: self.web_view.reload() if self.web_view else None)

        self.box_nav.append(self.btn_atras)
        self.box_nav.append(self.btn_adelante)
        self.box_nav.append(self.btn_recargar)
        self.header.pack_start(self.box_nav)

        # Botones de acceso rápido a plataformas
        self.box_plataformas = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.btn_platzi = Gtk.Button(label="🟢 Platzi", tooltip_text="Ir a Platzi Home")
        self.btn_platzi.add_css_class("flat")
        self.btn_platzi.connect("clicked", lambda _: self.cargar_url(PLATZI_HOME))

        self.btn_udemy = Gtk.Button(label="🟣 Udemy", tooltip_text="Ir a Mis Cursos de Udemy")
        self.btn_udemy.add_css_class("flat")
        self.btn_udemy.connect("clicked", lambda _: self.cargar_url(UDEMY_HOME))

        self.box_plataformas.append(self.btn_platzi)
        self.box_plataformas.append(self.btn_udemy)
        self.header.pack_start(self.box_plataformas)

        self.btn_tarjeta = Gtk.Button(icon_name="document-new-symbolic", tooltip_text="Crear tarjeta con Bit (Ctrl+N)")
        self.btn_tarjeta.connect("clicked", self._on_crear_tarjeta)

        self.auto_pausa_al_salir = True
        self.btn_autopause = Gtk.ToggleButton(
            icon_name="media-playback-pause-symbolic",
            tooltip_text="Pausar automáticamente al salir de la ventana (activo)",
            active=True
        )
        def _on_toggle_autopause(btn):
            self.auto_pausa_al_salir = btn.get_active()
            if self.auto_pausa_al_salir:
                btn.set_tooltip_text("Pausar automáticamente al salir de la ventana (activo)")
            else:
                btn.set_tooltip_text("Reproducción continua en segundo plano permitida")
        self.btn_autopause.connect("toggled", _on_toggle_autopause)

        self.btn_limpiar = Gtk.Button(
            icon_name="edit-clear-symbolic",
            tooltip_text="Restablecer cookies y verificación de seguridad si la página se atasca"
        )
        self.btn_limpiar.connect("clicked", lambda _: self.limpiar_cookies_y_recargar())

        self.header.pack_end(self.btn_autopause)
        self.header.pack_end(self.btn_tarjeta)
        self.header.pack_end(self.btn_limpiar)

        self.connect("notify::is-active", self._on_is_active_changed)

        # Barra informativa inferior (Muestra curso y video actual detectado)
        self.bar_info = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.bar_info.set_margin_start(12)
        self.bar_info.set_margin_end(12)
        self.bar_info.set_margin_top(4)
        self.bar_info.set_margin_bottom(4)

        self.lbl_info = Gtk.Label(label="Cargando reproductor...", xalign=0.0, hexpand=True)
        self.lbl_info.add_css_class("dim-label")
        self.lbl_info.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        self.bar_info.append(self.lbl_info)

        self.box_raiz.append(self.bar_info)

        # WebView WebKit
        if not HAY_WEBKIT:
            lbl_error = Gtk.Label(
                label="WebKit 6.0 no se encuentra disponible en este sistema.\n"
                      "Instala libwebkitgtk-6.0 para usar el reproductor web integrado.",
                wrap=True, justify=Gtk.Justification.CENTER
            )
            lbl_error.set_vexpand(True)
            self.box_raiz.append(lbl_error)
            self.web_view = None
            return

        session = obtener_perfil_webkit()
        self.ucm = WebKit.UserContentManager()
        try:
            self.ucm.register_script_message_handler("videoFin")
            self.ucm.connect("script-message-received::videoFin", self._on_video_fin)
        except Exception:
            pass

        self.web_view = WebKit.WebView(network_session=session, user_content_manager=self.ucm)
        self.web_view.set_vexpand(True)
        self.web_view.set_hexpand(True)

        # Ajustes de almacenamiento, sesión persistente y multimedia
        settings = self.web_view.get_settings()
        if hasattr(settings, "set_enable_html5_local_storage"):
            settings.set_enable_html5_local_storage(True)
        if hasattr(settings, "set_enable_html5_database"):
            settings.set_enable_html5_database(True)
        if hasattr(settings, "set_enable_page_cache"):
            settings.set_enable_page_cache(True)
        if hasattr(settings, "set_enable_site_specific_quirks"):
            settings.set_enable_site_specific_quirks(True)
        if hasattr(settings, "set_javascript_can_open_windows_automatically"):
            settings.set_javascript_can_open_windows_automatically(True)
        if hasattr(settings, "set_allow_modal_dialogs"):
            settings.set_allow_modal_dialogs(True)
        if hasattr(settings, "set_enable_media"):
            settings.set_enable_media(True)
        if hasattr(settings, "set_enable_mediasource"):
            settings.set_enable_mediasource(True)
        if hasattr(settings, "set_enable_encrypted_media"):
            settings.set_enable_encrypted_media(True)
        if hasattr(settings, "set_enable_media_stream"):
            settings.set_enable_media_stream(True)
        if hasattr(settings, "set_enable_webaudio"):
            settings.set_enable_webaudio(True)
        if hasattr(settings, "set_media_playback_allows_inline"):
            settings.set_media_playback_allows_inline(True)
        if hasattr(settings, "set_media_playback_requires_user_gesture"):
            settings.set_media_playback_requires_user_gesture(False)
        if hasattr(settings, "set_enable_webgl"):
            settings.set_enable_webgl(True)
        if hasattr(settings, "set_enable_2d_canvas_acceleration"):
            settings.set_enable_2d_canvas_acceleration(True)
        if hasattr(settings, "set_javascript_can_access_clipboard"):
            settings.set_javascript_can_access_clipboard(True)

        self.web_view.connect("load-changed", self._on_load_changed)
        self.web_view.connect("notify::uri", self._on_uri_changed)
        self.web_view.connect("notify::title", self._on_title_changed)
        self.web_view.connect("decide-policy", self._on_decide_policy)

        self.box_raiz.append(self.web_view)

    def _on_decide_policy(self, view, decision, decision_type):
        """Navega las aperturas de nuevas ventanas en el mismo visor web para evitar fallos de WebKit."""
        if decision_type == WebKit.PolicyDecisionType.NEW_WINDOW_ACTION:
            try:
                nav = decision.get_navigation_action()
                req = nav.get_request() if nav else None
                uri = req.get_uri() if req else None
                if uri:
                    view.load_uri(uri)
                    decision.ignore()
                    return True
            except Exception:
                pass
        return False

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if (state & Gdk.ModifierType.CONTROL_MASK) and (keyval in (Gdk.KEY_n, Gdk.KEY_N, Gdk.KEY_t, Gdk.KEY_T)):
            self._on_crear_tarjeta()
            return True
        return False

    def _on_is_active_changed(self, window, param):
        """Pausa el video cuando la ventana pierde el foco o se minimiza, y lo reanuda al volver."""
        if not getattr(self, "auto_pausa_al_salir", True) or not self.web_view:
            return
        if not self.is_active():
            self.pausar_video(recordar_estado=True)
        else:
            self.reanudar_video(solo_si_reproduciendo=True)

    def _al_cerrar(self, *args):
        global _instancia_reproductor
        _instancia_reproductor = None
        if self.web_view:
            try:
                self.web_view.set_is_muted(True)
                self.pausar_video(recordar_estado=False)
                self.web_view.stop_loading()
                self.web_view.load_uri("about:blank")
            except Exception:
                pass
        return False

    def pausar_video(self, recordar_estado: bool = False):
        """Pausa el elemento de video HTML5 si está reproduciendo."""
        if not self.web_view:
            return
        if recordar_estado:
            js = "var v = document.querySelector('video'); if (v && !v.paused) { v.pause(); window._appstudy_was_playing = true; } else if (v && v.paused) { window._appstudy_was_playing = false; }"
        else:
            js = "var v = document.querySelector('video'); if (v) { v.pause(); window._appstudy_was_playing = false; }"
        try:
            self.web_view.evaluate_javascript(js, -1, None, None, None, None)
        except Exception:
            pass

    def reanudar_video(self, solo_si_reproduciendo: bool = False):
        """Reanuda el elemento de video HTML5."""
        if not self.web_view:
            return
        if solo_si_reproduciendo:
            js = "var v = document.querySelector('video'); if (v && v.paused && window._appstudy_was_playing) { v.play(); window._appstudy_was_playing = false; }"
        else:
            js = "var v = document.querySelector('video'); if (v && v.paused) { v.play(); window._appstudy_was_playing = false; }"
        try:
            self.web_view.evaluate_javascript(js, -1, None, None, None, None)
        except Exception:
            pass

    def cargar_url(self, url: str):
        """Carga una URL en el WebView."""
        if not self.web_view or not url:
            return
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        self.lbl_info.set_text(f"Cargando {url}...")
        self.web_view.load_uri(url)

    def limpiar_cookies_y_recargar(self):
        """Limpia cookies de verificación fallidas de Cloudflare y recarga la página."""
        cookie_file = str(PERFIL_DIR / "cookies.sqlite")
        if Path(cookie_file).exists():
            try:
                import sqlite3
                with sqlite3.connect(cookie_file) as c:
                    c.execute("DELETE FROM moz_cookies WHERE name LIKE '%cf%'")
                    c.commit()
            except Exception:
                pass
        self.lbl_info.set_text("Cookies de verificación restablecidas. Recargando...")
        if self.web_view:
            self.web_view.reload()

    def _on_uri_changed(self, view, param):
        uri = view.get_uri() or ""
        self.btn_atras.set_sensitive(view.can_go_back())
        self.btn_adelante.set_sensitive(view.can_go_forward())
        self._inspeccionar_pagina(uri)

    def _on_title_changed(self, view, param):
        titulo = view.get_title() or ""
        if titulo:
            self.set_title(f"{titulo} · AppStudy")

    def _on_load_changed(self, view, event):
        if event == WebKit.LoadEvent.FINISHED:
            uri = view.get_uri() or ""
            self._inspeccionar_pagina(uri)
            self._ejecutar_extractor_js(uri)

    def _detectar_plataforma(self, uri: str) -> str | None:
        if "platzi.com" in uri:
            return "platzi"
        if "udemy.com" in uri:
            return "udemy"
        return None

    def _inspeccionar_pagina(self, uri: str):
        plat = self._detectar_plataforma(uri)
        if not plat:
            self.lbl_info.set_text(uri)
            return

        if plat == "platzi":
            m = re.search(r"platzi\.com/(?:clases|cursos)/([^/?#]+)", uri)
            slug = m.group(1) if m else "platzi"
            self.lbl_info.set_text(f"🟢 Platzi · Curso: {slug.replace('-', ' ').title()}")
        elif plat == "udemy":
            m = re.search(r"udemy\.com/course/([^/?#]+)", uri)
            slug = m.group(1) if m else "udemy"
            self.lbl_info.set_text(f"🟣 Udemy · Curso: {slug.replace('-', ' ').title()}")

    def _ejecutar_extractor_js(self, uri: str):
        """Inyecta script para extraer títulos, enlace siguiente y enganchar evento fin de video."""
        plat = self._detectar_plataforma(uri)
        if not plat:
            return

        js_script = r"""
        (function() {
            var res = {
                title: document.title || "",
                course_title: "",
                lesson_title: "",
                next_url: ""
            };

            // 1. Extraer en Platzi
            if (location.hostname.indexOf("platzi.com") !== -1) {
                var h1 = document.querySelector("h1") || document.querySelector(".Class-title");
                if (h1) res.lesson_title = h1.innerText.trim();
                
                var courseElem = document.querySelector(".Course-title") || document.querySelector("a[href*='/cursos/']");
                if (courseElem) res.course_title = courseElem.innerText.trim();

                var nextBtn = document.querySelector("a[data-testid='next-class']") ||
                              document.querySelector("a.NextClass") ||
                              document.querySelector("a[href*='/clases/']:not([aria-current='page'])");
                if (nextBtn && nextBtn.href) res.next_url = nextBtn.href;
            }
            // 2. Extraer en Udemy
            else if (location.hostname.indexOf("udemy.com") !== -1) {
                var uTitle = document.querySelector("h1") || document.querySelector("[data-purpose='lead-title']");
                if (uTitle) res.lesson_title = uTitle.innerText.trim();

                var uCourse = document.querySelector(".header--course-title") || document.querySelector("a[href*='/course/']");
                if (uCourse) res.course_title = uCourse.innerText.trim();

                var uNext = document.querySelector("button[data-purpose='go-to-next-lecture']") ||
                            document.querySelector("a[data-purpose='next-lecture-button']");
                if (uNext && uNext.href) res.next_url = uNext.href;
            }

            // Enganchar detección de fin de video HTML5
            function hookVideo() {
                var v = document.querySelector("video");
                if (v && !v._appstudy_hooked) {
                    v._appstudy_hooked = true;
                    v.addEventListener("ended", function() {
                        try {
                            if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.videoFin) {
                                window.webkit.messageHandlers.videoFin.postMessage("ended");
                            }
                        } catch(e) {}
                    });
                }
            }
            hookVideo();
            setInterval(hookVideo, 3000);

            return JSON.stringify(res);
        })();
        """
        try:
            self.web_view.evaluate_javascript(
                js_script, -1, None, None, None, self._on_extractor_js_cb, uri
            )
        except Exception:
            pass

    def _on_extractor_js_cb(self, obj, res, uri):
        try:
            val = obj.evaluate_javascript_finish(res)
            raw = val.to_string() if val else ""
            if not raw or raw == "undefined":
                return
            datos = json.loads(raw)
            self._guardar_progreso_curso(uri, datos)
        except Exception:
            pass

    def _guardar_progreso_curso(self, uri: str, datos: dict):
        plat = self._detectar_plataforma(uri)
        if not plat:
            return

        lesson_title = datos.get("lesson_title") or ""
        course_title = datos.get("course_title") or ""
        next_url = datos.get("next_url") or ""

        slug = ""
        if plat == "platzi":
            m = re.search(r"platzi\.com/(?:clases|cursos)/([^/?#]+)", uri)
            slug = m.group(1) if m else "platzi"
        elif plat == "udemy":
            m = re.search(r"udemy\.com/course/([^/?#]+)", uri)
            slug = m.group(1) if m else "udemy"

        if not slug:
            return

        if not course_title:
            course_title = slug.replace("-", " ").title()
        if not lesson_title:
            doc_title = datos.get("title", "")
            lesson_title = doc_title.split("|")[0].split("-")[0].strip() or "Clase en curso"

        db.upsert_online_course(
            self.con,
            platform=plat,
            course_slug=slug,
            course_title=course_title,
            course_url=f"https://platzi.com/cursos/{slug}/" if plat == "platzi" else f"https://www.udemy.com/course/{slug}/",
            last_video_title=lesson_title,
            last_video_url=uri,
            next_video_url=next_url
        )

        icono = "🟢" if plat == "platzi" else "🟣"
        self.lbl_info.set_text(f"{icono} {plat.capitalize()} · {course_title} » {lesson_title}")

    def _on_video_fin(self, manager, js_result):
        """Llamado cuando el video de la lección termina."""
        GLib.idle_add(self._mostrar_dialogo_post_video)

    def _mostrar_dialogo_post_video(self):
        """Muestra opciones de repaso espaciado al terminar la clase."""
        uri = self.web_view.get_uri() if self.web_view else ""
        plat = self._detectar_plataforma(uri) or "platzi"
        ultimo = db.get_last_course(self.con, plat)
        curso_nombre = ultimo.get("course_title", "tu curso") if ultimo else "tu curso"
        clase_nombre = ultimo.get("last_video_title", "esta clase") if ultimo else "esta clase"

        dlg = Adw.Window(modal=True, transient_for=self)
        dlg.set_title("🎉 ¡Clase completada! Comprobación con Bit")
        dlg.set_default_size(500, 360)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_start(20)
        box.set_margin_end(20)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        dlg.set_content(box)

        lbl_tit = Gtk.Label(
            label="<span size='large' weight='bold'>🎉 ¡Has terminado esta clase!</span>",
            use_markup=True, xalign=0
        )
        box.append(lbl_tit)

        lbl_desc = Gtk.Label(
            label=f"Acabas de ver <b>{clase_nombre}</b> ({curso_nombre}).\n"
                  "Para consolidar lo aprendido en tu memoria antes de seguir, ¿qué quieres hacer?",
            use_markup=True, wrap=True, xalign=0
        )
        box.append(lbl_desc)

        fila_acciones = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        btn_voz = Gtk.Button(label="🎙️ Repaso por voz con Bit", css_classes=["suggested-action", "pill"])
        btn_voz.connect("clicked", lambda _: (dlg.close(), self._lanzar_comprobacion_voz(clase_nombre, curso_nombre)))
        fila_acciones.append(btn_voz)

        btn_examen = Gtk.Button(label="📝 Pregunta rápida tipo examen", css_classes=["pill"])
        btn_examen.connect("clicked", lambda _: (dlg.close(), self._lanzar_comprobacion_examen(plat)))
        fila_acciones.append(btn_examen)

        btn_cerrar = Gtk.Button(label="Listo, volver al curso", css_classes=["flat", "pill"])
        btn_cerrar.connect("clicked", lambda _: dlg.close())
        fila_acciones.append(btn_cerrar)

        box.append(fila_acciones)
        dlg.present()

    def _lanzar_comprobacion_voz(self, clase_nombre: str, curso_nombre: str):
        from . import voz_rec
        dlg = Adw.Window(modal=True, transient_for=self)
        dlg.set_title("🎙️ Repaso por voz · Bit")
        dlg.set_default_size(460, 340)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_start(20)
        box.set_margin_end(20)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        dlg.set_content(box)

        pregunta = f"¿Cuál fue el concepto o idea más importante de «{clase_nombre}»?"
        lbl = Gtk.Label(label=f"<b>Bit te pregunta:</b>\n«{pregunta}»", use_markup=True, wrap=True, xalign=0)
        box.append(lbl)

        lbl_estado = Gtk.Label(label="Pulsa el micrófono y dilo en voz alta.", wrap=True, xalign=0, css_classes=["dim-label"])
        box.append(lbl_estado)

        txt_resultado = Gtk.Label(label="", wrap=True, xalign=0)
        box.append(txt_resultado)

        grabador = voz_rec.GrabadorMicrofono()
        btn_mic = Gtk.Button(icon_name="audio-input-microphone-symbolic", css_classes=["circular", "suggested-action"], halign=Gtk.Align.CENTER)
        btn_mic.set_size_request(56, 56)

        def _toggle_rec(_):
            if grabador.esta_grabando():
                ruta = grabador.detener()
                btn_mic.set_icon_name("audio-input-microphone-symbolic")
                btn_mic.remove_css_class("destructive-action")
                btn_mic.add_css_class("suggested-action")
                lbl_estado.set_text("Transcribiendo y evaluando con Bit...")

                def _evaluar():
                    dicho = voz_rec.transcribir_audio(ruta, idioma="es")
                    if not dicho:
                        return "No se detectó voz clara. Intenta hablar más cerca del micrófono."
                    cfg_ia = ia.config(self.con)
                    if cfg_ia.get("activa"):
                        prompt = (f"El estudiante vio la clase '{clase_nombre}' de '{curso_nombre}' y dijo: '{dicho}'.\n"
                                  "En 1 o 2 frases breves, dale retroalimentación positiva y refuerza la idea principal.")
                        return ia.completar(cfg_ia, prompt, timeout=12)
                    return f"¡Bien expresado! Dijiste: «{dicho}». Excelente retención de la clase."

                def _fin(fb):
                    lbl_estado.set_text("✅ ¡Comprobación completada!")
                    txt_resultado.set_markup(f"<b>Bit:</b> {fb}")
                    voz.hablar(fb, voz.config(self.con))

                threading.Thread(target=lambda: GLib.idle_add(_fin, _evaluar()), daemon=True).start()
            else:
                grabador.iniciar()
                btn_mic.set_icon_name("media-record-symbolic")
                btn_mic.remove_css_class("suggested-action")
                btn_mic.add_css_class("destructive-action")
                lbl_estado.set_text("🎙️ Grabando... habla ahora y pulsa de nuevo al terminar.")

        btn_mic.connect("clicked", _toggle_rec)
        box.append(btn_mic)

        dlg.present()

    def _lanzar_comprobacion_examen(self, plat: str):
        from . import examen
        mazos = self.con.execute("SELECT id, name FROM decks ORDER BY pos").fetchall()
        deck_id = mazos[0]["id"] if mazos else None
        for m in mazos:
            if plat in m["name"].lower() or (plat == "platzi" and "ingl" in m["name"].lower()):
                deck_id = m["id"]
                break
        win = examen.ExamenWindow(self, self.con, deck_id=deck_id, n=5, deck_nombre=f"Quiz Rápido · {plat.capitalize()}")
        win.present()

    def _on_crear_tarjeta(self, *args):
        """Genera una tarjeta inteligente con IA a partir de la selección o de la clase actual."""
        if not self.web_view:
            return

        js = r"""
        (function() {
            var sel = window.getSelection().toString().trim();
            return JSON.stringify({
                selection: sel,
                title: document.title || "",
                url: location.href
            });
        })();
        """
        try:
            self.web_view.evaluate_javascript(js, -1, None, None, None, self._on_datos_tarjeta_cb)
        except Exception:
            self._abrir_dialogo_tarjeta("", "")

    def _on_datos_tarjeta_cb(self, obj, res):
        try:
            val = obj.evaluate_javascript_finish(res)
            raw = val.to_string() if val else ""
            datos = json.loads(raw) if raw else {}
            sel = datos.get("selection") or ""
            doc_title = datos.get("title") or ""
        except Exception:
            sel = ""
            doc_title = ""
        self._abrir_dialogo_tarjeta(sel, doc_title)

    def _abrir_dialogo_tarjeta(self, sel: str, doc_title: str):
        uri = self.web_view.get_uri() if self.web_view else ""
        plat = self._detectar_plataforma(uri) or "curso"
        ultimo = db.get_last_course(self.con, plat)
        tema = ultimo.get("course_title", "") if ultimo else ""
        clase = ultimo.get("last_video_title", doc_title) if ultimo else doc_title

        dlg = Adw.Window(modal=True, transient_for=self)
        dlg.set_title("💡 Crear tarjeta con Bit")
        dlg.set_default_size(480, 420)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_start(16)
        box.set_margin_end(16)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        dlg.set_content(box)

        lbl_encabezado = Gtk.Label(label=f"💡 Tarjeta para: <b>{tema or clase}</b>", use_markup=True, wrap=True, xalign=0)
        box.append(lbl_encabezado)

        lbl_ia_status = Gtk.Label(label="", wrap=True, xalign=0, css_classes=["dim-label"])
        box.append(lbl_ia_status)

        # Mazo destino
        mazos = self.con.execute("SELECT id, name FROM decks ORDER BY pos").fetchall()
        combo_mazos = Gtk.DropDown()
        nombres = [m["name"] for m in mazos] or ["General"]
        combo_mazos.set_model(Gtk.StringList.new(nombres))
        box.append(combo_mazos)

        # Pregunta / Anverso
        txt_front = Gtk.Entry(placeholder_text="Pregunta o concepto (Anverso)")
        box.append(txt_front)

        # Respuesta / Reverso
        txt_back = Gtk.Entry(placeholder_text="Respuesta o explicación (Reverso)")
        box.append(txt_back)

        # Etiquetas
        txt_tags = Gtk.Entry(placeholder_text="Etiquetas (separadas por coma)")
        txt_tags.set_text(f"{plat},online")
        box.append(txt_tags)

        # Generación asistida con IA si hay contexto
        cfg_ia = ia.config(self.con)
        texto_base = sel if sel else f"Clase: {clase} (Curso: {tema})"
        if cfg_ia.get("activa") and texto_base:
            lbl_ia_status.set_text("🤖 Bit está redactando la tarjeta con IA local...")
            def _generar():
                prompt = (
                    f"Eres un profesor experto creando tarjetas de repaso espaciado (flashcards).\n"
                    f"A partir de este concepto de la clase de {tema}:\n"
                    f"«{texto_base}»\n\n"
                    "Genera una tarjeta concisa en formato JSON estricto con estas claves:\n"
                    "{\n  \"front\": \"pregunta o concepto clave\",\n  \"back\": \"respuesta o explicación concisa\",\n  \"tags\": \"etiquetas\"\n}"
                )
                try:
                    resp = ia.completar(cfg_ia, prompt, timeout=12)
                    m = re.search(r"\{.*\}", resp, re.DOTALL)
                    if m:
                        return json.loads(m.group(0))
                except Exception:
                    pass
                return None

            def _aplicar_ia(res_ia):
                if res_ia:
                    txt_front.set_text(res_ia.get("front", ""))
                    txt_back.set_text(res_ia.get("back", ""))
                    if res_ia.get("tags"):
                        txt_tags.set_text(f"{plat},online,{res_ia['tags']}")
                    lbl_ia_status.set_text("✨ Tarjeta redactada por Bit. Puedes ajustarla o guardarla:")
                else:
                    if sel:
                        txt_front.set_text(sel[:60])
                        txt_back.set_text(sel)
                    else:
                        txt_front.set_text(clase)
                    lbl_ia_status.set_text("Escribe o ajusta los detalles de la tarjeta:")

            threading.Thread(target=lambda: GLib.idle_add(_aplicar_ia, _generar()), daemon=True).start()
        else:
            if sel:
                txt_front.set_text(sel[:60])
                txt_back.set_text(sel)
            else:
                txt_front.set_text(clase)

        btn_guardar = Gtk.Button(label="Guardar tarjeta", css_classes=["suggested-action"])
        def _guardar(_):
            f = txt_front.get_text().strip()
            b = txt_back.get_text().strip()
            t = txt_tags.get_text().strip()
            if not f:
                return
            idx = combo_mazos.get_selected()
            deck_id = mazos[idx]["id"] if mazos and idx < len(mazos) else 1
            deck_key = mazos[idx]["name"].lower() if mazos and idx < len(mazos) else "general"
            db.add_card(self.con, deck_id, deck_key, "card", f, b, tags=t)
            self.con.commit()
            dlg.close()

        btn_guardar.connect("clicked", _guardar)
        box.append(btn_guardar)

        dlg.present()


def abrir_reproductor(con, parent_window=None, url: str | None = None,
                      plataforma: str | None = None, **kwargs) -> CursosPlayerWindow:
    """Abre o enfoca la ventana del reproductor web de cursos."""
    global _instancia_reproductor
    if _instancia_reproductor is not None:
        win = _instancia_reproductor
        win.present()
    else:
        win = CursosPlayerWindow(con, parent_window=parent_window)
        win.present()

    # Determinar qué URL cargar
    if url:
        win.cargar_url(url)
    elif plataforma:
        p = plataforma.lower().strip()
        win.cargar_url(UDEMY_HOME if p == "udemy" else PLATZI_HOME)
    elif not win.web_view.get_uri():
        win.cargar_url(PLATZI_HOME)

    return win
