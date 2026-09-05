import unittest

from appstudy import db
from tests.apoyo import BaseTemporal


class FuentesTarjetaTest(BaseTemporal):
    def setUp(self):
        super().setUp()
        self.did = self.mazo()
        self.cid = self.tarjeta(self.did, "Pregunta sin palabras comunes", "Respuesta")

    def test_capitulo_explicito_gana_al_parecido(self):
        capid, uid = db.upsert_chapter(self.con, self.did, "linux", {
            "title": "Origen exacto", "body": [{"p": "Un texto completamente distinto"}]})
        db.set_card_source(self.con, self.cid, {
            "kind": "chapter", "chapter_uid": uid, "title": "Origen exacto"})
        self.con.commit()
        fuente = db.source_for_card(self.con, self.cid)
        self.assertEqual(fuente["chapter_id"], capid)
        self.assertEqual(db.chapter_for_card(
            self.con, db.card_by_id(self.con, self.cid))["id"], capid)

    def test_un_libro_explicito_no_se_sustituye_por_un_capitulo_parecido(self):
        db.upsert_chapter(self.con, self.did, "linux", {
            "title": "Pregunta sin palabras comunes", "level": 1,
            "body": [{"p": "Respuesta"}]})
        db.set_card_source(self.con, self.cid, {
            "kind": "book", "ruta": "/libros/uno.pdf", "page_start": 8,
            "page_end": 10, "title": "Manual"})
        self.con.commit()
        self.assertIsNone(db.chapter_for_card(self.con, db.card_by_id(self.con, self.cid)))
        self.assertEqual(db.source_label(db.source_for_card(self.con, self.cid)),
                         "Manual · págs. 8–10")

    def test_etiqueta_de_una_pagina_y_un_capitulo(self):
        self.assertEqual(db.source_label({"kind": "book", "title": "Libro",
                                          "page_start": 4, "page_end": 4}),
                         "Libro · pág. 4")
        self.assertEqual(db.source_label({"kind": "chapter", "title": "Tema"}), "Tema")

    def test_borrar_tarjeta_borra_solo_su_vinculo(self):
        db.set_card_source(self.con, self.cid, {
            "kind": "book", "ruta": "/libros/uno.pdf", "page_start": 1})
        self.con.commit()
        db.delete_card(self.con, self.cid)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM card_sources").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
