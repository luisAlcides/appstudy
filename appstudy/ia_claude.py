"""Bit hablando con Claude a través de Claude Code (`claude -p`).

Es la alternativa a Ollama para quien ya paga una suscripción de Claude: cada
consulta arranca `claude -p` con tu sesión de claude.ai, así que no hace falta
clave de API ni se cobra aparte; cuenta contra los límites de uso del plan, los
mismos del chat. A cambio, las preguntas y tus tarjetas salen del equipo.

Se lanza sin herramientas, sin MCP, sin plugins y sin guardar la sesión: aquí
Claude solo conversa. Cada consulta tarda unos segundos más que la API directa
porque arranca un proceso nuevo.

Igual que `ia`, esto bloquea: se llama siempre fuera del hilo de la interfaz.
"""
import json
import os
import shutil
import subprocess
import threading
from pathlib import Path

MODELO_DEFECTO = "claude-sonnet-5"
ESPERA = 120            # segundos; una respuesta larga con tarjetas cabe de sobra
# Bit contesta en un globo: pensar mucho solo lo haría más lento.
ESFUERZO = "low"
# Sin esto, Claude Code usaría su propio prompt de programador.
SISTEMA_VACIO = "Responde en español, de forma breve."


class ClaudeError(RuntimeError):
    """Algo salió mal con Claude Code; el mensaje es para enseñarlo."""


def _carpeta() -> Path:
    """Un directorio neutro: fuera del proyecto no se carga ningún CLAUDE.md."""
    carpeta = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "appstudy" / "claude"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def _entorno() -> dict:
    """El entorno sin claves de API: esto va con la suscripción, no se cobra aparte.

    Si hubiera una ANTHROPIC_API_KEY exportada, Claude Code la preferiría a la
    sesión de claude.ai y cada pregunta de Bit se facturaría en la API.
    """
    entorno = dict(os.environ)
    for clave in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        entorno.pop(clave, None)
    return entorno


def _orden(modelo: str, sistema: str, formato, streaming: bool) -> list:
    orden = ["claude", "-p", "--model", modelo,
             "--system-prompt", sistema or SISTEMA_VACIO,
             "--tools", "", "--strict-mcp-config", "--setting-sources", "",
             "--disable-slash-commands", "--no-session-persistence",
             "--effort", ESFUERZO,
             "--output-format", "stream-json" if streaming else "json"]
    if streaming:
        orden += ["--verbose", "--include-partial-messages"]
    if formato:
        orden += ["--json-schema", json.dumps(formato)]
    return orden


def _separar(mensajes: list) -> tuple:
    """(sistema, texto) a partir de la lista al estilo de Ollama.

    `claude -p` recibe un solo mensaje, así que una charla con historial se le
    pasa como transcripción y se le pide contestar al último turno.
    """
    sistema = "\n\n".join(m["content"] for m in mensajes if m["role"] == "system")
    turnos = [m for m in mensajes if m["role"] != "system"]
    if len(turnos) == 1:
        return sistema, turnos[0]["content"]
    quien = {"user": "Usuario", "assistant": "Tú"}
    previos = "\n\n".join(f"{quien.get(m['role'], m['role'])}: {m['content']}"
                          for m in turnos[:-1])
    return sistema, (f"Conversación hasta ahora:\n\n{previos}\n\n---\n"
                     f"Responde al último mensaje del usuario:\n\n{turnos[-1]['content']}")


def _final(dato: dict, formato) -> str:
    if dato.get("is_error") or dato.get("subtype") != "success":
        raise ClaudeError(f"Claude no pudo responder: {dato.get('result') or dato.get('subtype')}")
    if formato and dato.get("structured_output") is not None:
        return json.dumps(dato["structured_output"], ensure_ascii=False)
    return (dato.get("result") or "").strip()


def mensaje(mensajes: list, modelo: str = MODELO_DEFECTO, formato=None, trozo=None,
            espera: int = ESPERA) -> str:
    """Manda la conversación a Claude y devuelve el texto completo.

    Con `formato` (un esquema JSON) devuelve el JSON ya validado como texto, que
    es lo que esperan los que llaman. Con `trozo`, lo va entregando según llega.
    """
    sistema, texto = _separar(mensajes)
    streaming = trozo is not None
    try:
        proceso = subprocess.Popen(
            _orden(modelo, sistema, formato, streaming),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=_carpeta(), env=_entorno())
    except FileNotFoundError:
        raise ClaudeError("No encontré Claude Code (la orden «claude»). Instálalo o "
                          "elige Ollama en Ajustes.") from None

    if not streaming:
        try:
            salida, error = proceso.communicate(texto, timeout=espera)
        except subprocess.TimeoutExpired:
            proceso.kill()
            raise ClaudeError(f"Claude no respondió a tiempo ({espera} s).") from None
        try:
            return _final(json.loads(salida), formato)
        except json.JSONDecodeError:
            ultima = (error or "").strip().splitlines()[-1:] or ["sin salida"]
            raise ClaudeError(f"Claude Code falló: {ultima[0]}") from None

    reloj = threading.Timer(espera, proceso.kill)
    reloj.start()
    final = None
    try:
        proceso.stdin.write(texto)
        proceso.stdin.close()
        for linea in proceso.stdout:
            try:
                dato = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if dato.get("type") == "stream_event":
                delta = (dato.get("event") or {}).get("delta") or {}
                if delta.get("type") == "text_delta" and delta.get("text"):
                    trozo(delta["text"])
            elif dato.get("type") == "result":
                final = dato
        proceso.wait(timeout=5)
    finally:
        reloj.cancel()
    if final is None:
        raise ClaudeError("Se cortó la respuesta de Claude antes de terminar.")
    return _final(final, formato)


def probar(modelo: str = MODELO_DEFECTO) -> tuple:
    """(ok, mensaje) sin gastar cuota: solo mira que haya sesión iniciada."""
    if not shutil.which("claude"):
        return False, "No encontré Claude Code (la orden «claude») en este equipo."
    try:
        r = subprocess.run(["claude", "auth", "status"], capture_output=True, text=True,
                           timeout=15, env=_entorno())
        estado = json.loads(r.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return False, "Claude Code no respondió al comprobar la sesión."
    if not estado.get("loggedIn"):
        return False, "No hay sesión de Claude. Ejecuta «claude auth login» en una terminal."
    if estado.get("authMethod") != "claude.ai":
        return True, (f"Conectado con «{modelo}», pero con {estado.get('authMethod')}: "
                      "puede cobrarse aparte de tu suscripción.")
    return True, f"Conectado con «{modelo}» mediante tu suscripción de Claude."
