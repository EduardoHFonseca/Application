"""Registro de fontes: carrega config/sources.yaml e instancia adaptadores."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import yaml

from .base import JobSource, slugify
from .linkedin import LinkedInSource
from .link_only import LinkOnlySource
from .remotive import RemotiveSource
from .rss import RSSSource
from .workingnomads import WorkingNomadsSource

log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_PATH = os.path.join(BASE_DIR, "config", "sources.yaml")

IMPLEMENTED = {
    "remotive": RemotiveSource,
    "wwr": RSSSource,
    "workingnomads": WorkingNomadsSource,
    "linkedin": LinkedInSource,
}


def load_config(path: Optional[str] = None) -> Dict[str, Any]:
    config_path = path or os.getenv("CRAWLER_CONFIG") or DEFAULT_CONFIG_PATH
    with open(config_path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    defaults = data.get("defaults") or {}
    sources = {}
    for name, raw in (data.get("sources") or {}).items():
        merged = dict(defaults)
        merged.update(raw or {})
        merged["name"] = name
        sources[name] = merged

    return {
        "defaults": defaults,
        "sources": sources,
        "discarded": data.get("discarded") or [],
    }


def enabled_source_names(config: Optional[Dict[str, Any]] = None) -> List[str]:
    config = config or load_config()
    sources = config.get("sources") or {}
    env_value = os.getenv("CRAWLER_SOURCES", "").strip()
    if env_value:
        requested = [slugify(item) for item in env_value.split(",") if item.strip()]
    else:
        requested = [name for name, cfg in sources.items() if cfg.get("enabled")]
    return [name for name in requested if name in sources]


def build_source(
    name: str,
    config: Optional[Dict[str, Any]] = None,
    source_config: Optional[Dict[str, Any]] = None,
) -> JobSource:
    config = config or load_config()
    cfg = source_config or (config.get("sources") or {}).get(name)
    if not cfg:
        raise KeyError(f"Fonte desconhecida: {name}")

    source_class = IMPLEMENTED.get(name)
    if source_class is None and cfg.get("type") == "marketplace":
        source_class = LinkOnlySource
    if source_class is None:
        raise NotImplementedError(
            f"A fonte '{name}' está no catálogo mas ainda não tem parser implementado "
            f"(tipo={cfg.get('type')!r})."
        )
    return source_class(cfg)


def build_sources(
    names: Optional[List[str]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> List[JobSource]:
    config = config or load_config()
    names = names or enabled_source_names(config)
    return [build_source(name, config=config) for name in names]


def default_keywords(config: Optional[Dict[str, Any]] = None) -> List[str]:
    config = config or load_config()
    env_value = os.getenv("SEARCH_KEYWORDS", "").strip()
    if env_value:
        return [item.strip() for item in env_value.split(",") if item.strip()]
    return list((config.get("defaults") or {}).get("keywords") or [])


def default_locations(config: Optional[Dict[str, Any]] = None) -> List[str]:
    config = config or load_config()
    env_value = os.getenv("SEARCH_LOCATIONS", "").strip()
    if env_value:
        return [item.strip() for item in env_value.split(",") if item.strip()]
    return list((config.get("defaults") or {}).get("locations") or [])


def source_summary(config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    config = config or load_config()
    enabled = set(enabled_source_names(config))
    rows = []
    for name, cfg in (config.get("sources") or {}).items():
        rows.append(
            {
                "name": name,
                "label": cfg.get("label", name),
                "type": cfg.get("type", ""),
                "apply_mode": cfg.get("apply_mode", "assisted"),
                "enabled": name in enabled,
                "implemented": name in IMPLEMENTED or cfg.get("type") == "marketplace",
                "fetchable": name in IMPLEMENTED,
                "url": cfg.get("url", ""),
                "notes": (cfg.get("notes") or "").strip(),
            }
        )
    return rows
