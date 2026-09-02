"""Los retos de la mascota: convertir una tarjeta en una pregunta jugable.

Lo que se protege aquí es sobre todo la calidad de las opciones falsas (que no
sean calcadas a la buena ni de otro tamaño, porque entonces el reto se adivina
a ojo) y que la corrección de lo escrito perdone acentos y erratas sin dar por
buena una respuesta que no lo es.
"""
import unittest

from appstudy import reto
from tests.apoyo import BaseTemporal


class TestNormalizar(unittest.TestCase):
    def test_quita_acentos_mayusculas_y_puntuacion(self):
        self.assertEqual(reto.normalizar("¡Configuración, RÁPIDA!"), "configuracion rapida")

    def test_quita_las_etiquetas_del_markup(self):
        self.assertEqual(reto.normalizar("<b>chmod</b> 755"), "chmod 755")

    def test_texto_vacio_o_nulo(self):
        self.assertEqual(reto.normalizar(""), "")
        self.assertEqual(reto.normalizar(None), "")


class TestAciertaEscrito(unittest.TestCase):
    def test_la_respuesta_exacta_acierta(self):
        self.assertTrue(reto.acierta_escrito("chmod", "chmod"))

    def test_se_perdona_el_acento_y_la_mayuscula(self):
        self.assertTrue(reto.acierta_escrito("PERMISOS DE EJECUCION",
                                             "permisos de ejecución"))

    def test_se_perdona_una_errata(self):
        self.assertTrue(reto.acierta_escrito("permisos de ejecucon",
                                             "permisos de ejecución"))

    def test_una_respuesta_distinta_no_cuela(self):
        self.assertFalse(reto.acierta_escrito("borrar un archivo",
                                              "cambiar los permisos"))

    def test_una_palabra_suelta_de_una_respuesta_larga_no_basta(self):
        self.assertFalse(reto.acierta_escrito(
            "permisos", "cambia los permisos de lectura, escritura y ejecución"))

    def test_casi_toda_la_respuesta_contenida_si_basta(self):
        self.assertTrue(reto.acierta_escrito("cambia los permisos de un archivo",
                                             "cambia los permisos de un archivo o carpeta"))

    def test_lo_vacio_nunca_acierta(self):
        self.assertFalse(reto.acierta_escrito("", "chmod"))
        self.assertFalse(reto.acierta_escrito("chmod", ""))


class TestEsencia(unittest.TestCase):
    def test_una_respuesta_corta_se_deja_como_esta(self):
        self.assertEqual(reto.esencia("Cambia los permisos de un archivo."),
                         "Cambia los permisos de un archivo.")

    def test_una_respuesta_larga_se_corta_por_donde_no_duele(self):
        largo = ("La primera idea es bastante larga y explica el concepto con calma; "
                 "la segunda ya es otra cosa distinta que aquí no hace falta para nada.")
        salida = reto.esencia(largo)
        self.assertLessEqual(len(salida), reto.MAX_OPCION + 1)
        self.assertTrue(salida.endswith(("…", ";", ".", ",", ":")) or " " in salida)

    def test_una_respuesta_en_pasos_se_queda_en_el_primero(self):
        salida = reto.esencia("1. Monta el disco con mount. 2. Añádelo a fstab.")
        self.assertNotIn("fstab", salida)

    def test_junta_las_primeras_lineas_de_una_lista(self):
        salida = reto.esencia("cat\nmuestra todo de golpe\nless\npagina el resultado")
        self.assertTrue(salida.startswith("cat"))
        self.assertIn("muestra", salida)


class TestHueco(unittest.TestCase):
    def test_saca_una_frase_con_hueco_y_la_palabra_que_falta(self):
        resultado = reto.hueco("El comando chmod cambia los permisos del archivo indicado.")
        self.assertIsNotNone(resultado)
        frase, palabra = resultado
        self.assertIn("_____", frase)
        self.assertNotIn(palabra, frase)

    def test_no_deja_hueco_en_palabras_de_relleno(self):
        for _ in range(25):
            resultado = reto.hueco("Esto siempre puede hacerse cuando tienes permisos.")
            if resultado:
                self.assertNotIn(reto.normalizar(resultado[1]), reto.COMUNES)

    def test_sin_palabras_aprovechables_no_inventa_nada(self):
        self.assertIsNone(reto.hueco("es de la ley"))


class TestPreparar(BaseTemporal):
    """`preparar()` arma el reto concreto; necesita otras tarjetas del mazo."""

    # Respuestas de verdad distintas entre sí: si se parecen demasiado el propio
    # filtro de calidad las descarta y nunca llega a haber opciones que ofrecer.
    MATERIAL = [
        ("¿Qué hace chmod?", "Cambia los permisos de lectura, escritura y ejecución."),
        ("¿Qué hace grep?", "Busca un patrón dentro de los archivos indicados."),
        ("¿Qué hace ps?", "Enseña la lista de procesos que corren ahora mismo."),
        ("¿Qué hace df?", "Informa del espacio libre en cada sistema de ficheros."),
        ("¿Qué hace ssh?", "Abre una sesión cifrada contra una máquina remota."),
        ("¿Qué hace tar?", "Empaqueta varios archivos en uno solo, comprimido o no."),
        ("¿Qué hace kill?", "Manda una señal a un proceso para pararlo o recargarlo."),
        ("¿Qué hace mount?", "Engancha un dispositivo en un punto del árbol de directorios."),
        ("¿Qué hace cron?", "Lanza tareas repetidas a la hora que le digas."),
        ("¿Qué hace du?", "Suma cuánto ocupa cada carpeta que le pases."),
    ]

    def poblar(self, cuantas=10):
        deck = self.mazo()
        ids = [self.tarjeta(deck, front, back)
               for front, back in self.MATERIAL[:cuantas]]
        return deck, ids

    def carta(self, card_id):
        return self.con.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()

    def test_el_reto_trae_todo_lo_que_el_globo_necesita(self):
        _, ids = self.poblar()
        r = reto.preparar(self.con, self.carta(ids[0]))
        for clave in ("formato", "segundos", "icono", "titulo", "pregunta", "respuesta"):
            self.assertIn(clave, r)
        self.assertIn(r["formato"], reto.SEGUNDOS)
        self.assertEqual(r["segundos"], reto.SEGUNDOS[r["formato"]])

    def test_evitar_no_repite_el_formato_anterior(self):
        _, ids = self.poblar()
        carta = self.carta(ids[0])
        for _ in range(30):
            anterior = reto.preparar(self.con, carta)["formato"]
            self.assertNotEqual(reto.preparar(self.con, carta, evitar=anterior)["formato"],
                                anterior)

    def test_las_opciones_incluyen_la_correcta_y_no_se_repiten(self):
        _, ids = self.poblar()
        carta = self.carta(ids[0])
        vistas = 0
        for _ in range(40):
            r = reto.preparar(self.con, carta)
            if r["formato"] != "opciones":
                continue
            vistas += 1
            opciones = r["opciones"]
            self.assertGreaterEqual(len(opciones), 3)
            self.assertEqual(len(set(opciones)), len(opciones))
            self.assertTrue(0 <= r["correcta"] < len(opciones))
        self.assertGreater(vistas, 0, "nunca salió el formato de opciones")

    def test_una_tarjeta_quiz_usa_sus_propias_opciones(self):
        deck = self.mazo()
        cid = self.tarjeta(deck, "¿Cuál corta la primera columna?",
                           "cut -d' ' -f1 recorta por delimitador.", kind="quiz",
                           choices=["cut -f1", "head -1", "tail -1", "wc -l"], answer=0)
        for _ in range(3):
            self.tarjeta(deck, f"otra {_}", "otra respuesta cualquiera del mazo")
        carta = self.carta(cid)
        for _ in range(40):
            r = reto.preparar(self.con, carta)
            if r["formato"] == "opciones":
                self.assertEqual(r["opciones"], ["cut -f1", "head -1", "tail -1", "wc -l"])
                self.assertEqual(r["correcta"], 0)
                break
        else:
            self.fail("nunca salió el formato de opciones")

    def test_verdadero_o_falso_dice_la_verdad_sobre_si_misma(self):
        _, ids = self.poblar()
        carta = self.carta(ids[0])
        correcta = reto.esencia(carta["back"])
        salieron = 0
        for _ in range(60):
            r = reto.preparar(self.con, carta)
            if r["formato"] != "vf":
                continue
            salieron += 1
            self.assertEqual(r["verdadera"], r["afirmacion"] == correcta)
        self.assertGreater(salieron, 0, "nunca salió verdadero o falso")

    def test_una_respuesta_larga_no_se_pide_por_escrito(self):
        deck = self.mazo()
        cid = self.tarjeta(deck, "¿Cómo se monta un disco?",
                           "Se identifica con lsblk, se crea el punto de montaje, se monta "
                           "con mount y se añade a fstab para que persista al reiniciar.")
        for i in range(6):
            self.tarjeta(deck, f"otra pregunta {i}", f"otra respuesta larga número {i} aquí")
        carta = self.carta(cid)
        for _ in range(60):
            self.assertNotEqual(reto.preparar(self.con, carta)["formato"], "escribir")

    def test_una_leccion_sin_respuesta_siempre_es_contrarreloj(self):
        deck = self.mazo()
        cid = self.tarjeta(deck, "Los permisos se leen en octal.", "", kind="lesson")
        r = reto.preparar(self.con, self.carta(cid))
        self.assertEqual(r["formato"], "relampago")

    def test_un_mazo_sin_material_no_impide_preguntar(self):
        # Con una sola tarjeta no hay distractores posibles, pero el globo no
        # puede quedarse vacío: siempre queda contrarreloj.
        deck = self.mazo()
        cid = self.tarjeta(deck, "¿Qué hace ls?", "Lista el contenido del directorio.")
        r = reto.preparar(self.con, self.carta(cid))
        self.assertIn(r["formato"], ("relampago", "hueco", "escribir"))


class TestDistractores(BaseTemporal):
    def test_no_se_cuela_una_opcion_calcada_a_la_correcta(self):
        deck = self.mazo()
        buena = "Cambia los permisos de un archivo del sistema de ficheros."
        cid = self.tarjeta(deck, "¿Qué hace chmod?", buena)
        self.tarjeta(deck, "¿Y qué hace chmod entonces?", buena + " Sin más.")
        for i in range(6):
            self.tarjeta(deck, f"pregunta {i}", f"respuesta bien distinta número {i} del mazo")
        carta = self.con.execute("SELECT * FROM cards WHERE id=?", (cid,)).fetchone()
        for opcion in reto.distractores(self.con, carta, 3):
            self.assertLessEqual(reto.parecido(opcion, reto.esencia(buena)), 0.80)

    def test_no_se_cuelan_opciones_de_otro_tamano(self):
        deck = self.mazo()
        cid = self.tarjeta(deck, "¿Qué hace pwd?", "Enseña el directorio actual.")
        self.tarjeta(deck, "larguísima", "Una respuesta muchísimo más larga que la buena, "
                                         "con varias frases seguidas para que no encaje "
                                         "por tamaño en ningún caso posible aquí.")
        self.tarjeta(deck, "cortísima", "No.")
        for i in range(6):
            self.tarjeta(deck, f"normal {i}", f"Respuesta de tamaño parecido número {i}.")
        carta = self.con.execute("SELECT * FROM cards WHERE id=?", (cid,)).fetchone()
        correcta = reto.esencia("Enseña el directorio actual.")
        for opcion in reto.distractores(self.con, carta, 3):
            self.assertGreaterEqual(len(opcion) / len(correcta), 0.35)
            self.assertLessEqual(len(opcion) / len(correcta), 2.8)

    def test_los_distractores_salen_del_mismo_mazo(self):
        linux = self.mazo("linux", "Linux")
        ingles = self.mazo("ingles", "Inglés")
        cid = self.tarjeta(linux, "¿Qué hace ls?", "Lista el contenido del directorio.")
        for i in range(6):
            self.tarjeta(linux, f"linux {i}", f"Una respuesta de linux número {i} aquí.",
                         key="linux")
            self.tarjeta(ingles, f"english {i}", f"An answer in english number {i} here.",
                         key="ingles")
        carta = self.con.execute("SELECT * FROM cards WHERE id=?", (cid,)).fetchone()
        for opcion in reto.distractores(self.con, carta, 3):
            self.assertNotIn("english", opcion.lower())


if __name__ == "__main__":
    unittest.main()
