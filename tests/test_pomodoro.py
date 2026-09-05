import unittest
from tests.apoyo import BaseTemporal
from appstudy import pomodoro


class TestPomodoro(BaseTemporal):

    def test_estados_pomodoro(self):
        ctrl = pomodoro.PomodoroControl(self.con, mins_trabajo=25, mins_descanso=5)
        self.assertEqual(ctrl.estado, pomodoro.ESTADO_INACTIVO)
        self.assertEqual(ctrl.restante, 25 * 60)

        ctrl.iniciar()
        self.assertEqual(ctrl.estado, pomodoro.ESTADO_TRABAJO)

        ctrl.pausar()
        self.assertEqual(ctrl.estado, pomodoro.ESTADO_PAUSA)

        ctrl.iniciar()
        self.assertEqual(ctrl.estado, pomodoro.ESTADO_TRABAJO)

        ctrl.reiniciar()
        self.assertEqual(ctrl.estado, pomodoro.ESTADO_INACTIVO)
        self.assertEqual(ctrl.restante, 25 * 60)

    def test_transicion_a_descanso(self):
        llamado_fin = False
        def on_fin():
            nonlocal llamado_fin
            llamado_fin = True

        ctrl = pomodoro.PomodoroControl(self.con, mins_trabajo=1, mins_descanso=1,
                                        on_fin_trabajo=on_fin)
        ctrl.iniciar()
        ctrl.restante = 1
        ctrl._tick()

        self.assertEqual(ctrl.estado, pomodoro.ESTADO_DESCANSO)
        self.assertEqual(ctrl.restante, 60)
        self.assertTrue(llamado_fin)


if __name__ == "__main__":
    unittest.main()
