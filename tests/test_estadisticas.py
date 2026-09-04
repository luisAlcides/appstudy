"""Lo que dice el historial: las series que alimentan la pestaña de progreso.

Aquí se comprueba sobre todo que los recuentos caigan en el día que les toca
—que es donde se cuelan los errores de zona horaria— y que las medias no se
midan sobre repasos que no significan nada, como la primera vez que ves una
tarjeta.
"""
import time
import unittest

from appstudy import db, estadisticas as est, scheduler
from tests.apoyo import BaseTemporal

AGAIN, HARD, GOOD, EASY = (scheduler.AGAIN, scheduler.HARD,
                           scheduler.GOOD, scheduler.EASY)
DIA = 86400.0


class TestMapaCalor(BaseTemporal):
    def test_sin_repasos_sale_un_ano_vacio(self):
        m = est.mapa_calor(self.con)
        self.assertEqual(m["total"], 0)
        self.assertEqual(m["maximo"], 0)
        self.assertIsNone(m["mejor"])
        self.assertGreater(len(m["semanas"]), 50)

    def test_todas_las_semanas_tienen_siete_dias(self):
        # Es lo que hace que el dibujo salga cuadrado.
        semanas = est.mapa_calor(self.con)["semanas"]
        for s in semanas[:-1]:
            self.assertEqual(len(s), 7)

    def test_la_primera_casilla_de_cada_semana_es_lunes(self):
        for semana in est.mapa_calor(self.con)["semanas"]:
            ts = semana[0]["ts"]
            self.assertEqual(time.localtime(ts).tm_wday, 0)

    def test_cuenta_cada_repaso_en_su_dia(self):
        deck = self.mazo()
        cid = self.tarjeta(deck, "una cualquiera")
        self.repasar(cid, GOOD)
        self.repasar(cid, GOOD)
        self.repasar(cid, GOOD, cuando=time.time() - 3 * DIA)
        m = est.mapa_calor(self.con)
        por_dia = {c["dia"]: c["n"] for s in m["semanas"] for c in s}
        hoy = time.strftime("%Y-%m-%d", time.localtime())
        hace_tres = time.strftime("%Y-%m-%d", time.localtime(time.time() - 3 * DIA))
        self.assertEqual(por_dia[hoy], 2)
        self.assertEqual(por_dia[hace_tres], 1)
        self.assertEqual(m["total"], 3)
        self.assertEqual(m["dias_activos"], 2)
        self.assertEqual(m["maximo"], 2)

    def test_marca_el_dia_de_hoy_una_sola_vez(self):
        celdas = [c for s in est.mapa_calor(self.con)["semanas"] for c in s]
        self.assertEqual(sum(1 for c in celdas if c["hoy"]), 1)

    def test_los_dias_futuros_de_la_ultima_semana_van_marcados(self):
        celdas = [c for s in est.mapa_calor(self.con)["semanas"] for c in s]
        hoy = next(i for i, c in enumerate(celdas) if c["hoy"])
        for c in celdas[:hoy + 1]:
            self.assertFalse(c["futuro"])
        for c in celdas[hoy + 1:]:
            self.assertTrue(c["futuro"])

    def test_lo_anterior_al_periodo_no_entra(self):
        cid = self.tarjeta(self.mazo(), "vieja")
        self.repasar(cid, GOOD, cuando=time.time() - 500 * DIA)
        self.assertEqual(est.mapa_calor(self.con, dias=30)["total"], 0)

    def test_el_mejor_dia_es_el_de_mas_repasos(self):
        deck = self.mazo()
        cid = self.tarjeta(deck, "una")
        for _ in range(4):
            self.repasar(cid, GOOD, cuando=time.time() - 2 * DIA)
        self.repasar(cid, GOOD)
        self.assertEqual(est.mapa_calor(self.con)["mejor"]["n"], 4)


class TestRetencion(BaseTemporal):
    def preparar(self, notas, deck=None, key="linux"):
        deck = deck or self.mazo(key, key.title())
        cid = self.tarjeta(deck, f"tarjeta de {key}", key=key)
        base = time.time() - 30 * DIA
        for i, nota in enumerate(notas):
            self.repasar(cid, nota, cuando=base + i * DIA)
        return deck, cid

    def test_la_primera_vez_no_cuenta_para_la_media(self):
        # Una tarjeta nueva no se «recuerda»: meterla ensucia la medida.
        self.preparar([AGAIN])
        self.assertEqual(est.retencion_global(self.con)["repasos"], 0)

    def test_a_partir_del_segundo_repaso_si_cuenta(self):
        self.preparar([GOOD, GOOD, AGAIN, GOOD])
        g = est.retencion_global(self.con)
        self.assertEqual(g["repasos"], 3)
        self.assertEqual(g["aciertos"], 2)
        self.assertAlmostEqual(g["retencion"], 2 / 3)

    def test_todo_acertado_da_el_cien_por_cien(self):
        self.preparar([GOOD] * 5)
        self.assertAlmostEqual(est.retencion_global(self.con)["retencion"], 1.0)

    def test_todo_fallado_da_cero(self):
        self.preparar([AGAIN] * 5)
        self.assertAlmostEqual(est.retencion_global(self.con)["retencion"], 0.0)

    def test_dificil_cuenta_como_acierto(self):
        # Te costó, pero te acordaste: para la retención es un acierto.
        self.preparar([GOOD, HARD])
        self.assertAlmostEqual(est.retencion_global(self.con)["retencion"], 1.0)

    def test_separa_los_mazos(self):
        self.preparar([GOOD, GOOD, GOOD], key="linux")
        self.preparar([GOOD, AGAIN, AGAIN], key="ingles")
        por_mazo = {m["key"]: m for m in est.retencion_por_mazo(self.con)}
        self.assertAlmostEqual(por_mazo["linux"]["retencion"], 1.0)
        self.assertAlmostEqual(por_mazo["ingles"]["retencion"], 0.0)

    def test_un_mazo_sin_repasos_medibles_no_da_numero(self):
        self.preparar([GOOD])          # solo el primero, que no cuenta
        mazos = est.retencion_por_mazo(self.con)
        self.assertEqual(mazos, [])

    def test_trae_la_retencion_que_tienes_pedida(self):
        db.set_meta(self.con, "retencion", 0.95)
        self.assertAlmostEqual(est.retencion_global(self.con)["objetivo"], 0.95)

    def test_lo_muy_antiguo_queda_fuera_de_la_ventana(self):
        deck = self.mazo()
        cid = self.tarjeta(deck, "vieja")
        base = time.time() - 300 * DIA
        for i in range(4):
            self.repasar(cid, GOOD, cuando=base + i * DIA)
        self.assertEqual(est.retencion_global(self.con, dias=90)["repasos"], 0)
        self.assertGreater(est.retencion_global(self.con, dias=365)["repasos"], 0)


class TestTemasDebiles(BaseTemporal):
    def test_prioriza_la_etiqueta_con_mas_fallos(self):
        deck = self.mazo()
        redes = self.tarjeta(deck, "redes", key="redes")
        shell = self.tarjeta(deck, "shell", key="shell")
        self.con.execute("UPDATE cards SET tags='redes, tcp' WHERE id=?", (redes,))
        self.con.execute("UPDATE cards SET tags='shell' WHERE id=?", (shell,))
        self.con.commit()
        for nota in (AGAIN, AGAIN, HARD):
            self.repasar(redes, nota)
        for nota in (HARD, GOOD, GOOD):
            self.repasar(shell, nota)
        temas = est.temas_debiles(self.con)
        self.assertEqual(temas[0]["tema"], "redes")
        self.assertEqual(temas[0]["fallos"], 2)
        self.assertEqual(temas[0]["tags"], "redes")

    def test_sin_etiqueta_usa_el_mazo(self):
        deck = self.mazo("ingles", "Inglés")
        cid = self.tarjeta(deck, "verbs", key="verbs")
        self.repasar(cid, AGAIN)
        tema = est.temas_debiles(self.con)[0]
        self.assertEqual(tema["tema"], "Inglés")
        self.assertEqual(tema["deck_key"], "ingles")

    def test_no_muestra_temas_sin_dificultades(self):
        cid = self.tarjeta(self.mazo(), "fácil")
        for _ in range(3):
            self.repasar(cid, GOOD)
        self.assertEqual(est.temas_debiles(self.con), [])

    def test_limita_el_historial_consultado(self):
        deck = self.mazo()
        viejo = self.tarjeta(deck, "viejo", key="viejo")
        nuevo = self.tarjeta(deck, "nuevo", key="nuevo")
        self.con.execute("UPDATE cards SET tags='viejo' WHERE id=?", (viejo,))
        self.con.execute("UPDATE cards SET tags='nuevo' WHERE id=?", (nuevo,))
        self.con.commit()
        self.repasar(viejo, AGAIN, cuando=time.time() - 10)
        self.repasar(nuevo, AGAIN)
        temas = est.temas_debiles(self.con, max_repasos=1)
        self.assertEqual([t["tema"] for t in temas], ["nuevo"])


class TestCurvaVencimientos(BaseTemporal):
    def vence_en(self, card_id, dias):
        self.con.execute("UPDATE state SET reps=3, due=? WHERE card_id=?",
                         (time.time() + dias * DIA, card_id))
        self.con.commit()

    def test_devuelve_un_dia_por_cada_dia_pedido(self):
        self.assertEqual(len(est.curva_vencimientos(self.con, 30)), 30)
        self.assertEqual(len(est.curva_vencimientos(self.con, 7)), 7)

    def test_cada_tarjeta_cae_en_su_dia(self):
        deck = self.mazo()
        self.vence_en(self.tarjeta(deck, "en tres días"), 3)
        self.vence_en(self.tarjeta(deck, "en diez días"), 10)
        curva = est.curva_vencimientos(self.con, 30)
        self.assertEqual(curva[3]["n"], 1)
        self.assertEqual(curva[10]["n"], 1)
        self.assertEqual(sum(d["n"] for d in curva), 2)

    def test_lo_vencido_se_apunta_aparte_en_el_primer_dia(self):
        deck = self.mazo()
        self.vence_en(self.tarjeta(deck, "atrasada"), -5)
        curva = est.curva_vencimientos(self.con, 30)
        self.assertEqual(curva[0]["atrasadas"], 1)
        self.assertEqual(curva[0]["total"], 1)
        self.assertEqual(sum(d["atrasadas"] for d in curva[1:]), 0)

    def test_lo_que_vence_mas_alla_del_periodo_no_aparece(self):
        deck = self.mazo()
        self.vence_en(self.tarjeta(deck, "muy lejana"), 200)
        self.assertEqual(sum(d["n"] for d in est.curva_vencimientos(self.con, 30)), 0)

    def test_las_sin_estrenar_no_vencen(self):
        self.tarjeta(self.mazo(), "sin estrenar")
        curva = est.curva_vencimientos(self.con, 30)
        self.assertEqual(sum(d["total"] for d in curva), 0)

    def test_las_apartadas_no_cuentan_como_carga(self):
        deck = self.mazo()
        cid = self.tarjeta(deck, "apartada")
        self.vence_en(cid, 3)
        self.con.execute("UPDATE state SET leech=1 WHERE card_id=?", (cid,))
        self.con.commit()
        self.assertEqual(sum(d["n"] for d in est.curva_vencimientos(self.con)), 0)

    def test_un_mazo_apagado_no_cuenta(self):
        deck = self.mazo()
        self.vence_en(self.tarjeta(deck, "de mazo apagado"), 3)
        self.con.execute("UPDATE decks SET enabled=0")
        self.con.commit()
        self.assertEqual(sum(d["n"] for d in est.curva_vencimientos(self.con)), 0)


class TestTiempos(BaseTemporal):
    def repaso_de(self, card_id, ms, cuando=None):
        scheduler.apply_review(self.con, card_id, GOOD, elapsed_ms=ms)
        if cuando:
            self.con.execute("UPDATE log SET ts=? WHERE id=(SELECT MAX(id) FROM log)",
                             (cuando,))
            self.con.commit()

    def test_usa_la_mediana_y_no_la_media(self):
        # Un despiste con el popup abierto no debe mover la cifra.
        deck = self.mazo()
        cid = self.tarjeta(deck, "una")
        for ms in (3000, 3200, 3400, 3600, 110000):
            self.repaso_de(cid, ms)
        self.assertEqual(est.tiempo_por_nivel(self.con)[0]["mediana_ms"], 3400)

    def test_descarta_lo_imposiblemente_rapido_y_lo_absurdamente_lento(self):
        deck = self.mazo()
        cid = self.tarjeta(deck, "una")
        for ms in (50, 5000, 999999):
            self.repaso_de(cid, ms)
        salida = est.tiempo_por_nivel(self.con)
        self.assertEqual(salida[0]["n"], 1)
        self.assertEqual(salida[0]["mediana_ms"], 5000)

    def test_separa_por_nivel(self):
        deck = self.mazo()
        facil = self.tarjeta(deck, "básica", level=1)
        dura = self.tarjeta(deck, "avanzada", level=3)
        for _ in range(3):
            self.repaso_de(facil, 2000)
            self.repaso_de(dura, 9000)
        por_nivel = {d["level"]: d for d in est.tiempo_por_nivel(self.con)}
        self.assertEqual(por_nivel[1]["mediana_ms"], 2000)
        self.assertEqual(por_nivel[3]["mediana_ms"], 9000)

    def test_sin_datos_no_devuelve_filas(self):
        self.assertEqual(est.tiempo_por_nivel(self.con), [])

    def test_con_mazo_usa_los_nombres_de_nivel_de_verdad(self):
        deck = self.mazo("ingles", "Inglés", niveles=("A2", "B1", "B2", "C1"))
        cid = self.tarjeta(deck, "one", key="ingles", level=4)
        self.repaso_de(cid, 5000)
        salida = est.tiempo_por_nivel_de_mazo(self.con, "ingles")
        self.assertEqual(salida[0]["nombre"], "C1")

    def test_un_mazo_que_no_existe_no_revienta(self):
        self.assertEqual(est.tiempo_por_nivel_de_mazo(self.con, "fantasma"), [])


class TestRepartoYMemoria(BaseTemporal):
    def test_el_reparto_suma_todas_las_tarjetas(self):
        deck = self.mazo()
        for i in range(5):
            self.tarjeta(deck, f"t{i}")
        reparto = {d["clave"]: d["n"] for d in est.reparto_madurez(self.con)}
        self.assertEqual(reparto["nuevas"], 5)

    def test_una_tarjeta_estudiada_deja_de_ser_nueva(self):
        cid = self.tarjeta(self.mazo(), "una")
        scheduler.apply_review(self.con, cid, GOOD)
        reparto = {d["clave"]: d["n"] for d in est.reparto_madurez(self.con)}
        self.assertEqual(reparto["nuevas"], 0)
        self.assertEqual(reparto["jovenes"], 1)

    def test_las_de_intervalo_largo_son_maduras(self):
        cid = self.tarjeta(self.mazo(), "una")
        scheduler.apply_review(self.con, cid, GOOD)
        self.con.execute("UPDATE state SET interval=40 WHERE card_id=?", (cid,))
        self.con.commit()
        reparto = {d["clave"]: d["n"] for d in est.reparto_madurez(self.con)}
        self.assertEqual(reparto["maduras"], 1)

    def test_la_memoria_es_la_suma_de_estabilidades(self):
        deck = self.mazo()
        for i in range(3):
            cid = self.tarjeta(deck, f"t{i}")
            scheduler.apply_review(self.con, cid, GOOD)
            self.con.execute("UPDATE state SET stability=10 WHERE card_id=?", (cid,))
        self.con.commit()
        self.assertAlmostEqual(est.memoria_total(self.con)["dias"], 30.0)
        self.assertAlmostEqual(est.memoria_total(self.con)["media"], 10.0)

    def test_sin_nada_estudiado_la_memoria_es_cero(self):
        self.tarjeta(self.mazo(), "sin estrenar")
        self.assertEqual(est.memoria_total(self.con)["dias"], 0.0)
        self.assertIsNone(est.probabilidad_hoy(self.con))

    def test_la_probabilidad_baja_conforme_pasan_los_dias(self):
        cid = self.tarjeta(self.mazo(), "una")
        scheduler.apply_review(self.con, cid, GOOD)
        self.con.execute("UPDATE state SET stability=10, last=? WHERE card_id=?",
                         (time.time(), cid))
        self.con.commit()
        recien = est.probabilidad_hoy(self.con)
        self.con.execute("UPDATE state SET last=? WHERE card_id=?",
                         (time.time() - 30 * DIA, cid))
        self.con.commit()
        self.assertLess(est.probabilidad_hoy(self.con), recien)

    def test_a_los_s_dias_la_probabilidad_es_del_noventa_por_ciento(self):
        cid = self.tarjeta(self.mazo(), "una")
        scheduler.apply_review(self.con, cid, GOOD)
        self.con.execute("UPDATE state SET stability=20, last=? WHERE card_id=?",
                         (time.time() - 20 * DIA, cid))
        self.con.commit()
        self.assertAlmostEqual(est.probabilidad_hoy(self.con), 0.90, places=4)


class TestResumenSemanal(BaseTemporal):
    def test_sin_nada_lo_dice_sin_numeros_raros(self):
        r = est.resumen_semanal(self.con)
        self.assertEqual(r["total"], 0)
        self.assertEqual(r["activos"], 0)
        self.assertIsNone(r["retencion"])
        self.assertIsNone(r["mejor"])
        self.assertIn("no hemos estudiado", est.contar_semana(self.con))

    def test_la_serie_trae_siete_dias_terminando_hoy(self):
        serie = est.resumen_semanal(self.con)["serie"]
        self.assertEqual(len(serie), 7)
        self.assertEqual(serie[-1]["dia"],
                         time.strftime("%Y-%m-%d", time.localtime()))

    def test_los_dias_llevan_su_nombre_en_castellano(self):
        for d in est.resumen_semanal(self.con)["serie"]:
            self.assertIn(d["nombre"], est.DIAS_ES)

    def test_cuenta_los_dias_activos_y_el_mejor(self):
        deck = self.mazo()
        cid = self.tarjeta(deck, "una")
        for _ in range(3):
            self.repasar(cid, GOOD, cuando=time.time() - 2 * DIA)
        self.repasar(cid, GOOD)
        r = est.resumen_semanal(self.con)
        self.assertEqual(r["total"], 4)
        self.assertEqual(r["activos"], 2)
        self.assertEqual(r["mejor"]["n"], 3)

    def test_compara_con_la_semana_anterior(self):
        deck = self.mazo()
        cid = self.tarjeta(deck, "una")
        for _ in range(2):
            self.repasar(cid, GOOD, cuando=time.time() - 9 * DIA)
        for _ in range(4):
            self.repasar(cid, GOOD)
        r = est.resumen_semanal(self.con)
        self.assertEqual(r["anterior"], 2)
        self.assertAlmostEqual(r["cambio"], 1.0)          # el doble
        self.assertIn("más que la semana pasada", est.contar_semana(self.con))

    def test_el_texto_nombra_dias_tarjetas_y_acierto(self):
        deck = self.mazo()
        cid = self.tarjeta(deck, "una")
        for nota in (GOOD, GOOD, AGAIN, GOOD):
            self.repasar(cid, nota)
        texto = est.contar_semana(self.con)
        self.assertIn("1 día", texto)
        self.assertIn("4 tarjetas", texto)
        self.assertIn("75 %", texto)

    def test_el_texto_menciona_la_racha_solo_si_es_larga(self):
        deck = self.mazo()
        cid = self.tarjeta(deck, "una")
        self.repasar(cid, GOOD)
        self.assertNotIn("días seguidos", est.contar_semana(self.con))
        for atras in range(1, 5):
            self.repasar(cid, GOOD, cuando=time.time() - atras * DIA)
        self.assertIn("días seguidos", est.contar_semana(self.con))

    def test_el_texto_cuenta_los_capitulos_leidos(self):
        deck = self.mazo()
        cid = self.tarjeta(deck, "una")
        self.repasar(cid, GOOD)
        capitulo, _ = db.upsert_chapter(self.con, deck, "linux",
                                        {"title": "Uno", "body": []})
        db.mark_read(self.con, capitulo)
        self.assertIn("capítulo leído", est.contar_semana(self.con))

    def test_el_texto_no_lleva_markup_roto(self):
        import gi
        gi.require_version("Pango", "1.0")
        from gi.repository import Pango
        deck = self.mazo()
        cid = self.tarjeta(deck, "una")
        for _ in range(3):
            self.repasar(cid, GOOD)
        Pango.parse_markup(est.contar_semana(self.con), -1, "\x00")


if __name__ == "__main__":
    unittest.main()
