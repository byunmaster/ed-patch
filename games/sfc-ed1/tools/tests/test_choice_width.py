"""선택지·메뉴 창 칸 수 — 고정 칸 창(예/아니오·패배 선택·속도·도망·전투 설정)과 메뉴 라벨이 창 칸 안에 든다(원문 인용 없음)."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import text  # noqa: E402,F401,I001
import battle_ui  # noqa: E402
import namesrc  # noqa: E402
import textmap  # noqa: E402


class ChoiceWidth(unittest.TestCase):
    def test_fixed_cell_windows(self):
        # rows() 가 칸을 넘는 줄·줄 수 어긋남을 SystemExit 으로 막는다
        for g in battle_ui.GROUPS:
            out = battle_ui.rows(g["key"])
            self.assertEqual(len(out), g["count"])
            self.assertTrue(all(len(r) == g["cells"] for r in out), g["key"])

    def test_menu_labels_fit_budget(self):
        d = json.loads(textmap.MENUS_PATH.read_text(encoding="utf-8"))
        over = []
        for k, v in d.items():
            kr = v.get("kr")
            if not kr:
                hit = namesrc._ui_hit(k.split("@")[0])  # 정본에서 읽는다(자기 표 없음)
                kr = hit[0] if hit else None
            if kr and textmap.render_width(kr) > v["budget_tiles"]:
                over.append((k, textmap.render_width(kr), v["budget_tiles"]))
        self.assertEqual(over, [])


if __name__ == "__main__":
    unittest.main()
