"""Los logros: que se den cuando toca, una sola vez, y nunca por accidente.

Lo importante no es que se consigan, sino que **no** se consigan antes de
tiempo: un logro que salta solo pierde toda la gracia. Por eso casi cada prueba
comprueba primero que no está y después que sí.
"""
import time
import unittest

from appstudy import db, logros, scheduler
from tests.apoyo import BaseTemporal

GOOD = scheduler.GOOD
AGAIN = scheduler.AGAIN
DIA = 86400.0


class BaseLogros(BaseTemporal):
    def claves(self, celebrar=False):
        return {le["clave"] for le in logros.revisar(self.con, celebrar=celebrar)}

    def dias_seguidos(self, cuantos):
        """Un repaso en cada uno de los últimos `cuantos` días."""
        cid = self.tarjeta(self.mazo(), "la de la racha")
        for atras in range(cuantos):
            self.repasar(cid, GOOD, cuando=time.time() - atras * DIA)
        return cid


class TestRachas(BaseLogros):
    def test_la_racha_de_siete_no_salta_con_seis(self):
        self.dias_seguidos(6)
        self.assertNotIn("racha_7", self.claves())

    def test_la_racha_de_siete_salta_con_siete(self):
        self.dias_seguidos(7)
        self.assertIn("racha_7", self.claves())

    def test_con_treinta_dias_caen_las_dos_rachas(self):
        self.dias_seguidos(30)
        conseguidas = self.claves()
        self.assertIn("racha_7", conseguidas)
        self.assertIn("racha_30", conseguidas)
        self.assertNotIn("racha_100", conseguidas)

    def test_un_hueco_rompe_la_racha(self):
        cid = self.tarjeta(self.mazo(), "la de la racha rota")
        for atras in list(range(0, 4)) + list(range(5, 12)):
            self.repasar(cid, GOOD, cuando=time.time() - atras * DIA)
        self.assertNotIn("racha_7", self.claves())


class TestVolumen(BaseLogros):
    def test_el_primer_repaso(self):
        cid = self.tarjeta(self.mazo(), "la primera")
        self.assertNotIn("primer_repaso", self.claves())
        scheduler.apply_review(self.con, cid, GOOD)
        self.assertIn("primer_repaso", self.claves())

    def test_cincuenta_en_un_dia(self):
        cid = self.tarjeta(self.mazo(), "una")
        for _ in range(49):
            self.repasar(cid, GOOD)
        self.assertNotIn("dia_50", self.claves())
        self.repasar(cid, GOOD)
        self.assertIn("dia_50", self.claves())

    def test_cincuenta_repartidos_en_dos_dias_no_cuentan(self):
        cid = self.tarjeta(self.mazo(), "una")
        for _ in range(30):
            self.repasar(cid, GOOD)
        for _ in range(30):
            self.repasar(cid, GOOD, cuando=time.time() - 2 * DIA)
        self.assertNotIn("dia_50", self.claves())

    def test_mil_repasos_en_total(self):
        cid = self.tarjeta(self.mazo(), "una")
        base = time.time() - 300 * DIA
        for i in range(999):
            self.repasar(cid, GOOD, cuando=base + i * 3600)
        self.assertNotIn("repasos_1000", self.claves())
        self.repasar(cid, GOOD, cuando=base + 1000 * 3600)
        self.assertIn("repasos_1000", self.claves())


class TestDominio(BaseLogros):
    def madurar(self, deck, cuantas, total, intervalo=40):
        ids = [self.tarjeta(deck, f"t{i}") for i in range(total)]
        for cid in ids[:cuantas]:
            scheduler.apply_review(self.con, cid, GOOD)
            self.con.execute("UPDATE state SET interval=? WHERE card_id=?",
                             (intervalo, cid))
        self.con.commit()
        return ids

    def test_un_mazo_pequeno_no_se_puede_dominar(self):
        # Con cinco tarjetas «dominar» no significa nada.
        deck = self.mazo()
        self.madurar(deck, 5, 5)
        self.assertNotIn("mazo_dominado", self.claves())

    def test_hace_falta_el_ochenta_por_ciento(self):
        deck = self.mazo()
        self.madurar(deck, 15, 25)          # 60 %
        self.assertNotIn("mazo_dominado", self.claves())

    def test_con_el_ochenta_por_ciento_si(self):
        deck = self.mazo()
        self.madurar(deck, 20, 25)          # 80 %
        nuevos = logros.revisar(self.con, celebrar=False)
        dominado = next(le for le in nuevos if le["clave"] == "mazo_dominado")
        self.assertEqual(dominado["dato"], "Linux")

    def test_las_de_intervalo_corto_no_valen(self):
        deck = self.mazo()
        self.madurar(deck, 25, 25, intervalo=5)
        self.assertNotIn("mazo_dominado", self.claves())

    def test_un_ano_de_memoria(self):
        deck = self.mazo()
        ids = [self.tarjeta(deck, f"t{i}") for i in range(10)]
        for cid in ids:
            scheduler.apply_review(self.con, cid, GOOD)
            self.con.execute("UPDATE state SET stability=36 WHERE card_id=?", (cid,))
        self.con.commit()
        self.assertNotIn("memoria_año", self.claves())
        self.con.execute("UPDATE state SET stability=37 WHERE reps>0")
        self.con.commit()
        self.assertIn("memoria_año", self.claves())


class TestLectura(BaseLogros):
    def capitulo(self, deck, titulo, nivel=1):
        cid, _ = db.upsert_chapter(self.con, deck, "linux",
                                   {"title": titulo, "level": nivel, "body": []})
        return cid

    def test_un_capitulo_avanzado_leido(self):
        deck = self.mazo()
        basico = self.capitulo(deck, "El básico", nivel=1)
        db.mark_read(self.con, basico)
        self.assertNotIn("capitulo_avanzado", self.claves())
        avanzado = self.capitulo(deck, "El difícil", nivel=3)
        db.mark_read(self.con, avanzado)
        nuevos = {le["clave"]: le for le in logros.revisar(self.con, celebrar=False)}
        self.assertEqual(nuevos["capitulo_avanzado"]["dato"], "El difícil")

    def test_un_capitulo_avanzado_sin_leer_no_cuenta(self):
        deck = self.mazo()
        self.capitulo(deck, "El difícil", nivel=3)
        self.assertNotIn("capitulo_avanzado", self.claves())

    def test_un_mazo_leido_entero(self):
        deck = self.mazo()
        ids = [self.capitulo(deck, f"Capítulo {i}") for i in range(4)]
        for cid in ids[:3]:
            db.mark_read(self.con, cid)
        self.assertNotIn("mazo_leido", self.claves())
        db.mark_read(self.con, ids[3])
        self.assertIn("mazo_leido", self.claves())

    def test_un_mazo_de_dos_capitulos_no_cuenta_como_leido_entero(self):
        deck = self.mazo()
        for i in range(2):
            db.mark_read(self.con, self.capitulo(deck, f"Capítulo {i}"))
        self.assertNotIn("mazo_leido", self.claves())


class TestSinAtragantadas(BaseLogros):
    def test_hacen_falta_cien_repasos(self):
        cid = self.tarjeta(self.mazo(), "una")
        for _ in range(99):
            self.repasar(cid, GOOD)
        self.assertNotIn("sin_atragantadas", self.claves())
        self.repasar(cid, GOOD)
        self.assertIn("sin_atragantadas", self.claves())

    def test_una_atragantada_lo_impide(self):
        deck = self.mazo()
        buena = self.tarjeta(deck, "la buena")
        mala = self.tarjeta(deck, "la mala")
        for _ in range(100):
            self.repasar(buena, GOOD)
        for _ in range(scheduler.UMBRAL_SANGUIJUELA):
            scheduler.apply_review(self.con, mala, AGAIN)
        self.assertNotIn("sin_atragantadas", self.claves())


class TestGuardado(BaseLogros):
    def test_celebrar_false_no_apunta_nada(self):
        scheduler.apply_review(self.con, self.tarjeta(self.mazo(), "una"), GOOD)
        logros.revisar(self.con, celebrar=False)
        self.assertEqual(logros.conseguidos(self.con), {})

    def test_solo_se_celebra_una_vez(self):
        scheduler.apply_review(self.con, self.tarjeta(self.mazo(), "una"), GOOD)
        primera = logros.revisar(self.con)
        self.assertTrue(primera)
        self.assertEqual(logros.revisar(self.con), [])

    def test_se_guarda_la_fecha_y_el_dato(self):
        deck = self.mazo()
        ids = [self.tarjeta(deck, f"t{i}") for i in range(25)]
        for cid in ids[:20]:
            scheduler.apply_review(self.con, cid, GOOD)
            self.con.execute("UPDATE state SET interval=40 WHERE card_id=?", (cid,))
        self.con.commit()
        logros.revisar(self.con)
        guardado = logros.conseguidos(self.con)["mazo_dominado"]
        self.assertEqual(guardado["dato"], "Linux")
        self.assertAlmostEqual(guardado["ts"], time.time(), delta=10)

    def test_el_recuento_va_subiendo(self):
        self.assertEqual(logros.cuantos(self.con), (0, len(logros.LOGROS)))
        scheduler.apply_review(self.con, self.tarjeta(self.mazo(), "una"), GOOD)
        logros.revisar(self.con)
        self.assertEqual(logros.cuantos(self.con)[0], 1)

    def test_el_listado_los_trae_todos_con_su_estado(self):
        scheduler.apply_review(self.con, self.tarjeta(self.mazo(), "una"), GOOD)
        logros.revisar(self.con)
        lista = logros.listado(self.con)
        self.assertEqual(len(lista), len(logros.LOGROS))
        conseguido = next(le for le in lista if le["clave"] == "primer_repaso")
        self.assertTrue(conseguido["conseguido"])
        self.assertIsNotNone(conseguido["ts"])
        pendiente = next(le for le in lista if le["clave"] == "racha_100")
        self.assertFalse(pendiente["conseguido"])
        self.assertIsNone(pendiente["ts"])

    def test_olvidar_los_borra_y_se_pueden_volver_a_ganar(self):
        scheduler.apply_review(self.con, self.tarjeta(self.mazo(), "una"), GOOD)
        logros.revisar(self.con)
        logros.olvidar(self.con)
        self.assertEqual(logros.cuantos(self.con)[0], 0)
        self.assertTrue(logros.revisar(self.con))

    def test_un_guardado_corrupto_no_tumba_nada(self):
        for basura in ("{no es json", "[1,2,3]", "null", '{"inventado": {"ts": 1}}'):
            db.set_meta(self.con, logros.CLAVE_META, basura)
            with self.subTest(basura=basura):
                self.assertEqual(logros.conseguidos(self.con), {})
                logros.listado(self.con)          # no debe lanzar

    def test_una_regla_que_falla_no_impide_los_demas(self):
        def explota(con, datos):
            raise RuntimeError("regla rota")

        original = logros.LOGROS[0]["regla"]
        logros.LOGROS[0]["regla"] = explota
        try:
            deck = self.mazo()
            cid = self.tarjeta(deck, "una")
            for _ in range(50):
                self.repasar(cid, GOOD)
            claves = {le["clave"] for le in logros.revisar(self.con, celebrar=False)}
            self.assertNotIn("primer_repaso", claves)   # la rota se salta
            self.assertIn("dia_50", claves)             # las demás siguen
        finally:
            logros.LOGROS[0]["regla"] = original


class TestCache(BaseLogros):
    """La comprobación corre en cada calificación: no puede ser cara."""

    def test_la_racha_se_calcula_una_sola_vez_por_comprobacion(self):
        self.dias_seguidos(10)
        datos = logros.Datos(self.con)
        llamadas = []
        original = db.streak
        db.streak = lambda con: (llamadas.append(1), original(con))[1]
        try:
            for _ in range(5):
                datos.racha
        finally:
            db.streak = original
        self.assertEqual(len(llamadas), 1)

    def test_el_mejor_dia_lo_calcula_la_base_y_no_un_bucle(self):
        deck = self.mazo()
        cid = self.tarjeta(deck, "una")
        for _ in range(7):
            self.repasar(cid, GOOD, cuando=time.time() - 3 * DIA)
        for _ in range(4):
            self.repasar(cid, GOOD)
        self.assertEqual(logros.Datos(self.con).mejor_dia, 7)

    def test_sin_repasos_el_mejor_dia_es_cero(self):
        self.assertEqual(logros.Datos(self.con).mejor_dia, 0)
        self.assertEqual(logros.Datos(self.con).repasos, 0)

    def test_cada_comprobacion_estrena_cache(self):
        # Si la caché sobreviviera entre llamadas, un logro recién cruzado
        # tardaría en detectarse.
        cid = self.dias_seguidos(6)
        self.assertNotIn("racha_7", self.claves())
        self.repasar(cid, GOOD, cuando=time.time() - 6 * DIA)
        self.assertIn("racha_7", self.claves())


class TestFrases(unittest.TestCase):
    def test_toda_frase_se_puede_escribir_sin_dato(self):
        for le in logros.LOGROS:
            with self.subTest(logro=le["clave"]):
                self.assertTrue(logros.frase_de(le))

    def test_las_frases_con_hueco_lo_rellenan(self):
        con_hueco = [le for le in logros.LOGROS if "{dato}" in le["frase"]]
        self.assertTrue(con_hueco)
        for le in con_hueco:
            self.assertIn("Linux", logros.frase_de(le, "Linux"))

    def test_las_claves_no_se_repiten(self):
        claves = [le["clave"] for le in logros.LOGROS]
        self.assertEqual(len(claves), len(set(claves)))

    def test_todos_traen_icono_titulo_y_pista(self):
        for le in logros.LOGROS:
            with self.subTest(logro=le["clave"]):
                for campo in ("icono", "titulo", "pista", "frase"):
                    self.assertTrue(le[campo].strip())


if __name__ == "__main__":
    unittest.main()
