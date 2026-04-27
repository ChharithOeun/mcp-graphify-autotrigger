"""Unit tests for mcp_server.agent_tools - the parity layer that lets Cowork
and Claude Code delegate every primitive (Read/Write/Edit/Glob/Grep/Bash) to
chharbot's MCP without losing capability.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Make the package importable when running tests directly.
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from mcp_server import agent_tools  # noqa: E402


class _MockMCP:
    """Minimal FastMCP stand-in for unit tests.

    Captures registered tool functions so tests can call them directly without
    spinning up a real MCP transport.
    """
    def __init__(self) -> None:
        self.fns: dict = {}

    def tool(self, fn):
        self.fns[fn.__name__] = fn
        return fn


class AgentToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mcp = _MockMCP()
        agent_tools.register(cls.mcp)
        cls.tmp = Path(tempfile.mkdtemp(prefix="chharbot-agent-tools-"))

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ---- registration ----------------------------------------------------

    def test_all_eight_tools_registered(self) -> None:
        expected = {
            "read_file", "write_file", "edit_file",
            "glob_files", "grep_files", "bash",
            "skill_dispatch", "list_skills",
        }
        self.assertEqual(expected, set(self.mcp.fns.keys()))

    # ---- write/read/edit cycle ------------------------------------------

    def test_write_then_read_roundtrip(self) -> None:
        p = self.tmp / "rw.txt"
        r = self.mcp.fns["write_file"](str(p), "alpha\nbeta\ngamma\n")
        self.assertTrue(r["ok"])
        self.assertEqual(r["bytes_written"], 17)

        r = self.mcp.fns["read_file"](str(p))
        self.assertTrue(r["ok"])
        self.assertEqual(r["total_lines"], 3)
        self.assertEqual(r["lines"][1]["text"], "beta")

    def test_edit_unique_replacement(self) -> None:
        p = self.tmp / "edit_unique.txt"
        p.write_text("hello world\n")
        r = self.mcp.fns["edit_file"](str(p), "world", "chharbot")
        self.assertTrue(r["ok"])
        self.assertEqual(r["replacements"], 1)
        self.assertEqual(p.read_text(), "hello chharbot\n")

    def test_edit_rejects_ambiguous_match(self) -> None:
        p = self.tmp / "edit_ambig.txt"
        p.write_text("foo foo foo\n")
        r = self.mcp.fns["edit_file"](str(p), "foo", "BAR")
        self.assertFalse(r["ok"])
        self.assertIn("3 occurrences", r["error"])
        # but replace_all=True should succeed
        r = self.mcp.fns["edit_file"](str(p), "foo", "BAR", replace_all=True)
        self.assertTrue(r["ok"])
        self.assertEqual(r["replacements"], 3)

    def test_edit_old_string_not_found(self) -> None:
        p = self.tmp / "edit_miss.txt"
        p.write_text("only this\n")
        r = self.mcp.fns["edit_file"](str(p), "absent", "x")
        self.assertFalse(r["ok"])
        self.assertIn("not found", r["error"])

    # ---- glob ------------------------------------------------------------

    def test_glob_finds_files(self) -> None:
        sub = self.tmp / "globtest"
        sub.mkdir(exist_ok=True)
        (sub / "a.py").write_text("# a")
        (sub / "b.py").write_text("# b")
        (sub / "c.txt").write_text("# c")
        r = self.mcp.fns["glob_files"]("*.py", path=str(sub))
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["files"]), 2)

    # ---- grep ------------------------------------------------------------

    def test_grep_files_with_matches(self) -> None:
        sub = self.tmp / "greptest"
        sub.mkdir(exist_ok=True)
        (sub / "match.txt").write_text("the needle is here")
        (sub / "skip.txt").write_text("nothing relevant")
        r = self.mcp.fns["grep_files"]("needle", path=str(sub),
                                       output_mode="files_with_matches")
        self.assertTrue(r["ok"])
        self.assertTrue(any("match.txt" in s for s in r["results"]))

    # ---- bash ------------------------------------------------------------

    def test_bash_captures_stdout_and_exit(self) -> None:
        r = self.mcp.fns["bash"]("echo chharbot-mcp-test")
        self.assertTrue(r["ok"])
        self.assertIn("chharbot-mcp-test", r["stdout"])

        r = self.mcp.fns["bash"]("exit 13" if sys.platform != "win32" else "exit /b 13")
        self.assertEqual(r["exit_code"], 13)
        self.assertFalse(r["ok"])

    def test_bash_timeout(self) -> None:
        # very short timeout against a sleep — should error cleanly, not hang
        sleep_cmd = "ping -n 5 127.0.0.1 >NUL" if sys.platform == "win32" else "sleep 5"
        r = self.mcp.fns["bash"](sleep_cmd, timeout=1)
        self.assertFalse(r["ok"])
        self.assertIn("timed out", r["error"])

    # ---- skill dispatch + list ------------------------------------------

    def test_skill_dispatch_rejects_path_traversal(self) -> None:
        for bad in ["../etc/passwd", "../../foo", "/etc/passwd", "skill name with spaces"]:
            r = self.mcp.fns["skill_dispatch"](bad)
            self.assertFalse(r["ok"], msg=f"should reject: {bad}")

    def test_skill_dispatch_returns_skill_md(self) -> None:
        # Stage a fake skill dir so the test is self-contained
        fake_root = self.tmp / "fake_skills"
        skill_dir = fake_root / "demo-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: demo-skill\ndescription: test fixture\n---\n# demo\n"
        )
        os.environ["CHHARBOT_SKILLS_DIR"] = str(fake_root)
        try:
            r = self.mcp.fns["skill_dispatch"]("demo-skill")
            self.assertTrue(r["ok"])
            self.assertIn("demo-skill", r["content"])
        finally:
            os.environ.pop("CHHARBOT_SKILLS_DIR", None)

    def test_list_skills_empty_when_root_missing(self) -> None:
        os.environ["CHHARBOT_SKILLS_DIR"] = str(self.tmp / "doesnotexist")
        try:
            r = self.mcp.fns["list_skills"]()
            self.assertTrue(r["ok"])
            self.assertEqual(r["skills"], [])
        finally:
            os.environ.pop("CHHARBOT_SKILLS_DIR", None)


if __name__ == "__main__":
    unittest.main()
