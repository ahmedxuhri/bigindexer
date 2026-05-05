import pytest

from bgi.core.cov import COV
from bgi.gate1.ai_fallback import AIFallback
from bgi.gate1.rust_scanner import scan_file_rust


RUST_CODE = b"""
struct UserService;
struct MyError;
struct Input;

#[test]
fn test_fetch() {
    assert!(true);
}

impl From<Input> for UserService {
    async fn fetch_users(&self, filter: i32) -> i32 {
        if filter > 0 {
            return filter;
        }
        for item in values() {
            let _ = item;
        }
        Ok(1)?;
        repo.save();
        value.await;
        0
    }
}

impl Default for UserService {
    fn make() -> UserService {
        UserService
    }
}

impl Error for MyError {
    fn source(&self) {
    }
}
"""


@pytest.fixture
def tmp_rust(tmp_path):
    f = tmp_path / "service.rs"
    f.write_bytes(RUST_CODE)
    return f, tmp_path


def _scan(tmp_rust):
    f, root = tmp_rust
    return scan_file_rust(f, root, AIFallback(enabled=False))


def _find(fps, name):
    return next(fp for fp in fps if name in fp.unit_id)


def test_detects_functions(tmp_rust):
    fps = _scan(tmp_rust)
    assert len(fps) == 4


def test_fetch_users_tokens(tmp_rust):
    fp = _find(_scan(tmp_rust), "fetch_users")
    assert COV.OUTPUT in fp.tokens
    assert COV.CONDITIONAL in fp.tokens
    assert COV.LOOP in fp.tokens
    assert COV.RECOVER in fp.tokens
    assert COV.ASYNC in fp.tokens
    assert COV.PERSIST in fp.tokens


def test_test_attribute_marks_test(tmp_rust):
    fp = _find(_scan(tmp_rust), "test_fetch")
    assert COV.TEST in fp.tokens


def test_from_trait_adds_transform_class_context(tmp_rust):
    fp = _find(_scan(tmp_rust), "fetch_users")
    assert COV.TRANSFORM in fp.class_context


def test_default_trait_adds_init_class_context(tmp_rust):
    fp = _find(_scan(tmp_rust), "make")
    assert COV.INIT in fp.class_context


def test_error_trait_adds_raise_class_context(tmp_rust):
    fp = _find(_scan(tmp_rust), "source")
    assert COV.RAISE in fp.class_context


def test_impl_type_appears_in_unit_id(tmp_rust):
    fp = _find(_scan(tmp_rust), "fetch_users")
    assert fp.unit_id == "service.rs::UserService::fetch_users"


def test_top_level_test_unit_id_has_no_impl_type(tmp_rust):
    fp = _find(_scan(tmp_rust), "test_fetch")
    assert fp.unit_id == "service.rs::test_fetch"


def test_fetch_users_has_intake(tmp_rust):
    fp = _find(_scan(tmp_rust), "fetch_users")
    assert COV.INTAKE in fp.tokens


def test_language_tag_is_rust(tmp_rust):
    fp = _find(_scan(tmp_rust), "fetch_users")
    assert fp.language == "rust"
