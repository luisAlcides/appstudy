#!/usr/bin/env bash
# Instala AppStudy: comando en ~/.local/bin, lanzador de escritorio y atajo global.
set -euo pipefail

ATAJO="${1:-<Super><Shift>e}"
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"

echo "▸ Verificando dependencias…"
python3 -c "
import gi
gi.require_version('Gtk', '4.0'); gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw
" || {
  echo "✗ Faltan GTK4/libadwaita. Instálalos con:"
  echo "  sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1"
  exit 1
}

echo "▸ Instalando el comando en $BIN_DIR/appstudy"
mkdir -p "$BIN_DIR"
ln -sf "$RAIZ/bin/appstudy" "$BIN_DIR/appstudy"

echo "▸ Creando el lanzador de escritorio"
mkdir -p "$APP_DIR"
cat > "$APP_DIR/appstudy.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=AppStudy
Comment=Estudio con repetición espaciada: inglés, Linux, datos, IA y mecánica
Exec=$RAIZ/bin/appstudy
Icon=accessories-dictionary
Terminal=false
Categories=Education;Science;
Keywords=estudio;flashcards;repaso;ingles;linux;mecanica;
StartupWMClass=io.github.appstudy.AppStudy
Actions=popup;

[Desktop Action popup]
Name=Estudiar ahora (popup)
Exec=$RAIZ/bin/appstudy --popup
DESKTOP
update-desktop-database "$APP_DIR" 2>/dev/null || true

echo "▸ Registrando el atajo global $ATAJO"
"$RAIZ/bin/appstudy" --install-hotkey "$ATAJO"

echo
echo "✓ Listo."
echo "  Popup:            pulsa el atajo desde cualquier aplicación"
echo "  Ventana completa: appstudy   (o busca «AppStudy» en el menú)"
echo "  Cambiar el atajo: dentro de la app, pestaña Ajustes"
