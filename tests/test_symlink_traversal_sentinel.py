from buildsite.symlink_traversal_sentinel import SymlinkTraversalSentinel


def test_symlink_traversal_sentinel(tmp_path):
    sentinel = SymlinkTraversalSentinel(str(tmp_path))
    ok, code = sentinel.is_safe_path("assets/style.css")
    assert ok is True and code == "OK"

    bad, err = sentinel.is_safe_path("../../etc/passwd")
    assert bad is False and err == "ERR_PATH_TRAVERSAL_SEGMENT"
