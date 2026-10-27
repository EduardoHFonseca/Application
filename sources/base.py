"""Contratos e utilitários compartilhados pelos adaptadores de fontes de vagas."""

from __future__ import annotations

import hashlib
import html as html_lib
import re
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "ref",
    "referrer",
    "referer",
    "source",
    "trk",
    "trackingid",
    "position",
    "p",
    "originalsubdomain",
    "gh_src",
    "lever-source",
    "lever-origin",
}

REMOTE_HINTS = (
    "remote",
    "remoto",
    "anywhere",
    "worldwide",
    "global",
    "latam",
    "distributed",
    "home office",
    "homeoffice",
)


def normalize_text(value: str) -> str:
    """Minúsculas, sem acentos e sem pontuação — usado em filtros e dedupe."""
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value))
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")


def html_to_text(value: str, max_chars: int = 30000) -> str:
    """Converte HTML de descrição em texto limpo, preservando parágrafos."""
    if not value:
        return ""
    soup = BeautifulSoup(str(value), "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text("\n")
    text = html_lib.unescape(text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    cleaned = "\n".join(line for line in lines if line)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned[:max_chars]


def canonicalize_url(url: str) -> str:
    """URL canônica para deduplicação (não é a URL exibida ao usuário)."""
    if not url:
        return ""
    parts = urlsplit(url.strip())
    scheme = "https" if parts.scheme in ("http", "https", "") else parts.scheme
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=False)
        if key.lower() not in TRACKING_PARAMS
    ]
    path = re.sub(r"/{2,}", "/", parts.path)
    if path.endswith("/") and len(path) > 1:
        path = path.rstrip("/")
    return urlunsplit((scheme, netloc, path, urlencode(sorted(query)), ""))


@dataclass
class JobPosting:
    """Vaga normalizada, independente do site de origem."""

    fonte: str
    source_job_id: str
    url: str
    titulo: str = ""
    empresa: str = ""
    localizacao: str = ""
    descricao: str = ""
    publicado_em: str = ""
    tags: List[str] = field(default_factory=list)
    apply_mode: str = "assisted"
    salary: str = ""
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        self.fonte = slugify(self.fonte)
        self.source_job_id = str(self.source_job_id or "").strip()
        self.url = (self.url or "").strip()
        self.titulo = (self.titulo or "").strip()
        self.empresa = (self.empresa or "").strip()
        self.localizacao = (self.localizacao or "").strip()
        self.publicado_em = str(self.publicado_em or "").strip()
        self.salary = str(self.salary or "").strip()
        self.tags = [str(tag).strip() for tag in (self.tags or []) if str(tag).strip()]
        if not self.fonte:
            raise ValueError("JobPosting.fonte é obrigatório")
        if not self.source_job_id:
            raise ValueError(f"JobPosting.source_job_id é obrigatório ({self.url})")
        if not self.url:
            raise ValueError(f"JobPosting.url é obrigatório ({self.fonte}/{self.source_job_id})")
        if not self.titulo:
            raise ValueError(f"JobPosting.titulo é obrigatório ({self.fonte}/{self.source_job_id})")

    @property
    def canonical_url(self) -> str:
        return canonicalize_url(self.url)

    @property
    def hash_source(self) -> str:
        """Chave de idempotência por fonte + id nativo."""
        return hashlib.sha256(f"{self.fonte}|{self.source_job_id}".encode("utf-8")).hexdigest()

    @property
    def hash_dedupe(self) -> str:
        """Chave de deduplicação cruzada entre fontes (título + empresa)."""
        company = normalize_text(self.empresa)
        if not company:
            company = normalize_text(self.localizacao) or urlsplit(self.canonical_url).netloc
        return hashlib.sha256(f"{normalize_text(self.titulo)}|{company}".encode("utf-8")).hexdigest()

    def to_db(self) -> Dict[str, Any]:
        return {
            "fonte": self.fonte,
            "source_job_id": self.source_job_id,
            "url": self.url,
            "titulo": self.titulo,
            "empresa": self.empresa,
            "localizacao": self.localizacao,
            "descricao": self.descricao,
            "apply_mode": self.apply_mode,
            "hash_dedupe": self.hash_dedupe,
        }


class JobSource(ABC):
    """Interface comum a todos os sites suportados."""

    name: str = ""
    label: str = ""
    apply_mode: str = "assisted"
    requires_login: bool = False
    can_auto_apply: bool = False
    min_interval_hours: float = 0.0

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = dict(config or {})
        self.name = self.config.get("name", self.name)
        self.label = self.config.get("label", self.label or self.name)
        self.apply_mode = self.config.get("apply_mode", self.apply_mode)
        self.requires_login = bool(self.config.get("requires_login", self.requires_login))
        self.can_auto_apply = bool(self.config.get("can_auto_apply", self.can_auto_apply))
        self.min_interval_hours = float(self.config.get("min_interval_hours", self.min_interval_hours))
        self.timeout = int(self.config.get("request_timeout", 20))
        self.max_items = int(self.config.get("max_items", 500))
        self.user_agent = self.config.get(
            "user_agent", "ApplicationCrawler/1.0 (+https://github.com/EduardoHFonseca/Application)"
        )
        self.description_max_chars = int(self.config.get("description_max_chars", 30000))
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent, "Accept": "*/*"})

    @abstractmethod
    def fetch(
        self,
        keywords: Optional[Iterable[str]] = None,
        locations: Optional[Iterable[str]] = None,
        limit: int = 50,
    ) -> List[JobPosting]:
        """Retorna as vagas disponíveis na fonte (sem aplicar filtros locais)."""

    def apply(self, posting: JobPosting, pdf_path: Optional[str] = None) -> bool:
        raise NotImplementedError(f"A fonte '{self.name}' não suporta candidatura automática")

    def close(self):
        self.session.close()

    # --- filtros locais (fontes sem busca nativa) ---

    @staticmethod
    def matches_keywords(posting: JobPosting, keywords: Optional[Iterable[str]]) -> bool:
        terms = [normalize_text(term) for term in (keywords or []) if str(term).strip()]
        if not terms:
            return True
        title_and_tags = normalize_text(" ".join([posting.titulo, " ".join(posting.tags)]))
        if any(term in title_and_tags for term in terms):
            return True
        # Menção isolada na descrição gera muito ruído; exige ao menos três
        # palavras-chave distintas para aceitar a vaga.
        description = normalize_text(posting.descricao[:6000])
        return sum(1 for term in terms if term in description) >= 3

    @staticmethod
    def matches_locations(posting: JobPosting, locations: Optional[Iterable[str]]) -> bool:
        terms = [normalize_text(term) for term in (locations or []) if str(term).strip()]
        if not terms:
            return True
        location = normalize_text(posting.localizacao)
        if not location:
            return True
        if any(hint in location for hint in REMOTE_HINTS):
            return True
        return any(term in location for term in terms)

    def filter_postings(
        self,
        postings: Iterable[JobPosting],
        keywords: Optional[Iterable[str]] = None,
        locations: Optional[Iterable[str]] = None,
    ) -> List[JobPosting]:
        return [
            posting
            for posting in postings
            if self.matches_keywords(posting, keywords) and self.matches_locations(posting, locations)
        ]

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r} apply_mode={self.apply_mode!r}>"
