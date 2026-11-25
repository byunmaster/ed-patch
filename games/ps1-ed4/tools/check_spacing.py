"""변수 삽입 앞뒤 띄어쓰기 게이트 — 엔진이 끼워 넣는 칸(이름·아이템·수 삽입 연산 `05`~`08`) **바로 앞 조각이 공백 없이 한글로 끝나는** 곳을 센다.

    python3 tools/check_spacing.py

배경(pce-ed1 10-29 「보물상자」): 「…가득 차서」+[아이템 이름]+「을(를) 포기했다」 처럼 조각이 낱말 끝에서 끊기고 뒤에 이름이 바로 붙으면 「차서스톤」으로 나간다.
번역 정본 조각은 앞뒤 공백을 안 적으면 그대로 붙는다(끼움 토막은 조각마다 제 줄을 지켜 공백도 그대로 — `typeset.rigid_segments`).
연산이 **아예 없는** 이음(두 조각이 같은 줄에 바로 붙는다)도 같다 — 둘 다 공백이 없으면 위반, 합쳐 24칸을 넘으면 앞 조각을 24칸까지 채워 뒷 조각이 줄 머리에서 시작해야 한다(안 그러면 낱말 속에서 접힌다).
판정: 두 출력 사이 연산이 **삽입 연산(`05`~`08`)뿐**(줄·쪽 연산이 끼면 새 줄이라 공백 불필요)이고, 뒷 조각이 삽입의 이음(조사 표지·조사·공백·부호)으로 시작하며,
앞 조각(조판 결과)이 공백·여는 부호가 아닌 글자로 끝나면 위반. 뒷 조각이 이음이 아니라 낱말로 바로 시작하는 곳(삽입 앞에 빈칸이 있어도 뒤에 붙는 말)도 따로 센다.
조사는 토큰 뒤에 붙는 게 맞다 — 어절 경계(토큰 **앞** 공백)만 본다. 양성 대조(`selftest`)가 가짜 위반을 잡는지 먼저 확인한다.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", ".."))
import build
import script_kr
import typeset
from shared.text import josa_rt

INSERT_OPS = {5, 6, 7, 8}
OPEN = set("「『(（[‘“")
JOSA_HEAD = re.compile(
    r"^(은|는|이|가|을|를|의|에|와|과|도|로|으로|만|께|한테|에게|이다|이야|이에요|입니다|라|야|여|아|조차|까지|부터|처럼|보다|마저|이라|이여|씨|님|들|\(이\)|\(가\)|\(을\))"
)


def is_join(b):
    """뒷 조각이 삽입 토큰에 이어 붙는 꼴(조사 표지·조사·공백·부호·빔)인가."""
    if not b:
        return True
    c = b[0]
    return c in josa_rt.MARKER_CHARS or c == " " or not ("가" <= c <= "힣") or bool(JOSA_HEAD.match(b))


def judge(a_text, b_text):
    """('앞' | '뒤' | None) — 삽입 앞(A 끝) 공백 누락 · 삽입 뒤(B 첫머리) 낱말이 맞붙음."""
    if a_text and a_text[-1] != " " and a_text[-1] not in OPEN and is_join(b_text):
        return "앞"
    if b_text and not is_join(b_text) and not (a_text or "").endswith(" "):
        return None  # 앞 조각이 비었거나 이름 목록의 항목 — 삽입 뒤 이음이 아니다
    return None


def violations():
    members = build.identity_gate({})
    rows_all = script_kr.load_all()
    bad, gaps, adj = [], 0, 0
    for key, rows in rows_all.items():
        mem = members[key]
        texts, _ = script_kr.page_plan(mem, rows)
        for si, st in enumerate(typeset.message_streams(mem)):
            pr = st["prints"]
            for (qa, a), (qb, b) in zip(pr, pr[1:]):
                ops = set(typeset._gap_ops(mem, qa, qb))
                if a == b:
                    continue
                if not ops:  # 연산이 없는 이음 — 두 조각이 같은 줄에 바로 붙는다
                    ta = texts.get(a, rows.get(a, {}).get("kr") or "")
                    tb = texts.get(b, rows.get(b, {}).get("kr") or "")
                    if ta.strip() and tb.strip():
                        adj += 1
                        if ta[-1] != " " and tb[0] != " ":
                            bad.append((key, si, a, b, ta[-12:], tb[:10]))
                        elif len(ta) < typeset.COLS and len(ta.rstrip()) + 1 + len(tb.rstrip()) > typeset.COLS:
                            # 합치면 한 줄(24칸)을 넘는다 — 엔진이 낱말 속에서 접는다. 앞 조각을 24칸까지 채워 뒷 조각을 다음 줄 머리에 앉힌다
                            bad.append((key, si, a, b, ta[-12:], tb[:10] + " (24칸 채움 필요)"))
                    continue
                if not ops <= INSERT_OPS:
                    continue
                ta = texts.get(a, rows.get(a, {}).get("kr") or "")
                tb = texts.get(b, rows.get(b, {}).get("kr") or "")
                if not ta.strip() and not tb.strip():
                    continue
                gaps += 1
                if judge(ta.rstrip("\n"), tb):
                    bad.append((key, si, a, b, ta[-12:], tb[:10]))
    return (gaps, adj), bad


ORPHAN = re.compile(r"(?<![을를이가은는과와])\((이|가|을|를|은|는|으)\)")


def orphans():
    """조사 병기가 런타임 훅이 안 푸는 꼴로 남은 조각 — 「[이름](이)에요」 의 「(이)」 는 표지로 안 바뀌어 화면에 괄호째 나간다(10-30 전수 촬영 실측)."""
    return [(k[1], i, v["kr"]) for k, rows in script_kr.load_all().items() for i, v in rows.items() if ORPHAN.search(v["kr"] or "")]


def selftest():
    """양성 대조 — 가짜 조각 쌍에서 위반을 잡고 정상은 통과시키나."""
    mk = next(iter(josa_rt.MARKER_CHARS))
    assert judge("소지품이 가득 차서", mk + " 포기했다.") == "앞"
    assert judge("소지품이 가득 차서 ", mk + " 포기했다.") is None
    assert judge("이쪽에서 ", "구입해 주세요.") is None
    assert judge("", mk + "가") is None
    assert ORPHAN.search("(이)에요.") and not ORPHAN.search("을(를) 건넸다.")


def main():
    selftest()
    (gaps, adj), bad = violations()
    print(f"삽입 연산 이음 {gaps} · 연산 없는 같은 줄 이음 {adj} · 공백 누락·낱말 속 접힘 {len(bad)} (양성 대조 ✓)")
    for key, si, a, b, ta, tb in bad[:40]:
        print(f"  ✗ {key[1]} s{si} 조각 {a}→{b}: …{ta!r} + [삽입] + {tb!r}")
    orp = orphans()
    print(f"조사 병기 잔존(괄호째 나가는 「(이)」 꼴) {len(orp)}")
    for mb, i, kr in orp[:20]:
        print(f"  ✗ {mb} 조각 {i}: {kr!r}")
    return 1 if bad or orp else 0


if __name__ == "__main__":
    sys.exit(main())
