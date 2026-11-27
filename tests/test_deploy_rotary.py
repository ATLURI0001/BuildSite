from src.buildsite.deploy_rotary import DeployRotary


def test_deploy_rotary():
    r = DeployRotary(capacity=3)
    for _ in range(4):
        r.record()
    assert len(r) == 3
