"""Contrato común para material semanal de Twitter/X."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Mapping, Sequence


TWITTER_OUTPUT_COLUMNS = (
    "tweet_id",
    "author",
    "published_at",
    "url",
    "text",
    "replies",
    "retweets",
    "likes",
    "bookmarks",
    "views",
    "query_raw",
    "is_reply",
)

TWITTER_SEARCH_QUERIES = (
    "to:MonicaVTampico",
    "from:MonicaVTampico",
    "to:TampicoGob",
    "from:TampicoGob",
    "@TampicoGob",
    "@MonicaVTampico",
)

CURRENT_SCHEMA_REQUIRED = {
    "author",
    "datetime",
    "datetime_parsed_utc",
    "url",
    "text",
    "query_used",
}
PROVIDER_SCHEMA_REQUIRED = {
    "Query_Str",
    "Author_Handle",
    "UTC_Time",
    "Tweet_Content",
    "Post_ID",
    "Tweet_URL",
}
CANONICAL_SCHEMA_REQUIRED = set(TWITTER_OUTPUT_COLUMNS)


def detect_twitter_schema(fieldnames: Sequence[str]) -> str | None:
    columns = set(fieldnames)
    if CANONICAL_SCHEMA_REQUIRED.issubset(columns):
        return "canonical_12_columns"
    if CURRENT_SCHEMA_REQUIRED.issubset(columns):
        return "radar_15_columns"
    if PROVIDER_SCHEMA_REQUIRED.issubset(columns):
        return "provider_24_columns"
    return None


def parse_twitter_datetime(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for date_format in ("%m/%d/%y %H:%M", "%m/%d/%Y %H:%M"):
            try:
                parsed = datetime.strptime(text, date_format)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_metric(value: object) -> str:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return ""
    try:
        return str(int(text))
    except ValueError:
        return ""


def normalize_bool(value: object) -> str:
    text = str(value or "").strip().casefold()
    return "true" if text in {"1", "true", "yes", "si", "sí"} else "false"


def normalize_author(value: object) -> str:
    text = str(value or "").strip()
    if text and not text.startswith("@") and re.fullmatch(r"[A-Za-z0-9_]+", text):
        return f"@{text}"
    return text


def tweet_id_from_values(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        match = re.search(r"/status/(\d+)", text)
        if match:
            return match.group(1)
        if text.isdigit():
            return text
    return ""


def _utc_iso(value: object) -> str:
    parsed = parse_twitter_datetime(str(value or ""))
    return parsed.isoformat() if parsed is not None else ""


def project_twitter_row(
    row: Mapping[str, object],
    *,
    schema: str,
) -> dict[str, str]:
    if schema == "radar_15_columns":
        published_at = row.get("datetime_parsed_utc") or row.get("datetime")
        projected = {
            "tweet_id": tweet_id_from_values(row.get("url")),
            "author": normalize_author(row.get("author")),
            "published_at": _utc_iso(published_at),
            "url": str(row.get("url") or "").strip(),
            "text": str(row.get("text") or "").strip(),
            "replies": normalize_metric(row.get("replies")),
            "retweets": normalize_metric(row.get("retweets")),
            "likes": normalize_metric(row.get("likes")),
            "bookmarks": normalize_metric(row.get("bookmarks")),
            "views": normalize_metric(row.get("views")),
            "query_raw": str(row.get("query_used") or "").strip(),
            "is_reply": normalize_bool(row.get("is_reply")),
        }
    elif schema == "provider_24_columns":
        projected = {
            "tweet_id": tweet_id_from_values(row.get("Post_ID"), row.get("Tweet_URL")),
            "author": normalize_author(row.get("Author_Handle")),
            "published_at": _utc_iso(row.get("UTC_Time")),
            "url": str(row.get("Tweet_URL") or "").strip(),
            "text": str(row.get("Tweet_Content") or "").strip(),
            "replies": normalize_metric(row.get("Reply_Count")),
            "retweets": normalize_metric(row.get("Repost_Count")),
            "likes": normalize_metric(row.get("Like_Count")),
            "bookmarks": normalize_metric(row.get("Bookmark_Count")),
            "views": normalize_metric(row.get("View_Count")),
            "query_raw": str(row.get("Query_Str") or "").strip(),
            "is_reply": normalize_bool(row.get("Replying_to")),
        }
    elif schema == "canonical_12_columns":
        projected = {
            "tweet_id": tweet_id_from_values(row.get("tweet_id"), row.get("url")),
            "author": normalize_author(row.get("author")),
            "published_at": _utc_iso(row.get("published_at")),
            "url": str(row.get("url") or "").strip(),
            "text": str(row.get("text") or "").strip(),
            "replies": normalize_metric(row.get("replies")),
            "retweets": normalize_metric(row.get("retweets")),
            "likes": normalize_metric(row.get("likes")),
            "bookmarks": normalize_metric(row.get("bookmarks")),
            "views": normalize_metric(row.get("views")),
            "query_raw": str(row.get("query_raw") or "").strip(),
            "is_reply": normalize_bool(row.get("is_reply")),
        }
    else:
        raise ValueError(f"Esquema Twitter no soportado: {schema}")
    return {column: projected.get(column, "") for column in TWITTER_OUTPUT_COLUMNS}


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", " ", text).strip().casefold()


def fold_text(value: object) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    without_accents = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    return without_accents.casefold()


def text_contains_tampico(value: object) -> bool:
    """Aplica la regla histórica uniforme sobre el texto observable."""
    return bool(
        re.search(
            r"(?<![a-z0-9_])tampico(?![a-z0-9_])",
            fold_text(value),
        )
    )


def normalize_twitter_query(value: object) -> str:
    query = str(value or "").strip()
    query = re.sub(
        r"\s+since:\d{4}-\d{2}-\d{2}\s+until:\d{4}-\d{2}-\d{2}\s*$",
        "",
        query,
        flags=re.IGNORECASE,
    ).strip()
    if len(query) >= 2 and query[0] == query[-1] == '"':
        query = query[1:-1].strip()
    return query.replace("@@", "@")


def twitter_query_targets_accounts(value: object) -> bool:
    query = normalize_twitter_query(value)
    folded = fold_text(query).strip()
    if folded in {fold_text(item) for item in TWITTER_SEARCH_QUERIES}:
        return True
    return (
        "@tampicogob" in folded
        and "@monicavtampico" in folded
        and bool(re.search(r"\bor\b", folded))
    )


def twitter_reply_parent_url(value: object) -> str:
    query = normalize_twitter_query(value)
    if query.casefold().startswith("reply_to:"):
        return query[len("reply_to:"):].strip()
    return ""


def filter_twitter_rows_to_account_scope(
    rows: Sequence[Mapping[str, object]],
) -> tuple[list[dict[str, object]], int]:
    parent_urls = {
        str(row.get("url") or "").strip()
        for row in rows
        if twitter_query_targets_accounts(row.get("query_raw"))
        and str(row.get("url") or "").strip()
    }
    kept: list[dict[str, object]] = []
    for row in rows:
        query = row.get("query_raw")
        parent_url = twitter_reply_parent_url(query)
        if twitter_query_targets_accounts(query) or (
            parent_url and parent_url in parent_urls
        ):
            kept.append(dict(row))
    return kept, len(rows) - len(kept)


def deduplicate_twitter_rows(
    rows: Sequence[Mapping[str, object]],
) -> tuple[list[dict[str, object]], int]:
    """Deduplica por tweet_id y usa autor+fecha+texto cuando falta el ID."""
    seen: set[tuple[str, ...]] = set()
    unique: list[dict[str, object]] = []
    for row in rows:
        tweet_id = str(row.get("tweet_id") or "").strip()
        if tweet_id:
            key = ("tweet_id", tweet_id)
        else:
            key = (
                "fallback",
                normalize_text(row.get("author")),
                str(row.get("published_at") or "").strip(),
                normalize_text(row.get("text")),
            )
        if key in seen:
            continue
        seen.add(key)
        unique.append(dict(row))
    return unique, len(rows) - len(unique)
