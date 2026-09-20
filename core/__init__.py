"""
PetaniProxy Core Package
High-Speed Multi-Protocol Scraper, Validator & Local Rotating Gateway
"""
import os

__version__ = "1.2.0"

def _load_env():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_paths = [
        os.path.join(base_dir, ".env"),
        os.path.join(base_dir, ".env.local")
    ]
    for p in env_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'\"")
                            if k and k not in os.environ:
                                os.environ[k] = v
            except Exception:
                pass

_load_env()
