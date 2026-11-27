"""output_manifest_contract.py – validates build output manifest contract."""


class OutputManifestContract:
    def __init__(self, required_keys: list[str]):
        self.required_keys = required_keys

    def validate(self, manifest: dict) -> bool:
        return all(k in manifest for k in self.required_keys)
