import pytest

from bgi.core.cov import COV
from bgi.gate1.ai_fallback import AIFallback
from bgi.gate1.php_scanner import scan_file_php


PHP_CODE = b"""
<?php
class UserService extends BaseRepository implements TestCase {
    public function __construct(string $name) {}

    public function fetchUsers(string $filter) {
        if ($filter === "") {
            return [];
        }
        foreach ($items as $item) {
        }
        return repo()->findAll();
    }

    public function failFast() {
        throw new RuntimeException("boom");
    }

    public function recoverWork() {
        try {
            repo()->save("x");
        } catch (Exception $e) {
        } finally {
        }
    }

    #[Test]
    public function testFetch() {
    }
}

function helper(string $x) {
    return $x;
}
"""


@pytest.fixture
def tmp_php(tmp_path):
    f = tmp_path / "UserService.php"
    f.write_bytes(PHP_CODE)
    return f, tmp_path


def _scan(tmp_php):
    f, root = tmp_php
    return scan_file_php(f, root, AIFallback(enabled=False))


def _find(fps, name):
    return next(fp for fp in fps if name in fp.unit_id)


def test_detects_methods_and_function(tmp_php):
    assert len(_scan(tmp_php)) == 6


def test_fetch_users_tokens(tmp_php):
    fp = _find(_scan(tmp_php), "fetchUsers")
    assert COV.OUTPUT in fp.tokens
    assert COV.CONDITIONAL in fp.tokens
    assert COV.LOOP in fp.tokens
    assert COV.FETCH in fp.tokens
    assert COV.INTAKE in fp.tokens


def test_fail_fast_has_raise(tmp_php):
    assert COV.RAISE in _find(_scan(tmp_php), "failFast").tokens


def test_recover_work_has_recover_and_defer(tmp_php):
    fp = _find(_scan(tmp_php), "recoverWork")
    assert COV.RECOVER in fp.tokens
    assert COV.DEFER in fp.tokens
    assert COV.PERSIST in fp.tokens


def test_test_attribute_marks_test(tmp_php):
    assert COV.TEST in _find(_scan(tmp_php), "testFetch").tokens


def test_construct_is_init(tmp_php):
    assert COV.INIT in _find(_scan(tmp_php), "__construct").tokens


def test_class_context_from_base_repository(tmp_php):
    fp = _find(_scan(tmp_php), "fetchUsers")
    assert COV.PERSIST in fp.class_context
    assert COV.TEST in fp.class_context


def test_unit_id_includes_class_name(tmp_php):
    assert _find(_scan(tmp_php), "fetchUsers").unit_id == "UserService.php::UserService::fetchUsers"


def test_language_tag_is_php(tmp_php):
    assert _find(_scan(tmp_php), "helper").language == "php"
