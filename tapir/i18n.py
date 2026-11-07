import os

LANGUAGES = {"en": "English", "fr": "Français"}

UINPUT_HELP = """Tapir cannot create its virtual mouse:
{error}

Tapir needs write access to /dev/uinput. Install this udev rule as /etc/udev/rules.d/70-tapir-uinput.rules:

KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", OPTIONS+="static_node=uinput"

then reload it (or reboot):

sudo udevadm control --reload-rules
sudo udevadm trigger --name-match=uinput

From the source tree, scripts/setup-permissions.sh does all of this."""

# Keyed by the English text, which is also the fallback.
FR = {
    # Window
    "Close": "Fermer",
    "Language": "Langue",
    "Interval": "Intervalle",
    "Random variation ±": "Variation aléatoire ±",
    "{gap} between clicks": "{gap} entre les clics",
    "Minimum is {min} ms, using {gap}": "Minimum {min} ms, donc {gap}",
    "Click": "Clic",
    "Button": "Bouton",
    "Left": "Gauche",
    "Right": "Droit",
    "Middle": "Milieu",
    "Type": "Type",
    "Single": "Simple",
    "Double": "Double",
    "Repetition": "Répétition",
    "Repeat": "Répéter",
    " times": " fois",
    "Until stopped": "Jusqu'à l'arrêt",
    "Startup": "Démarrage",
    "Delay before start": "Délai avant démarrage",
    "Hotkey": "Raccourci",
    "Set…": "Définir…",
    "Press the new hotkey. Esc cancels, Backspace removes it.":
        "Appuyez sur le nouveau raccourci. Échap annule, Retour arrière le supprime.",
    "Needs Hyprland, or read access to /dev/input/event*":
        "Nécessite Hyprland, ou l'accès en lecture à /dev/input/event*",
    "None": "Aucun",
    "{label} (inactive)": "{label} (inactif)",
    "Press a key or side button…": "Appuyez sur une touche ou un bouton latéral…",
    "Mouse": "Souris",
    "Clicks: {n}": "Clics : {n}",
    "Start": "Démarrer",
    "Stop": "Arrêter",
    "Stopped": "Arrêté",
    "Starting in {n} s": "Démarrage dans {n} s",
    "Running": "En cours",
    "Could not set the hotkey.": "Impossible de définir le raccourci.",
    "{label} is already bound in Hyprland.": "{label} est déjà utilisé dans Hyprland.",
    # Tray
    "Show": "Afficher",
    "Quit": "Quitter",
    "Tapir: {state}": "Tapir : {state}",
    UINPUT_HELP: """Tapir ne peut pas créer sa souris virtuelle :
{error}

Tapir a besoin de l'accès en écriture à /dev/uinput. Installez cette règle udev dans /etc/udev/rules.d/70-tapir-uinput.rules :

KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", OPTIONS+="static_node=uinput"

puis rechargez-la (ou redémarrez) :

sudo udevadm control --reload-rules
sudo udevadm trigger --name-match=uinput

Depuis les sources, scripts/setup-permissions.sh fait tout cela.""",
}

_language = "en"


def system_language() -> str:
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        if value := os.environ.get(var):
            return "fr" if value.startswith("fr") else "en"
    return "en"


def set_language(code: str) -> None:
    """Empty or unknown codes follow the system language."""
    global _language
    _language = code if code in LANGUAGES else system_language()


def language() -> str:
    return _language


def tr(text: str, **values) -> str:
    if _language == "fr":
        text = FR.get(text, text)
    return text.format(**values) if values else text


def number(n: int) -> str:
    return f"{n:,}".replace(",", " " if _language == "fr" else ",")


def translate_label(label: str) -> str:
    # Hotkey labels are saved in English; only the mouse button names are translated.
    return label.replace("Mouse", tr("Mouse"))
