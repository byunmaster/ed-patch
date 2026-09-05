"""시스템 문구 — 본 프로그램(rel 34~129) 안의 고정 문자열 가족을 뜯고(왕복 검증) 되쓴다.

가족(2026-09-05 실측, 뱅크는 본 프로그램 적재 뱅크, 오프셋은 뱅크 안):
    speakers  0x74+0x0330  64B 레코드 × 4, 앞 16B 가 `이름 06` — `09 nn` 공용 화자. ⚠ 뒤 48B 는 능력치(건드리지 않는다)
    chapter   0x74+0x0198  「第１章　王子の旅立ち」 0x20 패딩 — 장 제목(창 위 띠)
    items     0x74+0x11A4  20B × 117    14B 이름(0x20 으로 오른쪽 정렬) + 6B 능력치
    spells    0x74+0x1AC8  11B × 29     8B 이름(0x20 오른쪽 정렬) + 3B
    labels    0x6D+0x15F6~0x182F  00 구분 목록(메뉴 라벨) — 코드가 **절대주소**로 하나씩 가리킨다(분할 즉치 141곳)
    sysmsg    0x6D+0x182F~0x1F1A  씬 인터프리터 메시지(전투·세이브·아이템 문구) — 역시 절대주소 참조
    files     0x78+0x13FB  12B × 52     파일 선택 화면 지명(전각 공백 패딩)
    places    0x74+0x1C1E  12B × 50     **HUD 이름칸** 지명 — `이름 06` + 00 패딩. 12B 를 꽉 채우면 06 이 없다
                                        (렌더러 `$92A0` 가 06 까지 스캔하고 짧으면 전각 공백으로 채운다)
    screens   0x78+0x01E3~0x0330 · 0x78+0x049E~0x0558   부팅(백업 메모리 경고·안내)·파일 선택 화면
                                        `col row <SJIS> 00` 레코드가 이어지고 `FF` 로 화면이 끝난다

⚠ 재삽입 규칙: **주소를 안 옮긴다.** 고정폭은 폭 안에서, labels 는 원래 길이 안에서(라벨 렌더러는 점프를
모른다), sysmsg 는 제자리 + 짧아져 다음 단위로 흘러가면 `0F` 로 **같은 뱅크(0x6D) 안 다음 단위**에 잇는다.
🔴 예전 주석은 「뱅크 0x74 의 빈 화자 슬롯 영역(+0x430~)에 잇는다」고 적혀 있었는데 **구현은 그런 적이 없고**
(`sysbuild.apply` 는 `0F 0x8000+off` 로 0x6D 안에서만 잇는다) 그래도 됐다 — 그 구간은 비어 있지 않다.
전투 블록이 뱅크 0x74 **+0x400** 에 풀리고 전투 참가자 레코드가 `$C430` 이다(`battle.py`).
"""

import itertools
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import messages as M

MAIN_REL = 34


def bank_bytes(bank: int) -> bytes:
    return common.track_data(MAIN_REL + (bank - 0x68) * 4, 4)


def bank_rel(bank: int, off: int) -> tuple[int, int]:
    return MAIN_REL + (bank - 0x68) * 4 + off // common.USER, off % common.USER


def _pad_right_align(name: bytes, width: int, pad: bytes) -> bytes:
    if len(name) > width:
        raise ValueError(f"{name!r} 가 {width}B 를 넘는다")
    n = (width - len(name)) // len(pad)
    return pad * n + b" " * ((width - len(name)) % len(pad)) + name


# ─── 고정폭 표 ─────────────────────────────────────────────────────────────
FIXED = {
    # name: (bank, base, stride, name_width, count, pad, tail)
    #   pad `\x06` = 「이름 06 + 00 패딩」 꼴(HUD 이름칸) — 12B 를 꽉 채우면 06 을 안 쓴다
    "items": (0x74, 0x11A4, 20, 14, 117, b" ", 6),
    "spells": (0x74, 0x1AC8, 11, 8, 29, b" ", 3),
    "files": (0x78, 0x13FB, 12, 12, 52, b"\x81\x40", 0),
    "places": (0x74, 0x1C1E, 12, 12, 50, b"\x06", 0),
}


def read_fixed(name: str):
    bank, base, stride, w, n, pad, _tail = FIXED[name]
    b = bank_bytes(bank)
    out = []
    for k in range(n):
        e = b[base + k * stride : base + (k + 1) * stride]
        raw = e[:w]
        txt = raw.lstrip(b" ")
        if pad == b"\x06":
            txt = raw.split(b"\x06")[0]
        elif pad == b"\x81\x40":
            txt = raw.rstrip(b"\x81\x40") if raw.endswith(b"\x81\x40") else raw
            while txt.startswith(b"\x81\x40"):
                txt = txt[2:]
        out.append(
            {"i": k, "jp": txt.decode("cp932", "replace"), "raw": raw.hex(), "tail": e[w:].hex()}
        )
    return out


def read_speakers():
    b = bank_bytes(0x74)
    out = []
    for k in range(4):
        seg = b[0x330 + k * 64 : 0x330 + (k + 1) * 64]
        out.append({"i": k, "jp": seg.split(b"\x06")[0].decode("cp932")})
    return out


def read_chapter():
    """장 제목 필드 = 0x198 부터 「0x20 … 텍스트 … 0x20」 이 이어지는 만큼. ⚠ 32B 로 잡았다가 뒤 바이트를 덮었다."""
    b = bank_bytes(0x74)
    i = 0x198
    while b[i] == 0x20:
        i += 1
    j = i
    while b[j] != 0x20:
        j += 2
    k = j
    while b[k] == 0x20:
        k += 1
    seg = b[0x198:k]
    return [{"i": 0, "jp": seg.strip(b" ").decode("cp932"), "raw": seg.hex()}]


SPLIT_PTR = re.compile(rb"(?=\xa9(.)\x85(.)\xa9(.)\x85(.))", re.DOTALL)
LABELS = (0x15F6, 0x182F)
SYSMSG = (0x182F, 0x1F20)
TOK = re.compile(r"\{([0-9A-F]{2})\}")


def bank6d_refs() -> list[int]:
    """본 프로그램 코드가 분할 즉치(`LDA #lo/STA zp/LDA #hi/STA zp+1`)로 가리키는 뱅크 0x6D($8000~) 안 주소.

    코드가 어느 뱅크에 있든 값이 $95F0~$9F40 이면 0x6D 의 문구로 본다(실측 141곳, 전부 이 대역).
    ⚠ 다른 꼴의 참조(표·계산)는 못 본다 — 되읽기와 인게임 QA 가 잡는다.
    """
    main = common.track_data(MAIN_REL, 96)
    out = set()
    for m in SPLIT_PTR.finditer(main):
        lo, z1, hi, z2 = (m.group(k)[0] for k in (1, 2, 3, 4))
        if (
            z2 == z1 + 1 and z1 != 0xFA
        ):  # $FA/$FB 는 BIOS CD 인자 — 문구 포인터가 아니다(실측 $9D41/$9D46 가 글자 중간)
            w = lo | hi << 8
            if 0x8000 + LABELS[0] <= w < 0x8000 + SYSMSG[1]:
                out.add(w - 0x8000)
    # 시스템 메시지 영역 안의 스크립트 점프·호출(0F/10 lo hi)이 가리키는 공유 조각도 경계다
    b = bank_bytes(0x6D)
    for t in _tokens(b[SYSMSG[0] : SYSMSG[1]]):
        if isinstance(t, tuple) and t[1][0] in (0x0F, 0x10) and len(t[1]) == 3:
            w = t[1][1] | t[1][2] << 8
            if 0x8000 + SYSMSG[0] <= w < 0x8000 + SYSMSG[1]:
                out.add(w - 0x8000)
    return sorted(out)


OPLEN = {**M.TEXT_OPS, **M.OTHER_OPS}  # 씬 인터프리터 옵코드 길이(그 밖은 1)


def _tokens(seg: bytes) -> list:
    """바이트열 → [str | ("op", bytes)] — ≥0x24 는 2바이트 글자, 그 밖은 옵코드(피연산자 포함) 토큰."""
    out = []
    i = 0
    text = []
    while i < len(seg):
        b = seg[i]
        if (0x81 <= b <= 0x9F or 0xE0 <= b <= 0xEF) and i + 1 < len(seg):
            try:
                text.append(seg[i : i + 2].decode("cp932"))
                i += 2
                continue
            except UnicodeDecodeError:
                pass
        if text:
            out.append("".join(text))
            text = []
        ln = OPLEN.get(b, 1)
        out.append(("op", bytes(seg[i : i + ln])))
        i += ln
    if text:
        out.append("".join(text))
    return out


def op_text(t) -> str:
    return t if isinstance(t, str) else "{" + t[1].hex().upper() + "}"


def read_sysmsg():
    """참조 주소로 가른 시스템 메시지: [addr, 다음 참조) 가 한 단위. 앞뒤 옵코드는 도구가 보존한다."""
    b = bank_bytes(0x6D)
    refs = [r for r in bank6d_refs() if SYSMSG[0] <= r < SYSMSG[1]]
    bounds = refs + [SYSMSG[1]]
    out = []
    for a, nxt in itertools.pairwise(bounds):
        seg = b[a:nxt]
        # 뒤쪽 0/FF 패딩은 단위에서 뺀다
        core = seg.rstrip(b"\xff").rstrip(b"\0")
        toks = _tokens(core)
        first = next((i for i, t in enumerate(toks) if isinstance(t, str)), None)
        if first is None:
            continue
        last = max(i for i, t in enumerate(toks) if isinstance(t, str))
        lead = toks[:first]
        body = toks[first : last + 1]
        tail = toks[last + 1 :]
        jp = "".join(op_text(t) for t in body)
        out.append(
            {
                "addr": 0x8000 + a,
                "off": a,
                "room": nxt - a,
                "lead": [t[1].hex().upper() for t in lead],
                "tail": [t[1].hex().upper() for t in tail],
                "jp": jp,
                "key": M.jp_key(TOK.sub("", jp)),
            }
        )
    return out


# ─── 부팅·파일 선택 화면 ────────────────────────────────────────────────────
# `col row <SJIS…> 00` 레코드가 이어지고 `FF` 가 화면 끝. 코드가 **화면 머리를 절대주소로** 가리키므로
# 화면 총 길이를 지킨다 — 안에서 줄끼리 길이를 옮기는 건 자유다(레코드가 스스로 경계를 든다).
# ⚠ col·row 는 8px 타일 단위로 보인다(원본 최장 줄이 col2+19자 = 21칸). 폭 상한은 그 실측을 그대로 쓴다.
SCREENS = ((0x78, 0x01E3, 0x0330), (0x78, 0x049E, 0x0558))
SCREEN_COLS = 21  # col(칸) + 글자 수 상한 — 원본 최장 줄에서 잰 값


def read_screens():
    out = []
    for bank, lo, hi in SCREENS:
        b = bank_bytes(bank)
        i = lo
        while i < hi:
            start, lines = i, []
            while i < hi and b[i] != 0xFF:
                col, row = b[i], b[i + 1]
                j = b.index(0, i + 2)
                lines.append({"col": col, "row": row, "jp": b[i + 2 : j].decode("cp932")})
                i = j + 1
            if i < hi and b[i] == 0xFF:
                i += 1
            out.append(
                {
                    "key": f"{bank:02X}:{start:04X}",
                    "bank": bank,
                    "off": start,
                    "room": i - start,
                    "lines": lines,
                }
            )
    return out


def read_labels():
    """메뉴 라벨: 00 구분 + 코드 참조 주소에서도 가른다(『…逃げる 06 ＳＡＶＥ』처럼 06 뒤에 참조되는 라벨이 붙어 있다)."""
    b = bank_bytes(0x6D)
    refs = {r for r in bank6d_refs() if LABELS[0] <= r < LABELS[1]}
    out = []
    start = LABELS[0]
    i = LABELS[0]
    while i < LABELS[1]:
        if b[i] == 0 or (i in refs and i != start and b[i - 1] in (0x00, 0x06)):
            if i > start:
                seg = b[start:i]
                toks = _tokens(seg)
                out.append(
                    {
                        "addr": 0x8000 + start,
                        "off": start,
                        "room": len(seg),
                        "jp": "".join(op_text(t) for t in toks),
                    }
                )
            start = i + 1 if b[i] == 0 else i
        i += 1
    return out


def dump_all():
    out_dir = common.OUT_DIR / "sys"
    out_dir.mkdir(parents=True, exist_ok=True)
    fams = {
        "speakers": read_speakers(),
        "chapter": read_chapter(),
        "labels": read_labels(),
        "sysmsg": read_sysmsg(),
        "screens": read_screens(),
    }
    for k in FIXED:
        fams[k] = read_fixed(k)
    for k, v in fams.items():
        (out_dir / f"{k}.json").write_text(json.dumps(v, ensure_ascii=False, indent=1))
    return {k: len(v) for k, v in fams.items()}


if __name__ == "__main__":
    common.verify_originals()
    print(dump_all())
