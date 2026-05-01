from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Result:
    primary: str  # "A"/"B"/"C"/"D"
    secondary: str | None  # if tie for max


def compute_result(count_a: int, count_b: int, count_c: int, count_d: int) -> Result:
    counts = {"A": count_a, "B": count_b, "C": count_c, "D": count_d}
    max_count = max(counts.values())
    leaders = [k for k in ("A", "B", "C", "D") if counts[k] == max_count]
    primary = leaders[0]
    secondary = leaders[1] if len(leaders) >= 2 else None
    return Result(primary=primary, secondary=secondary)


def validate_channel_url(url: str) -> bool:
    u = (url or "").strip()
    if not u:
        return False
    if u.startswith("https://t.me/") or u.startswith("http://t.me/"):
        return True
    if u.startswith("https://telegram.me/") or u.startswith("http://telegram.me/"):
        return True
    if u.startswith("https://") or u.startswith("http://"):
        return True
    return False

