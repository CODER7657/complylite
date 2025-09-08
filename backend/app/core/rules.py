import os
import yaml
from functools import lru_cache

DEFAULT_RULES_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'rule_packs', 'default_rules.yaml')

@lru_cache(maxsize=1)
def load_rules(path: str | None = None) -> dict:
    """Load rule configuration from YAML. Returns an empty dict if missing."""
    rules_path = path or DEFAULT_RULES_PATH
    try:
        with open(rules_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}
