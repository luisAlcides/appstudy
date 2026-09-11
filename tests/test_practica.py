"""Comprueba avance, reanudación y contenido de los casos guiados."""
import json

from tests.apoyo import BaseTemporal
from appstudy import db
from appstudy.practica import SesionPractica, catalogo, numero, es_correcta


class TestPractica(BaseTemporal):
    def setUp(self):
        super().setUp()
        self.caso = catalogo()[0]
        self.sesion = SesionPractica(self.con, self.caso)

    def test_catalogo_resoluble(self):
        casos = catalogo()
        self.assertEqual(len({c['id'] for c in casos}), len(casos))
        for caso in casos:
            self.assertTrue(caso['contexto'])
            self.assertTrue(caso['solucion'])
            self.assertGreaterEqual(len(caso['pasos']), 3)
            sesion = SesionPractica(self.con, caso)
            for paso in caso['pasos']:
                if paso.get('tipo') != 'numero':
                    self.assertGreaterEqual(len(set(paso['opciones'])), 3)
                self.assertTrue(paso['pistas'])
                self.assertTrue(paso['explicacion'])
                self.assertTrue(sesion.responder(paso['respuesta'] if paso.get('tipo') == 'numero' else paso['correcta']))
            self.assertTrue(sesion.terminada)
            self.assertEqual(sesion.resumen()['sin_ayuda'], len(caso['pasos']))
            with self.assertRaises(ValueError):
                sesion.responder(0)

    def test_error_pista_y_reapertura(self):
        correcta = self.caso['pasos'][0]['correcta']
        incorrecta = (correcta + 1) % 3
        self.assertFalse(self.sesion.responder(incorrecta))
        self.assertEqual(self.sesion.indice, 0)
        self.sesion.pista()
        reabierta = SesionPractica(self.con, self.caso)
        self.assertEqual(reabierta.dato()['intentos'], [incorrecta])
        self.assertEqual(reabierta.dato()['pistas'], 1)
        self.assertTrue(reabierta.responder(correcta))
        reabierta = SesionPractica(self.con, self.caso)
        self.assertEqual(reabierta.indice, 1)
        self.assertEqual(reabierta.resumen()['sin_ayuda'], 0)
        for paso in self.caso['pasos'][1:]:
            reabierta.responder(paso['correcta'])
        self.assertTrue(SesionPractica(self.con, self.caso).terminada)

    def test_limites_y_reinicio(self):
        for opcion in [-1, 3, None, True]:
            with self.assertRaises(ValueError):
                self.sesion.responder(opcion)
        for _ in range(10):
            self.sesion.pista()
        self.assertEqual(self.sesion.dato()['pistas'], len(self.caso['pasos'][0]['pistas']))
        self.sesion.reiniciar()
        self.assertEqual(SesionPractica(self.con, self.caso).estado, [])

    def test_estado_invalido_no_desbloquea_pasos(self):
        for estado in ['mal json', '{}', '[null]', json.dumps([
                {'intentos': [0], 'pistas': 0, 'resuelto': True}])]:
            db.set_meta(self.con, self.sesion.clave, estado)
            self.assertEqual(SesionPractica(self.con, self.caso).indice, 0)

    def test_progreso_independiente(self):
        self.sesion.responder(self.caso['pasos'][0]['correcta'])
        otro = SesionPractica(self.con, catalogo()[1])
        self.assertEqual(otro.indice, 0)
        otro.reiniciar()
        self.assertEqual(SesionPractica(self.con, self.caso).indice, 1)

    def test_numeros_equivalentes_y_entradas_invalidas(self):
        self.assertEqual(numero(' 5 / 2 '), numero('2,5'))
        self.assertEqual(numero('−0,5'), numero('-1/2'))
        for texto in ['', '1/0', 'NaN', 'inf', '1e10000', '2+3', '__import__("os")',
                      '1,234.5', '1/2/3', '1' * 101, None]:
            with self.subTest(texto=texto), self.assertRaises(ValueError):
                numero(texto)

    def test_respuestas_matematicas_y_reanudacion(self):
        respuestas = {
            'mates-fracciones': ['6', '3', '10/12'],
            'mates-porcentajes': ['36', '204', '224,40'],
            'algebra-lineal': ['-6', '21', '7'],
            'algebra-cuadratica': ['2', '2', '3'],
            'estadistica-centro': ['30', '6', '3'],
            'estadistica-dispersion': ['4', '2', '1,41'],
            'mates-proporcion-directa': ['5/2', '750', '1250'],
            'mates-proporcion-inversa': ['48', '4', '16'],
            'mates-pitagoras': ['81', '225', '15'],
            'mates-potencias': ['7', '5', '32'],
            'algebra-sistema': ['14', '7', '3'],
            'algebra-desigualdad': ['8', '-4', '16'],
            'algebra-funcion-lineal': ['3', '1', '25'],
            'algebra-exponencial': ['4', '3', '81'],
            'estadistica-ponderada': ['2', '3/2', '8'],
            'estadistica-sin-reemplazo': ['0,6', '2/4', '0,3'],
            'estadistica-condicional': ['0,25', '0,625', '0,75'],
            'estadistica-varianza-muestral': ['4', '8', '4'],
            'mates-escalas': ['600', '4', '24'],
            'mates-unidades-velocidad': ['72000', '20', '300'],
            'mates-area-compuesta': ['80', '68', '0,85'],
            'mates-sucesion-aritmetica': ['3', '32', '185'],
            'algebra-ecuacion-fraccion': ['15', '13', '5'],
            'algebra-ecuacion-radical': ['16', '11', '4'],
            'algebra-valor-absoluto': ['8', '-2', '5'],
            'algebra-vertice-parabola': ['2', '3', '2'],
            'estadistica-frecuencias': ['10', '0,9', '6/10'],
            'estadistica-cuartiles': ['5/2', '17/2', '6'],
            'estadistica-puntuacion-z': ['15', '3/2', '30'],
            'estadistica-binomial': ['0,125', '3', '0,375'],
            'mates-mcd-mcm': ['6', '72', '0,75'],
            'mates-sucesion-geometrica': ['2', '48', '93'],
            'mates-volumen': ['60000', '60', '45'],
            'mates-trigonometria': ['5', '0,6', '0,75'],
            'algebra-logaritmos': ['8', '9', '3'],
            'algebra-composicion': ['19', '49', '7'],
            'algebra-racional': ['1', '3', '3'],
            'algebra-formula-cuadratica': ['9', '2', '0,5'],
            'estadistica-esperanza': ['1', '0,6', '1,6'],
            'estadistica-bernoulli': ['0,4', '0,4', '0,24'],
            'estadistica-complemento': ['0,7', '0,49', '0,51'],
            'estadistica-covarianza': ['2', '4', '8/6'],
            'mates-cilindro': ['314', '6280', '6,28'],
            'mates-combinaciones': ['20', '2', '10'],
            'mates-notacion-cientifica': ['6', '2', '600'],
            'mates-distancia-puntos': ['6', '8', '10'],
            'algebra-resto-polinomio': ['8', '8', '8'],
            'algebra-identidad-parametros': ['3', '4', '4'],
            'algebra-sistema-no-lineal': ['12', '3', '4'],
            'algebra-determinante': ['12', '2', '10'],
            'estadistica-media-combinada': ['24', '48', '36/5'],
            'estadistica-transformacion-lineal': ['35', '36', '6'],
            'estadistica-bayes': ['0,375', '0,5', '0,75'],
            'estadistica-correlacion': ['2', '3', '0,5'],
            'mates-derivada': ['10', '7', '-4'],
            'mates-integral': ['12', '2', '10'],
            'mates-limite': ['2', '4,1', '4'],
            'mates-producto-escalar': ['2', '0', '90'],
            'algebra-complejos': ['1', '7', '1'],
            'algebra-binomio-cuadrado': ['4', '-12', '9'],
            'algebra-fraccion-simplificada': ['-3', '-3', '2'],
            'algebra-raiz-doble': ['36', '9', '3'],
            'estadistica-regresion': ['2', '1', '7'],
            'estadistica-error-prediccion': ['2', '1', '10/6'],
            'estadistica-error-estandar': ['6', '2', '1'],
            'estadistica-frecuencia-esperada': ['0,3', '12', '6'],
        }
        for caso in catalogo()[3:]:
            sesion = SesionPractica(self.con, caso)
            for respuesta in respuestas[caso['id']]:
                with self.assertRaises(ValueError):
                    sesion.responder('texto inválido')
                self.assertEqual(sesion.dato()['intentos'], [])
                self.assertFalse(sesion.responder('999'))
                sesion.pista()
                sesion = SesionPractica(self.con, caso)
                self.assertEqual(sesion.dato()['intentos'], ['999'])
                self.assertTrue(sesion.responder(respuesta))
                sesion = SesionPractica(self.con, caso)
            self.assertTrue(sesion.terminada)
            self.assertEqual(sesion.resumen()['sin_ayuda'], 0)

    def test_redondeo_solo_dentro_de_tolerancia(self):
        paso = next(c for c in catalogo() if c['id'] == 'estadistica-dispersion')['pasos'][-1]
        self.assertTrue(es_correcta(paso, '1.4142'))
        self.assertTrue(es_correcta(paso, '1,41'))
        self.assertFalse(es_correcta(paso, '1,42'))
