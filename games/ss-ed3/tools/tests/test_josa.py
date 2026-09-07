"""일반 낱말 뒤 조사 검사 회귀 — **원본 없이 돈다**(순수 문자열 계산).

🔴 이 검사가 있는 이유는 **정본에 없는 낱말은 고유명사 검사가 안 보기 때문**이다
(2026-09-03 실측: `大蛇` 가 표에 없어 「큰뱀를」 넷을 못 봤다).

🔴 헛걸림을 거르는 규칙이 핵심이다 — **앞말이 딴 자리에서 홀로도 쓰이는 낱말인가**.
   받침만 보면 `마을을`·`무화과와` 가 죄다 걸린다(실측 167 건). 이 테스트가 그 둘을
   같이 못 박는다 — 규칙을 단순화하려다 소음이 돌아오는 걸 막는다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import check_josa as J


class General(unittest.TestCase):
    def rows(self, *texts):
        return [("t.json", str(i), s) for i, s in enumerate(texts)]

    def test_catches_wrong_josa_after_known_word(self):
        #   `큰뱀` 이 딴 줄에서 홀로 쓰이므로 `큰뱀를` 은 조사다 → 받침이 있으니 `큰뱀을`
        bad = J.scan_general(self.rows("큰뱀 등뼈", "큰뱀를 이긴 거인", "산맥만 한 큰뱀와 싸운"))
        self.assertEqual([x[2] for x in bad], ["큰뱀를", "큰뱀와"])
        self.assertEqual([x[3] for x in bad], ["큰뱀을", "큰뱀과"])

    def test_ignores_syllable_inside_word(self):
        #   `마`·`무화`·`사` 는 홀로 안 쓰인다 → `마을을`·`무화과와`·`사과를` 은 낱말이다
        self.assertEqual(
            J.scan_general(self.rows("마을을 나섰다", "무화과와 사과를", "항구마을과 배")), []
        )

    def test_ignores_correct_josa(self):
        self.assertEqual(
            J.scan_general(self.rows("크리스 는", "크리스를 보았다", "쥬리오", "쥬리오를")), []
        )


if __name__ == "__main__":
    unittest.main()
