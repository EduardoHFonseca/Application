"""Adaptador genérico de feeds RSS (We Work Remotely)."""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable, List, Optional
from urllib.parse import urlsplit

import feedparser

from .base import JobPosting, JobSource, html_to_text

log = logging.getLogger(__name__)


def _entry_job_id(link: str, fallback: str = "") -> str:
    path = urlsplit(link or "").path.rstrip("/")
    if path:
        return path.rsplit("/", 1)[-1]
    return fallback


def _split_title(title: str) -> tuple:
    """'Empresa: Cargo' -> ('Empresa', 'Cargo')."""
    if ": " in (title or ""):
        company, role = title.split(": ", 1)
        return company.strip(), role.strip()
    return "", (title or "").strip()


def _join_location(entry: Any) -> str:
    parts = []
    for key in ("region", "state", "country"):
        value = str(entry.get(key) or "").strip()
        if value and value not in parts:
            parts.append(value)
    return " · ".join(parts)


class RSSSource(JobSource):
    name = "wwr"
    label = "We Work Remotely"
    apply_mode = "assisted"

    def fetch(
        self,
        keywords: Optional[Iterable[str]] = None,
        locations: Optional[Iterable[str]] = None,
        limit: int = 50,
    ) -> List[JobPosting]:
        feeds = self.config.get("feeds") or ["https://weworkremotely.com/remote-jobs.rss"]
        fetch_limit = self.max_items
        postings: List[JobPosting] = []
        for feed_url in feeds:
            if len(postings) >= fetch_limit:
                break
            response = self.session.get(feed_url, timeout=self.timeout)
            response.raise_for_status()
            postings.extend(
                self.parse_feed(
                    response.content,
                    limit=fetch_limit - len(postings),
                    description_max_chars=self.description_max_chars,
                    apply_mode=self.apply_mode,
                )
            )
        return postings[:fetch_limit]

    @classmethod
    def parse_feed(
        cls,
        content: Any,
        limit: int = 50,
        description_max_chars: int = 30000,
        apply_mode: str = "assisted",
    ) -> List[JobPosting]:
        parsed = feedparser.parse(content)
        if getattr(parsed, "bozo", False):
            log.warning("Feed RSS com problemas de parsing: %s", getattr(parsed, "bozo_exception", ""))

        postings: List[JobPosting] = []
        seen = set()
        for entry in parsed.entries[:limit]:
            link = entry.get("link") or entry.get("id") or ""
            job_id = _entry_job_id(link, fallback=str(entry.get("id") or ""))
            if not job_id or job_id in seen:
                continue
            seen.add(job_id)

            company, role = _split_title(entry.get("title", ""))
            skills = entry.get("skills") or ""
            tags = [tag.strip() for tag in re.split(r",| and ", str(skills)) if tag.strip()]
            for extra in (entry.get("category"), entry.get("type")):
                if extra and str(extra).strip() not in tags:
                    tags.append(str(extra).strip())

            description = entry.get("summary") or entry.get("description") or ""
            try:
                posting = JobPosting(
                    fonte=cls.name,
                    source_job_id=job_id,
                    url=link,
                    titulo=role,
                    empresa=company,
                    localizacao=_join_location(entry),
                    descricao=html_to_text(description, description_max_chars),
                    publicado_em=entry.get("published", ""),
                    tags=tags,
                    apply_mode=apply_mode,
                )
            except ValueError as exc:
                log.debug("RSS: vaga ignorada (%s)", exc)
                continue
            postings.append(posting)
        return postings
