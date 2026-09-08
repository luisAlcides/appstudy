"""Registro de extensiones y paquetes. Instalar nunca ejecuta código externo.

Los permisos de un plugin Python son declarativos, no una caja de arena.
Al activarlo el usuario confía en código con los permisos de su sesión.
"""
from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import time
import zipfile

from . import db, fuentes

API_VERSION = 1
MAX_PAQUETE = 150 * 1024 * 1024
PERMISOS = {"network", "read_files", "execute_python"}
INCLUIDAS = [
    ("wikipedia", "Wikipedia", "source", ["network"]),
    ("openstax", "OpenStax", "source", ["network"]),
    ("mit", "MIT OpenCourseWare", "source", ["network"]),
    ("markdown", "Carpetas Markdown", "source", ["read_files"]),
    ("anki", "Anki y tarjetas multimedia", "tool", ["read_files"]),
    ("ocr", "OCR e indexación de documentos", "tool", ["read_files"]),
    ("documentos", "Preguntar a mis documentos", "tool", []),
    ("subtitulos", "Subtítulos SRT/VTT", "tool", ["read_files"]),
    ("exportador", "Exportar mazos", "tool", []),
]


def config(con, ident):
    try:
        valor = json.loads(db.get_meta(con, "extension:" + ident, "{}"))
        return valor if isinstance(valor, dict) else {}
    except ValueError:
        return {}


def configurar(con, ident, **valores):
    db.set_meta(con, "extension:" + ident, json.dumps({**config(con, ident), **valores}, ensure_ascii=False))
    con.commit()


def ruta_base():
    return db.DATA_DIR / "extensiones"


def manifiesto(data):
    if not isinstance(data, dict):
        raise ValueError("El manifiesto debe ser un objeto JSON")
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,60}", str(data.get("id", ""))):
        raise ValueError("Identificador de extensión no válido")
    if data["id"] in {x[0] for x in INCLUIDAS}:
        raise ValueError("El paquete no puede reemplazar una extensión incluida")
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(data.get("version", ""))):
        raise ValueError("La versión debe tener formato 1.0.0")
    if data.get("api_version") != API_VERSION:
        raise ValueError("Este paquete requiere otra versión de la API de AppStudy")
    if not isinstance(data.get("name"), str) or not 1 <= len(data["name"]) <= 120:
        raise ValueError("Nombre de extensión no válido")
    tipo = data.get("type")
    permisos = data.get("permissions", [])
    if not isinstance(permisos, list) or not all(isinstance(p, str) and p in PERMISOS for p in permisos):
        raise ValueError("Permisos no reconocidos")
    if tipo == "source":
        if "execute_python" not in permisos:
            raise ValueError("Un plugin Python debe declarar execute_python")
        relativa(data.get("entrypoint", ""))
        if not data["entrypoint"].endswith(".py"):
            raise ValueError("El punto de entrada debe ser un archivo Python")
    elif tipo == "content":
        if permisos:
            raise ValueError("Un paquete de contenido no puede pedir permisos de ejecución")
        relativa(data.get("content", ""))
    else:
        raise ValueError("Tipo de extensión no compatible")
    return data


def relativa(nombre):
    if not isinstance(nombre, str) or not nombre or "\\" in nombre or "\x00" in nombre:
        raise ValueError("Ruta de paquete no válida")
    p = PurePosixPath(nombre)
    if (not p.parts or p.is_absolute() or any(x in ("..", ".") for x in p.parts)
            or ":" in nombre or p.as_posix() != nombre.rstrip("/")):
        raise ValueError("El paquete contiene una ruta fuera de su carpeta")
    return nombre


def inspeccionar(ruta):
    p = Path(ruta)
    if p.stat().st_size > MAX_PAQUETE:
        raise ValueError("El paquete supera 150 MB")
    with zipfile.ZipFile(p) as z:
        infos = z.infolist()
        if len(infos) > 3000 or sum(i.file_size for i in infos) > MAX_PAQUETE:
            raise ValueError("El contenido descomprimido del paquete es demasiado grande")
        vistos = set()
        for i in infos:
            relativa(i.filename)
            if i.filename in vistos or (i.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("El paquete contiene duplicados o enlaces simbólicos")
            vistos.add(i.filename)
        if "manifest.json" not in vistos or z.getinfo("manifest.json").file_size > 64000:
            raise ValueError("Falta un manifest.json válido")
        data = manifiesto(json.loads(z.read("manifest.json")))
        entry = data.get("entrypoint") if data["type"] == "source" else data["content"]
        if entry not in vistos:
            raise ValueError("Falta el archivo principal declarado")
        if data["type"] == "content":
            if any(Path(i.filename).suffix.lower() in (".py", ".sh", ".exe", ".so", ".js") for i in infos):
                raise ValueError("Un paquete de contenido no puede incluir código ejecutable")
            validar_contenido(json.loads(z.read(entry)), lambda path: z.read(relativa(path)))
    return data


def instalar(ruta):
    raiz = ruta_base()
    raiz.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=raiz, prefix=".instalando-") as tmp:
        copia = Path(tmp) / "paquete.zip"
        with Path(ruta).open("rb") as f:
            datos = f.read(MAX_PAQUETE + 1)
        if len(datos) > MAX_PAQUETE:
            raise ValueError("El paquete supera 150 MB")
        copia.write_bytes(datos)
        data = inspeccionar(copia)
        destino = raiz / data["id"] / data["version"]
        if destino.exists():
            raise ValueError("Esta versión ya está instalada; usa una versión nueva para actualizar")
        extraido = Path(tmp) / "contenido"
        extraido.mkdir()
        with zipfile.ZipFile(copia) as z:
            for info in z.infolist():
                relativa(info.filename)
                if info.is_dir():
                    continue
                target = extraido / info.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(info))
        destino.parent.mkdir(parents=True, exist_ok=True)
        extraido.rename(destino)
    return {**data, "path": str(destino), "builtin": False}


def listar(con):
    salida = [{"id": i, "name": n, "type": t, "permissions": p, "version": "1.0.0",
               "api_version": 1, "builtin": True} for i, n, t, p in INCLUIDAS]
    externos = {}
    if ruta_base().exists():
        for path in sorted(ruta_base().glob("*/*/manifest.json")):
            try:
                m = manifiesto(json.loads(path.read_text(encoding="utf-8")))
                if path.parent.name != m["version"] or path.parent.parent.name != m["id"]:
                    continue
                anterior = externos.get(m["id"])
                if not anterior or tuple(map(int, m["version"].split("."))) > tuple(map(int, anterior["version"].split("."))):
                    externos[m["id"]] = {**m, "builtin": False, "path": str(path.parent)}
            except (OSError, ValueError):
                continue
    salida += list(externos.values())
    for m in salida:
        cfg = config(con, m["id"])
        # Cada nueva versión de código requiere activación; no hereda confianza.
        m["enabled"] = cfg.get("enabled", m["builtin"]) and (m["builtin"] or cfg.get("trusted_version") == m["version"])
    return salida


def activar(con, item, activo):
    configurar(con, item["id"], enabled=bool(activo), trusted_version=item["version"] if activo else "")


def habilitada(con, ident):
    return any(m["id"] == ident and m["enabled"] for m in listar(con))


def ejecutar(item, operacion, payload=None, ajustes=None):
    if item.get("builtin") or item.get("type") != "source" or not item.get("enabled"):
        raise ValueError("El plugin no está activado")
    if operacion not in ("search", "preview"):
        raise ValueError("Operación de plugin no admitida")
    path = Path(item["path"]).resolve()
    entry = (path / relativa(item["entrypoint"])).resolve()
    if not entry.is_relative_to(path):
        raise ValueError("Punto de entrada fuera del paquete")
    peticion = json.dumps({"api_version": 1, "operation": operacion,
                          "payload": payload or {}, "config": ajustes or {}}, ensure_ascii=False).encode()
    if len(peticion) > fuentes.MAX_TEXTO:
        raise ValueError("Solicitud de plugin demasiado grande")
    with tempfile.TemporaryFile() as inp, tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        inp.write(peticion)
        inp.seek(0)
        env = {k: os.environ[k] for k in ("PATH", "LANG", "LC_ALL") if k in os.environ}
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.Popen([sys.executable, "-I", str(entry)], cwd=path, env=env,
                                stdin=inp, stdout=out, stderr=err, start_new_session=True)
        import signal
        try:
            fin = time.monotonic() + 30
            while proc.poll() is None:
                if time.monotonic() > fin or os.fstat(out.fileno()).st_size + os.fstat(err.fileno()).st_size > fuentes.MAX_TEXTO:
                    raise ValueError("El plugin excedió el tiempo o el tamaño de respuesta")
                time.sleep(0.05)
            if proc.returncode:
                raise ValueError("El plugin falló; revisa su configuración")
            out.seek(0)
            raw = out.read(fuentes.MAX_TEXTO + 1)
            if len(raw) > fuentes.MAX_TEXTO:
                raise ValueError("Respuesta de plugin demasiado grande")
            result = json.loads(raw)
        finally:
            # Cierra también los procesos auxiliares del plugin.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
    if operacion == "search":
        if not isinstance(result, list) or len(result) > 150:
            raise ValueError("El plugin debe devolver hasta 150 resultados")
        return [fuentes.validar_documento({**r, "provider": item["id"], "text": r.get("text", "")}) for r in result]
    return fuentes.validar_documento({**result, "provider": item["id"]})


def validar_contenido(data, leer_archivo=None):
    from . import exportador
    if not isinstance(data, dict) or data.get("format") != 1:
        raise ValueError("Formato de contenido no compatible")
    crudas = data.get("cards", [])
    if not isinstance(crudas, list):
        raise ValueError("Lista de tarjetas no válida")
    preparadas = []
    for card in crudas:
        if not isinstance(card, dict):
            raise ValueError("Tarjeta no válida")
        media = card.get("media", [])
        if not isinstance(media, list):
            raise ValueError("Lista de adjuntos no válida")
        adjuntos = []
        for a in media:
            if not isinstance(a, dict):
                raise ValueError("Adjunto no válido")
            if "path" in a:
                if not leer_archivo:
                    raise ValueError("No se puede resolver el adjunto")
                import base64
                a = {**a, "data": base64.b64encode(leer_archivo(relativa(a["path"]))).decode("ascii")}
            adjuntos.append(a)
        preparadas.append({**card, "media": adjuntos})
    cards = exportador.validar_tarjetas(preparadas)
    docs = data.get("documents", [])
    if not isinstance(docs, list) or len(docs) > 1000:
        raise ValueError("El paquete contiene demasiados documentos")
    salida = []
    for d in docs:
        if not isinstance(d, dict):
            raise ValueError("Documento de paquete no válido")
        if "path" in d:
            if not leer_archivo:
                raise ValueError("No se puede resolver el recurso del paquete")
            text = leer_archivo(relativa(d["path"])).decode("utf-8-sig")
            d = {**d, "text": text}
        salida.append(fuentes.validar_documento({"provider": "paquete", **d}))
    return {"cards": cards, "documents": salida}


def contenido(item):
    if not item.get("enabled") or item["type"] != "content":
        raise ValueError("Activa el paquete para importar su contenido")
    path = Path(item["path"]).resolve()
    def leer(nombre):
        p = (path / relativa(nombre)).resolve()
        if not p.is_relative_to(path) or p.stat().st_size > MAX_PAQUETE:
            raise ValueError("Recurso fuera del paquete o demasiado grande")
        return p.read_bytes()
    return validar_contenido(json.loads(leer(item["content"])), leer)


def empaquetar(carpeta, destino):
    raiz, target = Path(carpeta).resolve(), Path(destino).resolve()
    if target.is_relative_to(raiz):
        raise ValueError("Guarda el ZIP fuera de la carpeta del plugin")
    manifiesto(json.loads((raiz / "manifest.json").read_text(encoding="utf-8")))
    with tempfile.TemporaryDirectory(prefix="appstudy-paquete-") as tmp:
        archivo = Path(tmp) / "paquete.zip"
        with zipfile.ZipFile(archivo, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(raiz.rglob("*")):
                if p.is_symlink():
                    raise ValueError("No se empaquetan enlaces simbólicos")
                if p.is_file() and "__pycache__" not in p.parts:
                    z.write(p, p.relative_to(raiz).as_posix())
        inspeccionar(archivo)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise ValueError("El archivo de destino ya existe")
        target.write_bytes(archivo.read_bytes())
    return target


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Crear un paquete instalable de AppStudy")
    parser.add_argument("carpeta")
    parser.add_argument("destino")
    args = parser.parse_args()
    print(empaquetar(args.carpeta, args.destino))
