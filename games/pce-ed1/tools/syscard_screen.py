"""구형 시스템 카드 안내 화면(「슈퍼 시스템 카드를 사용해 주십시오.」) 한글화 — 코드 훅으로 한글 타일을 덮어쓴다.

배경(2026-10-15 조사 — docs/devlog.md): IPL(`$4000`, rel 2~21)이 카드 버전 < 3 이면 rel 4~27(24섹터)을 뱅크 0x80~ 에 올려 `$4000` 으로 간다.
그 프로그램이 그림(공주·기사·카드)과 **글씨 띠**(BAT 행 23~25, 타일 0x211~0x24E, 4평면·팔레트 1)를 그린다. 글씨는 압축 그림 자산이라 풀지 않고,
**그림이 다 올라간 뒤 한 번 한글 타일·BAT 를 VRAM 에 덮어쓴다**(원판 그림 불변).

배치(전부 rel 4~27 안, IPL 스텁·정상 부팅 구역(rel ≥ 34) 불변):
  · 훅 호출부 — 메인 루프 끝 `JSR $4094`(rel 4 +0x43, 논리 `$4043`) → `JSR HOOK`
  · 훅 코드 — 0 런(이미지 +0x2240 = 논리 `$6240`, 원판 0 이 577B) 안
  · 데이터 — rel 25~27(원판 0 의 3섹터, 뱅크 0x85 +0x800 = 이미지 +0xA800). 훅이 MPR5(`$A000`)에 뱅크 0x85 를 잠깐 걸고 읽는다
  · 한 번만: RAM `$3090`(원판 0 인 작업 RAM) 플래그. BAT[24][0] 이 원판 글씨 타일(`$1218`)로 보일 때까지 기다린 뒤(그림이 아직 안 올라왔으면 원판이 나중에
    덮어쓰므로) 쓴다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import hook
from hook import Asm

hook.OPS.update({("ST1", "imm"): 0x13, ("ST2", "imm"): 0x23, ("NOP", "imp"): 0xEA, ("CLI", "imp"): 0x58})

# ── 값 하나로 바꿀 수 있는 것(마스터 10-15: 문안·정렬) ───────────────────────────
TEXT = "슈퍼 시스템 카드를 사용해 주십시오."
ALIGN = "center"  # "center" | "left"(원판은 왼쪽 x=2 부터 폭 가득)

# ── 좌표 규약 ───────────────────────────────────────────────────────────────
IPL_REL = 4  # 안내 프로그램 시작 섹터(rel)
LOGICAL0 = 0x4000  # 이미지 +0 ↔ 논리 $4000
CALL_OFF = 0x43  # 메인 루프 끝의 `JSR $4094`(20 94 40)
CALL_ORIG = b"\x20\x94\x40"
CODE_OFF = 0x2240  # 이미지 안 0 런(+0x223F, 577B) — 뱅크 0x81 +0x240. 🔴 루프 중엔 MPR3 가 뱅크 0 이라 `$6240` 이 안 보인다 → 트램펄린이 잠깐 건다
TRAMP_OFF = 0x1845  # 항상 보이는 `$4000~$5FFF` 안의 0 틈(+0x1845, 15B) — 논리 $5845. `TMA/TAM #3` + `JSR $6240`
CODE_MAX = 0x223F + 577 - CODE_OFF
DATA_OFF = 0xA800  # rel 25 시작 = 뱅크 0x85 +0x800
DATA_BANK, DATA_ADDR = 0x85, 0xA800
DATA_MAX = (27 - 25 + 1) * common.USER
FLAG_ADDR = 0x3090  # 원판 0 인 작업 RAM
BAT_ROWS = (23, 24, 25)  # 글씨 띠(타일 행)
BAT_STRIDE = 64  # BAT 한 행 = 64 워드
BAND_Y0 = 184  # 행 23 의 화면 y
GLYPH_Y0 = 191  # 원판 글자 첫 행 — 마스크 행 1 이 여기에 놓인다
BLANK_ENTRY = 0x1141  # 빈 타일(0x141) · 팔레트 1
TILE_SLOTS = list(range(0x211, 0x24F)) + list(range(0x24F, 0x300))  # 원판 글씨 타일 → 그 뒤 원판 0 이던 타일(스프라이트 패턴은 0x384~)
WORDS_PER_REC = 112  # 한 기록 최대 7타일(Y 8비트 안)


def render_mask(text: str):
    """한글 글씨 마스크 → (24행 × 256열 0/1 배열, 가로 시작 x). 글꼴·폭 규약은 오프닝 자막과 같은 Galmuri 11 12px · 공백 반각."""
    import numpy as np
    import opening_sub as o

    m, _edge = o.render_line(text)  # 14행 × W (글자 행 1~12)
    ink_w = m.shape[1] - 2
    band = np.zeros((24, 256), dtype=np.uint8)
    x0 = (256 - ink_w) // 2 - 1 if ALIGN == "center" else 1
    assert x0 >= 0 and x0 + m.shape[1] <= 256, f"한글 안내문이 띠(256px)를 넘는다: 폭 {ink_w}px"
    r0 = GLYPH_Y0 - BAND_Y0 - 1  # 마스크 행 1 → 띠 행 GLYPH_Y0−BAND_Y0
    for y in range(1, 13):
        for x in range(m.shape[1]):
            if m[y, x]:
                band[r0 + y, x0 + x] = 1
    return band, x0


def tile_bytes(rows8) -> bytes:
    """8행 글자 비트(행마다 정수 0~255, 왼쪽 = MSB) → 32B(평면 0 전부 1, 평면 1~3 = 글자). 원판 글씨 타일 규약(덤프 실측)과 같다."""
    out = bytearray()
    for b in rows8:
        out += bytes((0xFF, b))  # 평면 0·1
    for b in rows8:
        out += bytes((b, b))  # 평면 2·3
    return bytes(out)


def build_tiles(text: str = TEXT):
    """→ (tiles{타일번호: 32B}, bat{행: [32 워드]}, 한글 폭 px)."""
    band, x0 = render_mask(text)
    tiles: dict[bytes, int] = {}
    order: list[bytes] = []
    bat = {}
    for ri, row in enumerate(BAT_ROWS):
        words = []
        for c in range(32):
            rows8 = []
            for y in range(8):
                v = 0
                for x in range(8):
                    v = (v << 1) | int(band[ri * 8 + y, c * 8 + x])
                rows8.append(v)
            if not any(rows8):
                words.append(BLANK_ENTRY)
                continue
            tb = tile_bytes(rows8)
            if tb not in tiles:
                assert len(order) < len(TILE_SLOTS), "타일이 모자란다"
                tiles[tb] = TILE_SLOTS[len(order)]
                order.append(tb)
            words.append(0x1000 | tiles[tb])
        bat[row] = words
    return {tiles[tb]: tb for tb in order}, bat, int(band.any(axis=0).sum())


def build_data(text: str = TEXT) -> bytes:
    """뱅크 0x85 +0x800 에 놓을 기록 표 — `[워드 수][VRAM 주소 lo][hi][워드…(LE)]`… 끝 0."""
    tiles, bat, _w = build_tiles(text)
    recs = bytearray()
    ids = sorted(tiles)
    i = 0
    while i < len(ids):  # 연속 타일 번호를 한 기록(≤ 7타일)으로
        j = i
        while j + 1 < len(ids) and ids[j + 1] == ids[j] + 1 and (j + 1 - i + 1) * 16 <= WORDS_PER_REC:
            j += 1
        data = b"".join(tiles[t] for t in ids[i : j + 1])
        addr = ids[i] * 16
        recs += bytes((len(data) // 2, addr & 0xFF, addr >> 8)) + data
        i = j + 1
    for row in BAT_ROWS:
        words = bat[row]
        addr = row * BAT_STRIDE
        recs += bytes((len(words), addr & 0xFF, addr >> 8)) + b"".join(w.to_bytes(2, "little") for w in words)
    recs += b"\x00"
    assert len(recs) <= DATA_MAX, f"한글 타일 자료 {len(recs)}B > {DATA_MAX}B"
    return bytes(recs)


def build_tramp() -> bytes:
    """`JSR $5845` 로 불린다 — MPR3 에 뱅크 0x81 을 걸고 훅 본체(`$6240`)를 부른 뒤 되돌린다(14B)."""
    a = Asm(LOGICAL0 + TRAMP_OFF)
    a.op("TMA", "tma", 3)
    a.op("PHA")
    a.op("LDA", "imm", 0x81)
    a.op("TAM", "tam", 3)
    a.op("JSR", "abs", LOGICAL0 + CODE_OFF)
    a.op("PLA")
    a.op("TAM", "tam", 3)
    a.op("RTS")
    code = a.bytes()
    assert len(code) <= 15, len(code)
    return code


def build_code() -> tuple[bytes, int]:
    """훅 본체 → (바이트, 진입 논리 주소). 진입 = `$6240`(MPR3 = 뱅크 0x81 일 때)."""
    entry = LOGICAL0 + CODE_OFF
    a = Asm(entry)
    a.label("hook")
    a.op("JSR", "abs", 0x4094)  # 원래 호출
    a.op("LDA", "abs", FLAG_ADDR)
    a.op("BEQ", "rel", "go")
    a.op("RTS")  # 이미 했다
    a.label("go")
    a.op("SEI")
    # BAT[24][0] 이 원판 글씨 타일($1218)인가 — VDC MARR = 24×64 = $0600, VRR 읽기
    a.op("ST0", "imm", 0x01)
    a.op("ST1", "imm", 0x00)
    a.op("ST2", "imm", 0x06)
    a.op("ST0", "imm", 0x02)
    for _ in range(4):
        a.op("NOP")
    a.op("LDA", "abs", 0x0002)
    a.op("CMP", "imm", 0x18)
    a.op("BNE", "rel", "notready")
    a.op("LDA", "abs", 0x0003)
    a.op("CMP", "imm", 0x12)
    a.op("BNE", "rel", "notready")
    # 뱅크 0x85 를 MPR5($A000)에 잠깐 건다
    a.op("TMA", "tma", 5)
    a.op("PHA")
    a.op("LDA", "imm", DATA_BANK)
    a.op("TAM", "tam", 5)
    a.op("LDA", "zp", 0xFC)
    a.op("PHA")
    a.op("LDA", "zp", 0xFD)
    a.op("PHA")
    a.op("LDA", "imm", DATA_ADDR & 0xFF)
    a.op("STA", "zp", 0xFC)
    a.op("LDA", "imm", DATA_ADDR >> 8)
    a.op("STA", "zp", 0xFD)
    a.label("rec")
    a.op("LDY", "imm", 0)
    a.op("LDA", "izpy", 0xFC)
    a.op("BEQ", "rel", "fin")
    a.op("TAX")
    a.op("LDA", "imm", 0x00)
    a.op("STA", "abs", 0x0000)  # VDC 레지스터 0 = MAWR
    a.op("LDY", "imm", 1)
    a.op("LDA", "izpy", 0xFC)
    a.op("STA", "abs", 0x0002)
    a.op("INY")
    a.op("LDA", "izpy", 0xFC)
    a.op("STA", "abs", 0x0003)
    a.op("LDA", "imm", 0x02)
    a.op("STA", "abs", 0x0000)  # 레지스터 2 = VWR
    a.op("CLC")
    a.op("LDA", "zp", 0xFC)
    a.op("ADC", "imm", 3)
    a.op("STA", "zp", 0xFC)
    a.op("BCC", "rel", "w0")
    a.op("INC", "zp", 0xFD)
    a.label("w0")
    a.op("LDY", "imm", 0)
    a.label("w")
    a.op("LDA", "izpy", 0xFC)
    a.op("STA", "abs", 0x0002)
    a.op("INY")
    a.op("LDA", "izpy", 0xFC)
    a.op("STA", "abs", 0x0003)
    a.op("INY")
    a.op("DEX")
    a.op("BNE", "rel", "w")
    a.op("TYA")
    a.op("CLC")
    a.op("ADC", "zp", 0xFC)
    a.op("STA", "zp", 0xFC)
    a.op("BCC", "rel", "rec")
    a.op("INC", "zp", 0xFD)
    a.op("BRA", "rel", "rec")
    a.label("fin")
    a.op("PLA")
    a.op("STA", "zp", 0xFD)
    a.op("PLA")
    a.op("STA", "zp", 0xFC)
    a.op("PLA")
    a.op("TAM", "tam", 5)
    a.op("LDA", "imm", 1)
    a.op("STA", "abs", FLAG_ADDR)
    a.label("notready")
    a.op("LDA", "zp", 0xF7)  # 프로그램이 VDC 레지스터 선택 그림자를 $F7 에 둔다 — IRQ 가 복원에 쓴다
    a.op("STA", "abs", 0x0000)
    a.op("CLI")
    a.op("RTS")
    code = a.bytes()
    assert len(code) <= CODE_MAX, f"훅 코드 {len(code)}B > {CODE_MAX}B"
    return code, entry


def apply(f, touched) -> str:
    from shared.disc import mode1

    code, entry = build_code()
    data = build_data()
    T2 = common.T2_SECTOR

    def patch(img_off, new, expect, label):
        rel = IPL_REL + img_off // common.USER
        o = img_off % common.USER
        assert o + len(new) <= common.USER or True
        # 섹터 경계를 넘으면 나눠서 쓴다
        done = 0
        while done < len(new):
            r = IPL_REL + (img_off + done) // common.USER
            oo = (img_off + done) % common.USER
            n = min(len(new) - done, common.USER - oo)
            mode1.write_at(f, T2 + r, common.USER, oo, new[done : done + n], label=label, expect=expect[done : done + n])
            touched.append((T2 + r, 1))
            done += n

    tramp = build_tramp()
    tent = LOGICAL0 + TRAMP_OFF
    patch(CALL_OFF, b"\x20" + tent.to_bytes(2, "little"), CALL_ORIG, "syscard call")
    patch(TRAMP_OFF, tramp, b"\0" * len(tramp), "syscard trampoline")
    patch(CODE_OFF, code, b"\0" * len(code), "syscard hook code")
    patch(DATA_OFF, data, b"\0" * len(data), "syscard hangul tiles")
    return f"시스템 카드 안내 한글 띠: 코드 {len(code)}B · 타일·BAT 자료 {len(data)}B (rel {IPL_REL}~27 안, 정상 부팅 구역 불변)"


def verify_iso(iso) -> str:
    """굽고 난 이미지에서 훅 호출부·코드·자료가 의도한 그대로인지 되읽는다 + 안내 프로그램 이미지의 나머지(원판 쪽)는 안 바뀌었는지."""
    code, entry = build_code()
    data = build_data()
    with open(iso, "rb") as f:
        got = bytearray()
        for rel in range(IPL_REL, 28):
            f.seek((common.T2_SECTOR + rel) * common.RAW + common.USER_OFF)
            got += f.read(common.USER)
    tramp = build_tramp()
    assert got[CALL_OFF : CALL_OFF + 3] == b"\x20" + (LOGICAL0 + TRAMP_OFF).to_bytes(2, "little"), "훅 호출부가 다르다"
    assert got[TRAMP_OFF : TRAMP_OFF + len(tramp)] == tramp, "트램펄린이 다르다"
    assert got[CODE_OFF : CODE_OFF + len(code)] == code, "훅 코드가 다르다"
    assert got[DATA_OFF : DATA_OFF + len(data)] == data, "한글 타일 자료가 다르다"
    orig = b"".join(common.track_data(IPL_REL + i, 1) for i in range(24))
    diff = [i for i in range(len(orig)) if orig[i] != got[i]]
    allowed = set(range(CALL_OFF, CALL_OFF + 3)) | set(range(TRAMP_OFF, TRAMP_OFF + len(tramp))) | set(range(CODE_OFF, CODE_OFF + len(code))) | set(range(DATA_OFF, DATA_OFF + len(data)))
    assert set(diff) <= allowed, "안내 프로그램 이미지의 다른 자리가 바뀌었다"
    return f"시스템 카드 안내 되읽기 OK — 호출부 3B · 트램펄린 {len(tramp)}B · 코드 {len(code)}B · 자료 {len(data)}B, 이미지 나머지 불변"


def preview(out_dir) -> None:
    """굽기 전 미리보기 — 원판 띠 vs 한글 띠(1배·4배)와 안내 화면 전체."""
    import numpy as np
    from PIL import Image

    out_dir = Path(out_dir)
    src = out_dir / "orig-forced-old-path.png"
    a = np.array(Image.open(src).convert("RGB"))
    tiles, bat, _ = build_tiles()
    band, x0 = render_mask(TEXT)
    new = a.copy()
    bg = (36, 180, 144)
    new[BAND_Y0 : BAND_Y0 + 24, :, :] = bg
    for y in range(24):
        for x in range(256):
            if band[y, x]:
                new[BAND_Y0 + y, x] = (252, 252, 252)
    Image.fromarray(new).save(out_dir / "preview-ko-full-1x.png")
    Image.fromarray(new).resize((1024, 928), Image.NEAREST).save(out_dir / "preview-ko-full-4x.png")
    y0, y1 = 186, 208
    cmp = np.concatenate([a[y0:y1], np.full((2, 256, 3), 90, dtype=np.uint8), new[y0:y1]], axis=0).astype(np.uint8)
    Image.fromarray(cmp).save(out_dir / "preview-band-1x.png")
    Image.fromarray(cmp).resize((1024, cmp.shape[0] * 4), Image.NEAREST).save(out_dir / "preview-band-4x.png")
    print(f"미리보기 저장 — 한글 폭 {int(band.any(axis=0).sum())}px(시작 x={x0}) · 타일 {len(tiles)}장 · 자료 {len(build_data())}B")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--preview":
        preview(sys.argv[2])
    else:
        code, entry = build_code()
        print(f"훅 {len(code)}B @ ${entry:04X} (여유 {CODE_MAX - len(code)}B) · 자료 {len(build_data())}B / {DATA_MAX}B")
