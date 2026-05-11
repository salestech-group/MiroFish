"""Unit and integration tests for ``scripts/ci/i18n_cjk_guard.py``.

Stdlib-only tests using ``unittest``. Run from the repository root with::

    python -m unittest scripts/ci/tests/test_i18n_cjk_guard.py

or as a script::

    python scripts/ci/tests/test_i18n_cjk_guard.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_GUARD_DIR = _HERE.parent
sys.path.insert(0, str(_GUARD_DIR))

import i18n_cjk_guard as guard  # noqa: E402


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a git command in ``repo`` and return the completed process."""
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _make_repo(tmp: Path) -> Path:
    """Initialize an isolated git repository at ``tmp`` and return the path."""
    _git(tmp, "init", "-q", "-b", "main")
    _git(tmp, "config", "user.email", "test@example.com")
    _git(tmp, "config", "user.name", "Test")
    return tmp


def _commit_file(repo: Path, rel: str, content: str | bytes) -> None:
    """Write a file under ``repo`` and commit it."""
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        target.write_text(content, encoding="utf-8")
    else:
        target.write_bytes(content)
    _git(repo, "add", "--", rel)
    _git(repo, "commit", "-q", "-m", f"add {rel}")


class ScanLocaleCjkTests(unittest.TestCase):
    """``scan_locale_cjk`` returns one ``LocaleFinding`` per CJK leaf string."""

    def test_clean_catalogue_returns_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            en_path = Path(tmp) / "en.json"
            en_path.write_text(
                json.dumps(
                    {"common": {"confirm": "Confirm", "cancel": "Cancel"}},
                    indent=2,
                ),
                encoding="utf-8",
            )
            self.assertEqual(guard.scan_locale_cjk(en_path), [])

    def test_planted_cjk_returns_one_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            en_path = Path(tmp) / "en.json"
            data = {
                "common": {
                    "confirm": "Confirm",
                    "cancel": "取消",
                }
            }
            en_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            findings = guard.scan_locale_cjk(en_path)
            self.assertEqual(len(findings), 1)
            key, line_no, snippet = findings[0]
            self.assertEqual(key, "common.cancel")
            self.assertGreaterEqual(line_no, 1)
            self.assertIn("取消", snippet)

    def test_long_value_is_truncated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            en_path = Path(tmp) / "en.json"
            value = "前置" + ("x" * 200)
            en_path.write_text(
                json.dumps({"k": value}, ensure_ascii=False),
                encoding="utf-8",
            )
            findings = guard.scan_locale_cjk(en_path)
            self.assertEqual(len(findings), 1)
            self.assertLessEqual(len(findings[0][2]), guard.SNIPPET_MAX_LEN)


class CountPathCjkTests(unittest.TestCase):
    """``count_path_cjk`` shells out to ``git grep -nIP``."""

    def test_returns_zero_for_empty_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(Path(tmp))
            _commit_file(repo, "src/a.txt", "hello world\n")
            self.assertEqual(guard.count_path_cjk(repo, "src"), 0)

    def test_counts_planted_cjk_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(Path(tmp))
            _commit_file(
                repo,
                "src/a.py",
                "# 一\nprint('hi')\n# 二三\nx = '四'\n",
            )
            # Three lines contain CJK: # 一 ; # 二三 ; x = '四'.
            self.assertEqual(guard.count_path_cjk(repo, "src"), 3)

    def test_skips_binary_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(Path(tmp))
            # A "binary" blob containing CJK bytes; -I should exclude it.
            _commit_file(
                repo,
                "src/blob.bin",
                b"\x00\x01\x02\xe4\xb8\x80\x00\xff",
            )
            self.assertEqual(guard.count_path_cjk(repo, "src"), 0)

    def test_skips_untracked_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(Path(tmp))
            _commit_file(repo, "src/.gitkeep", "")
            (repo / "src" / "untracked.py").write_text(
                "x = '中'\n", encoding="utf-8"
            )
            self.assertEqual(guard.count_path_cjk(repo, "src"), 0)


class BaselineRoundTripTests(unittest.TestCase):
    """``read_baseline`` and ``write_baseline`` round-trip cleanly."""

    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "baseline.txt"
            counts = {"backend/app": 2792, "frontend/src": 902}
            guard.write_baseline(path, counts)
            self.assertTrue(path.read_text().endswith("\n"))
            self.assertEqual(guard.read_baseline(path), counts)

    def test_sorted_lexicographically_and_single_trailing_newline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "baseline.txt"
            guard.write_baseline(path, {"frontend/src": 1, "backend/app": 2})
            text = path.read_text(encoding="utf-8")
            data_lines = [
                line for line in text.splitlines() if not line.startswith("#")
            ]
            self.assertEqual(
                data_lines,
                ["backend/app\t2", "frontend/src\t1"],
            )
            self.assertTrue(text.endswith("\n"))
            self.assertFalse(text.endswith("\n\n"))

    def test_missing_file_raises_baseline_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.txt"
            with self.assertRaises(guard.BaselineError):
                guard.read_baseline(path)

    def test_malformed_line_raises_baseline_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "baseline.txt"
            path.write_text(
                "# header\nbackend/app 100\n", encoding="utf-8"
            )
            with self.assertRaises(guard.BaselineError):
                guard.read_baseline(path)


class RunCheckEndToEndTests(unittest.TestCase):
    """End-to-end test of ``run_check`` against a synthetic repo."""

    def _make_full_repo(
        self,
        tmp: Path,
        *,
        en_json: dict,
        backend_lines: int,
        frontend_lines: int,
        zh_json: dict | None = None,
    ) -> tuple[Path, Path]:
        repo = _make_repo(tmp)
        _commit_file(
            repo,
            "locales/en.json",
            json.dumps(en_json, indent=2, ensure_ascii=False),
        )
        zh_payload = zh_json if zh_json is not None else en_json
        _commit_file(
            repo,
            "locales/zh.json",
            json.dumps(zh_payload, indent=2, ensure_ascii=False),
        )
        if backend_lines:
            content = "\n".join(f"# 中{i}" for i in range(backend_lines)) + "\n"
            _commit_file(repo, "backend/app/x.py", content)
        else:
            _commit_file(repo, "backend/app/.gitkeep", "")
        if frontend_lines:
            content = "\n".join(f"// 中{i}" for i in range(frontend_lines)) + "\n"
            _commit_file(repo, "frontend/src/x.js", content)
        else:
            _commit_file(repo, "frontend/src/.gitkeep", "")
        baseline_path = repo / "baseline.txt"
        return repo, baseline_path

    def test_pass_within_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, baseline_path = self._make_full_repo(
                Path(tmp),
                en_json={"k": "Confirm"},
                backend_lines=3,
                frontend_lines=2,
            )
            guard.write_baseline(
                baseline_path,
                {"backend/app": 5, "frontend/src": 5},
            )
            rc = guard.run_check(repo, baseline_path)
            self.assertEqual(rc, 0)

    def test_fail_on_locale_cjk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, baseline_path = self._make_full_repo(
                Path(tmp),
                en_json={"k": "中文"},
                backend_lines=0,
                frontend_lines=0,
            )
            guard.write_baseline(
                baseline_path,
                {"backend/app": 0, "frontend/src": 0},
            )
            rc = guard.run_check(repo, baseline_path)
            self.assertEqual(rc, 1)

    def test_fail_on_regression_with_refresh_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, baseline_path = self._make_full_repo(
                Path(tmp),
                en_json={"k": "Confirm"},
                backend_lines=10,
                frontend_lines=0,
            )
            guard.write_baseline(
                baseline_path,
                {"backend/app": 5, "frontend/src": 0},
            )
            # Capture stderr.
            from io import StringIO

            captured_err = StringIO()
            old_err = sys.stderr
            sys.stderr = captured_err
            try:
                rc = guard.run_check(repo, baseline_path)
            finally:
                sys.stderr = old_err
            self.assertEqual(rc, 1)
            err_text = captured_err.getvalue()
            self.assertIn("cjk-regression", err_text)
            self.assertIn(
                "python scripts/ci/i18n_cjk_guard.py --update-baseline",
                err_text,
            )

    def test_missing_en_json_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(Path(tmp))
            _commit_file(repo, "backend/app/.gitkeep", "")
            _commit_file(repo, "frontend/src/.gitkeep", "")
            baseline_path = repo / "baseline.txt"
            guard.write_baseline(
                baseline_path,
                {"backend/app": 0, "frontend/src": 0},
            )
            rc = guard.run_check(repo, baseline_path)
            self.assertEqual(rc, 1)

    def test_missing_baseline_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, baseline_path = self._make_full_repo(
                Path(tmp),
                en_json={"k": "Confirm"},
                backend_lines=0,
                frontend_lines=0,
            )
            # Do not write the baseline.
            self.assertFalse(baseline_path.exists())
            rc = guard.run_check(repo, baseline_path)
            self.assertEqual(rc, 1)


class UpdateBaselineTests(unittest.TestCase):
    """``update_baseline`` writes current counts and exits 0."""

    def test_update_then_check_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(Path(tmp))
            _commit_file(
                repo,
                "locales/en.json",
                json.dumps({"k": "Confirm"}, indent=2),
            )
            _commit_file(
                repo,
                "locales/zh.json",
                json.dumps({"k": "Confirm"}, indent=2),
            )
            _commit_file(repo, "backend/app/x.py", "# 一\n# 二\n")
            _commit_file(repo, "frontend/src/.gitkeep", "")
            baseline_path = repo / "baseline.txt"
            self.assertEqual(
                guard.update_baseline(repo, baseline_path), 0
            )
            counts = guard.read_baseline(baseline_path)
            self.assertEqual(counts["backend/app"], 2)
            self.assertEqual(counts["frontend/src"], 0)
            self.assertEqual(guard.run_check(repo, baseline_path), 0)


class CliSmokeTests(unittest.TestCase):
    """``main`` exposes the documented CLI surface."""

    def test_help_flag_exits_zero(self) -> None:
        guard_script = _GUARD_DIR / "i18n_cjk_guard.py"
        proc = subprocess.run(
            [sys.executable, str(guard_script), "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        for flag in ("--update-baseline", "--baseline", "--repo-root"):
            self.assertIn(flag, proc.stdout)

    def test_unknown_flag_exits_nonzero(self) -> None:
        guard_script = _GUARD_DIR / "i18n_cjk_guard.py"
        proc = subprocess.run(
            [sys.executable, str(guard_script), "--no-such-flag"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)


class FlattenKeysTests(unittest.TestCase):
    """``_flatten_keys`` returns the dotted-key set of a parsed catalogue."""

    def test_empty_dict_returns_empty_set(self) -> None:
        self.assertEqual(guard._flatten_keys({}), set())

    def test_flat_dict_returns_top_level_keys(self) -> None:
        self.assertEqual(
            guard._flatten_keys({"a": "v", "b": "w"}),
            {"a", "b"},
        )

    def test_nested_dict_uses_dot_separator(self) -> None:
        self.assertEqual(
            guard._flatten_keys({"a": {"b": {"c": "v"}}}),
            {"a.b.c"},
        )

    def test_scalar_leaves_count_as_keys(self) -> None:
        # Requirement 1.5: scalar leaves (number, bool, null) and string
        # leaves are treated identically for parity purposes.
        self.assertEqual(
            guard._flatten_keys(
                {
                    "n": 42,
                    "b": True,
                    "s": "x",
                    "z": None,
                    "f": 3.14,
                }
            ),
            {"n", "b", "s", "z", "f"},
        )

    def test_dict_leaf_does_not_become_a_key(self) -> None:
        # Only non-dict leaves emit keys; the parent path is NOT itself
        # emitted when it has children.
        keys = guard._flatten_keys({"parent": {"child": "v"}})
        self.assertNotIn("parent", keys)
        self.assertIn("parent.child", keys)


class LocateKeyLineTests(unittest.TestCase):
    """``_locate_key_line`` resolves the 1-based line of a dotted key."""

    def test_returns_line_number_of_quoted_leaf_segment(self) -> None:
        text_lines = [
            "{",
            '  "a": {',
            '    "missingKey": "v"',
            "  }",
            "}",
        ]
        self.assertEqual(
            guard._locate_key_line(text_lines, "a.missingKey"),
            3,
        )

    def test_first_match_wins(self) -> None:
        text_lines = [
            "{",
            '  "k": "first"',
            '  "k": "second"',
            "}",
        ]
        self.assertEqual(guard._locate_key_line(text_lines, "k"), 2)

    def test_missing_key_falls_back_to_line_one(self) -> None:
        text_lines = ["{", '  "other": "v"', "}"]
        self.assertEqual(guard._locate_key_line(text_lines, "absent"), 1)


class FormatParityFindingTests(unittest.TestCase):
    """``_format_parity_finding`` produces canonical parity-failure lines."""

    def test_en_only_layout(self) -> None:
        line = guard._format_parity_finding(
            "locales/en.json", 17, "common.foo", "en-only"
        )
        self.assertEqual(
            line, "locales/en.json:17: parity-en-only: common.foo"
        )

    def test_zh_only_layout(self) -> None:
        line = guard._format_parity_finding(
            "locales/zh.json", 5, "log.api.bar", "zh-only"
        )
        self.assertEqual(
            line, "locales/zh.json:5: parity-zh-only: log.api.bar"
        )


class RunParityCheckTests(unittest.TestCase):
    """``run_parity_check`` returns a ``ParityResult`` for the live tree."""

    def _write_catalogues(
        self,
        repo: Path,
        en_payload: dict,
        zh_payload: dict,
    ) -> None:
        (repo / "locales").mkdir(parents=True, exist_ok=True)
        (repo / "locales" / "en.json").write_text(
            json.dumps(en_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (repo / "locales" / "zh.json").write_text(
            json.dumps(zh_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def test_passes_when_keys_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            payload = {"common": {"a": "A", "b": "B"}, "k": "v"}
            self._write_catalogues(repo, payload, payload)
            result = guard.run_parity_check(repo)
            self.assertTrue(result.passed)
            self.assertEqual(result.failure_lines, [])
            self.assertIsNotNone(result.success_summary)
            self.assertIn(
                "OK locale-parity:", result.success_summary or ""
            )
            # Three flattened keys: common.a, common.b, k.
            self.assertIn("3 keys per side", result.success_summary or "")

    def test_fails_on_en_only_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._write_catalogues(
                repo,
                {"k": "v", "extra": "only-en"},
                {"k": "v"},
            )
            result = guard.run_parity_check(repo)
            self.assertFalse(result.passed)
            self.assertTrue(
                any(
                    "parity-en-only: extra" in line
                    for line in result.failure_lines
                ),
                result.failure_lines,
            )
            self.assertEqual(
                result.failure_lines[-1],
                "parity: en-only=1, zh-only=0",
            )
            self.assertIsNone(result.success_summary)

    def test_fails_on_zh_only_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._write_catalogues(
                repo,
                {"k": "v"},
                {"k": "v", "extra": "only-zh"},
            )
            result = guard.run_parity_check(repo)
            self.assertFalse(result.passed)
            self.assertTrue(
                any(
                    "parity-zh-only: extra" in line
                    for line in result.failure_lines
                ),
                result.failure_lines,
            )
            self.assertEqual(
                result.failure_lines[-1],
                "parity: en-only=0, zh-only=1",
            )

    def test_fails_on_two_sided_divergence_with_en_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._write_catalogues(
                repo,
                {"a": "v", "z": "v", "shared": "v"},
                {"b": "v", "y": "v", "shared": "v"},
            )
            result = guard.run_parity_check(repo)
            self.assertFalse(result.passed)
            categories = [
                "en-only" if "parity-en-only" in line else
                "zh-only" if "parity-zh-only" in line else
                "summary"
                for line in result.failure_lines
            ]
            # All en-only lines come before all zh-only lines, and the
            # summary is last.
            self.assertEqual(
                categories,
                [
                    "en-only", "en-only",
                    "zh-only", "zh-only",
                    "summary",
                ],
                result.failure_lines,
            )
            # Within each side keys appear lexicographically.
            en_only_lines = [
                line for line in result.failure_lines
                if "parity-en-only" in line
            ]
            zh_only_lines = [
                line for line in result.failure_lines
                if "parity-zh-only" in line
            ]
            self.assertTrue(en_only_lines[0].endswith(": a"))
            self.assertTrue(en_only_lines[1].endswith(": z"))
            self.assertTrue(zh_only_lines[0].endswith(": b"))
            self.assertTrue(zh_only_lines[1].endswith(": y"))
            self.assertEqual(
                result.failure_lines[-1],
                "parity: en-only=2, zh-only=2",
            )

    def test_passes_with_scalar_leaves_at_same_path(self) -> None:
        # Requirement 1.5: scalar leaves at the same dotted path on both
        # sides do not count as a parity divergence.
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._write_catalogues(
                repo,
                {"flag": True, "count": 42, "label": "x", "missing": None},
                {"flag": False, "count": 7, "label": "y", "missing": None},
            )
            result = guard.run_parity_check(repo)
            self.assertTrue(result.passed)

    def test_missing_zh_catalogue_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "locales").mkdir(parents=True)
            (repo / "locales" / "en.json").write_text(
                '{"k": "v"}\n', encoding="utf-8"
            )
            # zh.json deliberately not written.
            result = guard.run_parity_check(repo)
            self.assertFalse(result.passed)
            self.assertTrue(
                any(
                    "locales/zh.json" in line and "parity-error" in line
                    for line in result.failure_lines
                ),
                result.failure_lines,
            )


class RunCheckParityCompositionTests(unittest.TestCase):
    """End-to-end: ``run_check`` composes CJK, ratchet, and parity."""

    def _make_repo(
        self,
        tmp: Path,
        *,
        en_json: dict,
        zh_json: dict | None = None,
        backend_lines: int = 0,
    ) -> tuple[Path, Path]:
        repo = _make_repo(tmp)
        _commit_file(
            repo,
            "locales/en.json",
            json.dumps(en_json, indent=2, ensure_ascii=False),
        )
        zh_payload = zh_json if zh_json is not None else en_json
        _commit_file(
            repo,
            "locales/zh.json",
            json.dumps(zh_payload, indent=2, ensure_ascii=False),
        )
        if backend_lines:
            content = (
                "\n".join(f"# 中{i}" for i in range(backend_lines)) + "\n"
            )
            _commit_file(repo, "backend/app/x.py", content)
        else:
            _commit_file(repo, "backend/app/.gitkeep", "")
        _commit_file(repo, "frontend/src/.gitkeep", "")
        baseline_path = repo / "baseline.txt"
        return repo, baseline_path

    def test_clean_repo_emits_three_success_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, baseline_path = self._make_repo(
                Path(tmp),
                en_json={"k": "Confirm"},
            )
            guard.write_baseline(
                baseline_path,
                {"backend/app": 0, "frontend/src": 0},
            )
            from io import StringIO

            captured_out = StringIO()
            old_out = sys.stdout
            sys.stdout = captured_out
            try:
                rc = guard.run_check(repo, baseline_path)
            finally:
                sys.stdout = old_out
            self.assertEqual(rc, 0)
            stdout = captured_out.getvalue()
            self.assertIn("OK locales/en.json is CJK-clean", stdout)
            self.assertIn("OK per-path counts within baseline", stdout)
            self.assertIn("OK locale-parity:", stdout)

    def test_no_short_circuit_on_combined_failures(self) -> None:
        # Plant CJK in en.json AND a parity divergence so that BOTH
        # the existing CJK-clean check and the new parity check fail
        # in the same run. The orchestrator must run both blocks
        # without short-circuiting; both failure tokens must surface
        # in stderr together.
        with tempfile.TemporaryDirectory() as tmp:
            repo, baseline_path = self._make_repo(
                Path(tmp),
                en_json={"k": "Confirm", "extra": "中文"},
                zh_json={"k": "Confirm"},
            )
            guard.write_baseline(
                baseline_path,
                {"backend/app": 0, "frontend/src": 0},
            )
            from io import StringIO

            captured_err = StringIO()
            old_err = sys.stderr
            sys.stderr = captured_err
            try:
                rc = guard.run_check(repo, baseline_path)
            finally:
                sys.stderr = old_err
            self.assertEqual(rc, 1)
            err = captured_err.getvalue()
            # Both check categories must surface.
            self.assertIn("cjk-in-en", err)
            self.assertIn("parity-en-only: extra", err)
            self.assertIn("parity: en-only=1, zh-only=0", err)


if __name__ == "__main__":
    unittest.main()
