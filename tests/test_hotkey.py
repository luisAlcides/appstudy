import unittest

from appstudy import hotkey


class HotkeyTest(unittest.TestCase):
    def test_parsea_lista_de_gsettings(self):
        raw = "['/uno/', '/dos/']"
        self.assertEqual(hotkey._parse_list(raw), ["/uno/", "/dos/"])

    def test_parsea_lista_vacia_tipada(self):
        self.assertEqual(hotkey._parse_list("@as []"), [])

    def test_presenta_combinacion_para_personas(self):
        self.assertEqual(hotkey.pretty("<Super><Shift>n"), "Super + Shift + N")

    def test_los_dos_atajos_tienen_slots_distintos(self):
        self.assertNotEqual(hotkey.SLOT, hotkey.CAPTURE_SLOT)
        self.assertNotEqual(hotkey.DEFAULT_BINDING, hotkey.DEFAULT_CAPTURE_BINDING)


if __name__ == "__main__":
    unittest.main()
