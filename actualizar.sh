#!/usr/bin/env bash
# Actualiza AppStudy de una vez: trae los cambios, reinstala lo que son copias,
# recarga el contenido y reinicia la mascota. Se puede repetir sin miedo.
set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$RAIZ"

echo "▸ Buscando cambios nuevos"
if git rev-parse --git-dir >/dev/null 2>&1 && [ -n "$(git remote)" ]; then
  if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "  (aviso) tienes cambios sin guardar: no toco el repositorio."
    echo "          Guárdalos con git commit, o descártalos, y vuelve a ejecutarme."
  else
    ANTES="$(git rev-parse HEAD)"
    if git pull --ff-only; then
      DESPUES="$(git rev-parse HEAD)"
      if [ "$ANTES" = "$DESPUES" ]; then
        echo "  Ya estabas al día."
      else
        echo "  Actualizado: $(git rev-list --count "$ANTES..$DESPUES") commits nuevos."
        CAMBIOS="$(git diff --name-only "$ANTES" "$DESPUES")"
      fi
    else
      echo "  (aviso) no pude traer los cambios; sigo con lo que hay aquí."
    fi
  fi
else
  echo "  Sin remoto configurado: uso el código que ya tienes aquí."
fi

# El atajo actual, para no pisarlo al reinstalar
ATAJO="$(python3 -c "
import sys; sys.path.insert(0, '$RAIZ')
from appstudy import hotkey
print(hotkey.current_binding('') or '<Super><Shift>e')" 2>/dev/null || echo '<Super><Shift>e')"

echo "▸ Reinstalando lo que son copias (icono, lanzador, dock, extensión)"
"$RAIZ/install.sh" "$ATAJO" | sed 's/^/  /'

echo "▸ Recargando el contenido incluido"
"$RAIZ/bin/appstudy" --reload 2>/dev/null | sed 's/^/  /' || echo "  (nada que recargar)"

echo "▸ Reiniciando a Bit"
ESTABA="$("$RAIZ/bin/appstudy" --status 2>/dev/null | grep -c '"mascota": true' || true)"
"$RAIZ/bin/appstudy" --pet-off >/dev/null 2>&1
sleep 1
if [ "${ESTABA:-0}" != "0" ]; then
  setsid "$RAIZ/bin/appstudy" --pet >/dev/null 2>&1 &
  sleep 3
  echo "  Bit ya corre con la versión nueva."
else
  echo "  No estaba suelta; la sueltas con: appstudy --pet"
fi

echo
echo "✓ Listo."
if pgrep -f "bin/appstudy$" >/dev/null 2>&1; then
  echo "  ⚠ Tienes la ventana principal abierta: ciérrala y vuelve a abrirla para"
  echo "    que coja el código nuevo (el contenido ya está recargado)."
fi
if [ -n "${CAMBIOS:-}" ] && echo "$CAMBIOS" | grep -q "^gnome-extension/"; then
  echo "  ⚠ Cambió la extensión de la barra superior: cierra sesión y vuelve a"
  echo "    entrar para que GNOME la recargue (en Wayland no hay otra forma)."
fi
