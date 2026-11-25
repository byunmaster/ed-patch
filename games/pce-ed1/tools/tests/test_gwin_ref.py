"""글리프 조립 참조 구현 == `gwin.make_window` — 편집기 자료의 음성 쪽 전량(원판 대조 근거 없는 거부 항목 제외)."""

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common
import font
import glyphdyn
import gwin
import gwin_ref
import translate
import typeset

import voice_editor_data

DATA = voice_editor_data.main_tree() / ".local" / "work" / "inbox" / "pce-ed1" / "voice-editor" / "data.json"


def _ctx():
    chars = glyphdyn.forced_chars() | (translate.all_glyph_chars() & set(font._order_canon()))
    table, bank = font.build_table(chars)
    return table, bytearray(bank)


class TestRef(unittest.TestCase):
    def test_all_voice_pages(self):
        if not DATA.exists():
            self.skipTest("편집기 자료(data.json) 없음")
        table, bank0 = _ctx()
        rows = json.loads(DATA.read_text("utf-8"))
        n = bad = 0
        for r in rows:
            if re.search("은/는|이/가|을/를|과/와|으로/로|아/야|이랑/랑", r["kr"]):
                continue  # 동적 조사 — 자막이 안 그린다
            sid = r["scene"]
            btab, dyn = glyphdyn.block_table(table, sid)
            bank = bytearray(bank0)
            for k, ch in enumerate(dyn):  # 블록이 열릴 때 동적 칸에 복사되는 비트맵
                at = font.glyph_at(font.DYN0 + k)
                bank[at : at + font.PACKED_BYTES] = font.pack(font.glyph(ch))
            spk0 = r["speaker_name"] or None
            for pi, pg in enumerate(typeset.pages(font.expand_packed(r["kr"]), speaker=spk0 is not None, four=True)):
                spk = spk0 if pi == 0 else None  # 이름은 첫 쪽만
                text = "\n".join(pg)
                try:
                    tiles, _bat = gwin.make_window(spk, text)
                    lines = ([spk] if spk else []) + gwin.page_lines(spk, text)  # make_window 와 같은 줄(갈린 글은 그대로 — 다시 짜지 않는다)
                    enc = [(font.encode(ln, btab, msg=True), 0) for ln in lines]
                except (ValueError, AssertionError):  # 씬 글리프 표에 없는 글자(카드 안내 화면 「&」 등) · 다시 조판하면 한 쪽이 아닌 것
                    continue
                got = gwin_ref.tiles_of(enc, bytes(bank), gwin_ref.adv_exceptions(btab))
                n += 1
                if got != tiles:
                    bad += 1
                    print("불일치", r["clip"], r["idx"], pi, repr(text)[:40])
        self.assertGreater(n, 100)
        self.assertEqual(bad, 0, f"{bad}/{n} 쪽 불일치")


    def test_message_bytes_pages(self):
        """실제 메시지 바이트(`translate.compose`)를 쪽·줄로 읽은 것 == 조판기 쪽·줄, 타일도 같다 — 음성 쪽이 든 메시지 전량."""
        if not DATA.exists():
            self.skipTest("편집기 자료(data.json) 없음")
        import glob

        import messages as M
        import translate

        table, bank0 = _ctx()
        rows = json.loads(DATA.read_text("utf-8"))
        seen = {(r["scene"], r["key"]) for r in rows if re.fullmatch("[0-9a-f]{16}", r["key"])}
        speakers = M.load_speakers()
        n = bad = 0
        for sid, key in sorted(seen):
            blk = Path(sorted(glob.glob(str(common.OUT_DIR / "text" / f"*_{sid:03d}.bin")))[0]).read_bytes()
            tr = M.load_translations(sid).get(key)
            m = next((x for x in M.parse(blk) if x.key == key), None)
            if tr is None or m is None or re.search("은/는|이/가|을/를|과/와|으로/로|아/야|이랑/랑", tr["t"]):
                continue
            btab, dyn = glyphdyn.block_table(table, sid)
            try:
                msg = translate.compose(m, tr, btab, speakers)
            except (ValueError, AssertionError):
                continue
            inv = {bytes(v): k for k, v in btab.items()}
            adv = gwin_ref.adv_exceptions(btab)
            bank = bytearray(bank0)
            for k, ch in enumerate(dyn):
                at = font.glyph_at(font.DYN0 + k)
                bank[at : at + font.PACKED_BYTES] = font.pack(font.glyph(ch))
            name, pages = gwin_ref.message_pages(msg + b"\x00", adv)
            want = typeset.pages(font.expand_packed(tr["t"].lstrip(" ")), speaker=m.speaker is not None or m.common is not None, four=True)
            n += 1
            try:
                self.assertEqual(len(pages), len(want))
                for pg, w in zip(pages, want, strict=True):
                    txt = ["".join(inv.get(ln[i : i + 2], "·") if ln[i : i + 2] != font.HALF_SPACE else " " for i in range(0, len(ln), 2)) for ln in pg]
                    self.assertEqual([x.strip(" ") for x in txt], [font.ligate(x).strip(" ") for x in w], f"scn{sid} {key[:6]}")
            except AssertionError as e:
                bad += 1
                print("불일치", str(e)[:200])
        self.assertGreater(n, 40)
        self.assertEqual(bad, 0, f"{bad}/{n} 메시지 불일치")


if __name__ == "__main__":
    unittest.main()
