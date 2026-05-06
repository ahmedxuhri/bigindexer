import pytest

from bgi.core.cov import COV
from bgi.gate1.ai_fallback import AIFallback
from bgi.gate1.ruby_scanner import scan_file_ruby


RUBY_CODE = b"""
class UserService < BaseRepository
  include EventHandler

  def initialize(name)
    @name = name
  end

  def fetch_users(filter)
    if filter
      return filter
    end
    for user in items do
    end
    return []
  end

  def fail_fast
    raise "boom"
  end

  def recover_work
    begin
      risky_call
    rescue => e
      logger.info(e)
    ensure
      cleanup
    end
  end

  def enqueue(user)
    job.perform_async(user)
  end

  def self.test_fetch
    yield 1
  end
end
"""


@pytest.fixture
def tmp_ruby(tmp_path):
    f = tmp_path / "service.rb"
    f.write_bytes(RUBY_CODE)
    return f, tmp_path


def _scan(tmp_ruby):
    f, root = tmp_ruby
    return scan_file_ruby(f, root, AIFallback(enabled=False))


def _find(fps, name):
    return next(fp for fp in fps if name in fp.unit_id)


def test_detects_methods(tmp_ruby):
    fps = _scan(tmp_ruby)
    assert len(fps) == 6


def test_fetch_users_tokens(tmp_ruby):
    fp = _find(_scan(tmp_ruby), "fetch_users")
    assert COV.OUTPUT in fp.tokens
    assert COV.CONDITIONAL in fp.tokens
    assert COV.LOOP in fp.tokens
    assert COV.INTAKE in fp.tokens


def test_fail_fast_has_raise(tmp_ruby):
    fp = _find(_scan(tmp_ruby), "fail_fast")
    assert COV.RAISE in fp.tokens


def test_recover_work_has_recover_and_defer(tmp_ruby):
    fp = _find(_scan(tmp_ruby), "recover_work")
    assert COV.RECOVER in fp.tokens
    assert COV.DEFER in fp.tokens
    assert COV.LOG in fp.tokens


def test_enqueue_has_async(tmp_ruby):
    fp = _find(_scan(tmp_ruby), "enqueue")
    assert COV.ASYNC in fp.tokens


def test_initialize_is_init(tmp_ruby):
    fp = _find(_scan(tmp_ruby), "initialize")
    assert COV.INIT in fp.tokens


def test_singleton_test_method_has_test_and_emit(tmp_ruby):
    fp = _find(_scan(tmp_ruby), "test_fetch")
    assert COV.TEST in fp.tokens
    assert COV.EMIT in fp.tokens


def test_class_context_from_superclass_and_include(tmp_ruby):
    fp = _find(_scan(tmp_ruby), "fetch_users")
    assert COV.PERSIST in fp.class_context
    assert COV.SUBSCRIBE in fp.class_context


def test_unit_id_includes_class_name(tmp_ruby):
    fp = _find(_scan(tmp_ruby), "fetch_users")
    assert fp.unit_id == "service.rb::UserService::fetch_users"


def test_language_tag_is_ruby(tmp_ruby):
    fp = _find(_scan(tmp_ruby), "fetch_users")
    assert fp.language == "ruby"
