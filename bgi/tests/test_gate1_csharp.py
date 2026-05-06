import pytest

from bgi.core.cov import COV
from bgi.gate1.ai_fallback import AIFallback
from bgi.gate1.csharp_scanner import scan_file_csharp


CSHARP_CODE = b"""
using System;
using System.Threading.Tasks;

class UserService : BaseRepository {
    public UserService() {}

    public async Task<string> FetchUsers(string filter) {
        if (filter == null) return "";
        foreach (var user in repo.FindAll()) {
        }
        await repo.FindAll();
        return filter;
    }

    public void FailFast() {
        throw new InvalidOperationException("boom");
    }

    public void RecoverWork() {
        try {
            repo.Save("x");
        } catch (Exception ex) {
        } finally {
        }
    }

    [Test]
    public void TestFetch() {
    }
}

void helper() {
    return;
}
"""


@pytest.fixture
def tmp_csharp(tmp_path):
    f = tmp_path / "UserService.cs"
    f.write_bytes(CSHARP_CODE)
    return f, tmp_path


def _scan(tmp_csharp):
    f, root = tmp_csharp
    return scan_file_csharp(f, root, AIFallback(enabled=False))


def _find(fps, name):
    return next(fp for fp in fps if name in fp.unit_id)


def test_detects_methods_and_global_function(tmp_csharp):
    assert len(_scan(tmp_csharp)) == 6


def test_fetch_users_tokens(tmp_csharp):
    fp = _find(_scan(tmp_csharp), "FetchUsers")
    assert COV.OUTPUT in fp.tokens
    assert COV.CONDITIONAL in fp.tokens
    assert COV.LOOP in fp.tokens
    assert COV.ASYNC in fp.tokens
    assert COV.FETCH in fp.tokens


def test_fail_fast_has_raise(tmp_csharp):
    assert COV.RAISE in _find(_scan(tmp_csharp), "FailFast").tokens


def test_recover_work_has_recover_and_defer(tmp_csharp):
    fp = _find(_scan(tmp_csharp), "RecoverWork")
    assert COV.RECOVER in fp.tokens
    assert COV.DEFER in fp.tokens
    assert COV.PERSIST in fp.tokens


def test_test_attribute_marks_test(tmp_csharp):
    assert COV.TEST in _find(_scan(tmp_csharp), "TestFetch").tokens


def test_constructor_is_init(tmp_csharp):
    assert COV.INIT in _find(_scan(tmp_csharp), "UserService::UserService").tokens


def test_class_context_from_base_repository(tmp_csharp):
    assert COV.PERSIST in _find(_scan(tmp_csharp), "FetchUsers").class_context


def test_unit_id_includes_class_name(tmp_csharp):
    assert _find(_scan(tmp_csharp), "FetchUsers").unit_id == "UserService.cs::UserService::FetchUsers"


def test_language_tag_is_csharp(tmp_csharp):
    assert _find(_scan(tmp_csharp), "helper").language == "csharp"
