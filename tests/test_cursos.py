"""Pruebas para el seguimiento de cursos online (Platzi y Udemy) y su integración con Bit y Pomodoro."""
import unittest

from tests.apoyo import BaseTemporal
from appstudy import db, pomodoro, reproductor


class TestCursosOnline(BaseTemporal):

    def test_upsert_y_get_online_courses(self):
        # Insertar curso Platzi
        id_p = db.upsert_online_course(
            self.con,
            platform="platzi",
            course_slug="ingles-c1",
            course_title="Curso de Inglés Avanzado C1",
            course_url="https://platzi.com/cursos/ingles-c1/",
            last_video_title="Phrasal verbs in formal contexts",
            last_video_url="https://platzi.com/clases/ingles-c1/phrasal-verbs/",
            next_video_title="Inversion and emphasis",
            next_video_url="https://platzi.com/clases/ingles-c1/inversion/"
        )
        self.assertGreater(id_p, 0)

        # Insertar curso Udemy
        id_u = db.upsert_online_course(
            self.con,
            platform="udemy",
            course_slug="docker-mastery",
            course_title="Docker Mastery with Kubernetes",
            course_url="https://www.udemy.com/course/docker-mastery/",
            last_video_title="Multi-stage builds",
            last_video_url="https://www.udemy.com/course/docker-mastery/learn/lecture/101",
            next_video_title="Docker Compose in production",
            next_video_url="https://www.udemy.com/course/docker-mastery/learn/lecture/102"
        )
        self.assertGreater(id_u, 0)

        # Obtener todos
        todos = db.get_online_courses(self.con)
        self.assertEqual(len(todos), 2)

        # Filtrar por plataforma
        platzi = db.get_online_courses(self.con, platform="platzi")
        self.assertEqual(len(platzi), 1)
        self.assertEqual(platzi[0]["course_slug"], "ingles-c1")
        self.assertEqual(platzi[0]["last_video_title"], "Phrasal verbs in formal contexts")
        self.assertEqual(platzi[0]["next_video_title"], "Inversion and emphasis")

        # Obtener último
        ultimo_platzi = db.get_last_course(self.con, platform="platzi")
        self.assertIsNotNone(ultimo_platzi)
        self.assertEqual(ultimo_platzi["next_video_url"], "https://platzi.com/clases/ingles-c1/inversion/")

        # Actualizar lección siguiente
        db.upsert_online_course(
            self.con,
            platform="platzi",
            course_slug="ingles-c1",
            course_title="Curso de Inglés Avanzado C1",
            last_video_title="Inversion and emphasis",
            last_video_url="https://platzi.com/clases/ingles-c1/inversion/",
            next_video_title="C1 Speaking Exam Prep",
            next_video_url="https://platzi.com/clases/ingles-c1/speaking-prep/"
        )

        actualizado = db.get_online_course(self.con, "platzi", "ingles-c1")
        self.assertEqual(actualizado["last_video_title"], "Inversion and emphasis")
        self.assertEqual(actualizado["next_video_title"], "C1 Speaking Exam Prep")

    def test_pausar_y_reanudar_reproductor_sin_error(self):
        # Cuando no hay reproductor activo, no debe lanzar excepción
        reproductor.pausar_reproductor_activo()
        reproductor.reanudar_reproductor_activo()

    def test_pomodoro_pausa_reproductor_al_completar(self):
        pausado = False
        class MockPlayer:
            def pausar_video(self):
                nonlocal pausado
                pausado = True

        reproductor._instancia_reproductor = MockPlayer()
        try:
            ctrl = pomodoro.PomodoroControl(self.con, mins_trabajo=1, mins_descanso=1)
            ctrl.iniciar()
            ctrl.restante = 1
            ctrl._tick()
            self.assertTrue(pausado)
        finally:
            reproductor._instancia_reproductor = None


if __name__ == "__main__":
    unittest.main()
