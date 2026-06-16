from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = BASE_DIR / "config.json"


def load_env_file(env_file: str | Path | None = None) -> Path | None:
    env_path = Path(env_file or os.getenv("CONTENT_PIPELINE_ENV", ".env"))
    if not env_path.is_absolute():
        env_path = BASE_DIR / env_path
    if not env_path.exists():
        return None

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            os.environ.setdefault(key, value)
    return env_path


def load_json_config() -> dict[str, Any]:
    configured_path = os.getenv("CONTENT_PIPELINE_CONFIG")
    config_path = Path(configured_path) if configured_path else DEFAULT_CONFIG_PATH
    if not config_path.is_absolute():
        config_path = BASE_DIR / config_path
    if not config_path.exists():
        return {}
    parsed = json.loads(config_path.read_text(encoding="utf-8"))
    return parsed if isinstance(parsed, dict) else {}


def nested_get(config: dict[str, Any], path: str, default: Any = "") -> Any:
    current: Any = config
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def str_env(name: str, config: dict[str, Any], config_path: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        value = nested_get(config, config_path, default)
    return str(value or "").strip()


def bool_env(name: str, config: dict[str, Any], config_path: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        value = nested_get(config, config_path, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def normalize_sqlite_url(value: str) -> str:
    if not value.startswith("sqlite:///"):
        return value
    raw_path = value.removeprefix("sqlite:///")
    if raw_path == ":memory:":
        return value
    db_path = Path(raw_path)
    if not db_path.is_absolute():
        db_path = BASE_DIR / db_path
    return f"sqlite:///{db_path.as_posix()}"


@dataclass(frozen=True)
class AppConfig:
    app_database_url: str
    external_database_url: str
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    pending_output_dir: Path
    wechat_app_id: str
    wechat_app_secret: str
    wechat_auto_publish: bool
    wechat_enable_mass_send: bool
    scheduler_enabled: bool
    scheduler_interval_minutes: int

    @property
    def has_llm(self) -> bool:
        return bool(self.llm_api_key)

    @property
    def has_external_database(self) -> bool:
        return bool(self.external_database_url)

    @property
    def has_wechat(self) -> bool:
        return bool(self.wechat_app_id and self.wechat_app_secret)


def build_config() -> AppConfig:
    load_env_file()
    config = load_json_config()
    data_dir = BASE_DIR / "data"
    default_app_db = f"sqlite:///{(data_dir / 'pipeline.db').as_posix()}"

    pending_dir = Path(
        str_env(
            "PENDING_OUTPUT_DIR",
            config,
            "publish.pending_output_dir",
            str(data_dir / "pending"),
        )
    )
    if not pending_dir.is_absolute():
        pending_dir = BASE_DIR / pending_dir

    interval = str_env("SCHEDULER_INTERVAL_MINUTES", config, "scheduler.interval_minutes", "240")

    app_database_url = normalize_sqlite_url(
        str_env("APP_DATABASE_URL", config, "app_database_url", default_app_db)
    )

    return AppConfig(
        app_database_url=app_database_url,
        external_database_url=str_env("DATABASE_URL", config, "database.url", ""),
        llm_api_key=str_env("CONTENT_LLM_API_KEY", config, "llm.api_key", ""),
        llm_base_url=str_env("CONTENT_LLM_BASE_URL", config, "llm.base_url", "https://api.openai.com/v1"),
        llm_model=str_env("CONTENT_LLM_MODEL", config, "llm.model", "gpt-4o-mini"),
        pending_output_dir=pending_dir,
        wechat_app_id=str_env("WECHAT_APP_ID", config, "wechat.app_id", ""),
        wechat_app_secret=str_env("WECHAT_APP_SECRET", config, "wechat.app_secret", ""),
        wechat_auto_publish=bool_env("WECHAT_AUTO_PUBLISH", config, "wechat.auto_publish", False),
        wechat_enable_mass_send=bool_env("WECHAT_ENABLE_MASS_SEND", config, "wechat.enable_mass_send", False),
        scheduler_enabled=bool_env("SCHEDULER_ENABLED", config, "scheduler.enabled", False),
        scheduler_interval_minutes=max(5, int(interval or "240")),
    )
