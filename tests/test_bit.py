import unittest

from appstudy import db, ia, pet, scheduler
from tests.apoyo import BaseTemporal


class EnfadoEstudioTest(BaseTemporal):
    def test_repasar_quita_enfado(self):
        ahora = 200000
        self.assertTrue(pet.enfado_por_estudio(self.con, 5, ahora=ahora))
        cid = self.tarjeta(self.mazo(), "Una pregunta")
        self.con.execute("INSERT INTO log(card_id,rating,ts,ms) VALUES(?,?,?,?)",
                         (cid, 2, ahora - 60, 1000))
        self.assertFalse(pet.enfado_por_estudio(self.con, 5, ahora=ahora))
        self.assertTrue(pet.enfado_por_estudio(self.con, 5, ahora=ahora + 86400))

    def test_lectura_con_avance_cuenta_y_solo_abrir_no(self):
        ahora = 200000
        did = self.mazo()
        cid, _ = db.upsert_chapter(self.con, did, "linux", {"title": "Lectura"})
        self.con.execute("UPDATE reading SET leido=0,avance=0,ts=? WHERE chapter_id=?",
                         (ahora - 60, cid))
        self.assertTrue(pet.enfado_por_estudio(self.con, 5, ahora=ahora))
        self.con.execute("UPDATE reading SET avance=.5 WHERE chapter_id=?", (cid,))
        self.assertFalse(pet.enfado_por_estudio(self.con, 5, ahora=ahora))

    def test_libro_con_tiempo_registrado_cuenta(self):
        self.con.execute("INSERT INTO books(ruta,titulo,minutos,abierto) VALUES('prueba.pdf','Libro',20,199940)")
        self.assertFalse(pet.enfado_por_estudio(self.con, 5, ahora=200000))
        self.assertTrue(pet.enfado_por_estudio(self.con, 5, ahora=300000))


class EvolucionBitTest(unittest.TestCase):
    def test_enfado_solo_tras_un_dia_con_trabajo_pendiente(self):
        self.assertFalse(pet.debe_enfadarse(23.9, 5))
        self.assertTrue(pet.debe_enfadarse(24, 5))
        self.assertFalse(pet.debe_enfadarse(72, 0))
        self.assertFalse(pet.debe_enfadarse(72, 5, dormida=True))
        self.assertTrue(pet.debe_enfadarse(4.5, 5, hoy=0))
        self.assertFalse(pet.debe_enfadarse(4.5, 5, hoy=10))

    def test_empieza_como_companero(self):
        estado = pet.evolucion(0)
        self.assertEqual(estado["nombre"], "Compañero")
        self.assertEqual(estado["siguiente"]["min"], 25)
        self.assertEqual(estado["avance"], 0)

    def test_cambia_en_cada_umbral(self):
        esperados = ((24, "Compañero"), (25, "Curioso"), (100, "Aplicado"),
                     (500, "Sabio"), (1500, "Maestro"))
        for repasos, nombre in esperados:
            self.assertEqual(pet.evolucion(repasos)["nombre"], nombre)

    def test_avance_es_acotado_y_el_maximo_no_tiene_siguiente(self):
        self.assertAlmostEqual(pet.evolucion(50)["avance"], 25 / 75)
        maestro = pet.evolucion(99999)
        self.assertEqual(maestro["avance"], 1)
        self.assertIsNone(maestro["siguiente"])

    def test_accesorios_se_desbloquean_gradualmente(self):
        self.assertEqual([a["key"] for a in pet.accesorios_disponibles(0)], ["ninguno"])
        self.assertEqual([a["key"] for a in pet.accesorios_disponibles(100)],
                         ["ninguno", "panuelo", "gafas"])

    def test_un_accesorio_bloqueado_o_desconocido_no_se_aplica(self):
        self.assertEqual(pet.accesorio_valido("corona", 499), "ninguno")
        self.assertEqual(pet.accesorio_valido("corona", 500), "corona")
        self.assertEqual(pet.accesorio_valido("sombrero", 9999), "ninguno")


class TotalRepasosBitTest(BaseTemporal):
    def test_cuenta_el_trabajo_real(self):
        did = self.mazo()
        cid = self.tarjeta(did, "Una")
        self.assertEqual(pet.total_repasos(self.con), 0)
        scheduler.apply_review(self.con, cid, scheduler.GOOD)
        scheduler.apply_review(self.con, cid, scheduler.HARD)
        self.assertEqual(pet.total_repasos(self.con), 2)


if __name__ == "__main__":
    unittest.main()


class ConversacionHabladaTest(unittest.TestCase):
    """Las decisiones de la charla hablada, sin levantar la ventana de Bit."""

    def despedida(self, texto):
        return pet.PetWindow.es_despedida(texto)

    def test_reconoce_las_despedidas(self):
        for frase in ("adiós", "Adiós", "hasta luego", "ya está", "Gracias Bit", "chao"):
            self.assertTrue(self.despedida(frase), frase)

    def test_no_corta_la_charla_por_una_palabra_suelta(self):
        # "adiós" dentro de una pregunta es materia de estudio, no una despedida
        for frase in ("¿cómo se dice adiós en inglés?", "explícame el para qué",
                      "hasta luego se dice see you later"):
            self.assertFalse(self.despedida(frase), frase)


class RespuestaHabladaTest(unittest.TestCase):
    def test_acorta_por_la_ultima_frase_entera(self):
        largo = ("Primera frase corta. " * 30).strip()
        corto = ia.acortar_para_hablar(largo, maximo=10)
        self.assertTrue(corto.endswith("."))
        self.assertLessEqual(len(corto.split()), 10)

    def test_deja_en_paz_lo_que_ya_es_breve(self):
        breve = "Claro, el repaso espaciado sirve para no olvidar. ¿Seguimos?"
        self.assertEqual(ia.acortar_para_hablar(breve), breve)
        self.assertEqual(ia.acortar_para_hablar(""), "")

    def test_una_parrafada_sin_puntos_se_corta_igual(self):
        sin_puntos = " ".join(["palabra"] * 80)
        corto = ia.acortar_para_hablar(sin_puntos, maximo=12)
        self.assertEqual(len(corto.split()), 12)
        self.assertTrue(corto.endswith("."))


class AnimoTest(unittest.TestCase):
    """Cuándo se pone verde Bit. Antes: casi siempre."""

    @staticmethod
    def totales(**cambios):
        base = {"pendientes": 0, "hoy": 0, "nuevas": 0, "racha": 0, "objetivo": 0}
        return {**base, **cambios}

    def test_una_tarjeta_suelta_no_la_pone_verde(self):
        # Era el fallo: repasar una sola tarjeta la dejaba contenta
        self.assertEqual(pet.animo(self.totales(hoy=1), horas=0.5, energia=0.9), "normal")
        self.assertEqual(pet.animo(self.totales(hoy=9), horas=0.5, energia=0.9), "normal")

    def test_verde_al_llegar_al_minimo_sin_pendientes(self):
        t = self.totales(hoy=pet.MINIMO_FELIZ)
        self.assertEqual(pet.animo(t, horas=0.5, energia=0.9), "feliz")

    def test_con_objetivo_manda_el_objetivo(self):
        t = self.totales(hoy=12, objetivo=30)
        self.assertEqual(pet.animo(t, horas=0.5, energia=0.9), "normal")
        self.assertEqual(pet.animo({**t, "hoy": 30}, horas=0.5, energia=0.9), "feliz")
        # Un objetivo bajo también vale: no se exige el mínimo por encima de él
        t_bajo = self.totales(hoy=5, objetivo=5)
        self.assertEqual(pet.animo(t_bajo, horas=0.5, energia=0.9), "feliz")

    def test_con_repasos_vencidos_no_hay_verde(self):
        t = self.totales(hoy=50, pendientes=7)
        self.assertEqual(pet.animo(t, horas=0.5, energia=0.9), "normal")

    def test_el_verde_no_dura_todo_el_dia(self):
        t = self.totales(hoy=40)
        self.assertEqual(pet.animo(t, horas=0.5, energia=0.9), "feliz")
        self.assertEqual(pet.animo(t, horas=pet.HORAS_ABURRIDO, energia=0.9), "aburrido")
        self.assertEqual(pet.animo(t, horas=pet.HORAS_HAMBRE, energia=0.9), "hambre")
        self.assertEqual(pet.animo(t, horas=pet.HORAS_TRISTE, energia=0.9), "triste")

    def test_dormida_manda_sobre_todo(self):
        t = self.totales(hoy=40)
        self.assertEqual(pet.animo(t, horas=0.5, energia=0.9, dormida=True), "dormido")

    def test_sin_energia_tiene_hambre(self):
        t = self.totales(hoy=2, pendientes=30)
        self.assertEqual(pet.animo(t, horas=1.0, energia=0.2), "hambre")


class ModoEstrictoTest(BaseTemporal):
    """Bit no puede dar por sabido lo que no ha comprobado."""

    def tarjeta_con_respuesta(self):
        return {"back": "Cambia los permisos", "kind": "card"}

    def leccion(self):
        return {"back": "", "kind": "lesson"}

    def test_de_fabrica_viene_encendido(self):
        self.assertTrue(pet.estricto(self.con))

    def test_se_puede_apagar(self):
        db.set_meta(self.con, "modo_estricto", "0")
        self.assertFalse(pet.estricto(self.con))
        db.set_meta(self.con, "modo_estricto", "1")
        self.assertTrue(pet.estricto(self.con))

    def test_apagado_ofrece_los_dos_botones_de_siempre(self):
        acciones = [a for _, a, _ in pet.calificaciones(self.tarjeta_con_respuesta(), False)]
        self.assertEqual(acciones, ["again", "good"])

    def test_encendido_cambia_lo_sabia_por_comprobarlo(self):
        acciones = [a for _, a, _ in pet.calificaciones(self.tarjeta_con_respuesta(), True)]
        self.assertEqual(acciones, ["again", "comprobar"])
        self.assertNotIn("good", acciones)

    def test_una_leccion_no_ofrece_calificar_en_estricto(self):
        self.assertEqual(pet.calificaciones(self.leccion(), True), [])

    def test_una_leccion_si_se_califica_con_el_modo_apagado(self):
        self.assertTrue(pet.calificaciones(self.leccion(), False))

    def test_el_relampago_no_deja_autocalificarse_en_estricto(self):
        self.assertEqual(pet.calificaciones_relampago(True), [])
        self.assertTrue(pet.calificaciones_relampago(False))


class GloboEstrictoUITest(BaseTemporal):
    """Los botones reales del globo, pulsados de verdad."""

    @classmethod
    def setUpClass(cls):
        from gi.repository import Gdk, Gtk
        Gtk.init()
        if Gdk.Display.get_default() is None:
            raise unittest.SkipTest("Requiere pantalla GTK")

    def bit(self, card):
        from types import MethodType
        from unittest.mock import Mock
        from gi.repository import Gtk

        class GloboBit:
            def __init__(self, con, card):
                self.con, self.card = con, card
                self.bubble_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                self.reto = None
                self.reto_timer = None
                self.ultimo_formato = None
                # El formato de enseñanza se sortea; aquí se fija, que lo que se
                # prueba son los botones de calificar, no el dado.
                self.formato_actual = "tarjeta"
                self.shown_at = 0
                self.creature = Mock()
                for nombre in ("clear_bubble", "say", "open_bubble", "refresh_stats",
                               "sonar", "voz_auto_si_toca", "arrancar_cuenta",
                               "celebrar_logro", "celebrar_vuelta", "open_main"):
                    setattr(self, nombre, Mock(return_value=False))
                self.stats = {"horas": 0.0}
                for nombre in ("bubble_header", "pie_leer", "boton_explicar",
                               "boton_chat", "boton_conversar", "cuenta_atras",
                               "enunciado"):
                    setattr(self, nombre, Mock(return_value=Gtk.Label()))
                self.char_width = Mock(return_value=30)

            def __getattr__(self, nombre):
                valor = getattr(pet.PetWindow, nombre)
                # Las propiedades (`nombre`) llegan aquí sin resolver
                return valor.fget(self) if isinstance(valor, property) else \
                    MethodType(valor, self)

        return GloboBit(self.con, card)

    def carta(self, back="Cambia los permisos de un archivo", kind="card"):
        did = self.mazo()
        cid = self.tarjeta(did, "¿Qué hace chmod?", back)
        if kind != "card":
            self.con.execute("UPDATE cards SET kind=? WHERE id=?", (kind, cid))
            self.con.commit()
        # dict, no fila: es lo que devuelve scheduler.next_card en la aplicación
        return dict(self.con.execute("""
            SELECT c.*, d.key AS deck_key, d.name AS deck_name, d.icon AS deck_icon,
                   d.color AS deck_color, d.levels AS deck_levels
              FROM cards c JOIN decks d ON d.id=c.deck_id WHERE c.id=?""",
            (cid,)).fetchone())

    def pulsar(self, bit, etiqueta):
        from gi.repository import Gtk
        hijo = bit.bubble_box.get_first_child()
        while hijo is not None:
            if isinstance(hijo, Gtk.Box):
                b = hijo.get_first_child()
                while b is not None:
                    if isinstance(b, Gtk.Button) and b.get_label() == etiqueta:
                        b.emit("clicked")
                        return True
                    b = b.get_next_sibling()
            elif isinstance(hijo, Gtk.Button) and hijo.get_label() == etiqueta:
                hijo.emit("clicked")
                return True
            hijo = hijo.get_next_sibling()
        return False

    def repasos(self):
        return self.con.execute("SELECT COUNT(*) c FROM log").fetchone()["c"]

    def test_lo_sabia_no_existe_en_estricto(self):
        bit = self.bit(self.carta())
        bit.render_card()
        self.assertFalse(self.pulsar(bit, "Lo sabía"))
        self.assertTrue(self.pulsar(bit, "Compruébamelo"))

    def test_comprobarlo_lanza_un_reto_y_no_apunta_nada_todavia(self):
        bit = self.bit(self.carta())
        bit.render_card()
        self.pulsar(bit, "Compruébamelo")
        self.assertIsNotNone(bit.reto)
        self.assertNotEqual(bit.reto["formato"], "relampago")
        self.assertEqual(self.repasos(), 0, "no se apunta hasta resolver el reto")

    def test_el_reto_es_de_la_misma_tarjeta_que_estabas_leyendo(self):
        carta = self.carta()
        bit = self.bit(carta)
        bit.render_card()
        self.pulsar(bit, "Compruébamelo")
        self.assertEqual(bit.card["id"], carta["id"])

    def test_no_lo_sabia_si_se_apunta_al_momento(self):
        bit = self.bit(self.carta())
        bit.render_card()
        self.pulsar(bit, "No lo sabía")
        self.assertEqual(self.repasos(), 1)

    def test_con_el_modo_apagado_lo_sabia_vuelve_y_apunta(self):
        db.set_meta(self.con, "modo_estricto", "0")
        bit = self.bit(self.carta())
        bit.render_card()
        self.assertTrue(self.pulsar(bit, "Lo sabía"))
        self.assertEqual(self.repasos(), 1)

    def test_una_leccion_no_ofrece_calificar_ni_apunta(self):
        bit = self.bit(self.carta(back="", kind="lesson"))
        bit.render_card()
        self.assertFalse(self.pulsar(bit, "Lo sabía"))
        self.assertFalse(self.pulsar(bit, "No lo sabía"))
        self.assertEqual(self.repasos(), 0)

    def test_el_relampago_no_deja_apuntarse_un_acierto(self):
        bit = self.bit(self.carta())
        bit.reto = {"formato": "relampago", "segundos": 20}
        bit.revelar_relampago()
        self.assertFalse(self.pulsar(bit, "La tenía"))
        self.assertEqual(self.repasos(), 0)


class InterruptorEstrictoTest(BaseTemporal):
    def test_el_ajuste_enciende_y_apaga_el_modo(self):
        from appstudy.main_window import MainWindow
        ventana = MainWindow(None, self.con)
        self.addCleanup(ventana.destroy)
        self.assertTrue(ventana.estricto_switch.get_active(),
                        "de fábrica el modo estricto viene encendido")
        ventana.estricto_switch.set_active(False)
        self.assertFalse(pet.estricto(self.con))
        ventana.estricto_switch.set_active(True)
        self.assertTrue(pet.estricto(self.con))


class RetroalimentacionYCreacionTest(GloboEstrictoUITest):
    def test_sesion_quiz_y_retroalimentacion(self):
        did = self.mazo(name="Redes", key="redes")
        cid1 = self.tarjeta(did, "¿Qué es TCP?", "Protocolo de control de transmisión")
        cid2 = self.tarjeta(did, "¿Qué es UDP?", "Protocolo de datagramas de usuario")
        carta1 = dict(self.con.execute(
            "SELECT c.*, d.key AS deck_key, d.name AS deck_name, d.icon AS deck_icon, d.color AS deck_color, d.levels AS deck_levels FROM cards c JOIN decks d ON d.id=c.deck_id WHERE c.id=?", (cid1,)).fetchone())
        carta2 = dict(self.con.execute(
            "SELECT c.*, d.key AS deck_key, d.name AS deck_name, d.icon AS deck_icon, d.color AS deck_color, d.levels AS deck_levels FROM cards c JOIN decks d ON d.id=c.deck_id WHERE c.id=?", (cid2,)).fetchone())

        bit = self.bit(carta1)
        bit.reto = {"formato": "opciones", "pregunta": "¿Qué es TCP?", "segundos": 10, "correcta": 0, "respuesta": "Protocolo TCP"}

        # Resolver primero con acierto
        bit.resolver(True, elegida="Protocolo TCP")
        self.assertIsNotNone(bit.sesion_quiz)
        self.assertEqual(bit.sesion_quiz["total"], 1)
        self.assertEqual(bit.sesion_quiz["aciertos"], 1)
        self.assertEqual(bit.sesion_quiz["fallos"], 0)

        # Resolver segundo con fallo
        bit.card = carta2
        bit.reto = {"formato": "opciones", "pregunta": "¿Qué es UDP?", "segundos": 10, "correcta": 1, "respuesta": "Protocolo UDP"}
        bit.resolver(False, elegida="Respuesta errónea")
        self.assertEqual(bit.sesion_quiz["total"], 2)
        self.assertEqual(bit.sesion_quiz["aciertos"], 1)
        self.assertEqual(bit.sesion_quiz["fallos"], 1)
        self.assertEqual(len(bit.sesion_quiz["historial"]), 2)

        # Mostrar retroalimentación
        bit.mostrar_retroalimentacion_quiz()
        self.assertGreater(len(bit.bubble_box.observe_children()), 0)

    def test_render_acta_retroalimentacion_examen(self):
        did = self.mazo(name="Ciberseguridad", key="ciberseguridad")
        cid = self.tarjeta(did, "¿Qué es XSS?", "Cross-Site Scripting")

        bit = self.bit(None)

        acta = {
            "nota": 45,
            "aprobadas": 1,
            "total": 2,
            "juicio": "A medias",
            "flojas": [{
                "card_id": cid,
                "front": "¿Qué es XSS?",
                "pregunta": "¿Qué es Cross-Site Scripting?",
                "respuesta": "Un ataque web",
                "falto": "Inyección de scripts maliciosos en el navegador de la víctima",
                "nota": 40,
                "veredicto": "Faltó precisión"
            }]
        }
        bit.render_acta(acta)
        self.assertGreater(len(bit.bubble_box.observe_children()), 0)

    def test_creacion_tema_y_preguntas_en_db(self):
        # Crear tema
        pos = (self.con.execute("SELECT MAX(pos) AS p FROM decks").fetchone()["p"] or 0) + 1
        did = db.upsert_deck(self.con, "biologia", "Biología", "🔬", "#26a269", pos, ["Básico", "Avanzado"])
        self.con.commit()
        deck = self.con.execute("SELECT * FROM decks WHERE id=?", (did,)).fetchone()
        self.assertEqual(deck["name"], "Biología")
        self.assertEqual(deck["icon"], "🔬")

        # Crear tarjeta flashcard
        cid1, es_nueva1 = db.add_card(self.con, did, "biologia", "card", "¿Qué es la mitocondria?",
                                      back="La central energética de la célula")
        self.con.commit()
        self.assertEqual(es_nueva1, 1)

        # Crear pregunta tipo quiz
        choices = ["Mitocondria", "Ribosoma", "Núcleo", "Vacuola"]
        cid2, es_nueva2 = db.add_card(self.con, did, "biologia", "quiz", "¿Dónde se sintetizan las proteínas?",
                                      back="En los ribosomas", choices=choices, answer=1)
        self.con.commit()
        self.assertEqual(es_nueva2, 1)

        c2 = self.con.execute("SELECT * FROM cards WHERE id=?", (cid2,)).fetchone()
        self.assertEqual(c2["kind"], "quiz")
        self.assertEqual(c2["answer"], 1)

    def test_repaso_tarjetas_especificas_flujo(self):
        did = self.mazo(name="Test", key="test")
        cid1 = self.tarjeta(did, "P1", "R1")
        cid2 = self.tarjeta(did, "P2", "R2")

        bit = self.bit(None)

        bit.repasar_tarjetas_especificas([cid1, cid2])
        self.assertEqual(bit.card["id"], cid1)
        self.assertEqual(bit.cola_repaso_especifico, [cid2])
        bit.siguiente_repaso_especifico()
        self.assertEqual(bit.card["id"], cid2)
        self.assertEqual(bit.cola_repaso_especifico, [])
        bit.siguiente_repaso_especifico()
        bit.say.assert_called()

