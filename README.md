# AppStudy

Aplicación de escritorio con **tres formas de estudiar**:

- **Modo lectura** — 31 capítulos que se leen de corrido, como un libro: portada, títulos,
  ejemplos, avisos y navegación entre capítulos. Para aprender algo desde cero.
  Los cinco de inglés son los más extensos (104 min, y casi la mitad en A2).
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

Temas incluidos (**450 tarjetas** de fábrica, ordenadas **de básico a avanzado**):

| Mazo | Niveles | Contenido |
|---|---|---|
| 🗣️ Inglés (98) | A2 · B1 · B2 · C1 | **todo en inglés**: gramática, phrasal verbs, vocabulario y escritura profesional |
| 🐧 Linux (63) | Básico · Intermedio · Avanzado | shell, permisos, procesos, systemd, red, SSH, LVM, scripting |
| 📊 Ciencia de Datos (61) | Básico · Intermedio · Avanzado | estadística, pandas, SQL, modelado, experimentos, producción |
| 🤖 Inteligencia Artificial (62) | Básico · Intermedio · Avanzado | LLM, RAG, embeddings, agentes, evaluación, coste y criterio |
| 🚜 Maquinaria Amarilla y Volquete (62) | Básico · Intermedio · Avanzado | hidráulica, tren de rodaje, diagnóstico, seguridad, gestión |
| 🔧 Mecánica Automotriz (62) | Básico · Intermedio · Avanzado | motor, frenos, eléctrico, diagnóstico OBD2, common rail, híbridos |
| ⚡ Electricidad y Electrónica (42) | Básico · Intermedio · Avanzado | Ohm, medición, componentes, PWM, alterna, motores, protecciones |

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
`python3-pygments` para los colores del código.

El lanzador se llama `io.github.appstudy.AppStudy.desktop`, igual que el id de la
aplicación: es lo que mira GNOME para emparejar la ventana abierta con su icono
del dock. El icono está en `appstudy/data/` — una tarjeta de estudio con el
asterisco de Bit, dibujado con la misma geometría de once rayos que la mascota.

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
espacios de trabajo. Está dibujado a la manera de la mascota de Claude: cuerpo
crema, tinta cálida y un asterisco de once rayos girando sobre la cabeza, que se
acelera cuando tiene algo que enseñarte. Es un homenaje hecho a mano con Cairo,
no el logotipo de nadie.

Como se pasa el día sobre fondos que no controla, lleva contorno cálido y una
sombra suave alrededor (tres trazos, porque Cairo no tiene desenfoque): se ve
igual sobre un escritorio negro, uno crema o una foto. Está dibujado en un lienzo
fijo de 152×176 que luego se escala, así que para hacerlo más grande o más
pequeño basta con cambiar `ANCHO` y `ALTO_PET` en `appstudy/pet.py`.

El asterisco, los cachetes y la barra de energía llevan el color de su ánimo:
terracota cuando todo va normal, verde si estás al día, ámbar si se te acumulan
repasos, teja si llevas mucho sin aparecer. La barra bajo sus pies es su energía,
que baja con las horas sin repasar y con lo que tienes pendiente.

| Acción | Qué hace |
|---|---|
| Clic | salta y te enseña una tarjeta en el globo |
| Pasar el ratón | te sigue con la mirada |
| Arrastrar | la mueve; recuerda dónde la dejaste |
| Clic derecho | menú: enséñame algo, ponme a prueba, una frase de libro, sesión completa, abrir AppStudy, dormir, salir |

Cuando **enseña**, enseña de verdad: la pregunta y la respuesta salen juntas desde
el primer momento, sin botón de por medio. Tú solo dices si la tenías —**No lo
sabía** / **Lo sabía**— y cuenta como un repaso normal, con el mismo intervalo que
el popup.

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

31 capítulos, **362 minutos** de material, ordenados por nivel dentro de cada mazo:

| Mazo | Capítulos |
|---|---|
| 🗣️ Inglés | Building a sentence (A2) · Getting things done (A2) · Present Perfect and phrasal verbs (B1) · Conditionals and professional writing (B2) · Register (C1) · Writing that gets read (C1) |
| 🐧 Linux | La terminal sin misterio · Tuberías · Permisos, procesos y servicios · Scripts que no te traicionan · El servidor por dentro |
| 📊 Ciencia de Datos | Mirar los datos antes de tocarlos · Entrenar sin engañarte · De un cuaderno a un sistema · Decidir con números sin engañarse |
| 🤖 Inteligencia Artificial | Qué es un modelo de lenguaje · RAG, herramientas y agentes · Seguridad, límites y criterio · Construir un RAG que no se inventa las cosas |
| 🚜 Maquinaria | Antes de mover la máquina · El sistema hidráulico · Tren de rodaje y volquete · Diagnóstico y predictivo · Hidráulica fina |
| 🔧 Automotriz | Cómo funciona un motor · Diagnóstico: leer los síntomas · Electrónica, common rail e híbridos · Gestión del motor |
| ⚡ Electricidad | Cuatro magnitudes y una sola ley · Los componentes y lo que hace cada uno · Alterna, motores y protecciones |

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

## Dónde se guardan tus datos

`~/.local/share/appstudy/appstudy.db` (SQLite). Para respaldar, copia ese archivo.

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
