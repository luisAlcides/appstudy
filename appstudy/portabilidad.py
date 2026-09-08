"""Identidades de libros por contenido y relojes de sus anotaciones."""
import hashlib
import uuid
from pathlib import Path


def identidad(ruta):
    try:
        with Path(ruta).open('rb') as archivo:
            return 'sha256:' + hashlib.file_digest(archivo, 'sha256').hexdigest()
    except OSError:
        return 'book:' + uuid.uuid4().hex


def preparar(con):
    for tabla in ('books', 'notas'):
        columnas = {r['name'] for r in con.execute(f'PRAGMA table_info({tabla})')}
        if not columnas:
            continue
        if 'uid' not in columnas:
            con.execute(f"ALTER TABLE {tabla} ADD COLUMN uid TEXT NOT NULL DEFAULT ''")
        for fila in con.execute(f"SELECT * FROM {tabla} WHERE uid='' ").fetchall():
            uid = identidad(fila['ruta']) if tabla == 'books' else uuid.uuid4().hex
            con.execute(f'UPDATE {tabla} SET uid=? WHERE id=?', (uid, fila['id']))
        if tabla == 'books':
            # Dos copias locales del mismo contenido comparten una sola ficha.
            for grupo in con.execute('SELECT uid FROM books GROUP BY uid HAVING COUNT(*)>1').fetchall():
                copias = con.execute('SELECT * FROM books WHERE uid=? ORDER BY abierto DESC,id', (grupo['uid'],)).fetchall()
                for copia in copias[1:]:
                    for referencia in ('notas', 'card_sources'):
                        con.execute(f'UPDATE {referencia} SET ruta=? WHERE ruta=?', (copias[0]['ruta'], copia['ruta']))
                    con.execute('DELETE FROM books WHERE id=?', (copia['id'],))
            con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_books_uid ON books(uid) WHERE uid!=''")
        entity = 'book' if tabla == 'books' else 'note' 
        con.execute("""INSERT OR IGNORE INTO sync_changes SELECT ?,uid,
                    (julianday('now')-2440587.5)*86400,0 FROM """ + tabla, (entity,))
        for evento in ('INSERT', 'UPDATE', 'DELETE'):
            ref = 'OLD' if evento == 'DELETE' else 'NEW'
            con.execute(f"""CREATE TRIGGER IF NOT EXISTS portable_{tabla}_{evento}
                AFTER {evento} ON {tabla} WHEN {ref}.uid != '' BEGIN
                INSERT INTO sync_changes(entity,uid,modified,deleted)
                VALUES('{entity}',{ref}.uid,(julianday('now')-2440587.5)*86400,{int(evento == 'DELETE')})
                ON CONFLICT(entity,uid) DO UPDATE SET
                modified=MAX(excluded.modified,sync_changes.modified+0.000001),
                deleted=excluded.deleted; END""")
    for tabla in ('cards', 'state', 'log', 'chapters', 'reading', 'books', 'notas', 'card_sources', 'sync_changes'):
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabla,)).fetchone():
            continue
        for evento in ('INSERT', 'UPDATE', 'DELETE'):
            con.execute(f"""CREATE TRIGGER IF NOT EXISTS revision_{tabla}_{evento}
                AFTER {evento} ON {tabla} BEGIN
                INSERT INTO meta(k,v) VALUES('data_revision','1')
                ON CONFLICT(k) DO UPDATE SET v=CAST(v AS INTEGER)+1; END""")


def vincular(con, ruta):
    """Reconoce un PDF trasladado sin reemplazar su progreso por valores vacíos."""
    actual = con.execute('SELECT uid FROM books WHERE ruta=?', (str(ruta),)).fetchone()
    if actual and actual['uid'].startswith('sha256:'):
        return actual['uid']
    uid = identidad(ruta)
    if actual and not uid.startswith('sha256:'):
        return actual['uid']
    anterior = con.execute('SELECT ruta FROM books WHERE uid=?', (uid,)).fetchone()
    if anterior and anterior['ruta'] != str(ruta):
        vieja = anterior['ruta']
        if actual:
            con.execute('DELETE FROM books WHERE ruta=?', (str(ruta),))
        con.execute('UPDATE books SET ruta=? WHERE uid=?', (str(ruta), uid))
        con.execute('UPDATE notas SET ruta=? WHERE ruta=?', (str(ruta), vieja))
        con.execute('UPDATE card_sources SET ruta=? WHERE ruta=?', (str(ruta), vieja))
    return uid
