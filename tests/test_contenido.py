"""El contenido incluido: que los JSON de fábrica sean importables y coherentes.

Los mazos y las lecturas se editan a mano, así que aquí se comprueba lo que una
errata rompería sin avisar: un nivel fuera de rango, un reto sin respuesta
correcta, dos tarjetas con el mismo enunciado (que comparten identidad en la
base y se pisarían), o una lectura que cuelga de un mazo que no existe.
"""
import json
import unittest
from pathlib import Path

from appstudy import db, seed
from tests.apoyo import BaseTemporal

RAIZ = Path(__file__).resolve().parent.parent
CONTENIDO = RAIZ / "appstudy" / "content"
LECTURAS = CONTENIDO / "readings"

MAZOS = sorted(CONTENIDO.glob("*.json"))
CAPITULOS = sorted(LECTURAS.glob("*.json"))


def leer(p):
    return json.loads(p.read_text(encoding="utf-8"))


class TestMazos(unittest.TestCase):
    def test_hay_mazos_que_revisar(self):
        self.assertGreater(len(MAZOS), 0)

    def test_cada_mazo_trae_lo_imprescindible(self):
        for archivo in MAZOS:
            with self.subTest(mazo=archivo.name):
                d = leer(archivo)
                for clave in ("key", "name", "levels", "cards"):
                    self.assertIn(clave, d)
                self.assertTrue(d["levels"])
                self.assertTrue(d["cards"])

    def test_las_claves_de_mazo_no_se_repiten(self):
        claves = [leer(a)["key"] for a in MAZOS]
        self.assertEqual(len(claves), len(set(claves)))

    def test_ninguna_tarjeta_se_sale_de_los_niveles_del_mazo(self):
        for archivo in MAZOS:
            d = leer(archivo)
            for c in d["cards"]:
                nivel = c.get("level", 1)
                with self.subTest(mazo=archivo.name, tarjeta=c["front"][:40]):
                    self.assertGreaterEqual(nivel, 1)
                    self.assertLessEqual(nivel, len(d["levels"]))

    def test_no_hay_dos_tarjetas_con_el_mismo_enunciado(self):
        # El enunciado es la identidad de la tarjeta en la base: dos iguales en
        # el mismo mazo se pisarían y una de las dos se perdería al importar.
        for archivo in MAZOS:
            d = leer(archivo)
            enunciados = [c["front"].strip() for c in d["cards"]]
            repetidos = {f for f in enunciados if enunciados.count(f) > 1}
            with self.subTest(mazo=archivo.name):
                self.assertEqual(repetidos, set(), f"enunciados repetidos: {repetidos}")

    def test_toda_tarjeta_tiene_enunciado(self):
        for archivo in MAZOS:
            for c in leer(archivo)["cards"]:
                with self.subTest(mazo=archivo.name):
                    self.assertTrue(c.get("front", "").strip())

    def test_una_tarjeta_de_huecos_tiene_al_menos_un_hueco(self):
        from appstudy import cloze
        for archivo in MAZOS:
            for c in leer(archivo)["cards"]:
                if c.get("kind") != "cloze":
                    continue
                with self.subTest(mazo=archivo.name, tarjeta=c["front"][:40]):
                    self.assertTrue(cloze.tiene_huecos(c["front"]))

    def test_una_tarjeta_invertida_tiene_respuesta_que_invertir(self):
        for archivo in MAZOS:
            for c in leer(archivo)["cards"]:
                if not c.get("reverse"):
                    continue
                with self.subTest(mazo=archivo.name, tarjeta=c["front"][:40]):
                    self.assertTrue(c.get("back", "").strip())
                    self.assertEqual(c.get("kind", "card"), "card")

    def test_una_tarjeta_normal_tiene_respuesta(self):
        # Las lecciones enseñan sin preguntar y las de huecos llevan la
        # respuesta dentro del propio enunciado: ninguna necesita «back».
        for archivo in MAZOS:
            for c in leer(archivo)["cards"]:
                if c.get("kind", "card") in ("lesson", "cloze"):
                    continue
                with self.subTest(mazo=archivo.name, tarjeta=c["front"][:40]):
                    self.assertTrue(c.get("back", "").strip())

    def test_los_retos_apuntan_a_una_opcion_que_existe(self):
        for archivo in MAZOS:
            for c in leer(archivo)["cards"]:
                if c.get("kind") != "quiz":
                    continue
                opciones, correcta = c.get("choices") or [], c.get("answer", -1)
                with self.subTest(mazo=archivo.name, tarjeta=c["front"][:40]):
                    self.assertGreaterEqual(len(opciones), 2)
                    self.assertTrue(0 <= correcta < len(opciones))

    def test_el_tipo_de_tarjeta_es_uno_de_los_tres(self):
        for archivo in MAZOS:
            for c in leer(archivo)["cards"]:
                with self.subTest(mazo=archivo.name):
                    self.assertIn(c.get("kind", "card"),
                                  ("card", "quiz", "lesson", "cloze"))


class TestLecturas(unittest.TestCase):
    def test_cada_lectura_cuelga_de_un_mazo_que_existe(self):
        claves = {leer(a)["key"] for a in MAZOS}
        for archivo in CAPITULOS:
            with self.subTest(lectura=archivo.name):
                self.assertIn(leer(archivo)["deck"], claves)

    def test_cada_capitulo_trae_titulo_nivel_minutos_y_cuerpo(self):
        for archivo in CAPITULOS:
            for ch in leer(archivo)["chapters"]:
                with self.subTest(lectura=archivo.name, cap=ch.get("title", "?")[:40]):
                    self.assertTrue(ch.get("title", "").strip())
                    self.assertGreaterEqual(ch.get("level", 1), 1)
                    self.assertGreater(ch.get("minutes", 0), 0)
                    self.assertTrue(ch.get("body"))

    def test_los_titulos_de_capitulo_no_se_repiten_dentro_de_un_mazo(self):
        # El título es la identidad del capítulo, igual que el enunciado en una tarjeta.
        for archivo in CAPITULOS:
            titulos = [c["title"].strip() for c in leer(archivo)["chapters"]]
            with self.subTest(lectura=archivo.name):
                self.assertEqual(len(titulos), len(set(titulos)))

    def test_el_nivel_de_un_capitulo_cabe_en_los_del_mazo(self):
        niveles = {leer(a)["key"]: len(leer(a)["levels"]) for a in MAZOS}
        for archivo in CAPITULOS:
            d = leer(archivo)
            for ch in d["chapters"]:
                with self.subTest(lectura=archivo.name, cap=ch["title"][:40]):
                    self.assertLessEqual(ch.get("level", 1), niveles[d["deck"]])

    def test_los_bloques_son_de_un_tipo_conocido(self):
        conocidos = {"h", "p", "list", "steps", "code", "math", "note", "warn",
                     "key", "quote"}
        for archivo in CAPITULOS:
            for ch in leer(archivo)["chapters"]:
                for bloque in ch["body"]:
                    with self.subTest(lectura=archivo.name, cap=ch["title"][:30]):
                        self.assertTrue(set(bloque) <= conocidos,
                                        f"bloque desconocido: {set(bloque) - conocidos}")


class TestImportacion(BaseTemporal):
    """Que todo el contenido de fábrica entre de verdad en una base vacía."""

    def test_se_importa_entero_y_sin_perder_nada(self):
        mazos, nuevas, retiradas, capitulos = seed.load_all(self.con)
        # Una entrada con `reverse` produce dos tarjetas, así que se cuentan
        # las variantes y no las entradas del JSON.
        esperadas = sum(len(seed.variantes(c)) for a in MAZOS for c in leer(a)["cards"])
        esperados = sum(len(leer(a)["chapters"]) for a in CAPITULOS)

        self.assertEqual(mazos, len(MAZOS))
        self.assertEqual(nuevas, esperadas)
        self.assertEqual(retiradas, 0)
        self.assertEqual(capitulos, esperados)
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM cards").fetchone()[0], esperadas)
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM chapters").fetchone()[0], esperados)

    def test_reimportar_no_duplica_ni_pierde_el_progreso(self):
        seed.load_all(self.con)
        antes = self.con.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        cid = self.con.execute("SELECT id FROM cards LIMIT 1").fetchone()["id"]
        self.con.execute("UPDATE state SET reps=7, interval=30 WHERE card_id=?", (cid,))
        self.con.commit()

        _, nuevas, retiradas, _ = seed.load_all(self.con)

        self.assertEqual(nuevas, 0)
        self.assertEqual(retiradas, 0)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM cards").fetchone()[0], antes)
        fila = self.con.execute("SELECT reps FROM state WHERE card_id=?", (cid,)).fetchone()
        self.assertEqual(fila["reps"], 7)

    def test_la_cara_inversa_se_importa_como_tarjeta_aparte(self):
        seed.load_all(self.con)
        for archivo in MAZOS:
            d = leer(archivo)
            for c in d["cards"]:
                if not c.get("reverse"):
                    continue
                with self.subTest(mazo=archivo.name, tarjeta=c["front"][:40]):
                    directa = self.con.execute(
                        "SELECT id, back FROM cards WHERE uid=?",
                        (db.uid_for(d["key"], c["front"]),)).fetchone()
                    inversa = self.con.execute(
                        "SELECT id, front, back, tags FROM cards WHERE uid=?",
                        (db.uid_for(d["key"], "inversa\x00" + c["front"]),)).fetchone()
                    self.assertIsNotNone(directa)
                    self.assertIsNotNone(inversa)
                    self.assertNotEqual(directa["id"], inversa["id"])
                    # La inversa pregunta lo que la directa respondía
                    self.assertEqual(inversa["front"].strip(), c["back"].strip())
                    self.assertEqual(inversa["back"].strip(), c["front"].strip())
                    self.assertIn(seed.ETIQUETA_INVERSA, inversa["tags"])

    def test_una_cloze_se_importa_con_sus_huecos_intactos(self):
        from appstudy import cloze
        seed.load_all(self.con)
        filas = self.con.execute("SELECT front FROM cards WHERE kind='cloze'").fetchall()
        self.assertGreater(len(filas), 0, "no hay ninguna tarjeta de huecos de fábrica")
        for f in filas:
            with self.subTest(tarjeta=f["front"][:40]):
                self.assertTrue(cloze.tiene_huecos(f["front"]))
                self.assertNotIn(cloze.HUECO, cloze.completo(f["front"]))

    def test_toda_tarjeta_importada_nace_con_su_estado(self):
        seed.load_all(self.con)
        huerfanas = self.con.execute(
            "SELECT COUNT(*) FROM cards c LEFT JOIN state s ON s.card_id=c.id "
            "WHERE s.card_id IS NULL").fetchone()[0]
        self.assertEqual(huerfanas, 0)


if __name__ == "__main__":
    unittest.main()
