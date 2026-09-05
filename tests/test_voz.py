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

    def test_hablar_inactivo_devuelve_cero(self):
        cfg = {"activo": False}
        dur = voz.hablar("Hola mundo", cfg)
        self.assertEqual(dur, 0.0)


if __name__ == "__main__":
    unittest.main()
