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
| `test_scheduler.py` | El algoritmo SM-2: la escalera de aprendizaje, el castigo del fallo, el techo del año, la elección de la próxima tarjeta y el deshacer del día |
| `test_reto.py` | Los seis formatos de reto, y sobre todo que las opciones falsas no se adivinen a ojo ni sean calcadas a la buena |
| `test_mates.py` | Las fórmulas en LaTeX: markup válido, y que un `$` que no es fórmula (un precio, `$1` de awk) se quede tal cual |
| `test_respaldo.py` | Que una copia sirva para volver atrás, que no se restaure cualquier archivo encima de tus datos y que restaurar tenga vuelta atrás |
| `test_contenido.py` | Que los JSON de fábrica sean importables: niveles en rango, enunciados sin repetir, retos con respuesta correcta |

Ninguna prueba toca tu progreso real: `apoyo.py` reapunta `db.DATA_DIR` a un
directorio temporal antes de conectar, y cada caso arranca con una base vacía.
