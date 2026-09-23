"""Las citas automáticas respetan la frecuencia elegida en ajustes."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests.apoyo import BaseTemporal
from appstudy import citas, db, pet
from appstudy.main_window import MainWindow


class TestFrecuenciaCitas(BaseTemporal):
    def ventana(self, transcurrido, pendientes=0):
        ahora = 100000.0
        return SimpleNamespace(
            con=self.con, refresh_stats=Mock(), dormida=lambda: False,
            vigilar_taller=lambda: False,
            bubble=SimpleNamespace(get_reveal_child=lambda: False),
            ultimo_quote_tiempo=ahora - transcurrido,
            last_nag=ahora - 10000, intervalo_min=lambda: 5,
            stats={"horas": 0, "pendientes": pendientes, "nuevas": 0, "energia": 1},
            ultimo_diario=ahora, sonar=Mock(), creature=Mock(),
            quote=Mock(), sabias_que=Mock(), quiz=Mock(), teach=Mock())

    def comprobar(self, ventana, azar=0):
        with patch.object(pet.time, "time", return_value=100000.0), \
                patch.object(pet.random, "random", return_value=azar):
            pet.PetWindow.on_check(ventana)

    def test_por_defecto_espera_treinta_minutos(self):
        self.assertEqual(citas.intervalo_min(self.con), 30)
        ventana = self.ventana(210)
        self.comprobar(ventana)
        ventana.quote.assert_not_called()

    def test_ninguna_ruta_automatica_se_salta_el_intervalo(self):
        db.set_meta(self.con, "pet_quote_every", 60)
        for pendientes in (0, 5):
            with self.subTest(pendientes=pendientes):
                ventana = self.ventana(1800, pendientes)
                self.comprobar(ventana)
                ventana.quote.assert_not_called()
                ventana.sabias_que.assert_called_once()

    def test_cero_desactiva_todas_las_rutas_automaticas(self):
        db.set_meta(self.con, "pet_quote_every", 0)
        for pendientes in (0, 5):
            ventana = self.ventana(10000, pendientes)
            self.comprobar(ventana)
            ventana.quote.assert_not_called()

    def test_al_cumplirse_el_intervalo_puede_mostrar_una_frase(self):
        ventana = self.ventana(1800)
        self.comprobar(ventana)
        ventana.quote.assert_called_once()

    def test_los_cambios_de_ajustes_se_aplican_sin_reiniciar(self):
        ventana = self.ventana(1800)
        fila = Mock()
        fila.get_value.return_value = 60
        MainWindow.on_pet_quote_every(ventana, fila, None)
        self.comprobar(ventana)
        ventana.quote.assert_not_called()
        fila.get_value.return_value = 15
        MainWindow.on_pet_quote_every(ventana, fila, None)
        self.comprobar(ventana)
        ventana.quote.assert_called_once()

    def test_un_valor_invalido_usa_el_intervalo_por_defecto(self):
        db.set_meta(self.con, "pet_quote_every", "invalido")
        self.assertEqual(citas.intervalo_min(self.con), 30)
