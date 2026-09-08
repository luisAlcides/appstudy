"""Comprobación optativa de los servicios reales, fuera de la suite sin red.

    python3 -m tests.verificar_fuentes_online
"""
from appstudy import fuentes


def main():
    errores = 0
    for provider in ("wikipedia", "openstax", "mit"):
        try:
            resultados = fuentes.buscar(provider, "Linux" if provider == "wikipedia" else "")
            item = resultados[0]
            preview = fuentes.previsualizar(item)
            if len(preview["text"]) < 100:
                raise ValueError("No se extrajo contenido suficiente")
            print(f"{provider}: OK · {len(preview['text'])} caracteres · {len(preview.get('links', []))} materiales", flush=True)
        except Exception as e:
            errores += 1
            print(f"{provider}: ERROR · {e}", flush=True)
    return int(bool(errores))


if __name__ == "__main__":
    raise SystemExit(main())
