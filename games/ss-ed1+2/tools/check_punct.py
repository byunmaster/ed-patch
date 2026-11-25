"""문장부호 형태 게이트 (마스터 11-13 「게임별 문장부호 검토」, 규칙 1-1·1-3·1-7·2-12).

대사 전 문안(`check_text.corpus()`)에서 규칙이 금지한 꼴을 센다 — 0 이어야 한다.
  ASCII 점 연속(`...`) · 일본식 가운뎃점(`・・・`·`･･･`) · 한 줄 안에서 띄워 쓴 `… …`(원문 「· · ·」 오역) ·
  전각 `！？`·`⁉‼⁈` · `～.` · `?.`·`!.` · `….`·`.…` · `?…`·`!…`(순서는 `…?`·`…!`).
「……」처럼 …를 붙여 여러 개 쓴 것은 원문 점 수가 많을 때 정상(round(n/3))이라 안 친다.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "shared"))

import check_text

CTL = re.compile(r"%c|%s|%d|\{p\}|[\x00-\x09\x0b-\x1f]")
RULES = [
    ("ASCII 점 연속", re.compile(r"\.{2,}")),
    ("가운뎃점 연속", re.compile(r"[・･]{2,}")),
    ("띄운 … …", re.compile(r"…[ \t]+…")),
    ("전각 ！？·⁉‼⁈", re.compile(r"[！？⁉‼⁈]")),
    ("～.", re.compile(r"～\.")),
    ("?. !.", re.compile(r"[?!]\.")),
    ("….", re.compile(r"…\.")),
    (".…", re.compile(r"\.…")),
    ("?… !… 순서", re.compile(r"[?!]…")),
]


def hits(text):
    out = []
    for line in CTL.sub(" ", text).split("\n"):
        for name, rx in RULES:
            if rx.search(line):
                out.append(name)
    return out


TILDE = re.compile(r"[～〜~]")


def tilde_over(jp, kr):
    """원문 물결표 개수 이하여야 한다(마스터 11-13 「원본대로 한 개씩」). 원문에 ～ 가 없으면 장음 「ー」 개수까지 허용."""
    a, b = len(TILDE.findall(jp)), len(TILDE.findall(kr))
    return b > (a if a else jp.count("ー"))


# 알려진 미해결 — (원문 첫 6자 대신 키 없이 한 줄 요약) 칸 때문에 못 되살린 곳. 「칸 문제는 기술 먼저」라 목록에 남기고 관리자에게 보고한다.


def dropped(jp, kr):
    """번역이 원문 부호(！ ？ ～ …)를 뺐나(마스터 11-13 「원문 부호는 빼지말자」) — 부호별 번역 수 < 원문 수. 원문 `･` 점 n개는 `…` round(n/3)개.
    예외: `、` 만 한국식 규칙(2-13)이라 안 센다 — `。` 는 문장 수가 줄면(합병 의역) 경보."""
    J, K = re.sub(r"%[csd]", "", jp), re.sub(r"%[csd]", "", kr)
    out = []
    if len(re.findall("[!！]", J)) > K.count("!"):
        out.append("!")
    if len(re.findall("[?？]", J)) > K.count("?"):
        out.append("?")
    if len(re.findall("[～〜]", J)) > K.count("～"):
        out.append("～")
    if len(re.findall("。", J)) > len(re.findall(r"[.!?…～]", K)):
        out.append("。(문장 합병)")
    dots = len(re.findall("[･]", J)) + 3 * J.count("…")
    # 마스터 11-14 「동료지. 동・료.」 — 원문 「な・か・ま」의 가운뎃점을 원판 전각 `・` 로 살린 한 블록은 `…` 1개로 친다.
    if dots and K.count("…") + K.count("동\u30fb료") < max(1, round(dots / 3)):
        out.append("…")
    return out


def selftest():
    assert dropped("あ。い。", "아 이") == ["。(문장 합병)"] and not dropped("あ。い。", "아. 이.")
    assert dropped("えっ ･ ･ ･ ?", "엇?") == ["…"] and dropped("やあ？", "여어.") == ["?"] and dropped("くらえ～ !!", "받아라!!") == ["～"]
    assert not dropped("な ･ か ･ ま。", "동\u30fb료.") and dropped("な ･ か ･ ま。", "동료.") == ["…"]
    assert not dropped("ｲｽﾞｰ～城", "이즈～성") and not dropped("うーむ ･ ･ ･ ", "으음…") and not dropped("バトル・スーツ", "배틀슈트")
    assert tilde_over("こけっ～ !?", "꼬꼬댁～～!?") and tilde_over("あいう", "아～") and tilde_over("あー", "아～～")
    assert not tilde_over("こけっ～ !?", "꼬꼬댁～!?") and not tilde_over("あー", "아～")
    bad = ["어...", "아・・・", "그래… … 응", "뭐！？", "좋아～.", "뭐?.", "그래….", "네.…응", "뭐?…"]
    for s in bad:
        assert hits(s), f"양성 대조 실패: {s}"
    for s in ["어…", "……", "엇!?", "엇?!", "응… 그래.", "…응", "뭐…?", "아…\n…그래"]:
        assert not hits(s), f"음성 대조 실패: {s}"


def main():
    selftest()
    bad = []
    rows = check_text.corpus()
    for path, off, _jp, kr in rows:
        for h in hits(kr):
            bad.append((os.path.basename(path)[:-4], hex(off), h, kr.replace("\n", "/")[:40]))
        for dr in dropped(_jp, kr):
            bad.append((os.path.basename(path)[:-4], hex(off), "원문 부호 빠짐 " + dr, kr.replace("\n", "/")[:40]))
        if tilde_over(_jp, kr):
            bad.append((os.path.basename(path)[:-4], hex(off), "～ 개수>원문", kr.replace("\n", "/")[:40]))
    print(f"  문장부호 금지 꼴 — {len(bad)}곳 (0 이어야 한다, {len(rows)}자리)")
    for b in bad[:10]:
        print(f"    ❌ {b[0]}:{b[1]} {b[2]}: {b[3]}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
