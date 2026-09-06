"""시스템 문구 되쓰기 — 정본(`script/sys/`) + 공용 사전(`shared/glossary`)을 본 프로그램 이미지에 **제자리**로.

정본:
    script/sys/names.json   {"items": {JP: KR}, "spells": …, "files": …, "speakers": …, "chapter": {JP: KR}}
                            — 사전(shared/glossary/eiyuu.json)이 정본이고 여기는 **덮어쓰기/보충**(폭 초과·미등재)
    script/sys/labels.json  {JP(토큰 포함 원문): KR(토큰 포함)}   메뉴 라벨
    script/sys/sysmsg.json  {열쇠: KR(토큰 포함)}                시스템 메시지 본문(앞뒤 옵코드는 도구가 보존)
    script/sys/screens.json {"뱅크:오프셋": [줄…]}              부팅·파일 선택 화면(줄 수는 원본 그대로)

규칙(2026-09-05): 주소를 안 옮긴다.
    고정폭 표 — 폭 안에서 원래 패딩 방식으로(아이템·주문 0x20 오른쪽 정렬 · 파일 지명 전각 공백)
    라벨 — 원래 길이 안, 남는 자리 00
    시스템 메시지 — 앞뒤 옵코드 보존, 본문 교체. 짧아졌는데 원문이 다음 단위로 흘러가면 `0F 다음주소` 로 잇는다
    (씬 인터프리터·단순 렌더러 둘 다 <0x20 에서 멈추므로 안전). 넘치면 빌드 실패 — 문안을 줄인다.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import common
import font
import sysstrings as S

from shared.disc import mode1

SYS_DIR = common.GAME_DIR / "script" / "sys"
TOK = re.compile(r"\{([0-9A-Fa-f]+)\}")
TERMINAL_OPS = {
    0x00,
    0x03,
    0x06,
    0x07,
    0x0A,
    0x0D,
}  # 0A·0D 도 단위 끝에서만 나온다(실측) — 되돌아가는 옵코드로 본다


class SysError(Exception):
    pass


def glossary() -> dict[str, str]:
    g = json.loads((common.ROOT / "shared" / "glossary" / "eiyuu.json").read_text())
    flat = {}

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str):
                    flat[k] = v
                else:
                    walk(v)

    walk(g)
    return flat


def _load(name):
    p = SYS_DIR / name
    return json.loads(p.read_text()) if p.exists() else {}


def all_glyph_chars() -> set[str]:
    chars = set()
    names = _load("names.json")
    gl = glossary()
    for fam in S.FIXED:
        for r in S.read_fixed(fam):
            kr = names.get(fam, {}).get(r["jp"], gl.get(r["jp"]))
            if kr:
                chars |= {c for c in kr if font.needs_glyph(c)}
    for fam, reader in (("speakers", S.read_speakers), ("chapter", S.read_chapter)):
        for r in reader():
            kr = names.get(fam, {}).get(r["jp"], gl.get(r["jp"]))
            if kr:
                chars |= {c for c in kr if font.needs_glyph(c)}
    for k, v in _load("labels.json").items():
        if k != "_doc" and v is not None:  # null = 원본 유지로 판정한 것
            chars |= {c for c in TOK.sub("", v) if font.needs_glyph(c)}
    for v in _load("sysmsg.json").get("messages", {}).values():
        chars |= {c for c in TOK.sub("", v) if font.needs_glyph(c)}
    for k, v in _load("screens.json").items():
        if not k.startswith("_"):
            chars |= {c for line in v for c in line if font.needs_glyph(c)}
    for k, v in _load("extras.json").items():
        if not k.startswith("_"):
            chars |= {c for t in v for c in t if font.needs_glyph(c)}
    return chars


def encode_tokens(text: str, table) -> bytes:
    """`{XX}` 토큰은 그 바이트로, 나머지는 font.encode."""
    out = bytearray()
    pos = 0
    for m in TOK.finditer(text):
        out += font.encode(text[pos : m.start()], table)
        out += bytes.fromhex(m.group(1))
        pos = m.end()
    out += font.encode(text[pos:], table)
    return bytes(out)


def _write(f, bank, off, data, expect, label, touched):
    rel, o = S.bank_rel(bank, off)
    lba = common.T2_SECTOR + rel
    mode1.write_at(f, lba, common.USER * 2, o, data, label=label, expect=expect)
    for i in range((o + len(data) - 1) // common.USER + 1):
        touched.append((lba + i, 1))


def check_keys(errors: list[str]) -> dict[str, int]:
    """🔴 **정본에 있는데 아무 데도 안 맞는 열쇠**를 잡는다.

    문안을 써 놨는데 열쇠가 한 글자 어긋나면 **조용히 아무 일도 안 일어난다** — 빌드도 게이트도
    초록불인데 화면만 일본어다. 실측(2026-09-06): `labels.json` 셋이 그 상태였다
    (`はい` ↔ 읽히는 꼴 `{04}{02}はい` · `{09}{02}` ↔ `{0902}` · 「プレイ時間」 뒤 `：　：` 누락).
    ⚠ 반대쪽(원문에 있는데 정본에 없는 것)은 **할 일**이지 실패가 아니다 — 여기선 안 본다.
    """
    seen = {}
    labels = _load("labels.json")
    lb = S.read_labels()
    keys = {r["jp"] for r in lb} | {f"@{r['addr']:04X}" for r in lb}
    stray = [k for k in labels if k != "_doc" and k not in keys]
    seen["labels"] = len(stray)
    errors += [f"labels.json 열쇠가 아무 라벨과도 안 맞는다: {k!r}" for k in stray]

    msgs = _load("sysmsg.json").get("messages", {})
    mk = {r["key"] for r in S.read_sysmsg()}
    stray = [k for k in msgs if k not in mk]
    seen["sysmsg"] = len(stray)
    errors += [f"sysmsg.json 열쇠가 아무 메시지와도 안 맞는다: {k!r}" for k in stray]

    scr = _load("screens.json")
    sk = {c["key"] for c in S.read_screens()}
    stray = [k for k in scr if not k.startswith("_") and k not in sk]
    seen["screens"] = len(stray)
    errors += [f"screens.json 열쇠가 아무 화면과도 안 맞는다: {k!r}" for k in stray]

    ex = _load("extras.json")
    ek = {g["key"] for g in S.read_extras()}
    stray = [k for k in ex if not k.startswith("_") and k not in ek]
    seen["extras"] = len(stray)
    errors += [f"extras.json 열쇠가 아무 덩이와도 안 맞는다: {k!r}" for k in stray]

    names = _load("names.json")
    for fam in ("items", "spells", "files", "places"):
        jp = {r["jp"] for r in S.read_fixed(fam)}
        stray = [k for k in names.get(fam, {}) if k not in jp]
        seen[fam] = len(stray)
        errors += [f"names.json[{fam}] 열쇠가 표에 없다: {k!r}" for k in stray]
    return seen


def apply(f, table, touched) -> dict:
    names = _load("names.json")
    gl = glossary()
    stats = {}
    errors: list[str] = []
    check_keys(errors)  # 정본에 써 놓고 안 붙는 열쇠부터 잡는다

    def kr_of(fam, jp):
        return names.get(fam, {}).get(jp, gl.get(jp))

    # 고정폭 표
    for fam, (bank, base, stride, w, _n, pad, _tail) in S.FIXED.items():
        b = S.bank_bytes(bank)
        cnt = 0
        for r in S.read_fixed(fam):
            kr = kr_of(fam, r["jp"])
            if not kr or not r["jp"]:
                continue
            enc = font.encode(kr, table)
            if len(enc) > w:
                errors.append(f"{fam} 「{r['jp']}」→「{kr}」 {len(enc)}B > {w}B")
                continue
            if fam == "files":
                new = enc + pad * ((w - len(enc)) // 2)
            elif fam == "places":
                # HUD 이름칸: 「이름 06」 + 00 패딩. 12B 를 꽉 채우면 06 을 안 쓴다
                # (렌더러 `$92A0` 가 06 까지 스캔하고, 없으면 12B 를 끝으로 본다)
                new = enc if len(enc) == w else enc + b"\x06" + b"\0" * (w - len(enc) - 1)
            else:
                new = S._pad_right_align(enc, w, pad)
            off = base + r["i"] * stride
            _write(f, bank, off, new, b[off : off + w], f"{fam}[{r['i']}]", touched)
            cnt += 1
        stats[fam] = cnt
    # 공용 화자(64B 슬롯) · 장 제목(32B, 0x20 패딩)
    b74 = S.bank_bytes(0x74)
    cnt = 0
    for r in S.read_speakers():
        kr = kr_of("speakers", r["jp"])
        if kr:
            enc = font.encode(kr, table) + b"\x06"
            # 🔴 64B 슬롯은 **캐릭터 레코드**다(이름 16B + 능력치 48B). 이름 칸 16B 만 쓴다 —
            #    슬롯을 통째로 썼다가 능력치가 0 이 돼 HUD 에 파티원 넷이 떴다(2026-09-05).
            if len(enc) > 16:
                raise SysError(f"speaker {kr} 가 이름 칸 16B 를 넘는다")
            off = 0x330 + r["i"] * 64
            _write(
                f,
                0x74,
                off,
                enc + b"\0" * (16 - len(enc)),
                b74[off : off + 16],
                f"speaker[{r['i']}]",
                touched,
            )
            cnt += 1
    stats["speakers"] = cnt
    for r in S.read_chapter():
        kr = kr_of("chapter", r["jp"])
        if kr:
            enc = font.encode(kr, table)
            raw = bytes.fromhex(r["raw"])
            if len(enc) > len(raw):
                raise SysError("chapter 제목이 32B 를 넘는다")
            lead = (len(raw) - len(enc)) // 2
            new = b" " * lead + enc + b" " * (len(raw) - len(enc) - lead)
            _write(f, 0x74, 0x198, new, raw, "chapter", touched)
            stats["chapter"] = 1
    # 라벨
    labels = _load("labels.json")
    b6d = S.bank_bytes(0x6D)
    cnt = 0
    for r in S.read_labels():
        kr = labels.get(
            f"@{r['addr']:04X}", labels.get(r["jp"])
        )  # 같은 JP 가 뜻이 다를 때 주소로 덮는다
        if kr is None:  # 미판정이거나 **원본 유지로 판정**(null) — 둘 다 안 건드린다
            continue
        enc = encode_tokens(kr, table)
        if len(enc) > r["room"]:
            errors.append(f"label 「{r['jp']}」→「{kr}」 {len(enc)}B > {r['room']}B")
            continue
        # ⚠ 00 으로 채우면 안 된다 — 상태 화면은 라벨을 00 개수로 세어 찾는다(실측: 지혜 뒤 라벨이 비었다).
        #   전각 공백으로 채운다(왼쪽 정렬이라 안 보인다). 남는 길이가 홀수면 문안을 다시 맞춘다.
        rest = r["room"] - len(enc)
        if rest % 2:
            errors.append(
                f"label 「{r['jp']}」→「{kr}」 남는 {rest}B 가 홀수 — 전각 공백으로 못 채운다"
            )
            continue
        new = enc + b"\x81\x40" * (rest // 2)
        _write(
            f,
            0x6D,
            r["off"],
            new,
            b6d[r["off"] : r["off"] + r["room"]],
            f"label {r['addr']:04X}",
            touched,
        )
        cnt += 1
    stats["labels"] = cnt
    # 시스템 메시지
    msgs = _load("sysmsg.json").get("messages", {})
    cnt = 0
    for r in S.read_sysmsg():
        kr = msgs.get(r["key"])
        if kr is None:
            continue
        lead = b"".join(bytes.fromhex(t) for t in r["lead"])
        tail = b"".join(bytes.fromhex(t) for t in r["tail"])
        body = encode_tokens(kr, table)
        new = lead + body + tail
        orig = b6d[r["off"] : r["off"] + r["room"]]
        core_len = len(orig.rstrip(b"\xff").rstrip(b"\0"))
        # 원문이 방을 꽉 채웠고(패딩 00 없음) 꼬리가 종료·점프가 아니면 다음 단위로 흘러가는 조각이다
        flows_on = core_len == r["room"] and not (
            tail and (tail[-1] in TERMINAL_OPS or tail[-3:-2] == b"\x0f")
        )
        if len(new) < core_len and flows_on:
            nxt = 0x8000 + r["off"] + core_len
            new += bytes([0x0F, nxt & 0xFF, nxt >> 8])
        if len(new) > r["room"]:
            errors.append(
                f"sysmsg {r['addr']:04X} 「{r['jp']}」→「{kr}」 {len(new)}B > {r['room']}B{' (0F 이어쓰기 3B 포함)' if flows_on else ''}"
            )
            continue
        new += b"\0" * (r["room"] - len(new))
        _write(f, 0x6D, r["off"], new, orig, f"sysmsg {r['addr']:04X}", touched)
        cnt += 1
    stats["sysmsg"] = cnt
    # 부팅·파일 선택 화면 — 화면 총 길이를 지킨다(코드가 화면 머리를 절대주소로 가리킨다).
    # 줄 수·col·row 는 원본 그대로 쓰고, 남는 자리는 마지막 줄 뒤에 전각 공백으로 채운다.
    screens = _load("screens.json")
    cnt = 0
    for sc in S.read_screens():
        kr = screens.get(sc["key"])
        if kr is None:
            continue
        if len(kr) != len(sc["lines"]):
            errors.append(f"screen {sc['key']} 줄 수 {len(kr)} ≠ 원본 {len(sc['lines'])}")
            continue
        enc = [font.encode(t, table) for t in kr]
        for ln, t, e in zip(sc["lines"], kr, enc, strict=True):
            if ln["col"] + len(e) // 2 > S.SCREEN_COLS:
                errors.append(
                    f"screen {sc['key']} col{ln['col']} 「{t}」 {ln['col'] + len(e) // 2}칸 > {S.SCREEN_COLS}칸"
                )
        total = sum(3 + len(e) for e in enc) + 1
        if total > sc["room"]:
            errors.append(f"screen {sc['key']} {total}B > {sc['room']}B")
            continue
        enc[-1] += b"\x81\x40" * ((sc["room"] - total) // 2)
        if (sc["room"] - total) % 2:
            errors.append(
                f"screen {sc['key']} 남는 {sc['room'] - total}B 가 홀수 — 전각 공백으로 못 채운다"
            )
            continue
        new = b"".join(
            bytes([ln["col"], ln["row"]]) + e + b"\0"
            for ln, e in zip(sc["lines"], enc, strict=True)
        )
        new += b"\xff"
        assert len(new) == sc["room"], sc["key"]
        b78 = S.bank_bytes(sc["bank"])
        _write(
            f,
            sc["bank"],
            sc["off"],
            new,
            b78[sc["off"] : sc["off"] + sc["room"]],
            f"screen {sc['key']}",
            touched,
        )
        cnt += 1
    stats["screens"] = cnt
    # 오마케 모듈(사운드 테스트 · 도감 메뉴) — rel 458~459 의 00 종단 목록.
    # 🔴 포인터 표가 없고 **00 을 세어** 찾으므로 항목 수를 지키고, 남는 자리는 00 으로 채운다
    #    (전각 공백으로 채우면 마지막 항목 뒤에 빈칸이 붙어 보인다).
    extras = _load("extras.json")
    d458 = common.track_data(S.EXTRAS_REL, 2)
    cnt = 0
    for g in S.read_extras():
        items = extras.get(g["key"])
        if items is None:
            continue
        if len(items) != len(g["items"]):
            errors.append(f"extras[{g['key']}] 항목 {len(items)} ≠ 원본 {len(g['items'])}")
            continue
        blob = b"".join(font.encode(t, table) + b"\0" for t in items)
        if len(blob) > g["room"]:
            errors.append(f"extras[{g['key']}] {len(blob)}B > {g['room']}B")
            continue
        blob += b"\0" * (g["room"] - len(blob))
        lba = common.T2_SECTOR + S.EXTRAS_REL
        mode1.write_at(
            f,
            lba,
            common.USER * 2,
            g["off"],
            blob,
            label=f"extras {g['key']}",
            expect=d458[g["off"] : g["off"] + g["room"]],
        )
        for i in range(g["off"] // common.USER, (g["off"] + g["room"] - 1) // common.USER + 1):
            touched.append((lba + i, 1))
        cnt += 1
    stats["extras"] = cnt
    if errors:
        raise SysError(
            "시스템 문구 " + str(len(errors)) + "건이 자리를 넘는다:\n  " + "\n  ".join(errors)
        )
    return stats
