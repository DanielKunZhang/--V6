import os
from pathlib import Path


ENV_FILE = Path(__file__).parent / ".ic_env.local"


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_local_env(env_file: Path = ENV_FILE) -> dict:
    loaded = {}
    if not env_file.exists():
        return loaded

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_quotes(value)
        if key and key not in os.environ:
            os.environ[key] = value
            loaded[key] = value

    return loaded
