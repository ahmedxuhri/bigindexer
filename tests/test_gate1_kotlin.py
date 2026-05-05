import pytest

from bgi.core.cov import COV
from bgi.gate1.ai_fallback import AIFallback
from bgi.gate1.kotlin_scanner import scan_file_kotlin


KOTLIN_CODE = b"""
class UserService : BaseRepository() {
    @Test
    suspend fun testFetch(filter: String): String {
        if (filter.isEmpty()) return ""
        for (x in xs) { }
        try { repo.save(filter) } catch (e: Exception) { handle() } finally { cleanup() }
        launch { repo.findAll() }
        return filter
    }

    fun failFast() {
        throw RuntimeException("boom")
    }

    constructor() : super()
}

fun helper(x: String): String {
    return x
}
"""


@pytest.fixture
def tmp_kotlin(tmp_path):
    f = tmp_path / "UserService.kt"
    f.write_bytes(KOTLIN_CODE)
    return f, tmp_path


def _scan(tmp_kotlin):
    f, root = tmp_kotlin
    return scan_file_kotlin(f, root, AIFallback(enabled=False))


def _find(fps, name):
    return next(fp for fp in fps if name in fp.unit_id)


def test_detects_functions_and_constructor(tmp_kotlin):
    assert len(_scan(tmp_kotlin)) == 4


def test_test_fetch_tokens(tmp_kotlin):
    fp = _find(_scan(tmp_kotlin), "testFetch")
    assert COV.TEST in fp.tokens
    assert COV.OUTPUT in fp.tokens
    assert COV.CONDITIONAL in fp.tokens
    assert COV.LOOP in fp.tokens
    assert COV.RECOVER in fp.tokens
    assert COV.DEFER in fp.tokens
    assert COV.ASYNC in fp.tokens


def test_fail_fast_has_raise(tmp_kotlin):
    assert COV.RAISE in _find(_scan(tmp_kotlin), "failFast").tokens


def test_constructor_is_init(tmp_kotlin):
    assert COV.INIT in _find(_scan(tmp_kotlin), "UserService::UserService").tokens


def test_class_context_from_base_repository(tmp_kotlin):
    assert COV.PERSIST in _find(_scan(tmp_kotlin), "testFetch").class_context


def test_unit_id_includes_class_name(tmp_kotlin):
    assert _find(_scan(tmp_kotlin), "testFetch").unit_id == "UserService.kt::UserService::testFetch"


def test_top_level_helper_unit_id(tmp_kotlin):
    assert _find(_scan(tmp_kotlin), "helper").unit_id == "UserService.kt::helper"


def test_language_tag_is_kotlin(tmp_kotlin):
    assert _find(_scan(tmp_kotlin), "helper").language == "kotlin"


def test_helper_has_intake_and_output(tmp_kotlin):
    fp = _find(_scan(tmp_kotlin), "helper")
    assert COV.INTAKE in fp.tokens
    assert COV.OUTPUT in fp.tokens
