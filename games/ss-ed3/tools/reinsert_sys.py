"""본체·시스템 문자열을 이미지에 써 넣는다 — **NUL 종료 문자열**.

    python3 games/ss-ed3/tools/reinsert_sys.py --check

대사(`reinsert.py`)와 규칙이 다르다. 여기는 표라서 **문자열마다 종료 NUL 이 있고 뒤에
패딩이 따라온다** — 그래서 원문보다 **조금 길어져도 된다**:

    예산 = 원문 바이트 + (뒤따르는 NUL 개수 − 1)     ← 종료자 1개는 반드시 남긴다

⚠ 늘리는 건 **패딩 안에서만**이다. 넘치면 다음 문자열의 첫 바이트를 먹고, 그 문자열을
   가리키는 포인터는 그대로라 **화면에만 엉뚱한 글자가 나온다.**
🔴 **포인터는 안 고친다** — 문자열 **시작 위치를 안 옮기기** 때문이다. 옮기기 시작하면
   `/0.BIN` 안의 BE32 132 곳을 전부 다시 계산해야 한다(`docs/status.md` 3절).

문안은 `script/system.json` — **자체 번역**이다. 고유명사 정본(`glossary_manual.json`)과
자리가 다르다: 정발 표기를 따르는 건 고유명사뿐이고, 대사·챕터는 우리가 옮긴다
(유저 확정 2026-08-24).
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import hangul_map as H
import strtab as S

SYSTEM = os.path.join(C.GAME_DIR, "script", "system.json")
# ⚠ **인명·지명 표는 안 고친다.** 그 이름들은 **대사 안에서** 쓰이므로 표만 고치면
#   대사와 갈린다 — 대사 쪽이 정본이다. 그래서 여기 오는 건 화면 문구뿐이다.


def table():
    """`{JP: KR}` — `script/system.json` 의 모든 갈래를 합친다(`_` 로 시작하는 키는 뺀다)."""
    if not os.path.exists(SYSTEM):
        return {}
    with open(SYSTEM, encoding="utf-8") as f:
        doc = json.load(f)
    out = {}
    for k, v in doc.items():
        if not k.startswith("_") and isinstance(v, dict):
            out.update(v)
    return out


def budget(data, s):
    """그 문자열이 쓸 수 있는 바이트 — 뒤따르는 NUL 패딩까지, 종료자 1개는 남긴다."""
    e = s["off"] + len(s["raw"])
    pad = 0
    while e + pad < len(data) and data[e + pad] == 0:
        pad += 1
    return len(s["raw"]) + max(0, pad - 1)


_LEAD = re.compile(r"^(?:<[0-9A-F]{2}>|[ \u3000])+")


def split_lead(text):
    """선행 서식(`<09>` · 들여쓰기 공백)과 몸통을 가른다.

    ⚠ 이게 없으면 **한 자리를 조용히 놓친다** — 최종장이 `<09>最終章…` 꼴이라 표의 키와
    안 맞았다(실측 7/8). 서식은 그대로 두고 몸통만 갈아 끼운다.
    """
    m = _LEAD.match(text)
    return (m.group(0), text[m.end() :]) if m else ("", text)


def patch(data, name, tbl):
    """`(새 bytes, 넣은 수, [(JP, 사유)])` — 파일 크기 불변."""
    out = bytearray(data)
    done, bad = 0, []
    for s in S.strings(data, S.LOAD_BASE.get(name)):
        lead, jp = split_lead(S.text_of(s["raw"]))
        kr = tbl.get(jp)
        if kr is None:
            continue
        raw = H.encode_kr(lead + kr)
        b = budget(data, s)
        if len(raw) > b:
            bad.append((jp, f"예산 {b}B 를 {len(raw) - b}B 넘는다"))
            continue
        # 남는 자리는 NUL 로 덮는다 — 원문 꼬리가 남으면 화면에 붙어 나온다
        out[s["off"] : s["off"] + len(s["raw"]) + 1] = raw + b"\x00" * (
            len(s["raw"]) + 1 - len(raw)
        )
        done += 1
    assert len(out) == len(data), (len(out), len(data))
    return bytes(out), done, bad


def main():
    tbl = table()
    if not tbl:
        print("⏭ 넣을 문안이 없다 (script/system.json)")
        return
    total = done = 0
    bad = []
    with C.open_disc(1) as d:
        for n, lba, size in d.files():
            if n != "/0.BIN":
                continue
            b = d.read_extent(lba, size)
            _, k, err = patch(b, n, tbl)
            done += k
            bad += err
    total = len(tbl)
    print(f"문안 {total}  넣음 {done}  실패 {len(bad)}")
    for jp, why in bad:
        print(f"  ❌ {jp} — {why}")
    if bad or done < total:
        if done < total and not bad:
            print(f"  ⚠ {total - done} 개는 `/0.BIN` 에서 그 문자열을 못 찾았다")
        raise SystemExit(1 if bad else 0)
    print("✅ 전부 들어간다")


if __name__ == "__main__":
    main()
