"""YAML alias bomb depth/size sentinel."""


def assert_safe_yaml_size(raw: str, max_bytes: int = 65536) -> None:
    if len(raw) > max_bytes:
        raise ValueError(f"sentinel violation: YAML payload {len(raw)} bytes exceeds {max_bytes}")
    if raw.count("&") > 32:
        raise ValueError("sentinel violation: excessive YAML anchors detected")
