import pytest

from bgi.core.cov import COV
from bgi.gate1.ai_fallback import AIFallback
from bgi.gate1.scala_scanner import scan_file_scala


SCALA_CODE = b"""
class UserService extends BaseRepository with Listener {
  def testFetch(x: String) = {
    if (x == "") return x
    for (i <- xs) {}
    try { repo.save(x) } catch { case e: Exception => handle() } finally { cleanup() }
    Future { 1 }
    repo.findAll()
  }

  def failFast() = {
    throw new RuntimeException("boom")
  }
}

object App {
  def main(args: Array[String]) = {
    println("x")
  }
}
"""


@pytest.fixture
def tmp_scala(tmp_path):
    f = tmp_path / "UserService.scala"
    f.write_bytes(SCALA_CODE)
    return f, tmp_path


def _scan(tmp_scala):
    f, root = tmp_scala
    return scan_file_scala(f, root, AIFallback(enabled=False))


def _find(fps, name):
    return next(fp for fp in fps if name in fp.unit_id)


def test_detects_methods_and_object_function(tmp_scala):
    assert len(_scan(tmp_scala)) == 3


def test_test_fetch_tokens(tmp_scala):
    fp = _find(_scan(tmp_scala), "testFetch")
    assert COV.TEST in fp.tokens
    assert COV.CONDITIONAL in fp.tokens
    assert COV.LOOP in fp.tokens
    assert COV.RECOVER in fp.tokens
    assert COV.DEFER in fp.tokens
    assert COV.ASYNC in fp.tokens
    assert COV.PERSIST in fp.tokens or COV.FETCH in fp.tokens


def test_fail_fast_has_raise(tmp_scala):
    assert COV.RAISE in _find(_scan(tmp_scala), "failFast").tokens


def test_main_is_init(tmp_scala):
    assert COV.INIT in _find(_scan(tmp_scala), "App::main").tokens


def test_class_context_from_extends_clause(tmp_scala):
    fp = _find(_scan(tmp_scala), "testFetch")
    assert COV.PERSIST in fp.class_context
    assert COV.SUBSCRIBE in fp.class_context


def test_unit_id_includes_class_name(tmp_scala):
    assert _find(_scan(tmp_scala), "testFetch").unit_id == "UserService.scala::UserService::testFetch"


def test_object_unit_id_includes_object_name(tmp_scala):
    assert _find(_scan(tmp_scala), "App::main").unit_id == "UserService.scala::App::main"


def test_language_tag_is_scala(tmp_scala):
    assert _find(_scan(tmp_scala), "testFetch").language == "scala"


def test_main_has_intake(tmp_scala):
    assert COV.INTAKE in _find(_scan(tmp_scala), "App::main").tokens
