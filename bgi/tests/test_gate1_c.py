import pytest

from bgi.core.cov import COV
from bgi.gate1.ai_fallback import AIFallback
from bgi.gate1.c_scanner import scan_file_c


C_CODE = b"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char** argv) {
    if (argc > 1) {
        printf("hi");
    }
    for (int i = 0; i < argc; ++i) {
    }
    fopen("x", "r");
    memcpy(argv, argv, 0);
    return argc;
}

void cleanup_buffer(char* ptr) {
    free(ptr);
}

int test_run(int value) {
    return value;
}
"""


@pytest.fixture
def tmp_c(tmp_path):
    f = tmp_path / "main.c"
    f.write_bytes(C_CODE)
    return f, tmp_path


def _scan(tmp_c):
    f, root = tmp_c
    return scan_file_c(f, root, AIFallback(enabled=False))


def _find(fps, name):
    return next(fp for fp in fps if name in fp.unit_id)


def test_detects_functions(tmp_c):
    assert len(_scan(tmp_c)) == 3


def test_main_tokens(tmp_c):
    fp = _find(_scan(tmp_c), "main")
    assert COV.INIT in fp.tokens
    assert COV.INTAKE in fp.tokens
    assert COV.CONDITIONAL in fp.tokens
    assert COV.LOOP in fp.tokens
    assert COV.OUTPUT in fp.tokens
    assert COV.LOG in fp.tokens
    assert COV.PERSIST in fp.tokens
    assert COV.TRANSFORM in fp.tokens


def test_cleanup_has_teardown(tmp_c):
    fp = _find(_scan(tmp_c), "cleanup_buffer")
    assert COV.TEARDOWN in fp.tokens


def test_test_name_marks_test(tmp_c):
    assert COV.TEST in _find(_scan(tmp_c), "test_run").tokens


def test_unit_id_has_no_class_context(tmp_c):
    fp = _find(_scan(tmp_c), "main")
    assert fp.unit_id == "main.c::main"
    assert fp.class_context == []


def test_language_tag_is_c(tmp_c):
    assert _find(_scan(tmp_c), "main").language == "c"


def test_test_run_has_output_and_intake(tmp_c):
    fp = _find(_scan(tmp_c), "test_run")
    assert COV.OUTPUT in fp.tokens
    assert COV.INTAKE in fp.tokens


def test_cleanup_unit_id(tmp_c):
    assert _find(_scan(tmp_c), "cleanup_buffer").unit_id == "main.c::cleanup_buffer"


def test_no_async_token_for_c(tmp_c):
    assert COV.ASYNC not in _find(_scan(tmp_c), "main").tokens
