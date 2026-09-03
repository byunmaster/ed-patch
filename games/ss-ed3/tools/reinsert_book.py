"""`BOOK*.BIN` 재삽입 — 문단 번역을 **줄로 다시 나눠** 제자리에 되끼운다.

🔴 **줄 수를 원문과 같게** 맞춰야 한다. 줄 하나가 독립 문자열이고 오프셋이 고정이라,
하나라도 남거나 모자라면 그 뒤가 통째로 어긋난다(설명문에서 배운 것과 같다).
모자라면 **빈 줄을 끝에 붙이고**, 넘치면 그 문단은 **원문을 그대로 둔다**(문안을 줄여야 한다).

⚠ 줄마다 **제 칸을 지킨다** — 남는 자리는 전각 공백, 넘치면 못 넣는다.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import book as B
import common as C
import hangul_map as H
import strtab as S

SCRIPT_DIR = os.path.join(C.GAME_DIR, "script", "book")


def table(stem):
    p = os.path.join(SCRIPT_DIR, f"{stem}.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def patch(data, stem, tbl, hg):
    """`(새 bytes, 넣은 문단 수, [문제])` — 파일 크기 불변."""
    if not tbl:
        return data, 0, []
    # ⚠ **덤프가 아니라 파일에서 읽는다** — 덤프 JSON 에는 `raw` 가 없어 칸 길이를 모른다.
    #   `book.load_lines` 는 눈으로 훑는 용도고, 되끼울 땐 원본 바이트가 필요하다.
    lines = [
        dict(s, text=S.text_of(s["raw"]))
        for s in S.strings(data, S.load_base(f"/SYSTEM/{stem}.BIN"))
    ]
    if not lines:
        return data, 0, []
    out = bytearray(data)
    done, bad, squeezed, cut = 0, [], 0, 0
    for pi, (at, rows) in enumerate(B.paragraphs(lines)):
        kr = tbl.get(str(pi))
        if kr is None:
            continue
        widths = [len(x["raw"]) for x in lines[at : at + len(rows)]]
        #   🔴 **전각으로 바꾸고 넣는다** — 반각이 하나만 끼어도 책 화면은 그 뒤를 통째로
        #     뭉갠다(`book.FULLWIDTH` 의 설명). 부호에 붙는 공백은 여기서 뺀다.
        base = B.tidy_spaces(B.to_fullwidth(kr))
        kr2, dropped = B.fit_spaces(base, widths)
        if not B.split_to(kr2, widths)[1] and "|" in base:
            #   ⚠ `|` 는 **옛 어절 배분의 낭비를 우회하려던 표식**이라, 글자 단위로 채우는
            #     지금은 오히려 줄을 버린다. 안 들어가면 하드 브레이크를 풀고 다시 채운다.
            kr2, dropped = B.fit_spaces(B.tidy_spaces(base.replace("|", "　")), widths)
        squeezed += bool(dropped)
        new, ok = B.split_to(kr2, widths)
        #   🟡 **낱말이 갈린 줄을 센다** — 실패가 아니라 「문안을 줄여야 하는 자리」의 크기다.
        #     조판으로 풀 수 있는 몫은 `book.split_to` 의 DP 가 이미 가져갔다(362→279).
        cut += B.word_cuts(kr2, new)
        if not ok:
            bad.append(f"{stem}[{pi}]: 원문 {sum(widths)}칸에 안 들어간다 — {kr[:24]}…")
            continue
        for k, s in enumerate(lines[at : at + len(rows)]):
            raw = H.encode_kr(new[k], hg)
            room = len(s["raw"])
            if len(raw) > room:
                bad.append(f"{stem}[{pi}] {k}번째 줄: {len(raw)}B > {room}B")
                break
            raw += "　".encode("shift_jis") * ((room - len(raw)) // 2)
            #   ⚠ 여백이 홀수로 남으면 **반각 한 칸**이 끼어 그 줄이 깨진다 — 못 넘어간다.
            if (room - len(raw)) % 2:
                bad.append(f"{stem}[{pi}] {k}번째 줄: 칸이 홀수로 남는다 ({room}B)")
                break
            #   ⚠ **두 바이트씩 걷어 선두 바이트만 본다** — SJIS 트레일 바이트는 `0x40`
            #     처럼 0x80 미만인 게 정상이라, 바이트를 통째로 보면 멀쩡한 줄을 퇴짜 놓는다.
            if any(
                not (0x81 <= raw[x] <= 0x9F or 0xE0 <= raw[x] <= 0xEF) for x in range(0, room, 2)
            ):
                bad.append(f"{stem}[{pi}] {k}번째 줄: 전각이 아닌 자리가 있다")
                break
            out[s["off"] : s["off"] + room] = raw
        else:
            done += 1
    assert len(out) == len(data), (len(out), len(data))
    return bytes(out), done, bad, squeezed, cut


def main():
    hg = H.load()
    total = nbad = nsq = ncut = 0
    with C.open_disc(1) as d:
        for name, lba, size in d.files():
            if not (name.startswith("/SYSTEM/BOOK") and name.endswith(".BIN")):
                continue
            stem = os.path.basename(name)[:-4]
            tbl = table(stem)
            if not tbl:
                continue
            b = d.read_extent(lba, size)
            _new, n, bad, sq, cut = patch(b, stem, tbl, hg)
            total += n
            nbad += len(bad)
            nsq += sq
            ncut += cut
            print(f"  {stem}: 문단 {n} 넣음" + (f" · 문제 {len(bad)}" if bad else ""))
            for e in bad[:4]:
                print(f"     ❌ {e}")
    print(f"\n문단 {total} 넣음 · 띄어쓰기를 줄인 문단 {nsq} · 문제 {nbad}")
    #   🟡 경고이지 실패가 아니다 — 조판이 아니라 **문안 길이**가 만드는 자국이다.
    #   ⚠ 0 일 때까지 노란불로 두면 「늘 노란불」이 되어 아무도 안 본다.
    if ncut:
        print(f"🟡 낱말이 갈린 줄 {ncut} — 문안을 줄여야 없어진다(조판 몫은 DP 가 이미 가져갔다)")
    else:
        print("✅ 낱말이 갈린 줄 없음")


if __name__ == "__main__":
    main()
