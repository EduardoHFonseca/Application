"""Fonte somente-link (marketplaces): registra a vaga e delega o envio ao humano."""

from __future__ import annotations

import logging
from typing import Iterable, List, Optional

from .base import JobPosting, JobSource

log = logging.getLogger(__name__)


class LinkOnlySource(JobSource):
    apply_mode = "link_only"
    requires_login = True

    def fetch(
        self,
        keywords: Optional[Iterable[str]] = None,
        locations: Optional[Iterable[str]] = None,
        limit: int = 50,
    ) -> List[JobPosting]:
        log.info("%s: fonte somente-link; descoberta manual nesta fase.", self.label)
        return []
