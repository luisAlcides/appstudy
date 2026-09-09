"""Trae contenido nuevo y decide si vale la pena. El único módulo con red.

«Calidad» tiene que ser algo que el código pueda decidir, así que son siete
comprobaciones con un motivo legible cada una. El motivo se guarda también
cuando se rechaza: sin eso, «no me trae nada» sería indepurable.

Toda la red pasa por `fuentes.descargar`, que valida HTTPS, dominio en lista
blanca, cada redirección y el tamaño del cuerpo.
"""
from __future__ import annotations

import json
import re
import time

from . import catalogo, db, fuentes, selector

MIN_PALABRAS, MAX_PALABRAS = 400, 20000
MIN_PROSA = 0.35            # renglones que son frases, no entradas de un menú
MIN_RELEVANCIA = 0.20
UMBRAL = 0.5

# Palabras vacías: bastan para distinguir un idioma de otro sin dependencias.
# No hay que acertar siempre, solo no colar un texto en inglés en un mazo en
# español y al revés.
_ES = {"de", "la", "que", "el", "en", "y", "los", "se", "del", "las", "un", "por",
       "con", "una", "para", "es", "al", "lo", "como", "más", "o", "si", "su",
       "sus", "este", "esta", "son", "pero", "sobre", "entre", "cuando"}
_EN = {"the", "of", "and", "to", "in", "a", "is", "that", "for", "it", "as", "with",
       "on", "be", "by", "this", "are", "from", "or", "an", "which", "you", "at",
       "was", "were", "can", "has", "have", "its", "not", "but", "when"}


def idioma(texto: str) -> str:
    palabras = re.findall(r"[a-záéíóúñü]+", texto.lower())[:2000]
    if not palabras:
        return "?"
    return "es" if sum(p in _ES for p in palabras) >= sum(p in _EN for p in palabras) else "en"


def nivel_de(texto: str, cuantos: int = 3) -> int:
    """Frases largas y palabras largas.

    Es lo más parecido a «dificultad» que se puede medir sin entender el texto,
    y basta para colocar un capítulo en su nivel dentro del mazo.
    """
    frases = [f for f in re.split(r"[.!?]+", texto) if f.strip()]
    palabras = texto.split()
    if not frases or not palabras:
        return 1
    media = len(palabras) / len(frases)
    largas = sum(len(p) > 9 for p in palabras) / len(palabras)
    if media < 16 and largas < 0.14:
        return 1
    if media < 24 and largas < 0.22:
        return min(2, cuantos)
    return min(3, cuantos)


def _prosa(texto: str) -> float:
    renglones = [l.strip() for l in texto.splitlines() if l.strip()]
    if not renglones:
        return 0.0
    return sum(len(l.split()) >= 8 for l in renglones) / len(renglones)


RAIZ = 6      # letras que se comparan de cada palabra


def _relevancia(doc: dict, plan: dict) -> float:
    """Cuánto tiene que ver el documento con lo que se pidió.

    Se compara por raíz y no por palabra entera: en español «electricidad» y
    «eléctrica» son lo mismo para esto, y exigir la palabra exacta descartaría
    casi todo lo que de verdad sirve.
    """
    # Cuando el término es el nombre del mazo no hay nada que medir: la fuente
    # ya está elegida por mazo, y «Inglés» no sale en un texto en inglés.
    if plan.get("origen_terminos") != "fallos":
        return 1.0
    campo = fuentes.clave(doc["title"] + " " + doc.get("text", "")[:3000])
    partes = [p for t in plan["terminos"] for p in fuentes.clave(t).split() if len(p) > 3]
    if not partes:
        return 1.0
    return sum(p[:RAIZ] in campo for p in partes) / len(partes)


MIN_RESUMEN = 20        # palabras mínimas para que un enlace valga la pena


def _duplicado(con, doc, plan, no):
    """Los dos avisos de «esto ya lo tienes», compartidos por las dos ramas."""
    if con.execute("SELECT 1 FROM source_imports WHERE provider=? AND origin=? AND deck_id=?",
                   (doc["provider"], doc["origin"], plan["deck"]["id"])).fetchone():
        return no("ya lo tienes importado en este mazo")
    if con.execute("SELECT 1 FROM inbox WHERE provider=? AND origin=? AND deck_id=?",
                   (doc["provider"], doc["origin"], plan["deck"]["id"])).fetchone():
        return no("ya está esperando en la bandeja")
    return None


def _filtrar_enlace(con, doc: dict, plan: dict, no):
    """Fuentes cuya licencia no permite guardar el texto.

    Entran con su título, su resumen y su enlace, que es lo que sí se puede
    guardar. Un resumen de dos palabras no vale para nada, así que se exige que
    diga algo.
    """
    resumen = (doc.get("summary") or "").strip()
    if len(resumen.split()) < MIN_RESUMEN:
        return no("solo-enlace y sin un resumen que merezca la pena")
    repetido = _duplicado(con, doc, plan, no)
    if repetido:
        return repetido
    return {"ok": True, "score": 0.5, "nivel": 1, "enlace": True,
            "motivo": f"{plan['motivo']} · solo enlace: la licencia no permite "
                      "guardar el texto"}


def filtrar(con, doc: dict, plan: dict) -> dict:
    """Si el documento entra, con qué nota y por qué. Nunca lanza."""
    def no(motivo, score=0.0):
        return {"ok": False, "score": score, "nivel": 1, "motivo": motivo}

    if not catalogo.abierta(doc["provider"]):
        return _filtrar_enlace(con, doc, plan, no)
    texto = doc.get("text", "") or ""
    palabras = len(texto.split())
    if palabras < MIN_PALABRAS:
        return no(f"demasiado corto: {palabras} palabras")
    if palabras > MAX_PALABRAS:
        return no(f"demasiado largo: {palabras} palabras")
    titulo = fuentes.clave(doc.get("title", ""))
    if "desambiguacion" in titulo or "disambiguation" in titulo:
        return no("es una página de desambiguación, no un artículo")
    prosa = _prosa(texto)
    if prosa < MIN_PROSA:
        return no(f"no es prosa: solo el {prosa:.0%} de los renglones son frases")
    esperado = "en" if plan["deck"]["key"] == "ingles" else "es"
    if idioma(texto) != esperado:
        return no(f"idioma equivocado: se esperaba {esperado}")
    relevancia = _relevancia(doc, plan)
    if relevancia < MIN_RELEVANCIA:
        return no(f"poco que ver con {', '.join(plan['terminos'])}", round(relevancia, 3))
    if con.execute("SELECT 1 FROM source_imports WHERE fingerprint=? AND deck_id=?",
                   (fuentes.huella(doc), plan["deck"]["id"])).fetchone():
        return no("ya lo tienes importado en este mazo")
    repetido = _duplicado(con, doc, plan, no)
    if repetido:
        return repetido
    score = round(0.5 * min(1.0, relevancia * 2) + 0.3 * prosa +
                  0.2 * min(1.0, palabras / 1500), 3)
    return {"ok": score >= UMBRAL, "score": score,
            "nivel": nivel_de(texto, len(selector.niveles(plan["deck"]))),
            "motivo": plan["motivo"] if score >= UMBRAL else f"nota baja: {score}"}


CADA = 86400
POR_RACION = 1
TARJETAS_POR_LECTURA = 6
CANDIDATOS_POR_FUENTE = 5
MAX_RECHAZOS_GUARDADOS = 40
MIN_APOYO = 0.5           # cuánto de la respuesta debe estar en el texto de origen


def _tarjetas(con, doc: dict) -> list:
    """Tarjetas de la IA local, validadas contra el texto de origen.

    Dos validaciones que `ia.generar_desde_texto` no hace: que la respuesta
    aparezca de verdad en el texto —contra las invenciones del modelo— y que el
    enunciado no repita una tarjeta que ya tienes.

    Si el modelo no está, no pasa nada: el capítulo se guarda igual y la
    bandeja ofrece generarlas más tarde.
    """
    from . import ia
    try:
        cfg = ia.config(con)
        if not cfg.get("activa", True):
            return []
        propuestas = ia.generar_desde_texto(cfg, doc["text"][:6000], doc["title"],
                                            TARJETAS_POR_LECTURA)
    except Exception:          # IAError, red, modelo ausente: da igual cuál sea
        return []
    cuerpo = fuentes.clave(doc["text"])
    ya = {fuentes.clave(r["front"]) for r in con.execute("SELECT front FROM cards")}
    salida = []
    for t in propuestas:
        frente, dorso = t.get("front", "").strip(), t.get("back", "").strip()
        if not frente:
            continue
        pistas = [p for p in fuentes.clave(dorso).split() if len(p) > 4]
        if pistas and sum(p in cuerpo for p in pistas) / len(pistas) < MIN_APOYO:
            continue           # el modelo se lo ha inventado: fuera
        if fuentes.clave(frente) in ya:
            continue
        ya.add(fuentes.clave(frente))
        salida.append({"front": frente, "back": dorso})
    return salida


def cosechar(con, plan: dict | None = None, cuantas: int = POR_RACION) -> list:
    """Ejecuta el plan del día y deja en la bandeja lo que pase los filtros."""
    from . import bandeja
    plan = plan or selector.plan(con)
    if not plan:
        return []
    consulta = " ".join(plan["terminos"])
    guardados, rechazos, caidas = [], [], []
    for f in plan["fuentes"]:
        if len(guardados) >= cuantas:
            break
        try:
            candidatos = fuentes.buscar(f["id"], consulta)
        except fuentes.FuenteError as e:
            rechazos.append(f"{f['id']}: {e}")
            caidas.append(f"{f['id']}: {e}")
            continue                 # una fuente caída no tumba a las demás
        solo_enlace = not catalogo.abierta(f["id"])
        for candidato in candidatos[:CANDIDATOS_POR_FUENTE]:
            if len(guardados) >= cuantas:
                break
            if solo_enlace:
                # Ni se pide la página: de aquí solo se puede guardar el enlace,
                # así que descargarla entera sería gastar la red del usuario y
                # la paciencia de la fuente para nada.
                doc = {**candidato, "text": (candidato.get("summary") or "").strip()}
            else:
                try:
                    doc = fuentes.previsualizar(candidato)
                except fuentes.FuenteError as e:
                    rechazos.append(f"{candidato['origin']}: {e}")
                    continue
            veredicto = filtrar(con, candidato if solo_enlace else doc, plan)
            if not veredicto["ok"]:
                rechazos.append(f"{doc['title']} ({f['id']}): {veredicto['motivo']}")
                continue
            doc["cards"] = [] if solo_enlace else _tarjetas(con, doc)
            guardados.append(bandeja.guardar(con, doc, plan, veredicto))
    selector.anotar_intento(con, plan["deck"]["id"], plan["ts"])
    db.set_meta(con, "cosecha_rechazos",
                json.dumps(rechazos[:MAX_RECHAZOS_GUARDADOS], ensure_ascii=False))
    # Que fallen todas suele ser quedarse sin red, y eso sí merece verse en
    # Ajustes. Que fallen algunas es normal y se queda en la lista de rechazos.
    if caidas and len(caidas) == len(plan["fuentes"]):
        raise fuentes.FuenteError(caidas[0].split(": ", 1)[-1])
    return guardados


def auto_si_toca(con, cada: float = CADA) -> bool:
    """Una ración al día, al abrir. Calcado de `respaldo.auto_si_toca`.

    Si falla no se dice nada por pantalla: no poder descargar no debe impedirte
    estudiar, y un aviso en cada arranque sin internet sería insufrible. El
    motivo queda en `meta` y se ve en Ajustes › Fuentes.

    Un fallo tampoco marca el día como cosechado: si abres más tarde con red,
    se vuelve a intentar.
    """
    if str(db.get_meta(con, "cosecha_auto", "1")) in ("0", "False"):
        return False
    try:
        ultimo = float(db.get_meta(con, "cosecha_last", 0) or 0)
    except (TypeError, ValueError):
        ultimo = 0
    if time.time() - ultimo < cada:
        return False
    try:
        hubo = bool(cosechar(con))
        db.set_meta(con, "cosecha_last", time.time())
        db.set_meta(con, "cosecha_error", "")
        return hubo
    except Exception as e:
        db.set_meta(con, "cosecha_error", str(e))
        return False
