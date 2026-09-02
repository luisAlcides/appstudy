"""Capítulos propios escritos en Markdown.

Lo que se protege: que cada cosa del Markdown acabe en el bloque que le toca,
que la ida y vuelta no pierda nada, y sobre todo que reimportar el contenido de
fábrica no se lleve por delante lo que tú has escrito.
"""
import unittest
from pathlib import Path

from appstudy import db, lecturas, seed
from tests.apoyo import BaseTemporal


class TestCabecera(unittest.TestCase):
    def test_lee_los_campos_en_castellano(self):
        datos, resto = lecturas.cabecera(
            "---\nmazo: linux\nnivel: 2\nminutos: 8\netiquetas: shell, red\n---\n# Hola\n")
        self.assertEqual(datos["deck"], "linux")
        self.assertEqual(datos["level"], "2")
        self.assertEqual(datos["minutes"], "8")
        self.assertEqual(datos["tags"], "shell, red")
        self.assertTrue(resto.startswith("# Hola"))

    def test_tambien_acepta_los_nombres_en_ingles(self):
        datos, _ = lecturas.cabecera("---\ndeck: ia\nlevel: 3\ntags: rag\n---\n")
        self.assertEqual(datos["deck"], "ia")
        self.assertEqual(datos["level"], "3")

    def test_sin_cabecera_devuelve_el_texto_entero(self):
        datos, resto = lecturas.cabecera("# Solo un título\n")
        self.assertEqual(datos, {})
        self.assertEqual(resto, "# Solo un título\n")

    def test_una_clave_desconocida_se_ignora(self):
        datos, _ = lecturas.cabecera("---\nmazo: linux\ncolorete: rojo\n---\n")
        self.assertEqual(set(datos), {"deck"})


class TestBloques(unittest.TestCase):
    def bloques(self, md):
        return lecturas.a_bloques(md)[1]

    def test_el_primer_titulo_es_el_del_capitulo(self):
        titulo, bloques = lecturas.a_bloques("# El título\n\nUn párrafo.\n")
        self.assertEqual(titulo, "El título")
        self.assertEqual(bloques, [{"p": "Un párrafo."}])

    def test_los_demas_titulos_son_secciones(self):
        self.assertEqual(self.bloques("## Una sección\n"), [{"h": "Una sección"}])
        self.assertEqual(self.bloques("### Otra\n"), [{"h": "Otra"}])

    def test_un_parrafo_de_varias_lineas_se_junta(self):
        self.assertEqual(self.bloques("una linea\ny otra\n"),
                         [{"p": "una linea y otra"}])

    def test_una_linea_en_blanco_separa_parrafos(self):
        self.assertEqual(self.bloques("uno\n\ndos\n"), [{"p": "uno"}, {"p": "dos"}])

    def test_negrita_cursiva_y_codigo(self):
        salida = self.bloques("con **negrita**, *cursiva* y `código`.\n")[0]["p"]
        self.assertIn("<b>negrita</b>", salida)
        self.assertIn("<i>cursiva</i>", salida)
        self.assertIn("<code>código</code>", salida)

    def test_un_asterisco_suelto_no_abre_cursiva(self):
        self.assertEqual(self.bloques("2 * 3 * 4\n"), [{"p": "2 * 3 * 4"}])

    def test_lista_con_vinetas(self):
        self.assertEqual(self.bloques("- uno\n- dos\n"), [{"list": ["uno", "dos"]}])

    def test_lista_numerada_son_pasos(self):
        self.assertEqual(self.bloques("1. uno\n2. dos\n"), [{"steps": ["uno", "dos"]}])

    def test_cambiar_de_tipo_de_lista_abre_otra(self):
        self.assertEqual(self.bloques("- uno\n1. dos\n"),
                         [{"list": ["uno"]}, {"steps": ["dos"]}])

    def test_bloque_de_codigo_con_lenguaje(self):
        self.assertEqual(self.bloques("```bash\nls -l\n```\n"),
                         [{"code": {"lang": "bash", "text": "ls -l"}}])

    def test_bloque_de_codigo_sin_lenguaje(self):
        self.assertEqual(self.bloques("```\nhola\n```\n"), [{"code": {"text": "hola"}}])

    def test_dentro_del_codigo_no_se_interpreta_nada(self):
        salida = self.bloques("```\n- no es lista\n**no es negrita**\n```\n")
        self.assertEqual(salida[0]["code"]["text"], "- no es lista\n**no es negrita**")

    def test_un_codigo_sin_cerrar_no_se_come_el_resto(self):
        salida = self.bloques("```\nsin cerrar\n")
        self.assertEqual(salida, [{"code": {"text": "sin cerrar"}}])

    def test_cita_normal(self):
        self.assertEqual(self.bloques("> una cita\n"), [{"quote": "una cita"}])

    def test_los_avisos_van_a_su_recuadro(self):
        casos = (("NOTA", "note"), ("AVISO", "warn"), ("CLAVE", "key"),
                 ("NOTE", "note"), ("WARNING", "warn"))
        for etiqueta, clase in casos:
            with self.subTest(etiqueta=etiqueta):
                self.assertEqual(self.bloques(f"> [!{etiqueta}] ojo con esto\n"),
                                 [{clase: "ojo con esto"}])

    def test_un_aviso_desconocido_se_queda_en_nota(self):
        self.assertEqual(self.bloques("> [!INVENTADO] algo\n"), [{"note": "algo"}])

    def test_una_cita_de_varias_lineas_se_junta(self):
        self.assertEqual(self.bloques("> una\n> y otra\n"), [{"quote": "una y otra"}])

    def test_formula_suelta(self):
        self.assertEqual(self.bloques("$$E = mc^2$$\n"), [{"math": "E = mc^2"}])

    def test_un_documento_vacio_no_da_bloques(self):
        self.assertEqual(self.bloques("\n\n  \n"), [])


class TestMinutos(unittest.TestCase):
    def test_estima_por_palabras(self):
        bloques = [{"p": " ".join(["palabra"] * lecturas.PALABRAS_POR_MINUTO * 3)}]
        self.assertEqual(lecturas.minutos_de(bloques), 3)

    def test_nunca_baja_de_un_minuto(self):
        self.assertEqual(lecturas.minutos_de([{"p": "dos palabras"}]), 1)

    def test_cuenta_tambien_dentro_de_listas_y_codigo(self):
        muchos = ["palabra"] * 200
        self.assertGreater(lecturas.minutos_de([{"list": muchos}]), 0)


class TestAnalizar(unittest.TestCase):
    MD = ("---\nmazo: linux\nnivel: 2\nminutos: 7\netiquetas: shell\n---\n\n"
          "# Los permisos\n\nUn párrafo.\n\n## Sección\n\n- uno\n")

    def test_saca_todo_lo_que_la_base_necesita(self):
        c = lecturas.analizar(self.MD, "permisos.md")
        self.assertEqual(c["deck"], "linux")
        self.assertEqual(c["title"], "Los permisos")
        self.assertEqual(c["level"], 2)
        self.assertEqual(c["minutes"], 7)
        self.assertEqual(c["tags"], "shell")
        self.assertTrue(c["propio"])
        self.assertEqual(len(c["body"]), 3)

    def test_sin_minutos_los_estima(self):
        c = lecturas.analizar("---\nmazo: linux\n---\n# Hola\n\nUn párrafo corto.\n")
        self.assertGreaterEqual(c["minutes"], 1)

    def test_sin_titulo_usa_el_nombre_del_archivo(self):
        c = lecturas.analizar("---\nmazo: linux\n---\n\nSolo un párrafo.\n",
                              "mis-notas.md")
        self.assertEqual(c["title"], "mis-notas")

    def test_un_nivel_absurdo_se_acota(self):
        self.assertEqual(lecturas.analizar("---\nnivel: 0\n---\n# H\n")["level"], 1)
        self.assertEqual(lecturas.analizar("---\nnivel: hola\n---\n# H\n")["level"], 1)

    def test_el_mazo_se_normaliza_a_minusculas(self):
        self.assertEqual(lecturas.analizar("---\nmazo:  LINUX \n---\n# H\n")["deck"],
                         "linux")


class TestVuelta(unittest.TestCase):
    """De capítulo a Markdown y otra vez a capítulo, sin perder nada."""

    def test_el_viaje_de_ida_y_vuelta_conserva_los_bloques(self):
        original = ("---\nmazo: linux\nnivel: 2\nminutos: 7\netiquetas: shell\n---\n\n"
                    "# El título\n\nUn párrafo con **negrita**.\n\n"
                    "## Sección\n\n- uno\n- dos\n\n1. paso uno\n2. paso dos\n\n"
                    "```bash\nls -l\n```\n\n> una cita\n\n> [!CLAVE] lo importante\n\n"
                    "$$a = b$$\n")
        primero = lecturas.analizar(original)
        segundo = lecturas.analizar(lecturas.a_markdown(primero))
        self.assertEqual(segundo["body"], primero["body"])
        self.assertEqual(segundo["title"], primero["title"])
        self.assertEqual(segundo["deck"], primero["deck"])
        self.assertEqual(segundo["level"], primero["level"])
        self.assertEqual(segundo["tags"], primero["tags"])

    def test_el_markup_vuelve_a_ser_markdown(self):
        md = lecturas.a_markdown({"deck": "linux", "title": "T", "body": [
            {"p": "con <b>negrita</b> y <code>código</code>"}]})
        self.assertIn("**negrita**", md)
        self.assertIn("`código`", md)
        self.assertNotIn("<b>", md)


class TestImportar(BaseTemporal):
    def setUp(self):
        super().setUp()
        self._carpeta = lecturas.CARPETA
        lecturas.CARPETA = self.tmp / "lecturas"
        lecturas.CARPETA.mkdir(parents=True, exist_ok=True)
        self.addCleanup(self._restaurar)

    def _restaurar(self):
        lecturas.CARPETA = self._carpeta

    def escribir(self, nombre, texto):
        ruta = lecturas.CARPETA / nombre
        ruta.write_text(texto, encoding="utf-8")
        return ruta

    def test_importa_un_capitulo_tuyo(self):
        self.mazo()
        self.escribir("mio.md", "---\nmazo: linux\nnivel: 2\n---\n# El mío\n\nHola.\n")
        self.assertEqual(lecturas.importar(self.con), (1, 0))
        fila = self.con.execute("SELECT * FROM chapters WHERE propio=1").fetchone()
        self.assertEqual(fila["title"], "El mío")
        self.assertEqual(fila["level"], 2)
        self.assertTrue(fila["fuente"].endswith("mio.md"))

    def test_un_mazo_que_no_existe_se_salta_sin_ruido(self):
        self.mazo()
        self.escribir("otro.md", "---\nmazo: fantasma\n---\n# Ni idea\n\nHola.\n")
        self.assertEqual(lecturas.importar(self.con), (0, 1))
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM chapters").fetchone()[0], 0)

    def test_un_archivo_sin_contenido_se_salta(self):
        self.mazo()
        self.escribir("vacio.md", "---\nmazo: linux\n---\n# Solo título\n")
        self.assertEqual(lecturas.importar(self.con), (0, 1))

    def test_reimportar_actualiza_sin_duplicar(self):
        self.mazo()
        self.escribir("mio.md", "---\nmazo: linux\n---\n# El mío\n\nPrimera versión.\n")
        lecturas.importar(self.con)
        self.escribir("mio.md", "---\nmazo: linux\n---\n# El mío\n\nSegunda versión.\n")
        lecturas.importar(self.con)
        filas = self.con.execute("SELECT body FROM chapters WHERE propio=1").fetchall()
        self.assertEqual(len(filas), 1)
        self.assertIn("Segunda", filas[0]["body"])

    def test_el_progreso_de_lectura_sobrevive_a_reimportar(self):
        self.mazo()
        self.escribir("mio.md", "---\nmazo: linux\n---\n# El mío\n\nUno.\n")
        lecturas.importar(self.con)
        cid = self.con.execute("SELECT id FROM chapters").fetchone()["id"]
        db.mark_read(self.con, cid)
        self.escribir("mio.md", "---\nmazo: linux\n---\n# El mío\n\nDos.\n")
        lecturas.importar(self.con)
        self.assertEqual(self.con.execute(
            "SELECT leido FROM reading WHERE chapter_id=?", (cid,)).fetchone()[0], 1)

    def test_borrar_el_archivo_retira_el_capitulo(self):
        self.mazo()
        ruta = self.escribir("mio.md", "---\nmazo: linux\n---\n# El mío\n\nUno.\n")
        lecturas.importar(self.con)
        ruta.unlink()
        self.assertEqual(lecturas.limpiar_huerfanos(self.con), 1)
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM chapters").fetchone()[0], 0)

    def test_no_retira_los_de_fabrica(self):
        deck = self.mazo()
        db.upsert_chapter(self.con, deck, "linux", {"title": "De fábrica", "body": [{}]})
        self.assertEqual(lecturas.limpiar_huerfanos(self.con), 0)

    def test_un_capitulo_tuyo_y_uno_de_fabrica_pueden_llamarse_igual(self):
        deck = self.mazo()
        db.upsert_chapter(self.con, deck, "linux",
                          {"title": "Permisos", "body": [{"p": "de fábrica"}]})
        self.escribir("p.md", "---\nmazo: linux\n---\n# Permisos\n\nEl mío.\n")
        lecturas.importar(self.con)
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM chapters").fetchone()[0], 2)


class TestConvivencia(BaseTemporal):
    """Lo que más duele: que recargar lo de fábrica borre lo tuyo."""

    def setUp(self):
        super().setUp()
        self._carpeta = lecturas.CARPETA
        lecturas.CARPETA = self.tmp / "lecturas"
        lecturas.CARPETA.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: setattr(lecturas, "CARPETA", self._carpeta))

    def test_recargar_el_contenido_incluido_respeta_tus_capitulos(self):
        seed.load_all(self.con)
        (lecturas.CARPETA / "mio.md").write_text(
            "---\nmazo: linux\n---\n# Sólo mío\n\nContenido.\n", encoding="utf-8")
        lecturas.importar(self.con)
        antes = self.con.execute(
            "SELECT COUNT(*) FROM chapters WHERE propio=1").fetchone()[0]
        self.assertEqual(antes, 1)

        seed.load_readings(self.con)          # la recarga que borraba los tuyos

        self.assertEqual(self.con.execute(
            "SELECT COUNT(*) FROM chapters WHERE propio=1").fetchone()[0], 1)
        self.assertIsNotNone(self.con.execute(
            "SELECT 1 FROM chapters WHERE title='Sólo mío'").fetchone())

    def test_load_all_importa_los_tuyos_junto_a_los_de_fabrica(self):
        (lecturas.CARPETA / "mio.md").write_text(
            "---\nmazo: linux\n---\n# Sólo mío\n\nContenido.\n", encoding="utf-8")
        _, _, _, capitulos = seed.load_all(self.con)
        de_fabrica = sum(len(__import__("json").loads(
            Path(a).read_text(encoding="utf-8"))["chapters"])
            for a in (seed.READINGS_DIR).glob("*.json"))
        self.assertEqual(capitulos, de_fabrica + 1)


if __name__ == "__main__":
    unittest.main()
