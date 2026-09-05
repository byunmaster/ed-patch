"""시스템 문구 되쓰기 — 정본(`script/sys/`) + 공용 사전(`shared/glossary`)을 본 프로그램 이미지에 **제자리**로.

정본:
    script/sys/names.json   {"items": {JP: KR}, "spells": …, "files": …, "speakers": …, "chapter": {JP: KR}}
                            — 사전(shared/glossary/eiyuu.json)이 정본이고 여기는 **덮어쓰기/보충**(폭 초과·미등재)
    script/sys/labels.json  {JP(토큰 포함 원문): KR(토큰 포함)}   메뉴 라벨
    script/sys/sysmsg.json  {열쇠: KR(토큰 포함)}                시스템 메시지 본문(앞뒤 옵코드는 도구가 보존)

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
    for v in _load("labels.json").values():
        chars |= {c for c in TOK.sub("", v) if font.needs_glyph(c)}
    for v in _load("sysmsg.json").get("messages", {}).values():
        chars |= {c for c in TOK.sub("", v) if font.needs_glyph(c)}
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


def apply(f, table, touched) -> dict:
    names = _load("names.json")
    gl = glossary()
    stats = {}
    errors: list[str] = []

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
            new = (
                S._pad_right_align(enc, w, pad)
                if fam != "files"
                else enc + pad * ((w - len(enc)) // 2)
            )
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
        if kr is None:
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
    if errors:
        raise SysError(
            "시스템 문구 " + str(len(errors)) + "건이 자리를 넘는다:\n  " + "\n  ".join(errors)
        )
    return stats
