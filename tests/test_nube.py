"""La cuenta en la nube: ajustes, sesión guardada y sincronización por Supabase.

Ninguna prueba toca la red. El transporte de `nube` se sustituye por una nube
de mentira que guarda los snapshots en un diccionario, así que lo que se prueba
de verdad es lo que importa: que dos equipos acaben con lo mismo y que la
sesión sobreviva a cerrar la aplicación.
"""
import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from appstudy import db, nube, sincronizacion
from tests.apoyo import BaseTemporal

EQUIPO_A = "a" * 32
EQUIPO_B = "b" * 32
UID = "11111111-2222-3333-4444-555555555555"
OTRO_UID = "99999999-8888-7777-6666-555555555555"


class NubeDeMentira:
    """Ocupa el sitio del transporte: guarda los snapshots en un diccionario."""

    def __init__(self):
        self.filas: dict[str, dict] = {}
        self.subidas = 0
        self.esperas: list[float] = []

    def token(self, espera=None):
        return "token-de-prueba"

    def descargar(self):
        # Se devuelve una copia: la de verdad llega por HTTP, no compartida.
        return [json.loads(json.dumps(d)) for d in self.filas.values()]

    def subir(self, datos, espera=None, acceso=None):
        self.subidas += 1
        self.esperas.append(espera)
        self.filas[datos["device"]] = json.loads(json.dumps(datos))


class AjustesTest(unittest.TestCase):
    def setUp(self):
        for clave in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "db_database"):
            os.environ.pop(clave, None)
            os.environ.pop(clave.upper(), None)
        # Sin esto, el `.env` de quien desarrolla se cuela en las pruebas y
        # "no hay clave" deja de ser cierto en su equipo pero sí en el de al lado.
        vacio = Path(tempfile.mkdtemp()) / ".env"
        parche = mock.patch.object(nube, "_archivos_env", lambda: [vacio])
        parche.start()
        self.addCleanup(parche.stop)
        self.addCleanup(self._limpiar)

    def _limpiar(self):
        for clave in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "DB_DATABASE"):
            os.environ.pop(clave, None)

    def test_deduce_la_url_del_uri_de_postgres(self):
        os.environ["DB_DATABASE"] = ("postgresql://postgres:secreta@"
                                     "db.zfdwyxiqqpnslnammtaj.supabase.co:5432/postgres")
        os.environ["SUPABASE_ANON_KEY"] = "clave-publica"
        cfg = nube.ajustes()
        self.assertEqual(cfg["url"], "https://zfdwyxiqqpnslnammtaj.supabase.co")
        self.assertTrue(nube.configurada())

    def test_la_url_explicita_manda_y_se_le_quita_la_barra(self):
        os.environ["SUPABASE_URL"] = "https://ejemplo.supabase.co/"
        os.environ["SUPABASE_ANON_KEY"] = "clave"
        self.assertEqual(nube.ajustes()["url"], "https://ejemplo.supabase.co")

    def test_rechaza_la_clave_secreta_nueva(self):
        """Confundir la secreta con la pública deja a todos los usuarios al aire."""
        os.environ["SUPABASE_URL"] = "https://ejemplo.supabase.co"
        os.environ["SUPABASE_ANON_KEY"] = "sb_secret_ZBm4od4iAlgoAlgo"
        self.assertFalse(nube.configurada())
        self.assertIn("SECRETA", nube.que_falta())

    def test_rechaza_la_jwt_de_service_role(self):
        import base64
        import json as _json
        carga = base64.urlsafe_b64encode(
            _json.dumps({"role": "service_role"}).encode()).decode().rstrip("=")
        os.environ["SUPABASE_URL"] = "https://ejemplo.supabase.co"
        os.environ["SUPABASE_ANON_KEY"] = f"cabecera.{carga}.firma"
        self.assertFalse(nube.configurada())
        self.assertIn("SECRETA", nube.que_falta())

    def test_acepta_la_publicable_y_la_anon_de_siempre(self):
        import base64
        import json as _json
        carga = base64.urlsafe_b64encode(
            _json.dumps({"role": "anon"}).encode()).decode().rstrip("=")
        os.environ["SUPABASE_URL"] = "https://ejemplo.supabase.co"
        for clave in ("sb_publishable_AlgoAlgo", f"cabecera.{carga}.firma"):
            os.environ["SUPABASE_ANON_KEY"] = clave
            self.assertTrue(nube.configurada(), clave)
            self.assertEqual(nube.que_falta(), "")

    def test_sin_clave_dice_lo_que_falta(self):
        os.environ["SUPABASE_URL"] = "https://ejemplo.supabase.co"
        self.assertFalse(nube.configurada())
        self.assertIn("SUPABASE_ANON_KEY", nube.que_falta())


class MensajesTest(unittest.TestCase):
    """Un error de Supabase tiene que decirte qué arreglar, no un número."""

    def mensaje(self, codigo, cuerpo):
        import io
        import urllib.error
        error = urllib.error.HTTPError(
            "https://ejemplo.supabase.co", codigo, "Unauthorized", {},
            io.BytesIO(json.dumps(cuerpo).encode()))
        try:
            return nube._mensaje_http(error)
        finally:
            error.close()

    def test_la_clave_del_proyecto_no_se_confunde_con_tu_sesion(self):
        # Un 401 por la clave mandaría a reescribir la contraseña para nada.
        texto = self.mensaje(401, {"message": "Invalid API key"})
        self.assertIn("SUPABASE_ANON_KEY", texto)

    def test_la_contrasena_equivocada_se_dice_en_claro(self):
        texto = self.mensaje(400, {"error_description": "Invalid login credentials"})
        self.assertIn("incorrect", texto.lower())

    def test_sin_la_tabla_dice_qué_ejecutar(self):
        texto = self.mensaje(404, {"code": "PGRST205",
                                   "message": "Could not find the table"})
        self.assertIn("esquema.sql", texto)


class SesionTest(BaseTemporal):
    def test_se_guarda_solo_para_ti_y_se_relee(self):
        nube._guardar_sesion({"user_id": UID, "email": "yo@ejemplo.com",
                              "access_token": "corto", "refresh_token": "largo",
                              "expira": time.time() + 3600})
        ruta = nube._archivo_sesion()
        self.assertEqual(ruta.stat().st_mode & 0o777, 0o600)
        self.assertEqual(nube.usuario(), {"user_id": UID, "email": "yo@ejemplo.com"})

    def test_un_archivo_roto_no_es_una_sesion(self):
        nube._archivo_sesion().write_text("{esto no es json", encoding="utf-8")
        self.assertIsNone(nube.sesion())

    def test_el_token_vigente_se_reutiliza_sin_pedir_nada(self):
        nube._guardar_sesion({"user_id": UID, "email": "yo@ejemplo.com",
                              "access_token": "vigente", "refresh_token": "largo",
                              "expira": time.time() + 3600})
        def falso(*a, **k):
            self.fail("con el token vigente no debía hablar con Supabase")

        original, nube._pedir = nube._pedir, falso
        self.addCleanup(lambda: setattr(nube, "_pedir", original))
        self.assertEqual(nube.token(), "vigente")

    def test_el_token_caducado_se_renueva_con_el_refresh(self):
        nube._guardar_sesion({"user_id": UID, "email": "yo@ejemplo.com",
                              "access_token": "viejo", "refresh_token": "largo",
                              "expira": time.time() - 10})
        pedidas = []

        def falso(ruta, cuerpo=None, **k):
            pedidas.append((ruta, cuerpo))
            return {"access_token": "nuevo", "refresh_token": "otro-largo",
                    "expires_in": 3600, "user": {"id": UID, "email": "yo@ejemplo.com"}}

        original, nube._pedir = nube._pedir, falso
        self.addCleanup(lambda: setattr(nube, "_pedir", original))
        self.assertEqual(nube.token(), "nuevo")
        self.assertIn("grant_type=refresh_token", pedidas[0][0])
        # Supabase rota el refresh en cada canje: hay que guardar el nuevo o la
        # próxima vez tocaría volver a escribir la contraseña.
        self.assertEqual(nube.sesion()["refresh_token"], "otro-largo")

    def test_un_refresh_rechazado_borra_la_sesion(self):
        nube._guardar_sesion({"user_id": UID, "email": "yo@ejemplo.com",
                              "access_token": "viejo", "refresh_token": "revocado",
                              "expira": time.time() - 10})

        def falso(*a, **k):
            raise nube.NubeError("Invalid Refresh Token", 400)

        original, nube._pedir = nube._pedir, falso
        self.addCleanup(lambda: setattr(nube, "_pedir", original))
        with self.assertRaises(nube.NubeError):
            nube.token()
        self.assertIsNone(nube.sesion())

    def test_un_fallo_de_red_conserva_la_sesion(self):
        """Estar sin internet no puede costarte tener que volver a entrar."""
        nube._guardar_sesion({"user_id": UID, "email": "yo@ejemplo.com",
                              "access_token": "viejo", "refresh_token": "bueno",
                              "expira": time.time() - 10})

        def falso(*a, **k):
            raise nube.NubeError("No pude conectar", 0)

        original, nube._pedir = nube._pedir, falso
        self.addCleanup(lambda: setattr(nube, "_pedir", original))
        with self.assertRaises(nube.NubeError):
            nube.token()
        self.assertIsNotNone(nube.sesion())


class CuentaLocalTest(BaseTemporal):
    def test_sin_cuenta_se_usa_la_base_de_siempre(self):
        self.assertEqual(db.cuenta_activa(), "")
        self.assertEqual(db.ruta_db(), db.DB_PATH)

    def test_cada_cuenta_tiene_su_propio_archivo(self):
        db.usar_cuenta(UID)
        una = db.ruta_db()
        db.usar_cuenta(OTRO_UID)
        otra = db.ruta_db()
        self.assertNotEqual(una, otra)
        self.assertEqual(db.cuenta_activa(), OTRO_UID)
        db.usar_cuenta("")
        self.assertEqual(db.ruta_db(), db.DB_PATH)

    def test_no_acepta_un_identificador_inventado(self):
        with self.assertRaises(ValueError):
            db.usar_cuenta("../../etc/passwd")
        self.assertEqual(db.cuenta_activa(), "")

    def test_dos_cuentas_no_se_ven_las_tarjetas(self):
        db.usar_cuenta(UID)
        una = db.connect()
        did = db.upsert_deck(una, "mio", "Mi mazo", "🧠", "#123456", 1)
        db.add_card(una, did, "mio", "card", "Solo mía", "sí")
        una.commit()
        una.close()

        db.usar_cuenta(OTRO_UID)
        otra = db.connect()
        self.addCleanup(otra.close)
        cuantas = otra.execute(
            "SELECT COUNT(*) c FROM cards WHERE front='Solo mía'").fetchone()["c"]
        self.assertEqual(cuantas, 0)

    def test_la_primera_cuenta_hereda_el_progreso_de_antes(self):
        """Entrar por primera vez no puede parecer que te borró meses de repasos."""
        did = self.mazo()
        self.tarjeta(did, "De cuando no tenía cuenta")
        self.con.commit()

        self.assertTrue(db.adoptar_cuenta(UID))
        db.usar_cuenta(UID)
        con = db.connect()
        self.addCleanup(con.close)
        cuantas = con.execute(
            "SELECT COUNT(*) c FROM cards WHERE front='De cuando no tenía cuenta'"
        ).fetchone()["c"]
        self.assertEqual(cuantas, 1)

    def test_la_segunda_cuenta_del_equipo_arranca_limpia(self):
        """Quien se sienta después en tu computadora no hereda tus tarjetas."""
        did = self.mazo()
        self.tarjeta(did, "Mías de siempre")
        self.con.commit()
        db.adoptar_cuenta(UID)

        self.assertFalse(db.adoptar_cuenta(OTRO_UID))
        db.usar_cuenta(OTRO_UID)
        con = db.connect()
        self.addCleanup(con.close)
        cuantas = con.execute("SELECT COUNT(*) c FROM cards").fetchone()["c"]
        self.assertEqual(cuantas, 0)


class SincronizarNubeTest(BaseTemporal):
    """Dos equipos, una cuenta: lo que estudias en uno aparece en el otro."""

    def setUp(self):
        super().setUp()
        self.falsa = NubeDeMentira()
        self._original = (nube.descargar_snapshots, nube.subir_snapshot, nube.token)
        nube.descargar_snapshots = self.falsa.descargar
        nube.subir_snapshot = self.falsa.subir
        nube.token = self.falsa.token
        self.addCleanup(self._restaurar)

        self.otra = sqlite3.connect(self.tmp / "portatil.db")
        self.otra.row_factory = sqlite3.Row
        self.otra.execute("PRAGMA foreign_keys = ON")
        self.otra.executescript(db.SCHEMA)
        db.migrate(self.otra)
        self.otra.executescript(db.INDEXES)
        self.addCleanup(self.otra.close)

    def _restaurar(self):
        (nube.descargar_snapshots, nube.subir_snapshot,
         nube.token) = self._original

    def sync_a(self):
        return sincronizacion.sincronizar_nube(self.con, EQUIPO_A)

    def sync_b(self):
        return sincronizacion.sincronizar_nube(self.otra, EQUIPO_B)

    def test_una_tarjeta_llega_al_otro_equipo(self):
        did = self.mazo()
        self.tarjeta(did, "¿Qué hace chmod?", "Cambia los permisos")
        self.sync_a()
        resultado = self.sync_b()

        self.assertEqual(resultado["equipos"], 1)
        fila = self.otra.execute(
            "SELECT back FROM cards WHERE front='¿Qué hace chmod?'").fetchone()
        self.assertEqual(fila["back"], "Cambia los permisos")

    def test_el_historial_de_repasos_viaja(self):
        did = self.mazo()
        cid = self.tarjeta(did, "¿Qué hace ls?")
        self.repasar(cid, 3)
        self.repasar(cid, 2)
        self.sync_a()
        resultado = self.sync_b()

        self.assertEqual(resultado["repasos"], 2)
        repasos = self.otra.execute("SELECT COUNT(*) c FROM log").fetchone()["c"]
        self.assertEqual(repasos, 2)

    def test_el_estado_fsrs_gana_el_repaso_mas_reciente(self):
        did = self.mazo()
        cid = self.tarjeta(did, "¿Qué hace grep?")
        self.repasar(cid, 3)
        self.sync_a()
        self.sync_b()

        # El portátil la repasa después: al volver a sincronizar, la torre debe
        # quedarse con ese estado, no con el suyo, que ya es el viejo.
        remoto = self.otra.execute(
            "SELECT id FROM cards WHERE front='¿Qué hace grep?'").fetchone()["id"]
        self.otra.execute(
            "UPDATE state SET reps=9, last=?, due=? WHERE card_id=?",
            (time.time() + 60, time.time() + 99999, remoto))
        self.otra.commit()
        self.sync_b()
        self.sync_a()

        reps = self.con.execute(
            "SELECT reps FROM state WHERE card_id=?", (cid,)).fetchone()["reps"]
        self.assertEqual(reps, 9)

    def test_los_dos_equipos_convergen_sin_importar_el_orden(self):
        did = self.mazo()
        self.tarjeta(did, "De la torre")
        self.sync_a()
        self.sync_b()

        otro_did = db.upsert_deck(self.otra, "linux", "Linux", "🐧", "#3584e4", 1)
        db.add_card(self.otra, otro_did, "linux", "card", "Del portátil", "sí")
        self.otra.commit()
        self.sync_b()
        self.sync_a()

        for con in (self.con, self.otra):
            frentes = {f["front"] for f in con.execute("SELECT front FROM cards")}
            self.assertIn("De la torre", frentes)
            self.assertIn("Del portátil", frentes)

    def test_un_snapshot_de_otro_formato_se_ignora_sin_romper(self):
        self.falsa.filas["c" * 32] = {"format": 99, "device": "c" * 32}
        did = self.mazo()
        self.tarjeta(did, "La mía")
        resultado = self.sync_a()
        self.assertEqual(resultado["ignorados"], 1)
        self.assertEqual(self.falsa.filas[EQUIPO_A]["device"], EQUIPO_A)

    def test_publicar_sube_sin_bajar_nada(self):
        """Lo que se hace al cerrar: una sola petición, sin fusionar."""
        did = self.mazo()
        self.tarjeta(did, "Recién estudiada")
        sincronizacion.publicar_nube(self.con, EQUIPO_A)

        self.assertEqual(self.falsa.subidas, 1)
        frentes = {c["front"] for c in self.falsa.filas[EQUIPO_A]["cards"]}
        self.assertIn("Recién estudiada", frentes)
        # Con la red caída, cerrar no puede quedarse esperando sin fin
        self.assertLessEqual(self.falsa.esperas[0], nube.LIMITE_CIERRE)

    def test_no_sube_una_biblioteca_mas_grande_que_el_limite(self):
        self._restaurar()                 # aquí sí interesa el guardia de verdad
        enorme = {"device": EQUIPO_A, "cards": ["x" * (nube.MAX_SUBIDA + 1)]}
        with self.assertRaises(nube.NubeError) as caso:
            nube.subir_snapshot(enorme)
        self.assertIn("carpeta compartida", str(caso.exception))


if __name__ == "__main__":
    unittest.main()
