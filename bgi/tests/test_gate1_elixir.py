import pytest

from bgi.core.cov import COV
from bgi.gate1.ai_fallback import AIFallback
from bgi.gate1.elixir_scanner import scan_file_elixir


ELIXIR_CODE = b"""
defmodule MyApp.Server do
  use GenServer

  def init(opts) do
    if opts do
      case opts do
        _ -> {:ok, opts}
      end
    end
  end

  defp handle_call(msg, from, state) do
    receive do
      x -> x
    end
  end

  def helper(x), do: x

  def async_work() do
    spawn(fn -> :ok end)
    Task.async(fn -> :ok end)
    GenServer.call(Server, :ping)
    GenServer.cast(Server, :pong)
  end

  def rescuey() do
    try do
      raise \"boom\"
    rescue
      _ -> :ok
    catch
      _, _ -> :ok
    after
      :ok
    end
  end

  def loop_users(xs) do
    for x <- xs do
      x
    end
  end
end
"""


@pytest.fixture
def tmp_elixir(tmp_path):
    f = tmp_path / "sample.ex"
    f.write_bytes(ELIXIR_CODE)
    return f, tmp_path


def _scan(tmp_elixir):
    f, root = tmp_elixir
    return scan_file_elixir(f, root, AIFallback(enabled=False))


def _find(fps, name):
    return next(fp for fp in fps if name in fp.unit_id)


def test_detects_def_and_defp_functions(tmp_elixir):
    assert len(_scan(tmp_elixir)) == 6


def test_init_has_conditional_and_init(tmp_elixir):
    fp = _find(_scan(tmp_elixir), "init")
    assert COV.CONDITIONAL in fp.tokens
    assert COV.INIT in fp.tokens
    assert COV.INTAKE in fp.tokens


def test_handle_call_is_subscribe(tmp_elixir):
    fp = _find(_scan(tmp_elixir), "handle_call")
    assert COV.SUBSCRIBE in fp.tokens


def test_rescue_blocks_produce_raise_recover_and_defer(tmp_elixir):
    fp = _find(_scan(tmp_elixir), "rescuey")
    assert COV.RAISE in fp.tokens
    assert COV.RECOVER in fp.tokens
    assert COV.DEFER in fp.tokens


def test_for_produces_loop(tmp_elixir):
    fp = _find(_scan(tmp_elixir), "loop_users")
    assert COV.LOOP in fp.tokens


def test_async_and_delegate_calls_detected(tmp_elixir):
    fp = _find(_scan(tmp_elixir), "async_work")
    assert COV.ASYNC in fp.tokens
    assert COV.DELEGATE in fp.tokens


def test_inline_def_is_detected(tmp_elixir):
    fp = _find(_scan(tmp_elixir), "helper")
    assert fp.unit_id == "sample.ex::MyApp.Server::helper"


def test_module_use_produces_class_context(tmp_elixir):
    fp = _find(_scan(tmp_elixir), "init")
    assert COV.SUBSCRIBE in fp.class_context


def test_unit_id_includes_module_name(tmp_elixir):
    fp = _find(_scan(tmp_elixir), "handle_call")
    assert fp.unit_id == "sample.ex::MyApp.Server::handle_call"


def test_language_tag_is_elixir(tmp_elixir):
    fp = _find(_scan(tmp_elixir), "init")
    assert fp.language == "elixir"
