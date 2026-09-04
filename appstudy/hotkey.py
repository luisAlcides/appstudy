"""Registro del atajo global en el escritorio (GNOME y Cinnamon)."""
import shlex
import subprocess

NAME = "AppStudy"
GNOME_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
GNOME_LIST = ("org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings")
SLOT = "appstudy"
DEFAULT_BINDING = "<Super><Shift>e"
CAPTURE_SLOT = "appstudy-capture"
CAPTURE_NAME = "AppStudy · Captura rápida"
DEFAULT_CAPTURE_BINDING = "<Super><Shift>n"


def _gs(*args) -> str:
    return subprocess.run(["gsettings", *args], capture_output=True, text=True).stdout.strip()


def _has_schema(schema: str) -> bool:
    out = subprocess.run(["gsettings", "list-schemas"], capture_output=True, text=True).stdout
    return schema in out.split()


def desktop() -> str:
    if _has_schema(GNOME_LIST[0]):
        return "gnome"
    if _has_schema("org.cinnamon.desktop.keybindings"):
        return "cinnamon"
    return "otro"


def _parse_list(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw or raw in ("@as []", "[]"):
        return []
    raw = raw.removeprefix("@as ").strip("[]")
    return [p.strip().strip("'\"") for p in raw.split(",") if p.strip()]


def current_binding(command: str, slot: str = SLOT) -> str | None:
    """Devuelve el atajo ya registrado para AppStudy, o None."""
    if desktop() != "gnome":
        return None
    path = f"{GNOME_PATH}{slot}/"
    schema = f"{GNOME_LIST[0]}.custom-keybinding:{path}"
    if path not in _parse_list(_gs("get", *GNOME_LIST)):
        return None
    return _gs("get", schema, "binding").strip("'") or None


def install(command: str, binding: str = DEFAULT_BINDING, slot: str = SLOT,
            name: str = NAME) -> tuple[bool, str]:
    """Registra (o actualiza) el atajo. Devuelve (ok, mensaje)."""
    env = desktop()
    if env != "gnome":
        return False, (
            f"Escritorio '{env}' no soportado automáticamente. Crea un atajo manual "
            f"que ejecute:\n{command}")

    path = f"{GNOME_PATH}{slot}/"
    schema = f"{GNOME_LIST[0]}.custom-keybinding:{path}"
    actuales = _parse_list(_gs("get", *GNOME_LIST))
    if path not in actuales:
        actuales.append(path)
        nuevo = "[" + ", ".join(f"'{p}'" for p in actuales) + "]"
        subprocess.run(["gsettings", "set", *GNOME_LIST, nuevo], check=True)

    for key, value in (("name", name), ("command", command), ("binding", binding)):
        subprocess.run(["gsettings", "set", schema, key, value], check=True)
    return True, f"Atajo {pretty(binding)} registrado."


def uninstall(slot: str = SLOT) -> None:
    if desktop() != "gnome":
        return
    path = f"{GNOME_PATH}{slot}/"
    actuales = [p for p in _parse_list(_gs("get", *GNOME_LIST)) if p != path]
    nuevo = "[" + ", ".join(f"'{p}'" for p in actuales) + "]" if actuales else "@as []"
    subprocess.run(["gsettings", "set", *GNOME_LIST, nuevo], check=True)


def pretty(binding: str) -> str:
    """'<Super><Shift>e' -> 'Super + Shift + E' para mostrar en la interfaz."""
    mods = {"<Super>": "Super", "<Shift>": "Shift", "<Control>": "Ctrl",
            "<Primary>": "Ctrl", "<Alt>": "Alt"}
    partes, resto = [], binding
    cambio = True
    while cambio:
        cambio = False
        for tag, nombre in mods.items():
            if resto.startswith(tag):
                partes.append(nombre)
                resto = resto[len(tag):]
                cambio = True
    if resto:
        partes.append(resto if len(resto) > 1 else resto.upper())
    return " + ".join(partes)


def accel_from_gtk(accel: str) -> str:
    """Normaliza un acelerador capturado por GTK al formato de gsettings."""
    return accel.replace("<Primary>", "<Control>")
