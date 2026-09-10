# Chispa: poses para AppStudy

Recurso: `chispa-poses.png`, generado con la herramienta integrada ImageGen a
partir de la referencia aportada por el usuario. Sin llamadas de red en ejecución.

Atlas de 1536 × 1024, tres columnas y dos filas: reposo, saludo, trabajo,
celebración, curiosidad y descanso. El motor compone el fondo magenta como
transparencia al cargar; también admite un atlas PNG con alfa nativo.
No cambiar el orden ni los márgenes de las celdas sin revisar los anclajes de
accesorios en `chispa.py`. La ilustración conserva la cola en cada pose;
las animaciones corporales y las partículas proceden del motor compartido.
`animacion_chispa.py` anima manos y pies con una malla local continua durante
el dibujo, conservando el atlas original y sin añadir dependencias. También
aporta movimiento local de boca y mirada, y párpados dibujados sobre los ojos.
El ritmo de boca sigue el estado y la duración del habla, no los fonemas del
audio.

Prompt final (herramienta integrada, edición del atlas generado):

> Change only the background of this sprite atlas to perfectly flat solid pure
> magenta RGB(255,0,255), hex #FF00FF, for chroma-key rendering in a desktop app.
> Remove every single checkerboard square and replace with uniform #FF00FF.
> Preserve the six fox characters and their exact positions, scale, colors,
> fur, and 3 by 2 equal grid layout on 1536x1024 canvas. No shadows, no gradients
> in background, no checkerboard, no text. Uniform pure magenta in all empty
> spaces and between limbs. Do not change the character designs.

## Es también la fuente de las capas

`capas_chispa.py` extrae de este atlas los ojos de cada pose y reconstruye el
pelaje de detrás, para que Chispa pueda parpadear. Si se cambia el atlas, las
capas se regeneran solas: el manifiesto guarda su huella. Cambiar el orden de
las celdas sí obliga a revisar `SIN_OJOS` en `capas_chispa.py`, que declara qué
poses vienen ya con los ojos cerrados.

Corrección del habla: se conserva el atlas sin usar las capas segmentadas
automáticamente, que producían bordes rotos. La deformación de boca se limita
a su zona inferior y a una amplitud pequeña; ojos y nariz quedan intactos.
