"""Adaptador do endpoint JSON público do Working Nomads."""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Iterable, List, Optional

from .base import JobPosting, JobSource, html_to_text

log = logging.getLogger(__name__)

_JOB_ID_RE = re.compile(r"/job/(?:go/)?(\d+)")


def _extract_job_id(url: str) -> str:
    match = _JOB_ID_RE.search(url or "")
    if match:
        return match.group(1)
    digest = hashlib.sha1((url or "").encode("utf-8")).hexdigest()
    return digest[:16]


class WorkingNomadsSource(JobSource):
    name = "workingnomads"
    label = "Working Nomads"
    apply_mode = "assisted"

    def fetch(
        self,
        keywords: Optional[Iterable[str]] = None,
        locations: Optional[Iterable[str]] = None,
        limit: int = 50,
    ) -> List[JobPosting]:
        url = self.config.get("url", "https://www.workingnomads.com/api/exposed_jobs/")
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return self.parse_payload(
            response.json(),
            limit=self.max_items,
            description_max_chars=self.description_max_chars,
            apply_mode=self.apply_mode,
        )

    @classmethod
    def parse_payload(
        cls,
        payload: Any,
        limit: int = 50,
        description_max_chars: int = 30000,
        apply_mode: str = "assisted",
    ) -> List[JobPosting]:
        if isinstance(payload, dict):
            jobs = payload.get("jobs", [])
        else:
            jobs = payload or []

        postings: List[JobPosting] = []
        seen = set()
        for job in jobs[:limit]:
            url = job.get("url", "")
            job_id = _extract_job_id(url)
            if not job_id or job_id in seen:
                continue
            seen.add(job_id)
            tags = job.get("tags") or []
            if isinstance(tags, str):
                tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
            try:
                posting = JobPosting(
                    fonte=cls.name,
                    source_job_id=job_id,
                    url=url,
                    titulo=job.get("title", ""),
                    empresa=job.get("company_name", ""),
                    localizacao=job.get("location", ""),
                    descricao=html_to_text(job.get("description", ""), description_max_chars),
                    publicado_em=job.get("pub_date", ""),
                    tags=tags,
                    apply_mode=apply_mode,
                    salary=job.get("salary", ""),
                )
            except ValueError as exc:
                log.debug("Working Nomads: vaga ignorada (%s)", exc)
                continue
            postings.append(posting)
        return postings
