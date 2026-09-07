import unittest
from tests.apoyo import BaseTemporal
from appstudy import voz


class TestVoz(BaseTemporal):

    def test_limpiar_para_voz(self):
        # HTML y markdown
        t = "<b>Hola</b>, esto es una *prueba* con `código` y # título."
        self.assertEqual(voz.limpiar_para_voz(t), "Hola, esto es una prueba con código y título.")

        # Cloze
        cloze = "La capital de Francia es {{c1::París}}."
        self.assertEqual(voz.limpiar_para_voz(cloze), "La capital de Francia es París.")

        # Cloze con pista
        cloze_pista = "El agua hierve a {{c1::100 °C::temperatura}}."
        self.assertEqual(voz.limpiar_para_voz(cloze_pista), "El agua hierve a 100 °C.")

        # Emojis y URLs
        complejo = "🧠 Mira este enlace: https://example.com/test ¡Genial! ✨"
        self.assertEqual(voz.limpiar_para_voz(complejo), "Mira este enlace: enlace ¡Genial!")

    def test_duracion_estimada(self):
        self.assertEqual(voz.duracion_estimada(""), 0.0)
        d_corta = voz.duracion_estimada("Hola Bit")
        self.assertGreater(d_corta, 1.0)

        # A mayor velocidad, menor duración
        d_rapida = voz.duracion_estimada("Una frase bastante larga con muchas palabras para comprobar", velocidad=50)
        d_lenta = voz.duracion_estimada("Una frase bastante larga con muchas palabras para comprobar", velocidad=-50)
        self.assertLess(d_rapida, d_lenta)

    def test_config_y_guardar(self):
        cfg = voz.config(self.con)
        self.assertTrue(cfg["activo"])
        self.assertTrue(cfg["auto"])
        self.assertEqual(cfg["volumen"], 100)
        self.assertEqual(cfg["velocidad"], 0)
        self.assertEqual(cfg["tono"], 0)

        voz.guardar(self.con, activo=False, auto=False, volumen=80, velocidad=10, tono=5)
        cfg2 = voz.config(self.con)
        self.assertFalse(cfg2["activo"])
        self.assertFalse(cfg2["auto"])
        self.assertEqual(cfg2["volumen"], 80)
        self.assertEqual(cfg2["velocidad"], 10)
        self.assertEqual(cfg2["tono"], 5)

    def test_tiene_motor_neuronal(self):
        self.assertTrue(voz.tiene_motor_neuronal())
        self.assertTrue(voz.tiene_motor_neuronal("es"))
        self.assertTrue(voz.tiene_motor_neuronal("en"))

    def test_es_tarjeta_ingles_deck(self):
        card_en = {"deck_key": "ingles", "deck_name": "Inglés", "front": "Present Simple"}
        self.assertTrue(voz.es_tarjeta_ingles(card_en))
        self.assertEqual(voz.detectar_idioma(card_en), "en")

        card_es = {"deck_key": "automotriz", "deck_name": "Mecánica Automotriz", "front": "Alternador"}
        self.assertFalse(voz.es_tarjeta_ingles(card_es))
        self.assertEqual(voz.detectar_idioma(card_es), "es")

    def test_es_tarjeta_ingles_texto(self):
        self.assertTrue(voz.es_tarjeta_ingles(None, "Choose the correct sentence for this question"))
        self.assertTrue(voz.es_tarjeta_ingles(None, "She doesn't work on Sundays"))
        self.assertFalse(voz.es_tarjeta_ingles(None, "Esta es una oración explicativa en español"))

    def test_es_tarjeta_ingles_explicacion_espanol(self):
        # Si la IA da una explicación larga en español de una tarjeta de inglés, debe leerse en español
        card_en = {"deck_key": "ingles", "deck_name": "Inglés"}
        texto_es = "En esta lección vamos a estudiar cómo y cuándo se utiliza el presente simple con ejemplos prácticos."
        self.assertFalse(voz.es_tarjeta_ingles(card_en, texto_es))
        self.assertEqual(voz.detectar_idioma(card_en, texto_es), "es")

    def test_limpiar_conserva_pausas_de_lista(self):
        # Cada línea es una frase: sin viñetas y con punto para que haya pausa
        texto = "Pasos del arranque:\n- Girar la llave\n- Soltar al encender"
        self.assertEqual(voz.limpiar_para_voz(texto),
                         "Pasos del arranque: Girar la llave. Soltar al encender")
        # La puntuación repetida no alarga las pausas artificialmente
        self.assertEqual(voz.limpiar_para_voz("¿Seguro??? Sí..."), "¿Seguro? Sí.")

    def test_preparar_prosodia(self):
        es = voz.preparar_prosodia("El motor rinde 90% p.ej. a 3000 rpm")
        self.assertIn("por ciento", es)
        self.assertIn("por ejemplo", es)
        self.assertTrue(es.endswith("."))

        en = voz.preparar_prosodia("Water is 100% pure, e.g. rain", idioma="en")
        self.assertIn("percent", en)
        self.assertIn("for example", en)

        # No se añade punto si ya termina en signo de cierre
        self.assertEqual(voz.preparar_prosodia("¡Genial!"), "¡Genial!")
        self.assertEqual(voz.preparar_prosodia(""), "")

    def test_modelo_para_prefiere_alta_calidad(self):
        import tempfile
        from pathlib import Path
        tmp = Path(tempfile.mkdtemp())
        anterior, cache = voz.PIPER_DIR, dict(voz._cache_modelos)
        try:
            voz.PIPER_DIR = tmp
            voz._cache_modelos.clear()
            (tmp / "es_ES-davefx-medium.onnx").touch()
            (tmp / "es_MX-claude-high.onnx").touch()
            self.assertEqual(voz.modelo_para("es").name, "es_MX-claude-high.onnx")

            # Una voz desconocida vale si es del idioma pedido
            voz._cache_modelos.clear()
            (tmp / "en_GB-alba-medium.onnx").touch()
            self.assertEqual(voz.modelo_para("en").name, "en_GB-alba-medium.onnx")

            # Sin modelos del idioma no hay motor neuronal
            voz._cache_modelos.clear()
            for f in tmp.glob("*.onnx"):
                f.unlink()
            self.assertIsNone(voz.modelo_para("en"))
        finally:
            voz.PIPER_DIR = anterior
            voz._cache_modelos.clear()
            voz._cache_modelos.update(cache)

    def test_troceado_kokoro(self):
        from appstudy import tts_kokoro
        # El primer trozo se corta corto para que la voz arranque enseguida
        texto = ("Primera frase corta. " + "Segunda frase bastante más larga que la primera. " * 4)
        bloques = list(tts_kokoro.trozos(texto))
        self.assertGreater(len(bloques), 1)
        self.assertLessEqual(len(bloques[0]), tts_kokoro.PRIMER_TROZO)
        for bloque in bloques[1:]:
            self.assertLessEqual(len(bloque), tts_kokoro.MAX_CARACTERES)
        # No se pierde ni se duplica texto
        self.assertEqual(" ".join(bloques).split(), texto.split())
        self.assertEqual(list(tts_kokoro.trozos("")), [])

    def test_motor_actual(self):
        self.assertIn(voz.motor_actual(), ("kokoro", "piper", "spd-say", ""))
        self.assertEqual(voz.config(self.con)["motor"], voz.motor_actual())

    def test_genero_de_la_voz(self):
        # Kokoro lo dice en el nombre; Piper necesita la tabla
        self.assertEqual(voz.genero_kokoro("af_heart"), "f")
        self.assertEqual(voz.genero_kokoro("em_santa"), "m")
        self.assertEqual(voz.genero_kokoro("ef_dora"), "f")
        for raro in ("", "x", "santa", "abc_def"):
            self.assertEqual(voz.genero_kokoro(raro), "")
        self.assertEqual(voz.GENERO_PIPER["es_ES-sharvard-medium"], "f")
        self.assertEqual(voz.GENERO_PIPER["es_ES-davefx-medium"], "m")
        self.assertIn(voz.genero_voz("es"), ("f", "m", ""))
        # La cara va con la voz de cada frase: una tarjeta de inglés la lee la
        # voz inglesa, y la cara tiene que ser la de esa voz, no la del ajuste
        card_en = {"deck_key": "ingles", "deck_name": "Inglés"}
        idioma = voz.detectar_idioma(card_en, "Choose the correct sentence")
        self.assertEqual(idioma, "en")
        self.assertEqual(voz.genero_voz(idioma), voz.genero_voz("en"))
        self.assertEqual(voz.config(self.con)["genero"], voz.genero_voz("es"))

    def test_hablar_inactivo_devuelve_cero(self):
        cfg = {"activo": False}
        dur = voz.hablar("Hola mundo", cfg)
        self.assertEqual(dur, 0.0)


if __name__ == "__main__":
    unittest.main()
