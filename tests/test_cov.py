"""Tests for bgi.core.cov — COV enum, KEY_LOCK_PAIRS, LOCK_MAP."""
import pytest
from bgi.core.cov import COV, KEY_LOCK_PAIRS, LOCK_MAP, CHARACTERIZATION_TOKENS, locks_with, is_edge_forming


class TestCOVEnum:
    def test_28_tokens_exist(self):
        assert len(COV) == 29

    def test_all_expected_tokens(self):
        expected = {
            "INTAKE", "OUTPUT", "TRANSFORM", "MUTATE", "SANITIZE",
            "CONDITIONAL", "LOOP", "GUARD", "ROUTE", "SCOPE",
            "FETCH", "PERSIST",
            "EMIT", "SUBSCRIBE", "DELEGATE",
            "CONTRACT", "COMPOSE", "INIT", "TEARDOWN",
            "RAISE", "RECOVER", "DEFER",
            "AUTHENTICATE", "AUTHORIZE", "VALIDATE", "LOG", "MEASURE", "ASYNC",
            "TEST",
        }
        assert {t.value for t in COV} == expected

    def test_cov_is_str_enum(self):
        assert isinstance(COV.INTAKE, str)
        assert COV.FETCH == "FETCH"


class TestKeyLockPairs:
    def test_core_pairs_present(self):
        pairs_set = set(KEY_LOCK_PAIRS)
        assert (COV.INTAKE, COV.OUTPUT) in pairs_set
        assert (COV.FETCH, COV.PERSIST) in pairs_set
        assert (COV.EMIT, COV.SUBSCRIBE) in pairs_set
        assert (COV.RAISE, COV.RECOVER) in pairs_set
        assert (COV.INIT, COV.TEARDOWN) in pairs_set
        assert (COV.TEST, COV.CONTRACT) in pairs_set
        assert (COV.AUTHENTICATE, COV.ROUTE) in pairs_set
        assert (COV.AUTHORIZE, COV.ROUTE) in pairs_set

    def test_guard_multi_pair(self):
        pairs_set = set(KEY_LOCK_PAIRS)
        assert (COV.GUARD, COV.CONTRACT) in pairs_set
        assert (COV.GUARD, COV.INTAKE) in pairs_set

    def test_no_self_pairs(self):
        for key, lock in KEY_LOCK_PAIRS:
            assert key != lock, f"Self-pair found: {key}"

    def test_14_pairs(self):
        assert len(KEY_LOCK_PAIRS) == 14


class TestLockMap:
    def test_bidirectional(self):
        # Every key should also appear as a lock (symmetric)
        for key, lock in KEY_LOCK_PAIRS:
            assert lock in LOCK_MAP, f"{lock} missing from LOCK_MAP"
            assert key in LOCK_MAP[lock], f"{key} not in LOCK_MAP[{lock}]"

    def test_locks_with_intake(self):
        result = locks_with(COV.INTAKE)
        assert COV.OUTPUT in result
        assert COV.GUARD in result
        assert COV.VALIDATE in result
        assert COV.SANITIZE in result

    def test_locks_with_missing_token(self):
        assert locks_with(COV.LOG) == set()


class TestCharacterizationTokens:
    def test_characterization_tokens_not_edge_forming(self):
        for token in CHARACTERIZATION_TOKENS:
            assert not is_edge_forming(token), f"{token} should not be edge-forming"

    def test_edge_forming_tokens_not_in_characterization(self):
        edge_tokens = {COV.INTAKE, COV.OUTPUT, COV.FETCH, COV.PERSIST,
                       COV.EMIT, COV.SUBSCRIBE, COV.RAISE, COV.RECOVER,
                       COV.INIT, COV.TEARDOWN, COV.AUTHENTICATE, COV.ROUTE}
        for t in edge_tokens:
            assert t not in CHARACTERIZATION_TOKENS
