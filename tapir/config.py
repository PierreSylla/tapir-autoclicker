import logging
import os
import tomllib
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import tomli_w

from tapir.engine import BUTTONS

log = logging.getLogger(__name__)

CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "tapir" / "config.toml"


@dataclass
class Config:
    hours: int = 0
    minutes: int = 0
    seconds: int = 0
    milliseconds: int = 100
    jitter_ms: int = 0
    button: str = "left"
    double_click: bool = False
    repeat_forever: bool = True
    repeat_count: int = 10
    start_delay_s: int = 3
    hotkey: str = ""
    hotkey_label: str = ""
    language: str = ""  # empty: follow the system


def load(path: Path = CONFIG_PATH) -> Config:
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        return Config()
    except (OSError, ValueError) as e:
        log.warning("Ignoring unreadable config %s: %s", path, e)
        return Config()
    defaults = Config()
    valid = {
        f.name: data[f.name]
        for f in fields(Config)
        if type(data.get(f.name)) is type(getattr(defaults, f.name))
    }
    if valid.get("button") not in (None, *BUTTONS):
        del valid["button"]
    return Config(**valid)


def save(config: Config, path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(tomli_w.dumps(asdict(config)), encoding="utf-8")
    tmp.replace(path)
