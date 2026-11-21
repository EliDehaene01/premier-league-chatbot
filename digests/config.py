from pathlib import Path

import yaml

WEIGHTS_FILE = Path(__file__).with_name("weights.yaml")


def load_weights(path: Path = WEIGHTS_FILE) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))
