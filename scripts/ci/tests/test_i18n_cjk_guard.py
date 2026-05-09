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
    ) -> tuple[Path, Path]:
        repo = _make_repo(tmp)
        _commit_file(
            repo,
            "locales/en.json",
            json.dumps(en_json, indent=2, ensure_ascii=False),
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


if __name__ == "__main__":
    unittest.main()
