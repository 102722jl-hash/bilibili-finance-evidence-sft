"""Public WeChat article ingestion with explicit CAPTCHA handling."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .bilibili import SourceBlocked


@dataclass(frozen=True)
class ArticleRecord:
    title: str
    author: str
    text: str
    paragraphs: tuple[str, ...]
    url: str
    retrieved_at: str | None = None
    raw_sha256: str | None = None


_BLOCK_MARKERS = ("验证码", "VerifyCode", "访问验证", "安全验证", "请完成验证")
_STRUCTURAL_BLOCK_MARKERS = ("secitptpage/verify", 'id="js_verify"', "TCaptcha.js")


def _ensure_public_wechat(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname != "mp.weixin.qq.com":
        raise ValueError("url must be a public mp.weixin.qq.com article")


def parse_article(html: str, url: str) -> ArticleRecord:
    if any(marker in html for marker in (*_BLOCK_MARKERS, *_STRUCTURAL_BLOCK_MARKERS)):
        raise SourceBlocked("wechat article returned a captcha page")
    _ensure_public_wechat(url)
    soup = BeautifulSoup(html, "html.parser")
    title_node = soup.select_one("#activity-name") or soup.find("h1") or soup.find("title")
    author_node = soup.select_one("#js_name") or soup.select_one(".profile_nickname")
    content = soup.select_one("#js_content")
    paragraphs = tuple(
        node.get_text(" ", strip=True)
        for node in (content.find_all("p") if content else [])
        if node.get_text(" ", strip=True)
    )
    if not paragraphs and content:
        text = content.get_text("\n", strip=True)
        paragraphs = tuple(line.strip() for line in text.splitlines() if line.strip())
    return ArticleRecord(
        title=title_node.get_text(" ", strip=True) if title_node else "",
        author=author_node.get_text(" ", strip=True) if author_node else "",
        text="\n\n".join(paragraphs),
        paragraphs=paragraphs,
        url=url,
        raw_sha256=hashlib.sha256(html.encode("utf8")).hexdigest(),
    )


def fetch_article(url: str, out_dir: str | Path, timeout: float = 20.0) -> ArticleRecord:
    _ensure_public_wechat(url)
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "evidence-chain/0.1 (public research; contact user)"},
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SourceBlocked(f"wechat article request failed: {exc}") from exc
    record = parse_article(response.text, url)
    retrieved_at = datetime.now(timezone.utc).isoformat()
    record = ArticleRecord(**{**asdict(record), "retrieved_at": retrieved_at})
    article_id = hashlib.sha256(url.encode("utf8")).hexdigest()[:16]
    target = Path(out_dir) / "raw" / "wechat" / article_id
    target.mkdir(parents=True, exist_ok=True)
    (target / "page.html").write_text(response.text, encoding="utf8")
    (target / "metadata.json").write_text(json.dumps(asdict(record), ensure_ascii=False, indent=2), encoding="utf8")
    return record
