"""La búsqueda global de Ctrl+K.

Lo que se protege: que se exijan todas las palabras (que es como espera todo el
mundo que funcione un buscador), que buscar «ingles» encuentre «inglés», y que
lo más relevante salga arriba sin importar en qué almacén estuviera.
"""
import time
import unittest

from appstudy import buscador, db, scheduler
from tests.apoyo import BaseTemporal

GOOD = scheduler.GOOD


class TestNormalizar(unittest.TestCase):
    def test_quita_acentos_y_mayusculas(self):
        self.assertEqual(buscador.normalizar("Inglés BÁSICO"), "ingles basico")

    def test_texto_vacio_o_nulo(self):
        self.assertEqual(buscador.normalizar(""), "")
        self.assertEqual(buscador.normalizar(None), "")


class TestPuntuar(unittest.TestCase):
    def test_le_falta_una_palabra_y_no_puntua(self):
        self.assertEqual(buscador._puntuar(["linux", "systemd"], "cosas de linux"), 0.0)

    def test_con_todas_las_palabras_puntua(self):
        self.assertGreater(
            buscador._puntuar(["linux", "systemd"], "systemd en linux"), 0.0)

    def test_el_primer_campo_pesa_mas_que_el_segundo(self):
        en_titulo = buscador._puntuar(["chmod"], "chmod", "otra cosa")
        en_cuerpo = buscador._puntuar(["chmod"], "otra cosa", "chmod")
        self.assertGreater(en_titulo, en_cuerpo)

    def test_empezar_por_la_palabra_vale_mas_que_llevarla_dentro(self):
        self.assertGreater(buscador._puntuar(["red"], "red de trabajo"),
                           buscador._puntuar(["red"], "una pared roja red"))

    def test_no_distingue_acentos(self):
        self.assertGreater(buscador._puntuar(["ingles"], "Inglés"), 0.0)

    def test_relaciona_sinonimos_y_flexiones_sin_modelo(self):
        puntos, relacionado = buscador._puntuar_amplio(
            ["administrar", "demonios"], "Controla los servicios del sistema")
        self.assertGreater(puntos, 0)
        self.assertTrue(relacionado)

    def test_una_relacion_no_puntua_si_falta_un_concepto(self):
        puntos, _ = buscador._puntuar_amplio(
            ["administrar", "bicicleta"], "Controla los servicios del sistema")
        self.assertEqual(puntos, 0)


class TestRecorte(unittest.TestCase):
    def test_recorta_alrededor_de_la_palabra(self):
        largo = "relleno " * 30 + "AGUJA " + "relleno " * 30
        salida = buscador._recorte(largo, ["aguja"])
        self.assertIn("AGUJA", salida)
        self.assertLess(len(salida), 120)

    def test_un_texto_corto_sale_entero(self):
        self.assertEqual(buscador._recorte("corto", ["corto"]), "corto")

    def test_quita_el_markup(self):
        self.assertNotIn("<b>", buscador._recorte("<b>negrita</b>", ["negrita"]))

    def test_texto_vacio(self):
        self.assertEqual(buscador._recorte("", ["x"]), "")


class TestBuscar(BaseTemporal):
    def poblar(self):
        linux = self.mazo("linux", "Linux")
        ingles = self.mazo("ingles", "Inglés", niveles=("A2", "B1"))
        self.tarjeta(linux, "¿Qué hace systemctl?",
                     "Controla los servicios de systemd.", tags="servicios")
        self.tarjeta(linux, "¿Qué hace chmod?", "Cambia los permisos.", key="linux")
        self.tarjeta(ingles, "How do you say «archivo»?", "File", key="ingles")
        db.upsert_chapter(self.con, linux, "linux", {
            "title": "Servicios systemd y temporizadores", "level": 1,
            "body": [{"p": "Un servicio se arranca con systemctl start."}]})
        db.book_abrir(self.con, "/libros/linux-avanzado.pdf", "Linux avanzado",
                      "Sistemas", 300)
        return linux, ingles

    def test_sin_consulta_no_devuelve_nada(self):
        self.poblar()
        for vacio in ("", "   ", "a"):
            self.assertEqual(buscador.buscar(self.con, vacio), [])

    def test_encuentra_en_los_cuatro_almacenes(self):
        self.poblar()
        db.nota_add(self.con, "/libros/linux-avanzado.pdf", 42, (0.1, 0.1, 0.9, 0.2),
                    texto="systemd arranca en paralelo", nota="repasar esto")
        tipos = {r["tipo"] for r in buscador.buscar(self.con, "systemd")}
        self.assertIn("tarjeta", tipos)
        self.assertIn("capitulo", tipos)
        self.assertIn("nota", tipos)
        tipos_libro = {r["tipo"] for r in buscador.buscar(self.con, "linux avanzado")}
        self.assertIn("libro", tipos_libro)

    def test_exige_todas_las_palabras(self):
        self.poblar()
        self.assertTrue(buscador.buscar(self.con, "systemd servicios"))
        self.assertEqual(buscador.buscar(self.con, "systemd bicicleta"), [])

    def test_no_distingue_acentos_ni_mayusculas(self):
        self.poblar()
        self.assertTrue(buscador.buscar(self.con, "INGLES"))
        self.assertTrue(buscador.buscar(self.con, "archivo"))

    def test_lo_del_titulo_sale_antes_que_lo_del_cuerpo(self):
        deck = self.mazo()
        self.tarjeta(deck, "Sobre las tuberías", "cosas variadas del sistema")
        self.tarjeta(deck, "Otra cosa cualquiera", "aquí se mencionan las tuberías")
        primero = buscador.buscar(self.con, "tuberías")[0]
        self.assertEqual(primero["titulo"], "Sobre las tuberías")

    def test_cada_resultado_trae_lo_que_la_lista_necesita(self):
        self.poblar()
        for r in buscador.buscar(self.con, "systemd"):
            for campo in ("tipo", "id", "titulo", "detalle", "contexto",
                          "icono", "etiqueta", "puntos"):
                self.assertIn(campo, r)

    def test_un_libro_del_estante_tambien_aparece(self):
        self.poblar()
        catalogo = [{"ruta": "/libros/redes.pdf", "nombre": "Redes desde cero",
                     "tema": "Sistemas", "ext": "pdf"}]
        titulos = [r["titulo"] for r in buscador.buscar(self.con, "redes", catalogo)]
        self.assertIn("Redes desde cero", titulos)

    def test_un_libro_ya_abierto_no_se_duplica_con_el_del_estante(self):
        self.poblar()
        catalogo = [{"ruta": "/libros/linux-avanzado.pdf", "nombre": "Linux avanzado",
                     "tema": "Sistemas", "ext": "pdf"}]
        libros = [r for r in buscador.buscar(self.con, "linux avanzado", catalogo)
                  if r["tipo"] == "libro"]
        self.assertEqual(len(libros), 1)

    def test_una_nota_trae_a_qué_página_ir(self):
        self.poblar()
        db.nota_add(self.con, "/libros/linux-avanzado.pdf", 77, (0, 0, 1, 0.1),
                    texto="una cita memorable")
        nota = next(r for r in buscador.buscar(self.con, "memorable")
                    if r["tipo"] == "nota")
        self.assertEqual(nota["pagina"], 77)
        self.assertEqual(nota["libro"]["ruta"], "/libros/linux-avanzado.pdf")

    def test_respeta_el_límite_pedido(self):
        deck = self.mazo()
        for i in range(40):
            self.tarjeta(deck, f"tubería número {i}", "sobre tuberías")
        self.assertLessEqual(len(buscador.buscar(self.con, "tubería", limite=5)), 5)

    def test_los_capitulos_tuyos_se_marcan_como_tuyos(self):
        deck = self.mazo()
        db.upsert_chapter(self.con, deck, "linux", {
            "title": "Mis apuntes de tuberías", "propio": True,
            "body": [{"p": "algo"}]})
        r = next(x for x in buscador.buscar(self.con, "apuntes"))
        self.assertIn("tuyo", r["contexto"])

    def test_una_base_recien_creada_no_revienta(self):
        self.assertEqual(buscador.buscar(self.con, "lo que sea"), [])

    def test_encuentra_por_conceptos_relacionados(self):
        self.poblar()
        salida = buscador.buscar(self.con, "administrar demonios")
        self.assertTrue(salida)
        self.assertIn("systemctl", salida[0]["titulo"])
        self.assertTrue(salida[0]["relacionado"])
        self.assertIn("Relacionado", salida[0]["contexto"])

    def test_la_coincidencia_literal_gana_a_la_relacionada(self):
        deck = self.mazo()
        self.tarjeta(deck, "Eliminar archivo", "literal")
        self.tarjeta(deck, "Borrar fichero", "relacionado")
        salida = buscador.buscar(self.con, "eliminar archivo")
        self.assertEqual(salida[0]["titulo"], "Eliminar archivo")
        self.assertFalse(salida[0]["relacionado"])


class TestRecientes(BaseTemporal):
    def test_sin_historial_no_hay_nada_que_ofrecer(self):
        self.assertEqual(buscador.recientes(self.con), [])

    def test_ofrece_lo_ultimo_estudiado(self):
        deck = self.mazo()
        vieja = self.tarjeta(deck, "la vieja")
        nueva = self.tarjeta(deck, "la nueva")
        self.repasar(vieja, GOOD, cuando=time.time() - 5000)
        self.repasar(nueva, GOOD)
        primero = buscador.recientes(self.con)[0]
        self.assertEqual(primero["titulo"], "la nueva")

    def test_ofrece_seguir_leyendo(self):
        db.book_abrir(self.con, "/libros/uno.pdf", "El libro", "Tema", 100)
        salida = buscador.recientes(self.con)
        self.assertTrue(any(r["tipo"] == "libro" for r in salida))

    def test_no_devuelve_mas_de_lo_pedido(self):
        deck = self.mazo()
        for i in range(20):
            self.repasar(self.tarjeta(deck, f"t{i}"), GOOD)
        self.assertLessEqual(len(buscador.recientes(self.con, 4)), 4)


class TestCuando(unittest.TestCase):
    def test_las_formas_de_decir_hace_cuanto(self):
        ahora = time.time()
        self.assertEqual(buscador.cuando(0), "")
        self.assertEqual(buscador.cuando(ahora - 60), "hace un rato")
        self.assertEqual(buscador.cuando(ahora - 7200), "hace 2 h")
        self.assertEqual(buscador.cuando(ahora - 3 * 86400), "hace 3 d")


if __name__ == "__main__":
    unittest.main()
