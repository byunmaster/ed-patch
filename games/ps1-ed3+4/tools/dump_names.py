"""실행파일 안의 **낱말 표**를 뽑는다 — 인물·아이템·마법·몬스터·지명·계급·의뢰.

맵 대사(`SC*.DAT`)만 덤프해 놓고 「대본을 다 안다」고 하면 안 된다. 화면에 나오는 낱말의
상당수는 **실행파일 안**에 종결 바이트(`0x0000`·`0xFFFF`)로 갈린 문자열로 앉아 있다.

⚠ **오프셋 표를 믿지 않는다.** 옆에 단조 증가하는 u16 표가 붙어 있지만, 그걸 오프셋으로 읽으면
   문자열 중간에 떨어지는 자리가 섞인다(실측). 재삽입에는 그 표가 필요하지만, **읽는 데는
   필요 없다** — 여기서는 블롭을 그냥 훑는다. 표 해독은 재삽입 단계의 몫이다.

⚠ 이건 **낱말**이다(아이템·지명·이름). 문장급 문안은 대본 쪽이고, 저작권 규율이 다르다
   (루트 CLAUDE.md 「저작권」 — 단어 수준 명칭은 코드에 둬도 되지만 문장은 안 된다).
   그래서 산출물은 `work/derived/` 로만 나가고 커밋하지 않는다.
"""

import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import textenc

EXE = {"ed3": "/ED3.EXE", "ed4": "/SLPS_015.40"}

# 구역 라벨 — **사람이 눈으로 붙인 판단**이라 여기(커밋되는 소스)에 둔다.
#   낱말(`person`·`place`·`monster`·`item`·`spell`·`rank`·`menu`)은 **고유명사 정본**의 소재고,
#   `text`(설명문·의뢰문·읽을거리)는 **문장급**이라 저작권 규율이 다르다(루트 CLAUDE.md).
#   `noise` 는 낱말처럼 걸리지만 뜻이 없는 자리(글꼴 표·조판 자료)다.
# ⚠ 시작 오프셋이 키다 — 원본이 바뀌면 못 찾고, 그때 조용히 넘어가지 않게 게이트가 운다.
REGIONS = {
    "ed3": {
        0x096E54: "person",
        0x096F18: "noise",
        0x09703E: "item",
        0x0970EE: "item",
        0x097446: "item",
        0x097574: "item",
        0x097686: "noise",
        0x097CC2: "spell",
        0x097DCC: "text",
        0x099776: "monster",
        0x099CCC: "noise",
        0x09B816: "place",
        0x09C04C: "noise",
        0x09D18C: "menu",
        0x09D830: "text",
        0x09DE96: "text",
        0x09E30E: "text",
        0x09E986: "text",
        0x09EDC6: "text",
        0x09F552: "text",
        0x09FC1E: "text",
        0x0A01EC: "text",
        0x0A109C: "menu",
        0x0A58AA: "noise",
    },
    "ed4": {
        0x000A28: "menu",
        0x06D3DE: "monster",
        0x06D7CC: "menu",
        0x06DFE4: "spell",
        0x06E2A2: "text",
        0x06E63E: "menu",
        0x06E860: "noise",
        0x06F208: "noise",
        0x06F49C: "noise",
        0x06FA02: "item",
        0x07002A: "item",
        0x07054E: "text",
        0x070592: "menu",
        0x070806: "text",
        0x0709A6: "text",
        0x072774: "noise",
        0x072798: "person",
        0x0730A8: "text",
        0x073362: "text",
        0x07363A: "text",
        0x07391A: "text",
        0x073CCA: "text",
        0x074062: "text",
        0x07432E: "text",
        0x0749D0: "text",
        0x074E98: "text",
        0x0753CA: "text",
        0x075E5E: "text",
        0x07602A: "text",
        0x0763A0: "text",
        0x076678: "text",
        0x076C26: "text",
        0x076D48: "menu",
        0x076EA2: "text",
        0x077046: "text",
        0x07727A: "rank",
        0x077500: "menu",
        0x077816: "place",
        0x077A5C: "place",
        0x079722: "noise",
    },
}
WORD_KINDS = ("person", "place", "monster", "item", "spell", "rank", "menu")


def is_term(w):
    """종결인가 — `0x0000` · `0xFFFF` · **최상위 비트가 선 코드**.

    🔴 표마다 종결이 다르다(실측 2026-09-03). 인물·아이템은 `0xFFFF`/`0x0000` 인데
       **마법·몬스터·지명은 `0x8002`** 다. `0x0000`·`0xFFFF` 만 보고 훑으면 그 세 표가
       **통째로 안 보인다** — 실제로 「실행파일에 마법·몬스터·지명이 없다」로 한 번 결론이
       났다. 대본 코드는 0x800 아래라 최상위 비트로 싸잡아도 안 잡아먹는다.
    """
    return w == 0xFFFF or w == 0x0000 or w & 0x8000


MAX_LEN = 24  # 이보다 길면 낱말 표가 아니다 (의뢰문은 예외라 --max 로 연다)
GAP = 64  # 이만큼 안에서 이어지면 한 구역


def strings(data, cm, max_len=MAX_LEN, newline=False):
    """[(바이트오프셋, 글자수, 문자열)] — 종결로 갈린 조각 중 **전부 아는 코드**인 것."""
    n = len(data) // 2
    w = struct.unpack(f"<{n}H", data[: n * 2])
    out, cur, start = [], [], 0
    for i, x in enumerate(w):
        if is_term(x):
            # ⚠ 0x0001 은 개행 제어다(주문 설명 안에 낀다, 2026-09-07) — `newline` 이면 글자로 친다.
            #    🔴 기본은 끈다 — 켜 두면 잡음 구역의 조각까지 문자열로 잡혀 「원본이 쓰는 코드」가
            #    불어나고, 글리프 자리 정본이 부딪힌다(check.sh 실측). `uitext` 만 켠다.
            if cur and len(cur) <= max_len and all(c in cm or (newline and c == 1) for c in cur):
                out.append((start * 2, len(cur), "".join(cm.get(c, "\n") for c in cur)))
            cur, start = [], i + 1
        else:
            if not cur:
                start = i
            cur.append(x)
    return out


def regions(strs, min_count=8, min_avg=2.0, min_long=0.4):
    """이웃한 문자열을 구역으로 묶는다 — **낱말답지 않은 구역은 버린다.**

    ⚠ 한 글자짜리가 늘어선 자리(글꼴 표·조판 자료)가 같은 규칙에 걸린다. 「평균 길이」와
      「3글자 이상 비율」로 거른다 — 밀도는 후보 좁히기지 판정이 아니다(체크리스트 5).
    """
    regs = []
    for off, ln, s in strs:
        if regs and off - regs[-1]["end"] < GAP:
            regs[-1]["end"] = off + ln * 2 + 2
            regs[-1]["items"].append(s)
            regs[-1]["offs"].append(off)
        else:
            regs.append({"start": off, "end": off + ln * 2 + 2, "items": [s], "offs": [off]})
    ok = []
    for r in regs:
        it = r["items"]
        if len(it) < min_count:
            continue
        avg = sum(len(s) for s in it) / len(it)
        long = sum(1 for s in it if len(s) >= 3) / len(it)
        if avg < min_avg or long < min_long:
            continue
        ok.append(r)
    return ok


def split(regs, labels):
    """라벨이 붙은 오프셋에서 구역을 **자른다**.

    표끼리 딱 붙어 있어 `GAP` 으로는 안 갈리는 자리가 있다 — 실측: ED3 의 지명 표 바로 뒤에
    조판 자료가, ED4 의 몬스터 표 뒤에 메모리카드 UI 가 붙어 한 구역으로 뭉쳤다.
    경계는 사람이 보고 정하는 것이라 `REGIONS` 의 키가 곧 칼자국이 된다.
    """
    out = []
    for r in regs:
        cuts = sorted(o for o in labels if r["start"] < o < r["end"])
        if not cuts:
            out.append(r)
            continue
        cur = {"start": r["start"], "end": r["start"], "items": [], "offs": []}
        for off, s in zip(r["offs"], r["items"], strict=True):
            if cuts and off >= cuts[0]:
                out.append(cur)
                cur = {"start": cuts.pop(0), "end": off, "items": [], "offs": []}
            cur["items"].append(s)
            cur["offs"].append(off)
            cur["end"] = off + len(s) * 2 + 2
        out.append(cur)
    return [r for r in out if r["items"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    ap.add_argument("--max", type=int, default=MAX_LEN)
    ap.add_argument("--show", type=int, default=8)
    ap.add_argument("--write", action="store_true", help="work/derived/<disc>/names.json 으로")
    a = ap.parse_args()
    common.verify_source(a.disc)
    cm = textenc.charmap(a.disc)
    lba, size = common.iso_files(a.disc)[EXE[a.disc]]
    data = common.read_lba(a.disc, lba, size)
    labels = REGIONS[a.disc]
    regs = split(regions(strings(data, cm, a.max)), labels)
    for r in regs:
        r["kind"] = labels.get(r["start"], "?")
    tot = sum(len(r["items"]) for r in regs)
    words = sum(len(r["items"]) for r in regs if r["kind"] in WORD_KINDS)
    print(f"{a.disc} {EXE[a.disc]}: 구역 {len(regs)} · 문자열 {tot:,} (그 중 낱말 {words:,})")
    for r in sorted(regs, key=lambda r: r["start"]):
        head = " · ".join(r["items"][: a.show])
        print(f"  0x{r['start']:06X} {r['kind']:8s} {len(r['items']):4d}개  {head[:80]}")
    unknown = [r for r in regs if r["kind"] == "?"]
    if unknown:
        print(f"  🔴 라벨이 없는 구역 {len(unknown)} — `REGIONS` 에 손으로 붙인다:")
        for r in unknown:
            print(f"       0x{r['start']:06X}  {' · '.join(r['items'][:6])[:70]}")
        return 1
    if a.write:
        p = os.path.join(common.OUT_DIR, a.disc, "names.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(
                {"disc": a.disc, "exe": EXE[a.disc], "regions": regs},
                f,
                ensure_ascii=False,
                indent=1,
            )
        print(f"→ {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
