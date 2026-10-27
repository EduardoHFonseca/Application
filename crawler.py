"""Orquestrador do crawler multi-fonte do projeto Application.

Pipeline: descoberta -> normalização -> filtro -> dedupe -> persistência ->
(geração opcional de CV) -> notificação.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

import database
from ai_brain import AIBrain
from sources import (
    JobPosting,
    build_source,
    default_keywords,
    default_locations,
    enabled_source_names,
    load_config,
    source_summary,
)
from sources.base import normalize_text
from telegram_bot import TelegramHumanFeedback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE_DIR, ".cache", "crawler_state.json")
CUSTOM_CV_DIR = os.path.join(BASE_DIR, "custom_cvs")

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Estado / agendamento
# ---------------------------------------------------------------------------

def load_state(path: str = STATE_PATH) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle) or {}
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Estado do crawler ilegível (%s); reiniciando.", exc)
        return {}


def save_state(state: Dict[str, Any], path: str = STATE_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _parse_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def source_is_due(
    name: str,
    min_interval_hours: float,
    state: Dict[str, Any],
    now: Optional[datetime] = None,
) -> bool:
    if min_interval_hours <= 0:
        return True
    last_run = _parse_datetime((state.get("last_run") or {}).get(name, ""))
    if last_run is None:
        return True
    now = now or datetime.now(timezone.utc)
    return now - last_run >= timedelta(hours=min_interval_hours)


# ---------------------------------------------------------------------------
# Normalização / dedupe / score
# ---------------------------------------------------------------------------

def dedupe_postings(postings: Iterable[JobPosting]) -> List[JobPosting]:
    """Remove duplicatas do lote por id de origem e por título + empresa."""
    unique: List[JobPosting] = []
    seen_source = set()
    seen_content = set()
    for posting in postings:
        if posting.hash_source in seen_source or posting.hash_dedupe in seen_content:
            continue
        seen_source.add(posting.hash_source)
        seen_content.add(posting.hash_dedupe)
        unique.append(posting)
    return unique


def fit_score(posting: JobPosting, keywords: Optional[Iterable[str]]) -> int:
    """Score determinístico (sem LLM) para priorizar o que será processado."""
    terms = [normalize_text(term) for term in (keywords or []) if str(term).strip()]
    if not terms:
        return 0
    title = normalize_text(posting.titulo)
    tags = normalize_text(" ".join(posting.tags))
    description = normalize_text(posting.descricao[:6000])
    score = 0
    for term in terms:
        if term in title:
            score += 30
        elif term in tags:
            score += 20
        elif term in description:
            score += 10
    return min(score, 100)


# ---------------------------------------------------------------------------
# Geração de CV / notificação
# ---------------------------------------------------------------------------

def _safe_filename(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")[:80]


def generate_cv(posting: JobPosting) -> str:
    competencias = AIBrain.get_competencias_context()
    data = AIBrain.customize_cv_text(competencias, posting.titulo, posting.descricao)
    os.makedirs(CUSTOM_CV_DIR, exist_ok=True)
    filename = f"{posting.fonte}-{_safe_filename(posting.source_job_id)}.pdf"
    output_path = os.path.join(CUSTOM_CV_DIR, filename)
    AIBrain.generate_pdf(data, output_path)
    return output_path


def notify_summary(summary: Dict[str, Any], limit: int = 10) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        log.info("Telegram não configurado; resumo mantido apenas no log.")
        return

    new_postings = summary.get("new_postings") or []
    lines = [
        f"🔎 Crawler multi-fonte: {summary.get('new', 0)} nova(s) vaga(s), "
        f"{summary.get('cvs', 0)} CV(s) gerado(s)."
    ]
    for item in new_postings[:limit]:
        lines.append(
            f"• [{item['fonte']}] {item['titulo']} — {item['empresa']}\n  {item['url']}"
        )
    if len(new_postings) > limit:
        lines.append(f"... e mais {len(new_postings) - limit} vaga(s).")
    try:
        TelegramHumanFeedback.send_telegram_message(token, chat_id, "\n".join(lines))
    except Exception as exc:
        log.warning("Falha ao notificar via Telegram: %s", exc)


# ---------------------------------------------------------------------------
# Coleta
# ---------------------------------------------------------------------------

def collect(
    source_names: Optional[Sequence[str]] = None,
    keywords: Optional[Sequence[str]] = None,
    locations: Optional[Sequence[str]] = None,
    limit: Optional[int] = None,
    with_cv: bool = False,
    dry_run: bool = False,
    ignore_schedule: bool = False,
    notify: bool = True,
    config: Optional[Dict[str, Any]] = None,
    state_path: str = STATE_PATH,
) -> Dict[str, Any]:
    config = config or load_config()
    keywords = list(keywords) if keywords else default_keywords(config)
    locations = list(locations) if locations else default_locations(config)
    limit = int(limit or (config.get("defaults") or {}).get("limit", 50))
    names = list(source_names) if source_names else enabled_source_names(config)

    state = load_state(state_path)
    summary: Dict[str, Any] = {
        "keywords": keywords,
        "locations": locations,
        "sources": {},
        "new": 0,
        "cvs": 0,
        "skipped": 0,
        "postings": [],
        "new_postings": [],
    }

    for name in names:
        source_summary_entry: Dict[str, Any] = {
            "fetched": 0,
            "matched": 0,
            "new": 0,
            "skipped": 0,
            "error": "",
            "skipped_reason": "",
        }
        summary["sources"][name] = source_summary_entry

        try:
            source = build_source(name, config=config)
        except (KeyError, NotImplementedError) as exc:
            source_summary_entry["error"] = str(exc)
            log.warning("Fonte '%s' ignorada: %s", name, exc)
            continue

        try:
            if not ignore_schedule and not source_is_due(name, source.min_interval_hours, state):
                source_summary_entry["skipped_reason"] = "intervalo mínimo não atingido"
                log.info(
                    "Fonte '%s' pulada: intervalo mínimo de %.1fh não atingido.",
                    name,
                    source.min_interval_hours,
                )
                continue

            try:
                fetched = source.fetch(keywords=keywords, locations=locations, limit=limit)
            except Exception as exc:
                source_summary_entry["error"] = f"fetch: {exc}"
                log.exception("Falha ao coletar da fonte '%s'", name)
                continue

            source_summary_entry["fetched"] = len(fetched)
            matched = source.filter_postings(fetched, keywords=keywords, locations=locations)[:limit]
            matched.sort(key=lambda posting: fit_score(posting, keywords), reverse=True)
            matched = dedupe_postings(matched)
            source_summary_entry["matched"] = len(matched)

            for posting in matched:
                if dry_run:
                    summary["postings"].append(posting)
                    continue

                job_id, created = database.save_posting(posting, status="descoberto")
                if created:
                    summary["new"] += 1
                    source_summary_entry["new"] += 1
                    summary["new_postings"].append(
                        {
                            "id": job_id,
                            "fonte": posting.fonte,
                            "titulo": posting.titulo,
                            "empresa": posting.empresa,
                            "url": posting.url,
                            "score": fit_score(posting, keywords),
                        }
                    )
                else:
                    summary["skipped"] += 1
                    source_summary_entry["skipped"] += 1

                if created and with_cv:
                    try:
                        pdf_path = generate_cv(posting)
                        database.update_job_status(job_id, "cv_gerado", pdf_path)
                        summary["cvs"] += 1
                    except Exception as exc:
                        log.exception("Falha ao gerar CV para %s/%s", posting.fonte, posting.source_job_id)

            if not dry_run:
                state.setdefault("last_run", {})[name] = datetime.now(timezone.utc).isoformat()
        finally:
            source.close()

    if not dry_run:
        save_state(state, state_path)

    if notify and not dry_run and summary["new"]:
        notify_summary(summary)

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_sources(config: Optional[Dict[str, Any]] = None) -> None:
    rows = source_summary(config)
    print(f"{'FONTE':<16} {'ATIVA':<6} {'PARSER':<8} {'MODO':<10} RÓTULO")
    for row in rows:
        print(
            f"{row['name']:<16} "
            f"{'sim' if row['enabled'] else 'não':<6} "
            f"{'sim' if row['implemented'] else 'não':<8} "
            f"{row['apply_mode']:<10} "
            f"{row['label']}"
        )


def _print_dry_run(summary: Dict[str, Any], limit: int = 40) -> None:
    postings = summary.get("postings") or []
    print(f"\n{len(postings)} vaga(s) encontrada(s) (dry-run, nada foi gravado):\n")
    for posting in postings[:limit]:
        print(
            f"[{posting.fonte}] {posting.titulo} — {posting.empresa} "
            f"({posting.localizacao or 'n/d'})\n  {posting.url}"
        )
    if len(postings) > limit:
        print(f"... e mais {len(postings) - limit} vaga(s).")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Crawler multi-fonte do projeto Application (LinkedIn, Remotive, WWR, Working Nomads)."
    )
    parser.add_argument("-s", "--source", action="append", default=[], help="Fonte a coletar (repetível)")
    parser.add_argument("-a", "--all", action="store_true", help="Coleta de todas as fontes habilitadas")
    parser.add_argument("-k", "--keywords", type=str, help="Cargos separados por vírgula")
    parser.add_argument("-l", "--locations", type=str, help="Localizações separadas por vírgula")
    parser.add_argument("-n", "--limit", type=int, help="Limite de vagas por fonte")
    parser.add_argument("--with-cv", action="store_true", help="Gera CV personalizado para cada vaga nova")
    parser.add_argument("--dry-run", action="store_true", help="Somente lista as vagas; não grava no banco")
    parser.add_argument("--ignore-schedule", action="store_true", help="Ignora o intervalo mínimo por fonte")
    parser.add_argument("--no-notify", action="store_true", help="Não envia resumo ao Telegram")
    parser.add_argument("--list-sources", action="store_true", help="Lista o catálogo de fontes e sai")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    config = load_config()

    if args.list_sources:
        _print_sources(config)
        return 0

    names = None
    if not args.all and args.source:
        names = args.source
    elif args.all:
        names = enabled_source_names(config)

    keywords = [item.strip() for item in args.keywords.split(",")] if args.keywords else None
    locations = [item.strip() for item in args.locations.split(",")] if args.locations else None

    summary = collect(
        source_names=names,
        keywords=keywords,
        locations=locations,
        limit=args.limit,
        with_cv=args.with_cv,
        dry_run=args.dry_run,
        ignore_schedule=args.ignore_schedule,
        notify=not args.no_notify,
        config=config,
    )

    if args.dry_run:
        _print_dry_run(summary)
        return 0

    print("\nResumo da coleta:")
    for name, info in summary["sources"].items():
        if info.get("error"):
            print(f"  {name}: ERRO — {info['error']}")
        elif info.get("skipped_reason"):
            print(f"  {name}: pulada — {info['skipped_reason']}")
        else:
            print(
                f"  {name}: {info['fetched']} coletadas, {info['matched']} filtradas, "
                f"{info['new']} novas, {info['skipped']} já conhecidas"
            )
    print(
        f"\nTotal: {summary['new']} nova(s), {summary['cvs']} CV(s), "
        f"{summary['skipped']} duplicada(s)/já conhecida(s)."
    )

    failed = [name for name, info in summary["sources"].items() if info.get("error")]
    return 1 if failed and len(failed) == len(summary["sources"]) else 0


if __name__ == "__main__":
    sys.exit(main())
