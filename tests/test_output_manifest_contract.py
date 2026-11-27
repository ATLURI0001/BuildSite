"""Tests for output_manifest_contract."""
import sys
sys.path.insert(0, "src")
from buildsite.output_manifest_contract import OutputManifestContract


def test_output_manifest_contract():
    c = OutputManifestContract(["version", "files"])
    assert c.validate({"version": "1.0", "files": []}) is True
    assert c.validate({"version": "1.0"}) is False
