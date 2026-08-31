"""본체·시스템 문자열을 덤프한다 — `work/derived/sys_jp/`.

    python3 games/ss-ed3/tools/dump_sys.py            # 덤프 + 라운드트립 확인
    python3 games/ss-ed3/tools/dump_sys.py --check    # 확인만
    python3 games/ss-ed3/tools/dump_sys.py --disc 2

대상은 `MAP*.BIN` **밖**이다 — 본체 `/0.BIN` · `/SYSTEM/*` · `/EVT/*` · `/BTL/*`.
매체(`/CPK` 무비 · `/SAP` 음성 · `/SND` 음악)는 **일부러 뺀다**: 압축 바이트가 SJIS 로
디코드돼 마커가 잔뜩 잡히지만 전부 오탐이다(실측 `/CPK/M08.CPK` 하나에서만 266건).

🔴 **파일 단위로 한 번 더 거른다 — 가나 비율.** 조각 하나하나를 아무리 잘 걸러도, 그래픽
   파일은 「한자처럼 보이는 바이트」를 통째로 낸다. 실측으로 완전히 갈린다:

     /SYSTEM  가나비율 중앙 **0.97** ← 진짜 텍스트(도감 · 몬스터명 · 파라미터)
     /EVT     최대 **0.20**          ← 전부 그래픽
     /BTL     최대 **0.00**          ← 전부 그래픽
     /0.BIN   0.52 + 포인터 확인 132 ← 본체

   그래서 **가나비율 ≥ 0.3 이거나 포인터가 확인된 파일**만 받는다. 이 문턱으로 파일 107 개
   (문자열 1,630)를 버렸고 그중 진짜 텍스트는 없었다 — 버려진 `/SYSTEM` 14 개도 전부
   `FACE*`·`BATTLE.BIN`·`*.PAK` 같은 그래픽이다.
   ⚠ 곁다리 관찰: 버려진 것의 대부분이 **`.FON` 확장자**다. `MAP*.FON` 과 같은 함정으로,
   이 게임에서 `.FON` 은 폰트가 아니라 그래픽이다(진짜 폰트는 `/SYSTEM/{ASCII,KANJI12}.FON`
   둘뿐이다).

🔴 **라운드트립을 매번 본다** — 되끼우면 원본과 바이트 동일해야 한다.

⚠ 산출물은 원문을 담는다 — `work/derived` 는 gitignore 다. 커밋하지 않는다.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import mapfile as M
import strtab as S

OUT = os.path.join(C.OUT_DIR, "sys_jp")

# 매체 — 텍스트가 없고 오탐만 낸다
MEDIA = ("/CPK/", "/SAP/", "/SND/")

MIN_KANA_RATIO = 0.3  # 이 아래는 그래픽으로 본다 (위 🔴 참조)


def is_text_source(st):
    """이 파일이 텍스트 소재인가 — 가나 비율 또는 포인터 확인."""
    if not st:
        return False
    if any(x["by"] == "ptr" for x in st):
        return True
    return sum(1 for x in st if M.has_kana(x["raw"])) / len(st) >= MIN_KANA_RATIO


def targets(d):
    return [
        (n, l, s)
        for n, l, s in d.files()
        if not n.startswith("/MAP/") and not any(k in n for k in MEDIA)
    ]


def dump_one(b, name):
    st = S.strings(b, S.load_base(name))
    return {
        "size": len(b),
        "load_base": S.load_base(name),
        "strings": [{"off": x["off"], "by": x["by"], "text": S.text_of(x["raw"])} for x in st],
    }, st


def rebuild(b, st):
    """덤프한 문자열을 제자리에 도로 써 넣는다 — 원본과 같아야 한다."""
    out = bytearray(b)
    for x in st:
        raw = S.encode_text(S.text_of(x["raw"]))
        if len(raw) != len(x["raw"]):
            raise AssertionError(f"길이가 변했다 @{x['off']:#x}")
        out[x["off"] : x["off"] + len(raw)] = raw
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", type=int, default=1, choices=C.DISCS)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    if not a.check:
        os.makedirs(OUT, exist_ok=True)
    nf = ns = nb = nptr = 0
    fails = []
    with C.open_disc(a.disc) as d:
        for n, l, s in targets(d):
            b = d.read_extent(l, s)
            rec, st = dump_one(b, n)
            if not is_text_source(st):
                continue
            if rebuild(b, st) != b:
                fails.append((n, "라운드트립 불일치"))
                continue
            nf += 1
            ns += len(st)
            nb += sum(len(x["raw"]) for x in st)
            nptr += sum(1 for x in st if x["by"] == "ptr")
            if not a.check:
                stem = n.strip("/").replace("/", "_").rsplit(".", 1)[0]
                with open(os.path.join(OUT, f"{stem}.json"), "w", encoding="utf-8") as f:
                    json.dump(rec, f, ensure_ascii=False, indent=1)

    print(f"disc{a.disc}  파일 {nf}  문자열 {ns:,} ({nb:,}B)  포인터확인 {nptr:,}")
    if fails:
        print(f"❌ 실패 {len(fails)}")
        for n, why in fails[:10]:
            print(f"   {n} — {why}")
        raise SystemExit(1)
    print("✅ 전 파일 라운드트립 통과" + ("" if a.check else f" → {OUT}"))


if __name__ == "__main__":
    main()
