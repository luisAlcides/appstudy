"""«¿Sabías que…?»: cultura general que Bit suelta y, si quieres, te guarda.

Un dato suelto entretiene y se olvida en diez minutos. Lo que hace culto a
alguien no es haberlo leído, es acordarse de ello tres meses después y poder
contarlo. Por eso cada dato trae dos cosas —el hecho y el porqué, que es lo que
lo hace contable— y un botón para convertirlo en tarjeta: en cuanto entra en el
mazo, el repaso espaciado se encarga de que siga ahí.

Los datos están escritos a mano y elegidos por ser comprobables. Hay una
categoría entera, «Lo que crees y no es», dedicada a desmontar las cosas que
todo el mundo repite y son falsas: quitar un error de la cabeza vale tanto como
meter un dato nuevo.
"""
import random

from . import db

DECK_CULTURA = "cultura"

# (dato, categoría, por qué importa)
DATOS = [
    # ---------------------------------------------------------------- Historia
    ("La Universidad de Oxford es más antigua que el Imperio azteca. En Oxford ya "
     "se daban clases en 1096; Tenochtitlan se fundó en 1325.",
     "Historia",
     "Las líneas de tiempo que aprendemos por separado engañan: cosas que "
     "parecen de épocas distintas se solapan."),
    ("Cleopatra vivió más cerca en el tiempo del primer alunizaje que de la "
     "construcción de la Gran Pirámide de Guiza.",
     "Historia",
     "La pirámide es de hacia 2560 a. C. y Cleopatra murió en el 30 a. C.: el "
     "Antiguo Egipto ya era antiguo para los propios egipcios."),
    ("El fax se inventó antes que el teléfono. Alexander Bain patentó su "
     "«telégrafo de imágenes» en 1843; el teléfono de Bell es de 1876.",
     "Historia",
     "La tecnología no avanza en línea recta: hay inventos que llegan décadas "
     "antes de que exista el mundo que los aproveche."),
    ("La guerra más corta de la historia duró unos 38 minutos: la anglo-zanzibarí "
     "del 27 de agosto de 1896.",
     "Historia",
     "Sirve para calibrar: no toda guerra es una campaña de años."),
    ("El Imperio romano de Oriente, con capital en Constantinopla, sobrevivió "
     "casi mil años a la caída de Roma: cayó en 1453, el mismo siglo que "
     "Colón cruzó el Atlántico.",
     "Historia",
     "«La caída del Imperio romano» en 476 solo cuenta la mitad occidental."),

    # ----------------------------------------------------------------- Ciencia
    ("El vidrio de las ventanas no es un líquido que fluya con los siglos. Los "
     "vidrios de las catedrales son más gruesos abajo por cómo se fabricaban, "
     "no porque hayan escurrido.",
     "Ciencia",
     "Es el ejemplo clásico de explicación bonita que se repite sin comprobar."),
    ("El agua caliente puede congelarse antes que la fría en ciertas "
     "condiciones. Se llama efecto Mpemba y aún se discute por qué ocurre.",
     "Ciencia",
     "Que un fenómeno sea observable no significa que esté explicado."),
    ("Un solo rayo calienta el aire a su alrededor hasta unos 30 000 °C, cinco "
     "veces la temperatura de la superficie del Sol.",
     "Ciencia",
     "El trueno es ese aire expandiéndose de golpe: primero la luz, luego el ruido."),
    ("El helio se descubrió en el Sol antes que en la Tierra, analizando la luz "
     "de un eclipse en 1868. De ahí su nombre, de «Helios».",
     "Ciencia",
     "La espectroscopía permite saber de qué está hecho algo sin tocarlo: así "
     "sabemos la composición de estrellas a las que jamás iremos."),
    ("Los átomos son casi todo vacío. Si el núcleo de un átomo fuera una canica "
     "en el centro de un estadio, los electrones andarían por las gradas.",
     "Ciencia",
     "Lo que impide que atravieses una silla no es la materia, son las fuerzas "
     "eléctricas entre electrones."),

    # ----------------------------------------------------------- Cuerpo humano
    ("El estómago segrega ácido clorhídrico capaz de disolver metal, y no se "
     "digiere a sí mismo porque renueva su capa de mucosa cada pocos días.",
     "Cuerpo humano",
     "Muchas úlceras son un fallo de esa protección, no un exceso de ácido."),
    ("Los huesos son más resistentes a la compresión que el hormigón, peso por "
     "peso, y además se reparan solos.",
     "Cuerpo humano",
     "El hueso no es una piedra: es tejido vivo que se remodela según la carga "
     "que soporta, y por eso el ejercicio lo fortalece."),
    ("Tienes más células bacterianas conviviendo contigo de las que crees: la "
     "proporción con tus propias células ronda el uno a uno.",
     "Cuerpo humano",
     "La cifra famosa de «diez bacterias por cada célula» venía de una "
     "estimación de 1972 hecha a ojo, y se corrigió en 2016."),
    ("El corazón late unas 100 000 veces al día sin que se lo mandes: tiene su "
     "propio marcapasos, el nódulo sinusal.",
     "Cuerpo humano",
     "Un corazón trasplantado late aunque le hayan cortado los nervios."),

    # ------------------------------------------------------------------ Lengua
    ("«Ojalá» viene del árabe «law šāʾ Allāh», ojalá quiera Dios. El español "
     "tiene unas cuatro mil palabras de origen árabe.",
     "Lengua",
     "Casi todas las que empiezan por «al-» —almohada, alcalde, algodón, "
     "álgebra— vienen de ahí."),
    ("«Salario» viene de sal: parte de la paga de los soldados romanos se "
     "entregaba en sal o en dinero para comprarla.",
     "Lengua",
     "La sal era el único conservante fiable de la carne, y por eso valía tanto."),
    ("El español es la segunda lengua del mundo por hablantes nativos, por "
     "detrás del chino mandarín y por delante del inglés.",
     "Lengua",
     "El inglés gana de largo cuando se cuentan los que lo hablan como segunda "
     "lengua: son cosas distintas."),
    ("La palabra más larga del castellano recogida por la RAE es "
     "«electroencefalografista».",
     "Lengua",
     "Las palabras kilométricas de las listas de internet casi siempre son "
     "inventos que ningún diccionario recoge."),

    # -------------------------------------------------------------------- Arte
    ("La Mona Lisa no fue famosa hasta que la robaron en 1911. El ladrón, un "
     "empleado del Louvre, la tuvo dos años escondida.",
     "Arte",
     "Buena parte de la fama de una obra es su historia, no solo su calidad."),
    ("Van Gogh vendió muy pocos cuadros en vida y pintó los más conocidos en sus "
     "últimos dos años y medio.",
     "Arte",
     "«Los girasoles» y «La noche estrellada» salieron de una etapa de enfermedad "
     "y encierro, no de una vida de éxito."),
    ("Las estatuas griegas y romanas estaban pintadas de colores vivos. El mármol "
     "blanco que admiramos es pintura perdida por el tiempo.",
     "Arte",
     "El «clasicismo blanco» que copió Occidente durante siglos es un malentendido "
     "arqueológico."),

    # --------------------------------------------------------------- Geografía
    ("Rusia abarca once husos horarios: cuando amanece en un extremo, en el otro "
     "es de noche del día siguiente.",
     "Geografía",
     "Ayuda a entender por qué un país así se gobierna distinto a uno pequeño."),
    ("África es tan grande que dentro caben Estados Unidos, China, India y buena "
     "parte de Europa a la vez.",
     "Geografía",
     "El mapa que ves en la pared, la proyección de Mercator, agranda lo que está "
     "cerca de los polos y encoge lo tropical."),
    ("El desierto más grande del mundo no es el Sáhara, es la Antártida: desierto "
     "es donde casi no llueve, no donde hace calor.",
     "Geografía",
     "Las definiciones importan más que la intuición al clasificar."),
    ("El punto más profundo del océano, la fosa de las Marianas, es más hondo que "
     "alto es el Everest.",
     "Geografía",
     "Casi once kilómetros hacia abajo frente a poco menos de nueve hacia arriba."),

    # -------------------------------------------------------------- Tecnología
    ("El primer «bug» informático documentado fue literalmente un bicho: una "
     "polilla atascada en un relé del Harvard Mark II, en 1947.",
     "Tecnología",
     "El equipo la pegó con cinta en el cuaderno de incidencias, y ahí sigue."),
    ("La primera programadora fue Ada Lovelace, en 1843, casi un siglo antes de "
     "que existiera un ordenador donde ejecutar su algoritmo.",
     "Tecnología",
     "Fue la primera en ver que una máquina de calcular podía manipular "
     "símbolos, y no solo números."),
    ("El correo electrónico es más antiguo que la web. El primer correo entre "
     "máquinas es de 1971; la web, de 1989.",
     "Tecnología",
     "Internet y la web no son lo mismo: la web es una aplicación que corre "
     "sobre internet, como el correo."),
    ("El GPS tiene que corregir los efectos de la relatividad: sin ajustar los "
     "relojes de los satélites, acumularía un error de kilómetros al día.",
     "Tecnología",
     "La relatividad no es solo teoría de pizarra: la usas al abrir el mapa."),

    # ------------------------------------------------------------- Matemáticas
    ("En un grupo de 23 personas hay más de un 50 % de posibilidades de que dos "
     "cumplan años el mismo día.",
     "Matemáticas",
     "Es la paradoja del cumpleaños: no comparas tu fecha con las demás, sino "
     "todas las parejas posibles, que son 253."),
    ("Hay infinitos números que no se pueden escribir como fracción, y son "
     "«más» que los que sí: los irracionales son un infinito mayor.",
     "Matemáticas",
     "Cantor demostró que hay infinitos de distinto tamaño, y eso le costó el "
     "desprecio de media comunidad matemática de su tiempo."),
    ("Un folio doblado 42 veces sobre sí mismo llegaría a la Luna, si se pudiera "
     "doblar tantas veces.",
     "Matemáticas",
     "El crecimiento exponencial es imposible de intuir: por eso nos sorprenden "
     "las epidemias y el interés compuesto."),

    # ---------------------------------------------------------------- Economía
    ("El interés compuesto hace que 100 euros al 7 % anual se conviertan en unos "
     "200 en diez años, sin tocar nada.",
     "Economía",
     "La regla del 72: divide 72 entre el interés y sabes en cuántos años se "
     "duplica el dinero."),
    ("La hiperinflación alemana de 1923 llegó a tal punto que el papel moneda "
     "salía más barato que el papel pintado, y se usaba para empapelar paredes.",
     "Economía",
     "El dinero vale lo que la gente cree que vale; cuando esa creencia cae, cae "
     "de golpe."),

    # ---------------------------------------------------------------- Historia natural
    ("Los pulpos tienen tres corazones y sangre azul, porque transportan el "
     "oxígeno con cobre en vez de hierro.",
     "Naturaleza",
     "Dos corazones bombean a las branquias y uno al resto del cuerpo; ese se "
     "para cuando el pulpo nada, y por eso prefiere caminar."),
    ("Los árboles de un bosque intercambian nutrientes y señales a través de "
     "redes de hongos conectadas a sus raíces.",
     "Naturaleza",
     "Un bosque se parece más a una red que a un montón de individuos que "
     "compiten por la luz."),
    ("Las abejas comunican dónde hay comida con una danza: la dirección respecto "
     "al Sol y la duración del meneo indican rumbo y distancia.",
     "Naturaleza",
     "Karl von Frisch lo descifró y le valió un Nobel: es lenguaje simbólico en "
     "un animal con un cerebro de un miligramo."),

    # -------------------------------------------------------------- Astronomía
    ("Un día en Venus dura más que su año: tarda más en girar sobre sí mismo que "
     "en dar la vuelta al Sol.",
     "Astronomía",
     "Además gira al revés que casi todos los planetas: allí el Sol saldría "
     "por el oeste."),
    ("La luz del Sol que te da ahora salió de él hace unos ocho minutos, pero "
     "tardó decenas de miles de años en salir de su interior.",
     "Astronomía",
     "El fotón rebota tantas veces dentro del Sol que el viaje interior dura "
     "más que la carrera hasta la Tierra."),
    ("Hay más estrellas en el universo observable que granos de arena en todas "
     "las playas de la Tierra.",
     "Astronomía",
     "Y en casi todas ellas hay planetas: los descubiertos ya se cuentan por "
     "miles."),

    # -------------------------------------------------------------- Filosofía
    ("Sócrates no escribió nada. Todo lo que sabemos de él nos llega por "
     "Platón, Jenofonte y Aristófanes, que no coinciden entre sí.",
     "Filosofía",
     "La figura más influyente del pensamiento occidental es, en parte, un "
     "personaje literario."),
    ("La navaja de Ockham no dice que la explicación simple sea la verdadera, "
     "sino que no hay que multiplicar entidades sin necesidad.",
     "Filosofía",
     "Es un criterio para elegir entre explicaciones que ya funcionan igual de "
     "bien, no una excusa para simplificar de más."),

    # ------------------------------------------------------------------ Música
    ("El «la» de referencia de las orquestas, a 440 Hz, no se acordó "
     "internacionalmente hasta el siglo XX. Antes cada ciudad afinaba distinto.",
     "Música",
     "La música antigua sonaba más grave de como la oímos hoy."),
    ("El silencio absoluto no existe en música: la pieza 4'33'' de John Cage "
     "consiste en no tocar, para que se oiga la sala.",
     "Música",
     "Obligó a preguntarse dónde acaba la música y empieza el ruido."),

    # ------------------------------------------------------- Lo que crees y no es
    ("La Gran Muralla china no se ve a simple vista desde el espacio. Es larga, "
     "pero muy estrecha y del color del terreno.",
     "Lo que crees y no es",
     "Los propios astronautas lo han desmentido; se repite desde antes de que "
     "hubiera vuelos espaciales."),
    ("No usamos solo el 10 % del cerebro. Las imágenes cerebrales muestran "
     "actividad en prácticamente todas las regiones a lo largo del día.",
     "Lo que crees y no es",
     "El mito es tan cómodo que lo venden libros de autoayuda y películas."),
    ("La lengua no tiene zonas separadas para cada sabor. El mapa de la lengua "
     "viene de una mala traducción de un estudio alemán de 1901.",
     "Lo que crees y no es",
     "Todos los sabores se detectan en toda la lengua, con pequeñas diferencias "
     "de sensibilidad."),
    ("Napoleón no era bajo: medía en torno a 1,68 m, la media francesa de su "
     "época. La confusión viene de las pulgadas francesas, más largas.",
     "Lo que crees y no es",
     "La propaganda británica hizo el resto."),
    ("Los camaleones no cambian de color para camuflarse, sino sobre todo para "
     "regular su temperatura y comunicarse.",
     "Lo que crees y no es",
     "El color dice más de su estado de ánimo que del fondo donde están."),
    ("Un rayo sí cae dos veces en el mismo sitio. El Empire State recibe "
     "decenas de impactos al año.",
     "Lo que crees y no es",
     "Los pararrayos existen precisamente porque el rayo prefiere ciertos sitios."),

    # --------------------------------------------------- Historia (más)
    ("Los vikingos llegaron a América unos quinientos años antes que Colón. En "
     "L'Anse aux Meadows, en Canadá, quedan los restos de su asentamiento.",
     "Historia",
     "Llegar no es lo mismo que cambiar el mundo: el viaje de Colón tuvo "
     "consecuencias porque detrás vino todo un imperio."),
    ("Las pirámides de Egipto no las levantaron esclavos. Se han excavado las "
     "aldeas de los obreros, con panaderías, hospitales y registros de pagos.",
     "Historia",
     "La idea de los esclavos viene de la Biblia y de Hollywood, no de la "
     "arqueología."),
    ("La Guerra de los Cien Años duró ciento dieciséis, y no fue una guerra "
     "continua sino una serie de campañas con largas treguas.",
     "Historia",
     "Los nombres de los periodos históricos los ponen después, y casi nunca "
     "los que los vivieron."),
    ("La peste negra mató a un tercio de Europa y, al hacerlo, subió los "
     "salarios de los que sobrevivieron.",
     "Historia",
     "Al faltar brazos, el trabajo se encareció: fue una de las grietas por las "
     "que se coló el fin de la servidumbre."),
    ("El Titanic llevaba botes salvavidas para menos de la mitad del pasaje, y "
     "aun así cumplía la ley: la normativa los calculaba por el tonelaje del "
     "barco, no por la gente que iba dentro.",
     "Historia",
     "Muchas catástrofes no son un fallo de la norma, son la norma bien "
     "aplicada a un mundo que ya cambió."),
    ("En Corea se imprimía con tipos móviles de metal antes que Gutenberg: el "
     "Jikji es de 1377, unos ochenta años anterior a la Biblia de Gutenberg.",
     "Historia",
     "Lo que cambió Europa no fue solo la imprenta, fue la imprenta con un "
     "alfabeto corto, papel barato y ganas de discutir de religión."),
    ("El Coliseo tenía un toldo gigante, el velarium, que desplegaban marineros "
     "de la flota imperial traídos para eso.",
     "Historia",
     "Manejar aquella lona era cosa de gente acostumbrada a velas y cabos."),
    ("La Biblioteca de Alejandría no ardió en una sola noche: se fue apagando "
     "durante siglos por recortes, guerras y abandono.",
     "Historia",
     "El relato del gran incendio es más cómodo que la verdad, que es que el "
     "conocimiento se pierde por desidia y poco a poco."),

    # ----------------------------------------------------- Ciencia (más)
    ("El diamante y la mina de tu lápiz son el mismo elemento, carbono. Solo "
     "cambia cómo están colocados sus átomos.",
     "Ciencia",
     "La estructura importa tanto como el material: lo mismo, ordenado de otra "
     "forma, es lo más duro o lo más resbaladizo."),
    ("La miel no se echa a perder. Se ha encontrado miel comestible en tumbas "
     "egipcias de hace más de tres mil años.",
     "Ciencia",
     "Tiene tan poca agua y tanto azúcar que ninguna bacteria puede vivir en "
     "ella; es conservación por deshidratación."),
    ("El agua es rara: al congelarse se expande en vez de encogerse, y por eso "
     "el hielo flota.",
     "Ciencia",
     "Si se hundiera, los lagos se congelarían desde el fondo y no habría vida "
     "acuática en invierno."),
    ("El sonido viaja más de cuatro veces más rápido en el agua que en el aire, "
     "y aún más rápido en el acero.",
     "Ciencia",
     "Por eso los indígenas pegaban la oreja al suelo y las ballenas se "
     "comunican a cientos de kilómetros."),
    ("Los plátanos son ligeramente radiactivos por el potasio que llevan. Tanto "
     "que existe la «dosis equivalente de plátano» para explicar la radiación.",
     "Ciencia",
     "Sirve para poner en escala los sustos: una radiografía de tórax son unos "
     "setenta plátanos."),
    ("En el vacío del espacio, dos piezas de metal limpio que se tocan se sueldan "
     "solas y no se pueden separar.",
     "Ciencia",
     "En la Tierra no pasa porque el aire deja una capa de óxido; es un problema "
     "real para los ingenieros de satélites."),
    ("El cero absoluto son −273,15 °C, y no es solo que haga mucho frío: es el "
     "punto donde ya no se puede extraer más energía. No se puede alcanzar.",
     "Ciencia",
     "Los laboratorios llegan a millonésimas de grado por encima, nunca a él."),

    # ----------------------------------------------- Cuerpo humano (más)
    ("El hígado se regenera: se puede extirpar buena parte y vuelve a crecer "
     "hasta recuperar su tamaño.",
     "Cuerpo humano",
     "Es lo que hace posible el trasplante de donante vivo."),
    ("Tienes un punto ciego en cada ojo, donde el nervio óptico atraviesa la "
     "retina. No lo notas porque el cerebro rellena el hueco.",
     "Cuerpo humano",
     "Buena parte de lo que «ves» es una reconstrucción, no una foto."),
    ("Los huesos más pequeños del cuerpo están en el oído: el martillo, el "
     "yunque y el estribo. El estribo mide unos tres milímetros.",
     "Cuerpo humano",
     "Amplifican la vibración del tímpano lo suficiente para mover el líquido "
     "del oído interno."),
    ("El olfato es el único sentido que llega al cerebro sin pasar por la "
     "estación de reparto que filtra a los demás, y entra casi directo en las "
     "zonas de la memoria y la emoción.",
     "Cuerpo humano",
     "Por eso un olor te devuelve una tarde de la infancia entera y una foto no."),
    ("Produces entre uno y dos litros de saliva al día, y sin ella no notarías "
     "casi ningún sabor.",
     "Cuerpo humano",
     "Las moléculas del sabor tienen que disolverse para llegar a las papilas."),

    # ------------------------------------------------------ Lengua (más)
    ("Los signos de apertura «¿» y «¡» son casi exclusivos del español. Los fijó "
     "la Academia en 1754 porque en frases largas no se sabía dónde empezaba la "
     "pregunta.",
     "Lengua",
     "Es una solución de ingeniería a un problema de lectura, no un capricho."),
    ("La «ñ» nació de una abreviatura: los copistas medievales escribían una "
     "rayita encima para no repetir la «n» de «annus».",
     "Lengua",
     "Ahorrar pergamino, que era carísimo, acabó creando una letra."),
    ("Chocolate, tomate, aguacate, chicle, petaca y cacahuete vienen del "
     "náhuatl; canoa, huracán y barbacoa, del taíno.",
     "Lengua",
     "El español se llevó de América palabras para cosas que en Europa no "
     "existían y había que nombrar."),
    ("«Usted» viene de «vuestra merced», gastado por el uso hasta quedar en dos "
     "sílabas.",
     "Lengua",
     "Las palabras más usadas son las que más se erosionan: por eso los verbos "
     "irregulares son siempre los comunes."),

    # -------------------------------------------------------- Arte (más)
    ("El David de Miguel Ángel salió de un bloque de mármol que otros "
     "escultores habían dado por inservible y llevaba años tirado.",
     "Arte",
     "Tenía veintiséis años cuando lo empezó."),
    ("El azul de los cuadros antiguos costaba más que el oro: se hacía con "
     "lapislázuli traído de Afganistán.",
     "Arte",
     "Por eso el manto de la Virgen es azul en tantos cuadros: era la forma de "
     "demostrar cuánto se había gastado el que pagaba."),
    ("La cúpula de Brunelleschi en Florencia se levantó sin la cimbra de madera "
     "que se usaba entonces, y todavía se discute exactamente cómo lo hizo.",
     "Arte",
     "No dejó planos: en su época, el método era el capital del maestro."),
    ("Picasso pintó el Guernica en unas cinco semanas, y el cuadro estuvo casi "
     "cuarenta años fuera de España por voluntad del propio pintor.",
     "Arte",
     "Llegó al Prado en 1981, cuando ya se cumplía la condición que puso: que "
     "en España hubiera libertades públicas."),

    # --------------------------------------------------- Geografía (más)
    ("El punto de la Tierra más alejado de su centro no es el Everest, es el "
     "volcán Chimborazo, en Ecuador.",
     "Geografía",
     "El planeta está achatado y abultado en el ecuador, así que allí la "
     "«altura» se mide desde más lejos."),
    ("Alaska es a la vez el punto más al norte, el más al oeste y el más al este "
     "de Estados Unidos.",
     "Geografía",
     "Sus islas Aleutianas cruzan el antimeridiano, y al otro lado las "
     "coordenadas cambian de signo."),
    ("Australia es más ancha que el diámetro de la Luna: unos cuatro mil "
     "kilómetros frente a tres mil cuatrocientos setenta y cinco.",
     "Geografía",
     "Nos cuesta comparar tamaños cuando una cosa está en el cielo y la otra en "
     "el mapa."),
    ("Canadá tiene más lagos que todos los demás países del mundo juntos.",
     "Geografía",
     "Los dejó la última glaciación al retirarse el hielo, hace unos diez mil años."),
    ("Estambul es la única ciudad grande repartida entre dos continentes: una "
     "orilla en Europa y otra en Asia.",
     "Geografía",
     "Ese estrecho es la razón de que la ciudad haya sido capital de tres "
     "imperios seguidos."),

    # -------------------------------------------------- Tecnología (más)
    ("«Wi-Fi» no significa nada. Se lo inventó una agencia de marketing en 1999 "
     "porque «IEEE 802.11b Direct Sequence» no se podía vender.",
     "Tecnología",
     "Lo de «wireless fidelity» se lo pusieron después, para justificar el nombre."),
    ("El primer ratón de ordenador era una caja de madera con dos ruedas, "
     "presentada por Douglas Engelbart en 1968.",
     "Tecnología",
     "En la misma demostración enseñó el hipertexto, la videollamada y la "
     "edición colaborativa. La llaman «la madre de todas las demos»."),
    ("La primera cámara digital, de Kodak en 1975, pesaba casi cuatro kilos y "
     "tardaba veintitrés segundos en guardar una foto en blanco y negro.",
     "Tecnología",
     "Kodak la archivó por miedo a estropear su negocio del carrete, y ese miedo "
     "acabó llevándosela por delante."),
    ("Los ordenadores que llevaron el Apollo 11 a la Luna tenían menos memoria "
     "que un correo con una foto adjunta.",
     "Tecnología",
     "La potencia importa menos que saber exactamente qué se quiere calcular."),
    ("El primer dominio de internet registrado fue symbolics.com, en marzo de "
     "1985, y sigue existiendo.",
     "Tecnología",
     "En aquel momento había unos pocos cientos de ordenadores conectados."),

    # ------------------------------------------------ Matemáticas (más)
    ("La NASA usa quince decimales de pi para sus cálculos interplanetarios. "
     "Con cuarenta bastaría para calcular el universo observable con la "
     "precisión de un átomo.",
     "Matemáticas",
     "Los millones de decimales que se calculan sirven para probar ordenadores, "
     "no para medir nada."),
    ("Los números primos son infinitos, y Euclides lo demostró hace más de dos "
     "mil trescientos años con un argumento de tres líneas.",
     "Matemáticas",
     "Supón que fueran finitos, multiplícalos todos, suma uno: el resultado no "
     "es divisible por ninguno de ellos."),
    ("En el concurso de las tres puertas conviene cambiar de puerta: pasas de "
     "acertar un tercio de las veces a dos tercios.",
     "Matemáticas",
     "Cuesta creerlo hasta que se hace la cuenta; cuando se publicó, miles de "
     "lectores con carrera escribieron para decir que estaba mal."),
    ("Una cinta de Möbius tiene una sola cara y un solo borde: si la recorres "
     "con el dedo, vuelves al principio habiendo pasado por «las dos caras».",
     "Matemáticas",
     "Se hace con una tira de papel y media vuelta antes de pegar los extremos."),

    # -------------------------------------------------- Naturaleza (más)
    ("Las hormigas cortadoras de hojas no comen hojas: las usan para cultivar un "
     "hongo del que sí se alimentan. Llevan millones de años haciendo agricultura.",
     "Naturaleza",
     "Tienen hasta pesticida propio: bacterias en el cuerpo que frenan a los "
     "hongos competidores."),
    ("Los delfines duermen con medio cerebro cada vez, y con un ojo abierto.",
     "Naturaleza",
     "Respiran de forma voluntaria: quedarse dormidos del todo sería ahogarse."),
    ("Una jirafa tiene siete vértebras en el cuello. Las mismas que tú.",
     "Naturaleza",
     "Casi todos los mamíferos tienen siete: cambia el tamaño, no el número."),
    ("Los tardígrados sobreviven al vacío del espacio, a la radiación y a "
     "temperaturas de casi cero absoluto: se deshidratan y esperan.",
     "Naturaleza",
     "Miden medio milímetro y viven en el musgo de cualquier tejado."),
    ("Hay pinos de casi cinco mil años vivos hoy en California. Ya eran árboles "
     "adultos cuando se construyeron las pirámides.",
     "Naturaleza",
     "El más viejo se mantiene en secreto para que nadie lo dañe."),
    ("El animal que más ruido hace no es el elefante ni el león: es el cachalote, "
     "cuyos chasquidos superan los 230 decibelios bajo el agua.",
     "Naturaleza",
     "Los usa como un sonar para cazar a un kilómetro de profundidad, donde no "
     "llega la luz."),

    # -------------------------------------------------- Astronomía (más)
    ("Saturno flotaría en el agua si hubiera una bañera lo bastante grande: es "
     "menos denso que ella.",
     "Astronomía",
     "Es casi todo hidrógeno y helio; de «superficie» no tiene nada."),
    ("La Luna se aleja de la Tierra unos tres centímetros y medio al año, y por "
     "eso los días se van alargando poco a poco.",
     "Astronomía",
     "Se mide con espejos que dejaron las misiones Apollo y a los que se "
     "dispara un láser desde la Tierra."),
    ("Casi todas las estrellas fugaces las provoca un grano de polvo del tamaño "
     "de una arenilla ardiendo en la atmósfera.",
     "Astronomía",
     "Lo que ves no es la piedra: es el aire incandescente a su paso."),
    ("La estrella más cercana después del Sol está a 4,2 años luz. Con la sonda "
     "más rápida que hemos lanzado, el viaje duraría decenas de miles de años.",
     "Astronomía",
     "Las distancias entre estrellas son de otro orden que las que hay dentro "
     "del sistema solar."),

    # ------------------------------------------------- Filosofía (más)
    ("«Conócete a ti mismo» no es una frase de Sócrates: estaba grabada en el "
     "templo de Delfos mucho antes que él.",
     "Filosofía",
     "Él la usó tanto que se la quedó, como pasa con casi todas las citas famosas."),
    ("El barco de Teseo: si le cambias las tablas una a una hasta que no queda "
     "ninguna original, ¿sigue siendo el mismo barco?",
     "Filosofía",
     "No es un juego: es la pregunta de qué te hace ser tú, si tus células se "
     "renuevan continuamente."),
    ("Rawls proponía elegir las leyes de una sociedad sin saber qué lugar vas a "
     "ocupar en ella: ni tu familia, ni tu salud, ni tu país.",
     "Filosofía",
     "Es una manera de comprobar si algo te parece justo o solo te conviene."),

    # ---------------------------------------------------- Música (más)
    ("«Cumpleaños feliz» estuvo bajo derechos de autor hasta 2016. Cantarla en "
     "una película costaba miles de dólares en licencias.",
     "Música",
     "Por eso en tantas series de antes cantaban otra cosa en las escenas de "
     "cumpleaños."),
    ("Beethoven estrenó su Novena Sinfonía completamente sordo, y hubo que "
     "girarlo hacia el público para que viera los aplausos que no oía.",
     "Música",
     "Componía sintiendo las vibraciones a través de la madera del piano."),

    # ------------------------------------------------------------- Cine
    ("El cine mudo nunca fue mudo: había piano, órgano o incluso orquesta en "
     "directo en la sala, porque el silencio total resultaba insoportable.",
     "Cine",
     "La música ya hacía entonces el trabajo de decirte qué sentir."),
    ("El grito de Chewbacca es una mezcla de sonidos de oso, morsa, tejón y "
     "camello grabados por un diseñador de sonido.",
     "Cine",
     "Casi ningún sonido de cine es el sonido real: un puñetazo suele ser carne "
     "cruda golpeada."),
    ("El «grito Wilhelm» es el mismo alarido grabado en 1951 y reutilizado en "
     "cientos de películas como broma privada entre técnicos de sonido.",
     "Cine",
     "Está en Star Wars, en Indiana Jones y en decenas de estrenos de este año."),

    # ---------------------------------------------------------- Deporte
    ("El maratón mide 42,195 kilómetros por una decisión de 1908: alargaron la "
     "salida hasta el castillo de Windsor para que la familia real lo viera "
     "desde la ventana.",
     "Deporte",
     "Una distancia que hoy define un deporte entero salió de una comodidad de "
     "palacio."),
    ("Las reglas del fútbol moderno se escribieron en una taberna de Londres en "
     "1863, y la primera discusión fue si valía coger el balón con la mano.",
     "Deporte",
     "Los que decían que sí se marcharon y fundaron el rugby."),
    ("Los cinco colores de los aros olímpicos se eligieron porque, con el fondo "
     "blanco, al menos uno aparecía en la bandera de cada país de entonces.",
     "Deporte",
     "No representan continentes, aunque se repita todo el rato."),

    # ----------------------------------------------------- Gastronomía
    ("La pasta no la trajo Marco Polo de China. En Italia ya se comía pasta seca "
     "un siglo antes de que él naciera.",
     "Gastronomía",
     "El bulo salió de una revista de fabricantes de macarrones estadounidenses "
     "en 1929."),
    ("Las zanahorias eran moradas, blancas o amarillas. La naranja se popularizó "
     "en los Países Bajos en el siglo XVII.",
     "Gastronomía",
     "Que la asocies al color es cosa de cuatro siglos de selección agrícola."),
    ("El chocolate se bebió amargo y con especias durante siglos: el azúcar "
     "llegó al cacao cuando cruzó el Atlántico.",
     "Gastronomía",
     "Los mexicas lo usaban en ceremonias y hasta como moneda."),
    ("El tomate estuvo décadas en Europa como planta ornamental porque se creía "
     "venenoso: es pariente de la belladona.",
     "Gastronomía",
     "La cocina italiana y la española que damos por eternas no son tan viejas "
     "como parecen."),

    # -------------------------------------------------------- Medicina
    ("En 1847, Semmelweis descubrió que lavarse las manos hundía la mortalidad "
     "de las parturientas. Sus colegas se ofendieron, lo apartaron y murió en un "
     "manicomio.",
     "Medicina",
     "Tener razón y demostrarlo no basta si lo que dices acusa a quien te "
     "escucha."),
    ("La penicilina se descubrió por un descuido: Fleming se fue de vacaciones y "
     "dejó unas placas destapadas que se contaminaron con un moho.",
     "Medicina",
     "El descuido lo tiene cualquiera; lo raro fue mirar la placa estropeada en "
     "vez de tirarla."),
    ("La viruela es la única enfermedad humana erradicada del planeta. El último "
     "caso natural fue en Somalia en 1977.",
     "Medicina",
     "Hizo falta una campaña mundial de vacunación en plena Guerra Fría, con "
     "Estados Unidos y la URSS colaborando."),
    ("Hasta 1846 se operaba sin anestesia general. La velocidad del cirujano era "
     "su mayor virtud, y una amputación se medía en segundos.",
     "Medicina",
     "Casi toda la cirugía que existe hoy es posterior a poder dormir al "
     "paciente."),

    # ------------------------------------------------------- Psicología
    ("Ebbinghaus midió en 1885 cuánto se olvida con el tiempo: sin repasar, en "
     "un día se pierde más de la mitad de lo aprendido.",
     "Psicología",
     "Esa curva es la razón de que esta aplicación exista y de que te haga "
     "repasar justo antes de que se te caiga."),
    ("Repartir el estudio en varios días hace recordar mucho más que meter las "
     "mismas horas seguidas, aunque estudiando del tirón te sientas mejor.",
     "Psicología",
     "La sensación de facilidad es mala consejera: lo que cuesta al aprender "
     "suele ser lo que se queda."),
    ("La memoria no graba, reconstruye. Cada vez que recuerdas algo lo vuelves a "
     "montar, y en el camino se le pegan detalles nuevos.",
     "Psicología",
     "Por eso un testigo puede estar sinceramente seguro y equivocado a la vez."),
    ("El efecto placebo funciona incluso cuando le dices al paciente que lo que "
     "toma es un placebo.",
     "Psicología",
     "Se ha probado en dolor crónico y en síndrome de intestino irritable: el "
     "ritual de tratarse ya hace parte del trabajo."),

    # ----------------------------------------------------------- Inventos
    ("El microondas se descubrió porque a un ingeniero de radares se le derritió "
     "una chocolatina en el bolsillo mientras trabajaba junto a un magnetrón.",
     "Inventos",
     "Lo siguiente que probó fueron palomitas, y funcionaron."),
    ("El velcro se le ocurrió a un ingeniero suizo al mirar con lupa los cardos "
     "que se le pegaban al perro en el monte.",
     "Inventos",
     "Copiar a la naturaleza tiene hasta nombre: biomímesis."),
    ("El Post-it nació de un pegamento fallido: se quería uno muy fuerte y salió "
     "uno que apenas pegaba y se despegaba sin dejar rastro.",
     "Inventos",
     "Tardó cinco años en encontrar para qué servía, y lo encontró un compañero "
     "harto de perder los marcapáginas del cantoral."),
    ("Nobel inventó la dinamita y creó los premios que llevan su nombre después "
     "de leer su propio obituario, publicado por error, que lo llamaba «el "
     "mercader de la muerte».",
     "Inventos",
     "Es de los pocos que han podido leer cómo se les iba a recordar y cambiarlo."),

    # ------------------------------------------- Lo que crees y no es (más)
    ("Los toros no ven el rojo: son daltónicos para ese color. Lo que les "
     "provoca es el movimiento del capote.",
     "Lo que crees y no es",
     "El rojo es para el público, y para disimular la sangre."),
    ("Los peces de colores no tienen tres segundos de memoria: recuerdan durante "
     "meses y se les puede entrenar.",
     "Lo que crees y no es",
     "El mito sirve para justificar tenerlos en una pecera diminuta."),
    ("El pelo y las uñas no siguen creciendo después de la muerte. La piel se "
     "retrae al deshidratarse y parece que asoman más.",
     "Lo que crees y no es",
     "Es un buen ejemplo de cómo el ojo interpreta un cambio de referencia como "
     "un movimiento."),
    ("No hay pruebas de que el azúcar ponga nerviosos a los niños. Los estudios "
     "a doble ciego no encuentran el efecto: lo que cambia es lo que esperan "
     "ver los padres.",
     "Lo que crees y no es",
     "Cuando la madre cree que su hijo ha tomado azúcar, lo describe más "
     "hiperactivo aunque no lo haya tomado."),
    ("Los murciélagos no están ciegos. Ven perfectamente; el sonar lo usan para "
     "cazar de noche.",
     "Lo que crees y no es",
     "«Más ciego que un murciélago» es de las comparaciones peor elegidas del "
     "idioma."),
    ("Einstein no suspendía matemáticas. Dominaba el cálculo diferencial a los "
     "quince años.",
     "Lo que crees y no es",
     "El bulo consuela tanto que sobrevive a todos los desmentidos, incluido el "
     "del propio Einstein en vida."),

    # ----------------------------------------------------- Economía (más)
    ("La primera burbuja financiera documentada fue la de los tulipanes en la "
     "Holanda de 1637: un bulbo llegó a costar lo que una casa junto al canal.",
     "Economía",
     "Todas las burbujas repiten el mismo argumento: «esta vez es distinto»."),
    ("El objetivo de inflación del 2 % que persiguen casi todos los bancos "
     "centrales salió de una cifra dicha casi de pasada en Nueva Zelanda en 1989.",
     "Economía",
     "No hay una teoría detrás de ese número exacto; hay una costumbre que "
     "cuajó y ya nadie quiere mover."),
    ("Quien inventó el PIB, Simon Kuznets, avisó de que no debía usarse para "
     "medir el bienestar de un país.",
     "Economía",
     "Suma lo que se produce, así que un vertido de petróleo lo hace subir por "
     "el gasto en limpiarlo."),
    ("Un billete de euro no vale nada por sí mismo: es papel de algodón. Vale "
     "porque todo el mundo acepta que vale.",
     "Economía",
     "Es un acuerdo colectivo, y como todo acuerdo puede romperse: eso es una "
     "crisis de confianza."),

    # -------------------------------------------------------- Cine (más)
    ("La primera película sonora que triunfó, El cantor de jazz, es de 1927. En "
     "cinco años el cine mudo había desaparecido y muchas estrellas con él.",
     "Cine",
     "No por sus voces, como se cuenta, sino porque el sonido cambió del todo "
     "la forma de rodar y de actuar."),
    ("Los créditos finales de las películas se hicieron largos por un acuerdo "
     "sindical: garantizan que aparezca quien trabajó en ella.",
     "Cine",
     "Detrás de cada nombre hay un oficio que casi nadie sabe que existe."),
    ("El sonido del sable láser de Star Wars es el zumbido de un proyector de "
     "cine viejo mezclado con la interferencia de un televisor.",
     "Cine",
     "Lo grabó Ben Burtt paseando un micrófono por su casa."),

    # ----------------------------------------------------- Deporte (más)
    ("El baloncesto se inventó en 1891 para tener a unos alumnos ocupados "
     "durante el invierno, y las primeras canastas eran cestas de melocotones "
     "con fondo: había que subir por una escalera a sacar el balón.",
     "Deporte",
     "Tardaron años en caer en la idea de quitarle el fondo a la cesta."),
    ("En los primeros Juegos Olímpicos modernos, en 1896, los ganadores "
     "recibían medalla de plata: el oro se consideraba de mal gusto.",
     "Deporte",
     "El podio de oro, plata y bronce no llegó hasta 1904."),

    # ------------------------------------------------------ Música (más)
    ("Mozart murió a los treinta y cinco años habiendo compuesto más de "
     "seiscientas obras, muchas de ellas de memoria y sin correcciones.",
     "Música",
     "No era solo talento: empezó a trabajar a los cinco años y no paró."),
    ("Las notas do, re, mi, fa, sol, la, si salen de las primeras sílabas de un "
     "himno medieval a san Juan, en el que cada verso empezaba un tono más alto.",
     "Música",
     "Fue un truco para enseñar a cantar a los monjes antes de que existiera "
     "el pentagrama."),
    ("El jazz, el blues, el rock, el soul y el hip hop nacieron todos de la "
     "música de los afroamericanos en menos de un siglo.",
     "Música",
     "Casi todo lo que suena hoy en el mundo desciende de esa raíz."),

    # ---------------------------------------------------- Medicina (más)
    ("El estetoscopio se inventó por pudor: a un médico francés le incomodaba "
     "pegar la oreja al pecho de una paciente y enrolló un papel.",
     "Medicina",
     "Descubrió que además se oía mejor, y de ahí salió el tubo."),
    ("Los grupos sanguíneos se descubrieron en 1901. Antes, una transfusión era "
     "una lotería que mataba a la mitad de los pacientes.",
     "Medicina",
     "Aquel hallazgo convirtió la cirugía mayor en algo sobrevivible."),

    # -------------------------------------------------- Psicología (más)
    ("Recordar algo cuesta más que releerlo, y por eso funciona: obligarte a "
     "sacar la respuesta de la cabeza fija mucho más que volver a mirarla.",
     "Psicología",
     "Es el efecto de examen, y es la razón de que aquí se pregunte en vez de "
     "mostrar."),
    ("Buscamos información que nos dé la razón y esquivamos la que nos "
     "contradice, sin darnos cuenta. Se llama sesgo de confirmación.",
     "Psicología",
     "Saber que existe no te libra: el que se cree inmune lo tiene peor."),
    ("Somos malísimos prediciendo cuánto nos va a durar una alegría o una pena: "
     "casi todo se diluye antes de lo que creíamos.",
     "Psicología",
     "Los que ganan la lotería y los que sufren un accidente grave vuelven, con "
     "el tiempo, cerca de su nivel de ánimo de antes."),

    # ---------------------------------------------------- Inventos (más)
    ("El cristal irrompible de los parabrisas se descubrió cuando a un químico "
     "se le cayó un matraz con restos de plástico y se agrietó sin romperse.",
     "Inventos",
     "Tardó años en convencer a los fabricantes de coches de que valía la pena."),
    ("El código de barras se patentó en 1952 pero no se usó hasta 1974, cuando "
     "por fin hubo láseres y ordenadores baratos. El primer producto escaneado "
     "fue un paquete de chicles.",
     "Inventos",
     "Una idea puede estar veinte años esperando a que el resto del mundo la "
     "alcance."),

    # ------------------------------------------------- Gastronomía (más)
    ("La patata tardó dos siglos en aceptarse en Europa: se sospechaba de ella "
     "por crecer bajo tierra. En Francia hizo falta una campaña de marketing con "
     "guardias custodiando un campo para que la gente quisiera robarla.",
     "Gastronomía",
     "Cuando por fin se extendió, acabó con siglos de hambrunas periódicas."),
    ("El pan de molde, la lata y el congelado nacieron para alimentar ejércitos, "
     "no hogares.",
     "Gastronomía",
     "La lata la inventó un confitero francés respondiendo a un premio de "
     "Napoleón para conservar comida en campaña."),

    # --------------------------------------------------- Filosofía (más)
    ("Diógenes vivía en una tinaja y, cuando Alejandro Magno le ofreció lo que "
     "quisiera, le pidió que se apartara porque le tapaba el sol.",
     "Filosofía",
     "Los cínicos griegos no eran desconfiados: eran gente que despreciaba las "
     "convenciones y vivía en consecuencia."),
    ("Para los estoicos, lo único que está de verdad en tu mano es lo que "
     "juzgas y lo que haces; el resto —la salud, la fama, lo que opinen— "
     "solo se administra.",
     "Filosofía",
     "De ahí sale buena parte de la terapia cognitiva moderna, dos mil años "
     "después."),
]

CATEGORIAS = tuple(dict.fromkeys(categoria for _, categoria, _ in DATOS))


def categorias() -> tuple:
    """Las categorías de las que hay datos, en orden de aparición."""
    return CATEGORIAS


def aleatorio(evitar=(), categoria: str | None = None) -> tuple:
    """Un dato al azar, evitando los que acabas de ver.

    Devuelve (dato, categoría, porqué). Si ya los has visto todos, se reinicia:
    volver a oír algo tras una vuelta entera es repaso, no repetición.
    """
    pozo = [d for d in DATOS if not categoria or d[1] == categoria]
    if not pozo:
        pozo = list(DATOS)
    libres = [d for d in pozo if d[0] not in set(evitar)] or pozo
    return random.choice(libres)


def titular(dato: str, limite: int = 72) -> str:
    """El arranque del dato, cortado por una palabra entera.

    Es lo que se ve en el frente de la tarjeta: lo justo para saber de qué iba
    y tener que recordar el resto tú, que es donde está el trabajo.
    """
    limpio = " ".join((dato or "").split())
    if len(limpio) <= limite:
        return limpio
    corte = limpio[:limite].rsplit(" ", 1)[0]
    return corte.rstrip(" ,;:.") + "…"


def guardar_como_tarjeta(con, dato: str, categoria: str, porque: str = "",
                         pregunta: str = "") -> int | None:
    """Convierte un «sabías que» en tarjeta, para que no se te olvide.

    Es el paso que separa enterarse de saber: leído hoy y no repasado, en una
    semana no queda nada. Devuelve None si ese dato ya estaba guardado.
    """
    deck_id = db.upsert_deck(con, DECK_CULTURA, "Cultura general", "💡", "#9C6ADE",
                             20, ["Datos"])
    # El frente lleva el arranque del dato porque de él sale el identificador de
    # la tarjeta: con un frente genérico, el segundo dato que guardaras
    # machacaría al primero.
    frente = pregunta.strip() or f"💡 {categoria} · {titular(dato)}"
    dorso = dato if not porque else f"{dato}\n\n<i>{porque}</i>"
    ya = con.execute("SELECT id FROM cards WHERE deck_id=? AND back=?",
                     (deck_id, dorso)).fetchone()
    if ya:
        return None
    card_id, _ = db.add_card(con, deck_id, DECK_CULTURA, "card", frente, dorso,
                             tags=f"cultura,{categoria.lower()}", level=1)
    con.commit()
    return card_id


def cuantas_guardadas(con) -> int:
    fila = con.execute(
        """SELECT COUNT(*) FROM cards c JOIN decks d ON d.id=c.deck_id
           WHERE d.key=?""", (DECK_CULTURA,)).fetchone()
    return fila[0] if fila else 0
