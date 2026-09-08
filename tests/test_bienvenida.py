"""El asistente de bienvenida: ritmo, prueba de nivel y lo que deja configurado.

Aquí solo se prueba la lógica, que no sabe de GTK: qué objetivo sale de los
minutos que dices tener, qué nivel sugiere la prueba y qué queda escrito en la
base al terminar. La ventana en sí (bienvenida.Asistente) es un armazón de
widgets sobre estas funciones.
"""
import unittest

from appstudy import bienvenida, db, sesiones
from tests.apoyo import BaseTemporal


class TestRitmo(unittest.TestCase):
    """De «tengo quince minutos» a un objetivo y un cupo de nuevas."""

    def test_mas_minutos_piden_mas_de_todo(self):
        corto = bienvenida.ritmo(5)
        largo = bienvenida.ritmo(45)
        self.assertLess(corto["objetivo"], largo["objetivo"])
        self.assertLess(corto["nuevas"], largo["nuevas"])

    def test_el_cupo_de_nuevas_es_una_fraccion_del_objetivo(self):
        # Una tarjeta recién estrenada se lleva varios repasos en sus primeros
        # días: si el cupo igualara al objetivo, la sesión sería toda estreno.
        for minutos in bienvenida.MINUTOS:
            r = bienvenida.ritmo(minutos)
            self.assertLess(r["nuevas"], r["objetivo"])
            self.assertGreaterEqual(r["nuevas"], 1)

    def test_la_media_hora_larga_cae_cerca_del_valor_de_fabrica(self):
        # El tope de fábrica son 15 nuevas al día; media hora larga de estudio
        # debería pedir algo parecido, o los dos números se contradirían.
        self.assertAlmostEqual(bienvenida.ritmo(25)["nuevas"],
                               db.NUEVAS_POR_DIA_DEFECTO, delta=5)

    def test_ningun_minutaje_deja_el_objetivo_en_cero(self):
        # Un objetivo de cero significa «sin objetivo» y apagaría el panel.
        for minutos in (1, 5, 15, 25, 45, 120):
            self.assertGreater(bienvenida.ritmo(minutos)["objetivo"], 0)


class TestPlanDeSesion(unittest.TestCase):
    def test_cada_minutaje_arranca_con_un_plan_existente(self):
        for minutos in bienvenida.MINUTOS:
            self.assertIn(bienvenida.plan_desde_minutos(minutos), sesiones.PLANES)

    def test_elige_el_plan_mas_cercano_en_minutos(self):
        self.assertEqual(bienvenida.plan_desde_minutos(5).minutos, 5)
        self.assertEqual(bienvenida.plan_desde_minutos(15).minutos, 15)
        self.assertEqual(bienvenida.plan_desde_minutos(45).minutos, 25)


class TestNivelSugerido(unittest.TestCase):
    NIVELES = ["Básico", "Intermedio", "Avanzado"]

    def test_fallar_casi_todo_empieza_por_el_principio(self):
        self.assertEqual(bienvenida.nivel_sugerido(1, 8, self.NIVELES), 1)

    def test_la_mitad_bien_empieza_en_medio(self):
        self.assertEqual(bienvenida.nivel_sugerido(4, 8, self.NIVELES), 2)

    def test_acertar_casi_todo_salta_al_ultimo(self):
        self.assertEqual(bienvenida.nivel_sugerido(8, 8, self.NIVELES), 3)

    def test_sin_prueba_no_se_presume_nada(self):
        self.assertEqual(bienvenida.nivel_sugerido(0, 0, self.NIVELES), 1)

    def test_nunca_se_pasa_de_los_niveles_que_tiene_el_mazo(self):
        for aciertos in range(9):
            nivel = bienvenida.nivel_sugerido(aciertos, 8, ["A2", "B1", "B2", "C1"])
            self.assertIn(nivel, (1, 2, 3, 4))
        self.assertEqual(bienvenida.nivel_sugerido(8, 8, ["Único"]), 1)


class TestPreguntasDePrueba(BaseTemporal):
    def mazo_con_niveles(self, por_nivel=6):
        deck = self.mazo()
        for nivel in (1, 2, 3):
            for i in range(por_nivel):
                self.tarjeta(deck, f"nivel {nivel} pregunta {i}", level=nivel)
        return deck

    def test_trae_las_que_le_pides(self):
        self.mazo_con_niveles()
        preguntas = bienvenida.preguntas_de_prueba(self.con, "linux", 8)
        self.assertEqual(len(preguntas), 8)

    def test_reparte_entre_todos_los_niveles(self):
        self.mazo_con_niveles()
        niveles = {p["level"] for p in bienvenida.preguntas_de_prueba(self.con, "linux", 6)}
        self.assertEqual(niveles, {1, 2, 3})

    def test_un_mazo_corto_devuelve_lo_que_tiene_sin_repetir(self):
        deck = self.mazo()
        for i in range(3):
            self.tarjeta(deck, f"solo tres {i}")
        preguntas = bienvenida.preguntas_de_prueba(self.con, "linux", 8)
        self.assertEqual(len(preguntas), 3)
        self.assertEqual(len({p["id"] for p in preguntas}), 3)

    def test_un_mazo_vacio_no_revienta(self):
        self.mazo()
        self.assertEqual(bienvenida.preguntas_de_prueba(self.con, "linux", 8), [])

    def test_solo_saca_tarjetas_del_mazo_pedido(self):
        self.mazo_con_niveles()
        otro = db.upsert_deck(self.con, "ingles", "Inglés", "🇬🇧", "#f00", 2,
                              ["A2", "B1"])
        self.tarjeta(otro, "una de inglés", key="ingles")
        preguntas = bienvenida.preguntas_de_prueba(self.con, "linux", 8)
        self.assertTrue(all("nivel" in p["front"] for p in preguntas))


class TestAplicar(BaseTemporal):
    def tres_mazos(self):
        for pos, (key, nombre) in enumerate(
                (("linux", "Linux"), ("ingles", "Inglés"), ("datos", "Datos"))):
            db.upsert_deck(self.con, key, nombre, "📘", "#3584e4", pos,
                           ["Básico", "Intermedio", "Avanzado"])

    def eleccion(self, **cambios):
        base = {"temas": ["linux"], "principal": "linux", "minutos": 15, "nivel": 2}
        return {**base, **cambios}

    def activos(self):
        return {r["key"] for r in self.con.execute(
            "SELECT key FROM decks WHERE enabled=1")}

    def test_deja_activos_solo_los_temas_elegidos(self):
        self.tres_mazos()
        bienvenida.aplicar(self.con, self.eleccion(temas=["linux", "datos"]))
        self.assertEqual(self.activos(), {"linux", "datos"})

    def test_guarda_el_objetivo_y_el_cupo_que_salen_de_los_minutos(self):
        self.tres_mazos()
        bienvenida.aplicar(self.con, self.eleccion(minutos=25))
        r = bienvenida.ritmo(25)
        self.assertEqual(db.objetivo_diario(self.con), r["objetivo"])
        self.assertEqual(db.nuevas_por_dia(self.con), r["nuevas"])

    def test_marca_la_bienvenida_como_hecha(self):
        self.tres_mazos()
        self.assertFalse(bienvenida.ya_vista(self.con))
        bienvenida.aplicar(self.con, self.eleccion())
        self.assertTrue(bienvenida.ya_vista(self.con))

    def test_recuerda_el_tema_y_el_nivel_para_la_primera_sesion(self):
        self.tres_mazos()
        bienvenida.aplicar(self.con, self.eleccion(principal="ingles", nivel=3))
        self.assertEqual(bienvenida.arranque(self.con), ("ingles", 3))

    def test_sin_ningun_tema_marcado_no_apaga_la_aplicacion_entera(self):
        # Quedarse sin mazos activos deja el panel en cero y sin nada que
        # estudiar: si no eligió ninguno, se quedan todos como estaban.
        self.tres_mazos()
        bienvenida.aplicar(self.con, self.eleccion(temas=[], principal=""))
        self.assertEqual(self.activos(), {"linux", "ingles", "datos"})

    def test_saltarse_el_asistente_no_toca_los_ajustes(self):
        self.tres_mazos()
        db.set_objetivo_diario(self.con, 40)
        bienvenida.saltar(self.con)
        self.assertTrue(bienvenida.ya_vista(self.con))
        self.assertEqual(db.objetivo_diario(self.con), 40)
        self.assertEqual(self.activos(), {"linux", "ingles", "datos"})

    def test_repetirlo_vuelve_a_dejar_lo_ultimo_elegido(self):
        self.tres_mazos()
        bienvenida.aplicar(self.con, self.eleccion(temas=["linux"], principal="linux"))
        bienvenida.aplicar(self.con, self.eleccion(temas=["ingles"], principal="ingles",
                                                   minutos=5, nivel=1))
        self.assertEqual(self.activos(), {"ingles"})
        self.assertEqual(bienvenida.arranque(self.con), ("ingles", 1))
        self.assertEqual(db.objetivo_diario(self.con), bienvenida.ritmo(5)["objetivo"])


if __name__ == "__main__":
    unittest.main()
