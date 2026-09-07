"""Catálogo de cursos de freeCodeCamp dentro de AppStudy.

Muestra las certificaciones con su avance, los módulos de cada una y las
lecciones de cada módulo. Desde aquí se toma el curso: cada lección se abre en
el reproductor web integrado (con su editor y sus pruebas, tal cual en
freeCodeCamp), se puede guardar para leerla sin conexión en «Leer» o pedirle a
la IA que saque tarjetas de repaso de ella.

Lo que se descarga se guarda en caché, así que el catálogo solo pesa la primera
vez. El avance vive en la base de AppStudy, no en la cuenta de freeCodeCamp.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from . import db, freecodecamp, ia  # noqa: E402

_instancia: "CursosFCCWindow | None" = None


def abrir_catalogo(con, parent_window=None, superblock: str | None = None):
    """Abre (o enfoca) el catálogo de freeCodeCamp."""
    global _instancia
    if _instancia is None:
        _instancia = CursosFCCWindow(con, parent_window=parent_window)
        _instancia.connect("close-request", _al_cerrar)
    _instancia.present()
    if superblock:
        _instancia.abrir_curso(superblock)
    return _instancia


def _al_cerrar(*_args):
    global _instancia
    _instancia = None
    return False


def _hilo(trabajo, al_terminar=None, al_fallar=None):
    """Ejecuta algo de red fuera del hilo de la interfaz."""
    import threading

    def correr():
        try:
            resultado = trabajo()
        except Exception as e:                       # noqa: BLE001 - se muestra al usuario
            if al_fallar:
                GLib.idle_add(al_fallar, e)
            return
        if al_terminar:
            GLib.idle_add(al_terminar, resultado)

    threading.Thread(target=correr, daemon=True).start()


class CursosFCCWindow(Adw.Window):
    """Ventana de tres pasos: cursos → módulos → lecciones."""

    def __init__(self, con, parent_window=None):
        super().__init__(transient_for=parent_window)
        self.con = con
        self.ventana_padre = parent_window
        self.set_title("Cursos de freeCodeCamp")
        self.set_default_size(880, 700)

        self.toasts = Adw.ToastOverlay()
        self.nav = Adw.NavigationView()
        self.toasts.set_child(self.nav)
        self.set_content(self.toasts)

        self.nav.push(self._pagina_cursos())

    # ------------------------------------------------------------- utilidades

    def aviso(self, texto: str):
        self.toasts.add_toast(Adw.Toast(title=texto))

    @staticmethod
    def _pagina(titulo, tag, contenido, cabecera_extra=None):
        vista = Adw.ToolbarView()
        cabecera = Adw.HeaderBar()
        if cabecera_extra is not None:
            cabecera.pack_end(cabecera_extra)
        vista.add_top_bar(cabecera)
        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        caja.set_margin_top(16)
        caja.set_margin_bottom(16)
        caja.set_margin_start(16)
        caja.set_margin_end(16)
        caja.append(contenido)
        clamp = Adw.Clamp(maximum_size=820)
        clamp.set_child(caja)
        scroll.set_child(clamp)
        vista.set_content(scroll)
        return Adw.NavigationPage(title=titulo, tag=tag, child=vista)

    @staticmethod
    def _barra(hechas: int, total: int) -> Gtk.Widget:
        barra = Gtk.ProgressBar(hexpand=True, show_text=True)
        barra.set_fraction((hechas / total) if total else 0.0)
        barra.set_text(f"{hechas} de {total} lecciones" if total else "sin lecciones")
        barra.set_valign(Gtk.Align.CENTER)
        barra.set_vexpand(False)
        barra.set_size_request(200, -1)
        return barra

    # ------------------------------------------------------ 1. lista de cursos

    def _pagina_cursos(self) -> Adw.NavigationPage:
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)

        titulo = Gtk.Label(
            label="Toma los cursos de freeCodeCamp sin salir de AppStudy",
            xalign=0, wrap=True, css_classes=["title-2"])
        caja.append(titulo)
        caja.append(Gtk.Label(
            label="Cada lección se abre con su editor y sus pruebas. Al terminarla se "
                  "marca sola, y puedes guardarla para leerla luego o convertirla en tarjetas.",
            xalign=0, wrap=True, css_classes=["dim-label"]))

        seguir = self._fila_continuar()
        if seguir is not None:
            caja.append(seguir)

        resumen = db.fcc_resumen(self.con)
        grupo = Adw.PreferencesGroup(title="Certificaciones y cursos")
        for curso in freecodecamp.listar_cursos():
            grupo.add(self._fila_curso(curso, resumen.get(curso["superblock"], {})))
        caja.append(grupo)

        boton_refrescar = Gtk.Button(icon_name="view-refresh-symbolic",
                                     tooltip_text="Volver a descargar el catálogo de freeCodeCamp")
        boton_refrescar.connect("clicked", lambda *_: self._refrescar_catalogo())
        return self._pagina("freeCodeCamp", "cursos", caja, boton_refrescar)

    def _fila_curso(self, curso: dict, avance: dict) -> Adw.ActionRow:
        cacheado = freecodecamp.catalogo_en_cache(curso["superblock"])
        total = cacheado.get("lecciones", 0) if cacheado else 0
        hechas = avance.get("hechas", 0)

        subtitulo = f"{hechas} lecciones completadas" if hechas else "sin empezar"
        if total:
            subtitulo = f"{hechas} de {total} lecciones · {len(cacheado['bloques'])} módulos"

        fila = Adw.ActionRow(title=f"{curso['icono']}  {curso['nombre']}",
                             subtitle=subtitulo, activatable=True)
        if total:
            fila.add_suffix(self._barra(hechas, total))
        fila.add_suffix(Gtk.Image(icon_name="go-next-symbolic", valign=Gtk.Align.CENTER))
        fila.connect("activated", lambda *_: self.abrir_curso(curso["superblock"]))
        return fila

    def _fila_continuar(self):
        ultima = db.fcc_ultima(self.con)
        if not ultima:
            return None
        caja = Gtk.Box(spacing=12, css_classes=["card"])
        caja.set_margin_top(4)
        for lado in ("top", "bottom", "start", "end"):
            getattr(caja, f"set_margin_{lado}")(12)
        texto = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        texto.append(Gtk.Label(label="Seguir donde lo dejaste", xalign=0,
                               css_classes=["heading"]))
        texto.append(Gtk.Label(
            label=f"{ultima.get('title') or 'Lección'} · "
                  f"{freecodecamp.nombre_bonito(ultima.get('block', ''))}",
            xalign=0, wrap=True, css_classes=["caption", "dim-label"]))
        caja.append(texto)
        boton = Gtk.Button(label="Continuar", css_classes=["suggested-action"],
                           valign=Gtk.Align.CENTER)
        url = f"https://www.freecodecamp.org{ultima['slug']}"
        boton.connect("clicked", lambda *_: self.abrir_en_reproductor(
            url, ultima.get("superblock", ""), ultima.get("block", ""),
            ultima.get("title", "")))
        caja.append(boton)
        return caja

    def _refrescar_catalogo(self):
        self.aviso("Descargando el currículo de freeCodeCamp…")
        primero = freecodecamp.CURSOS[0][0]
        _hilo(lambda: freecodecamp.catalogo(primero, refrescar=True),
              lambda _r: self._recargar_inicio("Catálogo actualizado"),
              lambda e: self.aviso(f"No se pudo actualizar: {e}"))

    def _recargar_inicio(self, mensaje=""):
        self.nav.replace([self._pagina_cursos()])
        if mensaje:
            self.aviso(mensaje)

    # --------------------------------------------------------- 2. los módulos

    def abrir_curso(self, superblock: str):
        """Muestra los módulos de un curso, descargando el catálogo si hace falta."""
        cacheado = freecodecamp.catalogo_en_cache(superblock)
        if cacheado:
            self.nav.push(self._pagina_modulos(superblock, cacheado))
            return

        self.aviso("Descargando el currículo de freeCodeCamp (solo la primera vez)…")
        _hilo(lambda: freecodecamp.catalogo(superblock),
              lambda cat: self.nav.push(self._pagina_modulos(superblock, cat)),
              lambda e: self.aviso(f"freeCodeCamp: {e}"))

    def _pagina_modulos(self, superblock: str, cat: dict) -> Adw.NavigationPage:
        nombre = freecodecamp.nombre_curso(superblock)
        avance = db.fcc_hechas(self.con, superblock)
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        hechas = sum(1 for s, f in avance.items() if f["hecho"])
        caja.append(self._barra(hechas, cat.get("lecciones", 0)))

        grupo = Adw.PreferencesGroup(
            title=f"{len(cat['bloques'])} módulos",
            description="Cada módulo es un proyecto o una serie de pasos de freeCodeCamp.")
        for bloque in cat["bloques"]:
            slugs = [l["slug"] for l in bloque["lecciones"]]
            b_hechas = sum(1 for s in slugs if avance.get(s, {}).get("hecho"))
            fila = Adw.ActionRow(
                title=bloque["titulo"],
                subtitle=f"{b_hechas} de {len(slugs)} lecciones",
                activatable=True)
            if b_hechas and b_hechas == len(slugs):
                fila.add_prefix(Gtk.Label(label="✓", css_classes=["success"]))
            fila.add_suffix(Gtk.Image(icon_name="go-next-symbolic", valign=Gtk.Align.CENTER))
            fila.connect("activated",
                         lambda _f, b=bloque: self.nav.push(
                             self._pagina_lecciones(superblock, b)))
            grupo.add(fila)
        caja.append(grupo)
        return self._pagina(nombre, f"curso-{superblock}", caja)

    # ------------------------------------------------------- 3. las lecciones

    def _pagina_lecciones(self, superblock: str, bloque: dict) -> Adw.NavigationPage:
        avance = db.fcc_hechas(self.con, superblock)
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        empezar = Gtk.Button(label="▶  Empezar el módulo",
                             css_classes=["suggested-action", "pill"],
                             halign=Gtk.Align.CENTER)
        pendiente = next((l for l in bloque["lecciones"]
                          if not avance.get(l["slug"], {}).get("hecho")),
                         bloque["lecciones"][0] if bloque["lecciones"] else None)
        if pendiente:
            empezar.connect("clicked", lambda *_: self.abrir_en_reproductor(
                pendiente["url"], superblock, bloque["block"], pendiente["titulo"]))
            caja.append(empezar)

        grupo = Adw.PreferencesGroup(title=f"{len(bloque['lecciones'])} lecciones")
        for leccion in bloque["lecciones"]:
            grupo.add(self._fila_leccion(superblock, bloque, leccion,
                                         avance.get(leccion["slug"], {})))
        caja.append(grupo)
        return self._pagina(bloque["titulo"], f"bloque-{bloque['block']}", caja)

    def _fila_leccion(self, superblock, bloque, leccion, estado) -> Adw.ActionRow:
        hecho = bool(estado.get("hecho"))
        fila = Adw.ActionRow(title=leccion["titulo"], activatable=True)
        if hecho:
            fila.set_subtitle("completada")
        elif estado:
            fila.set_subtitle("empezada")
        fila.add_prefix(Gtk.Label(label="✓" if hecho else "○",
                                  css_classes=["success"] if hecho else ["dim-label"]))

        b_leer = Gtk.Button(icon_name="document-open-symbolic", valign=Gtk.Align.CENTER,
                            css_classes=["flat"],
                            tooltip_text="Guardar la lección para leerla en «Leer»")
        b_leer.connect("clicked", lambda *_: self.guardar_para_leer(superblock, leccion))
        fila.add_suffix(b_leer)

        b_tarjetas = Gtk.Button(icon_name="view-list-symbolic", valign=Gtk.Align.CENTER,
                                css_classes=["flat"],
                                tooltip_text="Sacar tarjetas de esta lección con la IA")
        b_tarjetas.connect("clicked", lambda *_: self.generar_tarjetas(superblock, leccion))
        fila.add_suffix(b_tarjetas)

        b_marcar = Gtk.ToggleButton(icon_name="object-select-symbolic",
                                    valign=Gtk.Align.CENTER, css_classes=["flat"],
                                    active=hecho,
                                    tooltip_text="Marcar como completada")
        b_marcar.connect("toggled", self._alternar_hecha, superblock, bloque, leccion, fila)
        fila.add_suffix(b_marcar)

        fila.connect("activated", lambda *_: self.abrir_en_reproductor(
            leccion["url"], superblock, bloque["block"], leccion["titulo"]))
        return fila

    def _alternar_hecha(self, boton, superblock, bloque, leccion, fila):
        hecho = boton.get_active()
        db.fcc_marcar(self.con, superblock, bloque["block"], leccion["slug"],
                      leccion["titulo"], hecho=hecho)
        fila.set_subtitle("completada" if hecho else "")

    # ------------------------------------------------------------- acciones

    def abrir_en_reproductor(self, url, superblock, bloque, titulo):
        """Abre la lección en el reproductor web para hacerla de verdad."""
        db.fcc_marcar(self.con, superblock, bloque,
                      freecodecamp.ruta_de(url) or url, titulo)
        from . import reproductor
        reproductor.abrir_reproductor(self.con, parent_window=self.ventana_padre or self,
                                      url=url)

    def guardar_para_leer(self, superblock, leccion):
        self.aviso(f"Descargando «{leccion['titulo']}» de freeCodeCamp…")
        mazo_key = freecodecamp.MAZO_POR_CURSO.get(superblock, "python")
        fila = self.con.execute("SELECT id, key, name FROM decks WHERE key=?",
                                (mazo_key,)).fetchone()
        if not fila:
            fila = self.con.execute("SELECT id, key, name FROM decks ORDER BY pos LIMIT 1").fetchone()
        if not fila:
            self.aviso("No hay ningún mazo donde guardar la lección.")
            return
        mazo_id, mazo, nombre = fila["id"], fila["key"], fila["name"]

        def trabajo():
            leccion_web = freecodecamp.obtener_leccion(leccion["url"])
            otra = db.connect()
            try:
                return freecodecamp.guardar_como_lectura(otra, leccion_web, mazo_id, mazo)
            finally:
                otra.close()

        def listo(cap):
            self.aviso(f"«{cap['title']}» guardada en {nombre}: ábrela en «Leer».")
            if self.ventana_padre is not None and hasattr(self.ventana_padre, "refresh_reader"):
                self.ventana_padre.refresh_reader()

        _hilo(trabajo, listo, lambda e: self.aviso(f"No se pudo guardar: {e}"))

    def generar_tarjetas(self, superblock, leccion):
        cfg = ia.config(self.con)
        if not cfg.get("activa"):
            self.aviso("Activa la IA en Ajustes para sacar tarjetas.")
            return
        self.aviso(f"Pensando tarjetas de «{leccion['titulo']}»…")
        mazo_key = freecodecamp.MAZO_POR_CURSO.get(superblock, "python")

        def trabajo():
            leccion_web = freecodecamp.obtener_leccion(leccion["url"])
            return leccion_web, freecodecamp.generar_tarjetas_fcc(cfg, leccion_web, 5)

        def listo(resultado):
            leccion_web, tarjetas = resultado
            padre = self.ventana_padre
            mazos = db.deck_stats(self.con)
            mazo = next((m for m in mazos if m["key"] == mazo_key), mazos[0] if mazos else None)
            if padre is not None and hasattr(padre, "revisar_generadas") and mazo:
                padre.present()
                padre.revisar_generadas(
                    tarjetas, mazo, leccion_web["titulo"],
                    etiquetas=f"freecodecamp, {leccion_web['bloque']}",
                    fuente=leccion_web.get("fuente"))
            else:
                self._guardar_tarjetas(tarjetas, mazo_key)
            ia.hilo(lambda: ia.descargar(cfg))

        def falló(e):
            self.aviso(f"freeCodeCamp / IA: {e}")
            ia.hilo(lambda: ia.descargar(cfg))

        _hilo(trabajo, listo, falló)

    def _guardar_tarjetas(self, tarjetas, mazo_key):
        fila = self.con.execute("SELECT id, key FROM decks WHERE key=?", (mazo_key,)).fetchone()
        if not fila:
            return
        for t in tarjetas:
            db.add_card(self.con, fila["id"], fila["key"], "card", t["front"], t["back"],
                        tags=t.get("tags", "freecodecamp"), level=t.get("level", 2))
        self.con.commit()
        self.aviso(f"{len(tarjetas)} tarjetas guardadas.")
