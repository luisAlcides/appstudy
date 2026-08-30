# AppStudy

Aplicación de escritorio con **dos formas de estudiar**:

- **Modo lectura** — 22 capítulos que se leen de corrido, como un libro: portada, títulos,
  ejemplos, avisos y navegación entre capítulos. Para aprender algo desde cero.
  Los cinco de inglés son los más extensos (104 min, y casi la mitad en A2).
- **Modo repaso** — un popup que aparece con un atajo de teclado, te enseña algo o te pone
  un reto de lo que ya estudiaste, lo calificas en un segundo y desaparece. Para no olvidarlo.

Los dos se conectan: al terminar un capítulo, **«Practicar este capítulo»** abre el popup
con las tarjetas de ese tema y ese nivel.

Temas incluidos (**337 tarjetas** de fábrica, ordenadas **de básico a avanzado**):

| Mazo | Niveles | Contenido |
|---|---|---|
| 🗣️ Inglés (86) | A2 · B1 · B2 · C1 | **todo en inglés**: gramática, phrasal verbs y vocabulario |
| 🐧 Linux (51) | Básico · Intermedio · Avanzado | shell, permisos, procesos, systemd, red, scripting |
| 📊 Ciencia de Datos (50) | Básico · Intermedio · Avanzado | estadística, pandas, SQL, modelado, producción |
| 🤖 Inteligencia Artificial (50) | Básico · Intermedio · Avanzado | LLM, RAG, embeddings, agentes, evaluación, criterio |
| 🚜 Maquinaria Amarilla y Volquete (50) | Básico · Intermedio · Avanzado | hidráulica, tren de rodaje, diagnóstico, seguridad, gestión |
| 🔧 Mecánica Automotriz (50) | Básico · Intermedio · Avanzado | motor, frenos, eléctrico, diagnóstico OBD2, híbridos |

### Niveles

Cada tarjeta tiene un nivel. Las tarjetas **nuevas siempre entran de menor a mayor
nivel**: no verás nada de C1 mientras te queden tarjetas de A2 sin estudiar. Los repasos,
en cambio, aparecen cuando toca, sin importar el nivel.

El mazo de inglés está **íntegramente en inglés** y va de A2 a C1, repartido entre
gramática, phrasal verbs y vocabulario.

## Instalación

```bash
./install.sh                      # atajo por defecto: Super + Shift + E
./install.sh '<Control><Alt>e'    # o el que prefieras
```

Requiere Python 3 con GTK4 y libadwaita, que ya vienen en Ubuntu/Mint con GNOME
(`sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1` si faltaran).

## Uso

| Acción | Cómo |
|---|---|
| Popup de repaso | el atajo global, desde cualquier aplicación |
| Ventana completa | `appstudy`, o «AppStudy» en el menú de aplicaciones |
| Leer un capítulo | pestaña **Leer**, o «Continuar leyendo» en el panel |
| Estudiar un solo tema | `appstudy --popup --deck linux` |

### Teclas dentro del lector

| Tecla | Acción |
|---|---|
| `←` `→` | capítulo anterior o siguiente |
| `Esc` | volver a la biblioteca |

Un capítulo se marca como leído solo cuando llegas al final, o a mano con el botón.

### Teclas dentro del popup

| Tecla | Acción |
|---|---|
| `Espacio` | mostrar la respuesta |
| `1` – `4` | responder un reto, o calificar: Otra vez / Difícil / Bien / Fácil |
| `N` | saltar a otra tarjeta |
| `A` | abrir la ventana completa |
| `Esc` | cerrar |

## Cómo elige la tarjeta

Un algoritmo tipo **SM-2**: cada tarjeta tiene un intervalo y un factor de facilidad.
Al calificarla, el intervalo crece (Bien ×facilidad, Fácil aún más) o se reinicia a
10 minutos si fallaste. La escalera de aprendizaje es 10 min → 1 h → 1 día, y a partir
de ahí los repasos se van espaciando hasta un año.

El popup prioriza lo **vencido**, mezcla ~25% de tarjetas **nuevas** (siempre las del
nivel más bajo que te falte), y si no hay nada pendiente ofrece un repaso de refuerzo —
así el atajo nunca queda vacío.

## Las lecturas

22 capítulos, **272 minutos** de material, ordenados por nivel dentro de cada mazo:

| Mazo | Capítulos |
|---|---|
| 🗣️ Inglés | Building a sentence (A2) · Getting things done (A2) · Present Perfect and phrasal verbs (B1) · Conditionals and professional writing (B2) · Register (C1) |
| 🐧 Linux | La terminal sin misterio · Tuberías · Permisos, procesos y servicios · Scripts que no te traicionan |
| 📊 Ciencia de Datos | Mirar los datos antes de tocarlos · Entrenar sin engañarte · De un cuaderno a un sistema |
| 🤖 Inteligencia Artificial | Qué es un modelo de lenguaje · RAG, herramientas y agentes · Seguridad, límites y criterio |
| 🚜 Maquinaria | Antes de mover la máquina · El sistema hidráulico · Tren de rodaje y volquete · Diagnóstico y predictivo |
| 🔧 Automotriz | Cómo funciona un motor · Diagnóstico: leer los síntomas · Electrónica, common rail e híbridos |

Los capítulos viven en `appstudy/content/readings/*.json`. Cada uno tiene `level`,
`minutes`, `tags` (define qué tarjetas se practican al final) y un `body` de bloques:

| Bloque | Para qué |
|---|---|
| `h` | título de sección |
| `p` | párrafo |
| `list` / `steps` | lista con viñetas o numerada |
| `code` | bloque monoespaciado con fondo |
| `note` 💡 / `warn` ⚠️ / `key` 🔑 | recuadros destacados |
| `quote` | cita o ejemplo largo |

## Contenido propio

Desde la ventana principal (botón **+**) puedes crear tres tipos de tarjeta:

- **Tarjeta**: pregunta y respuesta, con pista opcional.
- **Reto**: opción múltiple con explicación del porqué.
- **Lección**: solo enseña algo, sin preguntar.

Cada una se guarda en un mazo y un **nivel**, y en el explorador puedes filtrar por
ambos.

Admite `<b>negrita</b>`, `<i>cursiva</i>` y `<code>código</code>`.

Los mazos de fábrica viven en `appstudy/content/*.json`; puedes editarlos y pulsar
**Recargar mazos incluidos** en Ajustes — se actualiza el texto **sin perder tu progreso**
(cada tarjeta se identifica por su enunciado). Cada archivo define sus propios `levels`,
y cada tarjeta su `level` (1 = el más básico).

⚠️ Al recargar, una tarjeta de fábrica que ya **no** esté en el JSON se retira junto con
su historial. Tus tarjetas propias nunca se tocan.

## Dónde se guardan tus datos

`~/.local/share/appstudy/appstudy.db` (SQLite). Para respaldar, copia ese archivo.

## Desinstalar

```bash
rm ~/.local/bin/appstudy ~/.local/share/applications/appstudy.desktop
```
Y quita el atajo desde Ajustes → **Quitar**. Tu progreso queda en `~/.local/share/appstudy/`.
# appstudy
