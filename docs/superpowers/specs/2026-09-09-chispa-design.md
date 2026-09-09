# Chispa: una segunda mascota, elegible desde Ajustes

## El problema

`Creature`, en `appstudy/pet.py`, mezcla dos cosas que no tienen por qué vivir
juntas: el **motor** (reloj de fotogramas, gestos, pose, partículas, mirada,
cachés de superficie) y la **piel** de Bit (unas 900 líneas de Cairo: el
estallido de once rayos, el mochi crema, la cara, los accesorios). Mientras
sigan fundidas, una segunda mascota obliga a duplicar el motor entero o a
llenar el dibujo de condicionales.

Se quiere a **Chispa**, un zorro naranja de cola turquesa, con la misma vida que
Bit —respira, parpadea, salta, sigue al ratón—, y un ajuste para elegir cuál
sale al escritorio.

## Arquitectura

Tres módulos donde hoy hay uno:

- **`appstudy/criatura.py`** — el motor, `class Creature(Gtk.DrawingArea)`. No
  sabe nada de zorros ni de mochis. Aporta el reloj, `_pose`, los gestos, las
  partículas, la barra de energía y la **orquestación de `draw`**; el dibujo
  concreto lo delega en ganchos que la piel rellena.
- **`appstudy/bit.py`** — `class Bit(Creature)`: paleta crema/terracota, el
  estallido de once rayos, la silueta de mochi y su insignia.
- **`appstudy/chispa.py`** — `class Chispa(Creature)`: paleta naranja/turquesa,
  la cola, las orejas, el hocico y el rombo de la frente.

`pet.py` se queda con `PetWindow` y la lógica de estudio, más la fábrica que
elige la piel. Baja de 4466 a unas 3000 líneas.

### Qué sube al motor y qué baja a la piel

La cara, los brazos y los pies **son del motor**, parametrizados por constantes
de clase. Las dos mascotas tienen ojos con iris y dos brillos, cejas que se
inclinan con el ánimo, boca que reacciona a doce gestos y extremidades que
alternan con el balanceo: duplicar eso serían 400 líneas repetidas y dos sitios
donde arreglar cada error. Lo que cambia entre pieles son números y colores
(`OJO_DX`, `BOCA_Y`, `PELAJE`, `PELAJE_SOMBRA`…), no la lógica.

La piel aporta solo lo que de verdad difiere, mediante estos ganchos:

| Gancho | Bit | Chispa |
|---|---|---|
| `_capa_fondo(cr, color)` | el estallido de once rayos | la cola, meneándose |
| `_tras_fondo(cr, color)` | nada | las orejas |
| `_forma(cr, rx, ry)` | silueta de mochi | silueta de pera |
| `_marca(cr, color)` | la insignia de luz | el rombo de la frente |
| `_rasgos_previos(cr, color)` | nada | el hocico |
| `_accesorio(cr, color)` | pañuelo, gafas, corona | los mismos, con sus offsets |

Las constantes de piel (`NOMBRE`, `DISENO`, `ANCHO`, `ALTO_PET`, `MOODS`,
`TINTA`, `CARA_ESCALA`, `CARA_BAJA`, `RX`/`RY`, la paleta de pelaje) pasan de
constantes de módulo a atributos de clase.

`angulo_estrella` se llama `giro_fondo`: el motor no debe hablar de estrellas.

### Cómo se ve Chispa

Pelaje naranja con degradado, pecho y hocico crema, orejas grandes de interior
crema y punta oscura, patas marrón oscuro, cola ancha con la punta turquesa y un
rombo turquesa en la frente.

**El pelaje naranja no cambia nunca.** Lo que se tiñe con el ánimo es el rombo,
la punta de la cola y los cachetes, igual que el asterisco de Bit. La paleta
propia usa turquesa como «normal», y verde, ámbar, granate y gris para feliz,
hambre, triste y dormido.

La cola se guarda en caché como el estallido: es la pieza cara del fotograma y
solo cambia con el color, la fase de meneo y el abandono.

## El ajuste

- Meta nuevo `pet_mascota`, `"bit"` o `"chispa"`, por `db.get_meta`/`set_meta`.
- `Adw.ComboRow` «Mascota» como primera fila de Ajustes › Apariencia y progreso.
  Las filas de abajo («Tamaño de…», «Accesorio de…», «Evolución de…») se
  retitulan con el nombre elegido.
- **Cambio en caliente**: el proceso `--pet` ya relee metas cada 15 s en
  `on_check`. Si `pet_mascota` cambió, sustituye el widget criatura dentro de su
  contenedor conservando posición, escala, accesorio y ánimo. Sin reiniciar.
- Entrada equivalente en el menú de clic derecho de la mascota.

Los accesorios y la evolución son **compartidos**: cambiar de mascota no pierde
progreso, y `total_repasos` sigue contando lo mismo.

## Nombre y voz

`pet.NOMBRE` deja de ser constante y pasa a `pet.nombre(con)`. Los títulos
(«Chispa dice», «Soltar a Chispa», «Chispa te echa de menos») se resuelven en
ejecución, no al importar el módulo.

La palabra clave de voz acepta **siempre las dos**, `bit` y `chispa`, con sus
confusiones fonéticas. Conmutarla obligaría a cambiar de costumbre al dictar y
dejaría a quien se equivoca sin forma de despertar a la mascota; aceptar ambas
no cuesta estado y no falla nunca.

## Pruebas

- **Huella de regresión**: el dibujo de Bit debe salir idéntico pixel a pixel
  tras el refactor. Se compara el SHA-256 de todos los ánimos × accesorios ×
  gestos × género × abandono contra la base tomada antes de mover nada
  (`4c622de9dd28f32e04047d88791a0f78224c8f9721defbd34db582a714276f7f`).
- `tests/test_chispa.py`: paleta completa por ánimo, la fábrica eligiendo clase
  según el meta, el nombre según el meta, y un render de cada ánimo y accesorio
  sobre un `ImageSurface` sin display.
- `tests/test_animacion_bit.py`: el arnés `BitSinVentana` se parametriza con la
  clase de piel para que Chispa reuse las mismas pruebas de animación.
- La palabra clave sigue reconociendo «bit» y ahora también «chispa»
  (`tests/test_voz_rec.py`).
