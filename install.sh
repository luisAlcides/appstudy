#!/usr/bin/env bash
# Instala AppStudy: comando en ~/.local/bin, lanzador de escritorio y atajo global.
set -euo pipefail

ATAJO="${1:-<Super><Shift>e}"
ATAJO_CAPTURA="${2:-<Super><Shift>n}"
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
command -v curl >/dev/null || command -v wget >/dev/null || \
  echo "  (aviso) falta curl o wget para descargar modelos: sudo apt install curl"
command -v paplay >/dev/null || command -v pw-play >/dev/null || command -v aplay >/dev/null || \
  echo "  (aviso) falta reproductor de audio: sudo apt install pulseaudio-utils"
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
Actions=popup;capture;pet;

[Desktop Action popup]
Name=Estudiar ahora (popup)
Exec=$RAIZ/bin/appstudy --popup

[Desktop Action capture]
Name=Captura rápida
Exec=$RAIZ/bin/appstudy --capture

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
echo "▸ Registrando captura rápida $ATAJO_CAPTURA"
"$RAIZ/bin/appstudy" --install-capture-hotkey "$ATAJO_CAPTURA"

echo "▸ Configurando modelos neuronales de voz (Piper TTS)…"
PIPER_DIR="$HOME/.local/share/appstudy/piper"
mkdir -p "$PIPER_DIR"

PROGRESS_FLAG=""
if [ -t 1 ]; then
  PROGRESS_FLAG="--progress-bar"
else
  PROGRESS_FLAG="-s"
fi

# 1. Motor Piper TTS
if [ ! -x "$PIPER_DIR/piper" ]; then
  echo "  Descargando binario Piper TTS…"
  ARCH="$(uname -m)"
  case "$ARCH" in
    x86_64)        PIPER_TAR="piper_linux_x86_64.tar.gz" ;;
    aarch64|arm64) PIPER_TAR="piper_linux_aarch64.tar.gz" ;;
    armv7l)        PIPER_TAR="piper_linux_armv7.tar.gz" ;;
    *)             PIPER_TAR="piper_linux_x86_64.tar.gz" ;;
  esac
  PIPER_URL="https://github.com/rhasspy/piper/releases/download/2023.11.14-2/${PIPER_TAR}"
  TMP_DIR="$(mktemp -d)"
  if curl -fSL $PROGRESS_FLAG "$PIPER_URL" -o "$TMP_DIR/piper.tar.gz" 2>/dev/null || \
     wget -qO "$TMP_DIR/piper.tar.gz" "$PIPER_URL" 2>/dev/null; then
    tar -xzf "$TMP_DIR/piper.tar.gz" -C "$HOME/.local/share/appstudy/"
    echo "  ✓ Piper instalado en $PIPER_DIR"
  else
    echo "  (aviso) No se pudo descargar Piper automáticamente."
  fi
  rm -rf "$TMP_DIR"
else
  echo "  ✓ Piper TTS ya instalado"
fi

# 2. Modelo de voz en español (es_ES-davefx-medium)
ES_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_ES/davefx/medium"
if [ ! -f "$PIPER_DIR/es_ES-davefx-medium.onnx" ]; then
  echo "  Descargando modelo de voz en español (es_ES-davefx-medium)…"
  curl -fSL $PROGRESS_FLAG "${ES_BASE}/es_ES-davefx-medium.onnx" -o "$PIPER_DIR/es_ES-davefx-medium.onnx" 2>/dev/null || \
    wget -qO "$PIPER_DIR/es_ES-davefx-medium.onnx" "${ES_BASE}/es_ES-davefx-medium.onnx" 2>/dev/null || true
  curl -fSL -s "${ES_BASE}/es_ES-davefx-medium.onnx.json" -o "$PIPER_DIR/es_ES-davefx-medium.onnx.json" 2>/dev/null || \
    wget -qO "$PIPER_DIR/es_ES-davefx-medium.onnx.json" "${ES_BASE}/es_ES-davefx-medium.onnx.json" 2>/dev/null || true
  if [ -f "$PIPER_DIR/es_ES-davefx-medium.onnx" ]; then
    echo "  ✓ Modelo de voz en español listo"
  fi
else
  echo "  ✓ Modelo de voz en español listo"
fi

# 3. Modelo de voz en inglés (en_US-lessac-medium)
EN_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium"
if [ ! -f "$PIPER_DIR/en_US-lessac-medium.onnx" ]; then
  echo "  Descargando modelo de voz en inglés (en_US-lessac-medium)…"
  curl -fSL $PROGRESS_FLAG "${EN_BASE}/en_US-lessac-medium.onnx" -o "$PIPER_DIR/en_US-lessac-medium.onnx" 2>/dev/null || \
    wget -qO "$PIPER_DIR/en_US-lessac-medium.onnx" "${EN_BASE}/en_US-lessac-medium.onnx" 2>/dev/null || true
  curl -fSL -s "${EN_BASE}/en_US-lessac-medium.onnx.json" -o "$PIPER_DIR/en_US-lessac-medium.onnx.json" 2>/dev/null || \
    wget -qO "$PIPER_DIR/en_US-lessac-medium.onnx.json" "${EN_BASE}/en_US-lessac-medium.onnx.json" 2>/dev/null || true
  if [ -f "$PIPER_DIR/en_US-lessac-medium.onnx" ]; then
    echo "  ✓ Modelo de voz en inglés listo"
  fi
else
  echo "  ✓ Modelo de voz en inglés listo"
fi

# 4. Modelo de IA local (Ollama)
echo "▸ Verificando modelo de IA local (Ollama)…"
if command -v ollama >/dev/null; then
  if ollama list 2>/dev/null | grep -q "gemma3:4b"; then
    echo "  ✓ Modelo gemma3:4b ya está disponible en Ollama"
  else
    echo "  Descargando modelo gemma3:4b en Ollama (esto puede tardar unos minutos)…"
    ollama pull gemma3:4b || echo "  (aviso) no se pudo descargar gemma3:4b automáticamente. Ejecuta: ollama pull gemma3:4b"
  fi
else
  echo "  (opcional) Sin Ollama no hay IA local. Para instalar:"
  echo "    curl -fsSL https://ollama.com/install.sh | sh && ollama pull gemma3:4b"
fi

echo
echo "✓ Listo."
echo "  Popup:            pulsa el atajo desde cualquier aplicación"
echo "  Captura rápida:   $ATAJO_CAPTURA"
echo "  Ventana completa: appstudy   (o busca «AppStudy» en el menú)"
echo "  Mascota:          appstudy --pet   (o Ajustes → Bit, la mascota)"
echo "  Dock:             anclado con su icono (si algo falla, arrástralo tú)"
echo "  Barra superior:   icono de AppStudy (tras reiniciar la sesión)"
echo "  Voz neuronal:     Piper TTS (español e inglés en $PIPER_DIR)"
echo "  IA local:         Ollama (gemma3:4b)"
echo "  Cambiar el atajo: dentro de la app, pestaña Ajustes"
