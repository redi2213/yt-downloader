"""Plain-text helpers for the Arvan storage screens (no Kivy, no network)."""
import re

GIB = 1024 ** 3
MIB = 1024 ** 2

_NUMBERED = re.compile(r"^ARVAN_(\d+)_ACCESS_KEY$")
DEFAULT_ENDPOINT = "https://s3.ir-thr-at1.arvanstorage.ir"


def fmt_bytes(n) -> str:
    n = float(n or 0)
    if n >= GIB:
        return f"{n / GIB:.2f} GB"
    if n >= MIB:
        return f"{n / MIB:.1f} MB"
    return f"{n / 1024:.0f} KB"


def fmt_expiry(hours) -> str:
    """'3 days left' / '5 h left' / 'expired' from hours until deletion."""
    if hours is None:
        return ""
    if hours <= 0:
        return "expires at the next cleanup"
    if hours >= 48:
        return f"{hours / 24:.0f} days left"
    return f"{hours:.0f} h left"


def bucket_ids(secret_names) -> list:
    """Bucket ids found in the repository's secret names: 'main' first, then
    the numbered ones. Only buckets that have an access key count."""
    names = set(secret_names)
    ids = ["main"] if "ARVAN_ACCESS_KEY" in names else []
    numbers = sorted(int(m.group(1)) for n in names for m in [_NUMBERED.match(n)] if m)
    return ids + [str(n) for n in numbers]


def next_bucket_id(existing_ids) -> str:
    """The id a newly added bucket gets: 'main' if there is none yet,
    otherwise the next free number (2, 3, ...)."""
    existing = set(existing_ids)
    if "main" not in existing:
        return "main"
    used = [int(i) for i in existing if i.isdigit()]
    return str(max([1] + used) + 1)


def secret_prefix(bucket_id: str) -> str:
    return "ARVAN" if bucket_id == "main" else f"ARVAN_{bucket_id}"


def parse_quota(text, default=5.0) -> float:
    try:
        value = float(str(text).strip().replace(",", "."))
        return value if value > 0 else default
    except ValueError:
        return default
