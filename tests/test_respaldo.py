"""Respaldo y restauración: que una copia sirva de verdad para volver atrás.

Lo importante no es que el archivo se cree, sino que restaurarlo devuelva el
progreso exacto, que no se pueda restaurar cualquier archivo encima de tus
datos, y que restaurar por error tenga vuelta atrás.
"""
import sqlite3
import time
import unittest

from appstudy import db, respaldo, scheduler
from tests.apoyo import BaseTemporal


class TestCrearYListar(BaseTemporal):
    def test_crear_deja_un_archivo_que_es_una_base_valida(self):
        self.tarjeta(self.mazo(), "¿Qué hace ls?")
        ruta = respaldo.crear(self.con, "manual")
        self.assertTrue(ruta.is_file())
        self.assertGreater(ruta.stat().st_size, 0)
        self.assertIn("tarjetas", respaldo.revisar(ruta))

    def test_no_queda_ningun_archivo_parcial(self):
        respaldo.crear(self.con)
        self.assertEqual(list(respaldo.CARPETA.glob("*.parcial")), [])

    def test_listar_los_devuelve_del_mas_nuevo_al_mas_viejo(self):
        for _ in range(3):
            respaldo.crear(self.con, "manual")
            time.sleep(1.05)          # el nombre lleva la hora al segundo
        copias = respaldo.listar()
        self.assertEqual(len(copias), 3)
        self.assertEqual([c["ts"] for c in copias],
                         sorted((c["ts"] for c in copias), reverse=True))

    def test_listar_sin_carpeta_no_falla(self):
        self.assertEqual(respaldo.listar(), [])

    def test_el_motivo_queda_en_el_nombre_y_se_lee_al_listar(self):
        respaldo.crear(self.con, "auto")
        self.assertEqual(respaldo.listar()[0]["motivo"], "auto")

    def test_un_archivo_ajeno_en_la_carpeta_se_ignora(self):
        respaldo.crear(self.con)
        (respaldo.carpeta() / "notas.txt").write_text("nada que ver")
        (respaldo.carpeta() / "appstudy-cualquiera.db").write_bytes(b"basura")
        self.assertEqual(len(respaldo.listar()), 1)


class TestPodar(BaseTemporal):
    def _falso(self, dia, motivo):
        ruta = respaldo.carpeta() / f"appstudy-201501{dia:02d}-120000-{motivo}.db"
        respaldo.copiar(self.con, ruta)
        return ruta

    def test_deja_solo_los_automaticos_mas_recientes(self):
        for dia in range(1, 8):
            self._falso(dia, "auto")
        respaldo.podar(maximo=3)
        quedan = respaldo.listar()
        self.assertEqual(len(quedan), 3)
        self.assertEqual([r["ruta"].name[9:17] for r in quedan],
                         ["20150107", "20150106", "20150105"])

    def test_no_poda_los_manuales_ni_los_de_antes_de_restaurar(self):
        for dia in range(1, 6):
            self._falso(dia, "auto")
        manual = self._falso(9, "manual")
        antes = self._falso(10, "antes")
        respaldo.podar(maximo=1)
        nombres = {r["ruta"].name for r in respaldo.listar()}
        self.assertIn(manual.name, nombres)
        self.assertIn(antes.name, nombres)
        self.assertEqual(sum(1 for r in respaldo.listar() if r["motivo"] == "auto"), 1)


class TestAutoSiToca(BaseTemporal):
    def test_el_primero_se_hace_siempre(self):
        self.assertIsNotNone(respaldo.auto_si_toca(self.con))

    def test_no_repite_si_el_ultimo_es_de_hace_un_rato(self):
        respaldo.auto_si_toca(self.con)
        self.assertIsNone(respaldo.auto_si_toca(self.con))
        self.assertEqual(len(respaldo.listar()), 1)

    def test_vuelve_a_hacerlo_pasado_el_plazo(self):
        respaldo.auto_si_toca(self.con)
        time.sleep(1.05)
        self.assertIsNotNone(respaldo.auto_si_toca(self.con, cada=0.5))

    def test_un_respaldo_manual_reciente_no_cuenta_como_automatico(self):
        respaldo.crear(self.con, "manual")
        self.assertIsNotNone(respaldo.auto_si_toca(self.con))

    def test_si_no_se_puede_escribir_no_revienta_el_arranque(self):
        respaldo.CARPETA = self.tmp / "no-existe" / "ni-se-puede"
        (self.tmp / "no-existe").write_text("esto es un archivo, no una carpeta")
        self.assertIsNone(respaldo.auto_si_toca(self.con))


class TestRevisar(BaseTemporal):
    def test_acepta_una_base_de_appstudy_y_la_resume(self):
        cid = self.tarjeta(self.mazo(), "¿Qué hace ls?")
        scheduler.apply_review(self.con, cid, scheduler.GOOD)
        resumen = respaldo.revisar(respaldo.crear(self.con))
        self.assertIn("1 tarjetas", resumen)
        self.assertIn("1 repasos", resumen)

    def test_rechaza_un_archivo_que_no_existe(self):
        with self.assertRaises(ValueError):
            respaldo.revisar(self.tmp / "fantasma.db")

    def test_rechaza_algo_que_no_es_sqlite(self):
        malo = self.tmp / "carta.db"
        malo.write_text("Querido diario, hoy no estudié.")
        with self.assertRaises(ValueError):
            respaldo.revisar(malo)

    def test_rechaza_una_base_sqlite_de_otro_programa(self):
        ajena = self.tmp / "ajena.db"
        otra = sqlite3.connect(ajena)
        otra.execute("CREATE TABLE recetas (id INTEGER, nombre TEXT)")
        otra.commit()
        otra.close()
        with self.assertRaises(ValueError) as caso:
            respaldo.revisar(ajena)
        self.assertIn("AppStudy", str(caso.exception))


class TestRestaurar(BaseTemporal):
    def test_devuelve_el_progreso_exacto_que_tenia_la_copia(self):
        deck = self.mazo()
        cid = self.tarjeta(deck, "¿Qué hace ls?")
        scheduler.apply_review(self.con, cid, scheduler.GOOD)
        copia = respaldo.crear(self.con)
        antes = dict(self.con.execute("SELECT * FROM state WHERE card_id=?",
                                      (cid,)).fetchone())

        # Se sigue estudiando y se añaden tarjetas después de la copia
        for _ in range(4):
            scheduler.apply_review(self.con, cid, scheduler.GOOD)
        self.tarjeta(deck, "una tarjeta posterior a la copia")

        respaldo.restaurar(self.con, copia)

        ahora = dict(self.con.execute("SELECT * FROM state WHERE card_id=?",
                                      (cid,)).fetchone())
        self.assertEqual(ahora["reps"], antes["reps"])
        self.assertAlmostEqual(ahora["interval"], antes["interval"])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM log").fetchone()[0], 1)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM cards").fetchone()[0], 1)

    def test_guarda_una_red_de_seguridad_antes_de_pisar_nada(self):
        deck = self.mazo()
        cid = self.tarjeta(deck, "¿Qué hace ls?")
        copia = respaldo.crear(self.con)
        self.tarjeta(deck, "la que solo existe ahora")
        scheduler.apply_review(self.con, cid, scheduler.EASY)

        red = respaldo.restaurar(self.con, copia)

        self.assertTrue(red.is_file())
        self.assertEqual(respaldo.listar()[0]["motivo"], "antes")
        # Y esa red de verdad contiene lo que había justo antes de restaurar
        guardado = sqlite3.connect(f"file:{red}?mode=ro", uri=True)
        try:
            self.assertEqual(guardado.execute("SELECT COUNT(*) FROM cards").fetchone()[0], 2)
        finally:
            guardado.close()

    def test_restaurar_la_red_deshace_la_restauracion(self):
        deck = self.mazo()
        self.tarjeta(deck, "la primera")
        vieja = respaldo.crear(self.con)
        self.tarjeta(deck, "la segunda")

        red = respaldo.restaurar(self.con, vieja)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM cards").fetchone()[0], 1)
        respaldo.restaurar(self.con, red)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM cards").fetchone()[0], 2)

    def test_no_restaura_un_archivo_que_no_es_de_appstudy(self):
        self.tarjeta(self.mazo(), "la que no se debe perder")
        malo = self.tmp / "cualquier.db"
        malo.write_bytes(b"esto no es una base de datos")
        with self.assertRaises(ValueError):
            respaldo.restaurar(self.con, malo)
        # Y sobre todo: no ha tocado nada
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM cards").fetchone()[0], 1)
        self.assertEqual(respaldo.listar(), [])

    def test_la_conexion_sigue_viva_despues_de_restaurar(self):
        # Restaurar no reinicia la aplicación: la misma conexión debe poder
        # seguir leyendo y escribiendo, y las otras ventanas ven lo nuevo.
        deck = self.mazo()
        self.tarjeta(deck, "la de siempre")
        copia = respaldo.crear(self.con)
        respaldo.restaurar(self.con, copia)
        nueva = self.tarjeta(deck, "escrita después de restaurar")
        self.assertIsNotNone(db.card_by_id(self.con, nueva))

    def test_restaurar_una_base_antigua_le_aplica_las_migraciones(self):
        antigua = self.tmp / "antigua.db"
        otra = sqlite3.connect(antigua)
        otra.executescript(db.SCHEMA)
        otra.execute("ALTER TABLE books DROP COLUMN zoom")     # como una versión vieja
        otra.commit()
        otra.close()
        respaldo.restaurar(self.con, antigua)
        columnas = {r["name"] for r in self.con.execute("PRAGMA table_info(books)")}
        self.assertIn("zoom", columnas)


class TestFormato(unittest.TestCase):
    def test_el_tamano_se_lee_de_un_vistazo(self):
        self.assertEqual(respaldo.tamano(512), "512 B")
        self.assertEqual(respaldo.tamano(2048), "2 KB")
        self.assertEqual(respaldo.tamano(5 * 1024 * 1024), "5.0 MB")

    def test_hoy_y_ayer_se_dicen_con_palabras(self):
        ahora = time.time()
        self.assertTrue(respaldo.cuando(ahora).startswith("hoy a las"))
        self.assertTrue(respaldo.cuando(ahora - 86400).startswith(("ayer a las", "hoy a las")))

    def test_lo_antiguo_lleva_fecha_completa(self):
        viejo = time.mktime(time.strptime("20200115-1030", "%Y%m%d-%H%M"))
        self.assertEqual(respaldo.cuando(viejo), "15/01/2020 a las 10:30")

    def test_describir_junta_fecha_tamano_y_motivo(self):
        texto = respaldo.describir({"ts": time.time(), "bytes": 3072, "motivo": "auto"})
        self.assertIn("3 KB", texto)
        self.assertIn("automático", texto)


if __name__ == "__main__":
    unittest.main()
