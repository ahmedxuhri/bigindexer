import pytest

from bgi.core.cov import COV
from bgi.gate1.ai_fallback import AIFallback
from bgi.gate1.go_scanner import scan_file_go


GO_CODE = b"""
package sample

type Worker struct{}

func (w *Worker) FetchUsers(filter string) []string {
    if filter == "" {
        return nil
    }
    for _, user := range repo.FindAll() {
        _ = user
    }
    go publish()
    return []string{}
}

func (w *Worker) Handle() {
    defer cleanup()
    recover()
}

func (w *Worker) Send(ch chan int, value int) {
    ch <- value
}

func (w *Worker) Fail() {
    panic("boom")
}

func Run(task string) {
    repo.Save(task)
}
"""


@pytest.fixture
def tmp_go(tmp_path):
    f = tmp_path / "worker.go"
    f.write_bytes(GO_CODE)
    return f, tmp_path


def _scan(tmp_go):
    f, root = tmp_go
    return scan_file_go(f, root, AIFallback(enabled=False))


def _find(fps, name):
    return next(fp for fp in fps if name in fp.unit_id)


def test_detects_functions_and_methods(tmp_go):
    fps = _scan(tmp_go)
    assert len(fps) == 5


def test_fetch_users_tokens(tmp_go):
    fp = _find(_scan(tmp_go), "FetchUsers")
    assert COV.OUTPUT in fp.tokens
    assert COV.CONDITIONAL in fp.tokens
    assert COV.LOOP in fp.tokens
    assert COV.ASYNC in fp.tokens
    assert COV.FETCH in fp.tokens


def test_handle_has_defer_and_recover(tmp_go):
    fp = _find(_scan(tmp_go), "Handle")
    assert COV.DEFER in fp.tokens
    assert COV.RECOVER in fp.tokens


def test_send_has_emit(tmp_go):
    fp = _find(_scan(tmp_go), "Send")
    assert COV.EMIT in fp.tokens


def test_fail_has_raise(tmp_go):
    fp = _find(_scan(tmp_go), "Fail")
    assert COV.RAISE in fp.tokens


def test_run_has_persist(tmp_go):
    fp = _find(_scan(tmp_go), "Run")
    assert COV.PERSIST in fp.tokens
    assert COV.INTAKE in fp.tokens


def test_method_unit_id_includes_receiver_type(tmp_go):
    fp = _find(_scan(tmp_go), "FetchUsers")
    assert fp.unit_id == "worker.go::Worker::FetchUsers"


def test_top_level_unit_id_has_no_receiver(tmp_go):
    fp = _find(_scan(tmp_go), "Run")
    assert fp.unit_id == "worker.go::Run"


def test_go_methods_have_no_class_context(tmp_go):
    fp = _find(_scan(tmp_go), "FetchUsers")
    assert fp.class_context == []


def test_language_tag_is_go(tmp_go):
    fp = _find(_scan(tmp_go), "FetchUsers")
    assert fp.language == "go"
