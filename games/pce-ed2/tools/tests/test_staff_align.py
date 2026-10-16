"""스태프롤 정렬(마스터 10-16 D안) — 쪽 전체를 8px 당기고(라벨 132 · 이름 148) 이름이 라벨보다 +16 인 원판 규칙을 지킨다. 12px(C안)은 그림 틀을 지워 못 쓴다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common
import ending as en


class Pad(unittest.TestCase):
    def test_당김은_앞_여백만으로_8px이다(self):
        """엔진 시작 열을 안 건드린다 — 열 14 는 그림 틀 오른쪽 테두리(x116~122)라 글자 타일이 덮으면 틀이 지워진다(시험 롬 실측)."""
        self.assertEqual(en.STAFF_SHIFT, 8)
        self.assertFalse(hasattr(en, "ENGINE_SHIFT"))

    def test_원판_앞_여백이_화면_x_로_옮겨진다(self):
        """원판 시작 x = 124 + 앞 여백. 라벨(16) → 132, 이름(32) → 148."""
        for orig_pre, want_x in ((16, 132), (32, 148)):
            pre = en._emit_pre(b"", max(0, orig_pre - en.STAFF_SHIFT))
            self.assertEqual(en.X0 + en._pre_px(pre), want_x, orig_pre)

    def test_앞_여백은_탭_공백_전각공백으로_만든다(self):
        self.assertEqual(en._compose(12), b"\x81\x40")
        self.assertEqual(en._compose(28), b"\x09\x81\x40")
        self.assertEqual(en._compose(0), b"")
        self.assertEqual(en._compose(4), b"\x20")  # 못 만드는 4 는 윗값 8


@unittest.skipUnless(common.ORIG_ISO.exists(), "원본 이미지 없음")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pkg = common.track_data(en.PKG_REL, 47)
        cls.text, cls.chars = en.build(cls.pkg)

    def test_줄은_화면_x124_부터_한계_안이다(self):
        started = False  # 첫 쪽(오프닝 대사 두 줄)은 당기지 않으니 건너뛴다
        for l in self.text.split(b"\r\n"):
            if b"\x1a" in l:
                break
            if not started:
                started = l.startswith(b"/*")
                continue
            pre, body, _suf = en._split_line(l)
            if not body or l.startswith(b"/*"):
                continue
            x = en.X0 + en._pre_px(pre)
            w = 0
            i = 0
            while i < len(body):
                w += 12 if body[i] >= 0x80 else 8
                i += 2 if body[i] >= 0x80 else 1
            if body.endswith(b")"):  # 끝 괄호는 칸 왼쪽 3px 만 잉크 — 오른쪽 빈 4px 는 한계 판정에서 뺀다
                w -= 4
            self.assertGreaterEqual(x, 124, l)
            self.assertLessEqual(x + w, en.LINE_LIMIT, l)

    def test_쪽마다_라벨_132_이름_148_열이다(self):
        """마스터 10-16 — 쪽 안 줄 시작 x 는 라벨 132 · 이름 148 뿐이다(괄호 줄도 반각 괄호라 이름 열). 예외는 사운드 팀 +8(156) · J.D.K +16(164), 제목 쪽(`스태프` · `제작・저작`)."""
        pages = [[]]
        for l in self.text.split(b"\r\n"):
            if b"\x1a" in l:
                break
            if l.startswith(b"/*"):
                pages.append([])
                continue
            pre, body, _suf = en._split_line(l)
            if body:
                pages[-1].append(en.X0 + en._pre_px(pre))
        for pi, xs in enumerate(pages):
            if pi < 2 or pi == len(pages) - 1 or not xs:  # 오프닝 대사 · 제목 쪽 · 마지막 로고 쪽
                continue
            self.assertLessEqual(set(xs), {132, 148, 156, 164}, (pi, sorted(set(xs))))

    def test_이그제큐티브_프로듀서는_두_줄이다(self):
        self.assertIn("이그제큐티브 프로듀서", en.FORCE_SPLIT)

    def test_괄호와_가운뎃점은_반각이다(self):
        """마스터 10-16 「문장부호는 반각」 — 괄호는 8px 한 바이트(`28` `29`)로 그리고 글리프는 우리 괄호, 가운뎃점은 원판 반각 점(`A5`)."""
        self.assertEqual(en._text_px("（스튜디오 라이브）"), 8 + 12 * 7 + 8 + 8 - 4)  # 끝 괄호 오른쪽 빈 4px 는 뺀다
        self.assertEqual(en._text_px("제작・총지휘"), 12 * 2 + 8 + 12 * 3)
        g = en.paren_glyphs()
        self.assertEqual(set(g), {0x28, 0x29})
        for code, gl in g.items():
            self.assertEqual(len(gl), 16)
            ink = 0
            for row in gl:
                ink |= row
            cols = [c for c in range(8) if ink & (0x80 >> c)]
            # 괄호는 칸 안쪽 가장자리 3px — `(` 는 오른쪽(열 4~6), `)` 는 왼쪽(열 1~3)
            self.assertEqual((min(cols), max(cols)), (4, 6) if code == 0x28 else (1, 3))

    def test_엔진_쓰기는_글리프_후킹뿐이다(self):
        """시작 열·칸 지우기 폭을 안 건드린다."""
        spans, _info = en.writes(self.pkg)
        for s in spans:
            self.assertNotIn("시작 열", s[3])
            self.assertNotIn("칸 지우기", s[3])
        self.assertEqual(sum("반각 괄호 글리프" in s[3] for s in spans), 2)


if __name__ == "__main__":
    unittest.main()
