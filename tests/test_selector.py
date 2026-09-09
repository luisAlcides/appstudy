"""El selector decide qué pedir hoy mirando solo la base. Aquí no hay red."""
from appstudy import db, extensiones, selector
from tests.apoyo import BaseTemporal


class SelectorTest(BaseTemporal):
    def mazo_de(self, key, name, niveles=("Básico", "Intermedio", "Avanzado")):
        did = db.upsert_deck(self.con, key, name, "📘", "#3584e4", 1, list(niveles))
        self.con.commit()
        return did

    def test_sin_mazos_no_hay_plan(self):
        self.assertIsNone(selector.plan(self.con))

    def test_elige_el_mazo_con_menos_material(self):
        pobre = self.mazo_de("electricidad", "Electricidad")
        rico = self.mazo_de("linux", "Linux")
        for i in range(40):
            db.add_card(self.con, rico, "linux", "card", f"Pregunta {i}", "Respuesta")
        db.add_card(self.con, pobre, "electricidad", "card", "¿Qué es un ohmio?", "Resistencia")
        self.con.commit()
        self.assertEqual(selector.plan(self.con)["deck"]["key"], "electricidad")

    def test_los_terminos_salen_de_las_etiquetas_de_lo_que_fallas(self):
        did = self.mazo_de("electricidad", "Electricidad")
        cid, _ = db.add_card(self.con, did, "electricidad", "card",
                             "¿Qué es un transistor?", "Un semiconductor",
                             tags="transistores")
        self.con.execute("INSERT OR REPLACE INTO state(card_id,lapses,last) VALUES(?,?,?)",
                         (cid, 6, 1.0))
        self.con.commit()
        self.assertIn("transistores", selector.plan(self.con)["terminos"])

    def test_sin_fallos_se_pide_por_el_nombre_del_mazo(self):
        self.mazo_de("linux", "Linux")
        self.assertEqual(selector.plan(self.con)["terminos"], ["Linux"])

    def test_el_nivel_elegido_es_el_primero_que_va_corto(self):
        did = self.mazo_de("linux", "Linux")
        for i in range(selector.MINIMO_POR_NIVEL):
            db.add_card(self.con, did, "linux", "card", f"Basico {i}", "R", level=1)
        self.con.commit()
        p = selector.plan(self.con)
        self.assertEqual((p["nivel"], p["nivel_num"]), ("Intermedio", 2))

    def test_el_mazo_de_ingles_usa_sus_propios_niveles(self):
        self.mazo_de("ingles", "Inglés", ("A2", "B1", "B2", "C1"))
        self.assertEqual(selector.plan(self.con)["nivel"], "A2")

    def test_no_propone_una_fuente_apagada_en_ajustes(self):
        self.mazo_de("linux", "Linux")
        for f in selector.plan(self.con)["fuentes"]:
            extensiones.configurar(self.con, f["id"], enabled=False)
        self.assertIsNone(selector.plan(self.con))

    def test_las_fuentes_del_catalogo_vienen_activadas_de_fabrica(self):
        self.mazo_de("linux", "Linux")
        self.assertTrue(selector.plan(self.con)["fuentes"])

    def test_el_plan_trae_siempre_un_motivo_legible(self):
        self.mazo_de("linux", "Linux")
        self.assertTrue(selector.plan(self.con)["motivo"].strip())

    def test_un_mazo_sin_fuentes_declaradas_no_da_plan(self):
        self.mazo_de("cocina", "Cocina")
        self.assertIsNone(selector.plan(self.con))


class RotacionTest(BaseTemporal):
    def mazo_de(self, key, name):
        did = db.upsert_deck(self.con, key, name, "📘", "#3584e4", 1,
                             ["Básico", "Intermedio", "Avanzado"])
        self.con.commit()
        return did

    def alimentado(self, deck_id, hace_dias):
        import time
        self.con.execute("INSERT INTO source_imports VALUES(?,?,?,?,?,?,?)",
                         ("wikipedia_es", f"https://es.wikipedia.org/wiki/x{deck_id}",
                          deck_id, None, "h", "{}", time.time() - hace_dias * 86400))
        self.con.commit()

    def test_no_alimenta_el_mismo_mazo_dos_dias_seguidos(self):
        recien = self.mazo_de("electricidad", "Electricidad")
        self.mazo_de("linux", "Linux")
        self.alimentado(recien, hace_dias=0)
        self.assertEqual(selector.plan(self.con)["deck"]["key"], "linux")

    def test_si_es_el_unico_mazo_se_repite_sin_remedio(self):
        solo = self.mazo_de("linux", "Linux")
        self.alimentado(solo, hace_dias=0)
        self.assertEqual(selector.plan(self.con)["deck"]["key"], "linux")

    def test_pasada_la_espera_vuelve_a_tocarle(self):
        recien = self.mazo_de("electricidad", "Electricidad")
        otro = self.mazo_de("linux", "Linux")
        for i in range(10):
            db.add_card(self.con, otro, "linux", "card", f"P{i}", "R")
        self.alimentado(recien, hace_dias=selector.DESCANSO_DIAS + 1)
        self.assertEqual(selector.plan(self.con)["deck"]["key"], "electricidad")


class TemaTest(BaseTemporal):
    def test_el_termino_de_busqueda_es_el_tema_no_el_nombre_largo_del_mazo(self):
        db.upsert_deck(self.con, "python", "Python y Análisis de Datos (freeCodeCamp)",
                       "🐍", "#3584e4", 1, ["Básico", "Intermedio", "Avanzado"])
        self.con.commit()
        self.assertEqual(selector.plan(self.con)["terminos"], ["Python"])

    def test_un_mazo_sin_tema_declarado_usa_su_nombre(self):
        db.upsert_deck(self.con, "linux", "Linux", "🐧", "#3584e4", 1, ["Básico"])
        self.con.commit()
        self.assertEqual(selector.plan(self.con)["terminos"], ["Linux"])


class IntentoTest(BaseTemporal):
    def test_un_mazo_que_no_dio_nada_tambien_descansa(self):
        import time
        flojo = db.upsert_deck(self.con, "python", "Python", "🐍", "#3584e4", 1, ["Básico"])
        otro = db.upsert_deck(self.con, "linux", "Linux", "🐧", "#3584e4", 2, ["Básico"])
        for i in range(5):
            db.add_card(self.con, otro, "linux", "card", f"P{i}", "R")
        self.con.commit()
        self.assertEqual(selector.plan(self.con)["deck"]["key"], "python")
        # No se trajo nada, pero se intentó: mañana le toca a otro
        selector.anotar_intento(self.con, flojo, time.time())
        self.assertEqual(selector.plan(self.con)["deck"]["key"], "linux")
