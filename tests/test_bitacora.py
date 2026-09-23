"""La bitácora del taller: cada equipo que llega se vuelve algo que aprender.

Lo que se protege: que la nota se guarde antes que nada (aunque la IA falle o
tarde), que el caso quede como registro con sus tarjetas, que las tarjetas
vuelvan a su caso como fuente, que salgan antes que las nuevas de fábrica y que
Ctrl+K encuentre cada visita de un equipo.
"""
import json
import time
import unittest
from unittest import mock

from appstudy import ausencia, bitacora, buscador, db, ia, scheduler
from tests.apoyo import BaseTemporal

PROPUESTAS = [
    {"front": "¿Por qué falla el sello de vástago de un cilindro hidráulico?",
     "back": "Por rayas en el vástago, contaminación o temperatura excesiva del aceite."},
    {"front": "¿Cómo distingues una fuga interna de una externa en un cilindro?",
     "back": "La externa se ve; la interna se nota porque el cilindro deriva bajo carga."},
]


class TestEquipo(unittest.TestCase):
    def test_reconoce_marca_y_modelo(self):
        self.assertEqual(bitacora.equipo_de("CAT 320D, fuga en el cilindro del brazo"),
                         "CAT 320D")
        self.assertEqual(bitacora.equipo_de("llegó la komatsu pc200-8 con humo blanco"),
                         "Komatsu PC200-8")
        self.assertEqual(bitacora.equipo_de("Volquete Volvo FMX recalentando"), "Volvo FMX")

    def test_una_palabra_corriente_no_es_un_modelo(self):
        self.assertEqual(bitacora.equipo_de("Toyota Hilux, falla el alternador"),
                         "Toyota Hilux")
        self.assertEqual(bitacora.equipo_de("la cat con fuga en el brazo"), "CAT")
        self.assertEqual(bitacora.equipo_de("komatsu excavadora sin fuerza"), "Komatsu")

    def test_sin_marca_usa_el_primer_trozo(self):
        self.assertEqual(bitacora.equipo_de("Retro de la obra norte, no levanta el brazo"),
                         "Retro de la obra norte")

    def test_texto_largo_se_recorta(self):
        self.assertLessEqual(len(bitacora.equipo_de("a" * 200)), bitacora.MAX_EQUIPO)


class TestMazo(BaseTemporal):
    def setUp(self):
        super().setUp()
        self.mazo("maquinaria", "Maquinaria")
        self.mazo("automotriz", "Mecánica")

    def test_maquinaria_por_defecto(self):
        self.assertEqual(bitacora.mazo_para(self.con, "CAT 320D, fuga en el cilindro"),
                         "maquinaria")

    def test_vehiculo_va_a_mecanica(self):
        self.assertEqual(bitacora.mazo_para(self.con, "Toyota Hilux, falla el alternador"),
                         "automotriz")

    def test_sin_esos_mazos_usa_el_primero(self):
        self.con.execute("DELETE FROM decks WHERE key IN ('maquinaria','automotriz')")
        self.mazo("linux", "Linux")
        self.assertEqual(bitacora.mazo_para(self.con, "CAT 320D"), "linux")


class TestCaso(BaseTemporal):
    def setUp(self):
        super().setUp()
        self.mazo("maquinaria", "Maquinaria")
        self.mazo("automotriz", "Mecánica")

    def test_registrar_guarda_antes_de_la_ia(self):
        caso = bitacora.registrar(self.con, "  CAT 320D, fuga en cilindro del brazo  ")
        self.assertEqual(caso["estado"], "pendiente")
        self.assertEqual(caso["texto"], "CAT 320D, fuga en cilindro del brazo")
        self.assertEqual(caso["equipo"], "CAT 320D")
        self.assertEqual(caso["deck_key"], "maquinaria")
        self.assertEqual([c["id"] for c in bitacora.pendientes(self.con)], [caso["id"]])

    def test_texto_vacio_no_se_guarda(self):
        with self.assertRaises(ValueError):
            bitacora.registrar(self.con, "   ")

    def test_proponer_y_aceptar_crea_tarjetas_con_fuente(self):
        caso = bitacora.registrar(self.con, "CAT 320D, fuga en cilindro del brazo")
        bitacora.proponer(self.con, caso["id"], PROPUESTAS)
        caso = bitacora.caso(self.con, caso["id"])
        self.assertEqual(caso["estado"], "propuesto")
        self.assertEqual(caso["propuestas"], PROPUESTAS)
        self.assertEqual([c["id"] for c in bitacora.por_revisar(self.con)], [caso["id"]])

        ids = bitacora.aceptar(self.con, caso["id"], PROPUESTAS[:1])
        self.assertEqual(len(ids), 1)
        card = db.card_by_id(self.con, ids[0])
        self.assertIn("bitacora", card["tags"])
        fuente = db.source_for_card(self.con, ids[0])
        self.assertEqual(fuente["kind"], "caso")
        self.assertEqual(fuente["chapter_uid"], caso["uid"])
        self.assertIn("CAT 320D", db.source_label(fuente))
        self.assertIsNone(db.chapter_for_card(self.con, card))
        self.assertEqual(bitacora.caso(self.con, caso["id"])["estado"], "listo")
        self.assertEqual([t["id"] for t in bitacora.tarjetas_de(self.con, caso["id"])], ids)
        self.assertEqual(bitacora.por_revisar(self.con), [])

    def test_aceptar_ninguna_deja_el_caso_como_registro(self):
        caso = bitacora.registrar(self.con, "CAT 320D, fuga")
        bitacora.proponer(self.con, caso["id"], PROPUESTAS)
        self.assertEqual(bitacora.aceptar(self.con, caso["id"], []), [])
        self.assertEqual(bitacora.caso(self.con, caso["id"])["estado"], "listo")
        self.assertEqual(len(bitacora.casos(self.con)), 1)

    def test_al_aceptar_se_puede_corregir_el_mazo(self):
        caso = bitacora.registrar(self.con, "CAT 320D, fuga")
        bitacora.proponer(self.con, caso["id"], PROPUESTAS)
        ids = bitacora.aceptar(self.con, caso["id"], PROPUESTAS, deck_key="automotriz")
        fila = self.con.execute("SELECT d.key FROM cards c JOIN decks d ON d.id=c.deck_id "
                                "WHERE c.id=?", (ids[0],)).fetchone()
        self.assertEqual(fila["key"], "automotriz")
        self.assertEqual(bitacora.caso(self.con, caso["id"])["deck_key"], "automotriz")

    def test_fallo_de_la_ia_deja_el_caso_pendiente_con_motivo(self):
        caso = bitacora.registrar(self.con, "CAT 320D, fuga")
        self.assertTrue(bitacora.tomar(self.con, caso["id"]))
        self.assertEqual(bitacora.pendientes(self.con), [])      # nadie más lo toma
        bitacora.fallar(self.con, caso["id"], "Ollama no responde")
        caso = bitacora.caso(self.con, caso["id"])
        self.assertEqual(caso["estado"], "pendiente")
        self.assertEqual(caso["motivo"], "Ollama no responde")

    def test_un_caso_tomado_hace_mucho_vuelve_a_pendiente(self):
        caso = bitacora.registrar(self.con, "CAT 320D, fuga")
        bitacora.tomar(self.con, caso["id"])
        self.assertFalse(bitacora.tomar(self.con, caso["id"]))
        tarde = time.time() + bitacora.TOMADO_CADUCA + 1
        self.assertEqual(len(bitacora.pendientes(self.con, ahora=tarde)), 1)

    def test_lo_recien_fallado_espera_antes_de_reintentar(self):
        caso = bitacora.registrar(self.con, "CAT 320D, fuga")
        bitacora.tomar(self.con, caso["id"])
        bitacora.fallar(self.con, caso["id"], "sin modelo")
        self.assertEqual(bitacora.pendientes(self.con, reintento=True), [])
        tarde = time.time() + bitacora.ESPERA_REINTENTO + 1
        self.assertEqual(len(bitacora.pendientes(self.con, reintento=True, ahora=tarde)), 1)

    def test_borrar_quita_el_caso_pero_no_las_tarjetas(self):
        caso = bitacora.registrar(self.con, "CAT 320D, fuga")
        bitacora.proponer(self.con, caso["id"], PROPUESTAS)
        ids = bitacora.aceptar(self.con, caso["id"], PROPUESTAS)
        bitacora.borrar(self.con, caso["id"])
        self.assertIsNone(bitacora.caso(self.con, caso["id"]))
        self.assertIsNotNone(db.card_by_id(self.con, ids[0]))

    def test_generar_pide_concepto_y_devuelve_tarjetas(self):
        caso = bitacora.registrar(self.con, "CAT 320D, fuga en cilindro del brazo")
        trabajo = bitacora.preparar(self.con, caso["id"])
        respuesta = json.dumps({"tarjetas": PROPUESTAS})
        with mock.patch.object(ia, "_mensaje", return_value=respuesta) as llamada:
            tarjetas = ia.tarjetas_de_caso({"activa": True}, trabajo["texto"],
                                           trabajo["mazo"], trabajo["contexto"])
        self.assertEqual(tarjetas, PROPUESTAS)
        pedido = llamada.call_args[0][1][-1]["content"]
        self.assertIn("CAT 320D, fuga en cilindro del brazo", pedido)
        self.assertIn("concepto", pedido.lower())


class TestContexto(BaseTemporal):
    def test_el_contexto_sale_solo_del_mazo_del_caso(self):
        maq = self.mazo("maquinaria", "Maquinaria")
        auto = self.mazo("automotriz", "Mecánica")
        self.tarjeta(maq, "¿Qué hace el sello de un cilindro hidráulico?", key="maquinaria")
        self.tarjeta(auto, "¿Cómo se mide la compresión de un cilindro del motor?",
                     key="automotriz")
        caso = bitacora.registrar(self.con, "CAT 320D, fuga en el cilindro del brazo")
        contexto = bitacora.preparar(self.con, caso["id"])["contexto"]
        self.assertIn("hidráulico", contexto)
        self.assertNotIn("compresión", contexto)


class TestPrioridad(BaseTemporal):
    def test_las_de_la_bitacora_salen_antes_que_las_nuevas_de_fabrica(self):
        mid = self.mazo("maquinaria", "Maquinaria")
        for i in range(8):
            self.tarjeta(mid, f"De fábrica {i}", key="maquinaria", level=1)
        caso = bitacora.registrar(self.con, "CAT 320D, fuga")
        bitacora.proponer(self.con, caso["id"], PROPUESTAS)
        ids = set(bitacora.aceptar(self.con, caso["id"], PROPUESTAS))
        for _ in range(10):
            card = scheduler.next_card(self.con, new_ratio=1.0)
            self.assertIn(card["id"], ids)


class TestBuscador(BaseTemporal):
    def test_ctrl_k_encuentra_cada_visita_de_un_equipo(self):
        self.mazo("maquinaria", "Maquinaria")
        bitacora.registrar(self.con, "CAT 320D, fuga en cilindro del brazo")
        bitacora.registrar(self.con, "CAT 320D, no enciende, batería")
        bitacora.registrar(self.con, "Komatsu PC200, humo blanco")
        casos = [r for r in buscador.buscar(self.con, "320d") if r["tipo"] == "caso"]
        self.assertEqual(len(casos), 2)
        self.assertTrue(all("CAT 320D" in r["titulo"] for r in casos))


class TestAusencia(unittest.TestCase):
    def test_avisa_al_volver_tras_una_ausencia_larga(self):
        v = ausencia.Vigia(umbral_s=600, enfriamiento_s=1800)
        self.assertIsNone(v.observar(30, ahora=1000))
        self.assertIsNone(v.observar(700, ahora=1670))     # sigue fuera
        self.assertAlmostEqual(v.observar(3, ahora=1685), 700 / 60)

    def test_una_pausa_corta_no_cuenta(self):
        v = ausencia.Vigia(umbral_s=600, enfriamiento_s=1800)
        v.observar(300, ahora=1000)
        self.assertIsNone(v.observar(2, ahora=1015))

    def test_no_pregunta_dos_veces_seguidas(self):
        v = ausencia.Vigia(umbral_s=600, enfriamiento_s=1800)
        v.observar(700, ahora=1000)
        self.assertIsNotNone(v.observar(1, ahora=1015))
        v.observar(700, ahora=1800)
        self.assertIsNone(v.observar(1, ahora=1815))       # dentro del enfriamiento
        v.observar(700, ahora=4000)
        self.assertIsNotNone(v.observar(1, ahora=4015))

    def test_sin_lectura_no_hace_nada(self):
        v = ausencia.Vigia(umbral_s=600, enfriamiento_s=0)
        v.observar(700, ahora=1000)
        self.assertIsNone(v.observar(None, ahora=1015))
        self.assertIsNotNone(v.observar(1, ahora=1030))

    def test_umbral_cero_desactiva(self):
        v = ausencia.Vigia(umbral_s=0, enfriamiento_s=0)
        v.observar(5000, ahora=1000)
        self.assertIsNone(v.observar(1, ahora=1015))


class TestAjustesAusencia(BaseTemporal):
    def test_por_defecto_diez_minutos_y_acotado(self):
        self.assertEqual(ausencia.minutos(self.con), 10)
        ausencia.guardar_minutos(self.con, 999)
        self.assertEqual(ausencia.minutos(self.con), ausencia.MAX_MINUTOS)
        ausencia.guardar_minutos(self.con, 0)
        self.assertEqual(ausencia.minutos(self.con), 0)


if __name__ == "__main__":
    unittest.main()
