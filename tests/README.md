# Pruebas

```bash
./pruebas.sh              # todas
./pruebas.sh scheduler    # solo las del planificador
```

Solo hace falta Python 3 con GTK (lo mismo que la aplicación): las pruebas usan
`unittest` de la biblioteca estándar, no `pytest`. Si tienes pytest instalado
también las corre (`pytest tests/`), porque reconoce las clases de `unittest`.

| Archivo | Qué protege |
|---|---|
| `test_fsrs.py` | El modelo de memoria: que la probabilidad de acordarte baje siempre, que fallar nunca suba la estabilidad, que pedir más retención acorte, y que calibrar no empeore nunca lo que hay |
| `test_scheduler.py` | Cómo se aplica el modelo a una tarjeta: el peldaño corto del fallo, el techo del año, la elección de la próxima tarjeta y el deshacer del día |
| `test_sesiones.py` | Los límites por tiempo y cantidad, la ampliación, el deshacer y el resumen de una sesión guiada |
| `test_importador.py` | CSV/TSV, exportaciones de texto y paquetes de Anki, incluidos límites y rutas maliciosas dentro del ZIP |
| `test_progreso.py` | Las sanguijuelas, el deshacer de un solo repaso, el objetivo diario y la migración desde el SM-2 anterior |
| `test_cloze.py` | Las tarjetas de huecos: tapar y destapar sin perder nada, las pistas, y el texto completo tal como se escribió |
| `test_reto.py` | Los seis formatos de reto, y sobre todo que las opciones falsas no se adivinen a ojo ni sean calcadas a la buena |
| `test_mates.py` | Las fórmulas en LaTeX: markup válido, y que un `$` que no es fórmula (un precio, `$1` de awk) se quede tal cual |
| `test_respaldo.py` | Que una copia sirva para volver atrás, que no se restaure cualquier archivo encima de tus datos y que restaurar tenga vuelta atrás |
| `test_estadisticas.py` | Las series de Progreso, los temas débiles, los cortes por fecha y que las medias no incluyan repasos que no significan nada |
| `test_logros.py` | Que los logros se den cuando toca, una sola vez, y nunca antes de tiempo |
| `test_lecturas.py` | El Markdown de tus capítulos: que cada cosa acabe en su bloque, la ida y vuelta sin pérdidas, y que recargar lo de fábrica no borre lo tuyo |
| `test_buscador.py` | La búsqueda de Ctrl+K: que exija todas las palabras, ignore acentos y ordene por relevancia |
| `test_notas.py` | Los subrayados (coordenadas relativas, colores, notas) y la lectura de EPUB, incluido que un ZIP con rutas de escape no escriba fuera de su carpeta |
| `test_contenido.py` | Que los JSON de fábrica sean importables: niveles en rango, enunciados sin repetir, retos con respuesta correcta, huecos con hueco |

Varias pruebas de `test_fsrs.py` comprueban **propiedades**, no números
concretos: son las que sobreviven a un cambio de pesos y las que de verdad
protegen el método.

Ninguna prueba toca tu progreso real: `apoyo.py` reapunta `db.DATA_DIR` a un
directorio temporal antes de conectar, y cada caso arranca con una base vacía.
