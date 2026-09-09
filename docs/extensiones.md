# Extensiones y fuentes de AppStudy

Abre **Biblioteca → Fuentes** o **Ajustes → Avanzado → Extensiones y fuentes**.
Las integraciones incluidas no requieren instalar plugins de terceros.

## Fuentes incluidas

- **Wikipedia:** búsqueda en español o inglés. Cambia `idioma` a `es` o `en` en la configuración de la extensión.
- **OpenStax:** catálogo seleccionado de libros en español e inglés, con navegación entre capítulos. También admite pegar una URL HTTPS de OpenStax. Los PDF se descargan a Biblioteca.
- **MIT OpenCourseWare:** catálogo seleccionado de cursos y sus materiales: apuntes, ejercicios y PDF. Admite URLs de otros cursos de MIT OCW.
- **Carpetas Markdown:** elige una carpeta en la configuración. La lista indica documentos nuevos, modificados o sin cambios. Mientras la ventana permanece abierta y esta fuente está seleccionada, se actualiza cada minuto. No modifica tus archivos ni importa cambios sin que elijas hacerlo. La exploración está limitada a 1.000 documentos y 100 MB por revisión.

Una vista previa muestra autor, dirección y licencia. Puedes guardar la lectura completa, seleccionar un fragmento o pedir cinco tarjetas a la IA y revisarlas antes de guardarlas. Volver a importar el mismo origen y mazo actualiza la lectura conservando su progreso. Dos documentos con el mismo título y distinto origen son independientes.

Los catálogos de OpenStax y MIT son selecciones iniciales, no buscadores de todo su contenido. Usa una URL de la institución para agregar otro material. No se importan credenciales ni se eluden accesos a cursos privados.

Las lecturas guardadas conservan la atribución. Los PDF descargados incluyen un archivo `.source.json` con su procedencia. Verifica la licencia de la edición y las excepciones de cada material antes de redistribuirlo.

## Fuentes del catálogo automático

Las usa la autoalimentación diaria (ver **Contenido que llega solo** en el
README) y también se pueden buscar a mano desde **Explorar fuentes**. Todas
declaran el permiso `network` y se apagan una a una con su interruptor.

| Identificador | Fuente | Cómo se recorre | Licencia |
|---|---|---|---|
| `wikipedia_es` · `wikipedia_en` · `wikipedia_simple` | Wikipedia | búsqueda | abierta |
| `wikibooks_es` · `wikiversity_es` · `wiktionary_en` | Wikimedia | búsqueda | abierta |
| `archwiki` · `gentoo` | Wikis de Linux | búsqueda | solo enlace |
| `arxiv` | arXiv | búsqueda | solo enlace |
| `mdn` | MDN Web Docs | búsqueda | solo enlace |
| `gutenberg` | Project Gutenberg | búsqueda | abierta |
| `libretexts_workforce` · `libretexts_esp` · `libretexts_eng` | LibreTexts | sitemap | abierta |
| `man7` | Páginas de manual | índice | solo enlace |
| `tldp` · `pydocs` · `pandas` · `sklearn` · `huggingface` | Documentación | índice | abierta |
| `ibiblio` | *Lessons In Electric Circuits* | índice | abierta |
| `voa` · `saylor` | Cursos abiertos | índice | abierta |
| `openstax` · `mit` | Catálogos seleccionados | catálogo | abierta |

De una fuente **abierta** se guarda el capítulo entero con su atribución. De una
**solo enlace** se guarda título, resumen y dirección, no se descarga la página
y no se generan tarjetas automáticas.

Los índices y sitemaps se guardan un mes en `~/.local/share/appstudy/fuentes/indices/`.
Si la descarga falla y hay copia, se usa la copia. El sitemap de LibreTexts pasa
de tres megas, así que no se pide en cada arranque.

## Herramientas

**OCR e indexación:** selecciona un PDF, EPUB, Markdown, texto o imagen. Para PDF elige el rango (máximo 50 páginas por operación). El texto de los PDF conserva el número de página; los demás formatos conservan el número de fragmento. Para documentos escaneados usa la opción OCR.

Dependencias opcionales en sistemas Debian/Ubuntu:

```bash
sudo apt install tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng poppler-utils
```

**Preguntarle a Bit sobre documentos:** primero indexa archivos o importa lecturas desde Fuentes. La búsqueda de fragmentos funciona sin IA. Con la IA local activada, Bit responde con referencias y citas que se cotejan con el texto indexado. Si las citas no existen en los fragmentos, la respuesta se rechaza. Esto comprueba la procedencia de las citas, no garantiza que toda interpretación del modelo sea correcta. El índice se guarda en tu base local y se puede retirar sin borrar los documentos originales. Puedes indexar un PDF en varios rangos: se conservan las páginas anteriores y se actualizan las que vuelves a seleccionar.

**Subtítulos:** importa SRT/VTT. Se proponen tarjetas de huecos para practicar inglés; cada pista conserva el título y el minuto de la frase. No se descarga el video ni se necesita IA para crear estos ejercicios.

**Anki multimedia:** importa APKG con colección SQLite y mapa multimedia JSON (exportación compatible con versiones anteriores). Conserva las imágenes y los audios referenciados en los dos primeros campos. Las imágenes se muestran y el audio se reproduce con controles en el popup. Se admiten PNG/JPEG/GIF/WebP y MP3/Ogg/FLAC/WAV; no se ejecuta el HTML del mazo. Máximo 12 MB por recurso y 100 MB de adjuntos por importación. Las plantillas y los complementos propios de Anki no se ejecutan; las exportaciones modernas con mapa multimedia binario deben volver a exportarse en formato compatible.

**Exportación:** elige un mazo o todos. JSON y ZIP conservan tipos, opciones, nivel, pistas, etiquetas y adjuntos. CSV/TSV son formatos de texto y no conservan multimedia ni todos los tipos; se neutralizan celdas que podrían ejecutarse como fórmulas en una hoja de cálculo. JSON puede volver a importarse con el importador de tarjetas. ZIP se instala como paquete de contenido y permite elegir el mazo de destino.

Los respaldos SQLite incluyen el índice y los adjuntos. La sincronización incluye los adjuntos de las tarjetas propias; siguen aplicando los límites de tamaño de la carpeta y de Supabase. Los PDF originales, plugins instalados, su configuración de confianza y el índice documental no se copian automáticamente a otros equipos. Las lecturas importadas sí se sincronizan como capítulos propios.

## Instalar paquetes y plugins

En **Extensiones → Instalar paquete ZIP o plugin**, elige un ZIP y revisa nombre, versión, tipo y permisos. Se instala desactivado. Las extensiones incluidas también se pueden activar o desactivar.

- Un paquete `content` contiene JSON, Markdown y recursos. No puede incluir código ejecutable ni pedir permisos.
- Un plugin `source` ejecuta Python en otro proceso. Declara sus permisos y requiere que actives explícitamente esa versión. Los permisos son informativos: **el proceso no está aislado de los archivos o la red del usuario**. Instala y activa solo código que conozcas.
- La instalación rechaza rutas de escape, enlaces simbólicos, entradas duplicadas, paquetes demasiado grandes y versiones incompatibles. Nunca ejecuta el código al instalar.
- No se sobrescribe una versión instalada. Para actualizar, sube el número de versión; una versión nueva empieza desactivada y conserva la configuración anterior.

Los archivos instalados viven en `~/.local/share/appstudy/extensiones/<id>/<version>/` (o en `XDG_DATA_HOME`). Desactivar una extensión conserva el material que ya importaste.

## Crear un paquete de contenido

Estructura:

```text
mi-curso/
  manifest.json
  content.json
  lecturas/tema.md
  media/imagen.png
```

`manifest.json`:

```json
{
  "id": "mi-curso",
  "name": "Mi curso",
  "version": "1.0.0",
  "api_version": 1,
  "type": "content",
  "permissions": [],
  "content": "content.json"
}
```

`content.json` usa `format: 1`, una lista `documents` y una lista `cards`. Cada documento lleva `origin`, `title`, `author`, `license` y `text` o `path` a un Markdown UTF-8 del paquete. Cada tarjeta lleva `front`, `back`, `kind`, `tags`, `level`; las de opción múltiple incluyen `choices` y `answer` (índice desde cero). Los adjuntos van en `media`, con `side` (`front` o `back`), `name` y `path` relativo al paquete; también se acepta `data` codificado en base64.

Hay dos ejemplos completos en `examples/extensiones/`. Para generar sus ZIP:

```bash
python3 -m appstudy.extensiones examples/extensiones/curso-ejemplo /tmp/curso-ejemplo.zip
python3 -m appstudy.extensiones examples/extensiones/fuente-ejemplo /tmp/fuente-ejemplo.zip
```

## API de plugins de fuentes, versión 1

Usa `type: "source"`, `entrypoint: "source.py"` y declara `execute_python`; añade `network` o `read_files` si corresponde. El proceso recibe una petición JSON por stdin y debe escribir una sola respuesta JSON por stdout. Los mensajes de diagnóstico van a stderr. Tiene 30 segundos y 4 MB de salida; se cierran también sus procesos auxiliares al terminar.

Petición de búsqueda:

```json
{"api_version":1,"operation":"search","payload":{"query":"linux"},"config":{}}
```

Devuelve una lista de hasta 150 documentos con `origin`, `title`, `text` (puede estar vacío), y opcionalmente `summary`, `author`, `license`. `origin` debe identificar de forma estable el recurso.

Para `preview`, `payload` contiene el documento seleccionado y la respuesta es el documento completo, con su `text`. La importación la hace AppStudy después de la revisión del usuario; el plugin no necesita acceder a SQLite. La configuración editable en la interfaz se entrega en `config` y persiste localmente. No uses stdout para mensajes de depuración.

## Verificación

```bash
./pruebas.sh fuentes_extensiones    # pruebas sin red con base temporal
./pruebas.sh fuentes_ui            # widgets GTK; necesita pantalla
python3 -m tests.verificar_fuentes_online  # consulta los tres proveedores reales
```
