"""La guía de uso que se abre con F1, dentro de la propia aplicación.

Solo contenido y búsqueda, sin GTK: se puede probar sin abrir una ventana.
Quien la enseña es la ventana principal.

Cada tema se escribe con **los mismos bloques que un capítulo** (`h`, `p`,
`list`, `steps`, `code`, `note`, `warn`, `key`, `quote`), así que lo pinta
`reader.render_body` y la ayuda se lee con la tipografía del modo lectura, sin
un renderizador aparte que mantener.
"""
from . import buscador, util

# Los que sabe dibujar `reader._bloque`. Está aquí para que una prueba sin GTK
# pueda avisar si un tema usa un bloque que nadie pintaría.
BLOQUES = ("h", "p", "list", "steps", "code", "math", "note", "warn", "key", "quote")

SECCIONES = ("Empezar", "Estudiar", "Tu material", "Bit y la IA", "Tus datos")

# Los ejemplos largos, fuera de la tabla para que se lean como se van a ver.
_CAPITULO_EJEMPLO = """---
mazo: linux
nivel: 2
etiquetas: permisos, procesos
---

# Lo que aprendí de los permisos

Un párrafo con **negrita**, *cursiva* y `código`.

- dueño
- grupo
- resto

> [!CLAVE] El primer dígito es siempre el dueño."""

_OLLAMA = """curl -fsSL https://ollama.com/install.sh | sh
ollama pull gemma3:4b"""

TEMAS = (
    {
        "key": "primeros-pasos",
        "seccion": "Empezar",
        "icono": "🚀",
        "titulo": "Los primeros diez minutos",
        "resumen": "Qué es cada pestaña y qué hacer el primer día",
        "claves": ("empezar", "inicio", "principio", "nuevo", "tutorial"),
        "ver": ("estudiar", "atajos", "capitulos"),
        "body": [
            {"p": "AppStudy tiene tres formas de estudiar y las tres escriben en la "
                  "misma base: <b>leer</b> capítulos de corrido, <b>repasar</b> en un "
                  "popup que sale con un atajo, y <b>Bit</b>, la mascota que te saca "
                  "una tarjeta en el escritorio cuando llevas rato sin aparecer."},
            {"key": "No hay que configurar nada para empezar: vienen 864 tarjetas y "
                    "101 capítulos de fábrica, ordenados de básico a avanzado."},
            {"h": "Tu primer día"},
            {"steps": [
                "Abre la pestaña <b>Leer</b> y lee un capítulo entero del tema que te "
                "interese. Es lo que hace que las tarjetas signifiquen algo en vez de "
                "ser frases sueltas.",
                "Al final del capítulo pulsa <b>«Practicar este capítulo»</b>: el popup "
                "te pregunta justo lo que acabas de leer, en ese mismo nivel.",
                "Vuelve mañana con el atajo global (<b>Super + Shift + E</b> de "
                "fábrica): el popup sabe qué te toca sin que tengas que elegir nada.",
                "Ponte un <b>objetivo diario</b> pequeño en Ajustes —diez o quince "
                "tarjetas— y deja suelta a Bit para que te lo recuerde.",
            ]},
            {"h": "Las pestañas"},
            {"list": [
                "<b>Panel</b> — lo que llevas hoy, lo pendiente, tu racha y por dónde "
                "ibas leyendo.",
                "<b>Leer</b> — los capítulos, por mazo y nivel, y el botón para "
                "escribir los tuyos.",
                "<b>Tarjetas</b> — el explorador: buscar, filtrar por mazo y nivel, "
                "editar, crear (<b>+</b>) e importar (<b>Abrir</b>).",
                "<b>Progreso</b> — cinco gráficas, qué conviene reforzar y los logros.",
                "<b>Biblioteca</b> — tus PDF y EPUB, con sus subrayados.",
                "<b>Ajustes</b> — atajos, Bit, la IA, los repasos, sincronización y "
                "respaldos.",
            ]},
            {"note": "<b>Estudiar ahora</b>, en la cabecera, deja elegir cuánto quieres "
                     "estudiar; el atajo global abre un repaso libre, sin temporizador."},
        ],
    },
    {
        "key": "atajos",
        "seccion": "Empezar",
        "icono": "⌨️",
        "titulo": "Atajos de teclado",
        "resumen": "Las teclas de cada ventana, de un vistazo",
        "claves": ("teclas", "teclado", "combinacion", "shortcut", "hotkey"),
        "ver": ("estudiar", "biblioteca"),
        "body": [
            {"h": "En cualquier ventana"},
            {"list": [
                "<code>Super + Shift + E</code> — el popup de repaso, desde la "
                "aplicación que sea (es el de fábrica; se cambia en Ajustes).",
                "<code>Super + Shift + N</code> — captura rápida: una tarjeta nueva "
                "sin dejar lo que estabas haciendo (dentro de la aplicación, "
                "<code>Ctrl + Shift + N</code>).",
                "<code>Ctrl + K</code> — buscar en tarjetas, capítulos, libros y "
                "subrayados a la vez.",
                "<code>Ctrl + R</code> o <code>F5</code> — recargar el contenido "
                "incluido y refrescar la ventana.",
                "<code>F1</code> — esta guía.",
                "<code>Ctrl + Q</code> — cerrar la aplicación.",
            ]},
            {"h": "En el popup de repaso"},
            {"list": [
                "<code>Espacio</code> — enseñar la respuesta.",
                "<code>1</code> – <code>4</code> — responder un reto, o calificar: "
                "Otra vez · Difícil · Bien · Fácil.",
                "<code>Z</code> — deshacer el último repaso.",
                "<code>N</code> — saltar a otra tarjeta.",
                "<code>A</code> — abrir la ventana completa.",
                "<code>Esc</code> — cerrar.",
            ]},
            {"h": "Leyendo un capítulo"},
            {"list": [
                "<code>←</code> <code>→</code> — capítulo anterior o siguiente.",
                "<code>Esc</code> — volver a la lista.",
            ]},
            {"h": "En el lector de PDF"},
            {"list": [
                "<code>←</code> <code>→</code> · <code>Espacio</code> · "
                "<code>AvPág</code> <code>RePág</code> — pasar página.",
                "<code>Inicio</code> / <code>Fin</code> — primera y última.",
                "<code>+</code> / <code>−</code> · <code>Ctrl + rueda</code> — zoom, "
                "del 35 % al 400 %.",
                "<code>F</code> — alternar ajuste al ancho o a la página.",
                "<code>Ctrl + F</code> — buscar en todo el libro.",
                "<code>M</code> — marcador en esta página.",
                "<code>N</code> — modo noche.",
                "<code>S</code> — rotulador: arrastra sobre el texto para subrayar.",
            ]},
            {"h": "En un EPUB"},
            {"list": [
                "<code>←</code> <code>→</code> · <code>AvPág</code> "
                "<code>RePág</code> — capítulo anterior o siguiente.",
                "<code>Inicio</code> / <code>Fin</code> — primero y último.",
                "<code>+</code> / <code>−</code> — letra más grande o más pequeña.",
                "<code>M</code> — marcador · <code>N</code> — modo noche.",
            ]},
            {"note": "Los dos atajos globales se cambian en <b>Ajustes → Atajo "
                     "global</b> y <b>Captura rápida</b>. Deben llevar Ctrl, Alt o "
                     "Super, y si otro programa ya usa esa combinación, gana el otro."},
        ],
    },
    {
        "key": "estudiar",
        "seccion": "Estudiar",
        "icono": "🎯",
        "titulo": "Estudiar: el popup y las sesiones",
        "resumen": "Cómo se repasa, cómo se califica y cómo se deshace",
        "claves": ("repasar", "popup", "sesion", "calificar", "estudio", "objetivo"),
        "ver": ("repasos", "atajos", "bit"),
        "body": [
            {"p": "El repaso normal es el <b>popup</b>: sale con el atajo global desde "
                  "cualquier aplicación, te enseña una tarjeta, la calificas y "
                  "desaparece. No hay que abrir la ventana grande para estudiar."},
            {"h": "Calificar"},
            {"p": "Pulsa <code>Espacio</code> para ver la respuesta y responde con "
                  "sinceridad; la calificación es lo único que decide cuándo vuelve:"},
            {"list": [
                "<b>1 · Otra vez</b> — no te sonaba. Vuelve dentro de diez minutos.",
                "<b>2 · Difícil</b> — la sacaste a duras penas.",
                "<b>3 · Bien</b> — la sabías. Es la respuesta normal.",
                "<b>4 · Fácil</b> — la sabías de sobra, tardará bastante en volver.",
            ]},
            {"note": "Si te equivocas de botón, <code>Z</code> deshace el último repaso "
                     "y deja la tarjeta exactamente como estaba. El aviso que sale al "
                     "calificar también trae su botón de deshacer."},
            {"h": "Sesiones con final"},
            {"p": "<b>Estudiar ahora</b>, en la cabecera de la ventana, abre una sesión "
                  "con tiempo y cantidad: termina al llegar al límite y nunca corta una "
                  "respuesta a la mitad. <b>Repaso libre</b> es lo mismo sin reloj, que "
                  "es lo que hace el atajo global."},
            {"h": "Objetivo diario"},
            {"p": "En <b>Ajustes → Objetivo diario</b> pones cuántas tarjetas quieres "
                  "hacer al día. Aparece en el panel, en la barra superior de GNOME con "
                  "los siete días de la semana, y en Ajustes. Con 0 no hay objetivo."},
            {"key": "Una meta pequeña que cumples rinde más que una grande que "
                    "abandonas. Diez tarjetas al día son 3.650 al año."},
        ],
    },
    {
        "key": "repasos",
        "seccion": "Estudiar",
        "icono": "🧠",
        "titulo": "Cuándo vuelve cada tarjeta",
        "resumen": "FSRS, retención objetivo y las tarjetas que se atragantan",
        "claves": ("fsrs", "intervalo", "retencion", "memoria", "olvido",
                   "sanguijuela", "atragantada", "calibrar"),
        "ver": ("estudiar", "progreso"),
        "body": [
            {"p": "AppStudy usa <b>FSRS</b>, el mismo modelo de memoria que trae Anki. "
                  "De cada tarjeta guarda cuánto aguanta ese recuerdo (estabilidad, en "
                  "días) y lo que te cuesta a ti (dificultad, de 1 a 10), y con eso "
                  "calcula el día en que ibas a olvidarla."},
            {"h": "Retención objetivo"},
            {"p": "Tú eliges cuánto quieres acordarte, en <b>Ajustes → Cómo se "
                  "programan los repasos</b>. Al 90 %, que es lo recomendado, una "
                  "tarjeta con 40 días de estabilidad vuelve a los 40 días; al 95 % "
                  "vuelve a los 18, y al 85 % a los 65. Subirla es estudiar más para "
                  "olvidar menos; bajarla, al revés."},
            {"list": [
                "Lo que fallas vuelve <b>en diez minutos</b>, no cuando diga la "
                "fórmula: una tarjeta recién fallada hay que volver a verla hoy.",
                "Las tarjetas <b>nuevas</b> entran de menor a mayor nivel y son ~25 % "
                "de cada sesión; los repasos vencidos van primero.",
                "Si no hay nada pendiente, el popup ofrece un repaso de refuerzo: el "
                "atajo nunca queda vacío.",
            ]},
            {"h": "Calibrar con tu historial"},
            {"p": "Con 400 repasos encadenados aparece <b>Calibrar con mi historial</b>: "
                  "reajusta los pesos del modelo a cómo memorizas tú. Tarda un rato, va "
                  "en segundo plano y no puede empeorar lo que hay — si ningún ajuste "
                  "mejora la predicción, deja los pesos como estaban y te lo dice."},
            {"h": "Tarjetas que se te atragantan"},
            {"p": "Una tarjeta que fallas una y otra vez no se arregla estudiándola "
                  "más: suele estar mal escrita o preguntar dos cosas a la vez. A los "
                  "<b>ocho fallos</b> se aparta sola y va a una lista en Ajustes, con "
                  "un botón para editarla y otro para devolverla al ciclo con los "
                  "fallos a cero. El umbral se cambia ahí mismo; con 0 se apaga."},
        ],
    },
    {
        "key": "tarjetas",
        "seccion": "Tu material",
        "icono": "🗂️",
        "titulo": "Crear y organizar tarjetas",
        "resumen": "Los cuatro tipos, los huecos, las etiquetas y el explorador",
        "claves": ("crear", "nueva", "editar", "huecos", "cloze", "reto", "leccion",
                   "etiqueta", "nivel", "captura"),
        "ver": ("importar", "capitulos", "ia"),
        "body": [
            {"p": "El botón <b>+</b> de la cabecera abre el editor. Desde cualquier "
                  "aplicación, <code>Super + Shift + N</code> abre la <b>captura "
                  "rápida</b>: escribes la idea y sigues con lo tuyo."},
            {"h": "Cuatro tipos"},
            {"list": [
                "<b>Tarjeta</b> — pregunta y respuesta, con pista opcional.",
                "<b>Reto</b> — opción múltiple, con la explicación del porqué.",
                "<b>Lección</b> — solo enseña algo, no pregunta.",
                "<b>Huecos</b> — un texto del que se tapa un trozo.",
            ]},
            {"h": "Huecos"},
            {"p": "En una tarjeta de huecos marcas entre dobles llaves lo que quieres "
                  "tapar. Cada vez que aparece se tapa <b>un hueco distinto</b>, así "
                  "que una sola tarjeta da tantas preguntas como trozos marques, "
                  "siempre en su contexto. Lo que va tras <code>::</code> es una pista."},
            {"code": "En chmod 755 el {{7}} es del dueño y el {{5::en octal}} del grupo."},
            {"h": "Cómo se ordenan"},
            {"list": [
                "Cada tarjeta va en un <b>mazo</b> y un <b>nivel</b> (1 es el más "
                "básico): las nuevas entran de menor a mayor nivel.",
                "Las <b>etiquetas</b> son lo que usa «Practicar este capítulo» y lo que "
                "agrupa «Qué conviene reforzar» en Progreso.",
                "En la pestaña <b>Tarjetas</b> se busca por texto y se filtra por mazo "
                "y nivel; al pulsar una se abre su editor.",
            ]},
            {"h": "Formato"},
            {"p": "Se admite <code>&lt;b&gt;negrita&lt;/b&gt;</code>, "
                  "<code>&lt;i&gt;cursiva&lt;/i&gt;</code>, "
                  "<code>&lt;code&gt;código&lt;/code&gt;</code> y fórmulas en LaTeX "
                  "entre signos de dólar. El código de varias líneas sale coloreado."},
            {"warn": "Al recargar el contenido incluido, una tarjeta <b>de fábrica</b> "
                     "que ya no esté en su JSON se retira con su historial. Las tuyas "
                     "no se tocan nunca."},
        ],
    },
    {
        "key": "importar",
        "seccion": "Tu material",
        "icono": "📥",
        "titulo": "Traer tarjetas de Anki o de un CSV",
        "resumen": "Importar sin perder el historial de lo que ya tenías",
        "claves": ("importar", "anki", "apkg", "csv", "tsv", "abrir", "migrar"),
        "ver": ("tarjetas",),
        "body": [
            {"p": "En la pestaña <b>Tarjetas</b>, el botón <b>Abrir</b> importa desde "
                  "CSV, TSV, las exportaciones de texto de Anki y los paquetes "
                  "<code>.apkg</code>."},
            {"steps": [
                "Elige el archivo. Se lee fuera del hilo gráfico, así que la ventana "
                "no se congela aunque sea una colección grande.",
                "Mira la muestra —las primeras 40 filas— y elige en qué mazo entran.",
                "Guarda. Las tarjetas se escriben en lotes de 100.",
            ]},
            {"list": [
                "Los <b>duplicados actualizan</b> el texto sin borrar su historial: "
                "cada tarjeta se reconoce por su enunciado.",
                "Como mucho, 5.000 tarjetas y 200 MB por importación.",
            ]},
            {"note": "Lo importado entra sin repasos: aparecerá como tarjeta nueva y "
                     "empezará a programarse desde la primera vez que la califiques."},
        ],
    },
    {
        "key": "capitulos",
        "seccion": "Tu material",
        "icono": "📖",
        "titulo": "Leer capítulos y escribir los tuyos",
        "resumen": "El modo lectura, practicar lo leído y el Markdown de tus capítulos",
        "claves": ("leer", "lectura", "capitulo", "markdown", "escribir", "fuente"),
        "ver": ("tarjetas", "biblioteca", "ia"),
        "body": [
            {"p": "La pestaña <b>Leer</b> tiene 101 capítulos que se leen de corrido, "
                  "ordenados por mazo y nivel. Un capítulo se marca como leído al "
                  "llegar al final, o a mano con su botón."},
            {"h": "Lo que enlaza leer con repasar"},
            {"list": [
                "<b>«Practicar este capítulo»</b> abre el popup con las tarjetas de ese "
                "tema y ese nivel.",
                "<b>«✦ Sacar tarjetas»</b> propone tarjetas del texto que tienes "
                "delante con la IA local; tú marcas cuáles se guardan.",
                "<b>«Volver a la fuente →»</b>, desde una tarjeta, abre el capítulo o la "
                "página de donde salió, en el párrafo exacto.",
            ]},
            {"h": "Escribir un capítulo tuyo"},
            {"p": "Desde <b>Leer → «Escribir un capítulo»</b>, o dejando un "
                  "<code>.md</code> en <code>~/.local/share/appstudy/lecturas/</code> y "
                  "pulsando <code>Ctrl+R</code>. La cabecera dice de qué mazo es y en "
                  "qué nivel va; el primer <code>#</code> es el título."},
            {"code": {"lang": "markdown", "text": _CAPITULO_EJEMPLO}},
            {"list": [
                "Los recuadros son <code>&gt; [!NOTA]</code>, <code>&gt; [!AVISO]</code> "
                "y <code>&gt; [!CLAVE]</code>; una fórmula suelta va entre dobles "
                "dólares.",
                "Si no pones <code>minutos</code>, se estiman contando palabras.",
            ]},
            {"key": "El archivo es la fuente y la base solo una copia: editas el "
                    "<code>.md</code>, pulsas Ctrl+R y ya está. Recargar el contenido "
                    "de fábrica no se lleva tus capítulos."},
        ],
    },
    {
        "key": "biblioteca",
        "seccion": "Tu material",
        "icono": "📚",
        "titulo": "Tus PDF y EPUB",
        "resumen": "Leer tus libros dentro de la app, subrayar y sacar tarjetas",
        "claves": ("libro", "pdf", "epub", "subrayado", "rotulador", "nota",
                   "marcador", "estante"),
        "ver": ("capitulos", "atajos", "ia"),
        "body": [
            {"p": "En <b>Ajustes → Biblioteca</b> eliges la carpeta donde tienes los "
                  "libros. La pestaña <b>Biblioteca</b> convierte tus carpetas en "
                  "estantes y, arriba, deja <b>Seguir leyendo</b> con los últimos que "
                  "abriste y por qué página ibas."},
            {"note": "Los libros no se copian ni se mueven: se leen donde están. En la "
                     "base solo queda su ruta, la página y los minutos leídos."},
            {"h": "Subrayar"},
            {"steps": [
                "Pulsa <code>S</code> (o el rotulador de la barra) y arrastra sobre el "
                "texto.",
                "Toca el subrayado para abrir su ficha: la cita, tu nota, cuatro "
                "colores y <b>✦ Hacer tarjeta</b>.",
                "En <b>✦ Hacer tarjeta</b> la cita ya viene de respuesta; la pregunta la "
                "escribes tú, que es lo que obliga a entender lo leído.",
            ]},
            {"p": "El botón de la lista enseña todo lo subrayado del libro, salta a su "
                  "página y lo copia entero en Markdown. Lo subrayado también sale en "
                  "la búsqueda global (<code>Ctrl+K</code>), y desde ahí se abre el "
                  "libro en esa misma página."},
            {"h": "Tarjetas del libro"},
            {"p": "En el menú <code>⋯</code> del lector, <b>✦ Tarjetas</b> saca tarjetas "
                  "de las páginas que tienes delante (en un EPUB, del capítulo abierto). "
                  "Las guardadas recuerdan el libro y el tramo, así que «Volver a la "
                  "fuente» te devuelve a esa página."},
            {"list": [
                "El progreso se guarda solo en cada cambio de página, y al salir se "
                "anotan los minutos leídos.",
                "<b>Modo noche</b> (<code>N</code>), <b>marcadores</b> "
                "(<code>M</code>) y <b>buscar en todo el libro</b> "
                "(<code>Ctrl+F</code>, solo PDF).",
                "Los EPUB necesitan WebKitGTK: "
                "<code>sudo apt install gir1.2-webkit-6.0</code>. Sin él, el resto de "
                "la biblioteca funciona igual.",
            ]},
        ],
    },
    {
        "key": "bit",
        "seccion": "Bit y la IA",
        "icono": "✨",
        "titulo": "Bit, la mascota",
        "resumen": "Soltarla, su menú, cuándo te habla y cómo evoluciona",
        "claves": ("mascota", "bit", "escritorio", "recordatorio", "aviso",
                   "accesorio", "evolucion", "silencio", "dormir"),
        "ver": ("estudiar", "ia", "problemas"),
        "body": [
            {"p": "Bit vive en una ventanita sin bordes, encima del resto y en todos "
                  "los espacios de trabajo. Se suelta desde <b>Ajustes → Bit, la "
                  "mascota</b>, con <code>appstudy --pet</code> o con el interruptor de "
                  "la barra superior de GNOME."},
            {"h": "Qué hace"},
            {"list": [
                "<b>Clic</b> — salta y te enseña una tarjeta, con pregunta y respuesta "
                "juntas: solo dices si la sabías, y cuenta como un repaso normal.",
                "<b>Clic derecho</b> — su menú: enséñame algo, ponme a prueba, una "
                "frase de libro, cómo va la semana, sesión completa, abrir AppStudy, "
                "más grande / más pequeño, silencio, dormir y salir.",
                "<b>Arrastrar</b> — la cambia de sitio, y recuerda dónde la dejaste.",
                "<b>Ponme a prueba</b> — seis formatos de reto contrarreloj; responder "
                "rápido y bien vale por «fácil».",
            ]},
            {"h": "Cuándo te habla"},
            {"p": "Cada 45 minutos por defecto, y solo si hay algo pendiente; si no, te "
                  "suelta una frase de un libro. En Ajustes se cambia cada cuánto, se "
                  "limita a <b>días laborables, fines de semana o todos los días</b> y "
                  "se elige la franja horaria. Si estorba ahora mismo, <b>Duérmete 60 "
                  "min</b> desde su menú."},
            {"p": "El ánimo depende sobre todo de cuánto llevas sin repasar: normal o "
                  "feliz al día, aburrida a las cuatro horas, hambrienta al día y "
                  "triste a los tres."},
            {"h": "Evolución y accesorios"},
            {"p": "Bit pasa de Compañero a Curioso, Aplicado, Sabio y Maestro según tus "
                  "repasos reales. A los 25, 100 y 500 repasos desbloquea un pañuelo, "
                  "unas gafas y una corona: eliges cuál lleva en <b>Ajustes → "
                  "Apariencia y progreso</b>, donde también ves cuánto falta para la "
                  "siguiente etapa."},
            {"note": "El tamaño va del 50 % al 250 %, desde su menú o con el número "
                     "exacto en Ajustes. Y si prefieres una interfaz quieta, <b>Reducir "
                     "movimiento</b> apaga rebotes, partículas y transiciones sin "
                     "quitarle las caras ni los colores."},
        ],
    },
    {
        "key": "ia",
        "seccion": "Bit y la IA",
        "icono": "🤖",
        "titulo": "La IA local",
        "resumen": "Qué hace falta para que Bit explique y genere tarjetas",
        "claves": ("ia", "ollama", "modelo", "gemma", "chatbot", "explicame",
                   "generar", "inteligencia"),
        "ver": ("bit", "tarjetas", "problemas"),
        "body": [
            {"p": "Bit puede hablar con un <b>modelo que corre en tu propia máquina</b>. "
                  "Ni tus tarjetas ni tus preguntas salen del equipo, no hay clave de "
                  "API y no cuesta nada por pregunta. Es opcional: todo lo demás "
                  "funciona sin ella."},
            {"h": "Ponerla en marcha"},
            {"steps": [
                "Instala Ollama (el servidor) y déjalo escuchando en "
                "<code>http://localhost:11434</code>.",
                "Descarga un modelo pequeño.",
                "En <b>Ajustes → Inteligencia artificial</b>, activa el interruptor y "
                "pulsa <b>Probar conexión</b>.",
            ]},
            {"code": {"lang": "bash", "text": _OLLAMA}},
            {"h": "Dónde se usa"},
            {"list": [
                "Menú de Bit → <b>Pregúntame algo</b>: una pregunta suelta; si venías "
                "de una tarjeta, la usa como contexto.",
                "En una tarjeta → <b>🧠 Explícamelo mejor</b>: te la explica con otras "
                "palabras y un ejemplo.",
                "En una tarjeta → <b>💬 Modo chatbot</b>: una conversación con esa "
                "tarjeta de contexto; Bit se pone azul mientras charláis.",
                "Pestaña Tarjetas → botón <b>✦</b>: genera tarjetas sobre un tema.",
                "En un capítulo, un PDF o un EPUB → <b>✦ Tarjetas</b>: genera solo desde "
                "ese texto y conserva la fuente.",
            ]},
            {"warn": "Un modelo local se equivoca, y una tarjeta mala se estudia igual "
                     "que una buena: por eso lo generado <b>se revisa antes de "
                     "guardarse</b> y queda etiquetado como <code>ia</code> para que "
                     "puedas encontrarlo después."},
            {"note": "Lo que manda la velocidad es la VRAM libre. <b>Pausar IA y liberar "
                     "memoria</b>, en Ajustes, devuelve la gráfica cuando no la uses."},
        ],
    },
    {
        "key": "progreso",
        "seccion": "Tus datos",
        "icono": "📈",
        "titulo": "Progreso, logros y qué reforzar",
        "resumen": "Qué dicen las gráficas y cómo empezar de cero sin perderlo todo",
        "claves": ("progreso", "grafica", "estadistica", "logro", "racha",
                   "retencion", "reforzar", "debil"),
        "ver": ("repasos", "estudiar"),
        "body": [
            {"p": "La pestaña <b>Progreso</b> convierte tu historial en cuatro cifras y "
                  "cinco gráficas. La primera cifra es <b>memoria construida</b>: la "
                  "suma de lo que aguantaría cada tarjeta si dejaras de estudiar hoy. "
                  "Es el mejor resumen del trabajo hecho, porque no cuenta repasos: "
                  "cuenta memoria."},
            {"list": [
                "<b>Tu año</b> — una casilla por día, como el cuadro de "
                "contribuciones.",
                "<b>En qué punto están tus tarjetas</b> — sin estrenar, aprendiendo, "
                "jóvenes, maduras y atragantadas.",
                "<b>Cuánto aciertas en cada mazo</b> — con tu retención objetivo "
                "marcada, para ver cuál se te resiste.",
                "<b>Lo que viene</b> — lo que vence cada día de los próximos 30, con lo "
                "atrasado en rojo.",
                "<b>Cuánto tardas en contestar</b> — la mediana por nivel.",
            ]},
            {"p": "Debajo, <b>Qué conviene reforzar</b> reúne los fallos y las "
                  "respuestas difíciles de los últimos 90 días por etiqueta y deja "
                  "practicar ese foco con un clic."},
            {"h": "Logros"},
            {"p": "Once marcas que se pasan sin darse cuenta —rachas de 7, 30 y 100 "
                  "días, mil repasos, un mazo dominado, un mazo leído entero…—. Bit lo "
                  "celebra una vez y luego se quedan al final de esta pestaña, con los "
                  "que faltan y qué hay que hacer para conseguirlos."},
            {"h": "Empezar de cero"},
            {"list": [
                "<b>Borrar lo estudiado hoy</b> — quita los repasos de las últimas 24 h "
                "y deja cada tarjeta como estaba antes. La racha se recalcula sola.",
                "<b>Reiniciar la racha</b> — vuelve a cero sin tocar ninguna tarjeta.",
            ]},
            {"note": "Los dos están en <b>Ajustes → Apariencia y progreso</b> y piden "
                     "confirmación."},
        ],
    },
    {
        "key": "nube",
        "seccion": "Tus datos",
        "icono": "☁️",
        "titulo": "Tu cuenta en la nube",
        "resumen": "Entrar una vez y tener tu historial en cualquier equipo",
        "claves": ("nube", "cuenta", "supabase", "entrar", "iniciar sesion",
                   "sesion", "usuario", "contrasena", "correo", "registrarse",
                   "salir", "en linea", "internet"),
        "ver": ("sincronizar", "progreso"),
        "body": [
            {"h": "Entrar"},
            {"steps": [
                "En <b>Ajustes → Cuenta en la nube</b>, escribe tu correo y una "
                "contraseña.",
                "Pulsa <b>Crear cuenta</b> la primera vez y <b>Entrar</b> las "
                "siguientes.",
                "En el otro equipo, entra con el mismo correo: tu historial aparece "
                "solo.",
            ]},
            {"key": "Se entra <b>una sola vez por equipo</b>. La sesión queda guardada "
                    "y se renueva sola al abrir, así que no vuelves a escribir la "
                    "contraseña."},
            {"h": "Qué viaja y cuándo"},
            {"p": "Lo mismo que por carpeta compartida: tus mazos, tarjetas y capítulos "
                  "propios, el estado de cada repaso, el historial completo, el avance "
                  "de lectura y el origen de cada tarjeta. Con <b>Sincronizar sola al "
                  "abrir y al cerrar</b> puesto no tienes que acordarte de nada; el "
                  "botón <b>Sincronizar</b> lo hace cuando tú quieras."},
            {"note": "Sin red se estudia igual: lo de hoy sube en el próximo arranque. "
                     "Nada de esto retrasa abrir ni cerrar la aplicación."},
            {"h": "Varias personas, un equipo"},
            {"p": "Cada cuenta tiene su propia base en el equipo y su propio espacio en "
                  "el servidor, así que dos personas no se ven ni se pisan el progreso. "
                  "Al entrar por primera vez en un equipo que ya usabas sin cuenta, lo "
                  "que llevabas estudiado pasa a ser de esa cuenta y sube; quien se "
                  "siente después arranca limpio."},
            {"note": "<b>Salir</b> solo cierra la sesión: tu progreso se queda en el "
                     "equipo y al volver a entrar sigue ahí."},
            {"h": "Si dice que falta configurar"},
            {"p": "El proyecto de Supabase se configura una vez, en el archivo "
                  "<code>.env</code> de la raíz. La propia sección te dice qué variable "
                  "falta y dónde encontrarla; el <code>README</code> lo explica paso a "
                  "paso, incluido el SQL que crea la tabla, que se copia del archivo "
                  "<code>supabase/esquema.sql</code> y se pega en el editor del panel."},
            {"warn": "Tus tarjetas se guardan en tu proyecto de Supabase, cifradas en "
                     "el viaje pero legibles allí. Si llevan datos sensibles, usa la "
                     "carpeta compartida."},
        ],
    },
    {
        "key": "sincronizar",
        "seccion": "Tus datos",
        "icono": "🔄",
        "titulo": "Sincronizar y respaldar",
        "resumen": "Llevar el progreso a otro equipo y no perderlo nunca",
        "claves": ("sincronizar", "sincronizacion", "otro equipo", "portatil",
                   "nextcloud", "syncthing", "dropbox", "respaldo", "copia",
                   "restaurar", "exportar"),
        "ver": ("nube", "progreso"),
        "body": [
            {"h": "Entre dos equipos"},
            {"steps": [
                "En <b>Ajustes → Sincronización entre equipos</b>, elige una carpeta "
                "compartida por Nextcloud, Syncthing, Dropbox o una memoria.",
                "Pulsa <b>Sincronizar</b> en este equipo: deja ahí su archivo.",
                "Haz lo mismo en el otro, apuntando a la misma carpeta.",
            ]},
            {"p": "Se fusionan los repasos y su estado, tus tarjetas, los capítulos que "
                  "escribiste y el avance de lectura. Los repasos se unen como eventos "
                  "y se deduplican; en una edición hecha a la vez en dos sitios gana la "
                  "más reciente; lo que borras no vuelve a aparecer."},
            {"note": "Solo trabaja cuando pulsas el botón: no hay ningún servicio "
                     "consultando la red por detrás. Cada equipo escribe su propio "
                     "archivo, así que no se pisan."},
            {"warn": "Los PDF y EPUB, sus subrayados y las preferencias del escritorio "
                     "<b>no viajan</b>: sus rutas son de cada equipo. Los archivos de "
                     "sincronización son JSON legible, sin cifrar; usa una carpeta "
                     "privada si tus tarjetas llevan datos sensibles."},
            {"h": "Respaldos"},
            {"p": "Todo tu progreso vive en un solo archivo: "
                  "<code>~/.local/share/appstudy/appstudy.db</code>. En <b>Ajustes → "
                  "Respaldo</b> hay copia manual, <b>respaldo automático diario</b> "
                  "(activado de fábrica), <b>Restaurar…</b> y <b>Exportar…</b>."},
            {"key": "Restaurar no reinicia nada, y antes de pisar lo que tienes guarda "
                    "una copia «antes de restaurar»: equivocarse tiene vuelta atrás."},
        ],
    },
    {
        "key": "problemas",
        "seccion": "Tus datos",
        "icono": "🛠️",
        "titulo": "Si algo no va",
        "resumen": "Los tropiezos habituales y qué hacer con cada uno",
        "claves": ("problema", "error", "falla", "no funciona", "arreglar",
                   "solucion", "wmctrl", "webkit", "pygments"),
        "ver": ("bit", "ia", "atajos"),
        "body": [
            {"h": "Bit no se queda encima de las demás ventanas"},
            {"p": "Wayland no deja que una aplicación se ponga encima, así que la "
                  "mascota se lanza aparte en X11 y se lo pide al gestor de ventanas. "
                  "Instala lo que le falta:"},
            {"code": {"lang": "bash", "text": "sudo apt install wmctrl x11-utils"}},
            {"h": "El atajo global no hace nada"},
            {"p": "Otro programa puede tener esa combinación. Cámbiala en <b>Ajustes → "
                  "Atajo global</b>; debe llevar Ctrl, Alt o Super."},
            {"h": "Un EPUB no abre"},
            {"p": "Falta WebKitGTK: <code>sudo apt install gir1.2-webkit-6.0</code>. "
                  "Los PDF y el resto de la biblioteca no lo necesitan."},
            {"h": "El código sale sin colores"},
            {"p": "Falta Pygments: <code>sudo apt install python3-pygments</code>. El "
                  "texto se ve igual, solo que sin resaltar."},
            {"h": "La IA no responde"},
            {"p": "Comprueba que el servidor está vivo y que el modelo está descargado; "
                  "luego vuelve a <b>Ajustes → Inteligencia artificial → Probar "
                  "conexión</b>."},
            {"code": {"lang": "bash", "text": "systemctl --user status ollama\nollama list"}},
            {"h": "El indicador de la barra superior no aparece"},
            {"p": "En Wayland, GNOME no carga extensiones nuevas en caliente: <b>cierra "
                  "sesión y vuelve a entrar</b> después de instalarla."},
            {"h": "Edité un capítulo o un JSON y no lo veo"},
            {"p": "<code>Ctrl+R</code> o <code>F5</code> recargan el contenido sin tocar "
                  "tu progreso. Tras actualizar la aplicación, cierra y abre la ventana; "
                  "para la mascota, <code>appstudy --pet-off &amp;&amp; appstudy "
                  "--pet</code>."},
        ],
    },
)


def temas() -> tuple:
    return TEMAS


def tema(key: str) -> dict | None:
    return next((t for t in TEMAS if t["key"] == key), None)


def por_seccion() -> list[tuple[str, list[dict]]]:
    """Los temas agrupados como se enseñan, en el orden declarado."""
    salida = []
    for seccion in SECCIONES:
        grupo = [t for t in TEMAS if t["seccion"] == seccion]
        if grupo:
            salida.append((seccion, grupo))
    return salida


def texto_plano(t: dict) -> str:
    """Todo el texto de un tema, sin etiquetas: para buscar y para probar."""
    partes = [t["titulo"], t["resumen"]]
    for bloque in t["body"]:
        for tipo, contenido in bloque.items():
            if tipo == "code":
                continue                  # las órdenes no son texto que se lea
            if isinstance(contenido, list):
                partes.extend(str(x) for x in contenido)
            elif isinstance(contenido, dict):
                partes.append(str(contenido.get("text", "")))
            else:
                partes.append(str(contenido))
    return util.plain(" ".join(partes))


def buscar(consulta: str, limite: int = 8) -> list[dict]:
    """Los temas que hablan de eso, primero los que lo llevan en el título.

    Se exigen todas las palabras, como en la búsqueda global, y no se distinguen
    acentos ni mayúsculas: «sincronizacion» encuentra «Sincronización».
    """
    palabras = [p for p in buscador.normalizar(consulta).split() if p]
    if not palabras or len("".join(palabras)) < 2:
        return []
    encontrados = []
    for t in TEMAS:
        cabeza = buscador.normalizar(
            f"{t['titulo']} {t['resumen']} {' '.join(t.get('claves', ()))}")
        cuerpo = buscador.normalizar(texto_plano(t))
        if not all(p in cabeza or p in cuerpo for p in palabras):
            continue
        puntos = sum(3.0 if p in cabeza else 1.0 for p in palabras)
        encontrados.append((puntos, t))
    return [t for _, t in sorted(encontrados, key=lambda x: -x[0])][:limite]
