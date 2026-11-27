"""RSS feed item contract validator."""


def validate_rss_item(item: dict) -> None:
    if not isinstance(item, dict):
        raise ValueError("RSS item must be a dict")
    for field in ("title", "link", "pubDate"):
        if not item.get(field) or not isinstance(item[field], str):
            raise ValueError(f"RSS item requires non-empty string '{field}'")
