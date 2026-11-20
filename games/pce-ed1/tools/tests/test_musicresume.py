"""음악 이어 재생(`musicresume.py`) — 자리·호출 계약. 소리 판정은 에뮬(CD 호출 로그)·마스터 귀."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cpu65
import musicresume as mr
import splitload
import winmask


class MusicResume(unittest.TestCase):
    def test_fits_in_bank73_tail_after_winmask(self):
        self.assertLessEqual(len(mr.code()), mr.CODE_LEN)
        self.assertGreaterEqual(
            mr.OFF, winmask.TAIL_OFF + winmask.TOTAL_LEN
        )  # winmask 와 안 겹친다
        self.assertLessEqual(mr.OFF + mr.CODE_LEN, 0x2000)

    def test_far_call_shape(self):
        for name in ("savepos", "replay"):
            b = mr.far_call(name)
            self.assertEqual(b[:3], b"\x20\xd8\x4f")  # JSR $4FD8
            self.assertEqual(b[3], mr.BANK - 0x68 - 1)
            addr = int.from_bytes(b[4:6], "little")
            self.assertTrue(mr.ORG <= addr < mr.ORG + mr.CODE_LEN)

    def test_load_hook_site_and_shape(self):
        # 원판 LOAD 성공 꼬리 `JSR $7D55 · JSR $4240` 6B 를 먼 호출 6B 로 갈아 끼운다(뒤따르는 CLA·CLC·RTS 는 그대로)
        self.assertEqual(len(mr.LOAD_SITE_ORIG), len(mr.far_call("loadhook")))
        self.assertEqual(mr.LOAD_SITE_ORIG[:3], b"\x20\x55\x7d")
        self.assertEqual(mr.LOAD_SITE_ORIG[3:], b"\x20\x40\x42")
        code = mr.code()
        off = mr.far_addr("loadhook") - mr.ORG
        self.assertEqual(code[off : off + 3], b"\x20\x18\xe0")  # JSR $E018(CD_PAUSE) 로 시작

    def test_buffer_is_ten_contiguous_bytes_and_passed_in_fa_fb(self):
        lab = mr._final().labels
        self.assertEqual(lab["buf7"] - lab["buf"], 7)
        self.assertEqual(lab["buf9"] - lab["buf"], 9)
        code = mr.code()
        buf = lab["buf"]
        # LDA #lo · STA $FA · LDA #hi · STA $FB (BIOS CD_SUBQ 는 10B 를 ($FA) 로 받는다)
        pat = bytes([0xA9, buf & 0xFF, 0x85, 0xFA, 0xA9, buf >> 8, 0x85, 0xFB])
        self.assertIn(pat, code)

    # ── 엔진 CD 곡 상태(`$76`) — 교체가 엔진에 안 보여야 한다(11-21 「겹침 · 계단마다 처음부터」) ──
    SONG = 0x0A
    START, END = (0x20, 0x58, 0x66), (0x23, 0x55, 0x12)  # 가짜 곡 범위(BCD 분·초·프레임)
    PLAY_CNT, ENG_CNT = 0x0300, 0x0301  # 스텁이 올리는 호출 수

    def _swap(self, status, pos, s76, cmd):
        """`savepos` → (컨테이너 로드가 `$76` 을 `FF` 로) → `replay` 를 돌려 (`$76`, CD_PLAY 횟수, 엔진 다시 걸기 횟수, 건 시작 MSF)."""
        m = bytearray(0x10000)
        code = mr.code()
        m[mr.ORG : mr.ORG + len(code)] = code
        lab = mr._final().labels
        m[mr.CD_SUBQ] = 0x60  # RTS — 버퍼는 아래에서 미리 채운다
        for at, cnt in ((mr.CD_PLAY, self.PLAY_CNT), (mr.ENG_SAME_SONG, self.ENG_CNT)):
            m[at : at + 4] = bytes([0xEE, cnt & 0xFF, cnt >> 8, 0x60])  # INC 횟수 칸 · RTS
        for k in range(3):
            m[mr.TBL_START[k] + self.SONG] = self.START[k]
            m[mr.TBL_END[k] + self.SONG] = self.END[k]
        m[mr.TBL_END[3] + self.SONG] = 0x41
        m[lab["buf"]] = status
        m[lab["buf7"] : lab["buf7"] + 3] = bytes(pos)
        m[0x4B], m[0x4C] = cmd
        m[mr.ENG_CD_STATE] = s76
        c = cpu65.CPU(m)
        c.run(lab["savepos"])
        m[mr.ENG_CD_STATE] = 0xFF  # 엔진 `$5716` — 컨테이너 CD_READ 직전
        c.x, c.y = 3, 5
        c.run(lab["replay"])
        self.assertEqual((c.x, c.y), (3, 5))
        return m[mr.ENG_CD_STATE], m[self.PLAY_CNT], m[self.ENG_CNT], tuple(m[0xF8:0xFB])

    def test_cd_state_restored_when_resumed(self):
        pos = (0x21, 0x10, 0x05)
        # 같은 곡이 흐르던 씬(계단) · PSG 밑에서 페이드된 채 흐르던 씬(마을) — 그 위치부터 다시 걸고 상태를 되돌린다
        for s76 in (self.SONG, self.SONG | 0x40):
            self.assertEqual(self._swap(0, pos, s76, (0x80, 0)), (s76, 1, 0, pos))

    def test_cd_state_restored_when_engine_restarts_song(self):
        # 곡 명령 직후(드라이브가 아직 안 돌아 위치가 없다) — 엔진 루틴으로 처음부터, 상태는 그 곡
        st, play, eng, _ = self._swap(3, (0, 0, 0), self.SONG, (self.SONG, 0))
        self.assertEqual((st, play, eng), (self.SONG, 0, 1))

    def test_cd_state_stays_dead_when_not_resumed(self):
        # CD 가 안 흐르고 있었고 되살리지도 않았다 — 엔진이 「흐르는 중」으로 알면 같은 곡 씬에서 PLAY 를 안 걸어 무음이 된다
        st, play, eng, _ = self._swap(3, (0, 0, 0), self.SONG | 0x40, (0x11, 1))
        self.assertEqual((st, play, eng), (0xFF, 0, 0))

    def test_pending_play_survives_swap(self):
        # SEARCH 만 걸린 채(재생 예약 비트7) 교체 — 예약을 되돌려야 엔진이 곧 PLAY 를 건다
        st, play, eng, _ = self._swap(2, (0, 0, 0), self.SONG | 0x80, (self.SONG, 1))
        self.assertEqual((st, play, eng), (self.SONG | 0x80, 0, 0))

    def test_splitload_still_fits(self):
        self.assertLessEqual(splitload.layout()["len"], splitload.ROOM)


if __name__ == "__main__":
    unittest.main()
