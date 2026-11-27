"""BuildSite: asset fingerprint sentinel – rejects non-hex hashes."""
import re

HASH_RE = re.compile(r'^[0-9a-f]{8,64}$')


def validate_asset_fingerprint(fp: str) -> None:
    if not HASH_RE.match(fp):
        raise ValueError(f"invalid asset fingerprint: {fp!r}")
