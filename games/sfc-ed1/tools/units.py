"""sfc-ed1 번역 단위 — 스크립트 항목 열에서 **글자 런**(가나가 든 연속 글자)을 단위로 뽑는다.

단위 = 제어·사전 코드 사이의 연속 글자 바이트(개행 $CF · 공백 $10 포함). 재삽입은 항목 열을 그대로 두고
단위만 한글 항목 열로 갈아 끼우므로, 번역 표의 키는 **단위의 원문 바이트 sha1**(같은 문안은 한 번만
번역한다 — 논리 단위)이고, 자리마다의 물리 단위는 주소로 센다.

⚠ 출력(work/derived/units/)은 원문이다 — 커밋하지 않는다(루트 「저작권」). 커밋되는 번역 정본은 sha1 키만
든 textmap 이 된다(ps1-ed1+2 와 같은 방식).
"""

import argparse
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: I001  (common 보다 먼저)
import common
import script

KANA = set(range(0x11, 0x70)) | set(range(0x71, 0x80)) | set(range(0x90, 0xC3))
# 사전 뒤에 바로 붙는 조사(이름 뒤 조사 → 한글에선 받침에 따라 갈린다 — 런타임 훅 수요)
PARTICLES = {
    0x29: "の",
    0x2A: "は",
    0x16: "が",
    0x3D: "を",
    0x26: "に",
    0x24: "と",
    0x2D: "へ",
    0x9D: "で",
    0x33: "も",
}


def units_of(items: list[script.Item]):
    """(단위 시작 항목 인덱스, 끝 인덱스(열림), raw) — 가나가 하나라도 든 런만."""
    out = []
    i = 0
    n = len(items)
    while i < n:
        if items[i].kind == "char":
            j = i
            while j < n and items[j].kind == "char":
                j += 1
            raw = bytes(it.code for it in items[i:j])
            if any(c in KANA for c in raw):
                out.append((i, j, raw))
            i = j
        else:
            i += 1
    return out


def speaker_before(items: list[script.Item], i: int, res) -> str | None:
    """단위 앞쪽의 `E3 {사전} CF E1` 꼴 화자. 없으면 None."""
    k = i - 1
    while k >= 0 and k > i - 8:
        it = items[k]
        if (
            it.kind == "ctrl"
            and it.code == 0xE3
            and k + 3 < len(items)
            and items[k + 1].kind == "dict"
        ):
            d = items[k + 1]
            try:
                return text.decode(
                    res(d.code, d.args[0] & 0x7F if d.code == 0xD0 else d.args[0]), res
                )
            except (IndexError, ValueError):
                return None
        if it.kind == "ctrl" and it.code in (0xE0, 0xE4, 0xFF):
            break
        k -= 1
    return None


def extract(rom: bytes):
    s, e = common.snes2off(text.TEXT_START), common.snes2off(0x0BFE76)
    items = script.parse_region(rom, s, e, script.pointer_anchors(rom))
    res = text.resolver(rom)
    # 조각 번호 — END($E0/$E4) 마다 하나씩. 화자는 조각 안에서 이어진다(tm.py)
    seg_of = []
    seg = 0
    for it in items:
        seg_of.append(seg)
        if it.kind == "ctrl" and it.code in (0xE0, 0xE4):
            seg += 1
    units = []
    for i, _j, raw in units_of(items):
        units.append(
            {
                "id": hashlib.sha1(raw).hexdigest()[:12],
                "seg": seg_of[i],
                "addr": f"{common.off2snes(items[i].off):06X}",
                "len": len(raw),
                "speaker": speaker_before(items, i, res),
                "jp": text.decode(raw, res),
                "raw": raw.hex(),
            }
        )
    return items, units


def token_of(it: script.Item) -> str:
    """번역문 안에 남기는 자리표시자 — 사전은 `{D3:08}`, 제어는 `<FF>`/`<F0:20>`. 글자는 토큰이 아니다."""
    if it.kind == "dict":
        return f"{{{it.code:02X}:{it.args[0]:02X}}}"
    if it.kind == "subst":
        return f"{{{it.code:02X}}}"
    if it.args:
        return f"<{it.code:02X}:{it.args.hex().upper()}>"
    return f"<{it.code:02X}>"


LABEL = "<@>"  # 런 한복판에 떨어지는 분기 목표 자리 — 번역문이 같은 자리에 <@> 를 둔다(공유 꼬리 「…しますか?」)


def segments(items: list[script.Item], res) -> list[dict]:
    """END 사이 조각 = **번역 정본의 단위**. id 는 조각 원문 바이트의 sha1(12) — textmap 의 키다.
    `tokens` 는 글자가 아닌 항목(사전·치환·제어)을 순서대로 — 번역문은 이 토큰을 같은 순서로 품어야 한다.
    (비교·번역은 조각으로, 물리 배치는 항목 열로 — 재삽입기가 번역문의 토큰 위치대로 항목을 다시 짠다.)"""
    targets = {t for it in items for t in it.targets}
    out = []
    cur: list[script.Item] = []
    start = 0
    for k, it in enumerate(items):
        cur.append(it)
        if it.kind == "ctrl" and it.code in (0xE0, 0xE4):
            raw = b"".join(bytes([x.code]) + x.args for x in cur)
            toks = []
            jp_parts = []
            run: list[int] = []
            for j, x in enumerate(cur):
                mid = x.kind == "char" and x.off in targets and j > 0 and cur[j - 1].kind == "char"
                if mid:
                    jp_parts.append(text.decode(bytes(run), res))
                    run = []
                    jp_parts.append(LABEL)
                    toks.append(LABEL)
                if x.kind == "char":
                    run.append(x.code)
                else:
                    jp_parts.append(text.decode(bytes(run), res))
                    run = []
                    jp_parts.append(text.decode(bytes([x.code]) + x.args, res))
                    toks.append(token_of(x))
            jp_parts.append(text.decode(bytes(run), res))
            out.append(
                {
                    "id": hashlib.sha1(raw).hexdigest()[:12],
                    "seg": len(out),
                    "addr": f"{common.off2snes(items[start].off):06X}",
                    "n_items": len(cur),
                    "tokens": toks,
                    "jp": "".join(jp_parts),
                }
            )
            cur = []
            start = k + 1
    for s in out:
        m = re.search(r"<COLOR_C>\s*\{([^{}]+)\}", s["jp"][:60])
        s["speaker"] = m.group(1) if m else None
        s["kana_len"] = len(re.sub(r"<[^<>]*>|\s", "", s["jp"]))
    return out


def josa_inventory(items: list[script.Item]) -> collections.Counter:
    c = collections.Counter()
    for k, it in enumerate(items[:-1]):
        nx = items[k + 1]
        if it.kind in ("dict", "subst") and nx.kind == "char" and nx.code in PARTICLES:
            c[PARTICLES[nx.code]] += 1
    return c


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stats", action="store_true")
    ap.add_argument(
        "--dump", action="store_true", help="work/derived/units/units.json (원문 — 커밋 금지)"
    )
    a = ap.parse_args()
    rom = common.rom_bytes()
    items, units = extract(rom)
    logical = {u["id"]: u for u in units}
    chars_phys = sum(u["len"] for u in units)
    chars_logical = sum(u["len"] for u in logical.values())
    lens = collections.Counter(min(u["len"], 60) // 10 * 10 for u in units)
    josa = josa_inventory(items)
    print(
        f"물리 단위 {len(units):,} · 논리(고유) {len(logical):,} · 글자 바이트 물리 {chars_phys:,} · 논리 {chars_logical:,}"
    )
    print("길이 분포(10 단위):", dict(sorted(lens.items())))
    print(
        "화자 있는 단위:",
        sum(1 for u in units if u["speaker"]),
        "· 화자 종류:",
        len({u["speaker"] for u in units if u["speaker"]}),
    )
    print("사전/치환 뒤 조사:", dict(josa.most_common()), "합계", sum(josa.values()))
    if a.dump:
        d = common.OUT_DIR / "units"
        d.mkdir(parents=True, exist_ok=True)
        (d / "units.json").write_text(
            json.dumps(units, ensure_ascii=False, indent=0), encoding="utf-8"
        )
        segs = segments(items, text.resolver(rom))
        (d / "segments.json").write_text(
            json.dumps(segs, ensure_ascii=False, indent=0), encoding="utf-8"
        )
        print(
            "→",
            d / "units.json",
            "·",
            d / "segments.json",
            f"(조각 {len(segs):,} · 화자 {sum(1 for x in segs if x['speaker']):,})",
        )


if __name__ == "__main__":
    main()
