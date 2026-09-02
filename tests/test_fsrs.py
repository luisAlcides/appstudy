"""El modelo de memoria: que las fórmulas hagan lo que dicen que hacen.

Varias de estas pruebas comprueban propiedades, no números concretos: que la
probabilidad de acordarte baje siempre con los días, que fallar nunca suba la
estabilidad, que pedir más retención acorte los intervalos. Son las que
sobreviven a un cambio de pesos, y las que de verdad protegen el método.
"""
import math
import time
import unittest

from appstudy import fsrs

AGAIN, HARD, GOOD, EASY = fsrs.OTRA_VEZ, fsrs.DIFICIL, fsrs.BIEN, fsrs.FACIL


class TestCurvaDeOlvido(unittest.TestCase):
    def test_a_los_cero_dias_te_acuerdas_seguro(self):
        self.assertAlmostEqual(fsrs.recuperabilidad(0, 10), 1.0)

    def test_a_los_s_dias_la_probabilidad_es_exactamente_el_noventa_por_ciento(self):
        # No es casualidad: es la definición de estabilidad, y de ahí sale FACTOR.
        for s in (0.5, 1, 7, 30, 365):
            with self.subTest(estabilidad=s):
                self.assertAlmostEqual(fsrs.recuperabilidad(s, s), 0.90, places=9)

    def test_la_probabilidad_baja_siempre_con_los_dias(self):
        anterior = 1.1
        for dias in range(0, 400, 7):
            ahora = fsrs.recuperabilidad(dias, 30)
            self.assertLess(ahora, anterior)
            anterior = ahora

    def test_mas_estabilidad_es_mas_probabilidad_al_mismo_plazo(self):
        self.assertGreater(fsrs.recuperabilidad(30, 100), fsrs.recuperabilidad(30, 10))

    def test_la_probabilidad_se_queda_entre_cero_y_uno(self):
        for dias in (0, 1, 1000, 100000):
            r = fsrs.recuperabilidad(dias, 5)
            self.assertGreater(r, 0.0)
            self.assertLessEqual(r, 1.0)

    def test_sin_estabilidad_no_hay_recuerdo(self):
        self.assertEqual(fsrs.recuperabilidad(1, 0), 0.0)


class TestIntervalo(unittest.TestCase):
    def test_a_la_retencion_de_fabrica_el_intervalo_es_la_estabilidad(self):
        for s in (1, 10, 200):
            self.assertAlmostEqual(fsrs.intervalo(s, 0.9), s, places=9)

    def test_pedir_mas_retencion_acorta(self):
        self.assertLess(fsrs.intervalo(100, 0.95), fsrs.intervalo(100, 0.90))
        self.assertLess(fsrs.intervalo(100, 0.90), fsrs.intervalo(100, 0.80))

    def test_el_intervalo_devuelto_da_la_retencion_pedida(self):
        # La vuelta entera: intervalo y recuperabilidad son inversas.
        for retencion in (0.80, 0.85, 0.90, 0.95):
            with self.subTest(retencion=retencion):
                dias = fsrs.intervalo(50, retencion)
                self.assertAlmostEqual(fsrs.recuperabilidad(dias, 50), retencion,
                                       places=9)

    def test_una_retencion_absurda_se_acota(self):
        self.assertEqual(fsrs.intervalo(10, 0.5), fsrs.intervalo(10, 0.70))
        self.assertEqual(fsrs.intervalo(10, 1.5), fsrs.intervalo(10, 0.99))


class TestEstadoInicial(unittest.TestCase):
    def test_mejor_nota_es_mas_estabilidad(self):
        valores = [fsrs.estabilidad_inicial(n) for n in (AGAIN, HARD, GOOD, EASY)]
        self.assertEqual(valores, sorted(valores))

    def test_mejor_nota_es_menos_dificultad(self):
        valores = [fsrs.dificultad_inicial(n) for n in (AGAIN, HARD, GOOD, EASY)]
        self.assertEqual(valores, sorted(valores, reverse=True))

    def test_la_dificultad_inicial_cabe_en_la_escala(self):
        for n in (AGAIN, HARD, GOOD, EASY):
            d = fsrs.dificultad_inicial(n)
            self.assertGreaterEqual(d, fsrs.D_MIN)
            self.assertLessEqual(d, fsrs.D_MAX)


class TestDificultad(unittest.TestCase):
    def test_fallar_la_sube_y_acertar_facil_la_baja(self):
        self.assertGreater(fsrs.siguiente_dificultad(5.0, AGAIN), 5.0)
        self.assertLess(fsrs.siguiente_dificultad(5.0, EASY), 5.0)

    def test_bien_la_deja_casi_donde_estaba(self):
        self.assertAlmostEqual(fsrs.siguiente_dificultad(5.0, GOOD), 5.0, delta=0.05)

    def test_nunca_se_sale_de_la_escala(self):
        for partida in (1.0, 5.0, 10.0):
            for nota in (AGAIN, HARD, GOOD, EASY):
                d = fsrs.siguiente_dificultad(partida, nota)
                with self.subTest(partida=partida, nota=nota):
                    self.assertGreaterEqual(d, fsrs.D_MIN)
                    self.assertLessEqual(d, fsrs.D_MAX)

    def test_una_tarjeta_ya_dificil_empeora_mas_despacio(self):
        # El amortiguado evita que unos fallos la claven en 10 para siempre.
        subida_media = fsrs.siguiente_dificultad(5.0, AGAIN) - 5.0
        subida_alta = fsrs.siguiente_dificultad(9.0, AGAIN) - 9.0
        self.assertLess(subida_alta, subida_media)

    def test_fallar_muchas_veces_no_la_deja_clavada_en_diez(self):
        d = 5.0
        for _ in range(50):
            d = fsrs.siguiente_dificultad(d, AGAIN)
        self.assertLessEqual(d, fsrs.D_MAX)
        # Y con aciertos vuelve a bajar: la reversión a la media funciona
        for _ in range(50):
            d = fsrs.siguiente_dificultad(d, EASY)
        self.assertLess(d, 5.0)


class TestEstabilidad(unittest.TestCase):
    def test_acertar_siempre_la_sube(self):
        for s in (0.5, 5.0, 100.0, 1000.0):
            r = fsrs.recuperabilidad(s, s)
            for nota in (HARD, GOOD, EASY):
                with self.subTest(estabilidad=s, nota=nota):
                    self.assertGreater(fsrs.estabilidad_tras_acierto(5.0, s, r, nota), s)

    def test_facil_sube_mas_que_bien_y_bien_mas_que_dificil(self):
        s, r = 20.0, fsrs.recuperabilidad(20, 20)
        valores = [fsrs.estabilidad_tras_acierto(5.0, s, r, n) for n in (HARD, GOOD, EASY)]
        self.assertEqual(valores, sorted(valores))

    def test_fallar_nunca_la_sube(self):
        for s in (0.5, 5.0, 100.0, 1000.0):
            r = fsrs.recuperabilidad(s, s)
            with self.subTest(estabilidad=s):
                self.assertLessEqual(fsrs.estabilidad_tras_fallo(5.0, s, r), s)

    def test_repasar_tarde_aporta_mas_que_repasar_pronto(self):
        s = 30.0
        pronto = fsrs.estabilidad_tras_acierto(5.0, s, fsrs.recuperabilidad(1, s), GOOD)
        tarde = fsrs.estabilidad_tras_acierto(5.0, s, fsrs.recuperabilidad(60, s), GOOD)
        self.assertGreater(tarde, pronto)

    def test_una_tarjeta_facil_crece_mas_que_una_dificil(self):
        s, r = 20.0, fsrs.recuperabilidad(20, 20)
        self.assertGreater(fsrs.estabilidad_tras_acierto(1.0, s, r, GOOD),
                           fsrs.estabilidad_tras_acierto(10.0, s, r, GOOD))

    def test_lo_que_ya_es_muy_estable_crece_proporcionalmente_menos(self):
        # Rendimientos decrecientes: si no, dos repasos bastarían para años.
        def factor(s):
            return fsrs.estabilidad_tras_acierto(5.0, s, fsrs.recuperabilidad(s, s),
                                                 GOOD) / s
        self.assertGreater(factor(2.0), factor(200.0))

    def test_el_mismo_dia_sube_poco_y_fallar_baja(self):
        self.assertGreater(fsrs.estabilidad_mismo_dia(10.0, GOOD), 10.0)
        self.assertLess(fsrs.estabilidad_mismo_dia(10.0, AGAIN), 10.0)

    def test_la_estabilidad_nunca_se_sale_de_los_limites(self):
        s = 1.0
        for _ in range(200):
            s = fsrs.estabilidad_tras_acierto(1.0, s, fsrs.recuperabilidad(s, s), EASY)
            self.assertLessEqual(s, fsrs.S_MAX)
        for _ in range(200):
            s = fsrs.estabilidad_tras_fallo(10.0, s, fsrs.recuperabilidad(s, s))
            self.assertGreaterEqual(s, fsrs.S_MIN)


class TestSimulacion(unittest.TestCase):
    """Una tarjeta a lo largo del tiempo: que la curva tenga sentido."""

    def simular(self, notas, w=fsrs.W_POR_DEFECTO):
        s = d = None
        intervalos = []
        for nota in notas:
            if s is None:
                s, d = fsrs.estabilidad_inicial(nota, w), fsrs.dificultad_inicial(nota, w)
            else:
                dias = intervalos[-1]
                r = fsrs.recuperabilidad(dias, s)
                d = fsrs.siguiente_dificultad(d, nota, w)
                s = (fsrs.estabilidad_tras_fallo(d, s, r, w) if nota == AGAIN
                     else fsrs.estabilidad_tras_acierto(d, s, r, nota, w))
            intervalos.append(fsrs.intervalo(s, 0.9))
        return intervalos

    def test_acertando_siempre_los_intervalos_crecen(self):
        intervalos = self.simular([GOOD] * 8)
        self.assertEqual(intervalos, sorted(intervalos))
        self.assertGreater(intervalos[-1], 300)

    def test_fallar_por_el_camino_recorta_de_verdad(self):
        limpio = self.simular([GOOD] * 6)
        con_fallo = self.simular([GOOD, GOOD, AGAIN, GOOD, GOOD, GOOD])
        self.assertLess(con_fallo[-1], limpio[-1])

    def test_fsrs_pide_menos_repasos_que_sm2_para_llegar_igual_de_lejos(self):
        # La afirmación que justifica el cambio: con las mismas notas, FSRS
        # llega a un año en menos repasos que la multiplicación por 2.5 de SM-2.
        def repasos_hasta(objetivo, siguiente, arranque):
            valor, n = arranque, 0
            while valor < objetivo and n < 100:
                valor = siguiente(valor)
                n += 1
            return n

        sm2 = repasos_hasta(365, lambda i: i * 2.5, 1.0)
        intervalos = self.simular([GOOD] * 40)
        fsrs_n = next(i for i, v in enumerate(intervalos, 1) if v >= 365)
        self.assertLess(fsrs_n, sm2)


class TestCalibrar(unittest.TestCase):
    def sintetico(self, tarjetas=60, repasos=12, semilla=7):
        """Historiales inventados pero verosímiles, para poder calibrar."""
        import random
        rnd = random.Random(semilla)
        salida = []
        for _ in range(tarjetas):
            ts = time.time() - 400 * 86400
            historial, s = [], None
            for _ in range(repasos):
                nota = rnd.choices([AGAIN, HARD, GOOD, EASY], [1, 2, 6, 2])[0]
                historial.append((ts, nota))
                s = (fsrs.estabilidad_inicial(nota) if s is None
                     else max(1.0, s * (0.5 if nota == AGAIN else 2.0)))
                ts += max(0.5, s) * 86400 * rnd.uniform(0.7, 1.2)
            salida.append(historial)
        return salida

    def test_la_perdida_es_finita_y_positiva(self):
        p = fsrs._perdida(self.sintetico(), fsrs.W_POR_DEFECTO)
        self.assertTrue(math.isfinite(p))
        self.assertGreater(p, 0)

    def test_calibrar_nunca_empeora_el_punto_de_partida(self):
        # Es la garantía que hace seguro ofrecerlo: en el peor caso no cambia nada.
        _, antes, despues = fsrs.calibrar(self.sintetico(), vueltas=2)
        self.assertLessEqual(despues, antes)

    def test_calibrar_devuelve_los_diecinueve_pesos_dentro_de_sus_limites(self):
        pesos, _, _ = fsrs.calibrar(self.sintetico(tarjetas=20), vueltas=1)
        self.assertEqual(len(pesos), len(fsrs.W_POR_DEFECTO))
        for peso, (bajo, alto) in zip(pesos, fsrs.LIMITES):
            self.assertGreaterEqual(peso, bajo)
            self.assertLessEqual(peso, alto)

    def test_los_pesos_calibrados_siguen_dando_formulas_usables(self):
        pesos, _, _ = fsrs.calibrar(self.sintetico(tarjetas=20), vueltas=1)
        s = fsrs.estabilidad_inicial(GOOD, pesos)
        d = fsrs.dificultad_inicial(GOOD, pesos)
        self.assertGreater(s, 0)
        self.assertGreaterEqual(d, fsrs.D_MIN)
        self.assertGreater(fsrs.estabilidad_tras_acierto(d, s, 0.9, GOOD, pesos), s)

    def test_sin_historial_no_se_inventa_nada(self):
        pesos, antes, despues = fsrs.calibrar([], vueltas=1)
        self.assertEqual(pesos, fsrs.W_POR_DEFECTO)
        self.assertEqual(antes, despues)

    def test_avisa_del_avance_si_se_lo_pides(self):
        vistos = []
        fsrs.calibrar(self.sintetico(tarjetas=10), vueltas=2,
                      progreso=lambda frac, perdida: vistos.append(frac))
        self.assertEqual(vistos, [0.5, 1.0])


if __name__ == "__main__":
    unittest.main()
