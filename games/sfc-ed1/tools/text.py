"""sfc-ed1 대본 — 문자표 · 사전 · 메시지 포인터 표 · 디코더 · 덤프.

읽어 낸 근거는 전부 `message.asm`($02:DC41~$02:F22C, 롬에 RCS 태그가 박혀 있다)의 디스어셈블이다.
자세한 경위는 `docs/status.md` 3~4절. 여기엔 **정본 상수**와 그 상수를 쓰는 도구만 둔다.

문자 체계(인게임 실측 아님 — 코드 판독, 인게임 확인은 「남은 일」):
  $00~$CE  1바이트 글자. 가나 전용(한자 없음). $10 = 공백, $CF = 개행.
           글자 → VRAM 타일은 `$03:F3EC` 표(2B × $D0)가 정하고, 글꼴은 1bpp 8×8 타일 시트
           (`$18:E02C` 부터, 위 타일 t · 아래 타일 t+$10 = 8×16 글자 한 자)다.
  $D0~$DF  사전 치환. `$D0 xx`(인명) `$D1 xx`(지명) `$D2 xx`(아이템) `$D3 xx`(몬스터)
           `$D4 xx`(마법) `$D5 xx`(시스템 문장)는 2바이트 — xx<$80 이면 2B 포인터 표의 항목.
           $D6~$DF 는 인자 없이 런타임 값(파티원 이름·아이템명 등)을 꽂는다.
  $E0~$FF  제어. $E0/$E4 끝 · $E1~$E3 색 · $EF 창 지움 · $FE 호출 복귀 · $FF 키 대기+페이지 ·
           $F0~$F7 조건(다음 항목 하나) · $F9/$FA/$FB/$FC/$FD 호출·점프(ARGLEN 주석). 선형 파싱은
           분기를 따라가지 않는다 — 한 포인터 구간에 END 로 끝나는 조각이 여럿 나오는 이유다.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

# ---------------------------------------------------------------- 문자표
_KANA = (
    "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん"
    "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン"
    "ゃゅょ"
)
_DAKU = "がぎぐげござじずぜぞだぢづでどばびぶべぼガギグゲゴザジズゼゾダヂヅデドバビブベボヴぱぴぷぺぽパピプペポ"

TABLE: dict[int, str] = {i: str(i) for i in range(10)}
TABLE.update({0x0A: " ", 0x0B: "ー", 0x0C: "!", 0x0D: " ", 0x0E: "…", 0x0F: "?", 0x10: "　"})
TABLE.update({0x11 + i: ch for i, ch in enumerate(_KANA)})  # $11~$6F
TABLE.update(
    {
        # $70~$7F — 소문자 가나 둘째 벌(타일 $100~$107). $70/$7A 는 타일 $1B9(시트 밖) — 사전의 「フ?ーガソン」(=ファーガソン)·
        # 「フ?ンガス」 문맥으로 ァ 로 확정. $0E(타일 $1BA)는 「ざんねんです???。」(1,627건) 문맥으로 … — ハイ?アギール 도 같은 글리프를 빌려 쓴다.
        0x70: "ァ",
        0x71: "ィ",
        0x72: "ゥ",
        0x73: "ぇ",
        0x74: "ォ",
        0x75: "っ",
        0x76: " ",
        0x77: "ャ",
        0x78: "ュ",
        0x79: "ョ",
        0x7A: "ァ",
        0x7B: "ィ",
        0x7C: "ゥ",
        0x7D: "ェ",
        0x7E: "ォ",
        0x7F: "ッ",
        0x80: " ",
        0x81: " ",
        0x82: " ",
        0x83: "。",
        0x84: "、",
        0x85: "「",
        0x86: "」",
        # 영문은 GOLD·HP·MP·LV 에 쓰는 만큼만 있다. $8C 는 타일 $1BB(시트 밖) — 문맥(GOLD)으로 O.
        0x87: "H",
        0x88: "M",
        0x89: "E",
        0x8A: "P",
        0x8B: "G",
        0x8C: "O",
        0x8D: "L",
        0x8E: "D",
        0x8F: "C",
    }
)
TABLE.update({0x90 + i: ch for i, ch in enumerate(_DAKU)})  # $90~$C2
TABLE.update({0xC3: "A", 0xC4: "B"})
# $C5~$CE → 타일 $1D6~$1DF: 글꼴 시트 밖이라 아직 모양을 못 봤다(빈도 70·19·1·24·27·27·21·26·25·2).
for _c in range(0xC5, 0xCF):
    TABLE[_c] = f"[{_c:02X}]"
NEWLINE = 0xCF
SPACE = 0x10

# ---------------------------------------------------------------- 사전 (2B 포인터 표, 항목은 $FF 종료)
# 뱅크 $02 의 네 표는 등을 맞대고 붙어 있다 — $D3(E7E0) → $D1(E8A2) → $D0(E902) → $D5(E9B4) → 문자열(EA1E~).
# 항목 수는 그 경계에서 나온다(D3 97 · D1 48 · D0 89 · D5 53). $D2 는 첫 문자열(F061)까지 119,
# $D4 는 문자열이 표 **앞**($03:EF19~)에 있어 포인터가 $8000 아래로 떨어지는 자리까지 21.
DICT_TABLES = {
    0xD0: (0x02E902, 89, "인명"),
    0xD1: (0x02E8A2, 48, "지명"),
    0xD2: (0x03EF73, 119, "아이템"),
    0xD3: (0x02E7E0, 97, "몬스터"),
    0xD4: (0x03F58A, 21, "마법"),
    0xD5: (0x02E9B4, 53, "시스템 문장"),
}
# 인자 없는 런타임 치환(핸들러 $02:E0E5~) — 파티원 이름·아이템·수치 등. 뜻은 인게임에서 못 박는다.
RUNTIME_SUBST = {0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xDB, 0xDC, 0xDD, 0xDE, 0xDF}

# ---------------------------------------------------------------- 제어코드 인자 길이
END_CODES = {0xE0, 0xE4}
ARGLEN = {0xE1: 0, 0xE2: 0, 0xE3: 0, 0xEF: 0, 0xFE: 0, 0xFF: 0}
ARGLEN.update({c: 1 for c in range(0xE5, 0xEE)})  # $E5~$ED
ARGLEN[0xEE] = 3  # 네이티브 코드 호출(24비트 주소, `jml [$06]`)
ARGLEN.update(
    {c: 1 for c in range(0xF0, 0xF9)}
)  # $F0~$F2 조건(거짓이면 다음 항목 건너뜀) · $F3~$F6 조건 · $F7 화자 · $F8
ARGLEN.update({0xF9: 3, 0xFA: 2, 0xFB: 5, 0xFC: 2, 0xFD: 5})  # 분기·호출 — 게임의 건너뛰기 표 값
CTRL_NAME = {
    0xE0: "END",
    0xE1: "COLOR_POP",
    0xE2: "COLOR_4",
    0xE3: "COLOR_C",
    0xE4: "END2",
    0xE5: "SFX",
    0xEE: "CALL_NATIVE",
    0xEF: "CLEAR",
    0xF0: "IF_SET",
    0xF1: "IF_SET1",
    0xF2: "IF_SET2",
    0xF3: "IF_SET3",
    0xF4: "IF_CLR",
    0xF5: "IF_CLR1",
    0xF6: "IF_CLR2",
    0xF7: "IF_CLR3",
    0xF8: "SPEAKER",
    0xF9: "CALL_ABS",
    0xFA: "JUMP",
    0xFB: "JUMP_TBL",
    0xFC: "CALL",
    0xFD: "CALL_TBL",
    0xFE: "RETURN",
    0xFF: "PAGE",
}

# ---------------------------------------------------------------- 메시지 포인터 표 (3B 포인터, 24비트 LoROM 주소)
# 어느 표를 쓰는지는 `$060C` 의 상위 비트가 고른다($02:DD00~). 세 표가 $07:8000~$07:A721 에 등을 맞대고
# 있고 문안은 $07:A721 부터다 — 스캔으로 세면 뒤 표까지 이어 읽으므로 **경계로 센다**(첫 세션엔 3,339 로
# 잘못 쟀다: 뒤 표 둘이 딸려 왔다).
MSG_TABLES = {
    "main": (0x078000, 2906),  # ~$07:A20E
    "alt1": (0x07A20E, 90),  # ~$07:A31C
    "alt2": (0x07A31C, 343),  # ~$07:A721
    "alt3": (0x0BE8AB, 19),
}
TEXT_START = 0x07A721  # 대본 본체 시작(표 끝) — 연속해서 $0B:FE75 까지
CHAR_BYTES_MAIN = (
    171_580  # main 표 2,906건 각 첫 조각의 글자 바이트(제어·사전 인자 제외) — 스캐너 회귀용
)
TILE_TABLE = 0x03F3EC  # 글자 코드 → VRAM 타일(2B: 번호 하위 · 속성|번호 상위 2비트)
FONT_SHEET = 0x18E02C  # 1bpp 8×8 타일 시트, 타일 0 = 빈 칸


def _rom() -> bytes:
    return common.rom_bytes()


def cstr(off: int, rom: bytes | None = None) -> bytes:
    rom = rom or _rom()
    end = rom.index(b"\xff", off)
    return rom[off:end]


def dict_entries(code: int, rom: bytes | None = None) -> list[bytes]:
    """사전 한 벌 — 항목 수는 DICT_TABLES 의 정본이고, 포인터가 롬 밖이면 그 자리에서 운다."""
    rom = rom or _rom()
    addr, n, _ = DICT_TABLES[code]
    base = common.snes2off(addr)
    bank = addr & 0xFF0000
    out = []
    for i in range(n):
        p = rom[base + 2 * i] | (rom[base + 2 * i + 1] << 8)
        if p < 0x8000:
            raise SystemExit(f"사전 {code:02X}[{i}] 포인터가 롬 밖이다: {p:04X}")
        out.append(cstr(common.snes2off(bank | p), rom))
    return out


def msg_pointers(name: str = "main", rom: bytes | None = None) -> list[int]:
    rom = rom or _rom()
    addr, n = MSG_TABLES[name]
    base = common.snes2off(addr)
    out = []
    for i in range(n):
        lo, hi, bk = rom[base + 3 * i : base + 3 * i + 3]
        p = (bk << 16) | (hi << 8) | lo
        if hi < 0x80 or not (0x04 <= bk <= 0x3F):  # $20~$3F = 확장 뱅크(build.py 가 옮긴 자리)
            raise SystemExit(f"{name}[{i}] 이 포인터가 아니다: {p:06X}")
        out.append(p)
    return out


def decode(b: bytes, resolve=None, depth: int = 0) -> str:
    """바이트열 → 읽을 수 있는 문자열. 사전은 `{…}`, 런타임 치환은 `<D6>`, 제어는 `<NAME …>`.
    `resolve(code, idx)` 가 사전 항목 바이트를 돌려준다(없으면 `<D0 xx>` 로 남긴다)."""
    out = []
    i = 0
    n = len(b)
    while i < n:
        c = b[i]
        if c < 0xD0:
            out.append("\n" if c == NEWLINE else TABLE[c])
            i += 1
        elif c in DICT_TABLES:
            arg = b[i + 1] if i + 1 < n else None
            if arg is not None and resolve is not None and depth < 2:
                try:
                    # $D0 8x = 항목 x&$F 를 강조색으로(핸들러 $02:E029~) — 표시는 같은 꼴로
                    out.append(
                        "{"
                        + decode(resolve(c, arg & 0x7F if c == 0xD0 else arg), resolve, depth + 1)
                        + "}"
                    )
                except (IndexError, ValueError):
                    out.append(f"<{c:02X} {arg:02X}>")
            else:
                out.append(f"<{c:02X}" + (f" {arg:02X}>" if arg is not None else ">"))
            i += 2
        elif c in RUNTIME_SUBST:
            out.append(f"<{c:02X}>")
            i += 1
        else:
            k = ARGLEN.get(c, 0)
            args = b[i + 1 : i + 1 + k]
            name = CTRL_NAME.get(c, f"{c:02X}")
            out.append(f"<{name}" + (" " + args.hex() if args else "") + ">")
            i += 1 + k
            if c in END_CODES:
                break
    return "".join(out)


def resolver(rom: bytes | None = None):
    rom = rom or _rom()
    cache = {code: dict_entries(code, rom) for code in DICT_TABLES}
    return lambda code, idx: cache[code][idx]


def parse_span(rom: bytes, start: int, end: int | None) -> list[tuple[int, bytes]]:
    """start 부터 선형으로 읽어 END 마다 끊는다. end(다음 포인터 목표)를 넘기면 거기서 자른다.
    분기($F9/$FA/$FC)를 따라가지 않으므로 한 포인터 구간 안에 여러 조각이 나온다 — 그게 정상이다."""
    segs = []
    i = start
    seg_start = i
    while end is None or i < end:
        c = rom[i]
        if c < 0xD0:
            i += 1
        elif c < 0xE0:
            i += 2 if c in DICT_TABLES else 1
        else:
            i += 1 + ARGLEN.get(c, 0)
            if c in END_CODES:
                segs.append((seg_start, rom[seg_start:i]))
                seg_start = i
                if end is None:
                    break
    if end is not None and seg_start < end:
        segs.append((seg_start, rom[seg_start:end]))  # END 없이 다음 포인터에 닿은 꼬리
    return segs


def all_segments(rom: bytes | None = None):
    """네 표의 포인터를 전부 모아 정렬하고, 이웃 포인터 사이를 선형 파싱한다.
    돌려주는 항목: (table, index, addr_snes, off, raw)."""
    rom = rom or _rom()
    targets: dict[int, list[tuple[str, int]]] = {}
    for name in MSG_TABLES:
        for idx, p in enumerate(msg_pointers(name, rom)):
            targets.setdefault(common.snes2off(p), []).append((name, idx))
    offs = sorted(targets)
    out = []
    for k, off in enumerate(offs):
        end = offs[k + 1] if k + 1 < len(offs) else None
        labels = targets[off]
        for j, (seg_off, raw) in enumerate(parse_span(rom, off, end)):
            table, idx = labels[0]
            out.append(
                (table, idx, j, common.off2snes(seg_off), seg_off, raw, labels if j == 0 else [])
            )
    return out


def stats(rom: bytes | None = None) -> dict:
    rom = rom or _rom()
    chars = 0
    for p in msg_pointers("main", rom):
        for _, raw in parse_span(rom, common.snes2off(p), None):
            chars += sum(1 for c in raw if c < 0xD0)
            break
    return {
        "tables": {k: len(msg_pointers(k, rom)) for k in MSG_TABLES},
        "dicts": {f"{k:02X}": len(dict_entries(k, rom)) for k in DICT_TABLES},
        "char_bytes_main": chars,
    }


def check(rom: bytes | None = None) -> None:
    rom = rom or _rom()
    s = stats(rom)
    for k, (_, n) in MSG_TABLES.items():
        assert s["tables"][k] == n, (k, s["tables"][k])
    assert s["char_bytes_main"] == CHAR_BYTES_MAIN, s["char_bytes_main"]
    # 문자표 자체 — 가나가 겹치면 역변환(재삽입)이 조용히 틀린다
    kana = [v for k, v in TABLE.items() if 0x11 <= k <= 0x6F or 0x90 <= k <= 0xC2]
    assert len(kana) == len(set(kana)), "문자표에 겹치는 가나가 있다"
    # 타일 표 — 코드 $10 은 위아래 같은 타일(공백), $CF 는 표 밖 값
    t = common.snes2off(TILE_TABLE)
    assert rom[t + 2 * 0x10] == 0x08 and rom[t + 2 * 0x10 + 1] == 0x01, "타일 표가 예상과 다르다"
    print(f"표 {s['tables']} · 사전 {s['dicts']} · main 글자 {s['char_bytes_main']:,}B — OK")


def dump(out_dir: Path, rom: bytes | None = None) -> None:
    rom = rom or _rom()
    out_dir.mkdir(parents=True, exist_ok=True)
    res = resolver(rom)
    rows = []
    lines = []
    for table, idx, j, addr, _off, raw, labels in all_segments(rom):
        text = decode(raw, res)
        rows.append(
            {
                "table": table,
                "index": idx,
                "seg": j,
                "addr": f"{addr:06X}",
                "raw": raw.hex(),
                "text": text,
            }
        )
        head = " ".join(f"{t}[{i}]" for t, i in labels) if labels else f"  +{j}"
        lines.append(f"### {addr:06X} {head}\n{text}\n")
    (out_dir / "messages.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8"
    )
    (out_dir / "messages.txt").write_text("\n".join(lines), encoding="utf-8")
    for code, (_, _, label) in DICT_TABLES.items():
        ents = dict_entries(code, rom)
        (out_dir / f"dict_{code:02X}_{label}.txt").write_text(
            "\n".join(f"{i:3d} {decode(e, res)}" for i, e in enumerate(ents)), encoding="utf-8"
        )
    print(f"덤프: {len(rows)} 조각 → {out_dir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="표 크기·글자 수·문자표 불변식")
    ap.add_argument(
        "--dump", action="store_true", help="work/derived/text/ 에 대본·사전 덤프(원문 — 커밋 금지)"
    )
    ap.add_argument("--msg", type=int, help="main 표의 메시지 하나를 풀어 보인다")
    a = ap.parse_args()
    if a.check:
        check()
    if a.dump:
        dump(common.OUT_DIR / "text")
    if a.msg is not None:
        rom = _rom()
        p = msg_pointers("main", rom)[a.msg]
        for off, raw in parse_span(rom, common.snes2off(p), None):
            print(f"--- {common.fmt(common.off2snes(off))}")
            print(decode(raw, resolver(rom)))
    if not (a.check or a.dump or a.msg is not None):
        ap.print_help()
