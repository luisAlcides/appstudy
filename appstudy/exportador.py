"""Exportaciones reutilizables; JSON y paquetes conservan tipos y adjuntos."""
import csv
import io
import json
from pathlib import Path
import tempfile
import zipfile

from . import multimedia


def tarjetas(con, deck_id=None):
    sql = "SELECT c.*,d.key AS deck,d.name AS deck_name FROM cards c JOIN decks d ON d.id=c.deck_id"
    args = ()
    if deck_id is not None:
        sql += " WHERE deck_id=?"
        args = (deck_id,)
    salida = []
    for r in con.execute(sql + " ORDER BY d.pos,c.id", args):
        t = {k: r[k] for k in ("front", "back", "kind", "hint", "tags", "level", "answer", "deck")}
        t["choices"] = json.loads(r["choices"]) if r["choices"] else []
        t["media"] = multimedia.serializar(multimedia.leer(con, r["id"]))
        fuente = con.execute("SELECT * FROM card_sources WHERE card_id=?", (r["id"],)).fetchone()
        if fuente:
            t["source"] = {k: fuente[k] for k in fuente.keys() if k != "card_id"}
        salida.append(t)
    return salida


def guardar(destino, cards, formato="json", title="Mis tarjetas"):
    """Archivo temporal y reemplazo atómico: un fallo no deja media exportación."""
    path = Path(destino)
    path.parent.mkdir(parents=True, exist_ok=True)
    if formato not in ("json", "csv", "tsv", "zip"):
        raise ValueError("Formato de exportación no compatible")
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        temporal = Path(f.name)
    try:
        if formato in ("csv", "tsv"):
            with temporal.open("w", encoding="utf-8", newline="") as f:
                w = csv.writer(f, delimiter="\t" if formato == "tsv" else ",")
                w.writerow(["front", "back", "tags", "deck", "hint"])
                for c in cards:
                    # No ejecutar fórmulas al abrir la exportación en una hoja de cálculo.
                    vals = [str(c.get(k, "")) for k in ("front", "back", "tags", "deck", "hint")]
                    w.writerow(["'" + v if v.startswith(("=", "+", "-", "@")) else v for v in vals])
        elif formato == "json":
            temporal.write_text(json.dumps({"format": 1, "cards": cards}, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("manifest.json", json.dumps({"id": "mis-tarjetas", "name": title,
                    "version": "1.0.0", "api_version": 1, "type": "content", "permissions": [],
                    "content": "content.json"}, ensure_ascii=False))
                z.writestr("content.json", json.dumps({"format": 1, "cards": cards, "documents": []}, ensure_ascii=False))
        temporal.replace(path)
    finally:
        temporal.unlink(missing_ok=True)
    return path


def validar_tarjetas(cards):
    if not isinstance(cards, list) or len(cards) > 5000:
        raise ValueError("El paquete debe contener hasta 5.000 tarjetas")
    salida, total = [], 0
    for t in cards:
        if not isinstance(t, dict) or not isinstance(t.get("front"), str) or not t["front"].strip():
            raise ValueError("Una tarjeta no tiene pregunta")
        kind = t.get("kind", "card")
        if kind not in ("card", "cloze", "quiz", "lesson"):
            raise ValueError("Tipo de tarjeta no reconocido")
        choices, answer = t.get("choices", []), t.get("answer", -1)
        if kind == "quiz" and (not isinstance(choices, list) or not 2 <= len(choices) <= 20 or
                               not all(isinstance(x, str) for x in choices) or
                               type(answer) is not int or not 0 <= answer < len(choices)):
            raise ValueError("Opciones de examen no válidas")
        if kind == "cloze" and not re_cloze(t["front"]):
            raise ValueError("La tarjeta de huecos no contiene huecos")
        for k in ("back", "hint", "tags", "deck"):
            if not isinstance(t.get(k, ""), str):
                raise ValueError(f"Campo {k} no válido")
        level = t.get("level", 1)
        if type(level) is not int or not 1 <= level <= 20:
            raise ValueError("Nivel de tarjeta no válido")
        media = multimedia.deserializar(t.get("media", []))
        total += sum(len(a["data"]) for a in media)
        if total > multimedia.MAX_TOTAL:
            raise ValueError("Los adjuntos superan 100 MB")
        salida.append({**t, "media": media})
    return salida


def re_cloze(texto):
    from . import cloze
    return cloze.tiene_huecos(texto)
