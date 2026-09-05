from types import SimpleNamespace
from unittest.mock import Mock, patch

import gi

gi.require_version("Pango", "1.0")
from gi.repository import Pango  # noqa: E402

from appstudy import db, historial, pet, popup, scheduler  # noqa: E402
from tests.apoyo import BaseTemporal


class HistorialTest(BaseTemporal):
    def test_recuerda_sin_responder_y_persiste_entre_conexiones(self):
        cid = self.tarjeta(self.mazo(), "¿Qué mostró Bit?")
        historial.registrar(self.con, cid)
        otra = db.connect()
        self.addCleanup(otra.close)
        self.assertEqual(historial.recientes(otra)[0]["id"], cid)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM log").fetchone()[0], 0)

    def test_ordena_por_aparicion_sin_duplicados_aunque_cambie_el_reloj(self):
        did = self.mazo()
        uno, dos = (self.tarjeta(did, t) for t in ("Primera", "Segunda"))
        with patch("appstudy.historial.time.time", return_value=100):
            historial.registrar(self.con, uno)
            historial.registrar(self.con, dos)
        with patch("appstudy.historial.time.time", return_value=50):
            historial.registrar(self.con, uno)
        self.assertEqual([c["id"] for c in historial.recientes(self.con)], [uno, dos])

    def test_conserva_solo_las_ultimas_cien(self):
        did = self.mazo()
        ids = [self.tarjeta(did, str(i)) for i in range(105)]
        for cid in ids:
            historial.registrar(self.con, cid)
        self.assertEqual([c["id"] for c in historial.recientes(self.con)], ids[-100:][::-1])

    def test_busca_sin_tildes_por_texto_respuesta_o_mazo(self):
        cid = self.tarjeta(self.mazo(), "Energía eléctrica", "Tensión alterna")
        historial.registrar(self.con, cid)
        for consulta in ("energia", "TENSION", "linux", "electrica alterna"):
            self.assertEqual(historial.recientes(self.con, consulta)[0]["id"], cid)
        self.assertEqual(historial.recientes(self.con, "inexistente"), [])

    def test_consultar_no_cambia_progreso_ni_orden(self):
        did = self.mazo()
        cid = self.tarjeta(did, "Uno")
        scheduler.apply_review(self.con, cid, scheduler.GOOD)
        historial.registrar(self.con, cid)
        antes = db.card_by_id(self.con, cid)
        log = [tuple(r) for r in self.con.execute("SELECT * FROM log")]
        vistos = [tuple(r) for r in self.con.execute("SELECT * FROM card_history")]
        for card in historial.recientes(self.con):
            historial.contenido(card)
        self.assertEqual(db.card_by_id(self.con, cid), antes)
        self.assertEqual([tuple(r) for r in self.con.execute("SELECT * FROM log")], log)
        self.assertEqual([tuple(r) for r in self.con.execute("SELECT * FROM card_history")], vistos)

    def test_borrar_tarjeta_elimina_su_entrada(self):
        cid = self.tarjeta(self.mazo(), "Temporal")
        historial.registrar(self.con, cid)
        self.con.execute("DELETE FROM cards WHERE id=?", (cid,))
        self.con.commit()
        self.assertEqual(historial.recientes(self.con), [])
        historial.registrar(self.con, cid)
        self.assertEqual(historial.recientes(self.con), [])

    def test_base_anterior_sin_historial_funciona(self):
        self.assertEqual(historial.recientes(self.con), [])
        self.con.execute("DROP TABLE card_history")
        self.assertEqual(historial.recientes(self.con), [])

    def test_recupera_repasos_anteriores_solo_en_la_primera_apertura(self):
        did = self.mazo()
        uno, dos = (self.tarjeta(did, t) for t in ("Antes", "Después"))
        self.repasar(uno, scheduler.GOOD, cuando=100)
        self.repasar(dos, scheduler.GOOD, cuando=200)
        self.assertEqual([c["id"] for c in historial.recientes(self.con)], [dos, uno])
        historial.registrar(self.con, uno)
        self.assertEqual([c["id"] for c in historial.recientes(self.con)], [uno, dos])

    def test_contenido_revela_quiz_y_huecos(self):
        card = {"kind": "quiz", "front": "Capital", "back": "Explicación",
                "choices": '["León", "Managua"]', "answer": 1}
        self.assertEqual(historial.contenido(card)[1],
                         "Respuesta correcta: Managua\n\nExplicación")
        card.update(kind="cloze", front="La capital es {{Managua::ciudad}}")
        self.assertEqual(historial.contenido(card)[0], "La capital es Managua")

    def test_subtitulo_escapa_mazos_con_signos_de_markup(self):
        cid = self.tarjeta(db.upsert_deck(self.con, "html", "Mazo <de> prueba", "📘",
                                          "#3584e4", 1, ["Básico"]), "Una tarjeta",
                           key="html")
        historial.registrar(self.con, cid)
        sub = historial.subtitulo(historial.recientes(self.con)[0])
        self.assertIn("Mazo &lt;de&gt; prueba", sub)
        Pango.parse_markup(f"<markup>{sub}</markup>", -1, "\x00")

    def test_bit_registra_al_mostrar_y_no_al_redibujar(self):
        cid = self.tarjeta(self.mazo(), "Una tarjeta")
        ventana = SimpleNamespace(con=self.con, card=None, render_card=Mock())
        pet.PetWindow.teach(ventana)
        self.assertEqual(historial.recientes(self.con)[0]["id"], cid)
        ventana.render_card.assert_called_once()

    def test_popup_registra_antes_de_responder(self):
        cid = self.tarjeta(self.mazo(), "Una tarjeta")
        ventana = SimpleNamespace(con=self.con, card=None, deck_key=None, level=None,
                                  tags=None, es_cloze=lambda: False, render=Mock())
        popup.PopupWindow.load_card(ventana)
        self.assertEqual(historial.recientes(self.con)[0]["id"], cid)
        self.assertFalse(ventana.revealed)

    def test_historial_detiene_el_reto_antes_de_abrirse(self):
        llamadas = Mock()
        ventana = SimpleNamespace(con=self.con, close_bubble=llamadas.cerrar)
        with patch("appstudy.pet.historial.abrir", llamadas.abrir):
            pet.PetWindow.abrir_historial(ventana)
        self.assertEqual([c[0] for c in llamadas.mock_calls], ["cerrar", "abrir"])
