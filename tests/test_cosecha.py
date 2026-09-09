"""La cosecha del día. La red se sustituye por respuestas grabadas."""
import time

from appstudy import bandeja, cosecha, db, fuentes, ia, selector
from tests.apoyo import BaseTemporal

TEXTO = ("La ley de Ohm relaciona la tensión, la corriente y la resistencia de un "
         "circuito eléctrico sencillo, y permite calcular cualquiera de las tres "
         "magnitudes conocidas las otras dos. " * 30)


class CosechaTest(BaseTemporal):
    def setUp(self):
        super().setUp()
        db.upsert_deck(self.con, "electricidad", "Electricidad", "⚡", "#3584e4", 1,
                       ["Básico", "Intermedio", "Avanzado"])
        self.con.commit()
        self.buscados = []
        self.parchear()

    def parchear(self, fallan=(), texto=TEXTO):
        def buscar(provider, consulta="", config=None):
            self.buscados.append(provider)
            if provider in fallan:
                raise fuentes.FuenteError("caída simulada")
            return [fuentes.documento(provider,
                                      f"https://es.wikipedia.org/wiki/{provider}",
                                      "Ley de Ohm")]

        def previsualizar(item):
            return {**item, "text": texto, "author": "Colaboradores",
                    "license": "CC BY-SA 4.0"}

        for nombre, valor in (("buscar", buscar), ("previsualizar", previsualizar)):
            original = getattr(fuentes, nombre)
            setattr(fuentes, nombre, valor)
            self.addCleanup(lambda n=nombre, o=original: setattr(fuentes, n, o))
        self.sin_ia()

    def sin_ia(self):
        original = ia.generar_desde_texto

        def revienta(*a, **k):
            raise ia.IAError("no hay modelo descargado")
        ia.generar_desde_texto = revienta
        self.addCleanup(lambda: setattr(ia, "generar_desde_texto", original))

    def con_ia(self, tarjetas):
        ia.guardar(self.con, activa=True)      # de fábrica está apagada
        ia.generar_desde_texto = lambda *a, **k: list(tarjetas)

    def test_con_la_ia_apagada_no_se_piden_tarjetas(self):
        pedidas = []
        ia.guardar(self.con, activa=False)
        ia.generar_desde_texto = lambda *a, **k: pedidas.append(1) or []
        cosecha.cosechar(self.con)
        self.assertEqual(pedidas, [])

    # ------------------------------------------------------------- cosechar

    def test_una_cosecha_deja_algo_en_la_bandeja(self):
        self.assertTrue(cosecha.cosechar(self.con))
        self.assertEqual(bandeja.cuantas(self.con), 1)

    def test_sin_ia_el_capitulo_llega_igual_y_sin_tarjetas(self):
        cosecha.cosechar(self.con)
        fila = bandeja.pendientes(self.con)[0]
        self.assertEqual(fila["cards"], "[]")
        self.assertTrue(fila["text"])

    def test_con_ia_llegan_las_tarjetas_propuestas(self):
        self.con_ia([{"front": "¿Qué relaciona la ley de Ohm?",
                      "back": "La tensión, la corriente y la resistencia"}])
        cosecha.cosechar(self.con)
        import json
        cards = json.loads(bandeja.pendientes(self.con)[0]["cards"])
        self.assertEqual(len(cards), 1)

    def test_una_tarjeta_inventada_por_la_ia_no_pasa(self):
        self.con_ia([{"front": "¿Cuántos satélites tiene Júpiter?",
                      "back": "Noventa y cinco satélites confirmados por astrónomos"}])
        cosecha.cosechar(self.con)
        import json
        self.assertEqual(json.loads(bandeja.pendientes(self.con)[0]["cards"]), [])

    def test_una_fuente_caida_no_tumba_a_las_demas(self):
        caida = selector.plan(self.con)["fuentes"][0]["id"]
        self.parchear(fallan={caida})
        self.assertTrue(cosecha.cosechar(self.con))
        self.assertIn(caida, db.get_meta(self.con, "cosecha_rechazos", ""))

    def test_si_nada_pasa_los_filtros_no_se_guarda_nada(self):
        self.parchear(texto="Muy corto.")
        self.assertEqual(cosecha.cosechar(self.con), [])
        self.assertEqual(bandeja.cuantas(self.con), 0)
        self.assertIn("corto", db.get_meta(self.con, "cosecha_rechazos", ""))

    def test_sin_mazos_no_revienta(self):
        self.con.execute("DELETE FROM decks")
        self.con.commit()
        self.assertEqual(cosecha.cosechar(self.con), [])

    # --------------------------------------------------------- auto_si_toca

    def test_auto_si_toca_cosecha_una_vez_al_dia(self):
        self.assertTrue(cosecha.auto_si_toca(self.con))
        self.assertFalse(cosecha.auto_si_toca(self.con))
        db.set_meta(self.con, "cosecha_last", time.time() - cosecha.CADA - 1)
        self.assertTrue(cosecha.auto_si_toca(self.con))

    def test_apagada_en_ajustes_no_cosecha(self):
        db.set_meta(self.con, "cosecha_auto", "0")
        self.assertFalse(cosecha.auto_si_toca(self.con))
        self.assertEqual(bandeja.cuantas(self.con), 0)

    def test_un_fallo_se_anota_y_no_se_propaga(self):
        def revienta(*a, **k):
            raise fuentes.FuenteError("sin conexión")
        fuentes.buscar = revienta
        self.assertFalse(cosecha.auto_si_toca(self.con))
        self.assertIn("conexión", db.get_meta(self.con, "cosecha_error", ""))

    def test_un_fallo_no_marca_el_dia_como_cosechado(self):
        def revienta(*a, **k):
            raise RuntimeError("algo raro")
        fuentes.buscar = revienta
        cosecha.auto_si_toca(self.con)
        self.assertFalse(float(db.get_meta(self.con, "cosecha_last", 0) or 0))

    def test_una_cosecha_buena_borra_el_error_anterior(self):
        db.set_meta(self.con, "cosecha_error", "sin conexión")
        cosecha.auto_si_toca(self.con)
        self.assertEqual(db.get_meta(self.con, "cosecha_error", ""), "")


class ArranqueTest(BaseTemporal):
    def test_el_trabajo_de_arranque_usa_su_propia_conexion(self):
        """Una conexión de SQLite pertenece a su hilo: el trabajo abre la suya."""
        import inspect
        from appstudy import app
        fuente = inspect.getsource(app.AppStudy.cosechar_en_silencio)
        self.assertIn("db.connect()", fuente)
        self.assertIn("largo=True", fuente)

    def test_el_arranque_llama_a_la_cosecha(self):
        import inspect
        from appstudy import app
        self.assertIn("cosechar_en_silencio", inspect.getsource(app.AppStudy.do_startup))
