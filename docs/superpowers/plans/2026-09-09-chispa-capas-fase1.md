# Chispa por capas · Fase 1 (cara) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que Chispa parpadee de verdad y mueva la boca, extrayendo los ojos y la boca del atlas como capas propias y reconstruyendo el pelaje que hay detrás.

**Architecture:** Un extractor sin estado convierte el atlas en capas y las guarda en el directorio de datos del usuario; un rig las carga y las compone al dibujar. Si algo falla, `Chispa._personaje` sigue dibujando como hoy con la malla sobre el atlas plano, así que la mascota nunca se queda sin dibujar.

**Tech Stack:** Python 3, PyCairo, `unittest`. Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-09-09-chispa-por-capas-design.md`

## Global Constraints

- **Sin dependencias nuevas.** Solo biblioteca estándar y lo que ya usa el proyecto.
- **Las superficies de Cairo son ARGB32 premultiplicado.** Hay que dividir por el alfa antes de comparar colores, o los píxeles semitransparentes se clasifican mal.
- **Las capas no van al repositorio.** Se generan en `db.DATA_DIR / "chispa" / "capas"`.
- **Nada de esto puede dejar a la mascota sin dibujar.** Ante cualquier fallo, respaldo.
- **Las poses 3 y 5 ya tienen los ojos cerrados dibujados**: no generan capa de ojos.
- **Las pruebas que necesiten el atlas se saltan si no está**, como hace `tests/test_animacion_chispa.py`.
- **Código y comentarios en español**, explicando el porqué.
- Suite: `./pruebas.sh`

---

### Task 1: Clasificar un píxel contra la paleta

**Files:**
- Create: `appstudy/capas_chispa.py`
- Test: `tests/test_capas_chispa.py`

**Interfaces:**
- Produces: `PALETA: dict[str, tuple]`, `clasificar(r, g, b) -> str`, `color_de(datos, i, ...) -> tuple`

- [ ] **Step 1: Write the failing test**

```python
from appstudy import capas_chispa as capas

class ClasificarTest(unittest.TestCase):
    def test_cada_color_de_la_paleta_se_reconoce_a_si_mismo(self):
        for nombre, refs in capas.PALETA.items():
            for r, g, b in refs:
                self.assertEqual(capas.clasificar(r, g, b), nombre)

    def test_un_naranja_algo_apagado_sigue_siendo_naranja(self):
        self.assertEqual(capas.clasificar(0xE0, 0x80, 0x36), "naranja")

    def test_el_blanco_del_ojo_no_se_confunde_con_la_crema_del_hocico(self):
        self.assertEqual(capas.clasificar(255, 255, 255), "ojo")
        self.assertEqual(capas.clasificar(0xFB, 0xF3, 0xE6), "crema")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_capas_chispa` → FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Write minimal implementation**

`appstudy/capas_chispa.py` con la paleta tomada de `chispa.py` y la clasificación por distancia euclídea al color más cercano.

- [ ] **Step 4: Run test to verify it passes**

- [ ] **Step 5: Commit**

```bash
git add appstudy/capas_chispa.py tests/test_capas_chispa.py
git commit -m "Capas: clasificar un píxel contra la paleta de Chispa"
```

---

### Task 2: Agrupar píxeles en piezas conexas

**Files:**
- Modify: `appstudy/capas_chispa.py`
- Test: `tests/test_capas_chispa.py`

**Interfaces:**
- Consumes: `clasificar` (Task 1)
- Produces: `grupos(superficie, colores, minimo=200) -> list[dict]` con claves `color`, `pixeles` (set de índices), `caja` (x0,y0,x1,y1 en fracciones), `centro` (fx,fy), `n`

- [ ] **Step 1: Write the failing test**

```python
class GruposTest(unittest.TestCase):
    def lienzo(self, manchas, lado=64):
        """Un atlas de mentira: cuadrados de color sobre fondo naranja."""
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32, lado, lado)
        cr = cairo.Context(s)
        cr.set_source_rgb(*[v/255 for v in capas.PALETA["naranja"][1]])
        cr.paint()
        for (x, y, w, h) in manchas:
            cr.set_source_rgb(1, 1, 1)
            cr.rectangle(x, y, w, h)
            cr.fill()
        s.flush()
        return s

    def test_dos_manchas_separadas_dan_dos_grupos(self):
        s = self.lienzo([(6, 6, 14, 14), (40, 6, 14, 14)])
        g = capas.grupos(s, {"ojo"}, minimo=20)
        self.assertEqual(len(g), 2)

    def test_el_grupo_sabe_donde_esta(self):
        s = self.lienzo([(16, 32, 16, 16)])
        g = capas.grupos(s, {"ojo"}, minimo=20)[0]
        self.assertAlmostEqual(g["centro"][0], 24/64, places=2)
        self.assertAlmostEqual(g["centro"][1], 40/64, places=2)

    def test_lo_pequeño_se_descarta(self):
        s = self.lienzo([(6, 6, 2, 2)])
        self.assertEqual(capas.grupos(s, {"ojo"}, minimo=20), [])
```

- [ ] **Step 2-5:** implementar por recorrido en anchura sobre los píxeles del color pedido, ejecutar, commit.

```bash
git commit -m "Capas: agrupar píxeles conexos en piezas con su caja y su centro"
```

---

### Task 3: Encontrar los ojos y la boca en el atlas real

**Files:**
- Modify: `appstudy/capas_chispa.py`
- Test: `tests/test_capas_chispa.py`

**Interfaces:**
- Consumes: `grupos` (Task 2)
- Produces: `piezas(superficie, indice) -> dict[str, set[int]]` con claves posibles `ojo_izq`, `ojo_der`, `boca`

- [ ] **Step 1: Write the failing test**

```python
class PiezasTest(unittest.TestCase):
    def setUp(self):
        self.poses = cargar_poses()
        if self.poses is None:
            self.skipTest("Requiere el atlas de Chispa")

    def test_en_la_pose_de_reposo_hay_dos_ojos_separados(self):
        p = capas.piezas(self.poses[0], 0)
        self.assertIn("ojo_izq", p)
        self.assertIn("ojo_der", p)

    def test_los_ojos_estan_en_la_mitad_de_arriba(self):
        for indice in (0, 1, 2, 4):
            p = capas.piezas(self.poses[indice], indice)
            for clave in ("ojo_izq", "ojo_der"):
                if clave in p:
                    cy = capas.caja_de(self.poses[indice], p[clave])[1]
                    self.assertLess(cy, 0.6, f"pose {indice} {clave}")

    def test_las_poses_con_los_ojos_ya_cerrados_no_dan_capa_de_ojo(self):
        for indice in (3, 5):
            p = capas.piezas(self.poses[indice], indice)
            self.assertNotIn("ojo_izq", p)

    def test_la_boca_esta_por_debajo_de_los_ojos(self):
        p = capas.piezas(self.poses[0], 0)
        self.assertIn("boca", p)
```

- [ ] **Step 2-5:** reglas por color, tamaño y posición; ejecutar; commit.

```bash
git commit -m "Capas: encontrar ojos y boca por color y posición, sin medirlos a ojo"
```

---

### Task 4: Reconstruir el pelaje de detrás y escribir el almacén

**Files:**
- Modify: `appstudy/capas_chispa.py`
- Test: `tests/test_capas_chispa.py`

**Interfaces:**
- Consumes: `piezas` (Task 3)
- Produces: `reconstruir(superficie, pixeles) -> superficie`, `recortar(superficie, pixeles) -> superficie`, `extraer(destino=None) -> dict` (el manifiesto), `VERSION: str`, `carpeta() -> Path`

- [ ] **Step 1: Write the failing test**

```python
class ReconstruirTest(BaseTemporal):
    def test_detras_del_ojo_ya_no_queda_blanco_de_ojo(self):
        poses = cargar_poses()
        if poses is None:
            self.skipTest("Requiere el atlas")
        p = capas.piezas(poses[0], 0)
        base = capas.reconstruir(poses[0], p["ojo_izq"] | p["ojo_der"])
        quedan = capas.contar_color(base, p["ojo_izq"] | p["ojo_der"], "ojo")
        self.assertEqual(quedan, 0)

    def test_la_capa_recortada_conserva_el_ojo_y_nada_mas(self):
        poses = cargar_poses()
        if poses is None:
            self.skipTest("Requiere el atlas")
        p = capas.piezas(poses[0], 0)
        capa = capas.recortar(poses[0], p["ojo_izq"])
        self.assertGreater(capas.contar_color(capa, p["ojo_izq"], "ojo"), 100)

    def test_extraer_deja_manifiesto_y_archivos(self):
        if cargar_poses() is None:
            self.skipTest("Requiere el atlas")
        m = capas.extraer()
        self.assertEqual(m["version"], capas.VERSION)
        self.assertTrue((capas.carpeta() / "base-0.png").exists())
        self.assertTrue((capas.carpeta() / "0-ojo_izq.png").exists())
```

- [ ] **Step 2-5:** difusión desde el borde y suavizado; escritura de PNG y `manifiesto.json` con versión y huella del atlas; ejecutar; commit.

```bash
git commit -m "Capas: reconstruir el pelaje de detrás y guardar el almacén"
```

---

### Task 5: El rig, con parpadeo y boca

**Files:**
- Create: `appstudy/rig_chispa.py`
- Test: `tests/test_rig_chispa.py`

**Interfaces:**
- Consumes: el almacén de la Task 4
- Produces: `cargar() -> Rig | None`; `Rig.dibujar(cr, indice, cierre=0.0, apertura=0.0)`; `Rig.tiene(indice, pieza) -> bool`

- [ ] **Step 1: Write the failing test**

```python
class RigTest(BaseTemporal):
    def test_sin_capas_no_hay_rig_y_no_revienta(self):
        self.assertIsNone(rig_chispa.cargar())

    def test_con_los_ojos_abiertos_se_ve_el_blanco_del_ojo(self):
        # extraer() primero
        blanco = self.pintar_y_contar(cierre=0.0)
        self.assertGreater(blanco, 200)

    def test_con_los_ojos_cerrados_no_queda_blanco_a_la_vista(self):
        self.assertLess(self.pintar_y_contar(cierre=1.0), 20)

    def test_la_boca_cerrada_no_deja_lengua(self):
        self.assertLess(self.pintar_y_contar(apertura=0.0, color="lengua"), 20)
```

- [ ] **Step 2-5:** carga del manifiesto, composición base + piezas, recorte del ojo contra el párpado y escala de la boca; ejecutar; commit.

```bash
git commit -m "Rig: componer las capas, con parpadeo y boca de verdad"
```

---

### Task 6: Engancharlo a Chispa, con respaldo

**Files:**
- Modify: `appstudy/chispa.py`
- Test: `tests/test_chispa.py`

**Interfaces:**
- Consumes: `rig_chispa.cargar` (Task 5)

- [ ] **Step 1: Write the failing test**

```python
def test_sin_capas_se_dibuja_como_hoy(self):
    """El respaldo es lo que garantiza que la mascota nunca se quede sin dibujar."""
    c = Chispa()
    self.assertIsNone(c._rig())
    # y draw() no lanza
```

- [ ] **Step 2-5:** `Chispa._rig()` cacheado, uso en `_personaje`, generación en segundo plano al primer arranque; ejecutar la suite entera; commit.

```bash
git commit -m "Chispa: dibujar por capas cuando las hay, y como siempre cuando no"
```

---

### Task 7: Documentación

- [ ] Sección en el README sobre el parpadeo y de dónde salen las capas, incluyendo que se generan solas y se pueden borrar.
- [ ] Nota en `appstudy/data/chispa-poses.md` de que el atlas es la fuente de las capas.
- [ ] `./pruebas.sh` en verde y commit.
