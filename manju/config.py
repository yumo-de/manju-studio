import os
from pathlib import Path
import yaml
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent.parent


def load_config() -> dict:
    with open(ROOT / "config.yaml") as f:
        config = yaml.safe_load(f)
    # 替换 ${ENV_VAR} 占位符
    def _resolve(val):
        if isinstance(val, str) and val.startswith("${") and val.endswith("}"):
            return os.getenv(val[2:-1], "")
        return val
    return _walk(config, _resolve)


def _walk(obj, fn):
    if isinstance(obj, dict):
        return {k: _walk(v, fn) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk(v, fn) for v in obj]
    return fn(obj)
