"""Plan diario explicable, calculado a partir del progreso local."""
import time
from . import db


def recomendar(con, deck_id=None, ahora=None):
    ahora = time.time() if ahora is None else ahora
    activos = {d['id']: dict(d) for d in con.execute('SELECT * FROM decks WHERE enabled=1')}
    if deck_id not in activos:
        principal = db.get_meta(con, 'bienvenida_tema', '')
        deck_id = next((did for did, d in activos.items() if d['key'] == principal), None)
    caps = [c for c in db.chapters(con) if c['deck_id'] in activos]
    lecturas = {r['chapter_id']: dict(r) for r in con.execute('SELECT * FROM reading')}
    cards = [dict(c) for c in con.execute('''SELECT c.*,s.reps,s.due,s.lapses,s.difficulty,s.leech
        FROM cards c JOIN state s ON s.card_id=c.id JOIN decks d ON d.id=c.deck_id WHERE d.enabled=1''')]
    ultima = max(caps, key=lambda c: lecturas.get(c['id'], {}).get('ts', 0), default=None)
    def dificultad(c):
        tags = {t.strip().lower() for t in c['tags'].split(',') if t.strip()}
        return sum(x['lapses'] + max(0, x['difficulty']-5) for x in cards
                   if x['deck_id'] == c['deck_id'] and x['level'] == c['level']
                   and (not tags or tags.intersection(t.strip().lower() for t in x['tags'].split(','))))
    def prioridad(c):
        rd = lecturas.get(c['id'], {})
        return (c['deck_id'] == deck_id, bool(rd.get('avance')) and not c['leido'],
                rd.get('ts', 0) if not c['leido'] else 0,
                c['deck_id'] == (ultima['deck_id'] if ultima and lecturas.get(ultima['id'], {}).get('ts') else None),
                dificultad(c), -c['level'], -c['pos'], -c['id'])
    pendientes = [c for c in caps if not c['leido']]
    cap = max(pendientes, key=prioridad, default=None)
    if cap is None:
        cap = max((c for c in caps if dificultad(c) > 0), key=prioridad, default=None)
    did = deck_id if deck_id in activos else cap['deck_id'] if cap else next(iter(activos), None)
    elegibles = [c for c in cards if c['deck_id'] == did and not c['leech']]
    reps = min(8, sum(c['reps'] > 0 and c['due'] <= ahora for c in elegibles))
    ejercicios = min(3, sum(bool(c['back']) for c in cards if c['deck_id'] == did))
    razon = ('Retoma tu última lectura' if cap and cap.get('avance') and not cap['leido'] else
             'Refuerza las dificultades detectadas' if cap and dificultad(cap) else 'Avanza en el tema elegido')
    partes = [f'{reps} repasos'] if reps else []
    if cap:
        partes.append(f"una lectura de {cap['minutes']} minutos")
    if ejercicios:
        partes.append(f'{ejercicios} ejercicios')
    return dict(capitulo=cap, repasos=reps, ejercicios=ejercicios, deck=activos.get(did),
                razon=razon, texto='Hoy: ' + ', '.join(partes) if partes else 'Todo al día. Elige un tema para empezar.')
