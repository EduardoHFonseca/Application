"""Adaptador do motor LinkedIn existente (Playwright Easy Apply)."""

from __future__ import annotations

import logging
from typing import Iterable, List, Optional

from .base import JobPosting, JobSource

log = logging.getLogger(__name__)


class LinkedInSource(JobSource):
    name = "linkedin"
    label = "LinkedIn Easy Apply"
    apply_mode = "auto"
    requires_login = True
    can_auto_apply = True

    def fetch(
        self,
        keywords: Optional[Iterable[str]] = None,
        locations: Optional[Iterable[str]] = None,
        limit: int = 50,
    ) -> List[JobPosting]:
        # A descoberta do LinkedIn depende do motor Playwright e permanece em
        # playwright_bot.py (run_search_loop). Este adaptador cobre a aplicação.
        log.info("LinkedIn: descoberta via Playwright; nada a coletar pelo crawler HTTP.")
        return []

    def apply(self, posting: JobPosting, pdf_path: Optional[str] = None) -> bool:
        from playwright_bot import PlaywrightEasyApplyBot
        import database

        bot = PlaywrightEasyApplyBot()
        bot.start(target_url=posting.url)
        job = database.get_job_by_source("linkedin", posting.source_job_id)
        return bool(job and job.get("status") == "aplicado")
