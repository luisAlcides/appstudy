# AppStudy

Aplicación de escritorio con **tres formas de estudiar**:

- **Modo lectura** — 145 capítulos que se leen de corrido, como un libro: portada, títulos,
  ejemplos, avisos y navegación entre capítulos. Para aprender algo desde cero.
  Inglés incluye veinte capítulos de A2 a C1 (208 min).
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
con las tarjetas de ese tema y ese nivel; **«✦ Sacar tarjetas»** propone tarjetas
del texto con la IA local; y desde una tarjeta, **«Volver a la fuente →»** abre
el capítulo o página exactos de donde salió.

Las fórmulas se escriben en **LaTeX** y el código sale **coloreado**; los detalles,
en [Fórmulas y código](#fórmulas-y-código).

Temas incluidos (**1.245 tarjetas** de fábrica, ordenadas **de básico a avanzado**):

| Mazo | Niveles | Contenido |
|---|---|---|
| 🗣️ Inglés (233) | A2 · B1 · B2 · C1 | **todo en inglés**: gramática, phrasal verbs, vocabulario, acuerdos, negociación y síntesis de fuentes |
| 🐧 Linux (172) | Básico · Intermedio · Avanzado | shell, permisos, procesos, systemd, red, SSH, LVM, codificación, inodos y escritura atómica |
| 📊 Ciencia de Datos (268) | Básico · Intermedio · Avanzado | estadística, pandas, SQL, modelado, granularidad, cardinalidad y disponibilidad temporal |
| 🤖 Inteligencia Artificial (141) | Básico · Intermedio · Avanzado | LLM, RAG, embeddings, agentes, razonamiento, MCP, inferencia, extracción validada, evaluación y abstención |
| 🚜 Maquinaria Amarilla y Volquete (150) | Básico · Intermedio · Avanzado | hidráulica, transmisiones powershift, GET, orugas SALT, CAN J1939, ciclos y flotas |
| 🔧 Mecánica Automotriz (100) | Básico · Intermedio · Avanzado | motor, frenos, eléctrico, OBD2, common rail, híbridos, bitácora, consumo y evidencia diagnóstica |
| 🧮 Matemáticas y Cálculo Rápido (95) | Básico · Intermedio · Avanzado | cálculo mental, porcentajes, cuadrados, fracciones, ecuaciones y probabilidad |
| ⚡ Electricidad y Electrónica (86) | Básico · Intermedio · Avanzado | Ohm, medición, componentes, motores, Kirchhoff, circuitos RC y conversión ADC |
| 🐍 Python y Análisis de Datos (84) | Básico · Intermedio · Avanzado | currículo freeCodeCamp: sintaxis, NumPy, Pandas, visualización (Matplotlib, Seaborn) y los 5 proyectos de certificación |

La ampliación general incorpora **25 lecturas y 150 tarjetas**: una lectura y seis tarjetas
por nivel en cada mazo (cuatro niveles en inglés y tres en los demás). Cada lectura
nueva incluye explicación, ejemplo resuelto, ejercicio con solución y tarjetas
con las mismas etiquetas para practicar al terminar. Hay preguntas abiertas,
retos de opción múltiple y huecos; el contenido de inglés se mantiene en inglés.

Inglés añade además **8 lecturas y 80 tarjetas** específicas: dos lecturas y veinte
tarjetas por nivel. Las nuevas tarjetas se reparten en **32 retos de opción
múltiple**, **32 frases con huecos** y **16 retos de escritura o corrección** con
respuesta orientativa para autoevaluarse. Las opciones múltiples muestran la
respuesta correcta y su explicación al responder.

| Nivel | Nuevas lecturas de inglés |
|---|---|
| A2 | Compras, precios y cantidades; direcciones y lugares de la ciudad |
| B1 | Narraciones con tiempos pasados; reservas, viajes y cambios de planes |
| B2 | Reclamaciones y solicitudes concretas; comparación de opciones |
| C1 | Argumentación y contraargumentos; precisión, ambigüedad y estructura paralela |

Linux añade **6 lecturas y 60 tarjetas** propias: dos lecturas por nivel con
sus bloques de código, un ejemplo resuelto y un ejercicio con solución. Las
tarjetas se reparten en **30 preguntas abiertas**, **18 retos de opción
múltiple** y **12 frases con huecos**, todas con la etiqueta de su lectura para
practicarlas al terminar de leer.

| Nivel | Nuevas lecturas de Linux |
|---|---|
| Básico | Rutas, comodines y comillas; empaquetar, comprimir y copiar |
| Intermedio | Redirección y código de salida; entorno, PATH y archivos de inicio |
| Avanzado | Señales y procesos que no se van; carga, memoria y espera de disco |

### Niveles

Cada tarjeta tiene un nivel. Las tarjetas **nuevas siempre entran de menor a mayor
nivel**: no verás nada de C1 mientras te queden tarjetas de A2 sin estudiar. Los repasos,
en cambio, aparecen cuando toca, sin importar el nivel.

El mazo de inglés está **íntegramente en inglés** y va de A2 a C1, repartido entre
gramática, phrasal verbs y vocabulario.

**Fuentes y extensiones:** Wikipedia, OpenStax, MIT OpenCourseWare, carpetas Markdown,
OCR, consultas a documentos con citas, subtítulos y Anki multimedia. Se abren desde
**Biblioteca → Fuentes** o **Ajustes → Avanzado → Extensiones y fuentes**.
Consulta la [guía de uso y creación de plugins](docs/extensiones.md).

## Instalación

```bash
./install.sh                      # atajo por defecto: Super + Shift + E
./install.sh '<Control><Alt>e'    # o el que prefieras
./install.sh --defaults           # sin preguntas, con lo ya elegido
```

El instalador deja el comando `appstudy` en `~/.local/bin`, el icono en el tema
del escritorio, el lanzador (con sus acciones «Estudiar ahora» y «Soltar a Bit»),
registra el atajo global e instala la extensión de la barra superior. Se puede
repetir sin miedo: no duplica nada.

Antes de descargar nada **pregunta qué quieres**, con el tamaño de cada cosa al
lado, porque entre todo suman casi cuatro gigas:

| Pregunta | Opciones | Descarga |
|---|---|---|
| Voz | Kokoro + Piper de reserva · solo Piper · ninguna | ~360 MB · ~80 MB · nada |
| Reconocimiento de voz (Vosk) | sí / no | ~90 MB |
| IA local (`gemma3:4b` en Ollama) | sí / no | ~3,3 GB |
| Bit al iniciar sesión | sí / no | — |
| Anclar al dock | sí / no | — |

Las respuestas quedan en `~/.config/appstudy/instalacion.conf`, y las siguientes
ejecuciones las respetan: `actualizar.sh` no volverá a intentar los tres gigas
del modelo de IA que dijiste que no querías. Para cambiar de idea basta volver a
ejecutar `./install.sh` y responder otra cosa —decir que no a la mascota también
la quita del autoarranque—, o editar ese archivo a mano. Sin terminal delante
(una tubería, un script) no pregunta: usa lo guardado, y en una instalación nueva
lo instala todo, como antes.

Requiere Python 3 con GTK4 y libadwaita, que ya vienen en Ubuntu/Mint con GNOME
(`sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1` si faltaran),
`python3-pygments` para los colores del código y `gir1.2-webkit-6.0` para leer
EPUB (sin él, todo lo demás funciona igual). La IA local es opcional y va
aparte (ver [Preguntarle a Bit](#preguntarle-a-bit-ia-local)), y los motores de
voz los descarga el propio instalador salvo dos cosas que piden root
(ver [Voz](#voz-leer-en-voz-alta-y-responder-hablando)).

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
| Motores o voces nuevas (Kokoro, Piper, Vosk) | `./install.sh` (o `./actualizar.sh`) |
| `sox` o `vosk` | a mano, una vez (ver abajo) |

### Actualizar en una máquina que ya tenía AppStudy

`actualizar.sh` llama a `install.sh --defaults`, y este salta lo que ya esté,
respeta lo que elegiste al instalar y descarga solo lo que falte de eso. Así que **para la voz y el oído no hay que hacer nada más**: la
primera actualización después de un cambio de motor se lleva un rato porque baja
lo que no tuvieras (Kokoro y su entorno son ~490 MB, una voz de Piper ~75 MB, los
modelos de Vosk ~126 MB), y las siguientes no bajan nada.

Lo único que hay que poner a mano, una sola vez por máquina, porque toca el
sistema y el instalador no puede:

```bash
sudo apt install sox            # control de tono de la voz
pip install --user vosk         # oír lo que dices, y el «hola bit»
```

Después de actualizar, para que todo coja lo nuevo:

- **La ventana principal**: ciérrala y ábrela (el propio script te lo recuerda).
- **Bit**: `actualizar.sh` ya la reinicia. A mano sería
  `appstudy --pet-off && appstudy --pet`. Hace falta para que empiece a escuchar
  el «hola bit», que se pone en marcha al arrancar la mascota.
- **La extensión de GNOME**: solo si cambió, y entonces hay que cerrar sesión.

Para comprobar que quedó todo en su sitio:

```bash
python3 -c "
from appstudy import voz, voz_rec
import shutil
print('motor de voz:', voz.motor_actual())
print('voces:      ', voz.voz_actual('es'), '·', voz.voz_actual('en'))
print('oído:       ', voz_rec.tiene_reconocimiento_voz('es'))
print('hola bit:   ', voz_rec.EscuchaPalabraClave.disponible('es'))
print('tono (sox): ', bool(shutil.which('sox')))"
```

Con todo puesto responde `kokoro`, las dos voces, y `True` en las tres últimas.
Un `piper` en la primera línea significa que Kokoro no llegó a instalarse —se oye
bien igual, pero menos natural—; un `False` en el oído deja el «hola bit» y las
respuestas habladas fuera, y se arregla con el `pip install` de arriba. Los
ajustes viven en la base de datos, así que **no se pierde nada al actualizar**:
volumen, velocidad, tono y el interruptor del «hola bit» siguen como los dejaste.

## Uso

| Acción | Cómo |
|---|---|
| Popup de repaso | el atajo global, desde cualquier aplicación |
| Capturar una tarjeta | `appstudy --capture` o `Super` + `Shift` + `N` |
| Ventana completa | `appstudy`, o «AppStudy» en el menú de aplicaciones |
| Abrir la guía de uso | **F1**, el botón **?** de la cabecera o `appstudy --ayuda` |
| Ver tu progreso en gráficas | pestaña **Progreso** |
| Buscar en todo a la vez | **Ctrl+K** desde cualquier ventana |
| Escribir un capítulo tuyo | pestaña **Leer** → «Escribir un capítulo» |
| Leer un capítulo | pestaña **Leer**, o «Continuar leyendo» en el panel |
| Estudiar un solo tema | `appstudy --popup --deck linux` |
| Soltar la mascota | `appstudy --pet`, o Ajustes → **Bit, la mascota**, o el interruptor de la barra superior |
| Recargar el contenido | **Ctrl+R** o **F5** en cualquier ventana, o `appstudy --reload` |
| Abrir la lectura de una tarjeta | `appstudy --read-card <id>` (es lo que usa Bit) |
| Ver las tarjetas que se te atragantan | `appstudy --leeches` |
| Ver el estado en JSON | `appstudy --status` (lo usa la extensión de GNOME) |

Si editas un JSON de `appstudy/content/`, **Ctrl+R** lo mete en la base y refresca la
ventana sin perder tu progreso. Y si el cambio viene con la aplicación, basta con subir
`CONTENT_VERSION` en `appstudy/seed.py`: se reimporta solo en el siguiente arranque.

### Teclas dentro del lector

| Tecla | Acción |
|---|---|
| `←` `→` | capítulo anterior o siguiente |
| `Esc` | volver a la biblioteca |

Los capítulos que escribas tú llevan un lápiz al lado para editarlos, y en la
cabecera de la pestaña está **«Escribir un capítulo»**.

Un capítulo se marca como leído solo cuando llegas al final, o a mano con el botón.

### Teclas dentro del popup

| Tecla | Acción |
|---|---|
| `Espacio` | mostrar la respuesta |
| `1` – `4` | responder un reto, o calificar: Otra vez / Difícil / Bien / Fácil |
| `Z` | deshacer el último repaso |
| `N` | saltar a otra tarjeta |
| `A` | abrir la ventana completa |
| `Esc` | cerrar |

## La guía, dentro de la aplicación

Con **F1**, el botón **?** de la cabecera o `appstudy --ayuda` se abre la **guía de
uso**: trece temas cortos —los primeros diez minutos, los atajos, cómo se
califica, cuándo vuelve cada tarjeta, las tarjetas, importar de Anki, los
capítulos, la biblioteca, Bit, la IA local, el progreso, sincronizar y respaldar,
y qué hacer si algo no va— agrupados en cinco bloques, con un buscador arriba y
un «ver también» al final de cada uno. Bit también la abre desde su menú, en
**Cómo se usa**.

El buscador es el mismo criterio que el de Ctrl+K: se exigen **todas** las
palabras y no distingue acentos ni mayúsculas, así que «sincronizacion» encuentra
«Sincronizar y respaldar» y «teclas» lleva a los atajos. Cada tema trae además
unas cuantas palabras por las que uno lo buscaría aunque no salgan en el texto
(«portátil», «nextcloud», «no funciona»).

Los temas viven en `appstudy/ayuda.py`, **sin nada de GTK**, y se escriben con los
mismos bloques que un capítulo (`p`, `list`, `steps`, `code`, `note`, `warn`,
`key`…). Los pinta `reader.render_body`, el renderizador del modo lectura: la
ayuda se lee con la misma tipografía que lo demás y no hay una segunda forma de
maquetar que mantener. Añadir un tema es añadir un diccionario a `TEMAS`; las
pruebas avisan si le falta un campo, si usa un bloque que nadie sabe pintar o si
un «ver también» apunta a un tema que no existe.

## Bit, la mascota

[Vista previa animada de Bit](docs/bit-demo.gif).

Vive en una ventanita sin bordes, **siempre encima del resto** y en todos los
espacios de trabajo. Es el asterisco de Claude cobrando vida: un **estallido de
once rayos** en el color de su ánimo y, delante, un mochi crema con la cara —
ojos grandes y brillantes, cejas que dicen cosas, dos manoplas y dos pies que
asoman por debajo. Un homenaje hecho a mano con Cairo, no el logotipo de nadie.

El estallido gira despacio todo el rato, sus rayos ondulan apenas para que la
silueta respire, se acelera y se enciende cuando tiene algo que enseñarte, y
casi se para y se encoge cuando llevas días sin aparecer. Los cambios de color
y de energía se funden de forma gradual, sin saltos entre estados.
Como se pasa el día sobre fondos que no controla, todo lleva contorno cálido y
una sombra suave (dos trazos concéntricos, que Cairo no tiene desenfoque): se ve
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
| Tarjetas recientes (icono de historial o clic derecho) | recupera las últimas tarjetas para releerlas |
| Clic derecho | menú: enséñame algo, ponme a prueba, una frase de libro, **cómo va la semana**, sesión completa, abrir AppStudy, **más grande / más pequeño**, dormir, salir |

**Volver a una tarjeta**: pulsa el icono de historial del globo o elige
**Tarjetas recientes** con clic derecho sobre Bit. También está en la cabecera
de AppStudy y de la ventana de estudio. Conserva las últimas 100 tarjetas
mostradas en este equipo, incluso las que cerraste sin responder, y permite
buscar por texto o mazo. Selecciona una para ver la pregunta y su respuesta;
consultarla no la vuelve a calificar ni cambia su próximo repaso. El historial
permanece al reiniciar y se incluye en los respaldos locales. Al estrenarlo
recupera los repasos anteriores que aún constan en la base de datos; las
tarjetas cerradas sin responder antes de esta función no se pueden reconstruir.

**Tamaño**: del 50 % al 250 %, desde su menú (pasos del 15 %) o con el número exacto en
Ajustes → Progreso. Se guarda, y la mascota lo recoge sola aunque lo cambies desde la
ventana principal.

**Evolución y accesorios**: Bit pasa de Compañero a Curioso, Aplicado, Sabio y
Maestro según tus repasos reales —no por dejar la aplicación abierta—. En 25,
100 y 500 repasos desbloquea un pañuelo, unas gafas y una corona. Desde
**Ajustes → Apariencia y progreso** eliges cuál lleva y ves el avance hacia la
siguiente etapa. Todo se dibuja con unas pocas curvas Cairo, sin cargar sprites
ni mantener otra animación.

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

En Ajustes puedes limitar esos avisos a **días laborables, fines de semana o
todos los días**, y elegir la franja horaria. También admite horarios que cruzan
la medianoche. La comprobación aprovecha el mismo pulso ligero que ya actualiza
a Bit: no se crea ningún servicio ni temporizador adicional.

Si prefieres una interfaz más quieta, **Ajustes → Apariencia y progreso → Reducir
movimiento** detiene rebotes, balanceos, partículas y transiciones. Las miradas,
caras y cambios de color permanecen para que Bit conserve sus emociones sin
movimiento innecesario.

### Cómo va la semana

Bit lleva la cuenta y de vez en cuando te la cuenta: «esta semana estudiaste 6
días y 144 tarjetas; el mejor día fue el sábado, con 32; acertaste el 90 %; un
17 % más que la semana pasada». También la pides tú desde su menú, en **Cómo va
la semana**. Sale como mucho una vez al día, y compara siempre con los siete
días anteriores, que es lo que da sentido al número.

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

### «Volver a la fuente →» lleva a la lectura

Las tarjetas creadas desde un capítulo, un PDF, un EPUB o un subrayado guardan
un vínculo explícito con su origen. El pie del globo de Bit y la respuesta del
popup vuelven a esa lectura: al párrafo del capítulo, a la página del PDF o al
capítulo numerado del EPUB. El vínculo también viaja con la sincronización.

Para las tarjetas antiguas que no tienen vínculo, se conserva la búsqueda por
las etiquetas, el nivel y las palabras en común (`db.chapter_for_card`); el
párrafo se elige por lo que comparte con la pregunta y la respuesta
(`reader._mejor_bloque`). Una fuente explícita siempre gana a ese parecido para
no mandar a un capítulo casual.

Por dentro es `appstudy --read-card <id>`: la mascota vive en otro proceso, así
que se lo pide a la aplicación principal por la línea de órdenes.

### Cómo se mueve

Nunca está quieto: respira, se balancea, parpadea (a veces dos veces seguidas),
mira alrededor y sigue el ratón con las pupilas. Al aparecer cae con un pequeño
rebote; cuando te acercas se inclina con curiosidad, levanta las cejas y las
manos, sonríe y enciende tres motas alrededor. Cada pocos segundos hace un gesto
suelto —saltar, estirarse, ladear la cabeza, asentir, sorprenderse o agitar la
antena— y reacciona a lo que pasa: saluda al avisarte, mueve la boca mientras
habla, ríe y baila cuando está feliz, bosteza si se aburre, suspira o tirita si
está bajo de ánimo, saca corazones y chispas cuando aciertas, una gota cuando
fallas, y zZz mientras duerme. Los saltos tienen anticipación, vuelo y un
aterrizaje elástico; cada gesto mueve de forma coordinada los ojos, las cejas,
la boca, las manos, los pies y el cuerpo.

Todo está dibujado con Cairo en `appstudy/pet.py`: los gestos puntuales se lanzan
con `play(nombre, segundos)` y `phase(nombre)` dice por dónde van, de 0 a 1.

### Lo que gasta

Bit limita el trabajo en reposo y usa el reloj de fotogramas de GTK durante los
gestos. El consumo depende de la pantalla, el tamaño y el renderizador; las
mediciones de versiones anteriores no describen esta nueva animación.

- **`GSK_RENDERER=cairo`** (se pone en `bin/appstudy`). Para una ventanita de 168
  píxeles dibujada a mano, el renderizador de software gasta menos de la mitad
  que el acelerado y 60 MB menos, porque el coste está en subir la textura en
  cada fotograma, no en pintarla.
- **Cadencia adaptativa**: los gestos siguen la frecuencia de la pantalla;
  en reposo dibuja como máximo 20 veces por segundo, y 10 con movimiento reducido.
- **Reloj de animación**: se pausa cuando el widget no está mapeado y se retoma
  sin saltos. Los cambios de hora del sistema no interrumpen los gestos.
- **Movimiento reducido**: respeta tanto Ajustes de AppStudy como la preferencia
  de animaciones de GTK; elimina partículas, deformaciones y destellos móviles.

Las tarjetas y el chat componen el color de tarjeta de Adwaita sobre una base
opaca. Así, incluso cuando el tema oscuro usa un color con transparencia, el
escritorio no se ve a través del texto. Solo el lienzo de la mascota y sus
contenedores externos quedan transparentes.

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
los cuatro números (pendientes, hoy, racha, dominadas), tu **objetivo del día**
con la semana en siete barritas, cuándo toca el siguiente repaso, cuántas
tarjetas se te atragantan, una frase de libro, y accesos a **Estudiar ahora**,
**Abrir AppStudy** y un interruptor para **soltar o guardar a Bit**.

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

AppStudy usa **FSRS**, el mismo modelo de memoria que trae Anki. En vez de un
«factor de facilidad» que sube y baja a ojo, guarda de cada tarjeta dos cosas:

- **Estabilidad**, en días: cuánto aguanta ese recuerdo. Es, por definición, los
  días que tardas en bajar al 90 % de probabilidad de acordarte.
- **Dificultad**, de 1 a 10: lo que te cuesta esa tarjeta en concreto.

Con eso el intervalo deja de ser una multiplicación: se calcula **el día en que
ibas a olvidarla**. Tú eliges cuánto quieres acordarte —la **retención
objetivo**— y la cuenta la hace la fórmula. Al 90 %, que es lo recomendado, una
tarjeta con 40 días de estabilidad vuelve a los 40 días; si subes al 95 %,
vuelve a los 18; si bajas al 85 %, a los 65.

Lo que hace que salgan menos repasos para el mismo resultado es que el modelo
sabe que **repasar algo que ya te sabías de sobra apenas aporta**: la memoria
crece más cuanto más cerca estabas de olvidarlo. Acertando siempre «Bien», FSRS
llega al año en seis repasos donde SM-2 necesitaba siete, y la diferencia se
ensancha con el historial.

Lo que fallas vuelve **en diez minutos**, no cuando diga la fórmula: una tarjeta
recién fallada hay que volver a verla hoy.

Todo se ajusta en **Ajustes → Cómo se programan los repasos**. Y cuando lleves
400 repasos encadenados, **Calibrar con mi historial** reajusta los diecinueve
pesos del modelo a cómo memorizas tú. Tarda un rato, corre en segundo plano y no
puede empeorar lo que hay: si ningún ajuste mejora la predicción, deja los pesos
como estaban y te lo dice.

El popup prioriza lo **vencido**, mezcla ~25% de tarjetas **nuevas** (siempre las del
nivel más bajo que te falte), y si no hay nada pendiente ofrece un repaso de refuerzo —
así el atajo nunca queda vacío.

### Si vienes de una versión anterior

No hay que hacer nada ni se pierde nada. Al arrancar, cada tarjeta ya estudiada
pasa sola a FSRS: su intervalo se convierte en estabilidad (a la retención de
fábrica son lo mismo) y su factor de facilidad, en dificultad. **Sigue venciendo
el día que le tocaba.**

### Tarjetas que se te atragantan

Una tarjeta que fallas una y otra vez no se arregla estudiándola más veces: está
mal escrita, o pregunta dos cosas a la vez. Al llegar a **ocho fallos** se
aparta, deja de salir a estudiar y va a una lista aparte, con un botón para
editarla y otro para devolverla al ciclo con los fallos a cero. Bit te avisa de
vez en cuando si tienes alguna. El umbral se cambia en Ajustes, y con 0 se apaga.

### Deshacer

Si te equivocas de botón, **Z** en el popup quita el último repaso y deja la
tarjeta exactamente como estaba, incluidos los fallos acumulados y el apartado
por atragantarse. El aviso que sale al calificar también trae su botón. Para
rehacer el estado se reproducen los repasos que quedan **con sus fechas de
verdad**, así que una tarjeta con repasos espaciados meses no acaba con la
memoria de una repasada tres veces seguidas.

## Cuántas nuevas al día

Un mazo grande sin freno se come de golpe: metes doscientas tarjetas nuevas una
tarde y tres semanas después te vuelven todas juntas, el día que menos tiempo
tienes. Por eso hay un **tope diario de tarjetas nuevas** en
**Ajustes → Tarjetas nuevas al día**, quince por defecto y 0 para quitarlo.

Agotado el cupo, Bit deja de estrenar y sigue con lo vencido —el refuerzo
también respeta el tope, que si no las colaría por la puerta de atrás—. La
misma tarjeta repasada dos veces el mismo día gasta cupo una sola vez, porque lo
que cuenta es estrenarla. En Ajustes ves cuántas llevas hoy, cuánto queda de
cupo y a cuántos días está el mazo a ese ritmo: mil quinientas nuevas a quince
al día son cien días, que es un plan, no una montaña.

Cuando practicas un capítulo recién leído se pide material nuevo a propósito y
el tope no aplica: ahí lo que quieres es justo lo que acabas de leer.

## Pronunciación en las tarjetas de inglés

En una tarjeta de inglés, responder por el micrófono ya no solo dice si
acertaste: puntúa **cómo lo dijiste**, palabra por palabra. Verde va bien, ámbar
salió dudosa, roja no se entendió, con una nota sobre 100 y los botones para
**escuchar el modelo** y **repetir** hasta que salga.

La diferencia entre decirlo mal y decir otra cosa la da Vosk, que devuelve una
confianza por palabra; sobre eso se alinea lo que dijiste con lo que había que
decir. En español no se puntúa: ahí lo que se juzga es si sabes la respuesta, no
cómo suena.

## Examen oral con Bit

**🎓 Examen oral** en la tarjeta de acciones de Bit. Te hace cinco preguntas
habladas sobre lo que ya has estudiado, escucha tu respuesta, la califica de 0 a
100 y cierra con un acta: nota, cuántas aprobaste y qué toca repasar. Es lo más
parecido a que alguien te pregunte en el taller, y mide otra cosa que la tarjeta:
no si reconoces la respuesta, sino si sabes explicarla.

Tres decisiones que lo hacen útil y no un juguete:

- **Pregunta por el porqué**, no lee el frente de la tarjeta. La pregunta la
  redacta el modelo a partir de la tarjeta, para que tengas que razonar.
- **La tarjeta es la verdad**, no lo que el modelo crea saber: se corrige contra
  ella, así que la nota es de tu temario. Si dices lo que dice la referencia son
  80 o más aunque sea corto, y no se te exige desarrollo que la tarjeta no trae.
- **Decir «ni idea» es un cero**, y eso no se le pregunta al modelo. Un modelo
  pequeño califica con la manga muy ancha: le puso un 60 a un «ni idea» porque
  al leer la referencia se le pegaba lo que ahí decía. Esa comprobación se hace
  en código, y la escala del examinador está anclada con ejemplos de qué es un
  0, un 30 y un 80.

Solo entra lo que ya estudiaste alguna vez —examinarte de lo que no has abierto
no mide nada— y salen primero las que llevas más tiempo sin repasar. Sin IA
local activada no hay examen; si el modelo falla a mitad, el examen sigue
preguntando el frente de la tarjeta tal cual.

## Otras formas de estudiar, además de la tarjeta

La tarjeta es buena para reconocer y floja para lo demás. Estos cuatro modos
cubren lo que la tarjeta no llega a medir, y todos salen de la tarjeta de
acciones de Bit.

### Práctica intercalada

Estudiar un mazo entero del tirón se siente más fácil y se recuerda peor. Ahora,
cuando no estás repasando un mazo concreto, **la siguiente tarjeta sale de otro
tema** que la que acabas de responder: al saltar, el cerebro tiene que reconocer
de qué va la pregunta antes de contestarla, y ese esfuerzo es justo lo que
consolida. Si lo único que queda es del mismo mazo se sigue estudiando: se
prefiere intercalar, no se impone.

### 🗒️ Recuerdo libre

Eliges un tema, cierras los ojos y **cuentas todo lo que te venga** —hablando o
escribiendo—, y luego la IA lo contrasta con el material y te dice **qué te
dejaste**. Es el ejercicio con más respaldo de todos y el único que ninguna
tarjeta cubre: leer engaña, porque reconoces lo que ya viste y te parece que lo
sabes; aquí no hay nada delante.

Lo que importa del resultado no es la nota, es la lista de lo que faltó. La nota
tiene dos frenos, porque un modelo pequeño puntúa por impresión y se equivoca en
las dos direcciones: si lo que cuentas **ni siquiera usa el vocabulario del
material** no hay nota que valga (le puso un 65 a un recuerdo de mecánica sobre
material de estadística), y si el modelo sí hizo el recuento, la nota no puede
pasar de la proporción entre lo cubierto y lo que faltó.

### 👩‍🎓 Te lo explico

Le explicas un tema **tú a ella**, y Bit hace de alumna que no se entera: no
explica, pregunta. Pide el porqué, un ejemplo, que le aclares la palabra
técnica, y te dice qué no le cuadra si te saltas un paso. Explicar en voz alta
destapa los huecos que releer no destapa, porque releyendo reconoces y
explicando tienes que producir. Va sobre la conversación hablada, así que es
manos libres.

### 🔗 Conexiones

En vez de definiciones, **relaciones**: qué tiene que ver una cosa con otra, qué
pasa si falla una. Saber qué es un alternador y saber qué es una batería no es
saber por qué el motor se para cuando falla el alternador, y eso último es lo
que se usa en el taller.

Emparejar bien es la mitad del ejercicio: las parejas salen del mismo mazo y se
prefieren las que comparten etiquetas, nivel o el término técnico que las une.
Hace falta haber estudiado **al menos dos tarjetas del mismo tema**; con una
suelta por mazo te dirá que aún no hay de qué preguntar.

## 💡 ¿Sabías que…?

Bit suelta datos de cultura general y los va soltando sola de vez en cuando,
cuando no hay nada que repasar. Hay **158 datos en 20 categorías** en
`appstudy/sabias.py`, escritos a mano y elegidos por comprobables: historia,
ciencia, cuerpo humano, lengua, arte, geografía, tecnología, matemáticas,
economía, naturaleza, astronomía, filosofía, música, cine, deporte,
gastronomía, medicina, psicología, inventos y **«Lo que crees y no es»**.

Esa última categoría desmonta lo que todo el mundo repite y es falso: la Gran
Muralla no se ve desde el espacio, no usamos el 10 % del cerebro, el mapa de
sabores de la lengua nunca existió, los toros no ven el rojo, Einstein no
suspendía matemáticas. Quitar un error de la cabeza vale tanto como meter un
dato nuevo.

Ninguna categoría baja de cinco datos, y hay una prueba que lo comprueba: con
dos, pedir ese tema sería oír siempre lo mismo.

Cada dato viene con **el hecho y el porqué**, que es lo que lo hace contable en
una conversación en vez de quedarse en anécdota suelta.

Lo importante es el botón **📌 Guárdamela**: el dato pasa a un mazo de Cultura
general y entra en el repaso espaciado como cualquier otra tarjeta. Un dato que
solo se lee se olvida en una semana; lo que te vuelve más culto no es haberlo
leído, es acordarte de él tres meses después. Con la IA local activa, además, se
guarda como **pregunta** en vez de como enunciado —le pide al modelo que redacte
la pregunta cuya respuesta es el dato—, porque una tarjeta que se lee no fija
nada y una que hay que responder sí. También está **«Cuéntame más»**, que amplía
el dato con la IA local.

Se filtra por tema con el desplegable del globo, no repite dato hasta agotar la
vuelta y no guarda dos veces el mismo.

## Las lecturas

150 capítulos, **1.410 minutos** de material, ordenados por nivel dentro de cada mazo:

| Mazo | Capítulos |
|---|---|
| 🗣️ Inglés (20 · 208 min) | Gramática y escritura profesional; nuevas lecturas de acuerdos, aclaración, negociación y síntesis |
| 🐧 Linux (19 · 167 min) | Terminal, permisos, almacenamiento y servicios; nuevas lecturas de globbing y comillas, empaquetado, redirección, entorno, señales y rendimiento |
| 📊 Ciencia de Datos (53 · 531 min) | Análisis, modelos y producción; nuevas lecturas de granularidad, cardinalidad y datos disponibles a tiempo |
| 🤖 Inteligencia Artificial (16 · 150 min) | Modelos, RAG, agentes y seguridad; criterios de aceptación, extracción y evaluación pareada; nuevas lecturas de uso responsable, modelos de razonamiento, MCP, latencia de inferencia y mantenimiento |
| 🚜 Maquinaria (16 · 140 min) | Operación, hidráulica y mantenimiento; transmisiones powershift, GET, volquetes ADT/RDT, CAN J1939 y gestión de orugas |
| 🔧 Automotriz (11 · 99 min) | Sistemas y diagnóstico; nuevas lecturas de bitácora, consumo y pruebas que discriminan hipótesis |
| ⚡ Electricidad (6 · 43 min) | Magnitudes, componentes y alterna; nuevas lecturas de nodos y mallas, transitorios RC y ADC |
| 🧮 Matemáticas (9 · 72 min) | Cálculo mental y verificación; nuevas lecturas de fracciones, ecuaciones y probabilidad compuesta |
| 🐍 Python (5 · 52 min) | Computación científica y análisis con NumPy, Pandas, Matplotlib, Seaborn y guía de proyectos de certificación freeCodeCamp |

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
| `img` | imagen remota por URL con descarga asíncrona y caché local |

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

Desde la ventana principal (botón **+**) puedes crear cuatro tipos de tarjeta:

- **Tarjeta**: pregunta y respuesta, con pista opcional.
- **Reto**: opción múltiple con explicación del porqué.
- **Lección**: solo enseña algo, sin preguntar.
- **Huecos**: un texto del que se tapa un trozo y lo dices de memoria.

### Huecos y doble sentido

En una tarjeta de **huecos** marcas entre dobles llaves lo que quieres tapar:

```json
{"kind": "cloze",
 "front": "En <tt>chmod 755</tt> el {{7}} es del dueño y el {{5::en octal}} del grupo."}
```

Cada vez que aparece se tapa **un hueco distinto**, así que una sola tarjeta da
tantas preguntas como trozos hayas marcado, y siempre en su contexto. Lo que va
detrás de `::` es una pista, que se enseña junto al hueco. La respuesta es el
texto entero con lo que faltaba en negrita. La mascota también las usa: cuando le
toca «Rellena el hueco» tapa lo que tú marcaste, en vez de adivinar la palabra.

Una tarjeta normal con **`"reverse": true`** genera además su cara inversa, que
pregunta al revés — de «¿qué comando muestra el directorio?» sale también «pwd
→ ¿qué es?». Son dos tarjetas independientes, cada una con su progreso, y la
inversa se etiqueta como `inversa` para que la encuentres:

```json
{"front": "¿Qué comando muestra en qué directorio estás?", "back": "pwd",
 "reverse": true, "reverse_hint": "Tres letras, de «print working directory»."}
```

Cada una se guarda en un mazo y un **nivel**, y en el explorador puedes filtrar por
ambos. El explorador no pinta la colección entera: pide a la base de datos grupos
de 60 tarjetas y el pie de la lista dice por dónde vas («Viendo 60 de 1.019») con
un botón **Ver 60 más** que añade el grupo siguiente sin rehacer lo ya pintado.
Al cambiar la búsqueda, el mazo o el nivel se vuelve al primer grupo.

El botón **Abrir** del explorador importa tarjetas desde CSV, TSV, exportaciones
de texto de Anki y paquetes `.apkg`. Antes de guardar enseña una muestra y deja
elegir el mazo; los duplicados actualizan el contenido sin borrar su historial.
La lectura ocurre fuera del hilo gráfico, la muestra se limita a 40 filas y las
tarjetas se guardan en lotes de 100 para que una colección grande no congele la
ventana. Se aceptan como máximo 5.000 tarjetas y 200 MB por importación.

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
AppStudy**: un lector de PDF y otro de EPUB, los dos recuerdan por dónde ibas.
Los libros no se copian ni se tocan: se leen donde están, y en la base solo
queda su ruta, la página y los minutos leídos.

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
| S | rotulador: arrastra sobre el texto para subrayar |

- **Zoom de verdad**: la hoja pide su tamaño y el lector la deja desplazarse. Se
  recuerda por libro cómo lo estabas leyendo (ajuste y escala).
- **Buscar en todo el libro**: saca el texto entero una vez y enseña en qué
  página está cada aparición, con su frase; pulsas y saltas allí.
- **Marcadores** por página, con su lista en el menú ⋯.
- **Modo noche**: invierte la página *en la GPU* (mezcla por diferencia), sin
  reprocesar la imagen ni gastar memoria.
- **Copiar el texto de la página** y **✦ Tarjetas** de las páginas que tienes
  delante, desde el mismo menú. Las generadas recuerdan este libro y el tramo de
  páginas para poder volver después.

**Subrayar y anotar**

Pulsa **S** (o el rotulador de la barra) y arrastra sobre el texto. Lo subrayado
se queda: al soltar, AppStudy le pregunta a poppler **qué texto hay justo debajo
de ese rectángulo**, así que el subrayado no es una mancha de color sino una
cita que se puede leer, buscar y copiar.

- Los rectángulos se guardan **de 0 a 1**, relativos a la página. Por eso siguen
  en su sitio con cualquier zoom, en cualquier pantalla y aunque cambies el
  ajuste de ancho a página.
- Al tocar un subrayado se abre su ficha: la cita, un hueco para **tu nota**,
  cuatro colores, y **✦ Hacer tarjeta**, que abre el editor con la cita ya en la
  respuesta y la página del libro en la pista. La pregunta la escribes tú, que es
  lo que obliga a entender lo leído en vez de copiarlo.
- Los que llevan nota se marcan con una pestañita azul al margen.
- El botón de la lista enseña **todo lo subrayado del libro**, salta a su página
  y lo copia entero **en Markdown** con un clic.
- Lo subrayado también sale en la búsqueda global (Ctrl+K), y desde ahí se abre
  el libro en esa misma página.

**Los EPUB**

Un EPUB es HTML comprimido, así que lo lee un navegador: **WebKitGTK**, que en
Ubuntu y Mint ya viene instalado (`sudo apt install gir1.2-webkit-6.0` si
faltara). Sin él, el resto de la biblioteca funciona igual y solo se avisa al
abrir uno.

El libro se descomprime una vez en la caché para que las imágenes y las hojas de
estilo resuelvan sus rutas solas; después, cada capítulo abre al instante. El
orden lo manda el *spine* del libro y los títulos salen de su índice.

| Tecla | |
|---|---|
| ← → · AvPág/RePág | capítulo anterior o siguiente |
| Inicio / Fin | primero y último |
| + / − | letra más grande o más pequeña |
| M | marcador en este capítulo |
| N | modo noche |

El índice completo está en el botón de la cabecera, el modo noche se aplica **sin
recargar** (no parpadea ni pierdes por dónde ibas) y **✦ Tarjetas** saca tarjetas
del capítulo que tienes delante y conserva ese capítulo como fuente. Los enlaces
internos del libro se siguen dentro; los que apuntan fuera se abren en tu navegador.

**El progreso se guarda solo**, en cada cambio de página: cierras el libro,
vuelves mañana y sigues en la 77. Al salir también se anotan los minutos leídos.

Las páginas se dibujan con `pdftocairo` (poppler, ya lo tienes) en un hilo
aparte, y se guardan en `~/.local/share/appstudy/paginas`: dibujar una tarda
~150 ms, volver a ella es instantáneo, y mientras lees una ya se está dibujando
la siguiente. La caché se puede borrar cuando quieras — se rehace sola.

## Voz: leer en voz alta y responder hablando

Bit lee las tarjetas, las citas y sus propias respuestas, y tú puedes contestar
por el micrófono. Todo pasa dentro del equipo: no hay servicio de nube ni clave
que guardar.

**`./install.sh` deja esto montado solo** — se puede repetir sin miedo, salta lo
que ya esté:

| Qué | Dónde queda | Tamaño |
|---|---|---|
| **Kokoro**, el motor de voz principal | `~/.local/share/appstudy/kokoro` (modelo) y `tts-venv` (entorno) | ~490 MB |
| **Piper**, el motor de reserva, con sus voces | `~/.local/share/appstudy/piper` | ~215 MB |
| **Vosk**, para responder hablando | `~/.local/share/appstudy/vosk` | ~126 MB |

Es cerca de **1 GB** en total y se descarga una sola vez; borrar cualquiera de
esas carpetas no rompe nada, solo baja un escalón de calidad.

Lo único que tienes que poner tú a mano, porque toca el sistema:

```bash
sudo apt install sox                    # control de tono de la voz
pip install --user vosk                 # transcribir lo que dices al micrófono
```

`sox` es lo único que pide root, y solo afecta al ajuste de tono: sin él la voz
suena igual de bien, simplemente el control se queda quieto. `vosk` va en el
Python del sistema (en Ubuntu reciente puede pedir `--break-system-packages`, o
un `pipx`); si prefieres, `whisper-cli` también sirve. Sin ninguno de los dos,
responder hablando queda desactivado y el resto funciona.

Reproducir el sonido lo hace `pw-play`, `paplay` o `aplay`, y con tener uno basta
— en Ubuntu/Mint con PipeWire o PulseAudio ya está. Para descargar los modelos
hace falta `curl` o `wget`.

### Conversar con Bit en voz alta

En cualquier globo con la IA activa hay un botón **🎙️ Hablar con Bit**, y dentro
del chat también. A partir de ahí es una conversación normal: hablas, Bit se da
cuenta de que has terminado, contesta en voz alta y se vuelve a poner a escuchar
sola. No hay que pulsar nada entre turno y turno.

**O no pulsas nada: le dices «hola bit».** Mientras Bit está suelta por el
escritorio deja el oído puesto esperando esa frase, y al oírla abre la charla
hablada ella sola. Se apaga desde **Ajustes → Voz → Responder a «Hola Bit»**.

Estar siempre escuchando cuesta **un 2% de un núcleo**, medido, porque el oído en
reposo no transcribe nada: el reconocedor trabaja con una lista cerrada de frases
—los saludos posibles y un puñado de señuelos— y todo lo que no encaje sale como
desconocido y se tira. Los señuelos son la parte que importa: con una lista
cerrada el motor mete a la fuerza lo que oye en la frase más parecida, así que sin
un «buenos días» o un «qué tal» donde caer, cualquier saludo acabaría siendo un
«hola bit». También se dan por buenas las confusiones típicas —vosk oye «vit» o
«bip» donde dices «bit»— y se exige el orden correcto, para que hablar *sobre* un
bit no la despierte. Nada de esto sale del equipo, y solo se mira cuando el
reconocedor cierra una frase, nunca a media palabra.

El globo te dice en qué punto está —«Te escucho…», «Déjame pensar…», «Bit está
hablando…»— y se corta diciendo **adiós**, **hasta luego** o **ya está**, o con
el botón de dejar de hablar. La despedida se compara con la frase entera, así que
preguntarle *«¿cómo se dice adiós en inglés?»* no te cierra la charla.

Tres detalles que hacen que se sienta como hablar con alguien:

- **Sabe cuándo has terminado** midiendo la energía del micrófono, no por tiempo
  fijo. El umbral se calcula sobre el ruido de fondo de tu habitación —el suelo
  de ruido es el mínimo de los últimos diez segundos—, así que un ventilador al
  lado sube el listón en vez de tomarse por voz. Un carraspeo suelto no cierra
  turno, y un turno no puede eternizarse: a los treinta segundos contesta con lo
  que haya oído.
- **No se escucha a sí misma.** Mientras Bit habla, el micrófono se ignora y lo
  que entró se tira; si no, se transcribiría su propia voz saliendo por los
  altavoces y se contestaría sola.
- **Responde como quien conversa, no como quien da clase.** En modo hablado se le
  pide otra cosa al modelo: una o dos frases, sin listas ni negritas —que en voz
  alta no significan nada—, y devolviendo la pelota. Además la respuesta se corta
  por la última frase entera si se pasa de cincuenta y cinco palabras: un modelo
  pequeño se emociona explicando, y medio minuto de monólogo no hay quien lo siga.
  Si quieres más, se lo pides.

Las órdenes de siempre siguen funcionando habladas: «abre Platzi», «crea una
tarjeta de…». Cuando es una orden y no una pregunta, Bit la ejecuta y vuelve a
escucharte sin esperar respuesta del modelo.

Hace falta la IA local activada (ver [Preguntarle a Bit](#preguntarle-a-bit-ia-local))
y el reconocimiento de voz instalado; sin ellos el botón te lo dice.

### Por qué Kokoro va en su propio entorno

Kokoro suena claramente más humano que Piper, pero necesita `onnxruntime`, que
tarda meses en publicar ruedas para cada Python nuevo. Si el Python del sistema
va por delante (Python 3.14, por ejemplo), no hay forma de instalarlo ahí. Por
eso el instalador crea con [uv](https://github.com/astral-sh/uv) un entorno
aparte con Python 3.12 en `~/.local/share/appstudy/tts-venv`, y la app —que
sigue corriendo con el Python del sistema— habla con él como un proceso más:
`appstudy/tts_kokoro.py` recibe el texto y devuelve audio.

Ese proceso **se queda vivo entre tarjetas**: cargar el modelo cuesta medio
segundo y pagarlo en cada tarjeta se nota. Con el motor caliente la voz arranca
en ~0,15 s, y el texto se trocea en frases para que empiece a sonar sin esperar a
tenerlo todo sintetizado.

Si algo de esto falla —no hay `uv`, no se pudo bajar el modelo, la máquina es
vieja— **no se rompe nada**: la voz cae sola en Piper, y si tampoco estuviera, en
`spd-say` del sistema. El instalador te lo dice al terminar, y en Ajustes ves qué
motor y qué voces están activos.

### La cara de Bit sigue a su voz

Bit se dibuja acorde a la voz con la que habla **en cada frase**, no al idioma
que tengas configurado: como una tarjeta de inglés la lee la voz inglesa, que es
de mujer, al leerla le salen pestañas, la ceja más fina y arqueada y los cachetes
un punto más presentes; en cuanto vuelve al español y a su voz masculina, vuelve
la cara de siempre. No hay ajuste que tocar y no hay que reiniciar nada: cambia
sola al hablar, y al callarse se queda con la cara de su voz habitual.

De dónde sale el dato: las voces de Kokoro lo llevan en el nombre (`af_heart` es
americana femenina, `em_santa` español masculino, `ef_dora` española femenina),
y las de Piper, que no siguen ninguna convención, están en la tabla
`GENERO_PIPER` de `appstudy/voz.py`. Una voz que no esté en ninguna de las dos
deja la cara neutra en vez de inventarse nada.

### Cambiar de voz

En español se usa `em_santa` y en inglés `af_heart`, elegidas de oído. Se cambian
en el diccionario `KOKORO_VOZ` de `appstudy/voz.py`; las disponibles se listan
así:

```bash
~/.local/share/appstudy/tts-venv/bin/python -c \
  "from kokoro_onnx import Kokoro; import os; d=os.path.expanduser('~/.local/share/appstudy/kokoro'); \
   print(Kokoro(f'{d}/kokoro-v1.0.onnx', f'{d}/voices-v1.0.bin').get_voices())"
```

Las voces de Piper son archivos `.onnx` sueltos en `~/.local/share/appstudy/piper`:
basta con dejar otra ahí para que se use, siguiendo el orden de `VOCES_PREFERIDAS`.
Ese orden es de escucha, no de tamaño — la `es_ES-sharvard-medium` suena mejor que
alguna «high», así que va primero.

La velocidad, el volumen y el tono se ajustan desde **Ajustes → Voz y lectura en
voz alta**, y valen para los dos motores.

## Preguntarle a Bit (IA local)

Bit puede conectarse a un **modelo de lenguaje que corre en tu propia máquina**.
Ni tus tarjetas ni tus preguntas salen del equipo, no hay clave de API que
guardar y no cuesta nada por pregunta.

Hacen falta dos cosas: **el servidor** (Ollama, que habla por
`http://localhost:11434`) y **los pesos del modelo**.

### Instalar Ollama

Si tienes root, el instalador oficial deja el servidor y su servicio de sistema
en un paso:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Si no lo tienes —o prefieres no meter nada fuera de tu carpeta—, el tarball hace
lo mismo sin tocar el sistema:

```bash
mkdir -p ~/.local/ollama ~/.local/bin
curl -fsSL https://ollama.com/download/ollama-linux-amd64.tar.zst \
  | tar --zstd -x -C ~/.local/ollama
ln -sf ~/.local/ollama/bin/ollama ~/.local/bin/ollama
```

Así no hay servicio que lo levante, así que se lo escribes tú en
`~/.config/systemd/user/ollama.service`:

```ini
[Unit]
Description=Ollama (servidor de modelos local, modo usuario)
After=network-online.target

[Service]
Type=simple
ExecStart=%h/.local/ollama/bin/ollama serve
Environment="OLLAMA_HOST=127.0.0.1:11434"
Environment="OLLAMA_KEEP_ALIVE=5m"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="LD_LIBRARY_PATH=%h/.local/ollama/lib/ollama"
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now ollama
```

Las dos variables del medio importan si vas justo de gráfica: `KEEP_ALIVE`
devuelve la VRAM a los cinco minutos sin preguntar nada, y `MAX_LOADED_MODELS=1`
impide que se cargue un segundo modelo encima del primero. AppStudy ya pide
`keep_alive` corto por su cuenta (ver `ia.py`); esto es el cinturón de seguridad
para cuando hables con Ollama por fuera.

### Descargar el modelo

```bash
ollama pull gemma3:4b
```

Después, en **Ajustes → Inteligencia artificial**: activa el interruptor y pulsa
**Probar conexión**. Si el modelo que pusiste no está descargado, AppStudy usa el
gemma que encuentre y te lo dice.

### Dónde se usa

| Dónde | Qué hace |
|---|---|
| Menú de Bit → **Pregúntame algo** | una pregunta suelta; si venías de una tarjeta, la usa como contexto |
| En una tarjeta → **🧠 Explícamelo mejor** | te la explica con otras palabras y un ejemplo |
| En una tarjeta → **💬 Modo chatbot** | abre una conversación nueva y sigue el hilo |
| Tarjetas → botón ✦ | genera tarjetas sobre un tema, **tú marcas cuáles se guardan** |
| Capítulo/PDF/EPUB → **✦ Tarjetas** | genera solo desde ese texto, deja revisarlas y conserva la fuente exacta |

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

### Con qué modelo

Lo que manda es la **VRAM libre**, no la RAM ni el procesador: un modelo que cabe
entero en la gráfica va a otra velocidad que uno que se desborda, porque las capas
que no entran las calcula la CPU y ahí se pierde casi todo lo ganado. Y cuenta la
VRAM *libre*, no la total: el escritorio y el navegador ya se llevan lo suyo.

| VRAM libre | Modelo | Cómo va |
|---|---|---|
| 4 GB | `gemma3:4b` | justo, pero entra |
| 6–8 GB | `gemma3:4b` | ocupa 3,5 GB y sobra sitio para el escritorio |
| 12 GB o más | `gemma3:12b` | mejor redacción y mejores tarjetas generadas |

Medido en una RTX 5060 Ti (7,5 GiB, 6,3 libres): `gemma3:4b` carga sus **35 capas
de 35 en la GPU** y responde a **123 tokens por segundo**, que en el globo de Bit
se lee como texto escribiéndose sin pausas. El mismo `gemma3:12b` pesa 8,1 GB y
ahí ya no cabe: funciona tirando de RAM, pero responde bastante más despacio.

Para comprobar dónde acabó el modelo:

```bash
ollama ps                                             # qué hay cargado, y si en GPU o CPU
journalctl --user -u ollama -n 200 | grep offloaded   # cuántas capas subieron
```

(sin el `--user` si instalaste Ollama como root, que entonces es servicio del sistema)

La línea que interesa es `offloaded 35/35 layers to GPU`: si los dos números
coinciden, entró entero. Si el primero es menor, el resto lo está calculando la
CPU y toca bajar de tamaño.

El nombre del modelo no tiene por qué ser un gemma: en Ajustes puedes escribir
cualquiera que tengas descargado. La familia gemma solo es la preferida cuando el
que pediste no está y AppStudy tiene que elegir por ti (`elegir_modelo()`).

### Tomar cursos de freeCodeCamp dentro de AppStudy

En el **Panel**, desplegando «Otras formas de estudiar», la fila **🔥 Cursos de freeCodeCamp**
abre el catálogo completo del currículo de [freeCodeCamp.org](https://www.freecodecamp.org/)
sin salir de la aplicación. Son tres pasos: **curso → módulo → lección**.

- **El catálogo.** Dieciocho certificaciones y cursos (desarrollo web, JavaScript,
  Python, análisis de datos, machine learning, bases de datos, back end, seguridad,
  álgebra, inglés para programadores…). Cada uno muestra cuántas lecciones llevas
  hechas de cuántas hay. El currículo entero se descarga **una sola vez** (unos 8 MB)
  y queda en caché en `~/.local/share/appstudy/fcc/`; a partir de ahí el catálogo abre
  al instante. El botón ↻ de la cabecera lo vuelve a descargar cuando quieras.
- **Hacer la lección.** Al pulsarla se abre en el reproductor web integrado, con su
  editor de código y sus pruebas, tal cual en freeCodeCamp: la haces ahí. Cuando
  freeCodeCamp da el reto por superado, AppStudy **la marca sola** como completada; el
  botón ✓ de la barra superior la marca a mano si prefieres. En el catálogo, «▶ Empezar
  el módulo» salta directamente a la primera lección que te falta, y arriba del todo
  tienes **«Seguir donde lo dejaste»**.
- **Convertirla en estudio.** Cada lección lleva dos botones más: 📄 la guarda como
  capítulo propio para leerla en **Leer** (también sin conexión), y ☰ le pide a la IA
  local que saque tarjetas de repaso de ella, con la previsualización de siempre para
  elegir cuáles guardar. El mazo destino se propone según el curso (Python, Datos, IA,
  Linux, Inglés, Matemáticas).

Tu avance vive en la base de AppStudy (tabla `fcc_progress`), no en tu cuenta de
freeCodeCamp: para que la web guarde tu progreso oficial, inicia sesión dentro del
reproductor como en cualquier navegador (la sesión y las cookies se conservan).

### Generar tarjetas desde una URL suelta de freeCodeCamp

Además del catálogo, cualquier página de freeCodeCamp —lecciones, artículos o
tutoriales— se puede convertir en tarjetas con la IA local:

- **Desde la interfaz gráfica:** en la pestaña **Tarjetas**, junto al botón de IA y el de importar, pulsa el botón del globo terráqueo 🌐 (*Generar tarjetas desde freeCodeCamp con IA*). Puedes elegir directamente una certificación de la lista o pegar cualquier URL de freeCodeCamp (`https://www.freecodecamp.org/learn/...`). La IA procesará la lección y te presentará una previsualización interactiva con casillas para elegir qué tarjetas guardar en tu mazo.
- **Por terminal:**
  ```bash
  # Ver certificaciones soportadas
  appstudy --fcc-certs

  # Descargar lección y generar tarjetas con IA automáticamente
  appstudy --fcc "https://www.freecodecamp.org/learn/scientific-computing-with-python/learn-string-manipulation-by-building-a-cipher/step-1"
  ```

## Empezar de cero

En Ajustes → **Apariencia y progreso** hay dos botones que piden confirmación:

- **Borrar lo estudiado hoy** — quita los repasos de las últimas 24 h (lo que cuenta
  como «hoy») y deja cada tarjeta como estaba antes: el estado no se puede restar, así
  que se rehace desde cero con los repasos anteriores de esa tarjeta, en orden. La
  racha se recalcula sola.
- **Reiniciar la racha** — vuelve a cero sin tocar ninguna tarjeta: a partir de ese
  momento solo cuentan los repasos nuevos (`racha_desde` en la tabla `meta`).

## Escribir tus propios capítulos

Los 134 capítulos de fábrica vienen en JSON porque es lo que come la base, pero
escribir JSON a mano es un castigo. Los tuyos se escriben en **Markdown**.

Desde la pestaña **Leer**, «Escribir un capítulo». O directamente, dejando un
`.md` en `~/.local/share/appstudy/lecturas/` y pulsando **Ctrl+R**.

````markdown
---
mazo: linux
nivel: 2
etiquetas: permisos, procesos
---

# Lo que aprendí de los permisos

Un párrafo con **negrita**, *cursiva* y `código`.

## Los tres tríos

- dueño
- grupo
- resto

```bash
chmod 755 script.sh
```

> [!CLAVE] El primer dígito es siempre el dueño.
````

La cabecera entre tres guiones dice de qué **mazo** es y en qué **nivel** va; el
primer `#` es el título. Si no pones `minutos`, se estiman contando las palabras.
Los recuadros destacados son `> [!NOTA]`, `> [!AVISO]` y `> [!CLAVE]`; una
fórmula suelta va entre `$$…$$`.

El archivo es la fuente y la base solo una copia: editar el `.md` y recargar
basta. Tus capítulos se marcan como **«escrito por ti»**, aparecen junto a los de
fábrica en su mazo y su nivel, y **recargar el contenido incluido no se los
lleva** — solo desaparecen si borras el archivo o pulsas Borrar en el editor. Un
capítulo tuyo puede llamarse igual que uno de fábrica sin pisarlo.

## Buscar en todo · Ctrl+K

Una caja que busca a la vez en **tus tarjetas, los capítulos, tus libros y lo que
hayas subrayado**. La gracia no es buscar en cada sitio, que ya se podía, sino no
tener que acordarse de dónde estaba: escribes «systemd» y salen la tarjeta, el
capítulo que lo explica, el libro que tienes a medias y el párrafo que marcaste.

- Se exigen **todos los conceptos**, y no distingue acentos ni mayúsculas:
  «ingles» encuentra «inglés», «eliminación» entiende «eliminar» y «administrar
  demonios» puede encontrar «controla los servicios».
- Lo que aparece en el título pesa más que lo que aparece en el cuerpo, y el
  nombre del mazo cuenta también, así que «inglés» saca ese mazo entero. Una
  coincidencia literal siempre pesa más que una relacionada, que se marca como
  **Relacionado** para que sepas por qué apareció.
- Enter abre el primer resultado; pulsando uno se va a donde esté: la tarjeta se
  abre en su editor, el capítulo en el lector, el libro por donde ibas y un
  subrayado **en su página exacta**.
- Con la caja vacía ofrece por dónde ibas: lo último que estudiaste y lo último
  que leíste.

La parte semántica es local y ligera: familias de conceptos en español e inglés,
raíces para sus flexiones y una caché acotada de 8.192 normalizaciones. No carga
Ollama, no crea embeddings y no deja crecer la memoria sin límite.

## La pestaña Progreso

Todo lo que has hecho vive en la base desde el primer día, pero hasta ahora solo
se veían cuatro números. La pestaña **Progreso** lo convierte en cinco gráficas,
dibujadas con Cairo —lo mismo que la mascota— sin ninguna biblioteca de por
medio, y que siguen el tema claro u oscuro.

Arriba, cuatro cifras. La primera es **memoria construida**: la suma de lo que
aguantaría cada tarjeta si dejaras de estudiar hoy. Es el mejor resumen del
trabajo hecho porque no cuenta repasos, cuenta memoria. La segunda es la
probabilidad media de que ahora mismo te acuerdes de lo estudiado, calculada
tarjeta a tarjeta con el modelo.

| Gráfica | Qué enseña |
|---|---|
| **Tu año** | Un cuadro de casillas, una por día, como el de las contribuciones: cuánto estudiaste cada día del último año, con hoy enmarcado |
| **En qué punto están tus tarjetas** | Una barra apilada: sin estrenar, aprendiendo, jóvenes, maduras y atragantadas |
| **Cuánto aciertas en cada mazo** | Una barra por mazo, con tu retención objetivo marcada con una línea de puntos, para ver de un vistazo cuál se te resiste |
| **Lo que viene** | Las tarjetas que vencen cada día de los próximos 30, con lo ya atrasado en rojo. Subir la retención sube estas barras; bajarla las aplana |
| **Cuánto tardas en contestar** | La mediana por nivel. La mediana y no la media: basta con dejar el popup abierto una vez para que una media deje de significar nada |

Un detalle que cambia lo que dice el número: en la retención **solo cuentan los
repasos de tarjetas que ya habías visto antes**. La primera vez que ves una
tarjeta no había nada que recordar, así que meterla en la media solo la ensucia.

Debajo de la retención aparece **Qué conviene reforzar**: reúne los fallos y las
respuestas difíciles de los últimos 90 días por etiqueta —o por mazo cuando una
tarjeta no tiene etiquetas— y permite practicar ese foco con un clic. Para que
el panel siga abriendo al instante incluso después de años de uso, solo recorre
los 5.000 repasos más recientes mediante el índice temporal de SQLite.

## Logros

Once marcas que se pasan sin darse cuenta. No hay puntos, ni niveles, ni una
pantalla que te felicite cada dos por tres: la racha de siete, treinta y cien
días, mil repasos, cincuenta en un día, un mazo dominado, un capítulo del nivel
más alto, un mazo leído entero, un año de memoria sumada, cien repasos sin
ninguna tarjeta atragantada.

Se comprueban al calificar, que es cuando cambian la racha y los intervalos.
Bit lo celebra **una vez**, con el salto y los corazones que ya sabe hacer; si
estabas en el popup, sale un aviso con un botón para ir a verlos. Después se
quedan al final de la pestaña Progreso, con los que faltan y qué hay que hacer
para conseguirlos.

Están en `appstudy/logros.py`: cada uno es una regla contra la base, así que
añadir el tuyo es escribir una función. Nada se guarda hasta que se consigue,
por lo que se pueden añadir logros nuevos sin migrar nada.

## Objetivo diario

En **Ajustes → Objetivo diario** pones cuántas tarjetas quieres hacer al día. Una
meta pequeña y cumplible rinde más que una grande que abandonas; con 0 no hay
objetivo y todo sigue como antes.

Cuando lo pones, aparece en tres sitios:

- En el **panel**, una barra con lo que llevas y lo que falta, que se pone verde
  al cumplirlo.
- En la **barra superior de GNOME**, la misma barra y debajo **siete barritas**,
  una por día de la semana, en verde los días que cumpliste.
- En **Ajustes**, cuántos de los últimos siete días cumpliste, en un vistazo.

## Cuenta en la nube

Tu progreso vive en **Supabase** y te sigue a cualquier equipo donde entres. Se
entra **una sola vez por equipo**: la sesión queda guardada y se renueva sola al
abrir, así que no vuelves a escribir la contraseña.

### Ponerlo en marcha

1. Abre [`supabase/esquema.sql`](supabase/esquema.sql), **copia su contenido**
   (no la ruta del archivo) y pégalo en el panel de Supabase, en **SQL Editor →
   New query → Run**. Crea la tabla `sync_snapshots`, su política RLS y su
   trigger. Se puede repetir cuantas veces quieras: solo crea lo que falte.
2. En **Project Settings → API Keys**, copia la clave **pública** —la que
   empieza por `sb_publishable_`, o la JWT etiquetada `anon / public` si tu
   proyecto usa las claves antiguas— y ponla en el `.env` de la raíz:

   ```ini
   db_database='postgresql://postgres:…@db.<referencia>.supabase.co:5432/postgres'
   SUPABASE_ANON_KEY='eyJhbGciOi…'
   ```

   **No uses la clave secreta** (`sb_secret_…`, antes `service_role`): se salta
   las políticas RLS, así que con ella cualquiera que tenga el archivo vería los
   datos de todos los usuarios. Están juntas en el panel y confundirlas es fácil,
   por eso AppStudy la reconoce, se niega a mandar una sola petición con ella y
   te lo dice en Ajustes.

   La URL del proyecto se deduce sola del URI de arriba; si prefieres darla
   aparte, `SUPABASE_URL` manda sobre lo deducido. El `.env` no entra en el
   repositorio, y también se busca en `~/.config/appstudy/.env` para una copia
   instalada.
3. En **Ajustes → Cuenta en la nube**, escribe tu correo y contraseña y pulsa
   **Crear cuenta** la primera vez, **Entrar** las siguientes.

Mientras falte algo, esa sección dice exactamente qué variable poner y dónde.

### Cada usuario, sus datos

La separación la impone Postgres, no la aplicación: las políticas RLS de
`sync_snapshots` atan cada fila a `auth.uid()`, así que dos personas pueden
compartir el mismo proyecto de Supabase sin verse nada. En local pasa lo mismo,
cada cuenta tiene su propio archivo:

```
~/.local/share/appstudy/appstudy.db                    sin cuenta
~/.local/share/appstudy/cuentas/<uuid>/appstudy.db     con cuenta
```

Al entrar por primera vez en un equipo que ya usabas sin cuenta, tus meses de
repasos pasan a ser los de esa cuenta y suben a la nube: no te encuentras una
base vacía. Solo hereda la **primera** cuenta del equipo; quien se siente
después arranca limpio. Cambiar de cuenta cierra y vuelve a abrir la ventana,
porque las ventanas guardan la conexión con la que nacieron.

**Salir** solo cierra la sesión: el progreso de esa cuenta se queda en el
equipo, y al volver a entrar sigue ahí.

### Qué sube y cuándo

Sube lo mismo que la carpeta compartida —mazos, tarjetas y capítulos propios,
estado FSRS, historial de repasos, avance de lectura y el origen de cada
tarjeta— porque es el mismo snapshot y la misma fusión. Cada equipo guarda **una**
fila con su snapshot; nadie escribe la del otro.

Con **Sincronizar sola al abrir y al cerrar** puesto (de fábrica lo está), se
fusiona al arrancar y se sube al cerrar, para que no tengas que acordarte antes
de cambiar de equipo. Al cerrar solo sube —una petición, sin bajar nada— para no
retrasar la salida. Si no hay red no pasa nada: se estudia igual y se sube en el
próximo arranque. El botón **Sincronizar** hace la fusión completa cuando tú
quieras.

Todo esto habla por HTTPS con `urllib` de la biblioteca estándar: **no añade
dependencias** ni hace falta un driver de Postgres. La conexión directa a
Postgres del `.env` no se usa —ese host solo resuelve por IPv6 y esa contraseña
es la del superusuario, que se salta RLS—, y la clave `anon` es pública por
diseño: sin haber entrado no da acceso a nada.

Los snapshots viajan por TLS pero se guardan en claro en tu propio proyecto, y
hay un límite de 8 MB por equipo; una biblioteca más grande que eso va por la
carpeta compartida, que no tiene ese tope.

## Sincronización entre equipos

La alternativa a la cuenta en la nube, sin registrarte en ningún sitio y sin que
tus tarjetas salgan de tus discos. Las dos usan la misma fusión y pueden
convivir.

En **Ajustes → Sincronización entre equipos** eliges una carpeta compartida por
Nextcloud, Syncthing, Dropbox o una memoria y pulsas **Sincronizar**. AppStudy
fusiona los repasos y su estado FSRS, las tarjetas propias, los capítulos que
escribiste y su avance de lectura. La operación corre fuera del hilo de la
interfaz y solo cuando la pides: no hay un servicio residente consultando la red.

Cada instalación escribe un archivo distinto y publica primero a un temporal,
por lo que dos equipos no pisan el mismo archivo ni dejan una copia a medias.
Los repasos se unen como eventos y se deduplican; para una edición concurrente
gana la más reciente. Los borrados conservan una pequeña lápida, así que un
equipo atrasado no vuelve a crear lo que ya eliminaste. Un archivo corrupto o de
más de 50 MB se ignora sin tocar el progreso local.

Los PDF/EPUB, sus subrayados y las preferencias del escritorio no se sincronizan:
sus rutas pertenecen a cada equipo. Los archivos de sincronización son JSON
legible, no cifrado; usa una carpeta privada si tus tarjetas contienen datos
sensibles.

## Respaldo

Todo tu progreso —tarjetas, repasos, racha, libros y por dónde ibas— vive en un
solo archivo SQLite: `~/.local/share/appstudy/appstudy.db`, o el de tu cuenta si
entraste con una (ver «Cuenta en la nube»). **Ajustes → Contenido** enseña la
ruta exacta de la que estás usando.

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

474 pruebas sobre lo que no lleva interfaz: el modelo de memoria FSRS y su
calibración, el planificador, las sanguijuelas, el deshacer, el objetivo diario,
las tarjetas de huecos, las series de la pestaña Progreso, los logros, los seis
formatos de reto, las fórmulas en LaTeX, los subrayados, la lectura de EPUB, el
Markdown de tus capítulos, la búsqueda global, los recordatorios, la
sincronización, el respaldo, la guía de uso y la validez del contenido
incluido. No hace falta
instalar nada más — son
`unittest` de la biblioteca estándar — y ninguna toca tu progreso real: cada
caso arranca con una base vacía en un directorio temporal. Los detalles, en
`tests/README.md`.

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


### Recomendación diaria y sincronización portable

El panel propone repasos pendientes, una lectura y hasta tres ejercicios con accesos
directos. Prioriza el tema elegido, las lecturas empezadas y recientes y las dificultades
registradas en tarjetas del mismo nivel y etiquetas. Excluye los mazos desactivados.

La sincronización por carpeta y por nube incluye libros, progreso, marcadores y
subrayados. Los libros se reconocen por SHA-256 del archivo: copia el mismo archivo
al otro equipo y ábrelo desde la biblioteca para vincularlo. Los archivos de los libros
no se transfieren. Si el archivo original no estaba disponible al asignar la identidad,
la ficha conserva una identidad provisional; no se puede reconocer automáticamente
una copia por contenido hasta disponer del original.

La cabecera muestra el estado de cada destino: **Pendiente**, **Sincronizado** o
**Error**, con el detalle al pasar el cursor y acceso a Ajustes. «Sincronizado» confirma
el último intercambio con ese destino; los demás equipos necesitan sincronizar también.
Los errores automáticos quedan guardados, incluidos los del cierre, y los archivos
ilegibles impiden mostrar una sincronización completa. Las ediciones simultáneas de
un libro o subrayado se resuelven por la fecha más reciente, igual que el contenido propio.
El formato 2 admite importaciones del formato 1; actualiza ambos equipos para
intercambiar el nuevo formato.
