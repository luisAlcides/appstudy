"""El algoritmo de repetición espaciada: lo que decide cuándo vuelve una tarjeta.

Es la pieza de la que depende que estudiar sirva de algo, así que aquí se fija
su comportamiento: la escalera de aprendizaje, el castigo del fallo, el techo
del año, la selección de la próxima tarjeta y el deshacer del día.
"""
import time
import unittest

from appstudy import fsrs, scheduler
from tests.apoyo import BaseTemporal

AGAIN, HARD, GOOD, EASY = scheduler.AGAIN, scheduler.HARD, scheduler.GOOD, scheduler.EASY
DIA = scheduler.DAY


class TestReview(unittest.TestCase):
    """`review()` es una función pura: estado + calificación -> estado nuevo."""

    def test_una_tarjeta_nueva_arranca_con_la_estabilidad_de_su_nota(self):
        for nota in (AGAIN, HARD, GOOD, EASY):
            with self.subTest(nota=nota):
                st = scheduler.review({}, nota)
                self.assertAlmostEqual(st["stability"], fsrs.estabilidad_inicial(nota))
                self.assertAlmostEqual(st["difficulty"], fsrs.dificultad_inicial(nota))

    def test_mejor_nota_significa_mas_espera_y_menos_dificultad(self):
        estados = [scheduler.review({}, n) for n in (HARD, GOOD, EASY)]
        intervalos = [e["interval"] for e in estados]
        dificultades = [e["difficulty"] for e in estados]
        self.assertEqual(intervalos, sorted(intervalos))
        self.assertEqual(dificultades, sorted(dificultades, reverse=True))

    def test_una_tarjeta_nueva_bien_no_vuelve_dentro_de_diez_minutos(self):
        # Con FSRS una tarjeta nueva que te sabes espera días, no minutos.
        st = scheduler.review({}, GOOD)
        self.assertGreater(st["interval"], 1.0)
        self.assertEqual(st["reps"], 1)
        self.assertEqual(st["lapses"], 0)

    def test_fallar_la_devuelve_hoy_mismo_y_cuenta_un_lapso(self):
        st = {"stability": 60.0, "difficulty": 5.0, "reps": 8, "lapses": 1,
              "due": 0, "last": time.time() - 60 * DIA}
        nuevo = scheduler.review(st, AGAIN)
        self.assertAlmostEqual(nuevo["interval"], scheduler.PASO_CORTO)
        self.assertEqual(nuevo["reps"], 0)
        self.assertEqual(nuevo["lapses"], 2)

    def test_fallar_nunca_sube_la_estabilidad(self):
        for estabilidad in (0.5, 5.0, 50.0, 300.0):
            st = {"stability": estabilidad, "difficulty": 5.0, "reps": 5, "lapses": 0,
                  "last": time.time() - estabilidad * DIA}
            with self.subTest(estabilidad=estabilidad):
                self.assertLessEqual(scheduler.review(st, AGAIN)["stability"], estabilidad)

    def test_acertar_siempre_sube_la_estabilidad(self):
        st = {"stability": 10.0, "difficulty": 5.0, "reps": 3, "lapses": 0,
              "last": time.time() - 10 * DIA}
        for nota in (HARD, GOOD, EASY):
            with self.subTest(nota=nota):
                self.assertGreater(scheduler.review(st, nota)["stability"], 10.0)

    def test_el_intervalo_es_la_estabilidad_a_la_retencion_de_fabrica(self):
        # Es la definición de estabilidad: los días hasta caer al 90 %.
        st = {"stability": 40.0, "difficulty": 5.0, "reps": 4, "lapses": 0,
              "last": time.time() - 40 * DIA}
        nuevo = scheduler.review(st, GOOD, retencion=0.90)
        self.assertAlmostEqual(nuevo["interval"], nuevo["stability"], delta=0.001)

    def test_pedir_mas_retencion_acorta_los_intervalos(self):
        st = {"stability": 40.0, "difficulty": 5.0, "reps": 4, "lapses": 0,
              "last": time.time() - 40 * DIA}
        exigente = scheduler.review(st, GOOD, retencion=0.95)["interval"]
        relajado = scheduler.review(st, GOOD, retencion=0.85)["interval"]
        self.assertLess(exigente, relajado)

    def test_repasar_algo_que_ya_te_sabias_aporta_menos(self):
        # El corazón del método: cuanto más a punto de olvidarlo, más crece.
        base = {"stability": 30.0, "difficulty": 5.0, "reps": 4, "lapses": 0}
        pronto = scheduler.review({**base, "last": time.time() - 1 * DIA}, GOOD)
        tarde = scheduler.review({**base, "last": time.time() - 30 * DIA}, GOOD)
        self.assertGreater(tarde["stability"], pronto["stability"])

    def test_una_tarjeta_dificil_crece_mas_despacio_que_una_facil(self):
        blanda = {"stability": 20.0, "difficulty": 2.0, "reps": 4, "lapses": 0,
                  "last": time.time() - 20 * DIA}
        dura = {**blanda, "difficulty": 9.0}
        self.assertGreater(scheduler.review(blanda, GOOD)["stability"],
                           scheduler.review(dura, GOOD)["stability"])

    def test_repasarla_el_mismo_dia_consolida_poco(self):
        st = {"stability": 10.0, "difficulty": 5.0, "reps": 3, "lapses": 0,
              "last": time.time() - 600}          # hace diez minutos
        nuevo = scheduler.review(st, GOOD)
        self.assertGreater(nuevo["stability"], 10.0)
        self.assertLess(nuevo["stability"], 20.0)

    def test_la_dificultad_se_queda_siempre_entre_uno_y_diez(self):
        st = {}
        for nota in [AGAIN] * 30 + [EASY] * 30 + [AGAIN, EASY] * 15:
            st = scheduler.review(st, nota)
            self.assertGreaterEqual(st["difficulty"], 1.0)
            self.assertLessEqual(st["difficulty"], 10.0)

    def test_el_intervalo_tiene_techo_de_un_ano(self):
        st = {"stability": 5000.0, "difficulty": 2.0, "reps": 20, "lapses": 0,
              "last": time.time() - 400 * DIA}
        self.assertLessEqual(scheduler.review(st, EASY)["interval"],
                             scheduler.MAX_INTERVALO)

    def test_el_ruido_solo_afecta_a_intervalos_de_dias(self):
        # Un fallo vuelve en diez minutos exactos, sin ruido.
        st = scheduler.review({"stability": 30.0, "difficulty": 5.0, "reps": 5,
                               "last": time.time() - 30 * DIA}, AGAIN)
        self.assertAlmostEqual(st["due"] - st["last"], scheduler.PASO_CORTO * DIA,
                               delta=0.01)
        # De un día en adelante el vencimiento se mueve como mucho un 5 %.
        largo = {"stability": 100.0, "difficulty": 5.0, "reps": 9, "lapses": 0,
                 "last": time.time() - 100 * DIA}
        for _ in range(40):
            nuevo = scheduler.review(largo, GOOD)
            desvio = (nuevo["due"] - nuevo["last"]) / DIA / nuevo["interval"]
            self.assertGreaterEqual(desvio, 0.95)
            self.assertLessEqual(desvio, 1.05)

    def test_sigue_guardando_una_facilidad_equivalente(self):
        # Las vistas antiguas leen `ease`; se deriva de la dificultad.
        facil = scheduler.review({"stability": 10.0, "difficulty": 1.0, "reps": 3,
                                  "last": time.time() - 10 * DIA}, GOOD)
        dificil = scheduler.review({"stability": 10.0, "difficulty": 10.0, "reps": 3,
                                    "last": time.time() - 10 * DIA}, GOOD)
        self.assertGreater(facil["ease"], dificil["ease"])
        for st in (facil, dificil):
            self.assertGreaterEqual(st["ease"], 1.3)
            self.assertLessEqual(st["ease"], 3.0)

    def test_un_estado_con_valores_nulos_no_revienta(self):
        st = scheduler.review({"ease": None, "interval": None, "reps": None,
                               "lapses": None, "stability": None,
                               "difficulty": None}, GOOD)
        self.assertEqual(st["reps"], 1)
        self.assertGreater(st["stability"], 0)

    def test_una_nota_fuera_de_rango_se_acota(self):
        self.assertEqual(scheduler.review({}, 99)["stability"],
                         scheduler.review({}, EASY)["stability"])
        self.assertEqual(scheduler.review({}, -5)["stability"],
                         scheduler.review({}, AGAIN)["stability"])

    def test_ahora_permite_fechar_el_repaso_en_el_pasado(self):
        cuando = time.time() - 100 * DIA
        st = scheduler.review({}, GOOD, ahora=cuando)
        self.assertAlmostEqual(st["last"], cuando)
        self.assertAlmostEqual(st["due"], cuando + st["interval"] * DIA,
                               delta=st["interval"] * DIA * 0.06)


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
