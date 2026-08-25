"""`ss_gameid.py` — mednafen GameID 계산. **원본 없이** 합성 이미지로 돈다.

🔴 지키는 것: **앞 512 섹터만 본다.** 한글패치가 고치는 게 대개 그 안이라(ss-ed3 는
`/0.BIN` 48 · `KANJI12.FON` 358 · `PARAM.BIN` 431) 빌드마다 GameID 가 바뀌고, 그러면
세이브가 **조용히 안 읽힌다**. 반대로 뒤쪽(`MAP*.BIN` 3203+)만 고치면 안 바뀐다 —
그래서 대사만 건드리던 동안에는 이 함정이 안 보였다.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ss_gameid import SECTOR, fit, game_id, resolve


def _img(path, sectors=600, mark=None):
    with open(path, "wb") as f:
        for i in range(sectors):
            body = bytes([(i * 7) & 0xFF]) * SECTOR
            if mark and i == mark:
                body = b"\xa5" * SECTOR
            f.write(body)
    return path


class GameId(unittest.TestCase):
    def test_only_first_512_sectors_matter(self):
        with tempfile.TemporaryDirectory() as d:
            base = game_id(_img(os.path.join(d, "a.bin")))
            inside = game_id(_img(os.path.join(d, "b.bin"), mark=431))  # PARAM.BIN 자리
            outside = game_id(_img(os.path.join(d, "c.bin"), mark=520))  # MAP 자리
            self.assertNotEqual(base, inside, "앞 512 섹터를 고치면 GameID 가 바뀌어야 한다")
            self.assertEqual(base, outside, "512 섹터 밖은 GameID 에 안 들어간다")

    def test_size_changes_the_id(self):
        # leadout LBA 가 TOC 에 들어가므로 총 섹터 수가 달라지면 GameID 도 달라진다.
        with tempfile.TemporaryDirectory() as d:
            a = game_id(_img(os.path.join(d, "a.bin"), sectors=600))
            b = game_id(_img(os.path.join(d, "b.bin"), sectors=601))
            self.assertNotEqual(a, b)

    def test_fit_copies_and_keeps_the_old_name(self):
        # ⚠ 옛 이름을 **지우지 않는다** — 다른 빌드로 되돌아갔을 때 필요하다.
        import glob

        with tempfile.TemporaryDirectory() as d:
            img = _img(os.path.join(d, "g.bin"), sectors=520)
            sav = os.path.join(d, "sav")
            os.makedirs(sav)
            for e in ("bkr", "bcr", "smpc"):
                with open(os.path.join(sav, f"Game.deadbeef.{e}"), "wb") as f:
                    f.write(b"\x01")
            gid, n, old = fit(sav, img)
            self.assertEqual((old, n), ("deadbeef", 3))
            got = {os.path.basename(x) for x in glob.glob(os.path.join(sav, "*.bkr"))}
            self.assertEqual(got, {"Game.deadbeef.bkr", f"Game.{gid}.bkr"})
            # 두 번 돌려도 아무 일 없다
            self.assertEqual(fit(sav, img)[1], 0)

    def test_resolve_follows_cue(self):
        with tempfile.TemporaryDirectory() as d:
            _img(os.path.join(d, "x.bin"), sectors=520)
            cue = os.path.join(d, "x.cue")
            with open(cue, "w", encoding="utf-8") as f:
                f.write('FILE "x.bin" BINARY\n  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n')
            self.assertEqual(resolve(cue), os.path.join(d, "x.bin"))


if __name__ == "__main__":
    unittest.main()
