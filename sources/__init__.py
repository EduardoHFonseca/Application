"""Camada de fontes do crawler multi-site do projeto Application."""

from .base import JobPosting, JobSource, canonicalize_url, normalize_text
from .registry import (
    build_source,
    build_sources,
    default_keywords,
    default_locations,
    enabled_source_names,
    load_config,
    source_summary,
)

__all__ = [
    "JobPosting",
    "JobSource",
    "canonicalize_url",
    "normalize_text",
    "build_source",
    "build_sources",
    "default_keywords",
    "default_locations",
    "enabled_source_names",
    "load_config",
    "source_summary",
]
