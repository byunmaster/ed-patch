#!/usr/bin/env python3
"""말투 경보 둘(래칫) — 번역 정본 줄에서 **사람이 한 번 더 볼 자리**를 센다.

    python3 tools/check_register_alarms.py            # 기준선보다 늘면 실패
    python3 tools/check_register_alarms.py --show     # 목록
    python3 tools/check_register_alarms.py --freeze   # 기준선을 내린다(올리지는 못한다)
    python3 tools/check_register_alarms.py --selftest # 양성 대조(경보가 실제로 우는지)

경보 ① **반말 줄 속 「-시-」 섞임** — 줄 끝이 반말(~다·~야·~어·~지·~군·~네·~거든·~게)인데 한 줄 안에 듣는 이를 높이는
  「-시-」(~시는데·~시지·~세요·~셨)이 섞였다. 마스터 11-12 말투 정렬(규칙 4-7·4-8·4-9)은 등급을 **원문 말투로** 정한다 — 반말 줄에 높임이
  남으면 변환이 덜 된 것이다. 제3자 높임(「왕께서 …하시니」)은 맞는 말이라 「께서」·「님」이 같은 줄에 있으면 거른다.
✱ 경보 ② **원문 대비 길이 급감** — 한국어 글자 수가 일본어 원문 글자 수의 35% 에도 못 미친다(원문 10자 이상). 누락·잘림의 냄새다
  (한국어는 보통 원문보다 길다). 효과음·감탄처럼 짧아도 되는 줄은 원문이 짧아 걸리지 않는다.
둘 다 **판정이 아니라 경보**다 — 기준선(`register_alarms_baseline.json`)보다 늘어난 줄만 실패, 하나씩 눈으로 보고 고치면 `--freeze`.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

BASELINE = os.path.join(common.ROOT, "register_alarms_baseline.json")

# 줄 끝이 반말 — 어미 뒤 부호까지 걷고 본다
# 해라·해체 반말 끝만 — 네·군·구먼·나·세(하게·하오체)는 「잘 오셨네」처럼 듣는 이 높임이 맞는 자리라 뺀다
_PLAIN_END = re.compile(r"(다|야|어|아|지|걸|거든|까|냐|니|잖아|는데|건데|란다|단다|느냐)$")
_POLITE_END = re.compile(r"(요|니다|니까|습니까|세요|시오|십시오)$")
# 듣는 이를 높이는 -시-
_HONOR = re.compile(r"(?<!마)(?<!성가)(?<!쑤)(?<!모)(?<!이)(시[는면던네군고지며니어]|시$|세요|셔서|셨|께서는?\s*주)")
_THIRD = re.compile(r"(께서|님[이은의도]?|왕|폐하|전하|각하)")  # 제3자 높임 — 같은 줄에 있으면 거른다
# 낱말 속 「시」(메시지·지시·혹시 …)는 높임이 아니다 — 판별 전에 걷는다
_WORD = re.compile(r"(메시지|지시|혹시|시장|시작|시간|시험|시내|시선|시설)")
# 눈으로 본 제3자 높임(11-13, 4-16 ③) — 말하는 이·듣는 이가 아니라 이야기 속 다른 사람을 높인다. 원문 말미 「おられた·なされ·〜てくれた」 등
THIRD = {
    "AT0110#146", "FT1000#178", "FT3001#137", "FT3005#157", "MR2100#33", "MT2200#24", "MT4000#147", "NT0005#49",
    "FT7010#12", "ST0100#25", "ST0101#21", "ST0201#173", "ST0201#174", "FT8000#70", "FT8000#117", "FT3008#116",
    "AT2203#14", "CT1001#55", "OT1000#121", "RC1000#53", "FT2101#98", "MT9200#152",
    "FT0102#68", "CT0202#85",  # 11-15 4-21 ⑤ — 원문 높임 낱말(お歳·お話)이 든 문장은 -시- 유지
}
_SENT = re.compile(r"[^.!?…]+[.!?…]*")


def _strip(s):
    return re.sub(r"[\s.!?…~〜,「」『』()]+$", "", s)


def honor_in_plain(kr):
    """반말로 끝나는 문장 안에 듣는 이 높임 「-시-」가 섞였나."""
    flat = kr.replace("\f", " ").replace("\n", " ")
    for m in _SENT.finditer(flat):
        s = m.group(0).strip()
        core = _WORD.sub("", _strip(s))
        if len(core) < 4 or _POLITE_END.search(core) or not _PLAIN_END.search(core):
            continue
        if _HONOR.search(core) and not _THIRD.search(core):
            return s
    return None


def length_drop(jp, kr):
    j = re.sub(r"[\s　・…！？。、「」『』（）()]+", "", jp)
    k = re.sub(r"[\s.!?…~〜,「」『』()�]+", "", re.sub("�[0-9a-f]{3,4}", "", kr))
    if len(j) < 10 or not k:  # 빈 조각은 앞 줄에 이어 붙인 자리(빈 쪽 해소 2-17) — 미번역은 check_jp_left 가 본다
        return None
    return (len(j), len(k)) if len(k) * 20 < len(j) * 7 else None


def scan(disc="ed3"):
    import check_typeset_rules as ctr

    a, b = [], []
    for where, jp, kr, _floor in ctr.scene_rows(disc):
        h = honor_in_plain(kr)
        if h and where.split("\\")[-1].replace(".BIN", "") not in THIRD:
            a.append((where, h))
        d = length_drop(jp, kr)
        if d:
            b.append((where, f"원문 {d[0]}자 → {d[1]}자 : {kr[:24]!r}"))
    return a, b


def selftest():
    ok = True
    pos = honor_in_plain("자네가 가시는데 같이 가겠지.")
    neg = honor_in_plain("왕께서 가시니 따라가지.")
    ok &= bool(pos) and neg is None
    ok &= honor_in_plain("괜찮으세요?") is None  # 해요 줄은 대상이 아니다
    ok &= length_drop("\u3042" * 12, "응.") is not None
    ok &= honor_in_plain("그건 말씀하시는데 어쩌지.") is not None
    ok &= length_drop("\u3042" * 12, "이것은 아주 긴 일본어 문장이다.") is None
    ok &= length_drop("\u3042" * 3, "네.") is None  # 짧은 원문은 대상 밖
    print("양성 대조", "통과" if ok else "🔴 실패")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", default="ed3")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if selftest():
        return 1
    common.verify_source(a.disc)
    h, d = scan(a.disc)
    cur = {"honor_in_plain": len(h), "length_drop": len(d)}
    base = json.load(open(BASELINE, encoding="utf-8")) if os.path.exists(BASELINE) else None
    print(f"{a.disc}: 말투 경보 — 반말 줄 속 -시- {len(h)} · 원문 대비 길이 급감 {len(d)}", end="")
    print(f" (기준선 {base['honor_in_plain']} · {base['length_drop']})" if base else " (기준선 없음)")
    if a.show:
        for tag, rows in (("-시-", h), ("길이", d)):
            for w, t in rows:
                print(f"  [{tag}] {w} {t}")
    if a.freeze:
        if base and any(cur[k] > base[k] for k in cur):
            print("  🔴 --freeze 는 올리지 못한다 — 늘어난 줄을 고친다")
            return 1
        json.dump(cur, open(BASELINE, "w", encoding="utf-8"), indent=1)
        print("  기준선 갱신")
        return 0
    if base is None:
        print("  🔴 기준선이 없다 — 한 번 눈으로 보고 --freeze")
        return 1
    bad = [k for k in cur if cur[k] > base[k]]
    for k in bad:
        print(f"  🔴 {k} 가 기준선보다 늘었다({cur[k]} > {base[k]}) — --show 로 늘어난 줄을 본다")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
