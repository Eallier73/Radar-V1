"""Contrato canónico y proyección histórica para Facebook en Radar V1."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Mapping
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


FACEBOOK_BASE_ACCOUNTS = ("monicavtampico", "tampicogob")
FACEBOOK_RAW_COLUMNS = (
    "tipo",
    "cuenta",
    "url",
    "post_url_padre",
    "fecha",
    "texto",
    "num_comentarios",
)
FACEBOOK_PROCESSED_COLUMNS = FACEBOOK_RAW_COLUMNS

LEGACY_ACCOUNT_IDS = {
    "964877296876825": "monicavtampico",
    "474462132406835": "tampicogob",
}

LEGACY_REQUIRED_COLUMNS = {"query_type", "message", "created_time", "object_id"}
CANONICAL_REQUIRED_COLUMNS = {
    "tipo",
    "url",
    "post_url_padre",
    "fecha",
    "texto",
    "num_comentarios",
}

NON_ACCOUNT_PATHS = {
    "reel",
    "watch",
    "photo.php",
    "permalink.php",
    "story.php",
}


def normalize_account(value: object) -> str:
    token = str(value or "").strip().lower().removeprefix("@").strip("/")
    if token in LEGACY_ACCOUNT_IDS:
        return LEGACY_ACCOUNT_IDS[token]
    compact = re.sub(r"[^a-z0-9]", "", token)
    aliases = {
        "monicavtampico": "monicavtampico",
        "tampicogob": "tampicogob",
    }
    return aliases.get(compact, token)


def account_from_url(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
    except ValueError:
        return ""
    if "facebook.com" not in parsed.netloc.lower():
        return ""
    first = (parsed.path or "").strip("/").split("/", 1)[0].lower()
    if not first or first in NON_ACCOUNT_PATHS:
        return ""
    return normalize_account(first)


def normalize_facebook_url(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
    except ValueError:
        return raw.rstrip("/")
    if "facebook.com" not in parsed.netloc.lower():
        return raw.rstrip("/")
    return urlunparse(
        (
            "https",
            "facebook.com",
            (parsed.path or "").rstrip("/"),
            "",
            "",
            "",
        )
    )


def normalize_facebook_comment_url(value: object) -> str:
    """Normaliza una URL sin perder los identificadores del comentario."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
    except ValueError:
        return raw.rstrip("/")
    if "facebook.com" not in parsed.netloc.lower():
        return raw.rstrip("/")
    identity_query = [
        (key.lower(), value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=False)
        if key.lower() in {"comment_id", "reply_comment_id"}
    ]
    identity_query.sort()
    return urlunparse(
        (
            "https",
            "facebook.com",
            (parsed.path or "").rstrip("/"),
            "",
            urlencode(identity_query),
            "",
        )
    )


def detect_facebook_schema(fieldnames: list[str] | tuple[str, ...]) -> str | None:
    fields = {str(field or "").strip().lower() for field in fieldnames}
    if LEGACY_REQUIRED_COLUMNS <= fields:
        return "legacy"
    if CANONICAL_REQUIRED_COLUMNS <= fields:
        return "canonical"
    return None


def normalize_absolute_datetime(value: str) -> tuple[str, str]:
    """Devuelve fecha ISO y estado: valid, unknown o invalid."""

    raw = (value or "").strip()
    if not raw or raw.lower() in {"desconocida", "unknown", "nan", "none", "null"}:
        return "", "unknown"

    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        pass

    if parsed is None:
        for fmt in ("%m/%d/%y %H:%M", "%m/%d/%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue

    if parsed is None:
        return "", "invalid"
    return parsed.isoformat(), "valid"


def _legacy_account(row: Mapping[str, str]) -> str:
    object_id = str(row.get("object_id", "") or "").strip().lower()
    for legacy_id, account in LEGACY_ACCOUNT_IDS.items():
        if object_id == legacy_id or object_id.startswith(f"{legacy_id}_"):
            return account

    path = str(row.get("path", "") or "").strip().lower()
    first_path_token = path.split("/", 1)[0]
    normalized_path_token = normalize_account(first_path_token)
    if normalized_path_token in FACEBOOK_BASE_ACCOUNTS:
        return normalized_path_token

    values = f"{object_id} {path} {row.get('object_key', '')}".lower()
    for legacy_id, account in LEGACY_ACCOUNT_IDS.items():
        if legacy_id in values:
            return account
    for account in FACEBOOK_BASE_ACCOUNTS:
        if account in values:
            return account
    return ""


def _legacy_post_url(account: str, object_id: str) -> str:
    value = (object_id or "").strip()
    if not account or not value:
        return ""
    post_id = value.split("_", 1)[-1]
    return f"https://www.facebook.com/{account}/posts/{post_id}"


def project_facebook_row(
    row: Mapping[str, str],
    *,
    schema: str,
    post_accounts: Mapping[str, str] | None = None,
) -> tuple[dict[str, str], str]:
    """Proyecta una fila y devuelve también el estado de su fecha."""

    if schema == "legacy":
        query_type = str(row.get("query_type", "") or "").lower()
        record_type = "COMENTARIO" if "comments" in query_type else "POST"
        account = _legacy_account(row)
        parent_url = _legacy_post_url(account, str(row.get("object_id", "") or ""))
        url = parent_url if record_type == "POST" else ""
        raw_date = str(row.get("created_time", "") or "")
        normalized_date, date_status = normalize_absolute_datetime(raw_date)
        projected = {
            "tipo": record_type,
            "cuenta": account,
            "url": url,
            "post_url_padre": "" if record_type == "POST" else parent_url,
            "fecha": normalized_date,
            "texto": str(row.get("message", "") or "").strip(),
            "num_comentarios": (
                str(row.get("comment_count", "") or "").strip()
                if record_type == "POST"
                else ""
            ),
        }
        return projected, date_status

    if schema != "canonical":
        raise ValueError(f"Esquema Facebook no soportado: {schema}")

    record_type = str(row.get("tipo", "") or "").strip().upper()
    url = (
        normalize_facebook_comment_url(row.get("url", ""))
        if record_type == "COMENTARIO"
        else normalize_facebook_url(row.get("url", ""))
    )
    parent_url = normalize_facebook_url(row.get("post_url_padre", ""))
    explicit = normalize_account(str(row.get("cuenta", "") or ""))
    account = explicit or account_from_url(url if record_type == "POST" else parent_url)
    if not account and post_accounts:
        account = normalize_account(post_accounts.get(parent_url or url, ""))
    raw_date = str(row.get("fecha", "") or "")
    normalized_date, date_status = normalize_absolute_datetime(raw_date)
    projected = {
        "tipo": record_type,
        "cuenta": account,
        "url": url,
        "post_url_padre": parent_url,
        "fecha": normalized_date,
        "texto": str(row.get("texto", "") or "").strip(),
        "num_comentarios": (
            str(row.get("num_comentarios", "") or "").strip()
            if record_type == "POST"
            else ""
        ),
    }
    return projected, date_status


def facebook_dedup_key(row: Mapping[str, str]) -> tuple[str, ...]:
    record_type = str(row.get("tipo", "") or "").strip().upper()
    url = str(row.get("url", "") or "").strip()
    parent_url = str(row.get("post_url_padre", "") or "").strip()
    normalized_parent = normalize_facebook_url(parent_url)
    if record_type == "POST" and url:
        return ("POST_URL", normalize_facebook_url(url))
    normalized_comment = normalize_facebook_comment_url(url)
    if (
        record_type == "COMENTARIO"
        and normalized_comment
        and normalized_comment != normalized_parent
    ):
        return ("COMMENT_URL", normalized_comment)
    normalized_text = re.sub(
        r"\s+",
        " ",
        str(row.get("texto", "") or "").strip().casefold(),
    )
    return (
        record_type,
        normalize_account(row.get("cuenta", "")),
        normalized_parent,
        str(row.get("fecha", "") or "").strip(),
        normalized_text,
    )
