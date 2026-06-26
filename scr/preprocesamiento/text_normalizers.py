#!/usr/bin/env python3
from __future__ import annotations

import re
import string
import unicodedata


URL_RE = re.compile(r"https?://\S+|www\.\S+", flags=re.IGNORECASE)
DOMAIN_RE = re.compile(r"\b[\w-]+(?:\.[\w-]+)+\b", flags=re.IGNORECASE)
WHITESPACE_RE = re.compile(r"\s+")


def _to_ascii(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return normalized.encode("ascii", "ignore").decode("ascii")


def _collapse_spaces(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def normalize_facebook(text: str) -> str:
    value = (text or "").lower()
    value = URL_RE.sub(" ", value)
    value = DOMAIN_RE.sub(" ", value)
    value = re.sub(r"@\w+", " ", value)
    value = re.sub(r"#(\w+)", r" \1 ", value)
    value = re.sub(r"\bhttp\b|\bhttps\b|\bcom\b", " ", value)
    value = re.sub(r"\bfacebook\b|\bfb\b", " ", value)
    value = re.sub(r"\bme gusta\b|\bcompartir\b", " ", value)
    value = _to_ascii(value)
    value = re.sub(r"[" + re.escape(string.punctuation + string.digits) + "]", " ", value)
    return _collapse_spaces(value)


def normalize_twitter(text: str) -> str:
    value = (text or "").lower()
    value = URL_RE.sub(" ", value)
    value = DOMAIN_RE.sub(" ", value)
    value = re.sub(r"@\w+", " ", value)
    value = re.sub(r"#(\w+)", r" \1 ", value)
    value = re.sub(r"\bhttp\b|\bhttps\b|\bcom\b", " ", value)
    value = re.sub(r"\brt\b|\bvia\b", " ", value)
    value = _to_ascii(value)
    value = re.sub(r"[" + re.escape(string.punctuation + string.digits) + "]", " ", value)
    return _collapse_spaces(value)


def normalize_youtube(text: str) -> str:
    value = (text or "").lower()
    value = URL_RE.sub(" ", value)
    value = re.sub(r"\bhttp\b|\bhttps\b|\bcom\b", " ", value)
    value = _to_ascii(value)
    value = re.sub(r"[" + re.escape(string.punctuation + string.digits) + "]", " ", value)
    return _collapse_spaces(value)


def normalize_medios(text: str) -> str:
    value = (text or "").lower()
    value = URL_RE.sub(" ", value)
    value = DOMAIN_RE.sub(" ", value)
    value = _to_ascii(value)
    value = re.sub(r"\d+", " ", value)
    value = re.sub(r"[^a-z\s]", " ", value)
    return _collapse_spaces(value)


NORMALIZERS = {
    "facebook": normalize_facebook,
    "twitter": normalize_twitter,
    "youtube": normalize_youtube,
    "medios": normalize_medios,
}


def normalize_for_source(source: str, text: str) -> str:
    try:
        normalizer = NORMALIZERS[source]
    except KeyError as exc:
        raise ValueError(f"Fuente sin normalizador: {source}") from exc
    return normalizer(text)
