"""Centro de fuentes, herramientas de documentos y extensiones instalables."""
from pathlib import Path
import json
import time

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from . import db, documentos, exportador, extensiones, fuentes, ia, importador, libros, util


class FuentesWindow(Adw.Window):
    def __init__(self, parent):
        super().__init__(title="Extensiones y fuentes", transient_for=parent,
                         default_width=880, default_height=720)
        self.set_destroy_with_parent(True)
        self.parent = parent
        self.con = parent.con
        self.viva = True
        self.ocupada = False
        self.generacion = 0
        self.mazos = db.deck_stats(self.con)
        self.stack = Adw.ViewStack(vexpand=True)
        self.aviso = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self.aviso.set_margin_start(16)
        self.aviso.set_margin_end(16)
        self.aviso.set_margin_top(8)
        self.aviso.set_margin_bottom(8)
        self.stack.add_titled(self.explorar(), "fuentes", "Explorar fuentes")
        self.stack.add_titled(self.herramientas(), "herramientas", "Herramientas")
        self.stack.add_titled(self.gestion(), "extensiones", "Extensiones")
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.ViewSwitcher(stack=self.stack))
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        caja.append(header)
        caja.append(self.aviso)
        caja.append(self.stack)
        self.set_content(caja)
        self.actualizar_extensiones()
        self.timer = GLib.timeout_add_seconds(60, self.vigilar)
        self.connect("close-request", self.cerrar)
        self.connect("destroy", self.cerrar)

    def cerrar(self, *_):
        self.viva = False
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = None
        return False

    def mensaje(self, texto):
        if self.viva:
            self.aviso.set_text(str(texto))

    def trabajo(self, fn, cb, mensaje="Trabajando…"):
        if self.ocupada:
            self.mensaje("Espera a que termine la operación en curso")
            return
        self.ocupada = True
        self.mensaje(mensaje)
        def bien(result):
            self.ocupada = False
            if self.viva:
                try:
                    cb(result)
                except Exception as e:
                    self.mensaje(f"No se pudo completar: {e}")
            return False
        def mal(error):
            self.ocupada = False
            self.mensaje(f"No se pudo completar: {error}")
            return False
        util.hilo(fn, bien, mal, largo=True)

    @staticmethod
    def columna():
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for lado in ("start", "end", "top", "bottom"):
            getattr(caja, f"set_margin_{lado}")(16)
        return caja

    @staticmethod
    def scroll(child):
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(child)
        return scroll

    @staticmethod
    def limpiar(box):
        while (child := box.get_first_child()) is not None:
            box.remove(child)

    def boton(self, box, title, cb):
        b = Gtk.Button(label=title)
        b.connect("clicked", lambda *_: cb())
        box.append(b)
        return b

    def explorar(self):
        box = self.columna()
        self.selector = Gtk.DropDown.new_from_strings(["Cargando fuentes…"])
        self.selector.connect("notify::selected", lambda *_: self.cambiar_fuente())
        box.append(self.selector)
        self.consulta = Gtk.Entry(placeholder_text="Buscar en el catálogo o pegar una URL de la fuente")
        self.consulta.connect("activate", lambda *_: self.buscar())
        box.append(self.consulta)
        self.detalle = Gtk.Label(xalign=0, wrap=True)
        box.append(self.detalle)
        self.boton(box, "Buscar / actualizar", self.buscar)
        self.resultados = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
        box.append(self.resultados)
        return self.scroll(box)

    def fuente_actual(self):
        i = self.selector.get_selected()
        return self.proveedores[i] if hasattr(self, "proveedores") and i < len(self.proveedores) else None

    def cambiar_fuente(self):
        self.generacion += 1
        if not hasattr(self, "detalle"):
            return
        item = self.fuente_actual()
        self.limpiar(self.resultados)
        if item:
            textos = {"wikipedia": "Busca artículos en español o inglés; el idioma se elige en Extensiones.",
                      "openstax": "Catálogo seleccionado de libros. También puedes pegar una URL de OpenStax y explorar sus capítulos.",
                      "mit": "Catálogo seleccionado de cursos. Abre un curso para elegir apuntes, ejercicios o PDF.",
                      "markdown": "Carpeta configurada en Extensiones. La detección se actualiza cada minuto mientras esta ventana está abierta."}
            self.detalle.set_text(textos.get(item["id"], "Fuente proporcionada por un plugin instalado"))

    def buscar(self):
        item = self.fuente_actual()
        if not item:
            self.mensaje("Activa una fuente en Extensiones")
            return
        cfg = extensiones.config(self.con, item["id"])
        consulta = self.consulta.get_text().strip()
        gen = self.generacion
        def recibir(resultados):
            if gen != self.generacion:
                return
            self.pintar_resultados(resultados)
        if item["id"] == "markdown":
            anteriores = {}
            for row in self.con.execute("SELECT origin,fingerprint FROM source_imports WHERE provider='markdown' AND chapter_id IS NOT NULL"):
                anteriores.setdefault(row["origin"], []).append(row["fingerprint"])
            self.trabajo(lambda: fuentes.cambios_carpeta(cfg.get("carpeta", ""), anteriores, consulta), recibir,
                         "Buscando apuntes nuevos o modificados…")
        elif item["builtin"]:
            self.trabajo(lambda: fuentes.buscar(item["id"], consulta, cfg), recibir, "Consultando la fuente…")
        else:
            self.trabajo(lambda: extensiones.ejecutar(item, "search", {"query": consulta}, cfg), recibir)

    def pintar_resultados(self, resultados):
        self.limpiar(self.resultados)
        self.mensaje(f"{len(resultados)} resultados · abre uno para previsualizarlo")
        for item in resultados:
            fila = Adw.ActionRow(title=util.as_label(item["title"]),
                                 subtitle=util.as_label(item.get("summary") or item["origin"]))
            fila.set_title_lines(2)
            fila.set_subtitle_lines(2)
            b = Gtk.Button(label="Ver", valign=Gtk.Align.CENTER)
            b.connect("clicked", lambda _b, d=item: self.previsualizar(d))
            fila.add_suffix(b)
            fila.set_activatable_widget(b)
            self.resultados.append(fila)

    def previsualizar(self, item):
        plugin = next((p for p in extensiones.listar(self.con) if p["id"] == item["provider"]), None)
        if plugin and not plugin["enabled"]:
            self.mensaje("Esta fuente está desactivada")
            return
        if plugin and not plugin["builtin"]:
            cfg = extensiones.config(self.con, plugin["id"])
            self.trabajo(lambda: extensiones.ejecutar(plugin, "preview", item, cfg), self.preview)
        else:
            self.trabajo(lambda: fuentes.previsualizar(item), self.preview, "Preparando la vista previa…")

    def preview(self, item):
        self.mensaje("Vista previa lista")
        dlg = Adw.AlertDialog(heading=item["title"][:150])
        box = self.columna()
        atribucion = Gtk.Label(label=(f"Fuente: {item['origin']}\n"
            f"Autor: {item.get('author') or 'No indicado'}\n"
            f"Licencia: {item.get('license') or 'Consultar la fuente'}"),
            xalign=0, wrap=True, selectable=True)
        box.append(atribucion)
        vista = Gtk.TextView(editable=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        vista.get_buffer().set_text(item.get("text", ""))
        sc = self.scroll(vista)
        sc.set_size_request(-1, 260)
        box.append(sc)
        elegir = Gtk.DropDown.new_from_strings([d["name"] for d in self.mazos] or ["No hay mazos"])
        box.append(elegir)
        estado = Gtk.Label(xalign=0, wrap=True, selectable=True)
        box.append(estado)
        def seleccionado(solo=False):
            buffer = vista.get_buffer()
            bounds = buffer.get_selection_bounds()
            if bounds:
                texto = buffer.get_text(*bounds, False)
                # Una selección es una lectura distinta; no reemplaza el documento entero.
                import hashlib
                return {**item, "text": texto, "pages": [], "origin": item["origin"] + "#fragmento-" + hashlib.sha256(texto.encode()).hexdigest()[:12]}
            if solo:
                raise ValueError("Selecciona primero el texto que quieras importar")
            return item
        def guardar(solo=False):
            try:
                if not self.mazos:
                    raise ValueError("Crea un mazo antes de importar")
                doc = seleccionado(True) if solo else item
                cap = fuentes.importar(self.con, doc, self.mazos[elegir.get_selected()])
                estado.set_text("Lectura guardada; disponible en Leer y en las consultas a documentos")
                self.parent.refresh()
                return cap
            except Exception as e:
                estado.set_text(str(e))
                return None
        if item.get("format") == "pdf":
            def descargado(ruta):
                db.book_abrir(self.con, ruta, item["title"], item["provider"], 0)
                self.parent.refresh()
                estado.set_text("PDF guardado en Biblioteca. Puedes indexar sus páginas con el botón de abajo.")
                self.boton(box, "Indexar texto del PDF", lambda: self.extraer_archivo(ruta, False))
                self.boton(box, "Abrir PDF", lambda: self.abrir_libro(ruta, item["title"]))
                self.mensaje("PDF descargado y añadido a Biblioteca")
            self.boton(box, "Descargar PDF a Biblioteca", lambda: self.trabajo(lambda: fuentes.descargar_pdf(item), descargado, "Descargando PDF…"))
        elif item.get("text"):
            self.boton(box, "Guardar lectura completa", guardar)
            self.boton(box, "Guardar texto seleccionado", lambda: guardar(True))
            def generar():
                if not self.mazos:
                    return
                cfg = ia.config(self.con)
                if not cfg.get("activa"):
                    estado.set_text("Activa la IA local en Ajustes para proponer tarjetas")
                    return
                doc = seleccionado()
                cap = fuentes.importar(self.con, doc, self.mazos[elegir.get_selected()])
                mazo = self.mazos[elegir.get_selected()]
                source = {"kind": "chapter", "chapter_uid": cap["uid"], "title": cap["title"]}
                self.trabajo(lambda: ia.generar_desde_texto(cfg, doc["text"], doc["title"], 5),
                    lambda cards: self.parent.revisar_generadas(cards, mazo, doc["title"],
                        etiquetas=cap["tags"], fuente=source), "Proponiendo tarjetas para revisar…")
            self.boton(box, "Proponer tarjetas con IA del texto seleccionado o completo", generar)
        links = item.get("links", [])
        if links:
            desplegar = Gtk.Expander(label=f"Explorar capítulos y materiales ({len(links)})")
            lista = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            for link in links:
                self.boton(lista, link["title"][:100], lambda d=link: self.previsualizar(d))
            desplegar.set_child(lista)
            box.append(desplegar)
        scroll = self.scroll(box)
        scroll.set_size_request(620, 480)
        dlg.set_extra_child(scroll)
        dlg.add_response("close", "Cerrar")
        dlg.present(self)

    def elegir_archivo(self, title, patrones, cb, carpeta=False):
        dlg = Gtk.FileDialog(title=title)
        if patrones:
            filtro = Gtk.FileFilter()
            filtro.set_name(title)
            for patron in patrones:
                filtro.add_pattern(patron)
            lista = Gio.ListStore.new(Gtk.FileFilter)
            lista.append(filtro)
            dlg.set_filters(lista)
        def listo(d, res):
            try:
                f = d.select_folder_finish(res) if carpeta else d.open_finish(res)
                if f and f.get_path() and self.viva:
                    cb(f.get_path())
            except GLib.Error:
                pass
            except Exception as e:
                self.mensaje(str(e))
        if carpeta:
            dlg.select_folder(self, None, listo)
        else:
            dlg.open(self, None, listo)

    def herramientas(self):
        box = self.columna()
        box.append(Gtk.Label(label="Documentos y OCR", xalign=0, css_classes=["title-3"]))
        fila = Gtk.Box(spacing=8)
        fila.append(Gtk.Label(label="Páginas desde"))
        self.desde = Gtk.SpinButton.new_with_range(1, 10000, 1)
        fila.append(self.desde)
        fila.append(Gtk.Label(label="hasta"))
        self.hasta = Gtk.SpinButton.new_with_range(1, 10000, 1)
        self.hasta.set_value(10)
        fila.append(self.hasta)
        self.idioma = Gtk.DropDown.new_from_strings(["spa+eng", "spa", "eng"])
        fila.append(self.idioma)
        box.append(fila)
        deps = documentos.dependencias()
        box.append(Gtk.Label(label=" · ".join(f"{k}: {'disponible' if v else 'no instalado'}" for k, v in deps.items()), wrap=True, xalign=0))
        if not all(deps.values()):
            box.append(Gtk.Label(label="Para OCR: sudo apt install tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng poppler-utils",
                                 wrap=True, selectable=True, xalign=0))
        self.boton(box, "Indexar PDF, EPUB o apuntes", lambda: self.herramienta("ocr", lambda: self.elegir_archivo(
            "Documento", ["*.pdf", "*.epub", "*.md", "*.txt"], lambda p: self.extraer_archivo(p, False))))
        self.boton(box, "Extraer texto con OCR de imagen o PDF escaneado", lambda: self.herramienta("ocr", lambda: self.elegir_archivo(
            "Imagen o PDF", ["*.pdf", "*.png", "*.jpg", "*.jpeg", "*.tif", "*.webp"], lambda p: self.extraer_archivo(p, True))))
        box.append(Gtk.Separator())
        self.pregunta = Gtk.Entry(placeholder_text="Pregúntale a Bit sobre los documentos indexados")
        box.append(self.pregunta)
        self.boton(box, "Buscar fragmentos y responder con citas", lambda: self.herramienta("documentos", self.preguntar))
        self.respuesta = Gtk.Label(xalign=0, wrap=True, selectable=True)
        box.append(self.respuesta)
        self.citas = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.append(self.citas)
        self.boton(box, "Ver documentos indexados", self.ver_indice)
        box.append(Gtk.Separator())
        self.boton(box, "Importar subtítulos SRT/VTT para practicar inglés", lambda: self.herramienta("subtitulos", lambda: self.elegir_archivo(
            "Subtítulos", ["*.srt", "*.vtt"], self.importar_subtitulos)))
        self.boton(box, "Importar Anki, CSV, TSV o JSON", lambda: self.herramienta("anki", self.parent.importar_tarjetas))
        self.boton(box, "Exportar un mazo", lambda: self.herramienta("exportador", self.exportar))
        return self.scroll(box)

    def herramienta(self, ident, cb):
        if not extensiones.habilitada(self.con, ident):
            self.mensaje("Activa esta herramienta en Extensiones")
            return
        cb()

    def extraer_archivo(self, ruta, ocr):
        desde, hasta = int(self.desde.get_value()), int(self.hasta.get_value())
        idioma = ["spa+eng", "spa", "eng"][self.idioma.get_selected()]
        def listo(paginas):
            if not any(t.strip() for _, t in paginas):
                self.mensaje("No se encontró texto. Si es un documento escaneado, usa OCR")
                return
            n = documentos.indexar(self.con, str(Path(ruta).resolve()), Path(ruta).stem, paginas,
                                    parcial=Path(ruta).suffix.lower() == ".pdf")
            self.con.commit()
            self.mensaje(f"Documento indexado: {n} fragmentos con referencias")
            texto = "\n\n".join(f"## {loc}\n\n{t}" for loc, t in paginas)
            self.preview(fuentes.documento("documentos", str(Path(ruta).resolve()), Path(ruta).stem,
                                           texto, pages=paginas))
        self.trabajo(lambda: documentos.extraer(ruta, desde, hasta, ocr, idioma), listo, "Extrayendo e indexando el documento…")

    def preguntar(self):
        pregunta = self.pregunta.get_text().strip()
        if not pregunta:
            self.mensaje("Escribe una pregunta")
            return
        fragments = documentos.buscar(self.con, pregunta)
        self.limpiar(self.citas)
        for n, f in enumerate(fragments, 1):
            lab = Gtk.Label(label=f"[{n}] {f['title']} — {f['locator']}\n{f['text']}", xalign=0, wrap=True, selectable=True)
            self.citas.append(lab)
        cfg = ia.config(self.con)
        if not cfg.get("activa"):
            self.respuesta.set_text("Fragmentos encontrados. Activa la IA local para redactar una respuesta con citas." if fragments else "No encontré fragmentos relevantes.")
            return
        def listo(result):
            self.respuesta.set_text(result["answer"])
            self.limpiar(self.citas)
            for f in result["sources"]:
                self.citas.append(Gtk.Label(label=f"[{f['id']}] {f['title']} — {f['locator']}\n«{f['quote']}»\n{f['origin']}",
                                            xalign=0, wrap=True, selectable=True))
            self.mensaje("Respuesta lista; citas cotejadas con los fragmentos originales")
        self.trabajo(lambda: documentos.responder(cfg, pregunta, fragments), listo, "Bit está consultando tus documentos…")

    def ver_indice(self):
        filas = list(self.con.execute("SELECT origin,title,COUNT(*) AS n FROM document_chunks GROUP BY origin ORDER BY title"))
        dlg = Adw.AlertDialog(heading="Documentos indexados", body=f"{len(filas)} documentos disponibles para consultas")
        box = self.columna()
        for f in filas:
            row = Gtk.Box(spacing=8)
            row.append(Gtk.Label(label=f"{f['title']} · {f['n']} fragmentos\n{f['origin']}", wrap=True, xalign=0, hexpand=True))
            def retirar(origin=f["origin"], fila=row):
                self.con.execute("DELETE FROM document_chunks WHERE origin=?", (origin,))
                self.con.commit()
                box.remove(fila)
                self.mensaje("Documento retirado del índice; el archivo original se conserva")
            self.boton(row, "Quitar del índice", retirar)
            box.append(row)
        sc = self.scroll(box)
        sc.set_size_request(550, 300)
        dlg.set_extra_child(sc)
        dlg.add_response("close", "Cerrar")
        dlg.present(self)

    def importar_subtitulos(self, ruta):
        def listo(cues):
            cards = documentos.tarjetas_subtitulos(cues, Path(ruta).stem)
            self.parent.revisar_importadas(cards, Path(ruta).name)
            self.mensaje(f"{len(cards)} ejercicios de huecos listos para revisar; conservan el minuto en la pista")
        self.trabajo(lambda: documentos.subtitulos(ruta), listo, "Leyendo subtítulos…")

    def abrir_libro(self, ruta, title):
        self.parent.stack.set_visible_child_name("biblioteca")
        p = Path(ruta)
        self.parent.biblioteca.abrir({"ruta": ruta, "nombre": title, "archivo": p.name,
            "tema": "Fuentes", "ext": p.suffix.lstrip("."), "tam": p.stat().st_size})

    def exportar(self):
        dlg = Adw.AlertDialog(heading="Exportar mazos",
            body="JSON y ZIP conservan tipos y adjuntos. CSV/TSV exportan texto; las fórmulas de hoja de cálculo se neutralizan.")
        box = self.columna()
        mazo = Gtk.DropDown.new_from_strings(["Todos los mazos"] + [d["name"] for d in self.mazos])
        formato = Gtk.DropDown.new_from_strings(["json", "zip", "csv", "tsv"])
        box.append(mazo)
        box.append(formato)
        dlg.set_extra_child(box)
        dlg.add_response("cancel", "Cancelar")
        dlg.add_response("save", "Elegir destino")
        def elegir(_d, respuesta):
            if respuesta != "save":
                return
            fmt = ["json", "zip", "csv", "tsv"][formato.get_selected()]
            idx = mazo.get_selected()
            cards = exportador.tarjetas(self.con, self.mazos[idx - 1]["id"] if idx else None)
            fd = Gtk.FileDialog(title="Guardar exportación", initial_name="appstudy-tarjetas." + fmt)
            def guardar(d, res):
                try:
                    target = d.save_finish(res)
                    if target and target.get_path():
                        self.trabajo(lambda: exportador.guardar(target.get_path(), cards, fmt),
                                     lambda p: self.mensaje(f"Exportación guardada: {p}"))
                except GLib.Error:
                    pass
            fd.save(self, None, guardar)
        dlg.connect("response", elegir)
        dlg.present(self)

    def gestion(self):
        box = self.columna()
        self.boton(box, "Instalar paquete ZIP o plugin", lambda: self.elegir_archivo("Paquete AppStudy", ["*.zip"], self.instalar))
        self.lista_ext = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
        box.append(self.lista_ext)
        return self.scroll(box)

    def actualizar_extensiones(self):
        items = extensiones.listar(self.con)
        self.proveedores = [m for m in items if m["type"] == "source" and m["enabled"]]
        self.selector.set_model(Gtk.StringList.new([m["name"] for m in self.proveedores] or ["No hay fuentes activas"]))
        self.cambiar_fuente()
        self.limpiar(self.lista_ext)
        for item in items:
            row = Adw.ActionRow(title=util.as_label(item["name"]),
                subtitle=f"v{item['version']} · API {item['api_version']} · " + ("incluida" if item["builtin"] else "instalada"))
            sw = Gtk.Switch(active=item["enabled"], valign=Gtk.Align.CENTER)
            sw.connect("state-set", self.cambiar_activacion, item)
            row.add_suffix(sw)
            btn = Gtk.Button(label="Configurar", valign=Gtk.Align.CENTER)
            btn.connect("clicked", lambda _b, m=item: self.configurar(m))
            row.add_suffix(btn)
            if item["type"] == "content" and item["enabled"]:
                importar = Gtk.Button(label="Importar", valign=Gtk.Align.CENTER)
                importar.connect("clicked", lambda _b, m=item: self.cargar_paquete(m))
                row.add_suffix(importar)
            self.lista_ext.append(row)

    def cambiar_activacion(self, _sw, activo, item):
        def guardar():
            extensiones.activar(self.con, item, activo)
            self.actualizar_extensiones()
        if activo and not item["builtin"] and item["type"] == "source":
            dlg = Adw.AlertDialog(heading=f"Activar {item['name']}",
                body="Este plugin ejecutará Python con los permisos de tu usuario. Los permisos declarados no son un aislamiento de seguridad.\n\n"
                     "Permisos declarados: " + ", ".join(item["permissions"]))
            dlg.add_response("cancel", "Cancelar")
            dlg.add_response("enable", "Confiar y activar esta versión")
            dlg.connect("response", lambda _d, r: guardar() if r == "enable" else None)
            dlg.present(self)
        else:
            guardar()
        return True

    def configurar(self, item):
        cfg = extensiones.config(self.con, item["id"])
        dlg = Adw.AlertDialog(heading=item["name"], body="Permisos: " + (", ".join(item["permissions"]) or "sin permisos adicionales"))
        box = self.columna()
        vista = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        editable = {k: v for k, v in cfg.items() if k not in ("enabled", "trusted_version")}
        if item["id"] == "wikipedia":
            editable.setdefault("idioma", "es")
        if item["id"] == "markdown":
            editable.setdefault("carpeta", "")
            self.boton(box, "Elegir carpeta Markdown", lambda: self.elegir_archivo("Carpeta de apuntes", [],
                lambda p: vista.get_buffer().set_text(json.dumps({"carpeta": p}, ensure_ascii=False, indent=2)), carpeta=True))
        vista.get_buffer().set_text(json.dumps(editable, ensure_ascii=False, indent=2))
        sc = self.scroll(vista)
        sc.set_size_request(450, 150)
        box.append(sc)
        error = Gtk.Label(xalign=0, wrap=True)
        box.append(error)
        def guardar():
            try:
                buf = vista.get_buffer()
                data = json.loads(buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False))
                if not isinstance(data, dict) or any(k in data for k in ("enabled", "trusted_version")):
                    raise ValueError("Introduce un objeto de configuración sin campos de activación")
                if item["id"] == "wikipedia" and data.get("idioma", "es") not in ("es", "en"):
                    raise ValueError("El idioma debe ser es o en")
                extensiones.configurar(self.con, item["id"], **data)
                error.set_text("Configuración guardada")
            except ValueError as e:
                error.set_text(str(e))
        self.boton(box, "Guardar configuración", guardar)
        dlg.set_extra_child(box)
        dlg.add_response("close", "Cerrar")
        dlg.present(self)

    def instalar(self, ruta):
        def preview(m):
            dlg = Adw.AlertDialog(heading=f"Instalar {m['name']} {m['version']}",
                body=f"Tipo: {m['type']} · API {m['api_version']}\n"
                     "Se instalará desactivado. Instalar no ejecuta código.\nPermisos: " + (", ".join(m["permissions"]) or "ninguno"))
            dlg.add_response("cancel", "Cancelar")
            dlg.add_response("install", "Instalar")
            def terminar(_d, r):
                if r == "install":
                    self.trabajo(lambda: extensiones.instalar(ruta),
                        lambda _m: (self.actualizar_extensiones(), self.mensaje("Paquete instalado. Actívalo en la lista para usarlo.")))
            dlg.connect("response", terminar)
            dlg.present(self)
        self.trabajo(lambda: extensiones.inspeccionar(ruta), preview, "Comprobando paquete…")

    def cargar_paquete(self, item):
        def listo(data):
            dlg = Adw.AlertDialog(heading=item["name"],
                body=f"{len(data['documents'])} lecturas y {len(data['cards'])} tarjetas. Elige el mazo de destino.")
            box = self.columna()
            elegir = Gtk.DropDown.new_from_strings([d["name"] for d in self.mazos])
            box.append(elegir)
            for doc in data["documents"][:20]:
                box.append(Gtk.Label(label=doc["title"], xalign=0, wrap=True))
            for card in data["cards"][:10]:
                box.append(Gtk.Label(label=util.plain(card["front"])[:150], xalign=0, wrap=True))
            sc = self.scroll(box)
            sc.set_size_request(480, 260)
            dlg.set_extra_child(sc)
            dlg.add_response("cancel", "Cancelar")
            dlg.add_response("import", "Importar contenido")
            def importar(_d, r):
                if r != "import" or not self.mazos:
                    return
                mazo = self.mazos[elegir.get_selected()]
                try:
                    for doc in data["documents"]:
                        fuentes.importar(self.con, doc, mazo, commit=False)
                    self.con.commit()
                    if data["cards"]:
                        self.parent.on_importar_tarjetas(None, "import", data["cards"], elegir, self.mazos)
                    self.parent.refresh()
                    self.mensaje("Contenido importado; las tarjetas se guardan por lotes")
                except Exception as e:
                    self.con.rollback()
                    self.mensaje(str(e))
            dlg.connect("response", importar)
            dlg.present(self)
        self.trabajo(lambda: extensiones.contenido(item), listo)

    def vigilar(self):
        if not self.viva:
            return False
        item = self.fuente_actual()
        if item and item["id"] == "markdown" and not self.ocupada:
            self.buscar()
        return True
