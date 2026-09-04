import unittest

from appstudy import pet, scheduler
from tests.apoyo import BaseTemporal


class EvolucionBitTest(unittest.TestCase):
    def test_empieza_como_companero(self):
        estado = pet.evolucion(0)
        self.assertEqual(estado["nombre"], "Compañero")
        self.assertEqual(estado["siguiente"]["min"], 25)
        self.assertEqual(estado["avance"], 0)

    def test_cambia_en_cada_umbral(self):
        esperados = ((24, "Compañero"), (25, "Curioso"), (100, "Aplicado"),
                     (500, "Sabio"), (1500, "Maestro"))
        for repasos, nombre in esperados:
            self.assertEqual(pet.evolucion(repasos)["nombre"], nombre)

    def test_avance_es_acotado_y_el_maximo_no_tiene_siguiente(self):
        self.assertAlmostEqual(pet.evolucion(50)["avance"], 25 / 75)
        maestro = pet.evolucion(99999)
        self.assertEqual(maestro["avance"], 1)
        self.assertIsNone(maestro["siguiente"])

    def test_accesorios_se_desbloquean_gradualmente(self):
        self.assertEqual([a["key"] for a in pet.accesorios_disponibles(0)], ["ninguno"])
        self.assertEqual([a["key"] for a in pet.accesorios_disponibles(100)],
                         ["ninguno", "panuelo", "gafas"])

    def test_un_accesorio_bloqueado_o_desconocido_no_se_aplica(self):
        self.assertEqual(pet.accesorio_valido("corona", 499), "ninguno")
        self.assertEqual(pet.accesorio_valido("corona", 500), "corona")
        self.assertEqual(pet.accesorio_valido("sombrero", 9999), "ninguno")


class TotalRepasosBitTest(BaseTemporal):
    def test_cuenta_el_trabajo_real(self):
        did = self.mazo()
        cid = self.tarjeta(did, "Una")
        self.assertEqual(pet.total_repasos(self.con), 0)
        scheduler.apply_review(self.con, cid, scheduler.GOOD)
        scheduler.apply_review(self.con, cid, scheduler.HARD)
        self.assertEqual(pet.total_repasos(self.con), 2)


if __name__ == "__main__":
    unittest.main()
