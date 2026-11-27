"""HTTP redirect rule contract validator."""


def validate_redirect_rule(rule: dict) -> None:
    if not isinstance(rule, dict):
        raise ValueError("redirect rule must be a dict")
    if not rule.get("source") or not rule.get("destination"):
        raise ValueError("redirect rule requires 'source' and 'destination'")
    if rule["source"] == rule["destination"]:
        raise ValueError("redirect loop detected: source equals destination")
