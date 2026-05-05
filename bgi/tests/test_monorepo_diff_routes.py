"""
Tests for monorepo scan_repository(), route manifest, and graph diff.
"""
from __future__ import annotations
import json
import tempfile
from pathlib import Path

import pytest

from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint
from bgi.gate1.scanner import scan_repository, _scan_file_auto, _EXT_TO_LANG
from bgi.gate1.ai_fallback import AIFallback
from bgi.output.route_manifest import build_route_manifest, write_route_manifest, _parse_route_segment
from bgi.delta.diff import diff_scans, format_diff_report, serialize_diff, ScanDiff


_NO_AI = AIFallback(enabled=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_fp(unit_id: str, tokens: list[COV], language: str = "python") -> COVFingerprint:
    return COVFingerprint(
        unit_id=unit_id,
        tokens=tokens,
        class_context=[],
        confidence=1.0,
        source="deterministic",
        language=language,
        line_range=(1, 10),
    )


# ── scan_repository ───────────────────────────────────────────────────────────

class TestScanRepository:
    def test_scans_python_files(self, tmp_path):
        (tmp_path / "app.py").write_text("def hello():\n    return 1\n")
        fps = scan_repository(tmp_path, ai=_NO_AI)
        assert len(fps) >= 1
        assert any(fp.language == "python" for fp in fps)

    def test_scans_typescript_files(self, tmp_path):
        (tmp_path / "server.ts").write_text("function greet(name: string): string { return name; }")
        fps = scan_repository(tmp_path, ai=_NO_AI)
        assert any(fp.language == "typescript" for fp in fps)

    def test_scans_mixed_language_repo(self, tmp_path):
        (tmp_path / "app.py").write_text("def main():\n    pass\n")
        (tmp_path / "server.ts").write_text("function start() { return true; }")
        fps = scan_repository(tmp_path, ai=_NO_AI)
        langs = {fp.language for fp in fps}
        assert "python" in langs
        assert "typescript" in langs

    def test_skips_node_modules(self, tmp_path):
        nm = tmp_path / "node_modules" / "lib"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("function foo() { return 1; }")
        (tmp_path / "app.py").write_text("def main(): pass")
        fps = scan_repository(tmp_path, ai=_NO_AI)
        assert not any("node_modules" in fp.unit_id for fp in fps)

    def test_skips_pycache(self, tmp_path):
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "app.pyc").write_bytes(b"\x00")
        (tmp_path / "real.py").write_text("def f(): pass")
        fps = scan_repository(tmp_path, ai=_NO_AI)
        assert not any("__pycache__" in fp.unit_id for fp in fps)

    def test_skips_declaration_files(self, tmp_path):
        (tmp_path / "types.d.ts").write_text("declare function foo(): void;")
        fps = scan_repository(tmp_path, ai=_NO_AI)
        # .d.ts files should be skipped
        assert not any(".d.ts" in fp.unit_id for fp in fps)

    def test_returns_empty_for_empty_dir(self, tmp_path):
        fps = scan_repository(tmp_path, ai=_NO_AI)
        assert fps == []

    def test_custom_exclude_dirs(self, tmp_path):
        excluded = tmp_path / "generated"
        excluded.mkdir()
        (excluded / "api.py").write_text("def gen(): pass")
        (tmp_path / "real.py").write_text("def real(): pass")
        fps = scan_repository(tmp_path, ai=_NO_AI, exclude_dirs={"generated"})
        assert not any("generated" in fp.unit_id for fp in fps)
        assert any("real.py" in fp.unit_id for fp in fps)

    def test_ext_to_lang_map_completeness(self):
        # All tree-sitter supported languages should be in the map
        for lang in ("python", "typescript", "javascript", "java", "go", "rust",
                     "ruby", "csharp", "php", "kotlin", "scala", "lua", "elixir"):
            assert lang in _EXT_TO_LANG.values(), f"{lang} missing from _EXT_TO_LANG"


class TestScanFileAuto:
    def test_dispatches_python(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("def foo(): return 1")
        fps = _scan_file_auto(f, tmp_path, _NO_AI)
        assert len(fps) >= 1
        assert fps[0].language == "python"

    def test_dispatches_typescript(self, tmp_path):
        f = tmp_path / "mod.ts"
        f.write_text("function bar(): number { return 42; }")
        fps = _scan_file_auto(f, tmp_path, _NO_AI)
        assert len(fps) >= 1
        assert fps[0].language == "typescript"

    def test_skips_unknown_extension(self, tmp_path):
        f = tmp_path / "data.xyz123"
        f.write_text("whatever")
        fps = _scan_file_auto(f, tmp_path, _NO_AI)
        assert fps == []

    def test_skips_dts_files(self, tmp_path):
        f = tmp_path / "types.d.ts"
        f.write_text("declare function foo(): void;")
        fps = _scan_file_auto(f, tmp_path, _NO_AI)
        assert fps == []


# ── Route manifest ────────────────────────────────────────────────────────────

class TestRouteManifest:
    def test_filters_route_tagged_units(self):
        fps = [
            _make_fp("api.ts::GET:/users", [COV.ROUTE, COV.FETCH], "typescript"),
            _make_fp("api.ts::createUser", [COV.PERSIST], "typescript"),
            _make_fp("api.py::POST:/users", [COV.ROUTE, COV.PERSIST], "python"),
        ]
        entries = build_route_manifest(fps)
        assert len(entries) == 2
        unit_ids = [e["unit_id"] for e in entries]
        assert "api.ts::GET:/users" in unit_ids
        assert "api.ts::createUser" not in unit_ids

    def test_parses_method_and_path_from_unit_id(self):
        fps = [_make_fp("routes.ts::GET:/users/:id", [COV.ROUTE], "typescript")]
        entries = build_route_manifest(fps)
        assert entries[0]["method"] == "GET"
        assert entries[0]["path"]   == "/users/:id"

    def test_decorator_route_has_null_method_path(self):
        # Routes detected via decorator (@app.get) don't have method:path unit_id
        fps = [_make_fp("views.py::list_users", [COV.ROUTE, COV.FETCH], "python")]
        entries = build_route_manifest(fps)
        assert entries[0]["method"] is None
        assert entries[0]["path"]   is None

    def test_includes_language_tokens_confidence(self):
        fps = [_make_fp("api.ts::POST:/items", [COV.ROUTE, COV.PERSIST], "typescript")]
        entries = build_route_manifest(fps)
        e = entries[0]
        assert e["language"]   == "typescript"
        assert "ROUTE"         in e["tokens"]
        assert "PERSIST"       in e["tokens"]
        assert e["confidence"] == 1.0

    def test_sorted_by_file_then_unit_id(self):
        fps = [
            _make_fp("b.ts::GET:/b", [COV.ROUTE], "typescript"),
            _make_fp("a.ts::GET:/a", [COV.ROUTE], "typescript"),
        ]
        entries = build_route_manifest(fps)
        assert entries[0]["file"] == "a.ts"
        assert entries[1]["file"] == "b.ts"

    def test_empty_when_no_routes(self):
        fps = [_make_fp("app.py::save", [COV.PERSIST], "python")]
        assert build_route_manifest(fps) == []

    def test_write_route_manifest(self, tmp_path):
        fps = [_make_fp("api.ts::GET:/users", [COV.ROUTE], "typescript")]
        out = str(tmp_path / "routes.json")
        entries = write_route_manifest(fps, out)
        assert len(entries) == 1
        data = json.loads(Path(out).read_text())
        assert data[0]["unit_id"] == "api.ts::GET:/users"


class TestParseRouteSegment:
    def test_get_route(self):
        m, p = _parse_route_segment("routes.ts::GET:/users")
        assert m == "GET"
        assert p == "/users"

    def test_post_route_with_param(self):
        m, p = _parse_route_segment("api.ts::UserController::POST:/users/:id")
        assert m == "POST"
        assert p == "/users/:id"

    def test_dynamic_path(self):
        m, p = _parse_route_segment("api.ts::GET:<dynamic>")
        assert m == "GET"
        assert p == "<dynamic>"

    def test_non_route_returns_none(self):
        m, p = _parse_route_segment("api.ts::createUser")
        assert m is None
        assert p is None


# ── Graph diff ────────────────────────────────────────────────────────────────

class TestDiffScans:
    def test_added_units(self):
        before = [_make_fp("a.py::foo", [COV.FETCH])]
        after  = [_make_fp("a.py::foo", [COV.FETCH]),
                  _make_fp("a.py::bar", [COV.PERSIST])]
        diff = diff_scans(before, after)
        assert len(diff.added_units) == 1
        assert diff.added_units[0].unit_id == "a.py::bar"

    def test_removed_units(self):
        before = [_make_fp("a.py::foo", [COV.FETCH]),
                  _make_fp("a.py::bar", [COV.PERSIST])]
        after  = [_make_fp("a.py::foo", [COV.FETCH])]
        diff = diff_scans(before, after)
        assert len(diff.removed_units) == 1
        assert diff.removed_units[0].unit_id == "a.py::bar"

    def test_changed_units(self):
        before = [_make_fp("a.py::foo", [COV.FETCH])]
        after  = [_make_fp("a.py::foo", [COV.FETCH, COV.PERSIST])]
        diff = diff_scans(before, after)
        assert len(diff.changed_units) == 1
        assert "PERSIST" in diff.changed_units[0].tokens_added

    def test_unchanged_units_not_in_diff(self):
        fps = [_make_fp("a.py::foo", [COV.FETCH])]
        diff = diff_scans(fps, fps)
        assert diff.is_clean

    def test_route_added(self):
        before = []
        after  = [_make_fp("api.ts::GET:/users", [COV.ROUTE], "typescript")]
        diff = diff_scans(before, after)
        assert len(diff.added_routes) == 1
        assert diff.added_routes[0].unit_id == "api.ts::GET:/users"
        assert diff.added_routes[0].status == "added"

    def test_route_removed(self):
        before = [_make_fp("api.ts::DELETE:/users/:id", [COV.ROUTE], "typescript")]
        after  = []
        diff = diff_scans(before, after)
        assert len(diff.removed_routes) == 1
        assert diff.removed_routes[0].status == "removed"

    def test_lang_counts(self):
        before = [_make_fp("a.py::f", [COV.FETCH], "python")]
        after  = [_make_fp("a.py::f", [COV.FETCH], "python"),
                  _make_fp("b.ts::g", [COV.OUTPUT], "typescript")]
        diff = diff_scans(before, after)
        assert diff.lang_counts["python"] == (1, 1)
        assert diff.lang_counts["typescript"] == (0, 1)

    def test_tokens_added_removed(self):
        before = [_make_fp("a.py::f", [COV.FETCH, COV.AUTHENTICATE])]
        after  = [_make_fp("a.py::f", [COV.FETCH, COV.PERSIST])]
        diff = diff_scans(before, after)
        u = diff.changed_units[0]
        assert "PERSIST"      in u.tokens_added
        assert "AUTHENTICATE" in u.tokens_removed


class TestFormatDiffReport:
    def test_report_contains_summary(self):
        before = [_make_fp("a.py::foo", [COV.FETCH])]
        after  = [_make_fp("a.py::bar", [COV.PERSIST])]
        diff = diff_scans(before, after)
        report = format_diff_report(diff)
        assert "Added units" in report
        assert "Removed units" in report

    def test_clean_diff_is_clean(self):
        fps = [_make_fp("a.py::foo", [COV.FETCH])]
        diff = diff_scans(fps, fps)
        assert diff.is_clean


class TestSerializeDiff:
    def test_serialize_roundtrip(self):
        before = [_make_fp("a.py::foo", [COV.FETCH])]
        after  = [_make_fp("a.py::bar", [COV.PERSIST])]
        diff = diff_scans(before, after)
        data = serialize_diff(diff)
        assert data["summary"]["added_units"]   == 1
        assert data["summary"]["removed_units"] == 1
        assert data["added_units"][0]["unit_id"] == "a.py::bar"
        assert data["removed_units"][0]["unit_id"] == "a.py::foo"
