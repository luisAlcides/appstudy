# Chispa por capas: de ilustración plana a muñeco articulado

Fecha: 2026-09-09

## El problema

Chispa es una ilustración renderizada: seis celdas de atlas donde manos, pies,
boca y ojos son píxeles cocidos. Hoy se le anima el cuerpo entero (balanceo,
respiración, saltos), la cola, y una deformación local de manos y pies mediante
una malla (`animacion_chispa.py`).

Eso tiene un techo que se alcanzó intentando hacerla parpadear: **detrás del ojo
no hay nada**. Sin píxeles debajo, un párpado solo puede *tapar* el ojo, no
cerrarlo. Se probaron cuatro caminos —comprimir el ojo con la malla, arrastrar
el pelaje de la frente, pintar un párpado de color liso, copiar pelaje de otra
zona— y todos fallan por la misma razón.

La solución es descomponer el dibujo en capas: si el ojo es una capa propia y
detrás hay pelaje reconstruido, cerrarlo deja de ser un truco.

## Lo que ya está verificado

Antes de diseñar se comprobaron las dos piezas de las que depende todo:

**Reconstruir lo que hay detrás.** Quitando los ojos de la pose 0 y rellenando
por difusión desde el borde de la máscara, la cara resultante es limpia y
creíble: pelaje continuo donde estaban los ojos, sin costuras visibles.

**Encontrar las piezas solas.** La paleta de Chispa está muy separada (naranja,
crema, pardo, turquesa, y el blanco y marrón del ojo), y ya vive declarada en
`chispa.py`. Clasificando cada píxel contra esa paleta, los ojos aparecen como
dos manchas grandes en la cara, las manos y los pies en pardo, la punta de la
cola en turquesa y el hocico en crema. Hay ruido en orejas y bordes, corregible
por tamaño y posición de cada grupo conectado.

Esto importa porque el intento anterior falló al medir a ojo: una de las elipses
quedó 22 píxeles desviada y pintaba encima del ojo abierto. Las piezas se buscan,
no se estiman.

## Fases

Un muñeco completo son seis poses por ocho piezas: 48 recortes con su
reconstrucción y su punto de giro. Se entrega en tres fases y **cada una deja a
Chispa funcionando**.

| Fase | Qué entra | Al terminar |
|---|---|---|
| 1 | El extractor, y las capas de **ojos y boca** | Parpadea de verdad y mueve la boca al hablar; brazos y piernas siguen con la malla actual |
| 2 | **Brazos y piernas** como capas con punto de giro | Saludar es un brazo que gira, no una celda del atlas |
| 3 | **Cabeza, orejas y cola** | Inclina la cabeza, mueve las orejas, y la cola se independiza de la pose |

Este documento especifica la fase 1 completa y deja las otras dos esbozadas.
Cada fase tendrá su propio plan de implementación.

## Arquitectura

Cuatro piezas con una responsabilidad cada una.

### `capas_chispa.py` — el extractor

Convierte el atlas en capas. **No se ejecuta al dibujar**: produce archivos.

- `clasificar(r, g, b) -> str` — a qué color de la paleta se parece más un píxel.
- `grupos(sprite) -> list[dict]` — componentes conexos por color, con su caja,
  su centro y su tamaño.
- `piezas(sprite, indice) -> dict[str, mascara]` — asigna grupos a piezas según
  reglas de color, tamaño y posición dentro de la celda.
- `reconstruir(sprite, mascara) -> superficie` — el fondo sin esa pieza, relleno
  por difusión desde el borde y suavizado.
- `extraer(destino) -> dict` — genera todas las capas y el manifiesto.

Reglas de asignación de la fase 1, por celda:

- **Ojos**: grupos clasificados como `ojo` (blanco de la esclerótica y marrón
  del iris), de más de 400 px, en la mitad superior. Se agrupan los que se
  solapan y se toman los dos mayores; si solo aparece uno, esa pose no parpadea.
- **Boca**: grupos `lengua` más el negro contiguo de su contorno, en la mitad
  superior y bajo los ojos. Si no hay lengua visible, la pose no habla.

Las poses 3 y 5 ya tienen los ojos cerrados dibujados: no generan capa de ojo, y
no parpadean.

### El almacén de capas

`~/.local/share/appstudy/chispa/capas/`, con:

- `base-{pose}.png` — la celda sin las piezas extraídas, ya reconstruida.
- `{pose}-{pieza}.png` — cada pieza recortada, con alfa.
- `manifiesto.json` — versión del extractor, huella del atlas y, por pieza:
  caja, centro, punto de giro y orden de dibujo.

No van al repositorio: son derivados de un atlas que ya está, pesan megas, y
regenerarlos cuesta segundos.

### `rig_chispa.py` — el muñeco

Carga el manifiesto y compone. No toca la red ni la base.

- `cargar() -> Rig | None` — `None` si las capas no están o no valen.
- `Rig.dibujar(cr, pose, gestos)` — pinta base y piezas en orden, aplicando a
  cada una su transformación.
- `Rig.parpadeo(cierre)` / `Rig.boca(apertura)` — la transformación de cada
  pieza de la cara.

**El parpadeo**: la capa del ojo se recorta contra un párpado que baja —una
curva que cruza la caja del ojo—, y lo que queda descubierto es la base, que ya
es pelaje. La pestaña se pinta en el filo del párpado con el tono oscuro del
contorno del ojo, tomado del propio dibujo.

**La boca**: la capa se escala en vertical desde su borde superior, que es como
se abre una boca. Al cerrarse del todo, la base muestra el hocico.

### El enganche y el respaldo

`Chispa._personaje` pide el rig. Si está, dibuja con él; si no, hace lo que hace
hoy: la malla sobre el atlas plano. Un fallo de extracción nunca deja a la
mascota sin dibujar.

La extracción se lanza **en segundo plano al primer arranque**, con
`util.hilo(..., largo=True)`, y se rehace cuando cambia la versión del extractor
o la huella del atlas. Mientras no termina, se usa el respaldo. Igual que la
cosecha diaria y el respaldo automático: si falla, se estudia igual.

## Errores

| Qué puede fallar | Qué pasa |
|---|---|
| El atlas no está | Ya hoy se cae al dibujo vectorial; no cambia |
| La extracción falla o no encuentra ojos | Se anota en `meta`, y se usa la malla actual |
| El manifiesto es de otra versión | Se regenera en segundo plano |
| Falta un PNG de capa | El rig se declara inválido y se usa el respaldo |
| No se puede escribir en el disco | Se usa el respaldo, sin avisar por pantalla |

## Pruebas

Sobre `BaseTemporal`, sin red. Las que necesitan el atlas se saltan si no está,
como ya hace `test_animacion_chispa.py`.

| Archivo | Comprueba |
|---|---|
| `test_capas_chispa.py` | `clasificar` acierta los colores de la paleta; los grupos de un atlas sintético salen donde deben |
| `test_capas_chispa.py` | En la pose 0 se encuentran **dos** ojos, en la mitad superior y separados en horizontal |
| `test_capas_chispa.py` | La base reconstruida no conserva ningún píxel clasificado como `ojo` dentro de la máscara |
| `test_capas_chispa.py` | Las poses 3 y 5 no generan capa de ojos |
| `test_rig_chispa.py` | Sin capas, `cargar()` devuelve `None` y no lanza |
| `test_rig_chispa.py` | Con cierre 0 el resultado es idéntico al atlas; con cierre 1 no queda blanco de ojo a la vista |
| `test_rig_chispa.py` | La boca cerrada no deja lengua visible |
| `test_chispa.py` | Sin rig, se dibuja como hoy: el respaldo sigue intacto |

La comprobación de «no queda blanco de ojo» se hace contando píxeles
clasificados, que es medible, en vez de comparar imágenes a ojo.

## Fuera de alcance

- **Bit no se toca.** Es vectorial y ya mueve cada parte.
- **No se generan celdas nuevas de atlas.** Se trabaja con las seis que hay.
- **Las capas no se editan a mano.** Salen del extractor y se regeneran; si una
  pieza sale mal, se corrige la regla, no el PNG.
- Fases 2 y 3, que tendrán su propio spec cuando llegue su turno.
