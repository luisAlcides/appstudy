import base64
import json
from pathlib import Path
import sqlite3
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import zlib

from appstudy import db, documentos, exportador, extensiones, fuentes, importador, multimedia
from tests.apoyo import BaseTemporal

def _png_chunk(tipo, data):
    return struct.pack("!I", len(data)) + tipo + data + struct.pack("!I", zlib.crc32(tipo + data))


PNG = (b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", struct.pack("!IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) +
       _png_chunk(b"IDAT", zlib.compress(b"\0\xff\0\0")) + _png_chunk(b"IEND", b""))


class FuentesTest(BaseTemporal):
    def setUp(self):
        super().setUp()
        self.did = self.mazo()
        self.deck = dict(self.con.execute("SELECT * FROM decks WHERE id=?", (self.did,)).fetchone())

    def test_importar_actualiza_sin_perder_progreso_ni_duplicar(self):
        doc = fuentes.documento("markdown", "/apuntes/permisos.md", "Permisos", "# Permisos\nEl modo de un archivo.")
        cap = fuentes.importar(self.con, doc, self.deck)
        db.mark_read(self.con, cap["id"])
        doc["text"] += "\nNueva información"
        otro = fuentes.importar(self.con, doc, self.deck)
        self.assertEqual(cap["id"], otro["id"])
        self.assertTrue(otro["leido"])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM chapters").fetchone()[0], 1)
        self.assertEqual(fuentes.estado(self.con, doc, self.did), "sin cambios")

    def test_mismo_titulo_distinto_origen_no_colisiona(self):
        a = fuentes.importar(self.con, fuentes.documento("markdown", "/uno.md", "Tema", "Texto uno"), self.deck)
        b = fuentes.importar(self.con, fuentes.documento("markdown", "/dos.md", "Tema", "Texto dos"), self.deck)
        self.assertNotEqual(a["id"], b["id"])

    def test_borrar_y_reimportar_recrea_capitulo(self):
        doc = fuentes.documento("markdown", "/uno.md", "Tema", "Texto uno")
        cap = fuentes.importar(self.con, doc, self.deck)
        db.borrar_capitulo(self.con, cap["id"])
        self.assertEqual(fuentes.estado(self.con, doc, self.did), "nuevo")
        self.assertIsNotNone(fuentes.importar(self.con, doc, self.deck))

    def test_atribucion_e_indice(self):
        doc = fuentes.documento("wikipedia", "https://es.wikipedia.org/wiki/Linux", "Linux", "El kernel administra procesos.",
                                author="Autores", license="CC BY-SA 4.0")
        cap = fuentes.importar(self.con, doc, self.deck)
        self.assertIn("CC BY-SA 4.0", cap["body"])
        self.assertIn("Autores", cap["body"])
        encontrados = documentos.buscar(self.con, "kernel")
        self.assertEqual(encontrados[0]["origin"], doc["origin"])

    def test_importar_documento_conserva_paginas_en_indice(self):
        doc = fuentes.documento("documentos", "/libro.pdf", "Libro", "Texto extraído",
                                pages=[("Página 12", "El kernel administra procesos")])
        fuentes.importar(self.con, doc, self.deck)
        self.assertIn("Página 12", documentos.buscar(self.con, "kernel")[0]["locator"])

    def test_carpeta_detecta_cambios_contenido_y_excluye_symlink(self):
        carpeta = self.tmp / "apuntes"
        carpeta.mkdir()
        p = carpeta / "Tema.md"
        p.write_text("# Tema\nContenido", encoding="utf-8")
        (carpeta / "enlace.md").symlink_to(p)
        resultado = fuentes.cambios_carpeta(str(carpeta), {})
        self.assertEqual(len(resultado), 1)
        self.assertTrue(resultado[0]["summary"].startswith("Nuevo"))
        doc = fuentes.previsualizar(resultado[0])
        previos = {str(p): [fuentes.huella(doc)]}
        self.assertTrue(fuentes.cambios_carpeta(str(carpeta), previos)[0]["summary"].startswith("Sin cambios"))
        p.write_text("# Tema\nOtro contenido", encoding="utf-8")
        self.assertTrue(fuentes.cambios_carpeta(str(carpeta), previos)[0]["summary"].startswith("Actualizado"))

    def test_urls_rechazan_host_parecido_http_puertos_y_credenciales(self):
        for url in ("http://openstax.org/a", "https://openstax.org.evil.test/a", "https://localhost/a",
                    "https://openstax.org:8000/a", "https://user@openstax.org/a", "file:///etc/passwd"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                fuentes.validar_url(url, fuentes.DOMINIOS["openstax"])

    def test_parser_omite_scripts_y_prefiere_articulo(self):
        pagina = fuentes.Pagina('<html><head><title>Título</title><meta name="citation_author" content="Ana"></head>'
            '<nav>Menú</nav><main><p>Contenido</p><script>peligro</script><a href="/a.pdf">PDF</a></main><footer>Pie</footer></html>')
        self.assertIn("Contenido", pagina.texto)
        self.assertNotIn("peligro", pagina.texto)
        self.assertNotIn("Menú", pagina.texto)
        self.assertEqual(pagina.autores, ["Ana"])
        self.assertIn(("/a.pdf", "PDF"), pagina.enlaces)

    def test_wikipedia_search_y_preview_normalizados(self):
        raw = json.dumps({"pages": [{"key": "Linux", "title": "Linux", "excerpt": "El <b>kernel</b>"}]}).encode()
        with patch.object(fuentes, "descargar", return_value=(raw, "application/json")):
            docs = fuentes.buscar("wikipedia", "Linux")
        self.assertEqual(docs[0]["summary"], "El kernel")
        with patch.object(fuentes, "descargar", return_value=(b"<main><p>Linux es un kernel.</p></main>", "text/html")):
            doc = fuentes.previsualizar(docs[0])
        self.assertIn("CC BY-SA", doc["license"])

    def test_mit_enlaces_pdf_resueltos_y_externos_excluidos(self):
        page = b'<main><p>Curso</p><a href="/courses/test/a.pdf">Apuntes</a><a href="https://evil.test/a.pdf">Otro</a></main>'
        item = fuentes.documento("mit", "https://ocw.mit.edu/courses/test/", "Curso")
        with patch.object(fuentes, "descargar", return_value=(page, "text/html")):
            doc = fuentes.previsualizar(item)
        self.assertEqual(len(doc["links"]), 1)
        self.assertEqual(doc["links"][0]["origin"], "https://ocw.mit.edu/courses/test/a.pdf")

    def test_descarga_pdf_exige_cabecera_real(self):
        item = fuentes.documento("mit", "https://ocw.mit.edu/a.pdf", "A")
        with patch.object(fuentes, "descargar", return_value=(b"<html>Error</html>", "text/html")):
            with self.assertRaises(ValueError):
                fuentes.descargar_pdf(item)

    def test_descarga_pdf_es_estable_y_no_sobrescribe_archivos_ajenos(self):
        item = fuentes.documento("mit", "https://ocw.mit.edu/a.pdf", "../../A")
        with patch.object(fuentes, "descargar", return_value=(b"%PDF-1.7\nfake", "application/pdf")):
            a, b = fuentes.descargar_pdf(item), fuentes.descargar_pdf(item)
        self.assertEqual(a, b)
        self.assertTrue(Path(a).is_relative_to(self.tmp))


class DocumentosTest(BaseTemporal):
    def test_indexar_otro_rango_pdf_conserva_las_paginas_anteriores(self):
        documentos.indexar(self.con, "a.pdf", "A", [("Página 1", "Kernel")], parcial=True)
        documentos.indexar(self.con, "a.pdf", "A", [("Página 2", "Memoria")], parcial=True)
        documentos.indexar(self.con, "a.pdf", "A", [("Página 1", "Permisos")], parcial=True)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM document_chunks").fetchone()[0], 2)
        self.assertTrue(documentos.buscar(self.con, "memoria"))
        self.assertEqual(documentos.buscar(self.con, "kernel"), [])

    def test_indexacion_reemplaza_fragmentos_y_busqueda_no_devuelve_ruido(self):
        documentos.indexar(self.con, "a", "A", [("Página 3", "Los permisos del kernel controlan archivos.")])
        self.assertIn("Página 3", documentos.buscar(self.con, "permisos")[0]["locator"])
        self.assertEqual(documentos.buscar(self.con, "astronomía"), [])
        documentos.indexar(self.con, "a", "A", [("Página 4", "La memoria es importante")])
        self.assertEqual(documentos.buscar(self.con, "permisos"), [])

    def test_pdf_conserva_numero_inicial_y_no_pagina_extra(self):
        p = self.tmp / "a.pdf"
        p.write_bytes(b"%PDF-1.7")
        with patch.object(documentos, "ejecutar", return_value="Primera\fSegunda\f"):
            paginas = documentos.extraer(p, 7, 8)
        self.assertEqual([n for n, _ in paginas], ["Página 7", "Página 8"])

    def test_ocr_rechaza_rango_e_idioma_invalidos(self):
        p = self.tmp / "a.pdf"
        p.write_bytes(b"%PDF-1.7")
        for args in ((0, 1, "eng"), (1, 60, "eng"), (1, 2, "eng;rm")):
            with self.assertRaises(ValueError):
                documentos.extraer(p, args[0], args[1], True, args[2])

    def test_ocr_procesa_cada_pagina_con_argumentos_separados(self):
        p = self.tmp / "un libro.pdf"
        p.write_bytes(b"%PDF-1.7")
        with patch.object(documentos, "ejecutar", side_effect=["", "Uno", "", "Dos"]) as run:
            paginas = documentos.extraer(p, 2, 3, True, "spa")
        self.assertEqual(paginas, [("Página 2 · OCR", "Uno"), ("Página 3 · OCR", "Dos")])
        self.assertEqual(run.call_args_list[1].args[0][-2:], ["-l", "spa"])

    def test_ia_sin_evidencia_no_se_invoca(self):
        from appstudy import ia
        with patch.object(ia, "_mensaje") as model:
            result = documentos.responder({"activa": True}, "Pregunta", [])
        model.assert_not_called()
        self.assertEqual(result["sources"], [])

    def test_ia_citas_verificadas_y_rechazo_de_citas_inventadas(self):
        from appstudy import ia
        f = [{"origin": "/a.pdf", "title": "A", "locator": "Página 2", "text": "El kernel controla los procesos del sistema."}]
        valid = {"answer": "El kernel controla procesos [1].", "citations": [{"id": 1, "quote": "El kernel controla los procesos"}]}
        with patch.object(ia, "_mensaje", return_value=json.dumps(valid)):
            self.assertEqual(documentos.responder({"activa": True}, "¿Qué controla?", f)["sources"][0]["locator"], "Página 2")
        for cita in ({"id": 7, "quote": "El kernel controla los procesos"}, {"id": 1, "quote": "Las naves controlan el sistema"}):
            with patch.object(ia, "_mensaje", return_value=json.dumps({**valid, "citations": [cita]})):
                with self.assertRaises(ValueError):
                    documentos.responder({"activa": True}, "Pregunta", f)

    def test_srt_y_vtt_con_marcas_y_etiquetas(self):
        for ext, data in (("srt", "1\n00:01:02,500 --> 00:01:04,000\nThis is <i>important</i>.\n"),
                          ("vtt", "WEBVTT\n\nNOTE ignored\nhello\n\n00:02.500 --> 00:04.000 align:start\nThis is important.\n")):
            p = self.tmp / ("subs." + ext)
            p.write_text(data, encoding="utf-8")
            cues = documentos.subtitulos(p)
            self.assertEqual(len(cues), 1)
            self.assertEqual(cues[0]["text"], "This is important.")
            card = documentos.tarjetas_subtitulos(cues, "Curso")[0]
            self.assertIn("{{important}}", card["front"])
            self.assertIn(cues[0]["time"], card["hint"])

    def test_subtitulos_rechaza_tiempos_invertidos(self):
        p = self.tmp / "subs.srt"
        p.write_text("1\n00:00:05,000 --> 00:00:02,000\nText", encoding="utf-8")
        with self.assertRaises(ValueError):
            documentos.subtitulos(p)


class ExtensionesTest(BaseTemporal):
    def paquete(self, manifest=None, files=None):
        m = {"id": "ejemplo", "name": "Ejemplo", "version": "1.0.0", "api_version": 1,
             "type": "content", "content": "content.json", "permissions": []}
        if manifest:
            m.update(manifest)
        p = self.tmp / ("test-" + str(len(list(self.tmp.glob("*.zip")))) + ".zip")
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("manifest.json", json.dumps(m))
            z.writestr("content.json", json.dumps({"format": 1, "cards": [], "documents": []}))
            for n, v in (files or {}).items():
                z.writestr(n, v)
        return p

    def test_instala_sin_activar_y_lee_contenido_al_activar(self):
        m = extensiones.instalar(self.paquete())
        item = next(x for x in extensiones.listar(self.con) if x["id"] == "ejemplo")
        self.assertFalse(item["enabled"])
        with self.assertRaises(ValueError):
            extensiones.contenido(item)
        extensiones.activar(self.con, item, True)
        item = next(x for x in extensiones.listar(self.con) if x["id"] == "ejemplo")
        self.assertEqual(extensiones.contenido(item), {"cards": [], "documents": []})
        self.assertTrue(Path(m["path"]).is_dir())

    def test_rechaza_path_traversal_codigo_en_contenido_y_version(self):
        for files in ({"../../outside": "oops"}, {"run.py": "print('oops')"}, {"/abs": "oops"},
                      {"./manifest.json": "{}"}, {"dir//file.txt": "oops"}):
            with self.assertRaises(ValueError):
                extensiones.inspeccionar(self.paquete(files=files))
        with self.assertRaises(ValueError):
            extensiones.inspeccionar(self.paquete({"api_version": 99}))

    def test_rechaza_symlink_y_zip_bomb_por_tamano_declarado(self):
        p = self.paquete()
        with zipfile.ZipFile(p, "a") as z:
            info = zipfile.ZipInfo("enlace")
            info.external_attr = 0o120777 << 16
            z.writestr(info, "/etc/passwd")
        with self.assertRaises(ValueError):
            extensiones.inspeccionar(p)
        with patch.object(extensiones, "MAX_PAQUETE", 10):
            with self.assertRaises(ValueError):
                extensiones.inspeccionar(self.paquete())

    def test_actualizar_requiere_activar_nueva_version(self):
        item = extensiones.instalar(self.paquete())
        extensiones.activar(self.con, item, True)
        extensiones.instalar(self.paquete({"version": "1.1.0"}))
        item = next(x for x in extensiones.listar(self.con) if x["id"] == "ejemplo")
        self.assertEqual(item["version"], "1.1.0")
        self.assertFalse(item["enabled"])

    def test_no_sobrescribe_version_existente(self):
        p = self.paquete()
        extensiones.instalar(p)
        with self.assertRaises(ValueError):
            extensiones.instalar(p)

    def test_plugin_protocolo_ejecucion_solo_tras_activar(self):
        script = ('import json,sys\nrequest=json.load(sys.stdin)\n'
                  'print(json.dumps([{"origin":"demo:1","title":request["payload"]["query"],"text":"Contenido"}]))\n')
        p = self.paquete({"type": "source", "entrypoint": "source.py", "permissions": ["execute_python"]}, {"source.py": script})
        extensiones.instalar(p)
        item = next(x for x in extensiones.listar(self.con) if x["id"] == "ejemplo")
        with self.assertRaises(ValueError):
            extensiones.ejecutar(item, "search", {"query": "Tema"})
        extensiones.activar(self.con, item, True)
        item = next(x for x in extensiones.listar(self.con) if x["id"] == "ejemplo")
        docs = extensiones.ejecutar(item, "search", {"query": "Tema"})
        self.assertEqual(docs[0]["title"], "Tema")
        self.assertEqual(docs[0]["provider"], "ejemplo")

    def test_documento_markdown_de_paquete(self):
        data = {"format": 1, "documents": [{"origin": "demo:1", "title": "Demo", "path": "docs/a.md"}]}
        docs = extensiones.validar_contenido(data, lambda p: b"# Demo\nContenido")
        self.assertIn("Contenido", docs["documents"][0]["text"])


class MultimediaExportacionTest(BaseTemporal):
    def test_migrar_copia_antigua_recrea_tablas_de_extensiones(self):
        for tabla in ("source_imports", "document_chunks", "card_media"):
            self.con.execute(f"DROP TABLE {tabla}")
        db.migrate(self.con)
        for tabla in ("source_imports", "document_chunks", "card_media"):
            self.assertEqual(self.con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0], 0)

    def test_sincronizacion_conserva_adjuntos_y_su_borrado(self):
        from appstudy import sincronizacion
        cid = self.tarjeta(self.mazo(), "Con imagen")
        multimedia.guardar(self.con, cid, [{"side": "front", "name": "a.png", "data": PNG}])
        self.con.commit()
        remoto = sqlite3.connect(":memory:")
        remoto.row_factory = sqlite3.Row
        remoto.execute("PRAGMA foreign_keys=ON")
        db.migrate(remoto)
        self.addCleanup(remoto.close)
        snap = sincronizacion.snapshot(self.con, "a" * 32)
        sincronizacion.fusionar(remoto, [snap], "b" * 32)
        rid = remoto.execute("SELECT id FROM cards WHERE front='Con imagen'").fetchone()[0]
        self.assertEqual(multimedia.leer(remoto, rid)[0]["data"], PNG)
        multimedia.guardar(self.con, cid, [])
        self.con.commit()
        sincronizacion.fusionar(remoto, [sincronizacion.snapshot(self.con, "a" * 32)], "b" * 32)
        self.assertEqual(multimedia.leer(remoto, rid), [])

    def test_paquete_resuelve_recursos_multimedia_relativos(self):
        data = {"format": 1, "cards": [{"front": "Imagen", "media": [{"side": "front", "name": "a.png", "path": "media/a.png"}]}]}
        contenido = extensiones.validar_contenido(data, lambda p: PNG)
        self.assertEqual(contenido["cards"][0]["media"][0]["data"], PNG)

    def test_exporta_json_e_importa_quiz_cloze_y_adjuntos(self):
        did = self.mazo()
        cid = self.tarjeta(did, "¿Qué ves?", kind="quiz", choices=["A", "B"], answer=1)
        multimedia.guardar(self.con, cid, [{"side": "front", "name": "imagen.png", "data": PNG}])
        self.tarjeta(did, "Esto es {{Linux}}", kind="cloze")
        destino = self.tmp / "cards.json"
        exportador.guardar(destino, exportador.tarjetas(self.con, did))
        cards = importador.leer(destino)
        self.assertEqual(cards[0]["choices"], ["A", "B"])
        self.assertEqual(cards[0]["answer"], 1)
        self.assertEqual(cards[0]["media"][0]["data"], PNG)
        self.assertEqual(cards[1]["kind"], "cloze")

    def test_zip_exportado_es_paquete_instalable(self):
        did = self.mazo()
        self.tarjeta(did, "Pregunta", "Respuesta")
        p = self.tmp / "cards.zip"
        exportador.guardar(p, exportador.tarjetas(self.con), "zip")
        m = extensiones.instalar(p)
        extensiones.activar(self.con, m, True)
        m = next(x for x in extensiones.listar(self.con) if x["id"] == "mis-tarjetas")
        self.assertEqual(extensiones.contenido(m)["cards"][0]["front"], "Pregunta")

    def test_multimedia_reemplaza_no_duplica_y_borrado_cascada(self):
        cid = self.tarjeta(self.mazo(), "Imagen")
        adjuntos = [{"name": "a.png", "side": "back", "data": PNG}]
        multimedia.guardar(self.con, cid, adjuntos)
        multimedia.guardar(self.con, cid, adjuntos)
        self.assertEqual(len(multimedia.leer(self.con, cid)), 1)
        db.delete_card(self.con, cid)
        self.assertEqual(multimedia.leer(self.con, cid), [])

    def test_rechaza_svg_ejecutable_y_base64_invalido(self):
        for datos in (b"<svg onload='evil()'/>", b"#!/bin/sh\nevil"):
            with self.assertRaises(ValueError):
                multimedia.validar({"data": datos})
        with self.assertRaises(ValueError):
            multimedia.deserializar([{"data": "%%%"}])

    def test_anki_extrae_imagen_y_audio_sin_escribir_nombre_remoto(self):
        p = self.tmp / "a.zip"
        wav = b"RIFF" + b"\0" * 4 + b"WAVEfmt " + b"\0" * 20
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("media", json.dumps({"0": "../../imagen.png", "1": "audio.wav"}))
            z.writestr("0", PNG)
            z.writestr("1", wav)
        with zipfile.ZipFile(p) as z:
            media = multimedia.de_anki(z, ['<img src="../../imagen.png">', '[sound:audio.wav]'])
        self.assertEqual([m["side"] for m in media], ["front", "back"])
        self.assertEqual(media[0]["data"], PNG)
        self.assertFalse((self.tmp.parent / "imagen.png").exists())

    def test_csv_comillas_y_formulas_neutralizadas(self):
        p = self.tmp / "cards.csv"
        exportador.guardar(p, [{"front": "=1+1", "back": 'una, "respuesta"\ncon salto'}], "csv")
        cards = importador.leer(p)
        self.assertEqual(cards[0]["front"], "'=1+1")
        self.assertIn('"respuesta"', cards[0]["back"])


if __name__ == "__main__":
    unittest.main()
