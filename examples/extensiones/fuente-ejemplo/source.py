"""Ejemplo mínimo del protocolo JSON: no usa red ni archivos del usuario."""
import json
import sys

DOC = {"origin": "demo:tarjetas", "title": "Una pregunta por tarjeta",
       "text": "# Una pregunta por tarjeta\n\nUna tarjeta clara plantea una sola pregunta. Su respuesta debe permitir comprobar si la recordaste.",
       "author": "Ejemplo de AppStudy", "license": "CC0-1.0"}


def main():
    request = json.load(sys.stdin)
    if request.get("api_version") != 1:
        raise ValueError("API no compatible")
    if request["operation"] == "search":
        query = request["payload"].get("query", "").casefold()
        result = [DOC] if query in (DOC["title"] + " " + DOC["text"]).casefold() else []
    elif request["operation"] == "preview" and request["payload"].get("origin") == DOC["origin"]:
        result = DOC
    else:
        raise ValueError("Operación o documento no reconocido")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
