"""Sanguijuelas, deshacer, objetivo diario y la migración desde SM-2.

Todo lo que rodea al repaso pero no es el modelo de memoria: qué se aparta, qué
se puede deshacer, cómo se cuenta la meta del día, y que una base con historial
de SM-2 entre en FSRS sin perder por dónde iba.
"""
import sqlite3
import time
import unittest

from appstudy import db, fsrs, scheduler
from tests.apoyo import BaseTemporal

AGAIN, HARD, GOOD, EASY = (scheduler.AGAIN, scheduler.HARD,
                           scheduler.GOOD, scheduler.EASY)


class TestSanguijuelas(BaseTemporal):
    def fallar(self, card_id, veces):
        for _ in range(veces):
            st = scheduler.apply_review(self.con, card_id, AGAIN)
        return st

    def test_se_aparta_al_llegar_al_umbral(self):
        cid = self.tarjeta(self.mazo(), "la que se me atraganta")
        st = self.fallar(cid, scheduler.UMBRAL_SANGUIJUELA)
        self.assertTrue(st["sanguijuela"])
        self.assertEqual(self.con.execute(
            "SELECT leech FROM state WHERE card_id=?", (cid,)).fetchone()[0], 1)

    def test_antes_del_umbral_no_se_aparta(self):
        cid = self.tarjeta(self.mazo(), "la que voy fallando")
        st = self.fallar(cid, scheduler.UMBRAL_SANGUIJUELA - 1)
        self.assertFalse(st["sanguijuela"])
        self.assertEqual(self.con.execute(
            "SELECT leech FROM state WHERE card_id=?", (cid,)).fetchone()[0], 0)

    def test_solo_avisa_la_primera_vez(self):
        cid = self.tarjeta(self.mazo(), "la pesada")
        self.fallar(cid, scheduler.UMBRAL_SANGUIJUELA)
        self.assertFalse(scheduler.apply_review(self.con, cid, AGAIN)["sanguijuela"])

    def test_una_apartada_no_sale_a_estudiar(self):
        deck = self.mazo()
        mala = self.tarjeta(deck, "la apartada")
        buena = self.tarjeta(deck, "la normal")
        self.fallar(mala, scheduler.UMBRAL_SANGUIJUELA)
        for _ in range(15):
            elegida = scheduler.next_card(self.con)
            self.assertEqual(elegida["id"], buena)

    def test_si_se_piden_expresamente_si_salen(self):
        cid = self.tarjeta(self.mazo(), "la apartada")
        self.fallar(cid, scheduler.UMBRAL_SANGUIJUELA)
        self.assertIsNotNone(scheduler.next_card(self.con, incluir_sanguijuelas=True))

    def test_perdonar_la_devuelve_al_ciclo_sin_fallos(self):
        cid = self.tarjeta(self.mazo(), "la perdonada")
        self.fallar(cid, scheduler.UMBRAL_SANGUIJUELA)
        scheduler.perdonar(self.con, cid)
        fila = self.con.execute("SELECT leech, lapses FROM state WHERE card_id=?",
                                (cid,)).fetchone()
        self.assertEqual(fila["leech"], 0)
        self.assertEqual(fila["lapses"], 0)
        self.assertIsNotNone(scheduler.next_card(self.con))

    def test_la_lista_las_ordena_por_lo_mucho_que_las_fallas(self):
        deck = self.mazo()
        poca = self.tarjeta(deck, "la de ocho fallos")
        mucha = self.tarjeta(deck, "la de quince fallos")
        self.fallar(poca, 8)
        self.fallar(mucha, 15)
        lista = db.leeches(self.con)
        self.assertEqual([c["id"] for c in lista], [mucha, poca])
        self.assertEqual(lista[0]["deck_name"], "Linux")

    def test_bajar_el_umbral_aparta_mas_y_subirlo_libera(self):
        deck = self.mazo()
        cid = self.tarjeta(deck, "la de cinco fallos")
        self.fallar(cid, 5)
        self.assertEqual(scheduler.recalcular_sanguijuelas(self.con), 0)
        db.set_meta(self.con, "umbral_sanguijuela", 4)
        self.assertEqual(scheduler.recalcular_sanguijuelas(self.con), 1)
        db.set_meta(self.con, "umbral_sanguijuela", 20)
        self.assertEqual(scheduler.recalcular_sanguijuelas(self.con), 0)

    def test_el_umbral_cero_lo_desactiva(self):
        cid = self.tarjeta(self.mazo(), "la que da igual")
        db.set_meta(self.con, "umbral_sanguijuela", 0)
        self.assertFalse(self.fallar(cid, 20)["sanguijuela"])
        self.assertEqual(scheduler.recalcular_sanguijuelas(self.con), 0)

    def test_los_totales_las_cuentan(self):
        cid = self.tarjeta(self.mazo(), "la apartada")
        self.fallar(cid, scheduler.UMBRAL_SANGUIJUELA)
        self.assertEqual(db.totals(self.con)["sanguijuelas"], 1)


class TestUndoLast(BaseTemporal):
    def test_deshace_el_ultimo_repaso_y_devuelve_lo_que_deshizo(self):
        cid = self.tarjeta(self.mazo(), "¿Qué hace ls?")
        scheduler.apply_review(self.con, cid, GOOD)
        antes = dict(self.con.execute("SELECT * FROM state WHERE card_id=?",
                                      (cid,)).fetchone())
        scheduler.apply_review(self.con, cid, EASY)

        hecho = scheduler.undo_last(self.con)

        self.assertEqual(hecho["card_id"], cid)
        self.assertEqual(hecho["rating"], EASY)
        ahora = dict(self.con.execute("SELECT * FROM state WHERE card_id=?",
                                      (cid,)).fetchone())
        self.assertEqual(ahora["reps"], antes["reps"])
        self.assertAlmostEqual(ahora["stability"], antes["stability"], places=6)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM log").fetchone()[0], 1)

    def test_deshacer_el_unico_repaso_la_deja_sin_ver(self):
        cid = self.tarjeta(self.mazo(), "¿Qué hace cat?")
        scheduler.apply_review(self.con, cid, GOOD)
        scheduler.undo_last(self.con)
        fila = self.con.execute("SELECT * FROM state WHERE card_id=?", (cid,)).fetchone()
        self.assertEqual(fila["reps"], 0)
        self.assertEqual(fila["stability"], 0.0)
        self.assertEqual(fila["interval"], 0.0)

    def test_sin_nada_que_deshacer_devuelve_nada(self):
        self.tarjeta(self.mazo(), "sin estudiar")
        self.assertIsNone(scheduler.undo_last(self.con))

    def test_deshace_el_de_la_tarjeta_que_le_pidas(self):
        deck = self.mazo()
        a = self.tarjeta(deck, "la primera")
        b = self.tarjeta(deck, "la segunda")
        scheduler.apply_review(self.con, a, GOOD)
        scheduler.apply_review(self.con, b, GOOD)

        hecho = scheduler.undo_last(self.con, card_id=a)

        self.assertEqual(hecho["card_id"], a)
        # El de la otra sigue en pie
        self.assertEqual(self.con.execute(
            "SELECT COUNT(*) FROM log WHERE card_id=?", (b,)).fetchone()[0], 1)

    def test_deshacer_un_fallo_quita_tambien_el_lapso(self):
        cid = self.tarjeta(self.mazo(), "la fallada por error")
        scheduler.apply_review(self.con, cid, GOOD)
        scheduler.apply_review(self.con, cid, AGAIN)
        self.assertEqual(self.con.execute(
            "SELECT lapses FROM state WHERE card_id=?", (cid,)).fetchone()[0], 1)
        scheduler.undo_last(self.con)
        self.assertEqual(self.con.execute(
            "SELECT lapses FROM state WHERE card_id=?", (cid,)).fetchone()[0], 0)

    def test_deshacer_saca_a_una_tarjeta_de_las_apartadas(self):
        # El caso que de verdad importa: le diste a «Otra vez» sin querer y la
        # tarjeta cruzó el umbral. Deshacer tiene que devolverla al ciclo.
        cid = self.tarjeta(self.mazo(), "apartada sin querer")
        for _ in range(scheduler.UMBRAL_SANGUIJUELA):
            scheduler.apply_review(self.con, cid, AGAIN)
        self.assertEqual(self.con.execute(
            "SELECT leech FROM state WHERE card_id=?", (cid,)).fetchone()[0], 1)
        scheduler.undo_last(self.con)
        self.assertEqual(self.con.execute(
            "SELECT leech FROM state WHERE card_id=?", (cid,)).fetchone()[0], 0)

    def test_deshacer_varias_veces_va_hacia_atras_en_orden(self):
        cid = self.tarjeta(self.mazo(), "la de muchos repasos")
        for nota in (GOOD, GOOD, HARD, EASY):
            scheduler.apply_review(self.con, cid, nota)
        for esperada in (EASY, HARD, GOOD, GOOD):
            self.assertEqual(scheduler.undo_last(self.con)["rating"], esperada)
        self.assertIsNone(scheduler.undo_last(self.con))

    def test_rehacer_usa_las_fechas_de_verdad_de_cada_repaso(self):
        # Si el rehecho ignorara las fechas, una tarjeta con repasos espaciados
        # meses acabaría con la estabilidad de una repasada tres veces seguidas.
        cid = self.tarjeta(self.mazo(), "la de repasos espaciados")
        base = time.time() - 200 * scheduler.DAY
        for i, nota in enumerate((GOOD, GOOD, GOOD)):
            self.repasar(cid, nota, cuando=base + i * 60 * scheduler.DAY)
        scheduler.apply_review(self.con, cid, GOOD)

        scheduler.undo_last(self.con)

        fila = self.con.execute("SELECT stability, last FROM state WHERE card_id=?",
                                (cid,)).fetchone()
        # El último repaso rehecho es el tercero, hace 80 días
        self.assertAlmostEqual(fila["last"], base + 120 * scheduler.DAY, delta=5)
        self.assertGreater(fila["stability"], 10.0)


class TestObjetivoDiario(BaseTemporal):
    def test_de_fabrica_no_hay_objetivo(self):
        t = db.totals(self.con)
        self.assertEqual(t["objetivo"], 0)
        self.assertEqual(t["restan"], 0)

    def test_se_guarda_y_se_lee(self):
        db.set_objetivo_diario(self.con, 30)
        self.assertEqual(db.objetivo_diario(self.con), 30)
        self.assertEqual(db.totals(self.con)["objetivo"], 30)

    def test_lo_que_falta_baja_con_cada_repaso(self):
        deck = self.mazo()
        db.set_objetivo_diario(self.con, 3)
        ids = [self.tarjeta(deck, f"tarjeta {i}") for i in range(3)]
        self.assertEqual(db.totals(self.con)["restan"], 3)
        scheduler.apply_review(self.con, ids[0], GOOD)
        self.assertEqual(db.totals(self.con)["restan"], 2)
        for cid in ids[1:]:
            scheduler.apply_review(self.con, cid, GOOD)
        self.assertEqual(db.totals(self.con)["restan"], 0)

    def test_pasarse_del_objetivo_no_deja_lo_que_falta_en_negativo(self):
        deck = self.mazo()
        db.set_objetivo_diario(self.con, 1)
        for i in range(5):
            scheduler.apply_review(self.con, self.tarjeta(deck, f"t{i}"), GOOD)
        self.assertEqual(db.totals(self.con)["restan"], 0)

    def test_un_objetivo_negativo_se_guarda_como_cero(self):
        db.set_objetivo_diario(self.con, -10)
        self.assertEqual(db.objetivo_diario(self.con), 0)

    def test_la_semana_trae_siete_dias_terminando_hoy(self):
        semana = db.repasos_por_dia(self.con, 7)
        self.assertEqual(len(semana), 7)
        self.assertEqual(semana[-1]["dia"],
                         time.strftime("%Y-%m-%d", time.localtime()))

    def test_la_semana_cuenta_cada_repaso_en_su_dia(self):
        deck = self.mazo()
        cid = self.tarjeta(deck, "una cualquiera")
        self.repasar(cid, GOOD)
        self.repasar(cid, GOOD, cuando=time.time() - 2 * 86400)
        semana = {d["dia"]: d["n"] for d in db.repasos_por_dia(self.con, 7)}
        hoy = time.strftime("%Y-%m-%d", time.localtime())
        hace_dos = time.strftime("%Y-%m-%d", time.localtime(time.time() - 2 * 86400))
        self.assertEqual(semana[hoy], 1)
        self.assertEqual(semana[hace_dos], 1)

    def test_marca_los_dias_en_que_cumpliste(self):
        deck = self.mazo()
        db.set_objetivo_diario(self.con, 2)
        for i in range(2):
            self.repasar(self.tarjeta(deck, f"t{i}"), GOOD)
        semana = db.repasos_por_dia(self.con, 7)
        self.assertTrue(semana[-1]["cumplido"])
        self.assertFalse(semana[0]["cumplido"])


class TestMigracionDesdeSM2(BaseTemporal):
    """Una base con historial de SM-2 tiene que entrar en FSRS sin perder nada."""

    def estado_sm2(self, card_id, interval, ease, reps=5, lapses=0):
        """Deja una tarjeta como la habría dejado el planificador anterior."""
        self.con.execute(
            """UPDATE state SET interval=?, ease=?, reps=?, lapses=?, due=?, last=?,
                                stability=0, difficulty=0 WHERE card_id=?""",
            (interval, ease, reps, lapses, time.time() + interval * 86400,
             time.time(), card_id))
        self.con.commit()

    def test_el_intervalo_se_convierte_en_estabilidad(self):
        cid = self.tarjeta(self.mazo(), "una de antes")
        self.estado_sm2(cid, interval=30.0, ease=2.5)
        db.convertir_a_fsrs(self.con)
        fila = self.con.execute("SELECT stability FROM state WHERE card_id=?",
                                (cid,)).fetchone()
        self.assertAlmostEqual(fila["stability"], 30.0)

    def test_la_facilidad_se_convierte_en_dificultad_al_reves(self):
        deck = self.mazo()
        facil = self.tarjeta(deck, "la que se me daba bien")
        dura = self.tarjeta(deck, "la que se me daba mal")
        self.estado_sm2(facil, 30.0, ease=3.0)
        self.estado_sm2(dura, 30.0, ease=1.3)
        db.convertir_a_fsrs(self.con)
        d_facil = self.con.execute("SELECT difficulty FROM state WHERE card_id=?",
                                   (facil,)).fetchone()[0]
        d_dura = self.con.execute("SELECT difficulty FROM state WHERE card_id=?",
                                  (dura,)).fetchone()[0]
        self.assertLess(d_facil, d_dura)
        self.assertAlmostEqual(d_facil, fsrs.D_MIN, places=3)
        self.assertAlmostEqual(d_dura, fsrs.D_MAX, places=3)

    def test_la_facilidad_de_fabrica_cae_en_mitad_de_la_escala(self):
        cid = self.tarjeta(self.mazo(), "una del montón")
        self.estado_sm2(cid, 10.0, ease=2.5)
        db.convertir_a_fsrs(self.con)
        d = self.con.execute("SELECT difficulty FROM state WHERE card_id=?",
                             (cid,)).fetchone()[0]
        self.assertGreater(d, 2.0)
        self.assertLess(d, 6.0)

    def test_no_toca_las_que_nunca_se_estudiaron(self):
        cid = self.tarjeta(self.mazo(), "sin estrenar")
        self.assertEqual(db.convertir_a_fsrs(self.con), 0)
        self.assertEqual(self.con.execute(
            "SELECT stability FROM state WHERE card_id=?", (cid,)).fetchone()[0], 0.0)

    def test_repetir_la_conversion_no_hace_nada(self):
        cid = self.tarjeta(self.mazo(), "una de antes")
        self.estado_sm2(cid, 30.0, 2.5)
        self.assertEqual(db.convertir_a_fsrs(self.con), 1)
        self.assertEqual(db.convertir_a_fsrs(self.con), 0)

    def test_la_tarjeta_convertida_sigue_venciendo_cuando_le_tocaba(self):
        cid = self.tarjeta(self.mazo(), "una de antes")
        self.estado_sm2(cid, 30.0, 2.5)
        vencia = self.con.execute("SELECT due FROM state WHERE card_id=?",
                                  (cid,)).fetchone()[0]
        db.convertir_a_fsrs(self.con)
        self.assertAlmostEqual(self.con.execute(
            "SELECT due FROM state WHERE card_id=?", (cid,)).fetchone()[0], vencia)

    def test_tras_convertir_el_siguiente_repaso_ya_usa_fsrs(self):
        cid = self.tarjeta(self.mazo(), "una de antes")
        self.estado_sm2(cid, 30.0, 2.5)
        db.convertir_a_fsrs(self.con)
        st = scheduler.apply_review(self.con, cid, GOOD)
        self.assertGreater(st["stability"], 30.0)
        self.assertGreater(st["interval"], 30.0)

    def test_una_base_sin_las_columnas_nuevas_se_migra_al_conectar(self):
        # Una instalación anterior no tiene stability, difficulty ni leech.
        vieja = self.tmp / "vieja.db"
        con = sqlite3.connect(vieja)
        con.executescript("""
            CREATE TABLE state (
                card_id INTEGER PRIMARY KEY, due REAL DEFAULT 0,
                interval REAL DEFAULT 0, ease REAL DEFAULT 2.5,
                reps INTEGER DEFAULT 0, lapses INTEGER DEFAULT 0,
                last REAL DEFAULT 0);
            INSERT INTO state VALUES (1, 0, 45.0, 2.2, 6, 1, 0);
        """)
        con.commit()
        con.row_factory = sqlite3.Row
        db.migrate(con)
        columnas = {r["name"] for r in con.execute("PRAGMA table_info(state)")}
        self.assertTrue({"stability", "difficulty", "leech"} <= columnas)
        fila = con.execute("SELECT stability, difficulty FROM state").fetchone()
        self.assertAlmostEqual(fila["stability"], 45.0)
        self.assertGreater(fila["difficulty"], 1.0)
        con.close()


class TestConfig(BaseTemporal):
    def test_los_valores_de_fabrica(self):
        c = scheduler.config(self.con)
        self.assertAlmostEqual(c["retencion"], scheduler.RETENCION_POR_DEFECTO)
        self.assertEqual(c["w"], fsrs.W_POR_DEFECTO)
        self.assertEqual(c["umbral"], scheduler.UMBRAL_SANGUIJUELA)

    def test_la_retencion_se_acota_a_lo_razonable(self):
        db.set_meta(self.con, "retencion", 0.5)
        self.assertAlmostEqual(scheduler.config(self.con)["retencion"], 0.70)
        db.set_meta(self.con, "retencion", 1.5)
        self.assertAlmostEqual(scheduler.config(self.con)["retencion"], 0.99)

    def test_unos_valores_corruptos_no_tumban_el_estudio(self):
        db.set_meta(self.con, "retencion", "lo que sea")
        db.set_meta(self.con, "fsrs_w", "{esto no es json")
        db.set_meta(self.con, "umbral_sanguijuela", "ocho")
        c = scheduler.config(self.con)
        self.assertAlmostEqual(c["retencion"], scheduler.RETENCION_POR_DEFECTO)
        self.assertEqual(c["w"], fsrs.W_POR_DEFECTO)
        self.assertEqual(c["umbral"], scheduler.UMBRAL_SANGUIJUELA)

    def test_unos_pesos_con_el_numero_equivocado_se_ignoran(self):
        db.set_meta(self.con, "fsrs_w", "[1, 2, 3]")
        self.assertEqual(scheduler.config(self.con)["w"], fsrs.W_POR_DEFECTO)

    def test_unos_pesos_propios_se_usan_al_calificar(self):
        import json
        propios = list(fsrs.W_POR_DEFECTO)
        propios[2] = 20.0                      # una nueva con «Bien» dura 20 días
        db.set_meta(self.con, "fsrs_w", json.dumps(propios))
        cid = self.tarjeta(self.mazo(), "con pesos míos")
        self.assertAlmostEqual(scheduler.apply_review(self.con, cid, GOOD)["stability"],
                               20.0)

    def test_la_retencion_elegida_se_usa_al_calificar(self):
        deck = self.mazo()
        db.set_meta(self.con, "retencion", 0.95)
        exigente = scheduler.apply_review(self.con, self.tarjeta(deck, "a"), GOOD)
        db.set_meta(self.con, "retencion", 0.80)
        relajado = scheduler.apply_review(self.con, self.tarjeta(deck, "b"), GOOD)
        self.assertLess(exigente["interval"], relajado["interval"])


if __name__ == "__main__":
    unittest.main()
