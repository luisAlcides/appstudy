"""Subrayados y notas de los libros, y la lectura de EPUB.

Las coordenadas se guardan de 0 a 1, relativas a la página: es lo que hace que
un subrayado siga en su sitio con cualquier zoom y en cualquier pantalla. Aquí
se comprueba eso, y que el EPUB se lea en el orden correcto.
"""
import unittest
import zipfile
from pathlib import Path

from appstudy import db, libros
from tests.apoyo import BaseTemporal

LIBRO = "/libros/uno.pdf"


class TestNotas(BaseTemporal):
    def test_guarda_y_devuelve_un_subrayado(self):
        nota_id = db.nota_add(self.con, LIBRO, 12, (0.1, 0.2, 0.8, 0.3),
                              texto="una frase", nota="mi comentario")
        notas = db.notas_de(self.con, LIBRO)
        self.assertEqual(len(notas), 1)
        n = notas[0]
        self.assertEqual(n["id"], nota_id)
        self.assertEqual(n["pagina"], 12)
        self.assertEqual(n["texto"], "una frase")
        self.assertEqual(n["nota"], "mi comentario")
        self.assertEqual(n["color"], "amarillo")

    def test_el_rectangulo_se_ordena_solo(self):
        # Arrastrar de abajo a la derecha hacia arriba a la izquierda vale igual
        db.nota_add(self.con, LIBRO, 1, (0.8, 0.9, 0.2, 0.1))
        n = db.notas_de(self.con, LIBRO)[0]
        self.assertAlmostEqual(n["x0"], 0.2)
        self.assertAlmostEqual(n["y0"], 0.1)
        self.assertAlmostEqual(n["x1"], 0.8)
        self.assertAlmostEqual(n["y1"], 0.9)

    def test_filtra_por_pagina(self):
        db.nota_add(self.con, LIBRO, 5, (0, 0, 1, 0.1))
        db.nota_add(self.con, LIBRO, 9, (0, 0, 1, 0.1))
        self.assertEqual(len(db.notas_de(self.con, LIBRO, 5)), 1)
        self.assertEqual(len(db.notas_de(self.con, LIBRO)), 2)

    def test_cada_libro_tiene_los_suyos(self):
        db.nota_add(self.con, LIBRO, 1, (0, 0, 1, 0.1))
        db.nota_add(self.con, "/libros/dos.pdf", 1, (0, 0, 1, 0.1))
        self.assertEqual(len(db.notas_de(self.con, LIBRO)), 1)

    def test_salen_ordenados_por_pagina_y_por_posicion(self):
        db.nota_add(self.con, LIBRO, 9, (0, 0.5, 1, 0.6))
        db.nota_add(self.con, LIBRO, 2, (0, 0.8, 1, 0.9))
        db.nota_add(self.con, LIBRO, 2, (0, 0.1, 1, 0.2))
        orden = [(n["pagina"], round(n["y0"], 1)) for n in db.notas_de(self.con, LIBRO)]
        self.assertEqual(orden, [(2, 0.1), (2, 0.8), (9, 0.5)])

    def test_un_color_inventado_cae_en_el_de_siempre(self):
        db.nota_add(self.con, LIBRO, 1, (0, 0, 1, 0.1), color="turquesa")
        self.assertEqual(db.notas_de(self.con, LIBRO)[0]["color"], "amarillo")

    def test_todos_los_colores_de_la_paleta_valen(self):
        for color in db.COLORES_NOTA:
            db.nota_add(self.con, LIBRO, 1, (0, 0, 1, 0.1), color=color)
        colores = {n["color"] for n in db.notas_de(self.con, LIBRO)}
        self.assertEqual(colores, set(db.COLORES_NOTA))

    def test_editar_cambia_solo_lo_que_le_pidas(self):
        nota_id = db.nota_add(self.con, LIBRO, 1, (0, 0, 1, 0.1), texto="original")
        db.nota_editar(self.con, nota_id, nota="lo que pienso")
        n = db.notas_de(self.con, LIBRO)[0]
        self.assertEqual(n["nota"], "lo que pienso")
        self.assertEqual(n["texto"], "original")

    def test_editar_un_campo_que_no_existe_no_hace_nada(self):
        nota_id = db.nota_add(self.con, LIBRO, 1, (0, 0, 1, 0.1))
        db.nota_editar(self.con, nota_id, pagina=99, inventado="x")
        self.assertEqual(db.notas_de(self.con, LIBRO)[0]["pagina"], 1)

    def test_queda_apuntada_la_tarjeta_que_salio_del_subrayado(self):
        deck = self.mazo()
        cid = self.tarjeta(deck, "¿De dónde salió esto?")
        nota_id = db.nota_add(self.con, LIBRO, 1, (0, 0, 1, 0.1))
        db.nota_editar(self.con, nota_id, card_id=cid)
        self.assertEqual(db.notas_de(self.con, LIBRO)[0]["card_id"], cid)

    def test_borrar_quita_solo_ese(self):
        uno = db.nota_add(self.con, LIBRO, 1, (0, 0, 1, 0.1))
        db.nota_add(self.con, LIBRO, 2, (0, 0, 1, 0.1))
        db.nota_borrar(self.con, uno)
        self.assertEqual(len(db.notas_de(self.con, LIBRO)), 1)

    def test_los_totales_cuentan_libros_distintos(self):
        db.nota_add(self.con, LIBRO, 1, (0, 0, 1, 0.1))
        db.nota_add(self.con, LIBRO, 2, (0, 0, 1, 0.1))
        db.nota_add(self.con, "/libros/dos.pdf", 1, (0, 0, 1, 0.1))
        self.assertEqual(db.notas_totales(self.con), {"n": 3, "libros": 2})

    def test_sin_subrayados_los_totales_son_cero(self):
        self.assertEqual(db.notas_totales(self.con), {"n": 0, "libros": 0})

    def test_un_subrayado_sin_texto_debajo_sigue_valiendo(self):
        # Una figura o un escaneo: no hay texto, pero la marca se ve igual
        db.nota_add(self.con, LIBRO, 1, (0.1, 0.1, 0.5, 0.4))
        self.assertEqual(db.notas_de(self.con, LIBRO)[0]["texto"], "")


class TestTextoRegion(unittest.TestCase):
    def test_lo_que_no_es_pdf_no_da_texto(self):
        self.assertEqual(libros.texto_region("/x/uno.epub", 1, (0, 0, 1, 1)), "")
        self.assertEqual(libros.texto_region("/x/uno.txt", 1, (0, 0, 1, 1)), "")

    def test_un_pdf_que_no_existe_no_revienta(self):
        self.assertEqual(
            libros.texto_region("/no/existe.pdf", 1, (0, 0, 1, 1), (595, 842)), "")


class TestEpub(unittest.TestCase):
    """Un EPUB de mentira, montado aquí mismo, para no depender de ninguno."""

    def crear(self, carpeta: Path, con_indice=True) -> Path:
        ruta = carpeta / "libro.epub"
        opf = """<?xml version="1.0"?>
<package><manifest>
  <item id="uno" href="cap1.xhtml" media-type="application/xhtml+xml"/>
  <item id="dos" href="cap2.xhtml" media-type="application/xhtml+xml"/>
  <item id="tres" href="cap3.xhtml" media-type="application/xhtml+xml"/>
</manifest><spine>
  <itemref idref="uno"/><itemref idref="dos"/><itemref idref="tres"/>
</spine></package>"""
        contenedor = ('<?xml version="1.0"?><container><rootfiles>'
                      '<rootfile full-path="OEBPS/libro.opf"/>'
                      '</rootfiles></container>')
        ncx = """<?xml version="1.0"?>
<ncx><navMap>
 <navPoint><navLabel><text>El principio</text></navLabel>
   <content src="cap1.xhtml"/></navPoint>
 <navPoint><navLabel><text>La
   mitad</text></navLabel><content src="cap2.xhtml#x"/></navPoint>
</navMap></ncx>"""
        with zipfile.ZipFile(ruta, "w") as z:
            z.writestr("META-INF/container.xml", contenedor)
            z.writestr("OEBPS/libro.opf", opf)
            if con_indice:
                z.writestr("OEBPS/toc.ncx", ncx)
            for i in (1, 2, 3):
                z.writestr(f"OEBPS/cap{i}.xhtml",
                           f"<html><body><p>Capítulo {i}</p></body></html>")
        return ruta

    def setUp(self):
        import tempfile
        from appstudy import db as _db
        self.tmp = Path(tempfile.mkdtemp(prefix="epub-test-"))
        self.ruta = self.crear(self.tmp)
        # La caché de los EPUB cuelga de DATA_DIR: se reapunta al temporal para
        # no dejar nada en la carpeta de verdad.
        self._data_dir = _db.DATA_DIR
        _db.DATA_DIR = self.tmp / "datos"
        self.addCleanup(self._limpiar)

    def _limpiar(self):
        import shutil
        from appstudy import db as _db
        _db.DATA_DIR = self._data_dir
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_los_capitulos_salen_en_el_orden_del_libro(self):
        caps = libros.capitulos_epub(str(self.ruta))
        self.assertEqual([c["href"] for c in caps],
                         ["OEBPS/cap1.xhtml", "OEBPS/cap2.xhtml", "OEBPS/cap3.xhtml"])

    def test_los_titulos_salen_del_indice(self):
        caps = libros.capitulos_epub(str(self.ruta))
        self.assertEqual(caps[0]["titulo"], "El principio")

    def test_un_titulo_partido_en_varias_lineas_se_junta(self):
        caps = libros.capitulos_epub(str(self.ruta))
        self.assertEqual(caps[1]["titulo"], "La mitad")

    def test_sin_indice_se_usa_el_nombre_del_archivo(self):
        ruta = self.crear(self.tmp, con_indice=False)
        caps = libros.capitulos_epub(str(ruta))
        self.assertTrue(all(c["titulo"] for c in caps))

    def test_un_archivo_que_no_es_epub_da_un_error_legible(self):
        malo = self.tmp / "roto.epub"
        malo.write_text("esto no es un zip")
        with self.assertRaises(libros.LibroError):
            libros.capitulos_epub(str(malo))

    def test_desplegar_deja_los_capitulos_donde_se_esperan(self):
        carpeta = libros.desplegar(str(self.ruta))
        for cap in libros.capitulos_epub(str(self.ruta)):
            self.assertTrue((carpeta / cap["href"]).exists())

    def test_desplegar_dos_veces_no_repite_el_trabajo(self):
        primera = libros.desplegar(str(self.ruta))
        marca = primera / ".listo"
        antes = marca.stat().st_mtime
        segunda = libros.desplegar(str(self.ruta))
        self.assertEqual(primera, segunda)
        self.assertEqual(marca.stat().st_mtime, antes)

    def test_un_zip_con_rutas_de_escape_no_escribe_fuera(self):
        # Un EPUB puede traer «../../algo»: se descarta en vez de obedecer.
        malicioso = self.tmp / "malo.epub"
        with zipfile.ZipFile(malicioso, "w") as z:
            z.writestr("META-INF/container.xml",
                       '<container><rootfiles><rootfile full-path="c.opf"/>'
                       '</rootfiles></container>')
            z.writestr("c.opf", '<package><manifest>'
                                '<item id="a" href="a.xhtml"/></manifest>'
                                '<spine><itemref idref="a"/></spine></package>')
            z.writestr("a.xhtml", "<html><body>hola</body></html>")
            z.writestr("../fuera.txt", "no debería salir de aquí")
        carpeta = libros.desplegar(str(malicioso))
        self.assertFalse((carpeta.parent / "fuera.txt").exists())
        self.assertTrue((carpeta / "a.xhtml").exists())


if __name__ == "__main__":
    unittest.main()
