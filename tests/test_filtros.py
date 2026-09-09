"""Los filtros que deciden si un texto descargado merece entrar.

Cada rechazo trae un motivo legible: sin eso, «no me trae nada» sería
imposible de depurar.
"""
from appstudy import cosecha, db, fuentes, selector
from tests.apoyo import BaseTemporal

BUENO = ("La resistencia eléctrica se opone al paso de la corriente por un conductor. "
         "Un conductor presenta una resistencia que depende de su longitud y de su sección. "
         "La ley de Ohm relaciona la tensión, la corriente y la resistencia del circuito. "
         "Al aumentar la tensión sobre una resistencia fija, la corriente crece de forma "
         "proporcional según esta misma ley. " * 22)


class FiltrosTest(BaseTemporal):
    def setUp(self):
        super().setUp()
        db.upsert_deck(self.con, "electricidad", "Electricidad", "⚡", "#3584e4", 1,
                       ["Básico", "Intermedio", "Avanzado"])
        self.con.commit()
        self.plan = selector.plan(self.con)

    def doc(self, texto, provider="wikipedia_es", titulo="Resistencia eléctrica"):
        return fuentes.documento(provider, "https://es.wikipedia.org/wiki/Resistencia",
                                 titulo, text=texto)

    def test_un_texto_bueno_pasa(self):
        r = cosecha.filtrar(self.con, self.doc(BUENO), self.plan)
        self.assertTrue(r["ok"], r["motivo"])
        self.assertGreaterEqual(r["score"], cosecha.UMBRAL)

    def test_un_esbozo_se_rechaza_por_corto(self):
        r = cosecha.filtrar(self.con, self.doc("Dos frases cortas. Nada más que decir."),
                            self.plan)
        self.assertFalse(r["ok"])
        self.assertIn("corto", r["motivo"])

    def test_un_texto_gigantesco_se_rechaza_por_largo(self):
        r = cosecha.filtrar(self.con, self.doc("palabra " * 25000), self.plan)
        self.assertFalse(r["ok"])
        self.assertIn("largo", r["motivo"])

    def test_una_lista_de_enlaces_se_rechaza_por_no_ser_prosa(self):
        r = cosecha.filtrar(self.con, self.doc("\n".join(["Véase también"] * 500)), self.plan)
        self.assertFalse(r["ok"])
        self.assertIn("prosa", r["motivo"])

    def test_una_pagina_de_desambiguacion_se_rechaza(self):
        r = cosecha.filtrar(self.con, self.doc(BUENO, titulo="Ohm (desambiguación)"), self.plan)
        self.assertFalse(r["ok"])
        self.assertIn("desambiguación", r["motivo"])

    def test_el_ingles_se_rechaza_en_un_mazo_en_espanol(self):
        ingles = ("The electrical resistance of a conductor depends on its length and on "
                  "the area of its section, and it is measured in ohms. " * 40)
        r = cosecha.filtrar(self.con, self.doc(ingles), self.plan)
        self.assertFalse(r["ok"])
        self.assertIn("idioma", r["motivo"])

    def test_el_mazo_de_ingles_si_acepta_ingles(self):
        db.upsert_deck(self.con, "ingles", "Inglés", "🗣️", "#3584e4", 0,
                       ["A2", "B1", "B2", "C1"])
        # Electricidad deja de ser el más flojo, así que le toca a inglés
        for i in range(5):
            db.add_card(self.con, self.plan["deck"]["id"], "electricidad", "card",
                        f"Relleno {i}", "R")
        self.con.commit()
        plan = selector.plan(self.con)
        self.assertEqual(plan["deck"]["key"], "ingles")
        ingles = ("The electrical resistance of a conductor depends on its length and on "
                  "the area of its section, and it is measured in ohms. " * 40)
        doc = fuentes.documento("wikipedia_simple", "https://simple.wikipedia.org/wiki/R",
                                "Resistance", text=ingles)
        self.assertTrue(cosecha.filtrar(self.con, doc, plan)["ok"])

    def test_una_fuente_solo_enlace_entra_como_enlace_no_como_texto(self):
        doc = self.doc(BUENO, provider="arxiv")
        doc["summary"] = ("Un resumen suficientemente largo del artículo como para "
                          "que merezca la pena guardarlo junto a su enlace y poder "
                          "decidir si abrirlo más tarde con calma.")
        r = cosecha.filtrar(self.con, doc, self.plan)
        self.assertTrue(r["ok"])
        self.assertTrue(r["enlace"])
        self.assertIn("solo enlace", r["motivo"])

    def test_una_fuente_solo_enlace_sin_resumen_no_entra(self):
        r = cosecha.filtrar(self.con, self.doc(BUENO, provider="arxiv"), self.plan)
        self.assertFalse(r["ok"])
        self.assertIn("resumen", r["motivo"])

    def test_un_texto_ya_importado_se_rechaza_por_duplicado(self):
        doc = self.doc(BUENO)
        self.con.execute("INSERT INTO source_imports VALUES(?,?,?,?,?,?,?)",
                         (doc["provider"], doc["origin"], self.plan["deck"]["id"], None,
                          fuentes.huella(doc), "{}", 1.0))
        self.con.commit()
        r = cosecha.filtrar(self.con, doc, self.plan)
        self.assertFalse(r["ok"])
        self.assertIn("ya", r["motivo"])

    def test_lo_que_ya_espera_en_la_bandeja_no_se_repropone(self):
        doc = self.doc(BUENO)
        self.con.execute(
            "INSERT INTO inbox(provider,origin,deck_id,title,created) VALUES(?,?,?,?,?)",
            (doc["provider"], doc["origin"], self.plan["deck"]["id"], doc["title"], 1.0))
        self.con.commit()
        r = cosecha.filtrar(self.con, doc, self.plan)
        self.assertFalse(r["ok"])
        self.assertIn("bandeja", r["motivo"])

    def test_algo_sin_relacion_con_lo_pedido_se_rechaza(self):
        cid, _ = db.add_card(self.con, self.plan["deck"]["id"], "electricidad", "card",
                             "¿Qué es un transistor?", "Semiconductor", tags="transistores")
        self.con.execute("INSERT OR REPLACE INTO state(card_id,lapses,last) VALUES(?,?,?)",
                         (cid, 5, 1.0))
        self.con.commit()
        plan = selector.plan(self.con)
        ajeno = ("La cocina mediterránea emplea aceite de oliva y verduras de temporada "
                 "en la mayor parte de sus recetas tradicionales. " * 40)
        r = cosecha.filtrar(self.con, self.doc(ajeno, titulo="Cocina"), plan)
        self.assertFalse(r["ok"])

    def test_el_nivel_sale_de_la_dificultad_del_texto(self):
        r = cosecha.filtrar(self.con, self.doc(BUENO), self.plan)
        self.assertIn(r["nivel"], (1, 2, 3))

    def test_un_texto_llano_es_mas_basico_que_uno_recargado(self):
        llano = "El agua hierve a cien grados. El hielo es agua sólida. " * 60
        denso = ("La caracterización electromagnética correspondiente presupone " 
                 "consideraciones termodinámicas fundamentalmente incompatibles con las "
                 "aproximaciones fenomenológicas convencionalmente establecidas. " * 30)
        self.assertLess(cosecha.nivel_de(llano, 3), cosecha.nivel_de(denso, 3))
