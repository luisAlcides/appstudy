"""Frases de libros que Bit suelta de vez en cuando.

Cada entrada lleva la obra de donde sale; cuando la atribución es tradicional y
no hay una página que señalar, se dice («atribuida»). La idea no es adornar: son
frases cortas que se quedan, y leerlas sueltas a lo largo del día es otra forma
de estudiar.
"""
import random

# (frase, autor, obra)
CITAS = [
    # -- literatura
    ("En un lugar de la Mancha, de cuyo nombre no quiero acordarme…",
     "Miguel de Cervantes", "Don Quijote de la Mancha"),
    ("El que lee mucho y anda mucho, ve mucho y sabe mucho.",
     "Miguel de Cervantes", "Don Quijote de la Mancha"),
    ("Muchos años después, frente al pelotón de fusilamiento, el coronel "
     "Aureliano Buendía había de recordar aquella tarde remota en que su padre "
     "lo llevó a conocer el hielo.",
     "Gabriel García Márquez", "Cien años de soledad"),
    ("Todas las familias felices se parecen; las infelices lo son cada una a su manera.",
     "León Tolstói", "Ana Karénina"),
    ("Era el mejor de los tiempos, era el peor de los tiempos.",
     "Charles Dickens", "Historia de dos ciudades"),
    ("Llamadme Ismael.", "Herman Melville", "Moby Dick"),
    ("Es una verdad universalmente reconocida que un hombre soltero, poseedor de "
     "una gran fortuna, necesita una esposa.",
     "Jane Austen", "Orgullo y prejuicio"),
    ("La guerra es la paz. La libertad es la esclavitud. La ignorancia es la fuerza.",
     "George Orwell", "1984"),
    ("Lo esencial es invisible a los ojos.",
     "Antoine de Saint-Exupéry", "El principito"),
    ("La perfección se alcanza no cuando no hay nada más que añadir, sino cuando "
     "no queda nada más que quitar.",
     "Antoine de Saint-Exupéry", "Tierra de hombres"),
    ("Un libro debe ser el hacha que rompa el mar helado dentro de nosotros.",
     "Franz Kafka", "Carta a Oskar Pollak, 1904"),
    ("El tiempo es la sustancia de que estoy hecho.",
     "Jorge Luis Borges", "Nueva refutación del tiempo"),
    ("Caminante, no hay camino, se hace camino al andar.",
     "Antonio Machado", "Campos de Castilla"),
    ("Nosotros, los de entonces, ya no somos los mismos.",
     "Pablo Neruda", "Veinte poemas de amor y una canción desesperada"),
    ("Cuando emprendas el viaje hacia Ítaca, pide que el camino sea largo.",
     "Constantino Cavafis", "Ítaca"),
    ("La felicidad solo es real cuando se comparte.",
     "Christopher McCandless", "citado en Hacia rutas salvajes"),

    # -- filosofía
    ("Todos los hombres desean por naturaleza saber.",
     "Aristóteles", "Metafísica"),
    ("Una vida sin examen no merece ser vivida.",
     "Platón", "Apología de Sócrates"),
    ("Solo sé que no sé nada.", "Sócrates", "atribuida"),
    ("Sapere aude: ten el valor de servirte de tu propio entendimiento.",
     "Immanuel Kant", "¿Qué es la Ilustración?"),
    ("Pienso, luego existo.", "René Descartes", "Discurso del método"),
    ("El corazón tiene razones que la razón no entiende.",
     "Blaise Pascal", "Pensamientos"),
    ("Vale más saber algo de todo que saberlo todo de una sola cosa.",
     "Blaise Pascal", "Pensamientos"),
    ("Los límites de mi lenguaje son los límites de mi mundo.",
     "Ludwig Wittgenstein", "Tractatus logico-philosophicus"),
    ("De lo que no se puede hablar, hay que callar.",
     "Ludwig Wittgenstein", "Tractatus logico-philosophicus"),
    ("Quien tiene un porqué para vivir puede soportar casi cualquier cómo.",
     "Friedrich Nietzsche", "El ocaso de los ídolos"),
    ("Hay que tener un caos dentro de sí para dar a luz una estrella danzarina.",
     "Friedrich Nietzsche", "Así habló Zaratustra"),
    ("Quien lucha con monstruos debe cuidar de no convertirse en monstruo.",
     "Friedrich Nietzsche", "Más allá del bien y del mal"),
    ("El hombre está condenado a ser libre.",
     "Jean-Paul Sartre", "El existencialismo es un humanismo"),
    ("Yo soy yo y mi circunstancia, y si no la salvo a ella no me salvo yo.",
     "José Ortega y Gasset", "Meditaciones del Quijote"),
    ("Mientras enseñamos, aprendemos.",
     "Séneca", "Cartas a Lucilio"),
    ("No aprendemos para la escuela, sino para la vida.",
     "Séneca", "inversión popular de Cartas a Lucilio 106"),

    # -- ciencia
    ("Si he visto más lejos, es porque estoy sentado sobre los hombros de gigantes.",
     "Isaac Newton", "Carta a Robert Hooke, 1675"),
    ("En los campos de la observación, el azar solo favorece a la mente preparada.",
     "Louis Pasteur", "Conferencia en Lille, 1854"),
    ("Nada en la vida debe temerse, solo comprenderse. Ahora es el momento de "
     "comprender más, para temer menos.",
     "Marie Curie", "atribuida"),
    ("La imaginación es más importante que el conocimiento.",
     "Albert Einstein", "entrevista en The Saturday Evening Post, 1929"),
    ("Somos polvo de estrellas.", "Carl Sagan", "Cosmos"),
    ("La ciencia es mucho más una forma de pensar que un cuerpo de conocimientos.",
     "Carl Sagan", "El mundo y sus demonios"),
    ("Dadme un punto de apoyo y moveré el mundo.",
     "Arquímedes", "atribuida"),
    ("Todos los modelos son falsos; algunos son útiles.",
     "George Box", "Robustness in the Strategy of Scientific Model Building"),
    ("No hay nada más práctico que una buena teoría.",
     "Kurt Lewin", "La teoría del campo en la ciencia social"),

    # -- oficio y código
    ("Los programas deben escribirse para que los lean las personas y solo de "
     "forma incidental para que los ejecuten las máquinas.",
     "Abelson y Sussman", "Structure and Interpretation of Computer Programs"),
    ("La informática no trata de los ordenadores más de lo que la astronomía "
     "trata de los telescopios.",
     "Edsger W. Dijkstra", "atribuida"),
    ("La optimización prematura es la raíz de todos los males.",
     "Donald Knuth", "Structured Programming with go to Statements"),
    ("Un lenguaje que no cambia tu manera de pensar sobre la programación no "
     "merece la pena conocerlo.",
     "Alan Perlis", "Epigrams on Programming"),
    ("Con suficientes ojos, todos los errores son evidentes.",
     "Eric S. Raymond", "La catedral y el bazar"),
    ("Hablar es barato. Enséñame el código.",
     "Linus Torvalds", "lista de correo del kernel de Linux, 2000"),
    ("Escribo para descubrir qué estoy pensando.",
     "Joan Didion", "Por qué escribo"),
    ("Nunca consideres el estudio como una obligación, sino como una oportunidad "
     "de entrar en el bello y maravilloso mundo del saber.",
     "Albert Einstein", "atribuida"),
]


def aleatoria(evitar=()):
    """Una cita al azar, esquivando las últimas que ya se dijeron."""
    libres = [c for c in CITAS if c[0] not in evitar] or CITAS
    return random.choice(libres)
