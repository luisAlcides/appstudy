"""Las fórmulas en LaTeX, dibujadas con texto y las etiquetas de Pango.

Dos cosas importan aquí. Que lo traducido sea markup válido, porque una etiqueta
mal cerrada tira abajo la tarjeta entera. Y que un `$` que no es una fórmula
—un precio, `$1` de awk, `$HOME`— se quede tal cual: es el error que estropea
los mazos de Linux.
"""
import unittest

import gi

gi.require_version("Pango", "1.0")
from gi.repository import Pango  # noqa: E402

from appstudy import mates  # noqa: E402


def valido(markup: str) -> bool:
    """¿Lo entiende Pango? Es la única definición que importa."""
    try:
        Pango.parse_markup(markup, -1, "\x00")
        return True
    except Exception:
        return False


class TestAMarkup(unittest.TestCase):
    def test_letras_griegas_y_simbolos(self):
        self.assertIn("σ", mates.a_markup(r"\sigma"))
        self.assertIn("≤", mates.a_markup(r"\leq"))
        self.assertIn("∑", mates.a_markup(r"\sum"))
        self.assertIn("→", mates.a_markup(r"\rightarrow"))

    def test_exponentes_y_subindices(self):
        self.assertIn("<sup>2</sup>", mates.a_markup("E=mc^2"))
        self.assertIn("<sub>i</sub>", mates.a_markup("x_i"))
        self.assertIn("<sup>n+1</sup>", mates.a_markup("x^{n+1}"))

    def test_una_fraccion_baja_a_una_linea_con_barra(self):
        self.assertIn("a/b", mates.a_markup(r"\frac{a}{b}"))

    def test_una_fraccion_con_operadores_lleva_parentesis(self):
        salida = mates.a_markup(r"\frac{a+b}{c}")
        self.assertIn("(a+b)/c", salida)

    def test_la_raiz_cuadrada(self):
        self.assertIn("√", mates.a_markup(r"\sqrt{x}"))
        self.assertIn("√(a+b)", mates.a_markup(r"\sqrt{a+b}"))

    def test_fracciones_anidadas(self):
        salida = mates.a_markup(r"\frac{\frac{a}{b}}{c}")
        self.assertNotIn("frac", salida)

    def test_los_acentos_van_encima_de_la_letra(self):
        self.assertIn("x̄", mates.a_markup(r"\bar{x}"))
        self.assertIn("v⃗", mates.a_markup(r"\vec{v}"))

    def test_text_deja_el_contenido_a_secas(self):
        salida = mates.a_markup(r"\text{aciertos}")
        self.assertIn("aciertos", salida)
        self.assertNotIn("text", salida)

    def test_una_orden_desconocida_no_rompe_nada(self):
        salida = mates.a_markup(r"\vueltasqueda{x}")
        self.assertTrue(valido(salida))
        self.assertIn("x", salida)

    def test_los_menor_y_mayor_sueltos_se_escapan(self):
        salida = mates.a_markup("a < b > c")
        self.assertTrue(valido(salida))
        self.assertIn("&lt;", salida)
        self.assertIn("&gt;", salida)

    def test_la_formula_de_la_desviacion_tipica_del_readme(self):
        salida = mates.a_markup(r"\sigma = \sqrt{\frac{\sum (x_i-\bar{x})^2}{n}}")
        self.assertTrue(valido(salida))
        for pieza in ("σ", "√", "∑", "x̄", "<sup>2</sup>"):
            self.assertIn(pieza, salida)

    def test_todo_simbolo_conocido_produce_markup_valido(self):
        for nombre in mates.SIMBOLOS:
            with self.subTest(simbolo=nombre):
                self.assertTrue(valido(mates.a_markup("\\" + nombre)))


class TestExtraer(unittest.TestCase):
    def test_una_formula_en_linea_con_senal_se_interpreta(self):
        texto, formulas = mates.extraer("La energía es $E=mc^2$ y ya.")
        self.assertEqual(len(formulas), 1)
        self.assertNotIn("$", texto)
        self.assertIn("<sup>2</sup>", formulas[0])

    def test_un_bloque_no_necesita_senal(self):
        _, formulas = mates.extraer("$$a = b$$")
        self.assertEqual(len(formulas), 1)

    def test_un_precio_se_queda_como_esta(self):
        texto, formulas = mates.extraer("cuesta $5 y $9")
        self.assertEqual(formulas, [])
        self.assertEqual(texto, "cuesta $5 y $9")

    def test_el_dolar_de_awk_no_se_toca(self):
        entrada = "awk '{print $1}' archivo.txt"
        texto, formulas = mates.extraer(entrada)
        self.assertEqual(formulas, [])
        self.assertEqual(texto, entrada)

    def test_dos_variables_de_shell_seguidas_no_son_una_formula(self):
        entrada = "usa $HOME y $PATH en el script"
        texto, formulas = mates.extraer(entrada)
        self.assertEqual(formulas, [])
        self.assertEqual(texto, entrada)

    def test_restaurar_devuelve_las_formulas_a_su_sitio(self):
        original = "La energía es $E=mc^2$ y la media $\\bar{x}$."
        texto, formulas = mates.extraer(original)
        vuelto = mates.restaurar(texto, formulas)
        self.assertEqual(len(formulas), 2)
        self.assertNotIn(mates.MARCA.format(0), vuelto)   # ninguna marca sin restaurar
        self.assertIn("<sup>2</sup>", vuelto)

    def test_restaurar_sin_formulas_no_cambia_nada(self):
        self.assertEqual(mates.restaurar("texto suelto", []), "texto suelto")

    def test_varias_formulas_conservan_su_orden(self):
        texto, formulas = mates.extraer("primero $a^1$, después $b^2$, al final $c^3$")
        vuelto = mates.restaurar(texto, formulas)
        self.assertLess(vuelto.index("<sup>1</sup>"), vuelto.index("<sup>2</sup>"))
        self.assertLess(vuelto.index("<sup>2</sup>"), vuelto.index("<sup>3</sup>"))


class TestHayFormula(unittest.TestCase):
    def test_reconoce_lo_que_lleva_formula(self):
        self.assertTrue(mates.hay_formula("$E=mc^2$"))
        self.assertTrue(mates.hay_formula("$$a=b$$"))

    def test_descarta_lo_que_no(self):
        self.assertFalse(mates.hay_formula("sin dólares"))
        self.assertFalse(mates.hay_formula(""))
        self.assertFalse(mates.hay_formula(None))


class TestContenidoIncluido(unittest.TestCase):
    """Ninguna fórmula de los mazos de fábrica debe romper el markup."""

    def test_las_formulas_de_los_mazos_se_dibujan_bien(self):
        import json
        from pathlib import Path

        contenido = Path(__file__).resolve().parent.parent / "appstudy" / "content"
        revisadas = 0
        for archivo in sorted(contenido.rglob("*.json")):
            crudo = archivo.read_text(encoding="utf-8")
            datos = json.loads(crudo)
            for texto in _textos(datos):
                if not mates.hay_formula(texto):
                    continue
                marcado, formulas = mates.extraer(texto)
                for f in formulas:
                    revisadas += 1
                    with self.subTest(archivo=archivo.name, formula=f[:60]):
                        self.assertTrue(valido(f))
        self.assertGreater(revisadas, 0, "no se encontró ninguna fórmula que revisar")


def _textos(datos):
    """Todas las cadenas de un JSON, sea cual sea su forma."""
    pila = [datos]
    while pila:
        actual = pila.pop()
        if isinstance(actual, str):
            yield actual
        elif isinstance(actual, dict):
            pila.extend(actual.values())
        elif isinstance(actual, list):
            pila.extend(actual)


if __name__ == "__main__":
    unittest.main()
