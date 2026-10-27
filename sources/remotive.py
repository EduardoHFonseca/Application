"""Adaptador da API pública do Remotive."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from .base import JobPosting, JobSource, html_to_text

log = logging.getLogger(__name__)


class RemotiveSource(JobSource):
    name = "remotive"
    label = "Remotive"
    apply_mode = "assisted"

    def fetch(
        self,
        keywords: Optional[Iterable[str]] = None,
        locations: Optional[Iterable[str]] = None,
        limit: int = 50,
    ) -> List[JobPosting]:
        url = self.config.get("url", "https://remotive.com/api/remote-jobs")
        params = {"limit": self.max_items}
        response = self.session.get(url, params=params, timeout=self.timeout)
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
        payload: Dict[str, Any],
        limit: int = 50,
        description_max_chars: int = 30000,
        apply_mode: str = "assisted",
    ) -> List[JobPosting]:
        postings: List[JobPosting] = []
        seen = set()
        for job in (payload or {}).get("jobs", [])[:limit]:
            job_id = job.get("id")
            if job_id is None or str(job_id) in seen:
                continue
            seen.add(str(job_id))
            tags = job.get("tags") or []
            if isinstance(tags, str):
                tags = [tag.strip() for tag in tags.split(",")]
            try:
                posting = JobPosting(
                    fonte=cls.name,
                    source_job_id=str(job_id),
                    url=job.get("url", ""),
                    titulo=job.get("title", ""),
                    empresa=job.get("company_name", ""),
                    localizacao=job.get("candidate_required_location", ""),
                    descricao=html_to_text(job.get("description", ""), description_max_chars),
                    publicado_em=job.get("publication_date", ""),
                    tags=tags,
                    apply_mode=apply_mode,
                    salary=job.get("salary", ""),
                )
            except ValueError as exc:
                log.debug("Remotive: vaga ignorada (%s)", exc)
                continue
            postings.append(posting)
        return postings
