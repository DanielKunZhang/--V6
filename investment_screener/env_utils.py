import os
from pathlib import Path


ENV_CANDIDATES = [
    Path(__file__).parent / ".screener_env.local",
    Path(__file__).resolve().parent.parent / ".ic_env.local",
]


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_local_env() -> dict:
    loaded = {}
    for env_file in ENV_CANDIDATES:
        if not env_file.exists():
            continue
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
