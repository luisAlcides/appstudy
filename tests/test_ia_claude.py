"""Bit con Claude a través de Claude Code: la orden, las respuestas y los fallos."""
import json
import subprocess
import unittest
from unittest import mock

from appstudy import ia, ia_claude


class _Proceso:
    """Un `claude -p` de mentira: devuelve lo que se le diga por stdout."""

    def __init__(self, salida, codigo=0, error=""):
        self.salida, self.returncode, self.error = salida, codigo, error
        self.stdin_recibido = None

    def communicate(self, entrada=None, timeout=None):
        self.stdin_recibido = entrada
        return self.salida, self.error

    def kill(self):
        pass


def _resultado(**extra):
    return json.dumps({"type": "result", "subtype": "success", "is_error": False,
                       "result": "Hola", **extra})


class OrdenTest(unittest.TestCase):
    def test_la_orden_no_lleva_herramientas_ni_sesion_y_usa_el_modelo(self):
        orden = ia_claude._orden("claude-sonnet-5", "Eres Bit.", None, streaming=False)
        self.assertEqual(orden[:2], ["claude", "-p"])
        self.assertEqual(orden[orden.index("--model") + 1], "claude-sonnet-5")
        self.assertEqual(orden[orden.index("--system-prompt") + 1], "Eres Bit.")
        self.assertEqual(orden[orden.index("--tools") + 1], "")
        self.assertIn("--no-session-persistence", orden)
        self.assertIn("--strict-mcp-config", orden)
        self.assertEqual(orden[orden.index("--output-format") + 1], "json")
        self.assertNotIn("--json-schema", orden)

    def test_con_esquema_pide_salida_estructurada(self):
        orden = ia_claude._orden("claude-sonnet-5", "s", ia.ESQUEMA_TARJETAS, streaming=False)
        self.assertEqual(json.loads(orden[orden.index("--json-schema") + 1]),
                         ia.ESQUEMA_TARJETAS)

    def test_en_streaming_pide_trozos_parciales(self):
        orden = ia_claude._orden("claude-sonnet-5", "s", None, streaming=True)
        self.assertEqual(orden[orden.index("--output-format") + 1], "stream-json")
        self.assertIn("--include-partial-messages", orden)

    def test_el_entorno_no_pasa_una_api_key(self):
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-x", "HOME": "/h"}):
            entorno = ia_claude._entorno()
        self.assertNotIn("ANTHROPIC_API_KEY", entorno)
        self.assertEqual(entorno["HOME"], "/h")


class ConversacionTest(unittest.TestCase):
    def test_un_mensaje_suelto_va_tal_cual(self):
        sistema, texto = ia_claude._separar([{"role": "system", "content": "S"},
                                            {"role": "user", "content": "¿Qué es un relé?"}])
        self.assertEqual((sistema, texto), ("S", "¿Qué es un relé?"))

    def test_el_historial_se_convierte_en_transcripcion(self):
        _, texto = ia_claude._separar([
            {"role": "system", "content": "S"},
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "¡Hola! ¿Qué repasamos?"},
            {"role": "user", "content": "Ohm"}])
        self.assertIn("Hola", texto)
        self.assertIn("¿Qué repasamos?", texto)
        self.assertTrue(texto.rstrip().endswith("Ohm"))


class MensajeTest(unittest.TestCase):
    def _con(self, proceso):
        return mock.patch("subprocess.Popen", return_value=proceso)

    def test_devuelve_el_texto_y_manda_el_prompt_por_stdin(self):
        proceso = _Proceso(_resultado(result="Un relé es un interruptor."))
        with self._con(proceso):
            texto = ia_claude.mensaje([{"role": "system", "content": "S"},
                                      {"role": "user", "content": "¿Relé?"}])
        self.assertEqual(texto, "Un relé es un interruptor.")
        self.assertEqual(proceso.stdin_recibido, "¿Relé?")

    def test_con_esquema_devuelve_el_json_estructurado(self):
        tarjetas = {"tarjetas": [{"front": "¿V?", "back": "I·R"}]}
        proceso = _Proceso(_resultado(result="texto", structured_output=tarjetas))
        with self._con(proceso):
            crudo = ia_claude.mensaje([{"role": "user", "content": "x"}],
                                      formato=ia.ESQUEMA_TARJETAS)
        self.assertEqual(json.loads(crudo), tarjetas)

    def test_un_error_de_claude_llega_con_su_mensaje(self):
        proceso = _Proceso(json.dumps({"type": "result", "subtype": "success", "is_error": True,
                                       "result": "Claude usage limit reached"}))
        with self._con(proceso), self.assertRaises(ia_claude.ClaudeError) as e:
            ia_claude.mensaje([{"role": "user", "content": "x"}])
        self.assertIn("usage limit", str(e.exception))

    def test_sin_claude_instalado_lo_dice(self):
        with mock.patch("subprocess.Popen", side_effect=FileNotFoundError), \
                self.assertRaises(ia_claude.ClaudeError) as e:
            ia_claude.mensaje([{"role": "user", "content": "x"}])
        self.assertIn("Claude Code", str(e.exception))

    def test_una_salida_ilegible_no_revienta(self):
        with self._con(_Proceso("", codigo=1, error="boom")), \
                self.assertRaises(ia_claude.ClaudeError):
            ia_claude.mensaje([{"role": "user", "content": "x"}])

    def test_streaming_entrega_los_trozos_en_orden(self):
        lineas = [
            {"type": "system", "subtype": "init"},
            {"type": "stream_event", "event": {"type": "content_block_delta",
                                               "delta": {"type": "text_delta", "text": "Un "}}},
            {"type": "stream_event", "event": {"type": "content_block_delta",
                                               "delta": {"type": "text_delta", "text": "relé"}}},
            {"type": "result", "subtype": "success", "is_error": False, "result": "Un relé"},
        ]
        proceso = mock.MagicMock()
        proceso.stdout = iter(json.dumps(l) + "\n" for l in lineas)
        proceso.wait.return_value = 0
        trozos = []
        with self._con(proceso):
            texto = ia_claude.mensaje([{"role": "user", "content": "x"}], trozo=trozos.append)
        self.assertEqual(trozos, ["Un ", "relé"])
        self.assertEqual(texto, "Un relé")


class DespachoTest(unittest.TestCase):
    def test_ia_usa_claude_cuando_es_el_proveedor(self):
        cfg = {"activa": True, "proveedor": "claude", "modelo_claude": "claude-sonnet-5",
               "url": ia.URL_DEFECTO, "modelo": "gemma4"}
        with mock.patch.object(ia_claude, "mensaje", return_value="hola") as llamada, \
                mock.patch.object(ia, "modelos") as ollama:
            self.assertEqual(ia._mensaje(cfg, [{"role": "user", "content": "x"}]), "hola")
        ollama.assert_not_called()
        self.assertEqual(llamada.call_args.kwargs["modelo"], "claude-sonnet-5")

    def test_los_errores_de_claude_salen_como_iaerror(self):
        cfg = {"activa": True, "proveedor": "claude", "modelo_claude": "claude-sonnet-5"}
        with mock.patch.object(ia_claude, "mensaje", side_effect=ia_claude.ClaudeError("sin red")), \
                self.assertRaises(ia.IAError):
            ia._mensaje(cfg, [{"role": "user", "content": "x"}])

    def test_con_claude_no_hay_nada_que_descargar_de_memoria(self):
        with mock.patch.object(ia, "en_memoria") as ollama:
            self.assertFalse(ia.descargar({"proveedor": "claude"}))
        ollama.assert_not_called()

    def test_probar_con_suscripcion(self):
        estado = json.dumps({"loggedIn": True, "authMethod": "claude.ai"})
        with mock.patch("shutil.which", return_value="/usr/bin/claude"), \
                mock.patch("subprocess.run",
                           return_value=subprocess.CompletedProcess([], 0, estado, "")):
            ok, texto = ia.probar({"proveedor": "claude", "modelo_claude": "claude-sonnet-5"})
        self.assertTrue(ok)
        self.assertIn("claude-sonnet-5", texto)
        self.assertIn("suscripción", texto)

    def test_probar_sin_sesion_iniciada(self):
        estado = json.dumps({"loggedIn": False})
        with mock.patch("shutil.which", return_value="/usr/bin/claude"), \
                mock.patch("subprocess.run",
                           return_value=subprocess.CompletedProcess([], 0, estado, "")):
            ok, texto = ia.probar({"proveedor": "claude", "modelo_claude": "claude-sonnet-5"})
        self.assertFalse(ok)
        self.assertIn("claude auth login", texto)


if __name__ == "__main__":
    unittest.main()
