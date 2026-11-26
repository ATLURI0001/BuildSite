"""CSS url() injection sentinel."""


def assert_safe_css_url(css: str) -> None:
    lowered = css.lower()
    if "javascript:" in lowered or "data:text/html" in lowered:
        raise ValueError("sentinel violation: unsafe scheme in CSS url()")
