"""Environment configuration profile manager."""
import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class ProfileConfig:
    env_name: str
    debug: bool
    api_endpoint: str
    timeout_sec: int = 30

    @classmethod
    def load_from_env(cls, default_env: str = "production") -> "ProfileConfig":
        env = os.environ.get("BUILDSITE_ENV", default_env).lower()
        debug = os.environ.get("BUILDSITE_DEBUG", "").lower() in ("1", "true", "yes")
        endpoint = os.environ.get("BUILDSITE_API_ENDPOINT", "https://api.buildsite.local")
        return cls(env_name=env, debug=debug, api_endpoint=endpoint)
