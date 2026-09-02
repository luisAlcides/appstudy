# AppStudy

Aplicación de escritorio con **tres formas de estudiar**:

- **Modo lectura** — 67 capítulos que se leen de corrido, como un libro: portada, títulos,
  ejemplos, avisos y navegación entre capítulos. Para aprender algo desde cero.
  Los ocho de inglés son los más extensos (152 min, casi un tercio en A2).
- **Modo repaso** — un popup que aparece con un atajo de teclado, te enseña algo o te pone
  un reto de lo que ya estudiaste, lo calificas en un segundo y desaparece. Para no olvidarlo.

- **Bit, la mascota** — un bicho que vive en el escritorio por encima de todas las
  ventanas. Te recuerda estudiar cuando llevas rato sin hacerlo, te enseña una
  tarjeta ahí mismo —pregunta y respuesta juntas— o te pone a prueba contrarreloj
  de seis maneras distintas, y de vez en cuando te suelta una frase de un libro.
  Desde su globo saltas a la lectura que explica justo eso.

Y encima de todo, un **indicador en la barra superior de GNOME** con lo que llevas
y lo que te falta, siempre a la vista.

Los dos primeros se conectan: al terminar un capítulo, **«Practicar este capítulo»** abre el popup
con las tarjetas de ese tema y ese nivel; y desde cualquier tarjeta, **«Sesión completa →»**
abre el capítulo que la explica, en el párrafo exacto.

Las fórmulas se escriben en **LaTeX** y el código sale **coloreado**; los detalles,
en [Fórmulas y código](#fórmulas-y-código).

Temas incluidos (**678 tarjetas** de fábrica, ordenadas **de básico a avanzado**):

| Mazo | Niveles | Contenido |
|---|---|---|
| 🗣️ Inglés (125) | A2 · B1 · B2 · C1 | **todo en inglés**: gramática, phrasal verbs, vocabulario, registro y escritura profesional |
| 🐧 Linux (87) | Básico · Intermedio · Avanzado | shell, permisos, procesos, systemd, red, SSH, LVM, scripting |
| 📊 Ciencia de Datos (83) | Básico · Intermedio · Avanzado | estadística, pandas, SQL, modelado, experimentos, producción |
| 🤖 Inteligencia Artificial (82) | Básico · Intermedio · Avanzado | LLM, RAG, embeddings, agentes, evaluación, coste y criterio |
| 🚜 Maquinaria Amarilla y Volquete (82) | Básico · Intermedio · Avanzado | hidráulica, tren de rodaje, diagnóstico, seguridad, gestión |
| 🔧 Mecánica Automotriz (82) | Básico · Intermedio · Avanzado | motor, frenos, eléctrico, diagnóstico OBD2, common rail, híbridos |
| 🧮 Matemáticas y Cálculo Rápido (73) | Básico · Intermedio · Avanzado | complementos, multiplicación védica, porcentajes, cuadrados, prueba del 9 |
| ⚡ Electricidad y Electrónica (64) | Básico · Intermedio · Avanzado | Ohm, medición, componentes, PWM, alterna, motores, protecciones |

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

El instalador deja el comando `appstudy` en `~/.local/bin`, el icono en el tema
del escritorio, el lanzador (con sus acciones «Estudiar ahora» y «Soltar a Bit»),
**lo ancla al dock**, registra el atajo global, deja a Bit en el autoarranque e
instala la extensión de la barra superior. Se puede repetir sin miedo: no duplica
nada.

Requiere Python 3 con GTK4 y libadwaita, que ya vienen en Ubuntu/Mint con GNOME
(`sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1` si faltaran), y
`python3-pygments` para los colores del código. La IA local es opcional y va
aparte (ver [Preguntarle a Bit](#preguntarle-a-bit-ia-local)).

El lanzador se llama `io.github.appstudy.AppStudy.desktop`, igual que el id de la
aplicación: es lo que mira GNOME para emparejar la ventana abierta con su icono
del dock. El icono está en `appstudy/data/` — una tarjeta de estudio con el
asterisco de Bit, dibujado con la misma geometría de once rayos que la mascota.

## Actualizar

```bash
./actualizar.sh
```

Hace todo de una vez y se puede repetir sin miedo: trae los cambios del remoto
(si tienes el árbol limpio), reinstala lo que son **copias** —icono, lanzador,
dock, autoarranque y extensión—, recarga el contenido incluido y reinicia a Bit
dejándola con la versión nueva. Al terminar te avisa solo si hace falta algo más:
cerrar y abrir la ventana principal, o cerrar sesión si cambió la extensión de
GNOME.

Lo que **no** hace falta reinstalar: el comando `appstudy` y el lanzador apuntan
directamente a esta carpeta, así que el código Python y los estilos entran con
solo volver a abrir lo que estuviera corriendo.

| Qué tocas | Qué basta |
|---|---|
| Código Python o `style.css` | cerrar y abrir la app |
| La mascota (`pet.py`, `ia.py`, `sonido.py`…) | `appstudy --pet-off && appstudy --pet` |
| Contenido de `content/*.json` | **Ctrl+R** o `appstudy --reload` |
| Icono, lanzador, dock, atajo, extensión | `./install.sh` (o `./actualizar.sh`) |

## Uso

| Acción | Cómo |
|---|---|
| Popup de repaso | el atajo global, desde cualquier aplicación |
| Ventana completa | `appstudy`, o «AppStudy» en el menú de aplicaciones |
| Leer un capítulo | pestaña **Leer**, o «Continuar leyendo» en el panel |
| Estudiar un solo tema | `appstudy --popup --deck linux` |
| Soltar la mascota | `appstudy --pet`, o Ajustes → **Bit, la mascota**, o el interruptor de la barra superior |
| Recargar el contenido | **Ctrl+R** o **F5** en cualquier ventana, o `appstudy --reload` |
| Abrir la lectura de una tarjeta | `appstudy --read-card <id>` (es lo que usa Bit) |
| Ver el estado en JSON | `appstudy --status` (lo usa la extensión de GNOME) |

Si editas un JSON de `appstudy/content/`, **Ctrl+R** lo mete en la base y refresca la
ventana sin perder tu progreso. Y si el cambio viene con la aplicación, basta con subir
`CONTENT_VERSION` en `appstudy/seed.py`: se reimporta solo en el siguiente arranque.

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

## Bit, la mascota

Vive en una ventanita sin bordes, **siempre encima del resto** y en todos los
espacios de trabajo. Es el asterisco de Claude cobrando vida: un **estallido de
once rayos** en el color de su ánimo y, delante, un mochi crema con la cara —
ojos grandes y brillantes, cejas que dicen cosas, dos manoplas y dos pies que
asoman por debajo. Un homenaje hecho a mano con Cairo, no el logotipo de nadie.

El estallido gira despacio todo el rato, se acelera y se enciende cuando tiene
algo que enseñarte, y casi se para y se encoge cuando llevas días sin aparecer.
Como se pasa el día sobre fondos que no controla, todo lleva contorno cálido y
una sombra suave (tres trazos concéntricos, que Cairo no tiene desenfoque): se ve
igual sobre un escritorio negro, uno crema o una foto. Está dibujado en un lienzo
fijo de 152×184 que luego se escala, así que para hacerlo más grande o más
pequeño basta con cambiar `ANCHO` y `ALTO_PET` en `appstudy/pet.py`.

El color del estallido, los cachetes y la barra de energía es el de su ánimo:
terracota cuando todo va normal, verde si estás al día, morado si se aburre,
ámbar si tiene hambre de repasos, teja si llevas días sin aparecer. La barra
bajo sus pies es su energía, que baja con las horas sin repasar y con lo que
tienes pendiente.

| Acción | Qué hace |
|---|---|
| Clic | salta y te enseña una tarjeta en el globo |
| Pasar el ratón | te sigue con la mirada |
| Arrastrar | la mueve; recuerda dónde la dejaste |
| Clic derecho | menú: enséñame algo, ponme a prueba, una frase de libro, sesión completa, abrir AppStudy, **más grande / más pequeño**, dormir, salir |

**Tamaño**: del 50 % al 250 %, desde su menú (pasos del 15 %) o con el número exacto en
Ajustes → Progreso. Se guarda, y la mascota lo recoge sola aunque lo cambies desde la
ventana principal.

Cuando **enseña**, enseña de verdad: la pregunta y la respuesta salen juntas desde
el primer momento, sin botón de por medio. Tú solo dices si la tenías —**No lo
sabía** / **Lo sabía**— y cuenta como un repaso normal, con el mismo intervalo que
el popup.

### Sonido

Bit hace ruiditos: un aviso de dos notas cuando viene a buscarte, un arpegio al
acertar, dos notas descendentes al fallar, un blip al abrirse el globo, otro al
hacerle clic y una escala grave al dormirse. También suenan los aciertos y
fallos del popup de estudio.

Los sonidos **no son archivos**: se sintetizan con la biblioteca estándar
(`appstudy/sonido.py`) la primera vez que hacen falta y se guardan en
`~/.local/share/appstudy/sonidos` — unos 220 KB, nada en el repositorio. Se
reproducen con GSound, sin abrir procesos ni bloquear la interfaz; si no
estuviera, se recurre a `paplay`, `pw-play` o `aplay`, y si no hay ninguno la
aplicación funciona igual, en silencio.

Para cambiarlos, las notas están en un diccionario al principio del módulo:
cada sonido es una lista de `(frecuencia, duración, volumen)`. Se apagan desde
el menú de Bit (**Silencio**) o en Ajustes, donde también está el volumen.

### Se le nota si no estudias

El ánimo lo manda, sobre todo, **cuánto llevas sin repasar**:

| Sin estudiar | Cómo se pone |
|---|---|
| menos de 4 h | normal, o **feliz** si estás al día |
| más de 4 h | **aburrido**: párpados a media asta, boca plana, se mueve menos |
| más de 1 día | **hambriento**: cejas caídas, empiezan las ojeras, y te lo dice |
| más de 3 días | **triste**: ojeras marcadas, el cuerpo hundido, el asterisco casi parado y algún suspiro |

Entre las cuatro horas y los tres días no hay saltos: el «abandono» crece poco a
poco y le va apagando el balanceo, la respiración y el giro del asterisco. Si
llevas más de un día fuera te lo echa en cara (como mucho una vez cada tres
horas), y en cuanto vuelves a calificar una tarjeta lo celebra con salto y
corazones. Los umbrales están en `HORAS_ABURRIDO`, `HORAS_HAMBRE` y
`HORAS_TRISTE`, al principio de `appstudy/pet.py`.

Cada cierto tiempo (45 min por defecto, configurable en Ajustes) te habla. Si no
tienes nada pendiente no te da la lata con tarjetas: te deja una **frase de un
libro** —Cervantes, Wittgenstein, Séneca, Knuth, Sagan…— con su autor y su obra.
También las pides tú desde el menú, y aparece una en el desplegable de la barra
superior. Están en `appstudy/citas.py`; añade las tuyas ahí.

Si estorba, **Duérmete 60 min** desde su menú.

### Ponme a prueba

Lo otro que sabe hacer es examinarte, y nunca dos veces igual. Cada reto lleva
**cuenta atrás** (la barra se pone roja en el último tercio) y responder rápido y
bien vale por «fácil», así que esa tarjeta tarda más en volver. Si se acaba el
tiempo, cuenta como fallo — pero la respuesta se enseña igual.

| Formato | Cómo te pregunta |
|---|---|
| 🎯 Elige la buena | cuatro opciones; las falsas salen de otras tarjetas del mismo mazo |
| 🔄 ¿De qué hablo? | te enseña la respuesta y eliges de qué tarjeta era |
| ⚖️ ¿Verdadero o falso? | una afirmación que puede ser la buena o una colada |
| 🧩 Rellena el hueco | falta una palabra de la respuesta y la escribes |
| ✍️ Escríbelo tú | respuestas cortas: se perdonan acentos y erratas |
| ⚡ Contrarreloj | piensas contra el reloj y luego te comparas con la respuesta |

El formato se sortea entre los que la tarjeta admite y no se repite dos veces
seguidas; una lección sin respuesta no se pregunta, se lee. Las opciones falsas
se eligen con cuidado: del mismo mazo y nivel parecido, ni calcadas a la buena
(podrían ser correctas) ni de otro tamaño (si la larga fuera siempre la correcta,
el reto se adivinaría a ojo). Está todo en `appstudy/reto.py`, sin nada de GTK,
para poder probarlo sin abrir una ventana.

### «Sesión completa →» lleva a la lectura

El pie del globo abre el capítulo que **explica esa tarjeta**, y no por el
principio: se desplaza hasta el párrafo concreto y lo marca como con rotulador.
El capítulo se elige por las etiquetas que comparte con la tarjeta, el nivel y
las palabras en común (`db.chapter_for_card`); el párrafo, por las palabras que
comparte con la pregunta y la respuesta (`reader._mejor_bloque`). Si no hay
ningún capítulo que encaje, el botón abre el popup de estudio como antes.

Por dentro es `appstudy --read-card <id>`: la mascota vive en otro proceso, así
que se lo pide a la aplicación principal por la línea de órdenes.

### Cómo se mueve

Nunca está quieto: respira, se balancea, parpadea (a veces dos veces seguidas),
mira alrededor y sigue el ratón con las pupilas. Cada pocos segundos hace un
gesto suelto —saltar, estirarse, ladear la cabeza, agitar la antena— y reacciona a
lo que pasa: saluda al avisarte, mueve la boca mientras habla, saca corazones y
chispas cuando aciertas, una gota cuando fallas, y zZz mientras duerme. Las cejas,
la boca, el color y la velocidad del balanceo cambian con su ánimo.

Todo está dibujado con Cairo en `appstudy/pet.py`: los gestos puntuales se lanzan
con `play(nombre, segundos)` y `phase(nombre)` dice por dónde van, de 0 a 1.

### Lo que gasta

Medido en este escritorio, **3 % de un núcleo y 127 MB** con la mascota suelta y
sin tocarla. Tres decisiones lo bajaron desde el 9 % del primer intento:

- **`GSK_RENDERER=cairo`** (se pone en `bin/appstudy`). Para una ventanita de 168
  píxeles dibujada a mano, el renderizador de software gasta menos de la mitad
  que el acelerado y 60 MB menos, porque el coste está en subir la textura en
  cada fotograma, no en pintarla.
- **Cadencia adaptativa**: 30 fotogramas por segundo mientras salta, habla o la
  señalas con el ratón; 10 cuando solo respira.
- **Repintar solo si se nota**: en reposo se compara la pose con la del fotograma
  anterior y se salta el repintado si no ha cambiado ni medio píxel.

### Por qué necesita X11 y wmctrl

Wayland no deja que una aplicación se ponga encima de las demás, así que la
mascota —y solo ella— se lanza en su propio proceso con `GDK_BACKEND=x11`
(XWayland) y le pide al gestor de ventanas el estado `_NET_WM_STATE_ABOVE` con
`wmctrl`. El resto de AppStudy sigue en Wayland nativo. Si faltan las
herramientas:

```bash
sudo apt install wmctrl x11-utils
```

Sin ellas la mascota funciona, pero no se queda encima ni recuerda su sitio.

## La extensión de la barra superior

Un indicador en la barra de GNOME con lo pendiente siempre visible. Al pulsarlo:
los cuatro números (pendientes, hoy, racha, dominadas), cuándo toca el siguiente
repaso, una frase de libro, y accesos a **Estudiar ahora**, **Abrir AppStudy** y un
interruptor para **soltar o guardar a Bit**.

La instala `install.sh` en `~/.local/share/gnome-shell/extensions/`. En Wayland
GNOME no carga extensiones nuevas en caliente: **cierra sesión y vuelve a entrar**
para verla.

```bash
gnome-extensions enable  appstudy@luisalcides.github.io   # activar
gnome-extensions disable appstudy@luisalcides.github.io   # desactivar
```

No lee la base de datos por su cuenta: pregunta con `appstudy --status`, que
responde JSON sin cargar GTK. Funciona en GNOME Shell 45 a 48.

## Cómo elige la tarjeta

Un algoritmo tipo **SM-2**: cada tarjeta tiene un intervalo y un factor de facilidad.
Al calificarla, el intervalo crece (Bien ×facilidad, Fácil aún más) o se reinicia a
10 minutos si fallaste. La escalera de aprendizaje es 10 min → 1 h → 1 día, y a partir
de ahí los repasos se van espaciando hasta un año.

El popup prioriza lo **vencido**, mezcla ~25% de tarjetas **nuevas** (siempre las del
nivel más bajo que te falte), y si no hay nada pendiente ofrece un repaso de refuerzo —
así el atajo nunca queda vacío.

## Las lecturas

67 capítulos, **774 minutos** de material, ordenados por nivel dentro de cada mazo:

| Mazo | Capítulos |
|---|---|
| 🗣️ Inglés (8 · 152 min) | Building a sentence in English · Getting things done in English · Present Perfect and the logic of phrasal verbs · Technical procedures, passive voice and instructions · Conditionals, reported speech and professional writing · Professional correspondence, incident reports and data commentary · Register: sounding like a professional · Writing that gets read |
| 🐧 Linux (10 · 107 min) | La terminal, sin misterio · Edición de texto, configuración y paquetes · Tuberías: la idea que hace poderosa a la terminal · Permisos, usuarios y control de procesos · Almacenamiento: discos, sistemas de archivos y fstab · Redes, diagnóstico profundo y túneles SSH · Servicios systemd, temporizadores y journalctl · Scripts defensivos que no te traicionan · El kernel por dentro, hardware y contenedores · Almacenamiento avanzado: LVM, RAID y recuperación |
| 📊 Ciencia de Datos (16 · 165 min) | Mirar los datos antes de tocarlos · Limpieza, transformación y consultas: Pandas y SQL · Motores analíticos modernos: DuckDB, Polars y Parquet · Visualización que cuenta historias y evita engaños · Entrenar un modelo sin engañarte · Ingeniería de variables (Feature Engineering) y Pipelines · Los algoritmos esenciales: de Lineales a Gradient Boosting · Evaluación rigurosa: métricas de Regresión y Curvas Avanzadas · Aprendizaje no supervisado: Clustering y Detección de Anomalías · Sistemas de recomendación y búsqueda vectorial · Series temporales y pronósticos en el mundo real · Estadística inferencial y diseño de experimentos A/B · Inferencia causal: Más allá de la correlación · MLOps: De cuadernos a sistemas en producción · Interpretabilidad, calibración y decisiones de negocio · Ética, equidad algorítmica y gobernanza de datos |
| 🤖 Inteligencia Artificial (8 · 86 min) | Qué es realmente un modelo de lenguaje · El mapa de la IA: de las reglas al Deep Learning · RAG, bases vectoriales y búsqueda híbrida · Agentes autónomos y llamada a herramientas · Evaluación, observabilidad y optimización de costes · La arquitectura Transformer y la atención · Entrenamiento, Fine-Tuning y Modelos Abiertos · Seguridad, Prompt Injection y Guardrails |
| 🚜 Maquinaria (8 · 86 min) | La familia de maquinaria y la inspección pre-operacional · El volquete: componentes, tolva y operación segura · Fundamentos y circuitos del sistema hidráulico · Tren de rodaje, mandos finales y neumáticos gigantes · Sistema neumático, frenos de aire y tren motriz del volquete · Hidráulica avanzada: bombas de caudal variable, Load Sensing y pilotaje · Motores diésel pesados, inyección Common Rail y emisiones Tier 4 / Stage V · Mantenimiento predictivo, tribología y gestión de flotas |
| 🔧 Automotriz (8 · 87 min) | El motor de combustión y el mantenimiento preventivo · Frenos, suspensión, dirección y transmisión · Diagnóstico ordenado: del síntoma a la causa raíz · Inyección electrónica, sensores y escáner OBD2 · Gestión de combustible: Fuel Trims y calibración estequiométrica · Sobrealimentación, distribución variable y emisiones anticontaminación · Inyección Diésel Common Rail de alta presión · Redes CAN Bus, osciloscopio y seguridad en alta tensión (EV / HEV) |
| ⚡ Electricidad (3 · 31 min) | Cuatro magnitudes y una sola ley · Los componentes y lo que hace cada uno · Alterna, motores y protecciones |
| 🧮 Matemáticas (6 · 60 min) | Suma, resta y complementos relámpago · Multiplicaciones relámpago y atajos directos · Porcentajes instantáneos y la regla reversible · Multiplicación védica cruzada y método de la base 100 · Cuadrados, raíces y productos notables mentales · Verificación por prueba del 9 y la Regla del 72 |

Los capítulos viven en `appstudy/content/readings/*.json`. Cada uno tiene `level`,
`minutes`, `tags` (define qué tarjetas se practican al final) y un `body` de bloques:

| Bloque | Para qué |
|---|---|
| `h` | título de sección |
| `p` | párrafo |
| `list` / `steps` | lista con viñetas o numerada |
| `code` | bloque de código, con colores si se reconoce el lenguaje |
| `math` | una fórmula suelta en LaTeX, centrada |
| `note` 💡 / `warn` ⚠️ / `key` 🔑 | recuadros destacados |
| `quote` | cita o ejemplo largo |

## Fórmulas y código

**Las fórmulas se escriben en LaTeX**, entre `$…$` dentro de un texto o como un
bloque `{"math": "…"}` en un capítulo. No hace falta instalar nada: se dibujan con
el propio texto —Unicode más los `<sup>`/`<sub>` de Pango— así que se pueden
seleccionar, copiar y escalan con la letra, y se ven igual en la lectura, en el
popup y en el globo de la mascota.

```json
{"math": "\\sigma = \\sqrt{\\frac{\\sum (x_i-\\bar{x})^2}{n}}"}
```

    σ = √((∑ (xᵢ-x̄)²)/n)

Se entienden `\frac`, `\sqrt`, `^` y `_`, las letras griegas y el centenar de
símbolos de `appstudy/mates.py` (`\times`, `\leq`, `\sum`, `\rightarrow`,
`\bar{x}`, `\text{...}`…). Lo que no conoce lo deja escrito tal cual, sin
romper nada.

Para que un `$` suelto siga siendo un `$`, una fórmula **en línea** solo se
interpreta si trae una señal inequívoca de LaTeX: una orden con barra, un
exponente o un subíndice. Así `awk '{print $1}'` o «cuesta $5 y $9» se quedan
como están. En bloque (`$$…$$`) no hace falta señal.

**El código se colorea con Pygments** (`sudo apt install python3-pygments`), tanto
en los bloques `code` de las lecturas como en un `<code>` de varias líneas dentro
de una tarjeta. El lenguaje se declara o se adivina, y arriba a la derecha se
enseña cuál salió:

```json
{"code": {"lang": "sql", "text": "SELECT ..."}}
```

Muchos bloques de las lecturas no son código sino tablas y diagramas hechos con
caracteres. Por eso el lenguaje solo se da por bueno cuando hay señales claras
—`SELECT` al principio de línea, `import`, un `$` de terminal, una orden conocida,
un `[Unit]`—; en la duda no se colorea, que es mejor que colorear al azar. Si
Pygments no está instalado, el código se enseña igual, solo que sin color.

## Contenido propio

Desde la ventana principal (botón **+**) puedes crear tres tipos de tarjeta:

- **Tarjeta**: pregunta y respuesta, con pista opcional.
- **Reto**: opción múltiple con explicación del porqué.
- **Lección**: solo enseña algo, sin preguntar.

Cada una se guarda en un mazo y un **nivel**, y en el explorador puedes filtrar por
ambos.

Admite `<b>negrita</b>`, `<i>cursiva</i>`, `<code>código</code>` y fórmulas en
LaTeX entre `$…$` (ver [Fórmulas y código](#fórmulas-y-código)).

Los mazos de fábrica viven en `appstudy/content/*.json`; puedes editarlos y pulsar
**Recargar mazos incluidos** en Ajustes (o subir `CONTENT_VERSION` en
`appstudy/seed.py`, que reimporta solo al arrancar) — se actualiza el texto **sin perder tu progreso**
(cada tarjeta se identifica por su enunciado). Cada archivo define sus propios `levels`,
y cada tarjeta su `level` (1 = el más básico).

⚠️ Al recargar, una tarjeta de fábrica que ya **no** esté en el JSON se retira junto con
su historial. Tus tarjetas propias nunca se tocan.

## Tu biblioteca

La pestaña **Biblioteca** organiza los libros que ya tienes y los abre **dentro de
AppStudy**, con un lector de PDF que recuerda por dónde ibas. Los libros no se
copian ni se tocan: se leen donde están, y en la base solo queda su ruta, la
página y los minutos leídos.

**El estante**

- Arriba, **Seguir leyendo**: los últimos libros que abriste, con su portada de
  verdad (la primera página del PDF), la barra de avance y «pág. 77 de 198».
- Debajo, tus carpetas convertidas en **estantes** que se despliegan —
  `Mecanica`, `Python`, `SQL`…— con cuántos libros tiene cada una y cuántos
  llevas empezados. Los libros de un estante se pintan al abrirlo, no antes: con
  1.281 libros la diferencia es entre instantáneo y esperar.
- El buscador filtra por título y por carpeta a la vez, y cada resultado enseña
  su portada y su avance.

**El lector**

| Tecla | |
|---|---|
| ← → · Espacio · AvPág/RePág | pasar página (la rueda al final de la hoja también) |
| Inicio / Fin | primera y última |
| + / − · Ctrl+rueda | zoom, del 35 % al 400 % |
| F | alternar ajuste **al ancho** / **a la página** |
| Ctrl+F | buscar en todo el libro |
| M | marcador en esta página |
| N | modo noche |

- **Zoom de verdad**: la hoja pide su tamaño y el lector la deja desplazarse. Se
  recuerda por libro cómo lo estabas leyendo (ajuste y escala).
- **Buscar en todo el libro**: saca el texto entero una vez y enseña en qué
  página está cada aparición, con su frase; pulsas y saltas allí.
- **Marcadores** por página, con su lista en el menú ⋯.
- **Modo noche**: invierte la página *en la GPU* (mezcla por diferencia), sin
  reprocesar la imagen ni gastar memoria.
- **Copiar el texto de la página** y **✦ Tarjetas** de las páginas que tienes
  delante, desde el mismo menú.

**El progreso se guarda solo**, en cada cambio de página: cierras el libro,
vuelves mañana y sigues en la 77. Al salir también se anotan los minutos leídos.

Las páginas se dibujan con `pdftocairo` (poppler, ya lo tienes) en un hilo
aparte, y se guardan en `~/.local/share/appstudy/paginas`: dibujar una tarda
~150 ms, volver a ella es instantáneo, y mientras lees una ya se está dibujando
la siguiente. La caché se puede borrar cuando quieras — se rehace sola.

## Preguntarle a Bit (IA local)

Bit puede conectarse a un **modelo de lenguaje que corre en tu propia máquina**.
Ni tus tarjetas ni tus preguntas salen del equipo, no hay clave de API que
guardar y no cuesta nada por pregunta.

```bash
curl -fsSL https://ollama.com/install.sh | sh   # el servidor
ollama pull gemma3:4b                           # el modelo (o gemma4 cuando lo tengas)
```

Después, en **Ajustes → Inteligencia artificial**: activa el interruptor y pulsa
**Probar conexión**. Si el modelo que pusiste no está descargado, AppStudy usa el
gemma que encuentre y te lo dice.

| Dónde | Qué hace |
|---|---|
| Menú de Bit → **Pregúntame algo** | una pregunta suelta; si venías de una tarjeta, la usa como contexto |
| En una tarjeta → **🧠 Explícamelo mejor** | te la explica con otras palabras y un ejemplo |
| En una tarjeta → **💬 Modo chatbot** | abre una conversación nueva y sigue el hilo |
| Tarjetas → botón ✦ | genera tarjetas sobre un tema, **tú marcas cuáles se guardan** |

### Modo chatbot

Desde cualquier tarjeta, **💬 Modo chatbot** abre una conversación nueva con esa
tarjeta como contexto: Bit recuerda lo que lleváis hablado (los últimos seis idas
y vueltas, que a un modelo pequeño más historial le sienta mal) y puedes tirar
del hilo — «¿y si es más rica?», «ponme un ejemplo».

Mientras charláis se nota a la legua: **Bit se pone azul** —el estallido, los
cachetes y la barra abandonan la paleta cálida— y el globo cambia de fondo,
borde y sombra al mismo azul, con tus mensajes a la derecha y los suyos a la
izquierda. **Salir del chat** lo devuelve todo a su color y a lo suyo.

La respuesta se escribe **en directo** en el globo (Bit mueve la boca mientras
tanto) y todo el trabajo va en un hilo aparte, así que la ventana nunca se
congela. Está en `appstudy/ia.py`, sin dependencias nuevas: habla HTTP con la
biblioteca estándar.

⚠️ Un modelo local se equivoca, y una tarjeta mala se estudia igual que una
buena: por eso lo generado se revisa antes de guardarse, y las tarjetas quedan
etiquetadas con `ia` para que puedas encontrarlas después.

**Nada de esto entra en el repositorio.** Los pesos del modelo viven en
`~/.ollama` (fuera del proyecto) y la configuración —servidor y modelo— en tu
base de datos. El `.gitignore` bloquea además `*.gguf`, `*.safetensors`,
`models/`, `.env` y las claves, por si algún día pruebas con archivos sueltos.

Con qué modelo: en un equipo con 4 GB de VRAM va bien un **4B** cuantizado
(rápido, cabe en la gráfica); un 12B funciona tirando de los 30 GB de RAM, pero
responde bastante más despacio.

## Empezar de cero

En Ajustes → **Apariencia y progreso** hay dos botones que piden confirmación:

- **Borrar lo estudiado hoy** — quita los repasos de las últimas 24 h (lo que cuenta
  como «hoy») y deja cada tarjeta como estaba antes: el estado no se puede restar, así
  que se rehace desde cero con los repasos anteriores de esa tarjeta, en orden. La
  racha se recalcula sola.
- **Reiniciar la racha** — vuelve a cero sin tocar ninguna tarjeta: a partir de ese
  momento solo cuentan los repasos nuevos (`racha_desde` en la tabla `meta`).

## Respaldo

Todo tu progreso —tarjetas, repasos, racha, libros y por dónde ibas— vive en un
solo archivo SQLite: `~/.local/share/appstudy/appstudy.db`.

En **Ajustes → Respaldo**:

| Qué | Para qué |
|---|---|
| **Respaldar** | una copia ahora mismo, en `~/.local/share/appstudy/backups` |
| **Respaldo automático diario** | al abrir la aplicación, si el último ya tiene más de un día (activado de fábrica) |
| **Restaurar…** | la lista de tus respaldos, con su fecha y su tamaño, o un archivo que traigas de fuera |
| **Exportar…** | guardar una copia donde tú digas, para llevártela a otro equipo o a un disco |

Copiar el archivo con `cp` mientras la aplicación escribe puede dejarte una copia
a medias, y más con WAL, donde parte de lo reciente está en otro archivo. Por eso
se usa la API de respaldo de SQLite, que copia una base abierta y en uso sin
partirla, y se escribe primero a un archivo temporal: si algo falla a mitad no
queda un respaldo cortado con nombre de bueno.

**Restaurar no reinicia nada.** El archivo elegido se vuelca *dentro* de la
conexión viva, así que las otras ventanas y la mascota siguen funcionando y ven
los datos nuevos. Antes de pisar nada se guarda un respaldo de lo que tienes en
ese momento (`-antes` en el nombre), así que restaurar por error tiene vuelta
atrás. Y no se restaura cualquier cosa: si el archivo no es una base de AppStudy
se dice y no se toca nada.

Se guardan los **40 respaldos automáticos** más recientes; los que haces a mano y
los de «antes de restaurar» no se borran nunca.

## Pruebas

```bash
./pruebas.sh              # todas
./pruebas.sh scheduler    # solo las del planificador
```

126 pruebas sobre lo que no lleva interfaz: el algoritmo de repetición espaciada,
los seis formatos de reto, las fórmulas en LaTeX, el respaldo y la validez del
contenido incluido. No hace falta instalar nada más — son `unittest` de la
biblioteca estándar — y ninguna toca tu progreso real: cada caso arranca con una
base vacía en un directorio temporal. Los detalles, en `tests/README.md`.

## Desinstalar

```bash
rm ~/.local/bin/appstudy \
   ~/.local/share/applications/io.github.appstudy.AppStudy.desktop \
   ~/.local/share/icons/hicolor/scalable/apps/io.github.appstudy.AppStudy.svg \
   ~/.config/autostart/appstudy-pet.desktop
rm -rf ~/.local/share/gnome-shell/extensions/appstudy@luisalcides.github.io
```
Y quita el atajo desde Ajustes → **Quitar**; del dock, clic derecho → **Quitar de
favoritos**. Tu progreso queda en `~/.local/share/appstudy/`.
# appstudy
