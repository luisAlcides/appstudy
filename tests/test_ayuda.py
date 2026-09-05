"""La guía de uso que se abre con F1.

Lo que se protege: que ningún tema quede a medias o use un bloque que el lector
no sabe pintar, que los «ver también» no lleven a un tema inexistente, y que
buscar «sincronizacion» encuentre «Sincronizar y respaldar».
"""
import unittest

from appstudy import ayuda


class ContenidoTest(unittest.TestCase):
    def test_cada_tema_esta_completo(self):
        for t in ayuda.TEMAS:
            with self.subTest(tema=t["key"]):
                for campo in ("key", "titulo", "resumen", "icono", "seccion"):
                    self.assertTrue(str(t.get(campo, "")).strip(), campo)
                self.assertIn(t["seccion"], ayuda.SECCIONES)
                self.assertTrue(t["body"])

    def test_las_claves_no_se_repiten(self):
        claves = [t["key"] for t in ayuda.TEMAS]
        self.assertEqual(len(claves), len(set(claves)))

    def test_solo_usa_bloques_que_el_lector_sabe_pintar(self):
        for t in ayuda.TEMAS:
            for bloque in t["body"]:
                for tipo in bloque:
                    with self.subTest(tema=t["key"], bloque=tipo):
                        self.assertIn(tipo, ayuda.BLOQUES)

    def test_los_ver_tambien_llevan_a_un_tema_de_verdad(self):
        for t in ayuda.TEMAS:
            for otro in t.get("ver", ()):
                with self.subTest(tema=t["key"], ver=otro):
                    self.assertIsNotNone(ayuda.tema(otro))
                    self.assertNotEqual(otro, t["key"])

    def test_por_seccion_no_pierde_ni_duplica_ninguno(self):
        agrupados = [t for _, grupo in ayuda.por_seccion() for t in grupo]
        self.assertEqual(len(agrupados), len(ayuda.TEMAS))
        self.assertEqual({t["key"] for t in agrupados},
                         {t["key"] for t in ayuda.TEMAS})

    def test_las_secciones_salen_en_el_orden_declarado(self):
        nombres = [s for s, _ in ayuda.por_seccion()]
        self.assertEqual(nombres, [s for s in ayuda.SECCIONES if s in nombres])

    def test_un_tema_desconocido_no_revienta(self):
        self.assertIsNone(ayuda.tema("no-existe"))

    def test_el_texto_plano_recoge_listas_pasos_y_recuadros(self):
        texto = ayuda.texto_plano(ayuda.tema("primeros-pasos"))
        self.assertIn("Practicar este capítulo", texto)   # va dentro de unos pasos
        self.assertIn("Biblioteca", texto)                # y esto dentro de una lista
        self.assertNotIn("<b>", texto)


class BuscarTest(unittest.TestCase):
    def test_no_distingue_acentos_ni_mayusculas(self):
        self.assertEqual(ayuda.buscar("SINCRONIZACIÓN")[0]["key"], "sincronizar")

    def test_encuentra_por_como_lo_diria_uno(self):
        self.assertEqual(ayuda.buscar("otro equipo")[0]["key"], "sincronizar")
        self.assertEqual(ayuda.buscar("teclas")[0]["key"], "atajos")

    def test_cada_tema_se_encuentra_por_su_titulo(self):
        for t in ayuda.TEMAS:
            with self.subTest(tema=t["key"]):
                self.assertIn(t["key"], [x["key"] for x in ayuda.buscar(t["titulo"])])

    def test_exige_todas_las_palabras(self):
        self.assertEqual(ayuda.buscar("sincronizar unicornios"), [])

    def test_sin_consulta_util_no_devuelve_nada(self):
        self.assertEqual(ayuda.buscar(""), [])
        self.assertEqual(ayuda.buscar("   "), [])
        self.assertEqual(ayuda.buscar("a"), [])

    def test_respeta_el_limite_pedido(self):
        self.assertLessEqual(len(ayuda.buscar("tarjeta", limite=2)), 2)


if __name__ == "__main__":
    unittest.main()
