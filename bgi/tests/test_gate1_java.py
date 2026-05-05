import pytest

from bgi.core.cov import COV
from bgi.gate1.ai_fallback import AIFallback
from bgi.gate1.java_scanner import scan_file_java


JAVA_CODE = b"""
public class UserService extends BaseRepository {
    public UserService(String name) {}

    public java.util.List<String> fetchUsers(String filter) {
        if (filter == null) return java.util.Collections.emptyList();
        for (String user : repo.findAll()) {
        }
        return new java.util.ArrayList<>();
    }

    public void failFast() {
        throw new IllegalStateException("boom");
    }

    public void recoverWork() {
        try {
            repo.save("x");
        } catch (Exception ex) {
        } finally {
        }
    }

    public synchronized void syncUsers() {
        repo.save("x");
    }

    @Test
    public void testFetch() {
    }
}
"""


@pytest.fixture
def tmp_java(tmp_path):
    f = tmp_path / "UserService.java"
    f.write_bytes(JAVA_CODE)
    return f, tmp_path


def _scan(tmp_java):
    f, root = tmp_java
    return scan_file_java(f, root, AIFallback(enabled=False))


def _find(fps, name):
    return next(fp for fp in fps if name in fp.unit_id)


def test_detects_methods(tmp_java):
    fps = _scan(tmp_java)
    assert len(fps) == 6


def test_fetch_users_tokens(tmp_java):
    fp = _find(_scan(tmp_java), "fetchUsers")
    assert COV.OUTPUT in fp.tokens
    assert COV.CONDITIONAL in fp.tokens
    assert COV.LOOP in fp.tokens
    assert COV.INTAKE in fp.tokens


def test_fail_fast_has_raise(tmp_java):
    fp = _find(_scan(tmp_java), "failFast")
    assert COV.RAISE in fp.tokens


def test_recover_work_has_recover_and_defer(tmp_java):
    fp = _find(_scan(tmp_java), "recoverWork")
    assert COV.RECOVER in fp.tokens
    assert COV.DEFER in fp.tokens
    assert COV.PERSIST in fp.tokens


def test_sync_users_has_async(tmp_java):
    fp = _find(_scan(tmp_java), "syncUsers")
    assert COV.ASYNC in fp.tokens
    assert COV.PERSIST in fp.tokens


def test_test_annotation_marks_test(tmp_java):
    fp = _find(_scan(tmp_java), "testFetch")
    assert COV.TEST in fp.tokens


def test_constructor_is_init(tmp_java):
    fp = _find(_scan(tmp_java), "UserService")
    assert COV.INIT in fp.tokens


def test_class_context_from_base_repository(tmp_java):
    fp = _find(_scan(tmp_java), "fetchUsers")
    assert COV.PERSIST in fp.class_context


def test_unit_id_includes_class_name(tmp_java):
    fp = _find(_scan(tmp_java), "fetchUsers")
    assert fp.unit_id == "UserService.java::UserService::fetchUsers"


def test_language_tag_is_java(tmp_java):
    fp = _find(_scan(tmp_java), "fetchUsers")
    assert fp.language == "java"
