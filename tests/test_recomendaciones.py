from appstudy import db, recomendaciones
from tests.apoyo import BaseTemporal


class RecomendacionesTest(BaseTemporal):
    def capitulo(self, did, key, titulo, **campos):
        cid, _ = db.upsert_chapter(self.con, did, key, dict(title=titulo, **campos))
        self.con.commit()
        return cid

    def test_tema_elegido_y_ultima_lectura(self):
        a, b = self.mazo(), self.mazo('python', 'Python')
        primero = self.capitulo(a, 'linux', 'Primero')
        segundo = self.capitulo(b, 'python', 'Segundo')
        self.con.execute('UPDATE reading SET avance=.4,ts=100 WHERE chapter_id=?', (segundo,))
        self.assertEqual(recomendaciones.recomendar(self.con)['capitulo']['id'], segundo)
        self.assertEqual(recomendaciones.recomendar(self.con, a)['capitulo']['id'], primero)
        self.con.execute('UPDATE decks SET enabled=0 WHERE id=?', (b,))
        self.assertEqual(recomendaciones.recomendar(self.con)['capitulo']['id'], primero)

    def test_dificultades_y_conteos_reales(self):
        did = self.mazo()
        self.capitulo(did, 'linux', 'Fácil', tags='facil', pos=0)
        dificil = self.capitulo(did, 'linux', 'Difícil', tags='dificil', pos=1)
        cid = self.tarjeta(did, 'Pregunta', tags='dificil')
        self.con.execute('UPDATE state SET reps=3,lapses=2,difficulty=9,due=1 WHERE card_id=?', (cid,))
        plan = recomendaciones.recomendar(self.con, ahora=100)
        self.assertEqual(plan['capitulo']['id'], dificil)
        self.assertEqual(plan['repasos'], 1)
        self.assertEqual(plan['ejercicios'], 1)
        self.con.execute('UPDATE state SET leech=1')
        self.assertEqual(recomendaciones.recomendar(self.con)['repasos'], 0)

    def test_vacio(self):
        plan = recomendaciones.recomendar(self.con)
        self.assertIsNone(plan['capitulo'])
        self.assertEqual(plan['ejercicios'], 0)
