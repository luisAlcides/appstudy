#!/usr/bin/env bash
# Instala AppStudy: comando en ~/.local/bin, lanzador de escritorio y atajo global.
set -euo pipefail

ATAJO="${1:-<Super><Shift>e}"
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
# El lanzador se llama como el id de la aplicación: así GNOME empareja la
# ventana abierta con su icono del dock (en Wayland el id es lo único que mira).
APP_ID="io.github.appstudy.AppStudy"

echo "▸ Verificando dependencias…"
command -v wmctrl >/dev/null || echo "  (aviso) falta wmctrl: la mascota no podrá quedarse encima. sudo apt install wmctrl x11-utils"
python3 -c "
import gi
gi.require_version('Gtk', '4.0'); gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw
" || {
  echo "✗ Faltan GTK4/libadwaita. Instálalos con:"
  echo "  sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1"
  exit 1
}
python3 -c "import pygments" 2>/dev/null || \
  echo "  (aviso) falta pygments: el código se verá sin colores. sudo apt install python3-pygments"
command -v ollama >/dev/null || \
  echo "  (opcional) sin ollama no hay IA local. curl -fsSL https://ollama.com/install.sh | sh"

echo "▸ Instalando el comando en $BIN_DIR/appstudy"
mkdir -p "$BIN_DIR"
ln -sf "$RAIZ/bin/appstudy" "$BIN_DIR/appstudy"

echo "▸ Instalando el icono"
mkdir -p "$ICON_DIR"
cp -f "$RAIZ/appstudy/data/$APP_ID.svg" "$ICON_DIR/$APP_ID.svg"
gtk-update-icon-cache -q -t -f "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo "▸ Creando el lanzador de escritorio"
mkdir -p "$APP_DIR"
rm -f "$APP_DIR/appstudy.desktop"          # el nombre viejo, de antes del icono
cat > "$APP_DIR/$APP_ID.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=AppStudy
Comment=Estudio con repetición espaciada: inglés, Linux, datos, IA y mecánica
Exec=$RAIZ/bin/appstudy
Icon=io.github.appstudy.AppStudy
Terminal=false
Categories=Education;
Keywords=estudio;flashcards;repaso;ingles;linux;mecanica;
StartupWMClass=io.github.appstudy.AppStudy
StartupNotify=true
Actions=popup;pet;

[Desktop Action popup]
Name=Estudiar ahora (popup)
Exec=$RAIZ/bin/appstudy --popup

[Desktop Action pet]
Name=Soltar a Bit (mascota)
Exec=$RAIZ/bin/appstudy --pet
DESKTOP
update-desktop-database "$APP_DIR" 2>/dev/null || true

echo "▸ Anclando AppStudy al dock"
if command -v gsettings >/dev/null && \
   gsettings writable org.gnome.shell favorite-apps >/dev/null 2>&1; then
  python3 - "$APP_ID.desktop" <<'FAV'
import subprocess, sys
entrada = sys.argv[1]
clave = ["org.gnome.shell", "favorite-apps"]
crudo = subprocess.run(["gsettings", "get", *clave],
                       capture_output=True, text=True).stdout.strip()
actuales = [p.strip().strip("'\"") for p in crudo.strip("[]").split(",") if p.strip()]
if entrada in actuales:
    print("  ya estaba en el dock")
else:
    actuales.append(entrada)
    lista = "[" + ", ".join(f"'{a}'" for a in actuales) + "]"
    subprocess.run(["gsettings", "set", *clave, lista], check=False)
    print(f"  añadido al dock ({len(actuales)} aplicaciones ancladas)")
FAV
else
  echo "  (aviso) sin GNOME Shell no puedo anclarlo: hazlo con clic derecho > Añadir a favoritos"
fi

echo "▸ Dejando a Bit en el escritorio al iniciar sesión"
mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/appstudy-pet.desktop" <<PET
[Desktop Entry]
Type=Application
Name=AppStudy · Bit
Comment=La mascota de estudio, siempre en el escritorio
Exec=$RAIZ/bin/appstudy --pet
Icon=io.github.appstudy.AppStudy
Terminal=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=8
PET

echo "▸ Instalando la extensión de la barra superior de GNOME"
UUID="appstudy@luisalcides.github.io"
EXT_DIR="$HOME/.local/share/gnome-shell/extensions/$UUID"
if [ -d "$RAIZ/gnome-extension/$UUID" ]; then
  mkdir -p "$EXT_DIR"
  cp -f "$RAIZ/gnome-extension/$UUID"/* "$EXT_DIR/"
  if command -v gnome-extensions >/dev/null; then
    gnome-extensions enable "$UUID" 2>/dev/null \
      || echo "  (aviso) actívala tú con: gnome-extensions enable $UUID"
  fi
  echo "  En Wayland hay que cerrar y volver a entrar en la sesión para que aparezca."
fi

echo "▸ Registrando el atajo global $ATAJO"
"$RAIZ/bin/appstudy" --install-hotkey "$ATAJO"

echo
echo "✓ Listo."
echo "  Popup:            pulsa el atajo desde cualquier aplicación"
echo "  Ventana completa: appstudy   (o busca «AppStudy» en el menú)"
echo "  Mascota:          appstudy --pet   (o Ajustes → Bit, la mascota)"
echo "  Dock:             anclado con su icono (si algo falla, arrástralo tú)"
echo "  Barra superior:   icono de AppStudy (tras reiniciar la sesión)"
echo "  Cambiar el atajo: dentro de la app, pestaña Ajustes"
