"""쪽 경계(지표 i) — 문장 끝·절 경계에서만 쪽을 끊는다(규칙 2-16, 10-28 시녀 창). 원본 없이 돈다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared"))
import typeset as T


class PageEdge(unittest.TestCase):
    def test_modifier_object_subject_edges_are_not_ok(self):
        for prev, nxt in (("아주", "좋아하시는"), ("왕자님께서", "아주"), ("물건을", "돌려주러")):
            self.assertFalse(T.page_edge_ok(prev, nxt), (prev, nxt))

    def test_clause_edges_are_ok(self):
        for prev, nxt in (("때인데", "어떤"), ("있다고", "쓰여"), ("가지고,", "그리고")):
            self.assertTrue(T.page_edge_ok(prev, nxt), (prev, nxt))

    def test_polish_moves_the_page_edge_to_a_clause_edge(self):
        # 같은 쪽 수·줄 수 안에서 「…데리고｜지금까지」(연결어미) 꼴로 쪽이 끊긴다 — 종전엔 「…지금까지｜거둬들인」(관형 앞)이었다
        pg = T.pages("리스톤 백작님께서는 병사들을 데리고 지금까지 거둬들인 세금과 물건을 돌려주러 가셨습니다.", speaker=False)
        self.assertEqual(len(pg), 2)
        self.assertTrue(T.page_edge_ok(pg[0][-1].rsplit(" ", 1)[-1], pg[1][0].split(" ", 1)[0]), pg)

    def test_unfixable_edge_stays_put(self):
        # 시녀 줄 — 절 경계가 없고 첫 줄 폭(화자 창 120px) 때문에 한 창에도 안 들어간다. 조판기는 억지로 옮기지 않는다(문안 판정 대기)
        pg = T.pages("오늘 저녁은 왕자님께서 아주 좋아하시는 비프 스튜입니다.", speaker=True)
        self.assertEqual(len(pg), 2)


if __name__ == "__main__":
    unittest.main()
