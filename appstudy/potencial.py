"""Ruta personal 2026–2028 y registros locales, sin dependencias de interfaz.

Los registros viven en meta, por cuenta, y entran en el respaldo SQLite.
No se incluyen en los snapshots de sincronización entre equipos.
"""
from datetime import date, timedelta
import json
import time
import uuid

from . import db

FASES = (
    dict(nombre="Fundamentos y concentración", inicio="2026-09-01", fin="2026-12-31",
         temas="Aritmética → álgebra → funciones → probabilidad → estadística. Papel y lápiz antes de la IA.",
         foco="Matemáticas y razonamiento", mazo="matematicas",
         practica="Una flota consume 12 193 L y produce 40 824 m³. Calcula m³/L y explica qué cambia si el consumo sube 8 % sin aumentar la producción.",
         entrega="Cuaderno de problemas resueltos, rutina de lectura y explicación de dos minutos."),
    dict(nombre="Convertirte en analista", inicio="2027-01-01", fin="2027-04-30",
         temas="Excel: tablas dinámicas y Power Query → SQL: JOIN, GROUP BY, subconsultas, CTE y ventanas → Python, NumPy, Pandas y Matplotlib → estadística, intervalos y regresión.",
         foco="Excel, SQL y Python", mazo="datos",
         practica="Limpia un dataset operativo, consulta sus datos y justifica una conclusión con un gráfico.",
         entrega="Análisis reproducible con datos, consultas, gráfico y limitaciones. 30 % aprender, 70 % construir."),
    dict(nombre="Heavy Equipment Analytics", inicio="2027-05-01", fin="2027-08-31",
         temas="Producción, combustible, mantenimiento, llantas, horas y fallas por equipo. Define unidades, periodos y denominadores antes de comparar.",
         foco="Analítica de operaciones", mazo="maquinaria",
         practica="Compara m³/L y costo de llantas/hora; documenta datos faltantes y diferencias de operación.",
         entrega="Proyecto con KPIs de flota y reporte que explique una decisión y sus límites."),
    dict(nombre="Ciencia de Datos", inicio="2027-09-01", fin="2027-12-31",
         temas="Regresión → clasificación → árboles → Random Forest → Gradient Boosting → clustering → series temporales → evaluación. Feature engineering y separación temporal para evitar fuga de datos.",
         foco="Modelado y evaluación", mazo="datos",
         practica="Construye horas desde mantenimiento, consumo de 30 días y fallas de 90 días usando solo información disponible al predecir.",
         entrega="Modelo comparado con una referencia simple, evaluación temporal y análisis de errores."),
    dict(nombre="Ingeniería de Datos", inicio="2028-01-01", fin="2028-04-30",
         temas="PostgreSQL → modelado → ETL/ELT → Docker → APIs → cloud → Airflow → dbt. Añade herramientas cuando el proyecto las necesite.",
         foco="Pipelines y calidad de datos", mazo="python",
         practica="Carga datos en PostgreSQL y repite el proceso sin duplicarlos; registra y prueba errores.",
         entrega="Fuentes → ETL → PostgreSQL → transformaciones → analítica/ML → dashboard, con instrucciones reproducibles."),
    dict(nombre="AI Engineer", inicio="2028-05-01", fin="2028-09-30",
         temas="APIs de modelos → embeddings → RAG → bases vectoriales → tool calling → agentes → evaluación → despliegue.",
         foco="Maintenance AI Assistant", mazo="ia",
         practica="Responde sobre fallas y reincidencias con consultas verificables y fuentes; evalúa también preguntas sin respuesta.",
         entrega="Asistente de mantenimiento con KPIs y reportes, evaluación de exactitud y presentación en español e inglés."),
)

HITOS = (
    ("2026-11-30", "Fundamentos", "Resuelve problemas de proporciones y álgebra; explica una lectura sin mirarla."),
    ("2027-02-28", "Primer análisis", "Entrega una limpieza de datos, consultas SQL y una conclusión verificable."),
    ("2027-05-31", "Prototipo de flota", "Entrega el modelo de datos y primeros KPIs de Heavy Equipment Analytics."),
    ("2027-08-31", "Proyecto operativo", "Compara eficiencia, mantenimiento y llantas con datos y limitaciones."),
    ("2027-11-30", "Modelo evaluado", "Compara un modelo con una referencia simple usando datos futuros separados."),
    ("2028-02-29", "Pipeline reproducible", "Carga y transforma datos en PostgreSQL, con pruebas de calidad."),
    ("2028-05-31", "Primer asistente", "Construye consultas o RAG con fuentes y un conjunto de evaluación."),
    ("2028-08-31", "Portafolio integrado", "Presenta el sistema, resultados, limitaciones y demo en español e inglés."),
    ("2028-09-30", "Cierre del plan", "¿Qué puedes resolver hoy que no podías hace 90 días? Documenta la respuesta."),
)
AREAS = ("Matemáticas / razonamiento", "Programación", "Data", "Inglés", "Lectura", "Proyectos")
CAMPOS = {
    "problema": ("Problema", "Mi hipótesis", "Datos necesarios", "Mi intento sin IA",
                 "Pistas y comparación con IA", "Solución explicada sin mirar", "Qué aprendí"),
    "lectura": ("Libro o capítulo y páginas", "Idea principal", "3 cosas que recuerdo",
                "Algo que no entendí", "Cómo podría utilizarlo"),
    "evidencia": ("Qué construí", "Archivo o enlace de la evidencia", "Cómo lo comprobé",
                  "Qué puedo hacer ahora", "Conclusión en dos minutos", "Resumen en inglés"),
}


def fase_actual(hoy=None, elegida=None):
    if elegida is not None:
        if type(elegida) is not int or not 0 <= elegida < len(FASES):
            raise ValueError("Fase inválida")
        return elegida
    hoy = (hoy or date.today()).isoformat()
    return next((i for i, f in enumerate(FASES) if hoy <= f["fin"]), len(FASES) - 1)


def semana(hoy=None):
    hoy = hoy or date.today()
    return (hoy - timedelta(days=hoy.weekday())).isoformat()


def agenda(hoy=None, minutos=90, elegida=None):
    """Presupuesto total: lectura e inglés están incluidos, no se suman aparte."""
    hoy = hoy or date.today()
    if minutos not in (60, 90):
        raise ValueError("El presupuesto debe ser 60 o 90 minutos")
    fase = FASES[fase_actual(hoy, elegida)]
    if hoy.weekday() == 6:
        return [("lectura", "Lectura y recuperación de memoria", 20),
                ("revision", "Revisión semanal y planificación; después descansa", 25)]
    if hoy.weekday() == 5:
        return [("lectura", "Lectura y recuperación de memoria", 20),
                ("ingles", "Inglés: vocabulario, escucha y expresión", 15),
                ("proyecto", fase["practica"], 85)]
    foco = ("Matemáticas con papel y lápiz" if hoy.weekday() in (0, 2)
            else "Repaso y comunicación de conclusiones" if hoy.weekday() == 4
            else fase["foco"])
    return [("lectura", "Lectura sin teléfono ni IA + recuerdo escrito", 20),
            ("ingles", "Inglés: 5 min vocabulario, 5 min escucha, 5 min expresión"
             if minutos == 90 else "Inglés: 2 min vocabulario, 5 min escucha, 3 min expresión",
             15 if minutos == 90 else 10),
            ("foco", foco, 35 if minutos == 90 else 20),
            ("proyecto", fase["practica"], 20 if minutos == 90 else 10)]


def leer(con, clave, default=None):
    raw = db.get_meta(con, "potencial:" + clave)
    return json.loads(raw) if raw is not None else default


def guardar(con, clave, valor):
    db.set_meta(con, "potencial:" + clave, json.dumps(valor, ensure_ascii=False))


def registrar_dia(con, hoy, tarea, hecho):
    if tarea not in ("lectura", "ingles", "foco", "proyecto", "revision"):
        raise ValueError("Actividad inválida")
    clave = "dia:" + hoy.isoformat()
    datos = leer(con, clave, {})
    datos[tarea] = bool(hecho)
    guardar(con, clave, datos)


def guardar_entrada(con, tipo, campos, identidad=None):
    if tipo not in CAMPOS or set(campos) != set(CAMPOS[tipo]):
        raise ValueError("Campos de cuaderno inválidos")
    if not all(isinstance(v, str) for v in campos.values()) or not next(iter(campos.values())).strip():
        raise ValueError("Escribe el primer campo antes de guardar")
    identidad = identidad or str(uuid.uuid4())
    guardar(con, "entrada:" + identidad, dict(id=identidad, tipo=tipo, campos=campos,
                                              fecha=date.today().isoformat(), ts=time.time()))
    return identidad


def entradas(con):
    return [json.loads(r["v"]) for r in con.execute(
        "SELECT v FROM meta WHERE k LIKE 'potencial:entrada:%' ORDER BY k")]


def guardar_revision(con, hoy, notas, reflexion):
    if set(notas) != set(AREAS) or any(type(n) is not int or not 0 <= n <= 5 for n in notas.values()):
        raise ValueError("Evalúa las seis áreas de 0 a 5")
    guardar(con, "semana:" + semana(hoy), dict(notas=notas, reflexion=reflexion))


class RelojRazonamiento:
    """Cada etapa exige continuar: una pausa larga no omite el trabajo propio."""
    ETAPAS = ((20, "Tú solo", "Papel, código y documentación. Escribe tu hipótesis e intento."),
              (10, "Consulta y compara", "Pide pistas a la IA; compara con tu intento, sin copiar una solución."),
              (5, "Explica sin mirar", "Cierra la consulta y explica la solución con tus palabras."))

    def __init__(self, reloj=time.monotonic):
        self.reloj = reloj
        self.etapa = 0
        self.acumulado = 0
        self.inicio = None

    @property
    def restante(self):
        delta = max(0, self.reloj() - self.inicio) if self.inicio is not None else 0
        return max(0, self.ETAPAS[self.etapa][0] * 60 - self.acumulado - delta)

    def pausar(self):
        self.acumulado = self.ETAPAS[self.etapa][0] * 60 - self.restante
        self.inicio = None

    def iniciar(self):
        if self.inicio is None and self.restante > 0:
            self.inicio = self.reloj()

    def siguiente(self):
        if self.restante > 0 or self.etapa == 2:
            return False
        self.etapa += 1
        self.acumulado = 0
        self.inicio = None
        return True
