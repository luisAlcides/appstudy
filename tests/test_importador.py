import csv
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from appstudy import importador


class ImportadorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_csv_con_cabecera_y_campos_en_espanol(self):
        ruta = self.dir / "tarjetas.csv"
        with ruta.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Pregunta", "Respuesta", "Etiquetas"])
            w.writerow(["¿Qué es FSRS?", "Un planificador", "memoria, ia"])
        tarjetas = importador.leer(ruta)
        self.assertEqual(tarjetas[0]["front"], "¿Qué es FSRS?")
        self.assertEqual(tarjetas[0]["tags"], "memoria, ia")

    def test_exportacion_tabulada_de_anki(self):
        ruta = self.dir / "anki.txt"
        ruta.write_text("#separator:tab\n#html:true\n<b>Pregunta</b>\tRespuesta\ttag1 tag2\n",
                        encoding="utf-8")
        tarjetas = importador.leer(ruta)
        self.assertEqual(tarjetas[0]["front"], "<b>Pregunta</b>")
        self.assertEqual(tarjetas[0]["back"], "Respuesta")

    def test_convierte_cloze_de_anki(self):
        ruta = self.dir / "cloze.tsv"
        ruta.write_text("{{c1::chmod::comando}} cambia permisos\tExplicación\n",
                        encoding="utf-8")
        tarjeta = importador.leer(ruta)[0]
        self.assertEqual(tarjeta["kind"], "cloze")
        self.assertIn("{{chmod::comando}}", tarjeta["front"])

    def test_apkg_lee_coleccion_sin_extraer_el_resto(self):
        db = self.dir / "collection.anki2"
        con = sqlite3.connect(db)
        con.executescript("""
            CREATE TABLE notes(id INTEGER PRIMARY KEY, flds TEXT, tags TEXT);
            CREATE TABLE cards(id INTEGER PRIMARY KEY, nid INTEGER, did INTEGER);
            CREATE TABLE col(decks TEXT);
        """)
        con.execute("INSERT INTO notes VALUES(1, ?, ?)", ("Frente\x1fReverso", " tag "))
        con.execute("INSERT INTO cards VALUES(1, 1, 42)")
        con.execute("INSERT INTO col VALUES(?)", (json.dumps({"42": {"name": "Mazo"}}),))
        con.commit()
        con.close()
        paquete = self.dir / "coleccion.apkg"
        with zipfile.ZipFile(paquete, "w") as z:
            z.write(db, "collection.anki2")
            z.writestr("../../no-extraer", "peligro")
        tarjeta = importador.leer(paquete)[0]
        self.assertEqual(tarjeta["front"], "Frente")
        self.assertEqual(tarjeta["deck"], "Mazo")
        self.assertFalse((self.dir.parent / "no-extraer").exists())

    def test_html_desconocido_se_elimina_pero_conserva_formato_basico(self):
        ruta = self.dir / "html.csv"
        ruta.write_text('front,back\n"<div><strong>Hola</strong><script>x</script></div>",ok\n',
                        encoding="utf-8")
        self.assertEqual(importador.leer(ruta)[0]["front"], "<b>Hola</b>x")

    def test_corta_al_limite_sin_cargar_todas_las_filas(self):
        ruta = self.dir / "grande.csv"
        ruta.write_text("front,back\n" + "\n".join(f"p{i},r{i}" for i in range(20)),
                        encoding="utf-8")
        with mock.patch.object(importador, "MAX_TARJETAS", 3):
            tarjetas = importador.leer(ruta)
        self.assertEqual([t["front"] for t in tarjetas], ["p0", "p1", "p2"])


if __name__ == "__main__":
    unittest.main()
