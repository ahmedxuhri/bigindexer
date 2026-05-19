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


HTTP_ROUTING_CODE = b"""
package server

func RegisterRoutes(mux *http.ServeMux) {
    mux.HandleFunc("/users", listUsers)
    mux.Handle("/admin", adminHandler)
}

func RegisterGin(r *gin.Engine) {
    r.GET("/users/:id", getUser)
    r.POST("/users", createUser)
    r.DELETE("/users/:id", deleteUser)
}

func RegisterChi(router chi.Router) {
    router.Get("/health", healthCheck)
    router.Use(authMiddleware)
}
"""


def _scan_code(tmp_path, name, code):
    f = tmp_path / name
    f.write_bytes(code)
    return scan_file_go(f, tmp_path, AIFallback(enabled=False))


def test_http_routing_emits_route(tmp_path):
    fps = _scan_code(tmp_path, "routes.go", HTTP_ROUTING_CODE)
    for func_name in ("RegisterRoutes", "RegisterGin", "RegisterChi"):
        fp = next(fp for fp in fps if func_name in fp.unit_id)
        assert COV.ROUTE in fp.tokens, f"{func_name} should emit COV.ROUTE"


CHANNEL_RECEIVE_CODE = b"""
package worker

func Receiver(ch chan int) int {
    v := <-ch
    return v
}

func Sender(ch chan int, v int) {
    ch <- v
}
"""


def test_channel_receive_emits_subscribe(tmp_path):
    fps = _scan_code(tmp_path, "chan.go", CHANNEL_RECEIVE_CODE)
    receiver = next(fp for fp in fps if "Receiver" in fp.unit_id)
    assert COV.SUBSCRIBE in receiver.tokens
    sender = next(fp for fp in fps if "Sender" in fp.unit_id)
    assert COV.EMIT in sender.tokens


AUTH_CODE = b"""
package auth

func ProtectedHandler(req *http.Request) error {
    if err := authenticate(req); err != nil {
        return err
    }
    if !authorize(req, "admin") {
        return errors.New("forbidden")
    }
    return nil
}
"""


def test_auth_methods_emit_auth_tokens(tmp_path):
    fps = _scan_code(tmp_path, "auth.go", AUTH_CODE)
    fp = next(fp for fp in fps if "ProtectedHandler" in fp.unit_id)
    assert COV.AUTHENTICATE in fp.tokens
    assert COV.AUTHORIZE in fp.tokens


TEARDOWN_CODE = b"""
package svc

func Cleanup(conn io.Closer, mu sync.Locker, wg *sync.WaitGroup) {
    conn.Close()
    mu.Unlock()
    wg.Done()
}
"""


def test_teardown_methods(tmp_path):
    fps = _scan_code(tmp_path, "cleanup.go", TEARDOWN_CODE)
    fp = next(fp for fp in fps if "Cleanup" in fp.unit_id)
    assert COV.TEARDOWN in fp.tokens


MARSHAL_CODE = b"""
package codec

func Encode(v interface{}) ([]byte, error) {
    return json.Marshal(v)
}

func Decode(data []byte, v interface{}) error {
    return json.Unmarshal(data, v)
}
"""


def test_marshal_unmarshal_emit_transform(tmp_path):
    fps = _scan_code(tmp_path, "codec.go", MARSHAL_CODE)
    enc = next(fp for fp in fps if "Encode" in fp.unit_id)
    assert COV.TRANSFORM in enc.tokens
    dec = next(fp for fp in fps if "Decode" in fp.unit_id)
    assert COV.TRANSFORM in dec.tokens
