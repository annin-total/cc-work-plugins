"""retitle の hook がディレクトリ名を要約の後ろへ移す処理の単体テスト。"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_retitle import HOOK, _load

LABELS = ["cc-work-plugins", "my-repo"]


class RelocateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.hook = _load("retitle_relocate", HOOK)
        patches = (
            mock.patch.object(self.hook, "_dir_labels", return_value=LABELS),
            mock.patch.object(self.hook, "_branch", return_value="feat/x"),
        )
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_leading_dir_name_moves_after_summary(self) -> None:
        for title in ("my-repo 認証の調査 · feat/x", "my-repo の認証の調査 · feat/x"):
            self.assertEqual(
                self.hook._relocate(title, "."),
                ("認証の調査 · my-repo · feat/x", "認証の調査", "my-repo"),
            )

    def test_old_order_is_rearranged(self) -> None:
        self.assertEqual(
            self.hook._relocate("認証の調査 · feat/x · my-repo", ".")[0],
            "認証の調査 · my-repo · feat/x",
        )

    def test_new_order_and_plain_titles_stay(self) -> None:
        for title in (
            "認証の調査 · my-repo · feat/x",
            "認証の調査 · feat/x",
            "my-repo",
            "my-repository の調査",
        ):
            self.assertEqual(self.hook._relocate(title, ".")[0], title)

    def test_sanitize_and_compose_put_dir_name_before_branch(self) -> None:
        base, repo = self.hook._sanitize("「cc-work-plugins の retitle 同期」\n", ".")
        self.assertEqual((base, repo), ("retitle 同期", "cc-work-plugins"))
        self.assertEqual(
            self.hook._compose(base, "feat/x", repo),
            "retitle 同期 · cc-work-plugins · feat/x",
        )


class DirLabelsTest(unittest.TestCase):
    def test_ancestors_and_workspace_children_longest_first(self) -> None:
        hook = _load("retitle_labels", HOOK)
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            for sub in ("a-b/long-child", "plain/c-d", ".hidden-x", "x/y/too-deep"):
                (ws / sub).mkdir(parents=True)
            cwd = ws / "a-b"
            env = {"CLAUDE_PROJECT_DIR": str(ws)}
            with mock.patch.dict(os.environ, env), mock.patch.object(
                hook, "_git", return_value=None
            ):
                labels = hook._dir_labels(str(cwd))
        self.assertEqual(labels, ["long-child", "a-b", "c-d"])


class SpawnFailureTest(unittest.TestCase):
    def test_request_is_removed_when_judge_cannot_start(self) -> None:
        hook = _load("retitle_spawn", HOOK)
        with tempfile.TemporaryDirectory() as tmp:
            payload = {
                "session_id": "s1",
                "prompt": "秘密を含むかもしれない長い依頼文です",
            }
            stdin = mock.Mock()
            stdin.buffer.read.return_value = json.dumps(payload).encode("utf-8")
            with mock.patch.object(hook, "CACHE_DIR", Path(tmp)), mock.patch.object(
                hook.sys, "stdin", stdin
            ), mock.patch.object(hook, "_spawn_judge", side_effect=OSError("denied")):
                with self.assertRaises(OSError):
                    hook._hook()
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), [])


class HookRequestTest(unittest.TestCase):
    """判定に渡す依頼と、判定結果の保存。"""

    def setUp(self) -> None:
        self.hook = _load("retitle_request", HOOK)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cache = Path(tmp.name)
        for patch in (
            mock.patch.object(self.hook, "CACHE_DIR", self.cache),
            mock.patch.object(self.hook, "_dir_labels", return_value=LABELS),
            mock.patch.object(self.hook, "_branch", return_value="feat/x"),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def test_renamed_title_keeps_dir_name_in_request(self) -> None:
        payload = {
            "session_id": "s1",
            "prompt": "別の観点からもう少し詳しく調べてほしい",
            "session_title": "認証の調査 · my-repo · feat/x",
            "cwd": ".",
        }
        stdin = mock.Mock()
        stdin.buffer.read.return_value = json.dumps(payload).encode("utf-8")
        with mock.patch.object(self.hook.sys, "stdin", stdin), mock.patch.object(
            self.hook, "_spawn_judge"
        ):
            self.hook._hook()
        req = json.loads((self.cache / "s1.req").read_text(encoding="utf-8"))
        self.assertEqual((req["base"], req["repo"]), ("認証の調査", "my-repo"))

    def test_keep_preserves_dir_name(self) -> None:
        req = {"prompt": "p", "base": "認証の調査", "repo": "my-repo"}
        req.update({"cwd": ".", "current": ""})
        (self.cache / "s1.req").write_text(json.dumps(req), encoding="utf-8")
        with mock.patch.object(self.hook, "_ask_model", return_value="KEEP\n"):
            self.hook._judge("s1")
        state = json.loads((self.cache / "s1.json").read_text(encoding="utf-8"))
        self.assertEqual(state["title"], "認証の調査 · my-repo · feat/x")


if __name__ == "__main__":
    unittest.main()
