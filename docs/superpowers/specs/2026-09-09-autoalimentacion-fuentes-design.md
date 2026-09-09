# Autoalimentación de contenido desde fuentes abiertas

Fecha: 2026-09-09

## El problema

AppStudy trae 1.245 tarjetas y 145 capítulos de fábrica. Es un catálogo fijo:
cuando se agota, se agota. Ampliarlo exige abrir la ventana de Fuentes, buscar a
mano, previsualizar e importar uno por uno.

Este diseño añade un subsistema que, en el primer arranque de cada día, sale a
buscar material nuevo en fuentes abiertas, lo filtra, propone tarjetas con la IA
local y lo deja esperando tu visto bueno en una bandeja de entrada.

## Decisiones tomadas

| Decisión | Elegido | Por qué |
|---|---|---|
| Qué produce | Capítulo de lectura **y** tarjetas derivadas | Encaja con el flujo que ya existe: leer, «Practicar este capítulo», «Volver a la fuente →» |
| Ritmo | Una ración diaria: 1 lectura + ~6 tarjetas | Abrir la app cinco veces no debe traer cinco raciones; satura el repaso |
| Aprobación | Bandeja de entrada | Nada entra a los mazos sin verlo |
| Sin red o sin IA | Silencio y reintento mañana | Un fallo de red no debe estorbar al estudio |
| Estrategia | Híbrida: catálogo curado + búsqueda + recorrido de índices | Calidad desde el día uno, sin techo a medio plazo |

## Fuentes

Todas comprobadas con peticiones reales el 2026-09-09. Se registran en
`extensiones.INCLUIDAS` para poder apagarlas una a una desde Ajustes.

### Con API de búsqueda

| Fuente | Punto de acceso | Formato |
|---|---|---|
| MediaWiki (Wikipedia es/en, simple, Wikibooks, Wikiversity, Wiktionary, ArchWiki, Gentoo) | `/w/rest.php/v1/search/page?q=` (ArchWiki y Gentoo, sin el `/w`) | JSON |
| arXiv | `https://export.arxiv.org/api/query?search_query=` | Atom |
| MDN | `https://developer.mozilla.org/api/v1/search?q=&locale=` | JSON |
| OpenStax | `https://openstax.org/apps/cms/api/v2/pages/?type=books.Book` | JSON |
| Project Gutenberg | `https://gutendex.com/books/?search=` | JSON |
| Open Library | `https://openlibrary.org/search.json?q=` | JSON |
| Standard Ebooks | `https://standardebooks.org/feeds/atom/new-releases` | Atom |

`export.arxiv.org` solo en HTTPS: el HTTP devuelve 301 y `validar_url` rechaza
esquemas que no sean HTTPS.

### Por índice enumerable

| Fuente | Índice | Nota |
|---|---|---|
| LibreTexts (`workforce`, `eng`, `espanol`, `math`, `phys`, `stats`) | `/sitemap.xml` | 3,6 MB por host: se refresca una vez al mes, nunca en el arranque |
| man7.org | `dir_all_alphabetic.html` | 1,8 MB, mismo tratamiento |
| docs.python.org (es) | índice de módulos | El `searchindex.js` pesa 4,3 MB: no se usa |
| MIT OCW | `CATALOGOS["mit"]` más los enlaces que ya extrae `previsualizar()` | La API `api/v0` fue retirada (404) |
| TLDP, kernel.org, scikit-learn, pandas, HuggingFace, ibiblio, VOA, Saylor | páginas índice propias | |

### Descartadas

All About Circuits (403), NIOSH/CDC (403), OER Commons (403), British Council
(sin conexión), Khan Academy (410, API retirada). La API de Stack Exchange
responde 200 pero queda fuera por criterio: respuestas sueltas de calidad
desigual no son material de estudio.

BBC Learning English y Paul's Online Math Notes responden 200 y quedan fuera por
licencia: son material con derechos reservados.

### Reparto por mazo

| Mazo | Fuentes |
|---|---|
| Inglés | simple.wikipedia (A2·B1), en.wikipedia (B2·C1), Wiktionary, VOA, Standard Ebooks, Gutenberg |
| Linux | ArchWiki, Gentoo, man7, TLDP, kernel.org |
| Ciencia de Datos | pandas, scikit-learn, OpenStax *Introductory Statistics*, LibreTexts Statistics, arXiv `stat.ML` |
| IA | arXiv `cs.AI`/`cs.CL`/`cs.LG`, HuggingFace, en.wikipedia |
| Matemáticas | OpenStax, LibreTexts Math, MIT OCW 18.01 y 18.06, es.wikiversity |
| Electricidad | ibiblio *Lessons In Electric Circuits*, LibreTexts eng y phys, OpenStax *University Physics* vol. 2, MIT 6.002 |
| Python | docs.python.org (es), Wikibooks Python, pandas, módulo freeCodeCamp existente |
| Automotriz | LibreTexts Workforce, Wikibooks, Wikipedia |
| Maquinaria amarilla | LibreTexts Workforce, Wikibooks, Wikipedia |

**Limitación conocida:** maquinaria amarilla apenas tiene fuentes abiertas. Los
manuales de hidráulica de volquetes y orugas son propiedad de los fabricantes.
Ese mazo se alimentará poco y con material general de hidráulica.

## Licencias

La app publica y sincroniza mazos (`nube.py`, `sincronizacion.py`), así que el
texto importado puede salir del equipo. Cada fuente se declara de un tipo:

- **`abierta`** — el texto completo pasa al capítulo. Wikimedia (CC BY-SA),
  OpenStax y LibreTexts (CC BY), VOA (dominio público), Gutenberg y Standard
  Ebooks (dominio público), Saylor (CC BY), HuggingFace, pandas, scikit-learn y
  kernel (Apache/BSD/GPL), ibiblio (Design Science License).
- **`solo-enlace`** — solo título, resumen breve y enlace. arXiv (licencia por
  artículo), man7 (licencias mezcladas por página), MDN, ArchWiki y Gentoo
  (GFDL/CC BY-SA con requisitos de atribución que es fácil incumplir por
  descuido).

`fuentes.importar()` ya añade un bloque de atribución con origen, autor,
licencia y fecha. Se conserva tal cual.

## Arquitectura

Cuatro módulos nuevos, cada uno con un trabajo y sin conocer al siguiente.

### `catalogo.py` — qué existe ahí fuera

Registro declarativo, sin red y sin estado. Por fuente: identificador, host,
tipo (`buscador` / `indice` / `catalogo`), licencia (`abierta` / `solo-enlace`),
mazos a los que sirve, niveles e idioma. Amplía `DOMINIOS` y `CATALOGOS` de
`fuentes.py` y registra cada conector en `extensiones.INCLUIDAS`.

Interfaz: `fuentes_de(deck_key, nivel=None) -> list[dict]`,
`por_id(ident) -> dict`, `hosts() -> set[str]`.

### `selector.py` — qué toca hoy

Puro cálculo sobre la base. Consulta qué mazo tiene menos material pendiente,
qué etiquetas se fallan más y qué se importó ya (`source_imports`, `inbox`).

Interfaz: `plan(con, ahora=None) -> dict | None` con `{deck, nivel, terminos,
fuentes, motivo}`. Devuelve `None` cuando no hay nada que pedir.

Es la pieza con toda la lógica interesante y no toca la red, así que se prueba
entera contra una base sintética.

### `cosecha.py` — traerlo

El único módulo con red. Ejecuta el plan contra `fuentes.buscar()` y
`fuentes.previsualizar()`, que ya validan URL, dominio, redirecciones y tamaño.
Aplica los filtros y deja lo que sobrevive en la bandeja.

Interfaz: `auto_si_toca(con) -> bool` (calcada de `respaldo.auto_si_toca`),
`cosechar(con, plan) -> list[dict]`, `filtrar(doc, plan) -> dict` con `score`,
`nivel` y `motivo`.

Captura `FuenteError` por fuente: si arXiv está caído, las demás siguen.

### `bandeja.py` — la cola del visto bueno

Interfaz: `pendientes(con) -> list[dict]`, `guardar(con, doc, plan)`,
`aceptar(con, inbox_id, cards_elegidas) -> chapter`, `descartar(con, inbox_id)`.

`aceptar` llama a `fuentes.importar()` y crea las tarjetas. `descartar` recuerda
el origen para no volver a proponerlo.

## Flujo en el arranque

`app.do_startup` llama a `cosecha.auto_si_toca(self.con)` justo después de
`respaldo.auto_si_toca`, con el mismo interruptor en `meta` para poder apagarlo.

`auto_si_toca` devuelve `False` sin hacer nada si ya se cosechó hoy
(`meta["cosecha_last"]`) o si el ajuste está desactivado. Si toca, lanza
`util.hilo(trabajo, listo, fallo, largo=True)`; `trabajo` abre su propia
conexión SQLite, porque una conexión pertenece a su hilo.

Nada de esto está en el camino crítico del arranque. Un fallo se anota en
`meta["cosecha_error"]` y se ve en Ajustes › Fuentes, igual que `nube_error`.
No se muestra ningún aviso.

## Esquema

Una tabla nueva:

```sql
CREATE TABLE IF NOT EXISTS inbox (
  id INTEGER PRIMARY KEY,
  provider TEXT NOT NULL, origin TEXT NOT NULL, deck_id INTEGER NOT NULL,
  title TEXT NOT NULL, summary TEXT DEFAULT '', text TEXT DEFAULT '',
  author TEXT DEFAULT '', license TEXT DEFAULT '',
  score REAL DEFAULT 0, motivo TEXT DEFAULT '', cards TEXT DEFAULT '[]',
  estado TEXT DEFAULT 'pendiente', created REAL NOT NULL,
  UNIQUE(provider, origin, deck_id));
```

`estado` toma `pendiente`, `aceptado` o `descartado`; los descartados se
conservan para no reproponerlos. `cards` guarda las tarjetas propuestas en JSON
hasta que se aceptan. Los duplicados se resuelven con `fuentes.huella()` y el
`UNIQUE(provider,origin,deck_id)` de `source_imports`, que ya existe.

## Filtros de calidad

Siete comprobaciones, cada una con un motivo legible cuando rechaza:

1. **Cuerpo** — entre 400 y 20.000 palabras, con párrafos reales. Fuera esbozos
   y páginas de desambiguación.
2. **Prosa, no navegación** — proporción mínima de frases con verbo frente a
   listas de enlaces.
3. **Idioma** — por frecuencia de palabras vacías, sin dependencias nuevas. El
   mazo de inglés exige inglés; los demás aceptan español, e inglés solo si no
   hubo nada en español.
4. **Relevancia** — solapamiento entre los términos del plan y el título más los
   primeros párrafos, por encima de un umbral.
5. **Nivel** — longitud media de frase y proporción de palabras largas dan
   básico / intermedio / avanzado. **No rechaza**: coloca el capítulo en su
   nivel.
6. **Duplicado** — `fuentes.huella()` y parecido de título contra los capítulos
   del mazo.
7. **Licencia** — de `catalogo.py`. Una fuente `solo-enlace` nunca llega con
   texto completo.

La suma ponderada es el `score`. Por debajo del umbral no entra en la bandeja, y
el motivo del rechazo se guarda: sin eso, «no me trae nada» sería indepurable.

## Tarjetas

Con el capítulo aceptado se llama a `ia.generar_desde_texto()`, que ya existe.
Encima, dos validaciones nuevas:

- la respuesta debe aparecer en el texto de origen, contra invenciones de la IA;
- el frente no puede repetir una tarjeta ya presente en el mazo, normalizando
  con `fuentes.clave()`.

Cada tarjeta nace con `card_sources` apuntando al capítulo, así que «Volver a la
fuente →» funciona sin código nuevo.

Si la IA local no está disponible, el capítulo se guarda igual y la bandeja
ofrece generar las tarjetas más tarde.

## Interfaz

Una pantalla en la ventana principal, con contador cuando hay algo esperando.
Por elemento: título, fuente, licencia, el motivo por el que se propone, el
texto plegado y las tarjetas propuestas con casilla individual.

Un botón **«Buscar ahora»**: una función que solo se dispara sola no se puede
probar a mano.

En Ajustes › Fuentes: interruptor de la autoalimentación, fecha del último
intento, último error y lista de lo descartado con su motivo.

## Pruebas

Sobre `BaseTemporal` (`tests/apoyo.py`). Ninguna toca la red.

| Archivo | Comprueba |
|---|---|
| `test_catalogo.py` | Cada fuente tiene host en `DOMINIOS`, licencia válida y mazos existentes |
| `test_selector.py` | Elige el mazo flojo; no repite lo ya importado; devuelve `None` cuando no hay nada |
| `test_filtros.py` | Texto bueno, esbozo, lista de enlaces, idioma equivocado, duplicado |
| `test_cosecha.py` | `descargar` sustituido por respuestas grabadas; una fuente caída no tumba a las demás |
| `test_cosecha.py` | `auto_si_toca` cosecha una vez al día, otra al siguiente |
| `test_bandeja.py` | Aceptar crea capítulo y tarjetas; descartar no vuelve a proponer |

Las respuestas grabadas salen de las peticiones reales hechas al comprobar las
fuentes, no inventadas.

## Fuera de alcance

- Feeds RSS/Atom arbitrarios elegidos por el usuario: la lista blanca de
  dominios es lo que hace segura la descarga.
- Traducción automática de material en inglés.
- Descarga de PDF en la cosecha automática. `descargar_pdf()` seguirá siendo
  manual desde la ventana de Fuentes: 100 MB no son una ración diaria.
