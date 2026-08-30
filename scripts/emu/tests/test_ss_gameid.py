"""`ss_gameid.py` — mednafen GameID 계산. **원본 없이** 합성 이미지로 돈다.

🔴 지키는 것 둘.

1. **앞 512 섹터만 본다.** 한글패치가 고치는 게 대개 그 안이라(ss-ed3 는 `/0.BIN` 48 ·
   `KANJI12.FON` 358 · `PARAM.BIN` 431) 빌드마다 GameID 가 바뀌고, 그러면 세이브가
   **조용히 안 읽힌다**. 반대로 뒤쪽(`MAP*.BIN` 3203+)만 고치면 안 바뀐다 — 그래서 대사만
   건드리던 동안에는 이 함정이 안 보였다.
2. **TOC 를 진짜로 읽는다**(2026-08-29 실측). 「데이터 트랙 하나」로 넘겨짚던 판은 우리
   이미지에서 틀렸다 — ss-ed3 는 데이터 1 + 오디오 1, ss-ed1+2 는 데이터 1 + **오디오 31**
   이다. 계산값이 어긋나면 `--fit` 이 **mednafen 이 쳐다보지도 않는 이름**으로 사본을 뜬다.

⚠ 이 파일은 `SECTOR`·`resolve` 를 쓰던 옛 판을 갈아 쓴 것이다 — 모듈이 cue/TOC 기반으로
  다시 쓰이면서 그 두 이름이 없어졌고, 테스트만 남아 **게이트가 통째로 빨간불**이었다.
"""

import glob
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ss_gameid  # noqa: E402
from ss_gameid import build_toc, fit, game_id, parse_cue  # noqa: E402

RAW = 2352  # MODE1/2352 — 우리 새턴 이미지가 전부 이 꼴이다


def _sector(i, mode=1, form=1, fill=None):
    """생 섹터 하나.

    ⚠ 유저 데이터가 어디 있는지는 cue 가 아니라 **섹터 헤더의 모드 바이트(오프셋 15)** 가
      정한다 — 모드1 은 16, 모드2 form1 은 24. 모드2 는 서브헤더(18)의 `0x20` 이 form2 다.
    """
    body = bytes([fill if fill is not None else (i * 7) & 0xFF]) * 2048
    sec = bytearray(RAW)
    sec[0:12] = b"\x00" + b"\xff" * 10 + b"\x00"
    sec[12:15] = bytes((i // 4500, (i // 75) % 60, i % 75))
    sec[15] = mode
    if mode == 2:
        sec[16:24] = bytes(8)
        if form == 2:
            sec[18] |= 0x20
            sec[22] |= 0x20
        sec[24 : 24 + 2048] = body
    else:
        sec[16 : 16 + 2048] = body
    return bytes(sec)


def _bin(path, sectors=600, mark=None, mode=1, form=1):
    with open(path, "wb") as f:
        for i in range(sectors):
            fill = 0xA5 if mark is not None and i == mark else None
            f.write(_sector(i, mode=mode, form=form, fill=fill))
    return path


def _cue(path, binname, body):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f'FILE "{binname}" BINARY\n{body}')
    return path


DATA_ONLY = "  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n"
DATA_PLUS_AUDIO = DATA_ONLY + "  TRACK 02 AUDIO\n    INDEX 01 00:08:00\n"  # 600섹터 뒤


class GameId(unittest.TestCase):
    def test_only_first_512_sectors_matter(self):
        """🔴 이 파일의 존재 이유 — 512 안을 고치면 이름이 바뀌고, 밖은 안 바뀐다."""
        with tempfile.TemporaryDirectory() as d:
            base = game_id(_bin(os.path.join(d, "a.bin")))
            inside = game_id(_bin(os.path.join(d, "b.bin"), mark=431))  # PARAM.BIN 자리
            outside = game_id(_bin(os.path.join(d, "c.bin"), mark=520))  # MAP 자리
            self.assertNotEqual(base, inside, "앞 512 섹터를 고치면 GameID 가 바뀌어야 한다")
            self.assertEqual(base, outside, "512 섹터 밖은 GameID 에 안 들어간다")

    def test_size_changes_the_id(self):
        """리드아웃 LBA 가 TOC 에 들어가므로 총 섹터 수가 달라지면 GameID 도 달라진다."""
        with tempfile.TemporaryDirectory() as d:
            a = game_id(_bin(os.path.join(d, "a.bin"), sectors=600))
            b = game_id(_bin(os.path.join(d, "b.bin"), sectors=601))
            self.assertNotEqual(a, b)

    def test_audio_track_changes_the_id(self):
        """🔴 TOC 를 진짜로 읽는가 — 같은 bin 이라도 **오디오 트랙을 선언하면** 값이 다르다.

        넘겨짚던 옛 판은 둘을 같게 봤고, 그래서 실제 이미지에서 어긋났다
        (`4be90310…` vs 진짜 `cf6b0bc1…`).
        """
        with tempfile.TemporaryDirectory() as d:
            _bin(os.path.join(d, "x.bin"), sectors=700)
            one = game_id(_cue(os.path.join(d, "one.cue"), "x.bin", DATA_ONLY))
            two = game_id(_cue(os.path.join(d, "two.cue"), "x.bin", DATA_PLUS_AUDIO))
            self.assertNotEqual(one, two, "트랙 구성이 다르면 GameID 가 달라야 한다")

    def test_toc_numbers_follow_the_cue(self):
        """first·last·LBA·리드아웃 control 을 cue 에서 유도한다."""
        with tempfile.TemporaryDirectory() as d:
            _bin(os.path.join(d, "x.bin"), sectors=700)
            tracks = parse_cue(_cue(os.path.join(d, "two.cue"), "x.bin", DATA_PLUS_AUDIO))
            first, last, total = build_toc(tracks)
            self.assertEqual((first, last), (1, 2))
            self.assertEqual([t["lba"] for t in tracks], [0, 600])
            self.assertEqual([t["control"] for t in tracks], [4, 0], "데이터 4 · 오디오 0")
            self.assertEqual(total, 700, "리드아웃 LBA = 총 섹터 수")

    def test_audio_sectors_are_not_hashed(self):
        """오디오 트랙의 바이트는 해시에 안 들어간다 — 512 안이어도 그렇다."""
        with tempfile.TemporaryDirectory() as d:
            # 오디오가 LBA 100 부터 시작하도록 잘라 둔다(=00:01:25)
            body = "  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n"
            body += "  TRACK 02 AUDIO\n    INDEX 01 00:01:25\n"
            _bin(os.path.join(d, "a.bin"), sectors=600)
            _bin(os.path.join(d, "b.bin"), sectors=600, mark=300)  # 오디오 구간 안
            a = game_id(_cue(os.path.join(d, "a.cue"), "a.bin", body))
            b = game_id(_cue(os.path.join(d, "b.cue"), "b.bin", body))
            self.assertEqual(a, b, "오디오 구간을 고쳐도 GameID 는 안 바뀐다")

    def test_mode2_form2_is_skipped(self):
        """모드 2 **form2** 는 mednafen 이 통째로 버린다 — 512 안이어도 해시에 안 들어간다."""
        with tempfile.TemporaryDirectory() as d:
            a = _bin(os.path.join(d, "a.bin"), sectors=600, mode=2, form=2)
            b = _bin(os.path.join(d, "b.bin"), sectors=600, mode=2, form=2, mark=100)
            self.assertEqual(game_id(a), game_id(b))

    def test_mode2_form1_reads_from_offset_24(self):
        """모드 2 form1 은 서브헤더 뒤(24)가 유저 데이터다 — 고치면 GameID 가 바뀐다."""
        with tempfile.TemporaryDirectory() as d:
            a = _bin(os.path.join(d, "a.bin"), sectors=600, mode=2)
            b = _bin(os.path.join(d, "b.bin"), sectors=600, mode=2, mark=100)
            self.assertNotEqual(game_id(a), game_id(b))

    def test_unknown_mode_is_skipped(self):
        """모드가 1·2 가 아니면(긁힌 섹터 등) mednafen 은 0 을 주고 해시에서 뺀다."""
        with tempfile.TemporaryDirectory() as d:
            a = _bin(os.path.join(d, "a.bin"), sectors=600, mode=3)
            b = _bin(os.path.join(d, "b.bin"), sectors=600, mode=3, mark=100)
            self.assertEqual(game_id(a), game_id(b))

    def test_bare_bin_is_one_data_track(self):
        """cue 없이 `.bin` 을 주면 데이터 트랙 하나로 친다 — mednafen 이 그렇게 읽는다."""
        with tempfile.TemporaryDirectory() as d:
            raw = _bin(os.path.join(d, "x.bin"), sectors=600)
            viacue = _cue(os.path.join(d, "x.cue"), "x.bin", DATA_ONLY)
            self.assertEqual(game_id(raw), game_id(viacue))


class Fit(unittest.TestCase):
    """`fit` 은 세이브를 **해시가 안 붙은 이름**으로 모은다 — 그러면 빌드를 갈아도 따라온다."""

    def setUp(self):
        # ⚠ 이 머신에서 mednafen 이 켜져 있든 말든 테스트 결과가 같아야 한다.
        self._real = ss_gameid._mednafen_running
        ss_gameid._mednafen_running = lambda: False

    def tearDown(self):
        ss_gameid._mednafen_running = self._real

    def _save(self, sav, stem, ext, nbytes):
        with open(os.path.join(sav, f"{stem}.{ext}"), "wb") as f:
            f.write(b"\x01" * nbytes)

    def test_copies_to_the_plain_name_and_keeps_the_old(self):
        """⚠ 옛 이름을 **지우지 않는다** — 다른 빌드로 되돌아갔을 때 필요하다."""
        with tempfile.TemporaryDirectory() as d:
            img = os.path.join(d, "Game.cue")
            _bin(os.path.join(d, "Game.bin"), sectors=520)
            _cue(img, "Game.bin", DATA_ONLY)
            sav = os.path.join(d, "sav")
            os.makedirs(sav)
            for e in ("bkr", "bcr", "smpc"):
                self._save(sav, "Game.deadbeef", e, 8)

            base, n, old = fit(sav, img)
            self.assertEqual((base, old, n), ("Game", "deadbeef", 3))
            got = {os.path.basename(x) for x in glob.glob(os.path.join(sav, "*.bkr"))}
            self.assertEqual(got, {"Game.deadbeef.bkr", "Game.bkr"}, "옛 이름이 남아야 한다")
            # 두 번 돌려도 아무 일 없다
            self.assertEqual(fit(sav, img)[1], 0)

    def test_picks_the_fullest_not_the_newest(self):
        """🔴 제일 새것이 **빈 것**일 수 있다(2026-08-29 실측: 새것 144B · 진행분 880B).

        세이브를 못 읽은 회차에도 mednafen 은 종료할 때 백업 RAM 을 쓰기 때문이다.
        """
        with tempfile.TemporaryDirectory() as d:
            img = os.path.join(d, "Game.cue")
            _bin(os.path.join(d, "Game.bin"), sectors=520)
            _cue(img, "Game.bin", DATA_ONLY)
            sav = os.path.join(d, "sav")
            os.makedirs(sav)
            self._save(sav, "Game.old1234", "bkr", 880)  # 진행분
            self._save(sav, "Game.new5678", "bkr", 8)  # 방금 만들어진 빈 것
            os.utime(os.path.join(sav, "Game.old1234.bkr"), (1_700_000_000, 1_700_000_000))

            _, n, old = fit(sav, img)
            self.assertEqual(old, "old1234", "든 것이 많은 쪽을 골라야 한다")
            self.assertEqual(n, 1)


if __name__ == "__main__":
    unittest.main()
