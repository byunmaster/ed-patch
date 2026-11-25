"""계수 경로와 출하 경로가 같은가 — 조판기 단독 결과(`typeset.pages`)가 롬(`translate.compose` 바이트를 되읽은 줄)·편집기(`voice_editor_data.pages_of`)와 전 문안에서 같아야 한다.

11-05 사고: 조판 모드를 문자열(`"nl"`)로 주는 식이 `A and not B` 꼴에서 `True` 로 뭉개져 「첫 줄 13칸」 규칙이 조판기 단독 계수에서는 맞고 롬에는 안 닿았다 —
계수는 맞고 롬은 틀린 상태를 이 시험이 잡는다. 예외(앞 줄 폭을 따로 주는 경로)는 아래 목록에 이유와 함께만 둔다.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_baked_typeset as C
import common
import font
import glyphdyn
import messages as M
import translate as T
import typeset
import voice_editor_data as VED


def _lines_of_compose(by: bytes, inv: dict) -> list[str]:
    _head, pages = C.decode(by, inv)
    return [p[0] for p in pages if p[0].strip()]  # 끝 쪽 넘김 뒤 빈 쪽은 뺀다


class ShipPath(unittest.TestCase):
    def test_compose_equals_typeset_and_editor(self):
        if not list(common.OUT_DIR.glob("text/*.bin")):
            self.skipTest("파생 블록(work/derived)이 없다")
        chars = glyphdyn.forced_chars() | (C.T.all_glyph_chars() & set(font._order_canon()))
        table, _ = font.build_table(chars)
        inv = C.inverse(table)
        speakers = M.load_speakers()
        bad_compose, bad_editor, n, sens = [], [], 0, 0
        for p in sorted(common.OUT_DIR.glob("text/*.bin")):
            tail = p.stem.split("_")[-1]
            if not tail.isdigit():
                continue
            sid = int(tail)
            tr = M.load_translations(sid)
            blk = p.read_bytes()
            ms = M.parse(blk)
            typeset.set_scene(sid)
            leads = T.continuation_leads(blk, ms, tr, speakers)
            for m in ms:
                v = tr.get(m.key)
                if not v or v.get("raw") or not v.get("t") or m.key in leads:
                    continue  # 앞 줄 폭을 따로 주는 경로(이어쓰기 lead — `continuation_leads`)는 조판기 단독 호출과 입력이 다르다
                if T._JOSA_LEAD.match(v["t"].lstrip(" ")) or m.key in T.INLINE_LEAD or m.key in T.ITEM_LEAD_KEYS:
                    continue  # 이름 변수 뒤 조사 조각 — 앞 이름 폭(lead)을 따로 준다
                if m.key in T.HARD_LINES:
                    continue  # 줄을 손으로 정한 메시지(해적섬 게임 — `HARD_LINES`) — 조판기 줄 계획이 아니라 지정한 줄이 롬 줄이다
                if (sid, m.key) in T.PAGE_SPEAKER:
                    continue  # 쪽 머리에 인라인 이름 줄을 더 내는 메시지(씬 34 OFF 끝 쪽) — 롬 줄이 조판기 줄보다 한 줄 많은 게 의도다
                src = font.expand_packed(v["t"].lstrip(" "))
                kind = M.speaker_kind(m, sid)
                want = typeset.pages(src, speaker=kind, four=True, keep_windows=typeset.keep_windows(sid))
                want = [pg for pg in want if pg]  # 끝 `\f`(쪽 넘김 옵코드로 끝나는 메시지)의 빈 쪽은 롬이 안 낸다
                if any(isinstance(pg, typeset.Card) for pg in want):
                    continue
                n += 1
                if kind in ("nl", "nl=") and typeset.pages(src, speaker=True, four=True) != want:
                    sens += 1  # 양성 대조 — 모드가 True 로 뭉개지면 달라질 문안
                try:
                    got = _lines_of_compose(T.compose(m, v, table, speakers), inv)
                except ValueError:
                    continue  # 동적 글리프 표 밖 글자 — 이 시험은 상주 표만 쓴다
                exp = [font.ligate("\n".join(pg)) for pg in want]  # 롬은 「!!」 같은 합자를 한 글자로 낸다
                # compose 바이트를 되읽으면 화자 머리 개행(`01`)이 앞에 붙는다 — 줄 내용만 비교
                norm = lambda s: [x.strip() for x in s.split("\n") if x.strip()]  # noqa: E731
                if [norm(g) for g in got] != [norm(e) for e in exp]:
                    bad_compose.append((sid, m.key[:8], got[:1], exp[:1]))
                ed, _w = VED.pages_of(v["t"], m.jp, speaker=False if m.key in T.INLINE_LEAD else kind, sid=sid)
                ed = [x for x in ed if x.strip()]
                if [norm(font.ligate(x)) for x in ed] != [norm(e) for e in exp]:
                    bad_editor.append((sid, m.key[:8], ed[:1], exp[:1]))
        self.assertGreater(n, 1000)
        self.assertGreater(sens, 50, "양성 대조: 조판 모드가 줄 모양을 바꾸는 문안이 있어야 이 시험이 모드 누락을 잡는다")
        self.assertEqual(bad_compose[:5], [], f"조판기 ≠ 롬(compose) {len(bad_compose)}건")
        self.assertEqual(bad_editor[:5], [], f"조판기 ≠ 편집기 {len(bad_editor)}건")


class ShipPathLeadExceptions(unittest.TestCase):
    """앞 줄 폭(lead)을 따로 주는 예외 경로(이름 변수 뒤 조사 조각 · 아이템 이름 뒤 조사 조각 · 이름 변수 이어쓰기 · 앞 메시지 줄 끝에 이어 붙는 쪽)는 조판기 단독 호출과 입력이 달라
    위 시험이 못 본다 — 여기서는 시험이 lead 폭을 직접 계산하고 compose 바이트를 되읽은 줄이 ① 글을 안 잃고 ② 런타임 줄넘김 모델과 같고(`_lead_runtime_ok`) ③ 칸 13 에 부호가 안 매달리는지 본다."""

    def test_lead_paths_ship_lines_are_runtime_safe(self):
        import re

        if not list(common.OUT_DIR.glob("text/*.bin")):
            self.skipTest("파생 블록(work/derived)이 없다")
        chars = glyphdyn.forced_chars() | (C.T.all_glyph_chars() & set(font._order_canon()))
        table, _ = font.build_table(chars)
        inv = C.inverse(table)
        speakers = M.load_speakers()
        josa = re.compile(r"(은/는|을/를|이/가|와/과|으로/로)")
        import typeset_check as TC

        n, bad = 0, []
        for p in sorted(common.OUT_DIR.glob("text/*.bin")):
            tail = p.stem.split("_")[-1]
            if not tail.isdigit():
                continue
            sid = int(tail)
            tr = M.load_translations(sid)
            blk = p.read_bytes()
            ms = M.parse(blk)
            typeset.set_scene(sid)
            leads = T.continuation_leads(blk, ms, tr, speakers)
            for m in ms:
                v = tr.get(m.key)
                if not v or v.get("raw") or not v.get("t"):
                    continue
                txt = v["t"].lstrip(" ")
                if m.key in T.HARD_LINES:
                    continue  # 줄을 손으로 정한 메시지(해적섬 게임) — 지정 줄이 곧 롬 줄이다(줄 폭은 아래 시험이 못 본다 → 손으로 px 확인)
                if m.key in T.FREE_FLOW_KEYS:
                    continue  # 개행을 안 내고 엔진이 이름 폭대로 접게 둔 문구(상자 「이/가 들어 있었습니다」) — 줄 계획이 곧 런타임이 아니다(시험 롬 실화면 11-17)
                if m.key in leads:
                    lead = leads[m.key]
                elif m.key in T.ITEM_LEAD_KEYS and T._JOSA_LEAD.match(txt):
                    lead = T.ITEM_LEAD_PX
                elif T._JOSA_LEAD.match(txt):
                    lead = typeset.px(T.JOIN_NAME if m.key in T.JOIN_KEYS else T.NAME_LONGEST)  # 동료 합류 문구는 두 글자 이름(류난·로우·게일)
                else:
                    continue
                n += 1
                try:
                    pages = C.decode(T.compose(m, v, table, speakers, lead_px=leads.get(m.key, 0)), inv)[1]
                except ValueError:
                    continue
                lines_pages = [[x.strip() for x in pg[0].split("\n")] for pg in pages if pg[0].strip()]  # 첫 줄이 빈 쪽(앞 줄 끝에 이어 붙고 개행으로 시작)은 빈 첫 줄을 둔다
                lines_pages = [ls[:1] + [x for x in ls[1:] if x] if ls[0] == "" else [x for x in ls if x] for ls in lines_pages]
                got_ink = typeset.ink("".join("".join(ls) for ls in lines_pages))
                want_ink = typeset.ink(josa.sub("", "".join(font.expand_packed(txt).split("\f"))))
                got_ink = typeset.ink(josa.sub("", got_ink))
                if len(got_ink) < len(want_ink) - 2:  # 글 소실(조사 토큰이 디코드에서 한 글자로 나오는 차이 정도만 허용)
                    bad.append((sid, m.key[:8], "글 소실", got_ink[:12], want_ink[:12]))
                    continue
                for i, ls in enumerate(lines_pages):
                    lead_i = lead if i == 0 else 0
                    if not typeset._lead_runtime_ok(ls, lead_i):
                        bad.append((sid, m.key[:8], "런타임 줄 불일치", i, ls[:2]))
                        break
                    px0 = lead_i
                    hung = False
                    for k, ln in enumerate(ls):
                        px = px0 if k == 0 else 0
                        for ch in ln:
                            if ch in TC.HANG and px // 12 >= TC.WIDTH:
                                hung = True
                            px += typeset.adv(ch)
                    if hung:
                        bad.append((sid, m.key[:8], "칸 13 부호 매달림", i, ls[:2]))
                        break
        self.assertGreater(n, 70)
        self.assertEqual(bad[:6], [], f"lead 예외 경로 불일치 {len(bad)}건 / {n}문안")


if __name__ == "__main__":
    unittest.main()
