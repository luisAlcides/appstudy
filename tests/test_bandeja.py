"""La bandeja: lo que llega solo y espera el visto bueno."""
from appstudy import db
from tests.apoyo import BaseTemporal


class InboxEsquemaTest(BaseTemporal):
    def test_la_tabla_inbox_existe_con_sus_columnas(self):
        columnas = {r["name"] for r in self.con.execute("PRAGMA table_info(inbox)")}
        self.assertEqual(columnas, {
            "id", "provider", "origin", "deck_id", "title", "summary", "text",
            "author", "license", "score", "motivo", "cards", "estado", "created"})

    def test_no_se_repite_el_mismo_origen_en_el_mismo_mazo(self):
        did = self.mazo()
        for _ in range(2):
            self.con.execute(
                "INSERT OR IGNORE INTO inbox(provider,origin,deck_id,title,created)"
                " VALUES('wikipedia','https://es.wikipedia.org/wiki/Ohm',?,'Ohm',1.0)", (did,))
        self.assertEqual(self.con.execute("SELECT COUNT(*) c FROM inbox").fetchone()["c"], 1)
