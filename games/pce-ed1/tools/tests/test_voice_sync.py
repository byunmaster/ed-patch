"""편집기 「싱크 확인 끝」(`sync: true`) → 시각표 토막 확정(`draft` 를 뗀다) — 11-07."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import voice_editor_apply as A
import voice_sched as VS


class ApplySync(unittest.TestCase):
    def test_sync_true_drops_draft(self):
        spec = {"scenes": {"73": {"voice_gate": 0, "draft": {"src": "x"}, "msgs": [{"key": "a", "ends": [1.0]}]}, "74": [{"voice_gate": 0, "draft": {"src": "y"}, "msgs": []}]}}
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "s.json"
            p.write_text(json.dumps(spec), "utf-8")
            old, VS.SPEC = VS.SPEC, p
            try:
                done = A.apply_sync([{"clip": "scn073_s0", "sync": True}, {"clip": "scn074_s0", "sync": False}])
                out = json.loads(p.read_text("utf-8"))
            finally:
                VS.SPEC = old
        self.assertEqual(done, ["scn073_s0"])
        self.assertNotIn("draft", out["scenes"]["73"])
        self.assertIn("synced", out["scenes"]["73"])
        self.assertIn("draft", out["scenes"]["74"][0])  # sync 아닌 토막은 그대로


if __name__ == "__main__":
    unittest.main()
