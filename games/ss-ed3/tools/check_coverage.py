"""화면에 나가는 글 출처 대장 + 구운 이미지의 일본어 잔존 검사.

    python3 games/ss-ed3/tools/check_coverage.py           # 출처별 표
    python3 games/ss-ed3/tools/check_coverage.py --check   # 잔존이 늘었으면 1 로 죽는다 (게이트)

🔴 **왜 있나** — ps1-ed3 에서 월드맵 지명 목록이 사전에 있는데도 일본어로 남았고, 이름 검사와 화면 일본어 게이트가 **둘 다 그 출처를 분모에 안 넣어** 못 잡았다(10-08).
   검사기는 「읽는 출처」 안에서만 초록이다. ⇒ 두 가지를 한 번에 본다:
   ① 출처별 표 — 이름 검사 어댑터(`names_corpus.pairs()`)에 든 줄 수 / 안 든 출처와 그 까닭.
   ② **구운 이미지를 원본 옆에 놓고 가나(히라가나가 낀 3 자↑) 연속을 센다**. 출처 목록과 무관하게 「일본어가 남았나」를 직접 본다 —
      파일마다 받아들인 상한은 `script/coverage_accept.json`. 한자는 못 센다(한글 코드와 SJIS 한자 영역이 겹쳐 전부 잡음이다).
"""

import argparse
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

ACCEPT = os.path.join(C.GAME_DIR, "script", "coverage_accept.json")
#   히라가나 둘 이상이 낀 가나 3 자↑ — 가타카나만인 연속은 글리프 데이터와 구분이 안 된다
_KANA = re.compile(rb"(?:\x82[\x9f-\xf1]|\x83[\x40-\x96]|\x81[\x5b\x45\x41\x42]){3,}")
_HIRA = re.compile(rb"(?:\x82[\x9f-\xf1]){2,}")
_SKIP = (".FON", ".CPK", ".DAT")  # 글꼴·영상·사운드 — 데이터라 잡음이다


def kana_runs(b):
    return [m.group() for m in _KANA.finditer(b) if _HIRA.search(m.group())]


def sources():
    """`[(출처, 줄 수, 이름검사 O/X, 일본어게이트, 비고)]`."""
    import names_corpus as N

    cnt = collections.Counter()
    tr = collections.Counter()
    for where, _jp, kr, _kind in N.pairs():
        key = where.split("#")[0] if where.startswith(("MAP", "BOOK")) else ":".join(where.split(":")[:2])
        key = "MAP" if key.startswith("MAP") else "BOOK" if key.startswith("BOOK") else key.split("#")[0]
        cnt[key] += 1
        tr[key] += kr is not None
    rows = [
        ("맵 대사·이름 칸·선택지 (MAP*.BIN)", cnt["MAP"], tr["MAP"], "O", "check_no_loss 대사"),
        ("읽을거리 문단 (BOOK*.BIN)", cnt["BOOK"], tr["BOOK"], "O", "이 파일의 가나 잔존(②)"),
        ("시스템 표 (0.BIN·RLTPRG·BLACK)", sum(v for k, v in cnt.items() if k.startswith("SYS")), sum(v for k, v in tr.items() if k.startswith("SYS")), "O", "check_sys_coverage · check_no_loss 시스템"),
        ("PARAM 이름 (아이템·적·마법)", sum(v for k, v in cnt.items() if k.startswith("PARAM:") and "desc" not in k), sum(v for k, v in tr.items() if k.startswith("PARAM:") and "desc" not in k), "O", "②만 (이름 칸은 가타카나라 못 센다 — 이름검사의 None 이 그 몫)"),
        ("PARAM 설명문 (desc_item·desc_spell)", cnt["PARAM:desc_item"] + cnt["PARAM:desc_spell"], tr["PARAM:desc_item"] + tr["PARAM:desc_spell"], "O", "check_no_loss 설명"),
        ("HP 창 이름판 (BATTLE.BIN 그림)", cnt["BATTLE:plate"], tr["BATTLE:plate"], "O", "그림 — 가나 검사 밖(사전에서 그린다)"),
    ]
    out = []
    for name, n, t, o, note in rows:
        out.append((name, n, f"{t}/{n}", o, note))
    return out


def extra_sources():
    """어댑터 밖 출처 — (이름, 줄 수, 까닭)."""
    sj = os.path.join(C.GAME_DIR, "script")

    def load(n):
        with open(os.path.join(sj, n), encoding="utf-8") as f:
            return json.load(f)

    voice = sum(len(v) for k, v in load("voice.json").items() if k.startswith("V") and isinstance(v, dict))
    movie = sum(len(v) for k, v in load("movie.json").items() if k.startswith("M") and isinstance(v, list))
    cred = len(load("voice_credits.json").get("subs", []))
    covers = sum(len(v) for k, v in load("book/covers.json").items() if k.startswith("BOOK"))
    return [
        ("음성 자막 (voice.json)", voice, "원문이 받아쓰기(work/review, 커밋 금지)라 쌍을 못 만든다"),
        ("V20 크레딧 자막 (voice_credits.json)", cred, "같음"),
        ("무비 하드섭 자막 (movie.json)", movie, "같음 — 영상에 구워서 이미지 가나 검사로도 안 보인다"),
        ("책 표지 그림 (covers.json)", covers, "그림 — 글자 검사 밖"),
        ("타이틀 그림 (LDDATA.PAK)", 1, "그림 — 글자 검사 밖"),
    ]


def dict_keys():
    """사전 열쇠(고유명사 원문 + 별칭) 중 SJIS 로 쓸 수 있는 2 자↑ — `{열쇠: bytes}`."""
    sys.path.insert(0, os.path.join(C.ROOT, "shared"))
    import canon as CN

    d = CN.nouns("ed3")
    keys = {k for t in d["categories"].values() for k in t} | set(d.get("_aliases", {}))
    out = {}
    for k in keys:
        try:
            out[k] = k.encode("shift_jis")
        except UnicodeEncodeError:
            continue
    return {k: v for k, v in out.items() if len(k) >= 2}


def residual():
    """`[(디스크, 파일, 원본 수, 구움 수, 예)]` — 구운 이미지에 가나가 남은 파일."""
    import build
    import check_build_discs as B

    out = []
    keys = dict_keys()
    for disc in (1, 2):
        img = build.out_paths(disc)[0]
        if not os.path.exists(img):
            print(f"  ⏭ disc{disc} 이미지 없음 — 건너뛴다")
            continue
        new = {n: (lba, size) for n, lba, size, *_ in build.patched(disc)}
        with C.open_disc(disc) as d:
            for n, lba, size in d.files():
                if size == 0 or n.endswith(_SKIP):
                    continue
                o = kana_runs(d.read_extent(lba, size))
                nl, ns = new.get(n, (lba, size))
                got = B.read_extent(img, nl, ns)
                r = kana_runs(got)
                #   🔴 사전 열쇠 정확 검색 — 출처 목록을 손으로 열거하면 숨은 표를 놓친다(md 실측: 목적지 표 10칸)
                hit = {k: got.count(e) for k, e in keys.items() if e in got}
                if r or hit:
                    ex = " / ".join(x.decode("shift_jis", "replace") for x in r[:3])
                    if hit:
                        ex += "  [사전 열쇠] " + ", ".join(f"{k}×{c}" for k, c in sorted(hit.items())[:6])
                    out.append((disc, n, len(o), len(r), sum(hit.values()), ex))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    print("  출처 | 줄 수 | 번역/전체 | 이름검사 | 일본어 확인")
    for name, n, tr, o, note in sources():
        print(f"  {name} | {n} | {tr} | {o} | {note}")
    print("  ── 어댑터 밖")
    for name, n, why in extra_sources():
        print(f"  {name} | {n} | X | {why}")
    with open(ACCEPT, encoding="utf-8") as f:
        ok = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    bad = []
    print("  ── 구운 이미지의 가나 잔존")
    for disc, n, no, nr, nk, ex in residual():
        cap, kcap = ok.get(n, {}).get("max", 0), ok.get(n, {}).get("keys", 0)
        good = nr <= cap and nk <= kcap
        print(f"  {'✅' if good else '❌'} disc{disc} {n}: 가나 {no} → {nr} (≤{cap}) · 사전 열쇠 {nk} (≤{kcap})  {ex}")
        if not good:
            bad.append(n)
    if bad and a.check:
        print(f"\n🔴 일본어가 남은 파일 {len(set(bad))} — 번역을 넣거나 `script/coverage_accept.json` 에 사유와 함께 받아들인다")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
