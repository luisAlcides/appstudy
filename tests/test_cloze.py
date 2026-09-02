"""Tarjetas de huecos escritas a mano.

Lo que se protege: que el texto marcado se pueda tapar y destapar sin perder
nada, que un hueco con pista siga siendo resoluble, y que el texto completo
vuelva exactamente igual que se escribió.
"""
import unittest

from appstudy import cloze


class TestDeteccion(unittest.TestCase):
    def test_reconoce_lo_que_lleva_huecos(self):
        self.assertTrue(cloze.tiene_huecos("El comando {{chmod}} cambia permisos."))

    def test_descarta_lo_que_no(self):
        for texto in ("Sin huecos.", "", None, "Una llave { sola }", "{{sin cerrar"):
            with self.subTest(texto=texto):
                self.assertFalse(cloze.tiene_huecos(texto))

    def test_cuenta_los_huecos(self):
        self.assertEqual(cloze.cuantos("{{a}} y {{b}} y {{c}}"), 3)
        self.assertEqual(cloze.cuantos("sin nada"), 0)


class TestHuecos(unittest.TestCase):
    def test_saca_las_respuestas_en_orden(self):
        h = cloze.huecos("En {{7}} el dueño, en {{5}} el grupo.")
        self.assertEqual([x["valor"] for x in h], ["7", "5"])
        self.assertEqual([x["indice"] for x in h], [0, 1])

    def test_la_pista_va_detras_de_dos_puntos_dobles(self):
        h = cloze.huecos("Es {{755::en octal}}.")
        self.assertEqual(h[0]["valor"], "755")
        self.assertEqual(h[0]["pista"], "en octal")

    def test_sin_pista_la_pista_queda_vacia(self):
        self.assertEqual(cloze.huecos("Es {{755}}.")[0]["pista"], "")

    def test_se_quitan_los_espacios_de_sobra(self):
        h = cloze.huecos("Es {{  755  ::  en octal  }}.")
        self.assertEqual(h[0]["valor"], "755")
        self.assertEqual(h[0]["pista"], "en octal")


class TestCompleto(unittest.TestCase):
    def test_devuelve_el_texto_tal_como_se_lee(self):
        self.assertEqual(cloze.completo("El comando {{chmod}} cambia los {{permisos}}."),
                         "El comando chmod cambia los permisos.")

    def test_la_pista_no_aparece_en_el_texto_completo(self):
        self.assertEqual(cloze.completo("Es {{755::en octal}}."), "Es 755.")

    def test_un_texto_sin_huecos_no_cambia(self):
        self.assertEqual(cloze.completo("Nada que tapar."), "Nada que tapar.")


class TestEnmascarar(unittest.TestCase):
    def test_tapa_solo_el_hueco_pedido(self):
        texto = "En {{7}} el dueño, en {{5}} el grupo."
        salida = cloze.enmascarar(texto, 0)
        self.assertIn(cloze.HUECO, salida)
        self.assertIn("5", salida)
        self.assertNotIn("7", salida)

    def test_sin_indice_los_tapa_todos(self):
        salida = cloze.enmascarar("En {{7}} el dueño, en {{5}} el grupo.")
        self.assertEqual(salida.count(cloze.HUECO), 2)
        self.assertNotIn("7", salida)
        self.assertNotIn("5", salida)

    def test_la_pista_se_enseña_junto_al_hueco(self):
        salida = cloze.enmascarar("Es {{755::en octal}}.", 0)
        self.assertIn("(en octal)", salida)
        self.assertNotIn("755", salida)

    def test_el_texto_de_alrededor_se_conserva_entero(self):
        texto = "El comando {{chmod}} cambia los permisos del archivo."
        salida = cloze.enmascarar(texto, 0)
        self.assertTrue(salida.startswith("El comando "))
        self.assertTrue(salida.endswith(" cambia los permisos del archivo."))


class TestResaltado(unittest.TestCase):
    def test_marca_en_negrita_el_hueco_pedido(self):
        salida = cloze.resaltado("En {{7}} el dueño, en {{5}} el grupo.", 0)
        self.assertIn("<b>7</b>", salida)
        self.assertNotIn("<b>5</b>", salida)
        self.assertIn("5", salida)

    def test_sin_indice_los_marca_todos(self):
        salida = cloze.resaltado("{{a}} y {{b}}")
        self.assertIn("<b>a</b>", salida)
        self.assertIn("<b>b</b>", salida)

    def test_se_puede_pedir_otra_etiqueta(self):
        self.assertIn("<i>a</i>", cloze.resaltado("{{a}}", etiqueta="i"))


class TestRespuestaYPista(unittest.TestCase):
    def test_devuelve_el_hueco_pedido(self):
        texto = "En {{7}} el dueño, en {{5}} el grupo."
        self.assertEqual(cloze.respuesta(texto, 0), "7")
        self.assertEqual(cloze.respuesta(texto, 1), "5")

    def test_sin_indice_junta_todas(self):
        self.assertEqual(cloze.respuesta("{{a}} y {{b}}"), "a · b")

    def test_un_indice_que_no_existe_devuelve_vacio(self):
        self.assertEqual(cloze.respuesta("{{a}}", 9), "")

    def test_un_texto_sin_huecos_no_tiene_respuesta(self):
        self.assertEqual(cloze.respuesta("nada"), "")

    def test_la_pista_se_recupera_por_indice(self):
        texto = "{{a}} y {{b::la segunda}}"
        self.assertEqual(cloze.pista(texto, 1), "la segunda")
        self.assertEqual(cloze.pista(texto, 0), "")


class TestElegir(unittest.TestCase):
    def test_devuelve_un_indice_valido(self):
        texto = "{{a}} y {{b}} y {{c}}"
        for _ in range(30):
            self.assertIn(cloze.elegir(texto), (0, 1, 2))

    def test_no_repite_el_de_la_vez_anterior(self):
        texto = "{{a}} y {{b}} y {{c}}"
        for _ in range(30):
            self.assertNotEqual(cloze.elegir(texto, evitar=1), 1)

    def test_con_un_solo_hueco_lo_repite_antes_que_no_dar_nada(self):
        self.assertEqual(cloze.elegir("{{unico}}", evitar=0), 0)

    def test_sin_huecos_no_hay_nada_que_elegir(self):
        self.assertIsNone(cloze.elegir("nada que tapar"))


class TestCasosRaros(unittest.TestCase):
    def test_un_hueco_que_ocupa_todo_el_texto(self):
        self.assertEqual(cloze.completo("{{todo}}"), "todo")
        self.assertEqual(cloze.enmascarar("{{todo}}", 0), cloze.HUECO)

    def test_huecos_pegados_sin_texto_entre_medias(self):
        self.assertEqual(cloze.cuantos("{{a}}{{b}}"), 2)
        self.assertEqual(cloze.completo("{{a}}{{b}}"), "ab")

    def test_un_hueco_de_varias_lineas(self):
        texto = "Empieza {{una\\nrespuesta larga}} y sigue."
        self.assertEqual(cloze.cuantos(texto), 1)
        self.assertIn("respuesta larga", cloze.completo(texto))

    def test_el_markup_de_dentro_se_conserva(self):
        texto = "Usa {{<tt>chmod</tt>}} para eso."
        self.assertIn("<tt>chmod</tt>", cloze.completo(texto))


if __name__ == "__main__":
    unittest.main()
