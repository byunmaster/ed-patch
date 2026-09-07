"""고유명사 표기를 **정발에서 찾아 준다** — 가타카나 이름 → 정발이 쓴 한글.

방침은 「**인물·지명은 정발을 따르고 나머지는 자체 번역**」이다(새턴 ED3 와 같다). 따르려면
정발이 뭐라고 썼는지 알아야 하는데, 눈대중으로 음차하면 **틀린다** — 실측:
`アヴィン` 은 「아빈」이 아니라 **「어빈」**, `ルキアス` 는 「루키아스」가 아니라 **「루키어스」**,
`ヴァルクド` 는 「발쿠드」가 아니라 **「발크드」**였다. 셋 다 그럴듯한 쪽이 0회였다.

그래서 **후보를 만들어 정발 코퍼스에서 센다.** 가타카나 한 글자에 한글 후보가 여럿이면
(`ル`→루/르, `ー`→장음 유지/생략, `ヴ`→브/바/버 …) 조합을 펼쳐 전부 세고, 가장 많이 나온
것을 **제안**한다.

🔴 **이건 제안이지 정본이 아니다**(patcher-checklist 3). 사람이 보고 `glossary_<disc>.json`
   에 박는다. 0회로 끝나면 정발에 그 이름이 없다는 뜻이고(PS1 리메이크에만 있는 것),
   그때는 **우리가 정한다** — 「정발에 짝이 없다」를 매처의 한계와 헷갈리지 않는다
   (`docs/reference/our-findings.md`).
"""

import argparse
import collections
import itertools
import json
import os
import re as _re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import kr_corpus

# 가타카나 → 한글 후보. 여럿이면 조합을 펼친다.
# ⚠ 「맞는 하나」를 고르려 들지 않는다 — 고르는 건 코퍼스가 한다.
KANA = {
    "ア": ["아"],
    "イ": ["이"],
    "ウ": ["우"],
    "エ": ["에"],
    "オ": ["오"],
    "カ": ["카", "가"],
    "キ": ["키", "기"],
    "ク": ["쿠", "크", "구"],
    "ケ": ["케", "게"],
    "コ": ["코", "고"],
    "サ": ["사"],
    "シ": ["시"],
    "ス": ["스", "수"],
    "セ": ["세"],
    "ソ": ["소"],
    "タ": ["타", "다"],
    "チ": ["치", "티"],
    "ツ": ["츠", "쓰"],
    "テ": ["테", "데"],
    "ト": ["토", "트", "도"],
    "ナ": ["나"],
    "ニ": ["니"],
    "ヌ": ["누"],
    "ネ": ["네"],
    "ノ": ["노"],
    "ハ": ["하"],
    "ヒ": ["히"],
    "フ": ["푸", "후", "프"],
    "ヘ": ["헤"],
    "ホ": ["호"],
    "マ": ["마"],
    "ミ": ["미"],
    "ム": ["무", "므", "ㅁ"],
    "メ": ["메"],
    "モ": ["모"],
    "ヤ": ["야"],
    "ユ": ["유"],
    "ヨ": ["요"],
    "ラ": ["라", "러"],
    "リ": ["리"],
    "ル": ["루", "르", "ㄹ"],
    "レ": ["레"],
    "ロ": ["로"],
    "ワ": ["와"],
    "ヲ": ["오"],
    "ン": ["ㄴ", "은"],
    "ガ": ["가"],
    "ギ": ["기"],
    "グ": ["구", "그"],
    "ゲ": ["게"],
    "ゴ": ["고"],
    "ザ": ["자"],
    "ジ": ["지"],
    "ズ": ["즈", "주"],
    "ゼ": ["제"],
    "ゾ": ["조"],
    "ダ": ["다"],
    "ヂ": ["지"],
    "ヅ": ["즈"],
    "デ": ["데"],
    "ド": ["도", "드"],
    "バ": ["바"],
    "ビ": ["비"],
    "ブ": ["부", "브"],
    "ベ": ["베"],
    "ボ": ["보"],
    "パ": ["파"],
    "ピ": ["피"],
    "プ": ["푸", "프"],
    "ペ": ["페"],
    "ポ": ["포"],
    "ヴ": ["브", "바", "버", "부"],
    "ッ": ["", "ㅅ"],
    "ー": ["", "ㅡ"],
}
# 요음 — 앞 글자와 묶여야 한다(`シャ`→샤). 늘려 쓰지 말고 여기서 처리한다.
YOON = {
    "ャ": {
        "キ": ["캬", "갸"],
        "シ": ["샤"],
        "チ": ["차", "챠"],
        "ニ": ["냐"],
        "ヒ": ["햐"],
        "ミ": ["먀"],
        "リ": ["랴"],
        "ギ": ["갸"],
        "ジ": ["자", "쟈"],
        "ビ": ["뱌"],
        "ピ": ["퍄"],
    },
    "ュ": {
        "キ": ["큐", "규"],
        "シ": ["슈"],
        "チ": ["추", "츄"],
        "ニ": ["뉴"],
        "ヒ": ["휴"],
        "ミ": ["뮤"],
        "リ": ["류"],
        "ギ": ["규"],
        "ジ": ["주", "쥬"],
        "ビ": ["뷰"],
        "ピ": ["퓨"],
        "テ": ["튜"],
        "デ": ["듀"],
        "フ": ["퓨"],
        "ヴ": ["뷰"],
    },
    "ョ": {
        "キ": ["쿄", "교"],
        "シ": ["쇼"],
        "チ": ["초", "쵸"],
        "ニ": ["뇨"],
        "ヒ": ["효"],
        "ミ": ["묘"],
        "リ": ["료"],
        "ギ": ["교"],
        "ジ": ["조", "죠"],
        "ビ": ["뵤"],
        "ピ": ["표"],
    },
    "ィ": {
        "テ": ["티"],
        "デ": ["디"],
        "フ": ["피", "휘"],
        "ウ": ["위"],
        "ヴ": ["비", "위"],
        "ツ": ["티"],
        "ズ": ["지"],
    },
    "ェ": {
        "シ": ["셰", "세"],
        "ジ": ["제"],
        "チ": ["체"],
        "フ": ["페"],
        "ウ": ["웨"],
        "ヴ": ["베"],
    },
    "ォ": {"フ": ["포", "훠"], "ウ": ["워"], "ヴ": ["보"]},
    "ァ": {"フ": ["파"], "ウ": ["와"], "ヴ": ["바"]},
}
JAMO_TAIL = {"ㄴ": 4, "ㄹ": 8, "ㅁ": 16, "ㅅ": 19, "ㅡ": None}  # 받침 코드 (ㅡ 는 장음 표식)
MAX_CANDS = 4096


def _attach(syl, jamo):
    """앞 음절에 받침을 붙인다. 이미 받침이 있으면 못 붙인다(그 조합은 버린다)."""
    if not syl or not ("가" <= syl[-1] <= "힣"):
        return None
    code = ord(syl[-1]) - 0xAC00
    if code % 28:
        return None
    t = JAMO_TAIL.get(jamo)
    if t is None:
        return None
    return syl[:-1] + chr(0xAC00 + code + t)


def candidates(name, cap=MAX_CANDS):
    """가타카나 이름 → [한글 후보]. 조합이 너무 많으면 앞에서 자른다."""
    slots, i = [], 0
    while i < len(name):
        c = name[i]
        nxt = name[i + 1] if i + 1 < len(name) else ""
        if nxt in YOON and c in YOON[nxt]:
            slots.append(YOON[nxt][c])
            i += 2
            continue
        if c in KANA:
            slots.append(KANA[c])
            i += 1
            continue
        if c == "・":  # 가운뎃점은 정발에서 사라지거나 공백이 된다
            slots.append(["", " "])
            i += 1
            continue
        return []  # 한자·기호가 섞였으면 음차 대상이 아니다
    if not slots:
        return []
    out = []
    for combo in itertools.islice(itertools.product(*slots), cap):
        s = ""
        ok = True
        for part in combo:
            if part in JAMO_TAIL:
                s2 = _attach(s, part)
                if s2 is None:
                    ok = False
                    break
                s = s2
            else:
                s += part
        if ok and s.strip():
            out.append(s.strip())
    return list(dict.fromkeys(out))


def near(cands, corpus_words, top=3):
    """음차가 빗나갔을 때 **근처**를 보여 준다 — 정발이 영어 철자를 따랐을 수 있다.

    실측: `ルキアス`→「루키어스」, `ダグラス`→「더글라스」, `ミッシェル`→「미첼」.
    셋 다 가나를 그대로 옮긴 후보가 0회였다 — 정발이 **원어 철자**를 보고 옮긴 것이다.
    음절 겹침으로 근처를 건져 사람이 고르게 한다(체크리스트 5: 후보 좁히기지 판정이 아니다).
    """
    best = []
    cs = [set(c) for c in cands]
    for w, n in corpus_words.items():
        if not (2 <= len(w) <= 9):
            continue
        sw = set(w)
        sc = max((len(sw & c) / max(len(sw), len(c)) for c in cs), default=0)
        if sc >= 0.5:
            best.append((sc, n, w))
    best.sort(reverse=True)
    return best[:top]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    ap.add_argument(
        "--kind", default="place,person", help="쉼표로 (place,person,monster,item,spell,rank)"
    )
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--only-missing", action="store_true", help="정본에 아직 없는 것만")
    ap.add_argument("words", nargs="*", help="직접 줄 낱말 (없으면 names.json 에서)")
    a = ap.parse_args()

    joined = "\n".join(kr_corpus.corpus(a.disc))
    if a.words:
        words = a.words
    else:
        p = os.path.join(common.OUT_DIR, a.disc, "names.json")
        if not os.path.exists(p):
            raise SystemExit(
                f"낱말 덤프가 없다: {p}\n   `dump_names.py --disc {a.disc} --write` 부터."
            )
        kinds = set(a.kind.split(","))
        doc = json.load(open(p, encoding="utf-8"))
        words = []
        for r in doc["regions"]:
            if r["kind"] in kinds:
                for s in r["items"]:
                    if s not in words:
                        words.append(s)
    if a.only_missing:
        import glossary

        have = glossary.flat(a.disc)
        words = [w for w in words if w not in have]

    corpus_words = collections.Counter()
    for m in _re.finditer(r"[가-힣]{2,9}", joined):
        corpus_words[m.group()] += 1

    found = 0
    for w in words:
        cs = candidates(w)
        root = w
        if not cs:
            # `マッター鉱山`·`ベネキア街道` 처럼 **가타카나 어근 + 한자 접미**가 흔하다.
            # 접미(鉱山·街道·の森…)는 우리가 옮기고, 어근만 정발에서 찾는다.
            runs_ = _re.findall(r"[ァ-ヴー・]{2,}", w)
            if runs_:
                root = max(runs_, key=len)
                cs = candidates(root)
        if not cs:
            print(f"  {w}: (음차 대상 아님 — 한자·기호)")
            continue
        mark = "" if root == w else f" [어근 {root}]"
        hits = collections.Counter({c: joined.count(c) for c in cs})
        top = [(c, n) for c, n in hits.most_common(a.top) if n]
        if top:
            found += 1
            print(f"  {w}{mark}: " + " · ".join(f"{c}({n})" for c, n in top))
        else:
            nb = near(cs, corpus_words)
            extra = ("  ← 근처: " + " · ".join(f"{x}({n})" for _, n, x in nb)) if nb else ""
            print(f"  {w}{mark}: 정발에 없음 (후보 {len(cs)}){extra}")
    print(f"\n{len(words)}개 중 정발에서 찾은 것 {found}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
