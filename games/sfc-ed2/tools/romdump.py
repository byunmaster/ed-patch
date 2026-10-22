"""롬에서 대사 단위별 실제 바이트를 디코드해 원판·한글 짝 표를 만든다(대본 JSON 이 아니라 롬 — 마스터 10-20 「원문칸에 올바른 번역이 왔는가」).

    python3 romdump.py <출력 폴더> [--kr <한글 롬>]      # → pairs.tsv · manifest.md

번호 · 원판 · 한글 · 표시. 표기: ⏎ 쪽 넘김 · ↵ 줄바꿈 · `{…}` 변수/제어 · 〔…〕 화자 머리 · 사전 문장(`$E1`)·호출 조각(`$10`)은 펼친다.
표시: 원판만(한글 쪽이 비었다) · 한글만(원판 쪽이 비었다) · 둘 다 빔 · 포인터 공유(다른 단위가 같은 자리를 지나간다 — 짝 비교는 하되 중복 주의).
"""

import argparse
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import font
import glyphmap
import hangul_font
import kr
import patches
import script
import segs

TRAMP = patches.TRAMP_CODE
JOSA = {k: p for k, p in enumerate(kr.JOSA_PAIRS)}


def kr_glyph_map(rom: bytes) -> dict[int, str]:
    """한글 롬의 글리프 색인 → 글자. 롬의 표 비트맵을 글꼴 원천 글리프와 맞춰 되짚는다(배정 규칙을 다시 구현하지 않는다)."""
    import json
    import glob

    chars = set()
    for f in glob.glob(str(kr.TEXTMAP / "*.json")):
        for m in re.finditer(r'"kr": "((?:[^"\\]|\\.)*)"', open(f, encoding="utf-8").read()):
            chars |= {c for c in json.loads('"' + m.group(1) + '"') if ord(c) > 0x7E}
    import canon  # 정본 이름·명칭의 글자도(사전 이름·아이템·주문 표)

    for c in range(0xAC00, 0xD7A4):  # 한글 음절 전체 — 정본 글자가 문안 지도에 없을 수 있다
        chars.add(chr(c))
    chars |= set("…「」『』・～、。！？　＋－＝")
    rev = {}
    for c in chars:
        try:
            rev.setdefault(hangul_font.glyph12(c), c)
        except Exception:
            pass
    out = {}
    base = patches.FONT_OUT if len(rom) > common.ROM_SIZE else font.FULL_BASE  # 한글 롬은 글꼴 표를 롬 끝 확장 영역으로 옮긴다
    for i in range(0, 2048):
        a = base + i * font.FULL_STRIDE
        if a + font.FULL_STRIDE > len(rom):
            break
        bm = bytes(rom[a : a + font.FULL_STRIDE])
        if any(bm) and bm in rev:
            out[i] = rev[bm]
    out[0] = "　"
    return out


class Dec:
    def __init__(self, rom: bytes, is_kr: bool, gmap: dict[int, str] | None = None):
        self.d = rom
        self.kr = is_kr
        self.g = gmap or {}
        self.dicts = {k: common.snes2off(v) for k, v in script.DICTS_BY_NAME.items()}

    def glyph(self, code: int) -> str:
        i = code - 0x8000
        if self.kr:
            if 0x7F0 <= i <= 0x7F3:
                a, b = kr.JOSA_PAIRS[i - 0x7F0]
                return "{%s/%s}" % (a, b)
            if i in self.g:
                return self.g[i]
        return glyphmap.TABLE[i] if 0 <= i < len(glyphmap.TABLE) else "？"

    def dict_text(self, tbl: int, n: int, depth: int) -> str:
        o = self.dicts[f"E{tbl}"] + 3 * (n - 1)
        if n < 1 or o + 3 > len(self.d):
            return "?"
        p = common.snes2off(self.d[o] | self.d[o + 1] << 8 | self.d[o + 2] << 16)
        return self.walk(p, depth + 1, sub=True)

    def walk(self, o: int, depth: int = 0, sub: bool = False, limit: int = 100000) -> str:
        self.capped = False
        seen_goto = set()  # 점프 순환 감지 — 같은 목적지로 두 번 가면 되돌이(이벤트 루프)라 끊는다
        d, out, opened = self.d, [], False
        steps = 0
        while steps < limit and o < len(d):
            steps += 1
            b = d[o]
            if self.kr and b == TRAMP:
                tg = d[o + 1] | d[o + 2] << 8 | d[o + 3] << 16
                if not (0xC00000 <= tg <= 0xDFFFFF and (tg & 0xFFFF) >= 0x8000 or (tg & 0xFFFF) < 0x8000 and 0xC00000 <= tg):
                    out.append("{?점프}")
                    break
                if o in seen_goto:
                    out.append("{순환}")
                    break
                seen_goto.add(o)
                o = common.snes2off(tg)
                continue
            if self.kr and b == 0x16:
                o += 1
                continue
            ln = script.token_len(d, o)
            if ln is None:
                out.append("{?%02x}" % b)
                break
            if b in (0x00, 0x06, 0x07) or (not self.kr and b in (0x16, 0x17)):
                if b == 0x07:
                    out.append("↵")
                break
            if 0x80 <= b < 0x88 or 0xE2 <= b < 0xF0:
                out.append(self.glyph((b << 8) | d[o + 1]))
            elif 0x20 <= b < 0x80:
                out.append("?" if (self.kr and b == 0x22) else chr(b))
            elif 0x88 <= b < 0xE0:
                out.append(glyphmap.HALF_TABLE[b - 0x88])
            elif b in (0xE0, 0xE1):
                t = self.dict_text(b - 0xE0, d[o + 1], depth) if depth < 4 else "…"
                out.append("{%s}" % t if b == 0xE0 else t)
            elif b == 0x01:
                out.append("↵")
            elif b in (0x05, 0x08):
                out.append("⏎")
            elif b == 0x02:
                out.append("⏎" if False else "")
            elif b == 0x1E:
                out.append("〔")
                opened = True
            elif b == 0x04:
                out.append("〕" if opened else "")
                opened = False
            elif b == 0x10 and depth < 4:
                bank = (o >> 16) & 0xFF  # 파일 오프셋 → 뱅크는 상위 바이트(HiROM)
                tg = (common.off2snes(o) & 0xFF0000) | d[o + 1] | d[o + 2] << 8
                out.append(self.walk(common.snes2off(tg), depth + 1, sub=True) if (tg & 0xFFFF) >= 0x8000 or (tg >> 16) >= 0xC0 else "{?호출}")
            elif b == 0x0F:
                tg = (common.off2snes(o) & 0xFF0000) | d[o + 1] | d[o + 2] << 8
                if (tg & 0xFFFF) < 0x8000 and (tg >> 16) < 0xC0:
                    out.append("{?점프}")
                    break
                if o in seen_goto:
                    out.append("{순환}")
                    break
                seen_goto.add(o)
                o = common.snes2off(tg)
                continue
            elif b in (0x11, 0x12, 0x13, 0x14):
                out.append("{조건%02x}" % b)
            elif 0xF0 <= b <= 0xF9:
                out.append("{F%x}" % (b & 15))
            elif b in (0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1F, 0x03, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x15):
                if b not in (0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1F):
                    out.append("{%02x}" % b)
            o += ln
        if steps >= limit:
            self.capped = True  # 길이 상한에 걸림(순환·폭주) — 표시한다
            out.append("{…상한}")
        return "".join(out)


def esc(s: str) -> str:
    return s.replace("\t", " ").replace("\n", " ")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--kr", default=str(common.BUILD_DIR / "sfc-ed2" / "Dragon Slayer - Eiyuu Densetsu 2 (KR).sfc"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    jp = common.rom_bytes()
    kb = Path(a.kr).read_bytes()
    dj, dk = Dec(jp, False), Dec(kb, True, kr_glyph_map(kb))
    units = script.all_units(jp)
    # 포인터 공유: 다른 단위의 점프·호출 목적지 안에 시작이 드는 단위
    shared = set()
    for tgt, srcs in segs.jump_sources(jp).items():
        for s, e in units:
            if s <= tgt < e:
                shared.add(s)
    capped = 0
    rows, cnt = [], {"원판만": 0, "한글만": 0, "둘 다 빔": 0, "포인터 공유": 0, "": 0}
    for s, e in units:
        o = s + 4 if jp[s : s + 4] == b"\x5c\x0b\x8f\xc1" else s
        try:
            tj = dj.walk(o)
        except Exception:
            tj = "{해독 실패}"
        try:
            tk = dk.walk(o)
        except Exception:
            tk = "{해독 실패}"
        mark = ""
        if not tj.strip("↵⏎ 　〔〕") and not tk.strip("↵⏎ 　〔〕"):
            mark = "둘 다 빔"
        elif not tk.strip("↵⏎ 　〔〕"):
            mark = "원판만"
        elif not tj.strip("↵⏎ 　〔〕"):
            mark = "한글만"
        elif s in shared:
            mark = "포인터 공유"
        if getattr(dj, "capped", False) or getattr(dk, "capped", False) or "{…상한}" in tj + tk:
            capped += 1
        cnt[mark] += 1
        rows.append(f"{common.off2snes(o):06X}\t{esc(tj)}\t{esc(tk)}\t{mark}")
    nd = 0
    for tbl, n_, _jpt in script.dict_entries(jp):  # 사전 항목(이름 `$E0` · 문장 끝맺음 `$E1`)도 짝으로
        try:
            tj = dj.dict_text(int(tbl[1]), n_, 0)
        except Exception:
            tj = "{해독 실패}"
        try:
            tk = dk.dict_text(int(tbl[1]), n_, 0)
        except Exception:
            tk = "{해독 실패}"
        mk = "" if tj.strip() and tk.strip() else "둘 다 빔"
        rows.append(f"{tbl}:{n_}\t{esc(tj)}\t{esc(tk)}\t{mk}")
        nd += 1
    (out / "pairs.tsv").write_text("번호\t원판\t한글\t표시\n" + "\n".join(rows) + "\n", encoding="utf-8")
    sj, sk = hashlib.sha1(jp).hexdigest(), hashlib.sha1(kb).hexdigest()
    (out / "manifest.md").write_text(
        f"""# sfc-ed2 롬 대사집 짝 표 — manifest
- 원판 롬 sha1 `{sj}` · 한글 롬 sha1 `{sk}`
- 분모: 대사 단위 {len(units):,}(`script.all_units`) + 사전 항목 {nd}(`E0:n`·`E1:n`) — 전투 문구·시스템 메시지(`$C0/$C1`·`$D4/$D5`)는 같은 단위 목록 안에 있다. UI 창 블록·고정폭 칸·고정 표(이름·아이템·주문 표)는 이 표에 아직 없다
- 길이 상한(10만 토큰)에 걸린 행 {capped}(0 이어야 한다 — 잘린 행은 끝에 `{{…상한}}`)
- 표시별: 원판만 {cnt['원판만']} · 한글만 {cnt['한글만']} · 둘 다 빔 {cnt['둘 다 빔']} · 포인터 공유 {cnt['포인터 공유']} · 표시 없음(정상 짝) {cnt['']}
- 방법: 롬 바이트를 토큰 문법(`script.py`)으로 읽는다. 한글 롬은 트램펄린(`$17`)·같은 뱅크 점프(`$0F`)를 따라가고, 글리프 번호→글자는 롬의 글리프 표 비트맵을 글꼴 원천과 맞춰 되짚는다. 호출(`$10`)·사전(`$E0/$E1`)은 펼친다(`$E0` 이름은 `{{…}}`).
- 한계: 조건 토큰(`$11~$14`)은 두 갈래를 위에서 아래로 이어서 적는다 · 선택 분기·계산 값·이름 버퍼 변수는 `{{…}}` 표식뿐 · 글리프를 못 되짚은 글자는 `？`.
""",
        encoding="utf-8",
    )
    print(len(units), cnt)


if __name__ == "__main__":
    main()
