"""
정렬 검수 목록 생성기 — PS1 일문 ↔ DOS 한국어 매칭을 사람이 정발판과 대조하도록 출력.

자동 매칭(align_jp_kr.py)은 화자·길이·순서 신호만 보므로, 같은 화자의 변형 대사가
서로 뒤바뀔 수 있다(2026-07-09 발견: 시녀 '깨우기'↔'저녁식사' swap, 둘 다 score>4라
low_confidence로도 안 걸림). 신호로 못 잡는 이 오류를 사람이 잡도록, 각 쌍을 JP·KR
나란히 놓고 '의미 충돌 의심'을 상위에 모아 준다.

의심 신호(휴리스틱, 확정 아님 — 사람이 정발판으로 확정):
 - concept_conflict: JP의 개념어(아침/저녁/식사 등)와 KR이 다른 축으로 어긋남
 - digit_mismatch: 숫자가 서로 다름
 - length_outlier: KR/JP 길이비가 기대(≈0.55)에서 크게 벗어남
 - low_confidence / unmatched: align 단계 플래그 승계

출력: out/review/<게임>_SCN<n>.md  (씬별, 의심 우선 정렬)
"""

import json
import os
import re

from common import OUT_DIR

ALIGN_DIR = os.path.join(OUT_DIR, "align")
SCN_JP_DIR = os.path.join(OUT_DIR, "scn_jp")
DOS_KR_DIR = os.path.join(OUT_DIR, "dos_kr")
REVIEW_DIR = os.path.join(OUT_DIR, "review")

GAMES = {"ED1": 6, "ED2": 13}

# 개념 충돌 축: JP가 이 축의 값을 말하는데 KR엔 대응 표현이 없으면 swap 의심.
# (축 이름, JP 표기 후보, KR 표기 후보) — 부분일치. 확정 아니라 사람 검수 트리거.
AXES = [
    ("아침/기상", ("朝", "おはよう", "お目覚め", "起き"), ("아침", "주무", "기침", "일어")),
    ("저녁/밤", ("夕", "夜", "晩", "おやすみ"), ("저녁", "밤", "안녕히 주무")),
    ("점심/낮", ("昼", "正午"), ("점심", "낮")),
    ("아침식사", ("朝食",), ("아침식사", "아침밥")),
    ("저녁식사", ("夕食", "晩ご"), ("저녁식사", "저녁밥")),
    ("점심식사", ("昼食",), ("점심식사",)),
    ("외출/이동", ("出かけ", "行って"), ("외출", "나가", "가십")),
    ("귀가", ("帰って", "戻って"), ("돌아오", "귀가")),
]
CJK = re.compile(r"[぀-ヿ一-鿿]")
TAG = re.compile(r"\{[^}]*\}|\\x[0-9A-F]{2}")
DIGITS_Z = str.maketrans("０１２３４５６７８９", "0123456789")


def clean_jp(text):
    return TAG.sub("", re.sub(r"^\{c\}.*?\{c\}", "", text, count=1)).replace("　", " ").strip()


def clean_kr(text):
    t = re.sub(r"^.*?\{/spk\}", "", text, count=1)
    t = t.replace("{n}", " ").replace("{p}", " / ").replace("{end}", "")
    return re.sub(r"\\x[0-9A-F]{2}|\{spk\}|\{/spk\}", "", t).strip()


def digits(s):
    return "".join(re.findall(r"\d", s.translate(DIGITS_Z)))


def concept_conflict(jp, kr):
    """JP가 어떤 축의 값을 말하는데 KR엔 그 대응 표현이 없으면 (축 이름) 반환."""
    return [
        name
        for name, jp_terms, kr_terms in AXES
        if any(t in jp for t in jp_terms) and not any(t in kr for t in kr_terms)
    ]


def review_rows(game, n):
    apath = os.path.join(ALIGN_DIR, f"{game}_SCN{n}.json")
    if not os.path.exists(apath):
        return None
    align = json.load(open(apath, encoding="utf-8"))
    jp = {
        e["entry_id"]: e
        for e in json.load(open(os.path.join(SCN_JP_DIR, f"{game}SCN{n}.json"), encoding="utf-8"))[
            "entries"
        ]
    }
    kr_cache = {}

    def kr_entry(table, eid):
        if table not in kr_cache:
            kr_cache[table] = {
                e["entry_id"]: e
                for e in json.load(
                    open(os.path.join(DOS_KR_DIR, f"{table}.json"), encoding="utf-8")
                )["entries"]
            }
        return kr_cache[table][eid]

    rows = []
    for p in align["pairs"]:
        if not p["jp"]:
            continue  # unmatched_kr은 검수 대상 아님(번역 저본 쪽 미사용 대사)
        jt = clean_jp(jp[p["jp"]["entry_id"]]["text"])
        ke = kr_entry(p["kr"]["table"], p["kr"]["entry_id"])
        kt = clean_kr(ke["text"])
        flags = list(p["flags"])
        # 의미 충돌 휴리스틱
        conflicts = concept_conflict(jt, kt)
        if conflicts:
            flags.append("concept?:" + "/".join(conflicts))
        if digits(jt) != digits(kt) and (digits(jt) or digits(kt)):
            flags.append("digit?")
        jlen = len(CJK.findall(jt)) or 1
        ratio = len(re.findall(r"[가-힣]", kt)) / jlen
        if ratio and (ratio > 1.6 or ratio < 0.2):
            flags.append(f"len?:{ratio:.1f}")
        # 의심도: concept > low_conf > digit > len
        suspect = (2 if any(f.startswith("concept?") for f in flags) else 0) + (
            1 if "low_confidence" in flags else 0
        )
        rows.append(
            {
                "ps1": p["jp"]["entry_id"],
                "spk_jp": p["jp"]["speaker"],
                "jp": jt,
                "kr_ref": f"{p['kr']['table']}#{p['kr']['entry_id']}",
                "spk_kr": p["kr"]["speaker"],
                "kr": kt,
                "score": p["score"],
                "flags": flags,
                "suspect": suspect,
            }
        )
    return rows


def write_md(game, n, rows):
    os.makedirs(REVIEW_DIR, exist_ok=True)
    path = os.path.join(REVIEW_DIR, f"{game}_SCN{n}.md")
    suspects = [r for r in rows if r["suspect"] > 0]
    # 의심 우선(내림차순), 그 안에서는 PS1 순서
    suspects.sort(key=lambda r: (-r["suspect"], r["ps1"]))
    rest = sorted((r for r in rows if r["suspect"] == 0), key=lambda r: r["ps1"])
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# 정렬 검수 — {game}SCN{n}\n\n")
        f.write(f"매칭 {len(rows)}쌍, **검수 우선 {len(suspects)}쌍**. ")
        f.write("JP(PS1 일문)와 KR(DOS 정발판)이 같은 대사인지 정발판과 대조. ")
        f.write("`concept?`는 개념 축이 어긋난 swap 의심(예: JP 아침 ↔ KR 저녁).\n\n")

        def block(r):
            fl = f"  `{' '.join(r['flags'])}`" if r["flags"] else ""
            return (
                f"- **PS1#{r['ps1']}** ({r['spk_jp']}) · score {r['score']}{fl}\n"
                f"  - JP: {r['jp'][:120]}\n"
                f"  - KR: {r['kr'][:120]}  _({r['kr_ref']}, {r['spk_kr']})_\n"
            )

        if suspects:
            f.write("## ⚠ 검수 우선 (의미 충돌·저신뢰)\n\n")
            for r in suspects:
                f.write(block(r))
            f.write("\n")
        f.write("## 나머지 매칭 (PS1 순서)\n\n")
        for r in rest:
            f.write(block(r))
    return len(suspects)


def main():
    total_suspect = 0
    for game, n_scn in GAMES.items():
        got = False
        for n in range(1, n_scn + 1):
            rows = review_rows(game, n)
            if rows is None:
                continue
            got = True
            s = write_md(game, n, rows)
            total_suspect += s
            print(f"{game}SCN{n}: {len(rows)}쌍 → 검수 우선 {s}")
        if not got:
            print(f"{game}: 정렬 산출물 없음 — 건너뜀")
    print(f"\n검수 우선 총 {total_suspect}쌍 → {REVIEW_DIR}")


if __name__ == "__main__":
    main()
