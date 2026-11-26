"""Asset manifest entry contract validator."""


def validate_asset_entry(entry: dict) -> None:
    if not isinstance(entry, dict):
        raise ValueError("asset entry must be a dict")
    if not entry.get("path") or not isinstance(entry["path"], str):
        raise ValueError("asset entry requires non-empty string 'path'")
    if "size" not in entry or not isinstance(entry["size"], int) or entry["size"] < 0:
        raise ValueError("asset entry requires non-negative integer 'size'")
