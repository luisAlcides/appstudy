"""La bandeja: lo que llega solo y espera el visto bueno."""
from appstudy import db
from tests.apoyo import BaseTemporal


class InboxEsquemaTest(BaseTemporal):
    def test_la_tabla_inbox_existe_con_sus_columnas(self):
        columnas = {r["name"] for r in self.con.execute("PRAGMA table_info(inbox)")}
        self.assertEqual(columnas, {
            "id", "provider", "origin", "deck_id", "title", "summary", "text",
            "author", "license", "score", "nivel", "motivo", "cards", "estado",
            "created"})

    def test_no_se_repite_el_mismo_origen_en_el_mismo_mazo(self):
        did = self.mazo()
        for _ in range(2):
            self.con.execute(
                "INSERT OR IGNORE INTO inbox(provider,origin,deck_id,title,created)"
                " VALUES('wikipedia','https://es.wikipedia.org/wiki/Ohm',?,'Ohm',1.0)", (did,))
        self.assertEqual(self.con.execute("SELECT COUNT(*) c FROM inbox").fetchone()["c"], 1)


class BandejaTest(BaseTemporal):
    def setUp(self):
        super().setUp()
        from appstudy import fuentes, selector
        db.upsert_deck(self.con, "electricidad", "Electricidad", "⚡", "#3584e4", 1,
                       ["Básico", "Intermedio", "Avanzado"])
        self.con.commit()
        self.plan = selector.plan(self.con)
        self.doc = fuentes.documento(
            "wikipedia_es", "https://es.wikipedia.org/wiki/Ley_de_Ohm", "Ley de Ohm",
            text="La ley de Ohm relaciona tensión, corriente y resistencia. " * 90,
            author="Colaboradores de Wikipedia", license="CC BY-SA 4.0")
        self.veredicto = {"ok": True, "score": 0.9, "nivel": 1,
                          "motivo": "porque fallas ohm"}

    def guardar(self, cards=None):
        from appstudy import bandeja
        return bandeja.guardar(self.con, {**self.doc, "cards": cards or []},
                               self.plan, self.veredicto)

    def test_lo_guardado_aparece_como_pendiente(self):
        from appstudy import bandeja
        self.guardar()
        self.assertEqual(bandeja.cuantas(self.con), 1)
        fila = bandeja.pendientes(self.con)[0]
        self.assertEqual(fila["title"], "Ley de Ohm")
        self.assertEqual(fila["motivo"], "porque fallas ohm")
        self.assertEqual(fila["deck_name"], "Electricidad")

    def test_aceptar_crea_el_capitulo_con_su_atribucion(self):
        from appstudy import bandeja
        capitulo = bandeja.aceptar(self.con, self.guardar())
        self.assertIn("Ley de Ohm", capitulo["title"])
        cuerpo = capitulo["body"] if isinstance(capitulo["body"], str) else ""
        self.assertIn("CC BY-SA 4.0", cuerpo)

    def test_aceptar_crea_solo_las_tarjetas_elegidas(self):
        from appstudy import bandeja
        fila = self.guardar([{"front": "¿Qué dice la ley de Ohm?", "back": "V = I · R"},
                             {"front": "¿En qué se mide la resistencia?", "back": "En ohmios"}])
        bandeja.aceptar(self.con, fila, cards=[0])
        frentes = [r["front"] for r in self.con.execute("SELECT front FROM cards")]
        self.assertEqual(frentes, ["¿Qué dice la ley de Ohm?"])
        self.assertEqual(bandeja.cuantas(self.con), 0)

    def test_la_tarjeta_creada_sabe_de_que_capitulo_salio(self):
        from appstudy import bandeja
        fila = self.guardar([{"front": "¿Qué dice la ley de Ohm?", "back": "V = I · R"}])
        capitulo = bandeja.aceptar(self.con, fila)
        card_id = self.con.execute("SELECT id FROM cards").fetchone()["id"]
        self.assertEqual(db.source_for_card(self.con, card_id)["chapter_id"], capitulo["id"])

    def test_el_capitulo_entra_en_el_nivel_que_dijo_el_filtro(self):
        from appstudy import bandeja
        capitulo = bandeja.aceptar(self.con, self.guardar())
        self.assertEqual(capitulo["level"], 1)

    def test_descartar_lo_saca_de_la_cola_y_no_se_vuelve_a_proponer(self):
        from appstudy import bandeja
        fila = self.guardar()
        bandeja.descartar(self.con, fila)
        self.assertEqual(bandeja.cuantas(self.con), 0)
        estado = self.con.execute("SELECT estado FROM inbox WHERE id=?", (fila,)).fetchone()
        self.assertEqual(estado["estado"], "descartado")

    def test_guardar_dos_veces_el_mismo_origen_no_duplica(self):
        self.guardar()
        self.guardar()
        self.assertEqual(self.con.execute("SELECT COUNT(*) c FROM inbox").fetchone()["c"], 1)

    def test_aceptar_algo_que_ya_no_esta_da_un_error_claro(self):
        from appstudy import bandeja, fuentes
        with self.assertRaises(fuentes.FuenteError):
            bandeja.aceptar(self.con, 9999)
