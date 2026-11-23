"""비모달 자막 안 B(런타임 글리프 조립)의 6502 렌더러를 `cpu65` 로 **실제로 돌려** `gwin.make_window` 와 바이트로 대조한다 — VRAM 글자 타일 · 창 그림(BAT 단어).
음성 쪽 전량(편집기 자료, `test_gwin_ref` 와 같은 분모). 원본 없이 돈다(자료가 없으면 건너뜀).
배치는 실제와 같다: 블록 쪽(통로·작업 7 스텁·버퍼)은 씬 창 $A000+, 컨테이너 쪽(코드·표)은 $8000(4번째 뱅크를 MPR4 에 건 꼴)."""

import glob
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cpu65
import font
import glyphdyn
import gwin
import gwin_rt as R
import translate
import typeset
import voice_editor_data

DATA = voice_editor_data.main_tree() / ".local" / "work" / "inbox" / "pce-ed1" / "voice-editor" / "data.json"
ORG = R.BASE  # 블록 쪽(시험에선 블록 데이터가 없어 꼬리가 곧 머리)
SIM_SID = 99  # 흉내용 씬 번호(디렉터리 항목)
SIM_CHUNK = 12  # 흉내 한 번에 싣는 쪽 수(코드 영역 8KB 안)
JOSA = "은/는|이/가|을/를|과/와|으로/로|아/야|이랑/랑"


def sim_setup(specs: dict[int, dict], sid: int, btab: dict[str, bytes], bank: bytes):
    """공용 코드 영역(씬 여럿) + 고정 영역을 흉내 메모리에 깔고 `slot` = sid 로 `gwsel` 까지 돌린다 — 통로 `gw`(상주부·TII·MPR)만 빼고 `gwr` 와 같은 상태. (mem, 라벨, cpu)."""
    R.SCENE_PARTS.clear()
    for k, sp in specs.items():
        R.register_scene(k, sp, b"", btab)  # 블록 없음 — 줄 코드는 전부 코드 영역 뒤에 복사된다
    code, lab = R.container_tail(sorted(specs))
    mem = bytearray(0x10000)
    mem[R.CODE_ORG : R.CODE_ORG + len(code)] = code
    fix = R.fixed_image(lab, code)
    mem[R.FIXED_ORG : R.FIXED_ORG + len(fix)] = fix
    cpu = cpu65.CPU(mem, {font.GLYPH_BANK0 + k: bank[k * 0x2000 : (k + 1) * 0x2000] for k in range(font.GLYPH_NBANKS)})
    mem[lab["slot"]] = sid
    cpu.run(lab["gwsel"])
    assert mem[lab["npg"]] == len(specs[sid]["pages"]), (mem[lab["npg"]], sid)
    assert mem[lab["dbase"]] | mem[lab["dbase"] + 1] << 8 == lab[f"desc{sid}"]
    return mem, lab, cpu


def render_pages(spec: dict, btab: dict[str, bytes], bank: bytes) -> list[tuple[list[int], bytes, int]]:
    """명세를 안 B 로 짜서 쪽마다 (VRAM 글자 타일 단어(그 쪽의 타일 칸), 창 그림 바이트, 준비 틱 수). 블록 없이 — 줄 코드는 전부 코드 영역 뒤에 복사된다."""
    if len(spec["pages"]) > SIM_CHUNK:  # 블록 없는 흉내는 줄 코드까지 코드 영역에 복사한다 — 쪽이 많으면 8KB 를 넘으니 묶음으로(실제 빌드는 블록 안 코드를 가리킨다)
        out = []
        for i in range(0, len(spec["pages"]), SIM_CHUNK):
            out += render_pages({"pages": spec["pages"][i : i + SIM_CHUNK]}, btab, bank)
        return out
    plines = [R.rt_lines(pg.get("speaker"), pg["text"], btab) for pg in spec["pages"]]
    mem, lab, cpu = sim_setup({SIM_SID: spec}, SIM_SID, btab, bank)
    out = []
    for p in range(len(spec["pages"])):
        mem[lab["qg"]] = p
        cpu.run(lab["pstart"])
        ticks = 0
        while mem[lab["rs"]] != 0:
            cpu.run(lab["rstep"])
            ticks += 1
            assert ticks < 2000
        assert mem[lab["ready0"] + (p & 1)] == 1 and mem[lab["qg"]] == p + 1
        cpu.run(lab["mkblank"])
        cpu.a = p & 1
        cpu.run(lab["applyrec"])
        nt = sum(n for _, n in plines[p]) * 2
        t0 = R.BANK_TILE0[p & 1] * 16
        vr = cpu.vram[t0 : t0 + nt * 16]
        out.append((vr, bytes(mem[lab["win"] : lab["win"] + R.ROW_BYTES * gwin.H]), ticks))
    return out


def want(spk, text):
    """`make_window` 의 타일(색 15)·BAT(타일 0x600 부터) → 안 B 기대값: 화자 줄 타일은 색 13(평면1 = 0)."""
    tiles, bat = gwin.make_window(spk, text)
    vr = [w for i in range(0, len(tiles), 8) for w in _expand_words(tiles[i : i + 8])]
    if spk:
        _rows, ncol0 = gwin.strip(spk)
        for t in range(ncol0 * 2):  # 화자 줄 타일: 앞 16단어 중 평면1(상위 바이트) = 0
            for y in range(8):
                vr[t * 16 + y] &= 0x00FF
    win = b"".join(bat[(r, c)].to_bytes(2, "little") for r in range(gwin.ROW0, gwin.ROW0 + gwin.H) for c in range(gwin.COL0, gwin.COL0 + gwin.W))
    return vr, win


def _expand_words(t: bytes) -> list[int]:
    e = gwin.expand(t)
    return [e[i] | e[i + 1] << 8 for i in range(0, 32, 2)]


def _retile(win: bytes, page: int) -> bytes:
    """`make_window` 의 BAT(타일 0x600 부터)를 쪽의 타일 칸 번호로 옮긴다 — 짝수 쪽 0x556 · 홀수 쪽 0x5C8 부터."""
    out = bytearray(win)
    for i in range(0, len(out), 2):
        w = out[i] | out[i + 1] << 8
        if (w & 0x7FF) >= gwin.TILE0:
            w = (w & 0xF800) | ((w & 0x7FF) - gwin.TILE0 + R.BANK_TILE0[page % 2])
            out[i], out[i + 1] = w & 0xFF, w >> 8
    return bytes(out)


def _ctx():
    chars = glyphdyn.forced_chars() | (translate.all_glyph_chars() & set(font._order_canon()))
    table, bank = font.build_table(chars)
    return table, bytes(bank)


class TestRtB(unittest.TestCase):
    def test_voice_pages(self):
        if not DATA.exists():
            self.skipTest("편집기 자료(data.json) 없음")
        table, bank0 = _ctx()
        by_scene: dict[int, list] = {}
        for r in json.loads(DATA.read_text("utf-8")):
            if re.search(JOSA, r["kr"]):
                continue
            spk0 = r["speaker_name"] or None
            for pi, pg in enumerate(typeset.pages(font.expand_packed(r["kr"]), speaker=spk0 is not None, four=True)):
                by_scene.setdefault(r["scene"], []).append((spk0 if pi == 0 else None, "\n".join(pg)))
        n = bad = 0
        maxt = 0
        over: list = []
        for sid, pgs in sorted(by_scene.items()):
            btab, dyn = glyphdyn.block_table(table, sid)
            bank = bytearray(bank0)
            for k, ch in enumerate(dyn):
                at = font.glyph_at(font.DYN0 + k)
                bank[at : at + font.PACKED_BYTES] = font.pack(font.glyph(ch))
            ok = []
            for spk, text in pgs:
                try:
                    gwin.make_window(spk, text)
                    lines = R.rt_lines(spk, text, btab)
                except (ValueError, AssertionError, KeyError):
                    continue
                if sum(n for _, n in lines) * 2 > R.BANK_TILES:  # 4줄 꽉 찬 쪽(씬 196, 134타일) — 타일 칸 한계로 못 붙는 쪽(ⓑ 글자 기둥 재사용 전까지 빌드 게이트가 막는다)
                    over.append((sid, text[:12]))
                    continue
                ok.append({"speaker": spk, "text": text, "start": len(ok), "end": len(ok) + 1})
            if not ok:
                continue
            got = render_pages({"pages": ok}, btab, bytes(bank))
            for p, (pg, (vr, win, ticks)) in enumerate(zip(ok, got, strict=True)):
                n += 1
                maxt = max(maxt, ticks)
                wv, ww = want(pg["speaker"], pg["text"])
                ww = _retile(ww, p)
                if vr != wv or win != ww:
                    bad += 1
                    print("불일치", sid, p, repr(pg["text"])[:40], "타일" if vr != wv else "", "창" if win != ww else "")
        print(f"안 B: {n}쪽 · 쪽당 최대 {maxt}틱 · 타일 칸 초과 {len(over)}쪽 {over[:3]}")
        self.assertLessEqual(len(over), 2, "타일 칸을 넘는 쪽이 늘었다")
        self.assertGreater(n, 100)
        self.assertEqual(bad, 0, f"{bad}/{n} 쪽 불일치")

    def test_tick_machine(self):
        """표시기·준비기를 프레임 단위로 돌린다 — 쪽 넷(0·1 이어짐 · 2 는 간격 뒤 · 3 마지막): 쪽마다 시작 시각 근처에 보이고(ph=4), 간격에서 닫히고(ph=5 → 0),
        끝에 ph=6. 쪽 전환은 빈 창 없이(이어지는 쪽은 ph 1·3 을 안 거친다 · 처음 열기만 1 미리 읽기 → 3 쓰기, 2 는 안 쓴다) · 타일 칸은 홀짝으로 갈린다 ·
        보이는 쪽의 창 그림이 그 쪽 것이다 · 열기·바꾸기·닫기 틱에서 창 행의 VRAM 쓰기는 한 틱 안에 다 끝난다(반쪽 창 프레임 없음)."""
        if not DATA.exists():
            self.skipTest("편집기 자료(data.json) 없음")
        table, bank0 = _ctx()
        btab, dyn = glyphdyn.block_table(table, 6)
        bank = bytearray(bank0)
        for k, ch in enumerate(dyn):
            at = font.glyph_at(font.DYN0 + k)
            bank[at : at + font.PACKED_BYTES] = font.pack(font.glyph(ch))
        texts = [("라이아스", "수많은 몬스터들이\n이 마을로 몰려왔습니다."), (None, "어서 이 갑옷을\n몸에 걸치시옵소서."), ("세리오스", "할아범들은\n어찌하려고?"), (None, "할아범!\n죽지 마라!!")]
        starts_ends = [(1.0, 3.0), (3.0, 5.0), (8.0, 10.0), (10.0, 12.0)]
        spec = {"pages": [{"speaker": s, "text": t, "start": a, "end": b} for (s, t), (a, b) in zip(texts, starts_ends, strict=True)]}
        other = {"pages": [{"speaker": "라이아스", "text": "다른 씬 쪽.", "start": 0.0, "end": 1.0}]}  # 같은 컨테이너의 둘째 씬 — 디렉터리가 slot 으로 가른다
        mem, lab, cpu = sim_setup({SIM_SID: spec, 98: other}, SIM_SID, btab, bank)
        mem[lab["slot"]] = 98  # 둘째 씬을 골라도 쪽 수·서술표가 그 씬 것
        cpu.run(lab["gwsel"])
        self.assertEqual((mem[lab["npg"]], mem[lab["dbase"]] | mem[lab["dbase"] + 1] << 8), (1, lab["desc98"]))
        mem[lab["slot"]] = SIM_SID
        cpu.run(lab["gwsel"])
        # gwr 의 초기화와 같게(상주부·트램펄린 자리는 빼고): 프레임 기준 0, 변수 0, 첫 쪽 서술
        for v in ("ph", "pg", "row", "qg", "rs", "ready0", "ready1", "last", "b0", "b1", "reopen", "wopen"):
            mem[lab[v]] = 0
        mem[R.SCROLL_Y] = R.SCROLL_Y0  # 엔진 BYR 그림자 — 창 행 11
        mem[0x43B4] = mem[0x43FE] = 0x60  # 엔진 분할 더하기/빼기 — 흉내에선 RTS
        cpu.run(lab["getdesc"])
        _step, _n = cpu.step, [0]

        def _tickstep():  # pre0 가 VBlank(FRAMECNT 오름)를 기다린다(11-04 래스터 분할 지연 방지) — 흉내에선 명령 400개마다 한 프레임
            _step()
            _n[0] += 1
            if _n[0] % 400 == 0:
                mem[R.FRAMECNT] = (mem[R.FRAMECNT] + 1) & 0xFF

        cpu.step = _tickstep
        npre = cpu.run(lab["pre0"])  # 첫 쪽 동기 미리 그리기 — gwr 가 틱을 켜기 전에 메인 스레드에서 쪽 0 을 다 그린다(첫 쪽 지연 11-01)
        self.assertEqual((mem[lab["ready0"]], mem[lab["qg"]], mem[lab["rs"]]), (1, 1, 0), "pre0 뒤 쪽 0 준비·다음 쪽 1")
        cpu.step = _step
        self.assertLessEqual(npre, 256 * 1855 * R.PRE_N, f"pre0 명령 수 {npre}")  # 상한 256회 × 틱 예산
        print("pre0 명령 수", npre, "≈ 프레임", round(npre * 4 / (7159090 / R.FPS), 2))  # 명령당 ≈4사이클로 어림
        seen = {}  # (ph, pg) 첫 프레임
        shown = {}  # pg → 보이기 시작한 프레임
        phases = []
        maxins = (0, 0)
        for f in range(1, int(13 * R.FPS)):
            mem[R.FRAMECNT], mem[R.FRAMECNT + 1] = f & 0xFF, f >> 8
            if f == 100:  # 쪽 0 보이는 중 스크롤이 8px 내려감 → **같은 틱**에 행 12 로 옮긴다(옛 행 11 되돌림 · 밑그림 고리)
                mem[R.SCROLL_Y] = R.SCROLL_Y0 + 8
                cpu.vram[(gwin.ROW0 + gwin.H) * 64 + gwin.COL0 + 3] = 0x1234  # 새로 덮일 바닥 행의 밑그림 — 되돌릴 때 다시 나와야 한다
            if f == 130:  # 도로 8px 올라감 → 행 11 로(위로 이동 경로)
                mem[R.SCROLL_Y] = R.SCROLL_Y0
            n = cpu.run(lab["tickr"])
            maxins = max(maxins, (n, f))
            ph, pg = mem[lab["ph"]], mem[lab["pg"]]
            rb = mem[lab["rowb"]]  # 틱 사이 화면: 창 행 220단어가 통째로 우리 것(팔레트 8)이거나 하나도 아니거나 — 반쪽 창 프레임 없음
            ours = [(cpu.vram[(rb + r) * 64 + gwin.COL0 + k] & 0xF000) == gwin.PAL for r in range(gwin.H) for k in range(gwin.W)]
            self.assertIn(sum(ours), (0, len(ours)), (f, ph, pg, sum(ours)))
            if f == 99:
                self.assertEqual(mem[lab["rowb"]], gwin.ROW0)
                self.assertEqual(cpu.vram[gwin.ROW0 * 64 + gwin.COL0], gwin.PAL | gwin.FRAME["tl"])
            if f == 100:  # 한 틱 이동 — 같은 틱에 창이 행 12 에, 옛 행 11 은 밑그림(0)으로, ph 는 4 그대로
                self.assertEqual((mem[lab["rowb"]], ph, mem[lab["ubase"]]), (gwin.ROW0 + 1, 4, 1))
                self.assertEqual(cpu.vram[(gwin.ROW0 + 1) * 64 + gwin.COL0], gwin.PAL | gwin.FRAME["tl"])
                self.assertEqual(cpu.vram[gwin.ROW0 * 64 + gwin.COL0], 0)
                self.assertLessEqual(n, 1400, f"이동 틱 명령 수 {n}")
            if f == 130:  # 되올림 — 행 11 로, 비는 바닥 행(21)은 읽어 둔 밑그림 0x1234 로
                self.assertEqual((mem[lab["rowb"]], ph, mem[lab["ubase"]]), (gwin.ROW0, 4, 0))
                self.assertEqual(cpu.vram[gwin.ROW0 * 64 + gwin.COL0], gwin.PAL | gwin.FRAME["tl"])
                self.assertEqual(cpu.vram[(gwin.ROW0 + gwin.H) * 64 + gwin.COL0 + 3], 0x1234)
            if (ph, pg) not in seen:
                seen[(ph, pg)] = f
                phases.append((f, ph, pg))
            if ph == 4 and pg not in shown:
                shown[pg] = f
                want_win = _retile(want(texts[pg][0], texts[pg][1])[1], pg)
                self.assertEqual(bytes(mem[lab["win"] : lab["win"] + R.ROW_BYTES * gwin.H]), want_win, f"쪽 {pg} 창 그림")
        self.assertEqual(mem[lab["ph"]], 6, phases)
        print("틱당 최대 명령 수", maxins)
        self.assertNotIn(2, [p for _, p, _ in phases])
        self.assertEqual(sorted(pg for _, p, pg in phases if p == 1), [0, 2], phases)  # 미리 읽기는 처음 여는 쪽(0 · 간격 뒤 2)만 — 이어지는 1·3 은 안 거친다
        self.assertEqual(sorted(pg for _, p, pg in phases if p == 3), [0, 2], phases)
        for pg, (a, _b) in enumerate(starts_ends):
            late = shown[pg] - R.frames(a)
            self.assertTrue(0 <= late <= 8, (pg, late, phases))  # 쪽 0 도 8 안 — 종전 60(틱으로 그릴 때)은 pre0 로 없어졌다
        self.assertNotIn((5, 0), seen, phases)  # 8px 스크롤은 닫지 않고 한 틱에 옮긴다
        self.assertIn((5, 2), seen, phases)  # 쪽 1 끝에서 닫았다(간격)
        self.assertIn((0, 2), seen, phases)  # 닫은 뒤 쪽 2 를 기다렸다
        self.assertNotIn((5, 1), seen, phases)  # 쪽 0→1 은 바로 이었다
        print("틱 기계:", phases)

    def test_pos_switch(self):
        """창 위치는 쪽마다다(11-23, 마스터 「줄별 위/아래」) — 쪽 넷: 0 아래 · 1 위(0 에 바로 이어짐) · 2 위(이어짐) · 3 아래(간격 뒤).
        · 쪽 서술 바이트 4·5 가 그 쪽의 창 첫 행·분할 줄 · 위치가 바뀌는 이음(0→1)은 이어지는 쪽이어도 **닫고 다시 연다**(같은 위치 1→2 는 종전대로 바로 잇는다)
        · 창 행(rowb)이 쪽 위치를 따르고 옛 자리는 밑그림으로 돌아간다 · 래스터 핸들러: 아래 = rc1 하나(줄 112), 위 = rc1(32) + rc2(112) — 닫을 때 건 만큼만 뺀다
        · 창 사각형 표(winmask)의 대사 슬롯이 그 위치 사각형이다."""
        import winmask

        table, bank0 = _ctx()
        btab, dyn = glyphdyn.block_table(table, 6)
        bank = bytearray(bank0)
        for k, ch in enumerate(dyn):
            at = font.glyph_at(font.DYN0 + k)
            bank[at : at + font.PACKED_BYTES] = font.pack(font.glyph(ch))
        texts = [("라이아스", "수많은 몬스터들이\n이 마을로 몰려왔습니다."), (None, "어서 이 갑옷을\n몸에 걸치시옵소서."), ("세리오스", "할아범들은\n어찌하려고?"), (None, "할아범!\n죽지 마라!!")]
        starts_ends = [(1.0, 3.0), (3.0, 5.0), (5.0, 7.0), (10.0, 12.0)]
        tops = [False, True, True, False]
        spec = {"pages": [{"speaker": s, "text": t, "start": a, "end": b, "top": tp} for (s, t), (a, b), tp in zip(texts, starts_ends, tops, strict=True)]}
        mem, lab, cpu = sim_setup({SIM_SID: spec}, SIM_SID, btab, bank)
        d0 = lab[f"desc{SIM_SID}"]
        self.assertEqual([tuple(mem[d0 + R.DESC * k + 4 : d0 + R.DESC * k + 6]) for k in range(4)], [(11, 112), (1, 32), (1, 32), (11, 112)])
        for v in ("ph", "pg", "row", "qg", "rs", "ready0", "ready1", "last", "b0", "b1", "reopen", "wopen"):
            mem[lab[v]] = 0
        mem[R.SCROLL_Y] = R.SCROLL_Y0
        LOG, CNT = 0x0400, 0x04F0  # 엔진 분할 더하기/빼기 흉내 — 더하기: 줄(A)을 적고 X = 항목 번호 · 빼기: 항목(X)을 적는다
        mem[0x43B4 : 0x43B4 + 10] = bytes([0xAE, CNT & 0xFF, CNT >> 8, 0x9D, LOG & 0xFF, LOG >> 8, 0xEE, CNT & 0xFF, CNT >> 8, 0x60])
        mem[0x43FE : 0x43FE + 11] = bytes([0x8A, 0xAE, (CNT + 1) & 0xFF, CNT >> 8, 0x9D, (LOG + 0x40) & 0xFF, LOG >> 8, 0xEE, (CNT + 1) & 0xFF, CNT >> 8, 0x60])
        ysel = []  # 창 사각형 복사 고리(`wmopen`)에 들어설 때의 원본 색인 Y — 아래 = SLOT_B-1(표 앞 반), 위 = 2·SLOT_B-1(뒤 반). 흉내 메모리는 글리프 뱅크가 같은 창을 덮어 바이트로는 못 본다
        cpu.run(lab["getdesc"])
        _step, _n = cpu.step, [0]

        def _tickstep():
            _step()
            _n[0] += 1
            if _n[0] % 400 == 0:
                mem[R.FRAMECNT] = (mem[R.FRAMECNT] + 1) & 0xFF

        cpu.step = _tickstep
        cpu.run(lab["pre0"])

        def _watch():
            if cpu.pc == lab["wmopen"] and cpu.x == winmask.SLOT_B - 1:
                ysel.append(cpu.y)
            _step()

        cpu.step = _watch
        seen, shown, phases = {}, {}, []
        adds = lambda: list(mem[LOG : LOG + mem[CNT]])
        rems = lambda: list(mem[LOG + 0x40 : LOG + 0x40 + mem[CNT + 1]])
        tl = lambda row: cpu.vram[row * 64 + gwin.COL0]
        for f in range(1, int(13 * R.FPS)):
            mem[R.FRAMECNT], mem[R.FRAMECNT + 1] = f & 0xFF, f >> 8
            cpu.run(lab["tickr"])
            ph, pg = mem[lab["ph"]], mem[lab["pg"]]
            rb = mem[lab["rowb"]]
            ours = [(cpu.vram[(rb + r) * 64 + gwin.COL0 + k] & 0xF000) == gwin.PAL for r in range(gwin.H) for k in range(gwin.W)]
            self.assertIn(sum(ours), (0, len(ours)), (f, ph, pg, sum(ours)))
            if (ph, pg) not in seen:
                seen[(ph, pg)] = f
                phases.append((f, ph, pg))
            if ph == 4 and pg not in shown:
                shown[pg] = f
                row, other = (R.POS_ROW[tops[pg]], R.POS_ROW[not tops[pg]])
                self.assertEqual(rb, row, (pg, phases))
                self.assertEqual((tl(row), tl(other)), (gwin.PAL | gwin.FRAME["tl"], 0), f"쪽 {pg}: 창은 제 자리에만")
                self.assertEqual(mem[lab["rcon"]], 2 if tops[pg] else 1, pg)
                self.assertEqual((adds(), rems()), {0: ([112], []), 1: ([112, 32, 112], [0]), 2: ([112, 32, 112], [0]), 3: ([112, 32, 112, 112], [0, 1, 2])}[pg], pg)
        self.assertEqual(mem[lab["ph"]], 6, phases)
        self.assertEqual(rems(), [0, 1, 2, 3], "건 핸들러를 다 뺐다")
        self.assertEqual(ysel, [winmask.SLOT_B - 1 if not t else 2 * winmask.SLOT_B - 1 for t in tops], "창 사각형: 쪽을 보일 때마다 그 쪽 위치 것")
        self.assertEqual((tl(1), tl(11)), (0, 0), "끝나면 두 자리 다 밑그림")
        self.assertIn((5, 1), seen, phases)  # 0(아래) → 1(위): 이어지는 쪽이어도 닫고 다시 연다
        self.assertNotIn((5, 2), seen, phases)  # 1 → 2(같은 위): 바로 잇는다
        self.assertIn((5, 3), seen, phases)  # 간격
        for pg, (a, _b) in enumerate(starts_ends):
            self.assertTrue(0 <= shown[pg] - R.frames(a) <= 8, (pg, shown[pg] - R.frames(a), phases))
        print("위치 전환 틱 기계:", phases)

    def test_scene6_block_fits(self):
        """씬 6 전 쪽을 안 B 로 붙인 블록이 한계(0x1A00) 안이고 코드 영역이 2섹터 안. 줄 코드는 거의 다 블록 안 번역 메시지에서 찾는다 — 꼬리 이음(`0F` 점프)으로 갈린 줄만 복사(10-31 실측 1줄)."""
        import common

        src = sorted(glob.glob(str(common.OUT_DIR / "text" / "*_006.bin")))
        if not src:
            self.skipTest("파생 블록 없음")
        table, _bank = _ctx()
        btab, _dyn = glyphdyn.block_table(table, 6)
        blk, _n = translate.translate_block(6, Path(src[0]).read_bytes(), btab)
        spec = R.on_flow_spec(6)
        plines = [R.rt_lines(pg.get("speaker"), pg["text"], btab) for pg in spec["pages"]]
        missing = [c for lines in plines for c, _ in lines if blk.find(c) < 0]
        self.assertLessEqual(len(missing), 3)  # 11-06 원판 도안(합자 폐지: 「!!」가 글리프 둘) 뒤 줄 끝 「!!」 3줄이 블록 안 줄과 달리 코드 영역에 따로 든다
        rt0 = R.RT
        try:
            R.RT = True
            R.SCENE_PARTS.clear()
            out, n = R.patch_block(6, blk, spec, btab)
            code, lab = R.container_tail([6])
        finally:
            R.RT = rt0
        self.assertEqual(n, 1)
        self.assertLessEqual(len(out), R.BLOCK_MAX)
        self.assertLessEqual(len(out) - len(blk), 160, "블록 쪽은 서명·통로 둘뿐(11-01 공용화)")
        self.assertLessEqual(len(code), R.CODE_MAX)
        fix = R.fixed_image(lab, code)
        self.assertLessEqual(R.FIXED_ORG + len(fix), R.FIXED_END)
        print(f"씬 6 안 B: 블록 +{len(out) - len(blk)}B({len(out)}B, 한계 {R.BLOCK_MAX}) · 코드 영역 {len(code)}B(한계 {R.CODE_MAX}) · 고정 영역 {len(fix)}B")


class TestMultiSite(unittest.TestCase):
    """토막이 둘 이상인 씬(168·88·196·151·46·50·63)은 첫 토막 하나만 자막이 붙던 구멍(11-05) — 명세가 토막마다 음성 호출 자리를 쥐고 둘째 이후는 `extra` 로 매달린다."""

    def test_extra_sites(self):
        import voice_sched as VS

        for sid, n in ((168, 3), (88, 2), (196, 2), (151, 2), (46, 2), (50, 2), (63, 2), (6, 1)):
            segs = VS.load(drafts=True)[str(sid)]
            self.assertEqual(len(segs), n)
            spec = R.on_flow_spec(sid)
            self.assertEqual(len(spec.get("extra", [])), n - 1, sid)
            for sp in spec.get("extra", []):
                self.assertTrue("voice_at" in sp or "voice_call_gate" in sp)

    def test_extra_keys_unique_and_clear_of_scene_ids(self):
        ks = {R._extra_key(s, i) for s in (168, 88, 196, 151, 46, 50, 63) for i in (1, 2)}
        self.assertEqual(len(ks), 14)
        self.assertTrue(all(0xE1 <= k < 0xFE for k in ks))


if __name__ == "__main__":
    unittest.main()


class CodeSector(unittest.TestCase):
    def test_code_sector_is_last_bank(self):
        """코드 영역은 컨테이너의 마지막 뱅크 — 뱅크 수를 원판보다 늘리지 않는다(16섹터 → 12 · 10섹터 → 8 · 14섹터 → 12)."""
        self.assertEqual([R.code_sector(n) for n in (16, 10, 14, 12, 9)], [12, 8, 12, 8, 8])
        self.assertEqual(R.code_sector(16), R.CODE_SECTOR)
