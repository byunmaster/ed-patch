#!/usr/bin/env python3
"""**시스템·행동 로그의 문체가 원문 등급과 같은가**(번역 규칙 4-17 — 마스터 11-15 「전투로그 등도 원문방향으로」).

런타임 주입 표지(`\\x1a` 이름 · `\\x17` 아이템)를 쓰는 블록이 곧 시스템·행동 로그다(화자 이름표가 없다). 이 부류는
**원문 끝이 「ました/ます」면 존댓말(「열었습니다」), 「た」면 평서**다. 어긋나면 실패 — 핫픽스 덮개(`hotfix/script`)를 겹친
문안으로 잰다(제품 정본 v1.2.0 은 잠겨 있다).

🔴 경위 — 09-03 「원문 정중이니 정중」 → 10-03 「로그는 전부 평어」(마스터) → **11-15 「원문 방향」**(4-17 확장)으로 되돌았다.
10-03 판정이 만든 「평어 통일」 검사는 이 검사의 앞 판이다(정중이 남으면 실패 — 방향이 반대였다).

읽을 수 없는 원문(이름 플레이트 조각이 섞인 블록)은 건너뛰고 몇 건인지 알린다.

  python3 tools/check_log_register.py
"""

import json
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("LOCK_BYPASS", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = Path(__file__).resolve().parents[1]
INJECT = ("\x1a", "\x17")  # 런타임 주입 표지 = 시스템·행동 로그
POLITE_KR = re.compile(r"(습니다|십시오|세요|십니다)[.!?…]?$")
PLAIN_KR = re.compile(r"(었다|았다|했다|였다|렸다|쳤다|된다|한다|이다|냈다)[.!?…]?$")


SYS_JP = re.compile(r"宝箱|手に入れ|渡し|買い|売り|取り上げ|受け取|もらい|拾い|見つけ|あきらめ|設置|セット|閉め|開け|解放|勝利|敗れ|覚え|習得|仲間|装備")  # 시스템·행동 로그 낱말(주입 표지가 없는 지문 포함)


def _jp_sents(j):
    b = re.sub(r"%[cdsx]", "", j.replace("\x00", "").replace("\n", ""))
    return [x.strip("　 ･…") for x in re.split(r"[。！？!?]", b) if x.strip("　 ･…")]


def jp_class(sent):
    if re.search(r"(ました|ません|ませんでした|ます|です|でした)$", sent):
        return "P"
    if re.search(r"(た|だ|る|い|う|く|ぐ|す|つ|ぬ|ぶ|む)$", sent) and not re.search(r"ご|お[一-龥]|ください|ませ|なさ", sent):
        return "L"
    return None


def jp_tail(j):
    ss = _jp_sents(j)
    return jp_class(ss[-1]) if ss else None


def kr_class(sent):
    t = re.sub(r"\{[pn]\}|%c|\ue003|\x1b|\x1a|\x17", "", sent).rstrip().rstrip("}pn{").rstrip()
    if POLITE_KR.search(t):
        return "P"
    if PLAIN_KR.search(t):
        return "L"
    m = re.search(r"([\uac00-\ud7a3])다[.!?…]*$", t)
    if m and (ord(m.group(1)) - 0xAC00) % 28 == 20:  # ㅆ 받침 + 다 = 과거 평서(샀다·냈다·잃었다 …)
        return "L"
    return None


def kr_tail(t):
    return kr_class(t)


def _kr_sents(t):
    parts = re.split(r"(?<=[.!?…])(?:\s+|\{p\}|\{n\}|\n)", t)
    return [x for x in parts if x and x.strip()]


def scan(track):
    from check_window_nl import SCN_COUNT, raws_of

    bad, total, unread = [], 0, 0
    for n in range(1, SCN_COUNT[track] + 1):
        scn = f"{track}SCN{n}"
        base = json.loads((ROOT / "script" / f"{scn}.json").read_text(encoding="utf-8"))
        hp = ROOT / "hotfix" / "script" / f"{scn}.json"
        hot = json.loads(hp.read_text(encoding="utf-8")) if hp.exists() else {}
        raws = raws_of(scn)
        for k, v in base.items():
            if not isinstance(v, dict) or not k.isdigit():
                continue
            e = hot.get(k)
            t = e["t"] if isinstance(e, dict) and "t" in e else (v.get("t") or "")
            sx = e.get("s") if isinstance(e, dict) and "s" in e else v.get("s")
            raw = raws.get(int(k))
            j = raw.decode("cp932", errors="replace") if raw else ""
            # 범위: 런타임 주입 표지 블록 + **화자 없고** 시스템·행동 낱말이 든 지문 블록(표지 없는 「상자에는 ◯가 있었다」·「샀다」류)
            is_log = any(m in t for m in INJECT) or (not sx and SYS_JP.search(j) and not re.match(r"%c[^%]+%c\n", j))
            if not is_log:
                continue
            total += 1
            if not raw or any(c in j for c in "\x14\x16\x17\x18\x19") or ("%s" not in j and "%c" not in j and not SYS_JP.search(j)):
                unread += 1
                continue
            js, ks = _jp_sents(j), _kr_sents(t)
            pairs = list(zip(js, ks)) if len(js) == len(ks) else [(js[-1], ks[-1])] if js and ks else []
            for js_, ks_ in pairs:
                a, b = jp_class(js_), kr_class(ks_)
                if a and b and a != b:
                    bad.append((scn, k, a, b, ks_[:40]))
                    break
    return total, unread, bad


def main():
    t1, u1, bad1 = scan("ED1")
    t2, u2, bad2 = scan("ED2")
    bad = bad1 + bad2
    if bad:
        print(f"  ❌ 로그 부류 {len(bad)}곳이 원문 등급과 다르다(4-17 — 원문 ました→존댓말 · 원문 た→평서)")
        for s, k, a, b, t in bad[:20]:
            print(f"       {s}:{k}  원문 {a} · 우리 {b}  {t!r}")
    else:
        print(f"  ✅ 로그 부류 문체 = 원문 등급 — ED1 {t1} · ED2 {t2}블록(읽을 수 없는 원문 {u1 + u2} 제외)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
