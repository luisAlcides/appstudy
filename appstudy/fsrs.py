"""FSRS: el modelo de memoria que decide cuándo vuelve una tarjeta.

Aquí no hay base de datos ni interfaz, solo las fórmulas, para poder probarlas
sin abrir nada. Quien las usa es `scheduler.py`.

La idea, en corto. SM-2 llevaba un «factor de facilidad» que subía o bajaba a
ojo. FSRS modela tres cosas separadas:

- **Estabilidad** (S), en días: cuánto aguanta un recuerdo. Es, por definición,
  los días que pasan hasta que la probabilidad de acordarte cae al 90 %.
- **Dificultad** (D), de 1 a 10: lo que cuesta esa tarjeta en concreto.
- **Recuperabilidad** (R), de 0 a 1: la probabilidad de que ahora mismo te
  acuerdes, que baja con los días transcurridos.

Con eso, el intervalo deja de ser una multiplicación ciega: se calcula el día en
que R cae hasta la **retención objetivo** que tú elijas. Pedir 90 % da repasos
más espaciados que pedir 95 %, y la cuenta la hace la fórmula, no una constante.

Los diecinueve pesos son los de FSRS-5, los mismos que trae Anki de fábrica,
ajustados sobre millones de repasos reales. `calibrar()` los reajusta con *tu*
historial cuando ya tienes suficiente.
"""
import math

# Pesos por defecto de FSRS-5. Funcionan bien sin tocar nada; `calibrar()` los
# mueve a partir de tu propio historial.
W_POR_DEFECTO = (
    0.40255, 1.18385, 3.173, 15.69105,      # 0-3  estabilidad inicial por nota
    7.1949, 0.5345,                          # 4-5  dificultad inicial
    1.4604, 0.0046,                          # 6-7  cambio de dificultad y reversión
    1.54575, 0.1192, 1.01925,                # 8-10 estabilidad al acertar
    1.9395, 0.11, 0.29605, 2.2698,           # 11-14 estabilidad al fallar
    0.2315, 2.9898,                          # 15-16 castigo de «difícil», premio de «fácil»
    0.51655, 0.6621,                         # 17-18 repasos del mismo día
)

# La curva de olvido es una potencia, no una exponencial: se ajusta bastante
# mejor a cómo se olvida de verdad. DECAY sale del ajuste original de FSRS.
DECAY = -0.5
FACTOR = 0.9 ** (1 / DECAY) - 1        # 19/81; hace que R(S, S) = 0.9 exacto

D_MIN, D_MAX = 1.0, 10.0
S_MIN = 0.01                            # un recuerdo nunca es exactamente cero
S_MAX = 36500.0

# Notas, con los mismos números que usa el resto de la aplicación (0..3)
OTRA_VEZ, DIFICIL, BIEN, FACIL = 0, 1, 2, 3


def _acotar(valor, minimo, maximo):
    return max(minimo, min(maximo, valor))


def recuperabilidad(dias: float, estabilidad: float) -> float:
    """Probabilidad de acordarte pasados `dias` desde el último repaso."""
    if estabilidad <= 0:
        return 0.0
    return (1 + FACTOR * max(0.0, dias) / estabilidad) ** DECAY


def intervalo(estabilidad: float, retencion: float = 0.9) -> float:
    """Días hasta que la probabilidad de acordarte baje a `retencion`."""
    retencion = _acotar(retencion, 0.70, 0.99)
    return (estabilidad / FACTOR) * (retencion ** (1 / DECAY) - 1)


def estabilidad_inicial(nota: int, w=W_POR_DEFECTO) -> float:
    """Lo que aguanta una tarjeta la primera vez, según cómo te fue."""
    return _acotar(w[_acotar(nota, 0, 3)], S_MIN, S_MAX)


def dificultad_inicial(nota: int, w=W_POR_DEFECTO) -> float:
    """Lo difícil que parece una tarjeta la primera vez que la ves."""
    return _acotar(w[4] - math.exp(w[5] * nota) + 1, D_MIN, D_MAX)


def siguiente_dificultad(dificultad: float, nota: int, w=W_POR_DEFECTO) -> float:
    """La dificultad se mueve con cada nota y tira despacio hacia la de «fácil».

    El amortiguado `(10 - D) / 9` hace que a una tarjeta ya muy difícil le cueste
    más empeorar: si no, unos cuantos fallos la clavaban en 10 para siempre.
    """
    delta = -w[6] * (nota - BIEN)
    movida = dificultad + delta * (D_MAX - dificultad) / 9
    # Reversión a la media: sin esto, la dificultad solo sabe subir.
    revertida = w[7] * dificultad_inicial(FACIL, w) + (1 - w[7]) * movida
    return _acotar(revertida, D_MIN, D_MAX)


def estabilidad_tras_acierto(dificultad, estabilidad, r, nota, w=W_POR_DEFECTO) -> float:
    """Cuánto crece la memoria al acertar.

    Crece más cuanto más a punto de olvidarlo estabas (`1 - r`): repasar algo
    que ya te sabías de sobra apenas aporta. Esa es la idea central del método.
    """
    penaliza = w[15] if nota == DIFICIL else 1.0
    premia = w[16] if nota == FACIL else 1.0
    crecimiento = (math.exp(w[8])
                   * (11 - dificultad)
                   * estabilidad ** -w[9]
                   * (math.exp(w[10] * (1 - r)) - 1)
                   * penaliza * premia)
    return _acotar(estabilidad * (1 + crecimiento), S_MIN, S_MAX)


def estabilidad_tras_fallo(dificultad, estabilidad, r, w=W_POR_DEFECTO) -> float:
    """Lo que queda de la memoria después de un fallo. Nunca sube."""
    largo = (w[11]
             * dificultad ** -w[12]
             * ((estabilidad + 1) ** w[13] - 1)
             * math.exp(w[14] * (1 - r)))
    corto = estabilidad / math.exp(w[17] * w[18])
    return _acotar(min(largo, corto), S_MIN, S_MAX)


def estabilidad_mismo_dia(estabilidad: float, nota: int, w=W_POR_DEFECTO) -> float:
    """Repasar algo el mismo día consolida un poco, pero no como un repaso real."""
    return _acotar(estabilidad * math.exp(w[17] * (nota - BIEN + w[18])),
                   S_MIN, S_MAX)


# ------------------------------------------------------------------ calibración

# Por debajo de esto el ajuste sería ruido: los pesos de fábrica salen de
# millones de repasos y no se mejoran con doscientos.
MINIMO_REPASOS = 400

# Cada peso se mueve dentro de lo razonable; fuera de aquí las fórmulas dejan de
# tener sentido (una estabilidad negativa, una dificultad que se dispara).
LIMITES = (
    (0.01, 60.0), (0.01, 60.0), (0.01, 60.0), (0.01, 60.0),
    (1.0, 10.0), (0.001, 4.0),
    (0.001, 4.0), (0.001, 0.75),
    (0.0, 4.5), (0.0, 0.8), (0.001, 3.5),
    (0.001, 5.0), (0.001, 0.25), (0.001, 0.9), (0.0, 4.0),
    (0.0, 1.0), (1.0, 6.0),
    (0.0, 2.0), (0.0, 2.0),
)


def _perdida(revisiones, w) -> float:
    """Log-loss: cuánto se equivoca el modelo prediciendo tus aciertos.

    Cada repaso es una predicción («con estos días transcurridos, ¿te vas a
    acordar?») que se puede comparar con lo que de verdad pasó. Menos es mejor.
    """
    total, n = 0.0, 0
    for historial in revisiones:
        s = d = None
        anterior = None
        for ts, nota in historial:
            if s is None:
                s = estabilidad_inicial(nota, w)
                d = dificultad_inicial(nota, w)
                anterior = ts
                continue
            dias = max(0.0, (ts - anterior) / 86400.0)
            r = recuperabilidad(dias, s)
            acerto = 1.0 if nota != OTRA_VEZ else 0.0
            p = _acotar(r, 1e-6, 1 - 1e-6)
            total -= acerto * math.log(p) + (1 - acerto) * math.log(1 - p)
            n += 1
            d = siguiente_dificultad(d, nota, w)
            if dias < 1.0:
                s = estabilidad_mismo_dia(s, nota, w)
            elif nota == OTRA_VEZ:
                s = estabilidad_tras_fallo(d, s, r, w)
            else:
                s = estabilidad_tras_acierto(d, s, r, nota, w)
            anterior = ts
    return total / n if n else float("inf")


def calibrar(revisiones, w=W_POR_DEFECTO, vueltas: int = 6, progreso=None):
    """Ajusta los pesos a tu propio historial. Devuelve (pesos, antes, después).

    `revisiones` es una lista por tarjeta de [(timestamp, nota), ...] en orden.

    El método es descenso por coordenadas: se prueba a mover cada peso arriba y
    abajo, se deja donde la predicción mejora, y se repite con pasos cada vez más
    cortos. Es lento comparado con un optimizador de verdad, pero cabe en la
    biblioteca estándar, es determinista y no puede empeorar el punto de partida:
    si ningún movimiento mejora, devuelve los pesos con los que entró.
    """
    actuales = list(w)
    inicial = mejor = _perdida(revisiones, actuales)
    if not math.isfinite(inicial):
        return tuple(actuales), inicial, inicial

    paso = 0.5
    for vuelta in range(vueltas):
        for i, (bajo, alto) in enumerate(LIMITES):
            margen = (alto - bajo) * paso
            for candidato in (actuales[i] - margen, actuales[i] + margen):
                candidato = _acotar(candidato, bajo, alto)
                if candidato == actuales[i]:
                    continue
                previo = actuales[i]
                actuales[i] = candidato
                puntos = _perdida(revisiones, actuales)
                if puntos < mejor:
                    mejor = puntos
                else:
                    actuales[i] = previo
        paso *= 0.5
        if progreso:
            progreso((vuelta + 1) / vueltas, mejor)
    return tuple(actuales), inicial, mejor
