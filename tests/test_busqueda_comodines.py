"""Buscar «50%» o «snake_case» no debe activar los comodines de SQL.

En un `LIKE`, `%` casa con cualquier cosa y `_` con cualquier letra. Si lo que
escribes en la caja de búsqueda llega crudo a la consulta, buscar un porcentaje
te devuelve media base y buscar un identificador con guion bajo te trae
palabras que no tienen nada que ver.
"""
from appstudy import db, scheduler
from tests.apoyo import BaseTemporal


class ComoLikeTest(BaseTemporal):
    def test_desactiva_los_comodines_y_la_propia_barra(self):
        self.assertEqual(db.como_like("50%"), r"50\%")
        self.assertEqual(db.como_like("snake_case"), r"snake\_case")
        self.assertEqual(db.como_like(r"c:\ruta"), r"c:\\ruta")
        self.assertEqual(db.como_like("nada que escapar"), "nada que escapar")

    def test_en_sqlite_el_escape_hace_lo_que_dice(self):
        con = self.con
        con.execute("CREATE TABLE prueba(t TEXT)")
        con.executemany("INSERT INTO prueba VALUES(?)",
                        [("rebaja del 50%",), ("rebaja del 5012",), ("snake_case",),
                         ("snakeXcase",)])
        def buscar(texto):
            return [r[0] for r in con.execute(
                "SELECT t FROM prueba WHERE t LIKE ? ESCAPE '\\' ORDER BY t",
                (f"%{db.como_like(texto)}%",))]

        self.assertEqual(buscar("50%"), ["rebaja del 50%"])
        self.assertEqual(buscar("snake_case"), ["snake_case"])


class BuscarTarjetasTest(BaseTemporal):
    def setUp(self):
        super().setUp()
        self.deck = self.mazo()
        self.tarjeta(self.deck, "Descuento del 50%", "La mitad del precio")
        self.tarjeta(self.deck, "Descuento del 5012", "Un número cualquiera")
        self.tarjeta(self.deck, "Qué es snake_case", "palabras_con_guion_bajo")
        self.tarjeta(self.deck, "Qué es snakeXcase", "no existe tal cosa")

    def frentes(self, texto):
        """Como filtra la lista de tarjetas de la ventana principal."""
        return sorted(r["front"] for r in self.con.execute(
            "SELECT front FROM cards WHERE LOWER(front) LIKE ? ESCAPE '\\'",
            (f"%{db.como_like(texto.lower())}%",)))

    def test_el_porcentaje_se_busca_como_porcentaje(self):
        self.assertEqual(self.frentes("50%"), ["Descuento del 50%"])

    def test_el_guion_bajo_no_casa_con_cualquier_letra(self):
        self.assertEqual(self.frentes("snake_case"), ["Qué es snake_case"])


class EtiquetasConComodinTest(BaseTemporal):
    """`next_card` filtra por etiquetas con el mismo `LIKE`."""

    def test_una_etiqueta_con_guion_bajo_no_pesca_la_de_al_lado(self):
        # La única tarjeta que hay lleva otra etiqueta. Con el guion bajo
        # haciendo de comodín, «mate_basica» casaba con «mateXbasica» y la
        # sesión te sacaba tarjetas de un tema que no habías pedido.
        deck = self.mazo()
        self.vencer(self.tarjeta(deck, "Sin guion bajo", tags="mateXbasica"))
        self.assertIsNone(scheduler.next_card(self.con, tags="mate_basica"))

    def test_y_sí_encuentra_la_suya_cuando_toca(self):
        deck = self.mazo()
        self.vencer(self.tarjeta(deck, "Con guion bajo", tags="mate_basica"))
        card = scheduler.next_card(self.con, tags="mate_basica")
        self.assertIsNotNone(card)
        self.assertEqual(card["front"], "Con guion bajo")

    def test_una_etiqueta_de_solo_comodin_ya_no_lo_trae_todo(self):
        deck = self.mazo()
        self.vencer(self.tarjeta(deck, "Una cualquiera", tags="linux"))
        self.assertIsNone(scheduler.next_card(self.con, tags="%"))


# `ia.buscar_contexto` usa el mismo `LIKE`, pero trocea la pregunta con
# `[a-záéíóúüñ0-9]{4,}`: un `%` o un `_` no sobreviven al troceo y nunca llegan
# a la consulta. El escape está puesto igual, por si ese patrón cambia.
