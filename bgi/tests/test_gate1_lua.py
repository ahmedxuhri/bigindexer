import pytest

from bgi.core.cov import COV
from bgi.gate1.ai_fallback import AIFallback
from bgi.gate1.lua_scanner import scan_file_lua


LUA_CODE = b"""
function M.fetch_users(filter)
    if filter then
        print(filter)
    end
    for i = 1, 10 do
        print(i)
    end
    while false do
        break
    end
    return filter
end

function Class:method(x)
    return x
end

local function helper(x)
    return x
end

M.setup = function(opts)
    pcall(run)
    coroutine.wrap(run)
    require('mod')
end
"""


@pytest.fixture
def tmp_lua(tmp_path):
    f = tmp_path / "sample.lua"
    f.write_bytes(LUA_CODE)
    return f, tmp_path


def _scan(tmp_lua):
    f, root = tmp_lua
    return scan_file_lua(f, root, AIFallback(enabled=False))


def _find(fps, name):
    return next(fp for fp in fps if name in fp.unit_id)


def test_detects_function_forms(tmp_lua):
    assert len(_scan(tmp_lua)) == 4


def test_function_declaration_has_output_conditional_and_loop(tmp_lua):
    fp = _find(_scan(tmp_lua), "fetch_users")
    assert COV.OUTPUT in fp.tokens
    assert COV.CONDITIONAL in fp.tokens
    assert COV.LOOP in fp.tokens
    assert COV.INTAKE in fp.tokens


def test_assignment_function_detected_as_init(tmp_lua):
    fp = _find(_scan(tmp_lua), "setup")
    assert COV.INIT in fp.tokens


def test_assignment_function_has_recover_fetch_and_async(tmp_lua):
    fp = _find(_scan(tmp_lua), "setup")
    assert COV.RECOVER in fp.tokens
    assert COV.FETCH in fp.tokens
    assert COV.ASYNC in fp.tokens


def test_method_index_expression_uses_class_context_in_unit_id(tmp_lua):
    fp = _find(_scan(tmp_lua), "Class::method")
    assert fp.unit_id == "sample.lua::Class::method"


def test_module_dot_form_uses_module_in_unit_id(tmp_lua):
    fp = _find(_scan(tmp_lua), "M::fetch_users")
    assert fp.unit_id == "sample.lua::M::fetch_users"


def test_local_function_uses_plain_unit_id(tmp_lua):
    fp = _find(_scan(tmp_lua), "helper")
    assert fp.unit_id == "sample.lua::helper"


def test_return_produces_output(tmp_lua):
    fp = _find(_scan(tmp_lua), "method")
    assert COV.OUTPUT in fp.tokens


def test_pcall_produces_recover(tmp_lua):
    fp = _find(_scan(tmp_lua), "setup")
    assert COV.RECOVER in fp.tokens


def test_coroutine_wrap_produces_async(tmp_lua):
    fp = _find(_scan(tmp_lua), "setup")
    assert COV.ASYNC in fp.tokens


def test_language_tag_is_lua(tmp_lua):
    fp = _find(_scan(tmp_lua), "fetch_users")
    assert fp.language == "lua"
