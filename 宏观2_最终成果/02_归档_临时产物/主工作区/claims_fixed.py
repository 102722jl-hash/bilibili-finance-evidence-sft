"""Deterministic atomic-claim candidate extraction."""

from __future__ import annotations

import re

from .models import Claim


_DATE_RE = re.compile(r"(?P<year>20\d{2})年(?P<month>\d{1,2})月?")
_STOCK_RE = re.compile(r"(?<!\d)\d{6}(?!\d)")
_AMOUNT_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:亿元|万元|元|%|倍)")
_SENTENCE_BREAK = re.compile(r"[。！？?]+")
_CAUSAL_SPLIT = re.compile(r"[，,]\s*(因此|所以|从而|进而)")
_TEMPORAL_SPLIT = re.compile(r"[，,]\s*(随后|之后|此后)")
_AUTHOR_SPLIT = re.compile(r"[，,]\s*(作者认为|作者指出|这说明|这意味着|这就是)")
_MECHANISM_TERMS = ("价格不敏感", "杠杆", "流动性", "平仓", "信息不对称", "控制权", "抛压")
_ACTION_RE = re.compile(r"(买入|卖出|清理|发布|收购|持有|减持|处罚|触发|导致|放大)")


def _segments(text: str) -> list[tuple[str, str | None]]:
    result: list[tuple[str, str | None]] = []
    for sentence in _SENTENCE_BREAK.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        causal = _CAUSAL_SPLIT.search(sentence)
        temporal = _TEMPORAL_SPLIT.search(sentence)
        split_match = causal or temporal
        if split_match:
            left = sentence[: split_match.start()].strip(" ，,")
            right = sentence[split_match.end() :].strip(" ，,")
            if left:
                result.append((left, None))
            cue = split_match.group(1)
            author = _AUTHOR_SPLIT.search(right)
            if author:
                middle = right[: author.start()].strip(" ，,")
                conclusion = right[author.end() :].strip(" ，,")
                if middle:
                    result.append((middle, cue))
                if conclusion:
                    result.append((conclusion, author.group(1)))
            elif right:
                result.append((right, cue))
            continue
        result.append((sentence, None))
    return result


def _node_type(segment: str, cue: str | None) -> str:
    if segment.startswith(("作者认为", "作者指出", "作者将", "作者把")):
        return "C"
    if segment.startswith(("作者声称", "作者描述", "作者推测")):
        return "I"
    if cue in {"作者认为", "作者指出", "这说明", "这意味着", "这就是"}:
        return "C"
    if any(term in segment for term in _MECHANISM_TERMS):
        return "M"
    return "F"


def _metadata(segment: str, cue: str | None) -> tuple[str | None, str]:
    date_match = _DATE_RE.search(segment)
    event_time_start = None
    if date_match:
        event_time_start = f"{date_match.group('year')}-{int(date_match.group('month')):02d}"
    markers = [f"cue:{cue}"] if cue else []
    markers.extend(f"stock_codes:{code}" for code in _STOCK_RE.findall(segment))
    markers.extend(f"amounts:{amount}" for amount in _AMOUNT_RE.findall(segment))
    return event_time_start, ";".join(markers)


def _triplet(segment: str) -> tuple[str, str, str]:
    match = _ACTION_RE.search(segment)
    if not match:
        return "", "states", segment
    return segment[: match.start()].strip(), match.group(1), segment[match.end() :].strip()


def split_claims(text: str, video_id: str, source_ref: str | None = None) -> list[Claim]:
    claims: list[Claim] = []
    for index, (segment, cue) in enumerate(_segments(text), start=1):
        subject, predicate, object_ = _triplet(segment)
        event_time_start, notes = _metadata(segment, cue)
        claims.append(
            Claim(
                claim_id=f"{video_id}:C{index}",
                video_id=video_id,
                node_type=_node_type(segment, cue),
                subject=subject,
                predicate=predicate,
                object=object_,
                event_time_start=event_time_start,
                event_time_end=None,
                quote=segment,
                timestamp_start=None,
                timestamp_end=None,
                source_ref=source_ref,
                source_grade="S1",
                verification_status="unverifiable",
                notes=notes,
            )
        )
    return claims
