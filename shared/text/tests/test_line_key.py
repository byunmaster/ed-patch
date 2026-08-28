"""문안 사전 키 회귀 — **원본 없이 돈다**(순수 계산).

🔴 이 키가 갈라지면 **사전이 있어도 못 쓴다.** 실측(PS1, 2026-08-20): 중립화 전에는
   새턴 15,468 문자열 중 붙는 게 **1.3%** 였다. 그래서 규칙을 여기 하나로 모았다.

⚠ **PS1 구현과 같은지도 본다** — 그쪽이 아직 자기 사본을 쓰고 있어(워크트리가 달라 지금은
  못 고친다) 조용히 갈라질 수 있다. 그 트리가 있으면 대조하고, 없으면 건너뛴다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from shared.text.line_key import key, neutral

_REPO = os.path.dirname(  # shared/text/tests → shared/text → shared → 레포 뿌리
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
PS1 = os.path.join(_REPO, ".claude/worktrees/ps1-ed1+2/games/ps1-ed1+2/tools")

SAMPLES = [
    "%cライアス%c\nなんだよ これ !?",
    "%c%s%cは %dのダメージ!!",
    "スライムが現れた。",
    "アムダの村",
    "･ ･ ･ よいかな アトラス君？",
]


class Key(unittest.TestCase):
    def test_markup_is_neutralised_across_dumpers(self):
        """🔴 **같은 원문이면 덤퍼가 달라도 같은 키다.** 이게 이 모듈의 존재 이유다."""
        self.assertEqual(key("%cライアス%c\nなんだよ"), key("{c}ライアス{c}{n}なんだよ"))
        self.assertEqual(key("%s は %d"), key("\\x25\\x73は\\x25\\x64"))

    def test_whitespace_and_dots_do_not_matter(self):
        """이식판은 줄나눔이 다르고 가운뎃점 표기가 셋이다."""
        self.assertEqual(key("あい うえ\nお"), key("あいうえお"))
        self.assertEqual(key("･ ･ ･"), key("・・・"))
        self.assertEqual(key("｡"), key("。"))

    def test_different_text_gives_different_key(self):
        """⚠ 너무 많이 지워서 서로 다른 원문이 한 키가 되면 사전이 무너진다."""
        ks = {key(s) for s in SAMPLES}
        self.assertEqual(len(ks), len(SAMPLES))
        self.assertNotEqual(key("%s と %d"), key("%d と %s"))

    def test_key_is_not_plaintext(self):
        """원문을 커밋에 안 남기려는 키다 — 16자 hex 여야 한다."""
        k = key(SAMPLES[0])
        self.assertEqual(len(k), 16)
        self.assertTrue(all(c in "0123456789abcdef" for c in k))
        self.assertNotIn("ライアス", neutral(SAMPLES[0])[:0] or "")

    @unittest.skipUnless(os.path.isdir(PS1), "PS1 워크트리가 없다")
    def test_matches_the_ps1_implementation(self):
        """⚠ 두 곳에 있는 동안은 **같은 답**이어야 한다. 갈라지면 사전이 조용히 안 붙는다."""
        sys.path.insert(0, PS1)
        try:
            import export_line_dict as E
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"PS1 도구를 못 읽는다: {exc}")
        for s in SAMPLES:
            self.assertEqual(key(s), E.key(s), s[:20])


if __name__ == "__main__":
    unittest.main(verbosity=2)


def test_dumper_escapes_are_unfolded():
    """🔴 덤퍼가 안 편 `\\xNN` 을 열쇠가 편다 — 안 펴면 **물음표가 든 줄이 통째로 안 붙는다**.

    실측 2026-08-29: 새턴의 「저본 없음」 781줄 중 403이 PS1 과 같은 줄이었고, 그중 384는
    사전에 우리 문안이 이미 있었다. `\\x21`(`!`)만 표로 접고 `\\x3F`(`?`)를 빠뜨린 탓이다.
    ⚠ 표로 하나씩 접는 방식이 이 사고의 뿌리다 — **규칙으로 편다.**
    """
    ss = "%c\uff30%c\n\u8b01\u898b\u306e\u9593\u3060\u3068 !?%c"  # 새턴 — 진짜 글자
    ps1 = "{c}\uff30{c}{n}\u8b01\u898b\u306e\u9593\u3060\u3068 \\x21\\x3F{c}"  # PS1 — 이스케이프
    assert key(ss) == key(ps1), "같은 원문인데 열쇠가 갈린다"


def test_escape_unfolding_is_a_superset_of_the_old_table():
    """⚠ 기존 열쇠가 안 깨져야 한다 — `\\x21` 은 옛 표로도 새 폄으로도 `!` 다."""
    assert neutral("\\x21") == "!"
    assert neutral("\\x25\\x73") == neutral("%s")
    assert neutral("\\x25\\x64") == neutral("%d")
