from datetime import date, timedelta
import sqlite3
import unittest

from tests.apoyo import BaseTemporal
from appstudy import potencial as plan, respaldo


class CalendarioTest(unittest.TestCase):
    def test_fases_en_cada_limite(self):
        for i, fase in enumerate(plan.FASES):
            self.assertEqual(plan.fase_actual(date.fromisoformat(fase["inicio"])), i)
            self.assertEqual(plan.fase_actual(date.fromisoformat(fase["fin"])), i)
        self.assertEqual(plan.fase_actual(date(2026, 1, 1)), 0)
        self.assertEqual(plan.fase_actual(date(2030, 1, 1)), 5)

    def test_override_y_fase_invalida(self):
        self.assertEqual(plan.fase_actual(date(2026, 10, 1), 3), 3)
        for n in (-1, 6, "1", True):
            with self.assertRaises(ValueError):
                plan.fase_actual(elegida=n)

    def test_presupuestos_sin_duplicar_habitos(self):
        lunes = date(2026, 9, 7)
        for presupuesto in (60, 90):
            for dia in range(7):
                agenda = plan.agenda(lunes + timedelta(days=dia), presupuesto)
                self.assertEqual(sum(t[2] for t in agenda),
                                 presupuesto if dia < 5 else 120 if dia == 5 else 45)
                self.assertEqual(sum(t[0] == "lectura" for t in agenda), 1)
                self.assertTrue(all(t[2] > 0 for t in agenda))
        with self.assertRaises(ValueError):
            plan.agenda(minutos=70)

    def test_martes_adapta_foco_y_proyecto_a_fase(self):
        agenda = plan.agenda(date(2026, 9, 8), elegida=5)
        self.assertEqual(agenda[2][1], plan.FASES[5]["foco"])
        self.assertEqual(agenda[3][1], plan.FASES[5]["practica"])

    def test_semana_en_cambio_de_anio(self):
        self.assertEqual(plan.semana(date(2027, 1, 3)), "2026-12-28")
        self.assertEqual(plan.semana(date(2027, 1, 4)), "2027-01-04")


class RegistrosTest(BaseTemporal):
    def test_dias_independientes_y_desmarcado(self):
        hoy = date(2026, 9, 9)
        plan.registrar_dia(self.con, hoy, "lectura", True)
        plan.registrar_dia(self.con, hoy, "ingles", True)
        plan.registrar_dia(self.con, hoy, "lectura", False)
        self.assertEqual(plan.leer(self.con, "dia:2026-09-09"), {"lectura": False, "ingles": True})
        self.assertIsNone(plan.leer(self.con, "dia:2026-09-10"))

    def test_cuaderno_edita_sin_duplicar_y_respalda(self):
        campos = dict.fromkeys(plan.CAMPOS["problema"], "")
        campos["Problema"] = "¿Qué equipo produce más por litro?"
        identidad = plan.guardar_entrada(self.con, "problema", campos)
        campos["Mi hipótesis"] = "Comparar producción / combustible"
        plan.guardar_entrada(self.con, "problema", campos, identidad)
        self.assertEqual(len(plan.entradas(self.con)), 1)
        destino = respaldo.copiar(self.con, self.tmp / "copia.db")
        with sqlite3.connect(destino) as copia:
            copia.row_factory = sqlite3.Row
            self.assertEqual(plan.entradas(copia)[0]["campos"], campos)

    def test_entrada_invalida_no_escribe(self):
        for tipo, campos in (("desconocido", {}), ("problema", {}),
                              ("lectura", dict.fromkeys(plan.CAMPOS["lectura"], ""))):
            with self.assertRaises(ValueError):
                plan.guardar_entrada(self.con, tipo, campos)
        self.assertEqual(plan.entradas(self.con), [])

    def test_revision_semanal_reemplaza_solo_su_semana(self):
        notas = dict.fromkeys(plan.AREAS, 3)
        plan.guardar_revision(self.con, date(2026, 9, 13), notas, "Construí una consulta")
        notas["Data"] = 4
        plan.guardar_revision(self.con, date(2026, 9, 12), notas, "Corregí un JOIN")
        self.assertEqual(plan.leer(self.con, "semana:2026-09-07")["notas"]["Data"], 4)
        self.assertIsNone(plan.leer(self.con, "semana:2026-09-14"))
        notas["Data"] = 6
        with self.assertRaises(ValueError):
            plan.guardar_revision(self.con, date.today(), notas, "")

    def test_hitos_y_preferencias_persisten(self):
        plan.guardar(self.con, "hito:2026-11-30", "informe.md: solución comprobada")
        plan.guardar(self.con, "fase", 2)
        self.assertEqual(plan.leer(self.con, "fase"), 2)
        self.assertIn("informe.md", plan.leer(self.con, "hito:2026-11-30"))


class RelojTest(unittest.TestCase):
    def test_pausas_y_transiciones_requieren_confirmacion(self):
        ahora = [0]
        reloj = plan.RelojRazonamiento(lambda: ahora[0])
        reloj.iniciar()
        ahora[0] = 100
        reloj.iniciar()
        self.assertEqual(reloj.restante, 1100)
        self.assertFalse(reloj.siguiente())
        reloj.pausar()
        ahora[0] = 10000
        self.assertEqual(reloj.restante, 1100)
        reloj.iniciar()
        ahora[0] += 2000
        self.assertEqual(reloj.etapa, 0)
        self.assertEqual(reloj.restante, 0)
        self.assertTrue(reloj.siguiente())
        self.assertEqual(reloj.restante, 600)
        self.assertIsNone(reloj.inicio)
        reloj.iniciar()
        ahora[0] += 600
        self.assertTrue(reloj.siguiente())
        self.assertEqual(reloj.restante, 300)
        reloj.iniciar()
        ahora[0] += 300
        self.assertFalse(reloj.siguiente())
        self.assertEqual(reloj.restante, 0)


if __name__ == "__main__":
    unittest.main()
