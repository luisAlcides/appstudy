"""El algoritmo de repetición espaciada: lo que decide cuándo vuelve una tarjeta.

Es la pieza de la que depende que estudiar sirva de algo, así que aquí se fija
su comportamiento: la escalera de aprendizaje, el castigo del fallo, el techo
del año, la selección de la próxima tarjeta y el deshacer del día.
"""
import time
import unittest

from appstudy import scheduler
from tests.apoyo import BaseTemporal

AGAIN, HARD, GOOD, EASY = scheduler.AGAIN, scheduler.HARD, scheduler.GOOD, scheduler.EASY
DIA = scheduler.DAY


class TestReview(unittest.TestCase):
    """`review()` es una función pura: estado + calificación -> estado nuevo."""

    def test_una_tarjeta_nueva_bien_entra_en_la_escalera(self):
        st = scheduler.review({}, GOOD)
        self.assertAlmostEqual(st["interval"], 10 / 1440)
        self.assertEqual(st["reps"], 1)
        self.assertEqual(st["lapses"], 0)
        self.assertAlmostEqual(st["due"], time.time() + st["interval"] * DIA, delta=5)

    def test_la_escalera_es_diez_minutos_una_hora_un_dia(self):
        st, vistos = {}, []
        for _ in range(3):
            st = scheduler.review(st, GOOD)
            vistos.append(round(st["interval"], 6))
        self.assertEqual(vistos, [round(p, 6) for p in scheduler.LEARN_STEPS])
        self.assertEqual(st["reps"], scheduler.GRADUATE_AT)

    def test_al_graduarse_el_intervalo_se_multiplica_por_la_facilidad(self):
        st = {"interval": 1.0, "ease": 2.5, "reps": scheduler.GRADUATE_AT,
              "lapses": 0, "due": 0, "last": 0}
        nuevo = scheduler.review(st, GOOD)
        self.assertAlmostEqual(nuevo["interval"], 2.5)
        self.assertEqual(nuevo["reps"], scheduler.GRADUATE_AT + 1)

    def test_facil_salta_el_aprendizaje(self):
        st = scheduler.review({}, EASY)
        self.assertEqual(st["interval"], 4.0)
        self.assertEqual(st["reps"], scheduler.GRADUATE_AT)
        self.assertAlmostEqual(st["ease"], 2.65)

    def test_dificil_en_aprendizaje_vuelve_al_primer_peldano(self):
        st = scheduler.review(scheduler.review({}, GOOD), HARD)
        self.assertAlmostEqual(st["interval"], scheduler.LEARN_STEPS[0])

    def test_dificil_ya_graduada_alarga_poco_y_baja_la_facilidad(self):
        st = {"interval": 10.0, "ease": 2.5, "reps": 5, "lapses": 0, "due": 0, "last": 0}
        nuevo = scheduler.review(st, HARD)
        self.assertAlmostEqual(nuevo["ease"], 2.35)
        self.assertAlmostEqual(nuevo["interval"], 12.0)   # max(10*1.2, 10+1)

    def test_dificil_con_intervalo_corto_crece_al_menos_un_dia(self):
        st = {"interval": 1.0, "ease": 2.5, "reps": 5, "lapses": 0, "due": 0, "last": 0}
        self.assertAlmostEqual(scheduler.review(st, HARD)["interval"], 2.0)

    def test_fallar_reinicia_el_intervalo_y_cuenta_un_lapso(self):
        st = {"interval": 60.0, "ease": 2.5, "reps": 8, "lapses": 1, "due": 0, "last": 0}
        nuevo = scheduler.review(st, AGAIN)
        self.assertAlmostEqual(nuevo["interval"], scheduler.LEARN_STEPS[0])
        self.assertEqual(nuevo["reps"], 0)
        self.assertEqual(nuevo["lapses"], 2)
        self.assertAlmostEqual(nuevo["ease"], 2.30)

    def test_la_facilidad_no_baja_de_1_3_por_mucho_que_falles(self):
        st = {}
        for _ in range(30):
            st = scheduler.review(st, AGAIN)
        self.assertAlmostEqual(st["ease"], 1.3)

    def test_la_facilidad_no_sube_de_3(self):
        st = {}
        for _ in range(30):
            st = scheduler.review(st, EASY)
        self.assertAlmostEqual(st["ease"], 3.0)

    def test_el_intervalo_tiene_techo_de_un_ano(self):
        st = {"interval": 300.0, "ease": 3.0, "reps": 20, "lapses": 0, "due": 0, "last": 0}
        for _ in range(5):
            st = scheduler.review(st, EASY)
            self.assertLessEqual(st["interval"], 365.0)
        self.assertAlmostEqual(st["interval"], 365.0)

    def test_el_ruido_solo_afecta_a_intervalos_de_dias(self):
        # Por debajo de un día no hay jitter: 10 min son 10 min exactos.
        st = scheduler.review({}, GOOD)
        self.assertAlmostEqual(st["due"] - st["last"], st["interval"] * DIA, delta=0.01)
        # Por encima, el vencimiento se mueve como mucho un 5 %.
        largo = {"interval": 100.0, "ease": 2.5, "reps": 9, "lapses": 0, "due": 0, "last": 0}
        for _ in range(40):
            nuevo = scheduler.review(largo, GOOD)
            desvio = (nuevo["due"] - nuevo["last"]) / DIA / nuevo["interval"]
            self.assertGreaterEqual(desvio, 0.95)
            self.assertLessEqual(desvio, 1.05)

    def test_un_estado_con_valores_nulos_no_revienta(self):
        st = scheduler.review({"ease": None, "interval": None, "reps": None,
                               "lapses": None}, GOOD)
        self.assertEqual(st["reps"], 1)
        self.assertAlmostEqual(st["ease"], 2.5)


class TestDueLabel(unittest.TestCase):
    def test_etiquetas_de_cuando_toca(self):
        ahora = time.time()
        # Se suma un segundo de margen: la etiqueta trunca hacia abajo y entre
        # calcular `ahora` y llamar pasa una fracción de segundo.
        casos = ((ahora - 10, "ahora"), (ahora + 301, "5 min"), (ahora + 7201, "2 h"),
                 (ahora + 3 * DIA + 1, "3 d"), (ahora + 90 * DIA + 1, "3.0 meses"))
        for ts, esperado in casos:
            with self.subTest(esperado=esperado):
                self.assertEqual(scheduler.due_label(ts), esperado)


class TestApplyReview(BaseTemporal):
    def test_guarda_el_estado_y_deja_rastro_en_el_log(self):
        cid = self.tarjeta(self.mazo(), "¿Qué hace ls?")
        scheduler.apply_review(self.con, cid, GOOD, elapsed_ms=1234)
        fila = self.con.execute("SELECT * FROM state WHERE card_id=?", (cid,)).fetchone()
        self.assertEqual(fila["reps"], 1)
        registro = self.con.execute("SELECT * FROM log WHERE card_id=?", (cid,)).fetchone()
        self.assertEqual(registro["rating"], GOOD)
        self.assertEqual(registro["ms"], 1234)

    def test_repasos_seguidos_van_alargando_el_intervalo(self):
        cid = self.tarjeta(self.mazo(), "¿Qué hace cat?")
        anterior = 0.0
        for _ in range(5):
            st = scheduler.apply_review(self.con, cid, GOOD)
            self.assertGreater(st["interval"], anterior)
            anterior = st["interval"]


class TestUndoRecent(BaseTemporal):
    def test_borra_los_repasos_del_dia_y_rehace_el_estado(self):
        deck = self.mazo()
        cid = self.tarjeta(deck, "¿Qué hace grep?")
        ayer = time.time() - 2 * 86400
        self.repasar(cid, GOOD, cuando=ayer)
        estado_de_ayer = dict(self.con.execute(
            "SELECT * FROM state WHERE card_id=?", (cid,)).fetchone())
        self.repasar(cid, GOOD)
        self.repasar(cid, GOOD)

        quitados = scheduler.undo_recent(self.con)

        self.assertEqual(quitados, 2)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM log").fetchone()[0], 1)
        ahora = self.con.execute("SELECT * FROM state WHERE card_id=?", (cid,)).fetchone()
        self.assertEqual(ahora["reps"], estado_de_ayer["reps"])
        self.assertAlmostEqual(ahora["interval"], estado_de_ayer["interval"])

    def test_sin_repasos_anteriores_la_tarjeta_vuelve_a_estar_sin_ver(self):
        cid = self.tarjeta(self.mazo(), "¿Qué hace sed?")
        self.repasar(cid, GOOD)
        scheduler.undo_recent(self.con)
        fila = self.con.execute("SELECT * FROM state WHERE card_id=?", (cid,)).fetchone()
        self.assertEqual(fila["reps"], 0)
        self.assertEqual(fila["interval"], 0.0)
        self.assertAlmostEqual(fila["ease"], 2.5)

    def test_no_toca_lo_anterior_a_la_ventana(self):
        cid = self.tarjeta(self.mazo(), "¿Qué hace awk?")
        self.repasar(cid, GOOD, cuando=time.time() - 3 * 86400)
        self.assertEqual(scheduler.undo_recent(self.con), 0)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM log").fetchone()[0], 1)


class TestNextCard(BaseTemporal):
    def test_sin_tarjetas_no_devuelve_nada(self):
        self.assertIsNone(scheduler.next_card(self.con))

    def test_prefiere_lo_vencido_cuando_no_se_sortean_nuevas(self):
        deck = self.mazo()
        vencida = self.tarjeta(deck, "vencida")
        self.tarjeta(deck, "nueva sin ver")
        scheduler.apply_review(self.con, vencida, GOOD)
        self.vencer(vencida)
        elegida = scheduler.next_card(self.con, new_ratio=0.0)
        self.assertEqual(elegida["id"], vencida)

    def test_con_ratio_uno_siempre_saca_una_nueva(self):
        deck = self.mazo()
        vencida = self.tarjeta(deck, "vencida")
        nueva = self.tarjeta(deck, "nueva")
        scheduler.apply_review(self.con, vencida, GOOD)
        self.vencer(vencida)
        self.assertEqual(scheduler.next_card(self.con, new_ratio=1.0)["id"], nueva)

    def test_las_nuevas_salen_del_nivel_mas_bajo_pendiente(self):
        deck = self.mazo()
        self.tarjeta(deck, "avanzada", level=3)
        basica = self.tarjeta(deck, "básica", level=1)
        for _ in range(12):
            self.assertEqual(scheduler.next_card(self.con)["id"], basica)

    def test_respeta_el_mazo_pedido(self):
        linux = self.mazo("linux", "Linux")
        ingles = self.mazo("ingles", "Inglés")
        self.tarjeta(linux, "una de linux", key="linux")
        cid = self.tarjeta(ingles, "one in english", key="ingles")
        for _ in range(8):
            self.assertEqual(scheduler.next_card(self.con, deck_key="ingles")["id"], cid)

    def test_respeta_el_nivel_pedido(self):
        deck = self.mazo()
        self.tarjeta(deck, "básica", level=1)
        media = self.tarjeta(deck, "intermedia", level=2)
        for _ in range(8):
            self.assertEqual(scheduler.next_card(self.con, level=2)["id"], media)

    def test_respeta_las_etiquetas_pedidas(self):
        deck = self.mazo()
        self.tarjeta(deck, "de permisos", tags="permisos")
        cid = self.tarjeta(deck, "de systemd", tags="systemd,servicios")
        for _ in range(8):
            self.assertEqual(scheduler.next_card(self.con, tags="systemd")["id"], cid)

    def test_un_mazo_apagado_no_aporta_tarjetas(self):
        deck = self.mazo()
        self.tarjeta(deck, "una cualquiera")
        self.con.execute("UPDATE decks SET enabled=0")
        self.con.commit()
        self.assertIsNone(scheduler.next_card(self.con))
        # Pero pidiéndolo por su clave sí, que es lo que hace «practicar este capítulo»
        self.assertIsNotNone(scheduler.next_card(self.con, deck_key="linux"))

    def test_no_repite_la_tarjeta_excluida_si_hay_alternativa(self):
        deck = self.mazo()
        a = self.tarjeta(deck, "la primera")
        b = self.tarjeta(deck, "la segunda")
        for _ in range(10):
            self.assertEqual(scheduler.next_card(self.con, exclude_id=a)["id"], b)

    def test_con_una_sola_tarjeta_la_repite_antes_que_dejarte_sin_nada(self):
        # El atajo global nunca debe quedarse vacío, aunque solo haya una tarjeta.
        cid = self.tarjeta(self.mazo(), "la única")
        self.assertEqual(scheduler.next_card(self.con, exclude_id=cid)["id"], cid)

    def test_todo_al_dia_ofrece_un_repaso_de_refuerzo(self):
        cid = self.tarjeta(self.mazo(), "estudiada y no vencida")
        scheduler.apply_review(self.con, cid, EASY)     # vence dentro de días
        elegida = scheduler.next_card(self.con)
        self.assertIsNotNone(elegida)
        self.assertEqual(elegida["id"], cid)

    def test_devuelve_los_datos_del_mazo_junto_a_la_tarjeta(self):
        deck = self.mazo()
        self.tarjeta(deck, "una cualquiera")
        elegida = scheduler.next_card(self.con)
        self.assertEqual(elegida["deck_key"], "linux")
        self.assertEqual(elegida["deck_name"], "Linux")
        self.assertIn("deck_levels", elegida)


if __name__ == "__main__":
    unittest.main()
