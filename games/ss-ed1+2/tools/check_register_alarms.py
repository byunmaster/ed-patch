"""말투·길이 경보 둘 (마스터 11-13 밤샘 지시, 규칙 4-16 ③).

① 반말 줄에 듣는 이 높임 「-시-」 섞임 — 반말 끝(나?·냐?·는가?·려나·겠는데·군.)인데 어간에 「-시-」가 든 줄.
   제3자 높임은 괜찮다(원문이 그 사람을 높인 것) — 그래서 **듣는 이를 가리키는 꼴만** 잡는다: 「모르시나」·「가지시겠는데」처럼
   의문·추측 끝에 바로 붙은 「-시-」. 0 이어야 한다.
② 원문 대비 길이 급감 — 원문 가나·한자 글자 수가 12 이상인데 우리 글자 수(제어 코드·공백 뺀 것)가 원문의 0.28 배 미만이면
   번역이 통째로 빠졌을 수 있다(누락 경보). 알려진 짧은 의역은 `LENGTH_OK` 에 자리로 둔다. 0 이어야 한다.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "shared"))

import check_text

CTL = re.compile(r"%c|%s|%d|\{n\}|\{p\}|\x1b|\x08|[-]|\s")
# 반말 끝에 바로 붙은 듣는 이 높임: 「…시나?」「…시냐?」「…시는가?」「…시겠는데」「…시려나」「…시군.」
SI = re.compile(r"(?:모르|가지|계|하|주|드|보|아|알|오|가|받|들|쓰|입|먹|타|사)시(?:나|냐|는가|겠는데|려나|겠나|겠어)[?？]?(?:[.!…]|$)")
LENGTH_OK = set()  # (파일, 오프셋 16진) — 의역이 짧은 줄을 판정 뒤 여기 둔다


def jp_len(s):
    return len(re.findall(r"[぀-ヿ一-鿿]", s))


def si_hits(text):
    out = []
    for seg in re.split(r"[\n]|(?<=[.!?…])\s+", CTL.sub(" ", text)):
        seg = seg.strip()
        if SI.search(seg) and not re.search(r"(습니다|십시오|니까|세요|해요|어요|아요|에요|예요|지요|죠|군요|네요)[.!?…~ ]*$", seg):
            out.append(seg)
    return out


def selftest():
    assert si_hits("그 사람 일은 모르시나?") and si_hits("못 가지시겠는데."), "양성 대조 실패"
    assert not si_hits("할아버지는 모르십니까?") and not si_hits("그분은 가셨어."), "음성 대조 실패"
    assert jp_len("あいうえおかきくけこさし") == 12


def main():
    selftest()
    rows = check_text.corpus()
    si, short = [], []
    for path, off, jp, kr in rows:
        name = os.path.basename(path)[:-4]
        for h in si_hits(kr):
            si.append((name, hex(off), h))
        j, k = jp_len(jp), len(CTL.sub("", kr))
        if j >= 12 and k < j * 0.28 and (name, hex(off)) not in LENGTH_OK:
            short.append((name, hex(off), j, k, kr.replace("\n", "/")[:40]))
    print(f"  반말 줄 듣는 이 「-시-」 — {len(si)}곳 (0 이어야 한다) · 원문 대비 길이 급감 — {len(short)}곳 (0 이어야 한다)")
    for s in si[:10]:
        print(f"    ❌ 「-시-」 {s[0]}:{s[1]} {s[2]}")
    for s in short[:10]:
        print(f"    ❌ 길이 {s[0]}:{s[1]} 원문 {s[2]}자 → {s[3]}자: {s[4]}")
    return 1 if (si or short) else 0


if __name__ == "__main__":
    sys.exit(main())
