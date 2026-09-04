#!/usr/bin/env python3
"""전투 문안을 정발로 맞춘다 — 정발 짝 후보를 찾아 검토표로 낸다(status 1-2).

**왜.** `textmap/battle.json` 은 엔트리 498 중 414개가 `ours`(자체 번역)다. 정발 전투 문안이
어디 있는지 몰라서였다. 이제 둘 다 찾았다:

| 부류                                       | 정발 출처                    |
| ------------------------------------------ | ---------------------------- |
| 몬스터 등장·공격 묘사·격파문·보스 대사     | `MONDLL/M0NN.DLL` (추출됨)   |
| **전투 시스템 문구**(승리·데미지·상태이상) | **`ED1MAIN.EXE` 0x23000~**   |

두 번째가 이 도구의 발견이다(2026-08-09) — `MONDLL` 에 없어서 "정발에 아예 없다"고 적어
뒀었는데, 실행 파일 안에 302문자열이 통째로 있었다. **"없다"는 결론은 안 찾아본 곳이
있는 한 가설일 뿐**이다(같은 실수를 `SINDLL` 에서 이미 한 번 했다).

**짝짓는 방법.** JP 로 매칭하지 않는다 — 우리 `ours` 는 이미 뜻이 맞으므로 **한국어끼리**
비교하는 게 훨씬 정확하다(difflib). 인자 자리는 정규화해서 본다(정발 `` `1 ``·`` `2 `` ↔
우리 `%s`, 정발 `2Kd`·`50` 류 리터럴 ↔ 우리 `%d`).

⚠ **자동 적용은 안 한다.** 배틀에도 계약이 있다 — 아크담 대사를 정발 포인터로 바꿨더니
`%c` 가 글자로 찍히고 꼬리가 깨졌다(2026-08-08). 이 도구는 **후보만** 내고, 승격은 사람이
`--apply` 로 고른 것만 한다.
⚠ 검토표는 정발 문안을 담으므로 **REVIEW_DIR(work/review, gitignore)** 로만 나간다.

**승격 조건(`--apply`)은 하나뿐이다** — 우리 문안의 **한글 부분이 정발 문자열의 부분열과
정확히 일치**할 때만. 그러면 `parts` 로 갈라 한글은 **포인터**(f/o/l)로, 남는 서식·부호
(`%c%s%c`·`!!`·개행)만 `ours` 로 둔다. 파생값이 지금 문안과 **글자 하나까지 같으므로 이미지가
안 바뀐다**(sha1 로 검산). 뜻을 바꾸는 승격은 이 도구가 하지 않는다 — 사람 몫이다.

⚠ **이건 저작권 정리이기도 하다.** `ours` 인데 정발과 글자까지 같은 엔트리가 실제로 있었다
(`전투에서 승리했다.` 등). 그대로 두면 정발 문안이 리포에 박힌 채 남는다 — 파생 체계를
만든 이유가 사라진다.

  python3 tools/past_battle_jeongbal.py            # 요약
  python3 tools/past_battle_jeongbal.py --report   # → work/review/past_battle_jeongbal.md
  python3 tools/past_battle_jeongbal.py --apply    # 글자 동일분만 포인터로 승격
  python3 tools/past_battle_jeongbal.py --mondll   # 몬스터별 메시지 — 표기 차이만 자동
  python3 tools/past_battle_jeongbal.py --table    # **결정표** → work/review/battle_table.md
  python3 tools/past_battle_jeongbal.py --stitch   # **조각 잇기**(앞은 우리 몫, 뒤는 정발 포인터)
  python3 tools/past_battle_jeongbal.py --bulk 0.7 # **일괄 채택**(위험 표시 없는 것) + 확인표
  python3 tools/past_battle_jeongbal.py --pick     # **터미널에서 한 행씩** 고른다(중간 저장)
  python3 tools/past_battle_jeongbal.py --accept work/review/battle_table.md   # 표의 `선택` 칸 반영
"""

import difflib
import json
import os
import re
import sys

os.environ.setdefault("LOCK_BYPASS", "1")

import patch_items as P
import reinsert_kr_pilot as R
from common import OUT_DIR, REVIEW_DIR, extract
from derive_text import _PUNCT_SP, DOS_ED1, TEXTMAP_DIR, jkey

# 정발 전투 시스템 문구가 사는 구간. 앞은 메뉴·아이템명(patch_sys_ui 관할), 뒤는 지명 블롭.
SYS_LO, SYS_HI = 0x23900, 0x27950
_KR_RUN = re.compile(rb"(?:[\xb0-\xc8][\xa1-\xfe]|[\x20-\x7e])+")
# 인자 자리 정규화 — 정발 DOS 는 `` `1 ``/`` `2 ``, PS1 은 `%s`/`%d`/`%c`.
_ARG = re.compile(r"`[0-9]|%[scd]|\\Z|\\\\Z")


# MONDLL 한 엔트리는 **여러 메시지가 이어 붙은 묶음**이다(등장·공격·상태이상…).
# 구분자는 제어바이트 `\x07`(다음 메시지)·`\x0A`·`\x02`·`\x0D`·`\x01`·`\x05`. 조각으로 갈라야
# 우리 블록과 1:1 이 된다 — 엔트리 통째로 비교하면 아무것도 안 맞는다(2026-08-09).
# ⚠ 오프셋은 **raw_hex 바이트 기준**으로 센다. 추출 텍스트는 `{n}` 같은 마크업으로 바뀌어
# 있어 문자 위치가 파일 오프셋과 어긋난다.
# ⚠ 제어 잔재(`\x03`·`\x06`)가 조각에 붙어 있으면 그대로 화면에 나가고 온점 판정도 어긋난다
# (`사용했다.  \x03` → 우리 온점이 겹쳐 `사용했다..`, `\x06내려갔다` 실측 2026-08-09).
# **0x20 미만은 전부 구분자**로 본다 — 제어바이트가 조각에 붙으면 그대로 화면에 나간다
# (`\x1e아크담`·`사용했다.  \x03` 실측 2026-08-09). 하나씩 열거하다 계속 새는 것보다 낫다.
_FRAG_SEP = bytes(range(0x20))


def mondll_strings():
    """`MONDLL` 조각 [(파일, 오프셋, 바이트길이, 텍스트)] — 몬스터별 전투 메시지."""
    out = []
    d = os.path.join(OUT_DIR, "dos_kr", "ed1")
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if not (fn.startswith("M") and fn.endswith(".json")):
            continue
        doc = json.load(open(os.path.join(d, fn), encoding="utf-8"))
        rel = "MONDLL/" + doc["source"]["file"].rsplit("/", 1)[-1]
        for e in doc["entries"]:
            raw = bytes.fromhex(e.get("raw_hex") or "")
            base = int(e["file_offset"], 16)
            i = 0
            while i < len(raw):
                j = i
                while j < len(raw) and raw[j] not in _FRAG_SEP:
                    j += 1
                seg, off = raw[i:j], base + i
                lead = len(seg) - len(seg.lstrip(b" "))
                seg, off = seg[lead:].rstrip(b" "), off + lead
                # 꼬리 말줄임(`.....`)은 우리 쪽 부호와 겹친다 — 조각에서 뗀다
                seg = seg.rstrip(b".") if seg.endswith(b"..") else seg
                # **선두 조사도 뗀다** — 정발은 이름을 인자로 주입하고 조사를 조각 앞에 두는데
                # (`는 소멸했다`), PS1 은 조사가 우리 몫이라 그대로 붙이면 `은(는) 는 소멸했다`
                # 가 된다(2026-08-09 일괄 검산에서 잡았다). 떼면 그 자리들이 깨끗이 맞는다.
                m2 = re.match(
                    rb"(?:\xc0\xba|\xb4\xc2|\xc0\xcc|\xb0\xa1|\xc0\xbb|\xb8\xa6)\x20+", seg
                )
                if m2:
                    seg, off = seg[m2.end() :], off + m2.end()
                if len(seg) >= 6:
                    try:
                        out.append((rel, off, len(seg), seg.decode("cp949")))
                    except UnicodeDecodeError:
                        pass
                i = j + 1
    return out


def jeongbal_strings(paths=("ED1MAIN.EXE",)):
    """정발 실행 파일의 한글 문자열 [(파일, 오프셋, 바이트길이, 텍스트)]."""
    out = []
    for rel in paths:
        b = open(os.path.join(DOS_ED1, rel), "rb").read()
        for m in _KR_RUN.finditer(b):
            if not (SYS_LO <= m.start() <= SYS_HI):
                continue
            s = m.group()
            if not re.search(rb"[\xb0-\xc8][\xa1-\xfe]", s):
                continue
            try:
                t = s.decode("cp949")
            except UnicodeDecodeError:
                continue
            if len(t.strip()) < 2:
                continue
            # ⚠ `\Z` 류 이스케이프가 앞에 붙은 문자열이 있다(`\Z아무 것도 일어나지 않았다.`).
            # 그대로 두면 화면에 글자로 나간다(2026-08-09 일괄 검산).
            off, ln = m.start(), len(s)
            # `\Z` 류 이스케이프가 앞에 붙은 문자열이 있다(그대로 두면 글자로 나간다).
            m2 = re.match(r"^(?:\\[A-Za-z])+", t)
            if m2:
                t, off, ln = t[m2.end() :], off + m2.end(), ln - m2.end()
            # ⚠ 선두 조사도 뗀다 — MONDLL 과 같은 이유다(우리 조사와 겹친다).
            # 여기 빠뜨려서 `는 방어의 준비를 했다` 가 계속 후보에서 밀렸다(2026-08-09).
            m3 = re.match(r"^(?:은|는|이|가|을|를)\s+", t)
            if m3:
                d = len(t[: m3.end()].encode("cp949"))
                t, off, ln = t[m3.end() :], off + d, ln - d
            # 꼬리 공백은 뗀다 — 안 떼면 부호 판정이 어긋나 우리 온점이 겹친다
            # (`방어의 준비를 했다.  ` + `.` = `했다..`, 2026-08-09).
            t2 = t.rstrip()
            ln -= len(t.encode("cp949")) - len(t2.encode("cp949"))
            if len(t2.strip()) >= 2:
                out.append((rel, off, ln, t2))
    return out


def mnorm(s):
    """몬스터 메시지 비교용 정규화 — 인자 자리·마크업·공백·부호를 지운다."""
    s = re.sub(r"`[0-9]|%[scd]|\\x[0-9A-Fa-f]{2}|\{[np]\}", "", s)
    return re.sub(r"[\s.,!?~…]+", "", s)


def norm(s):
    """비교용 정규화 — 인자 자리·공백·문장부호를 지운다."""
    return re.sub(r"[\s.!?…]+", "", _ARG.sub("", s))


def ours_entries():
    """자체 번역 상태인 배틀 엔트리 [(k, ours, jp)]."""
    tm = json.load(open(os.path.join(TEXTMAP_DIR, "battle.json"), encoding="utf-8"))
    by_k = {e["k"]: e for e in tm["entries"]}
    orig = extract(257, 1021952)
    rows = []
    for _fo, _end, jp in P.corpus_strings(orig):
        e = by_k.get(jkey(jp))
        if e is not None and "ours" in e:
            rows.append((e["k"], e["ours"], jp))
    return rows


_HANGUL = re.compile(r"[가-힣]")


def split_pointerable(ours, cands):
    """우리 문안의 **한글 몫이 정발 문자열의 부분열과 정확히 같으면** (pre, src, post) 반환.

    pre/post 에는 한글이 없어야 한다 — 남는 건 서식(`%c%s%c`)·부호·개행뿐이라 리포에 둬도
    저작권 대상이 아니다. 한 글자라도 다르면 승격하지 않는다(뜻을 바꾸는 판단은 사람 몫)."""
    m = _HANGUL.search(ours)
    if not m:
        return None
    lo = m.start()
    hi = max(x.end() for x in _HANGUL.finditer(ours))
    core = ours[lo:hi]
    for rel, off, _ln, t in cands:
        i = t.find(core)
        if i < 0:
            continue
        return (
            ours[:lo],
            (rel, off + len(t[:i].encode("cp949")), len(core.encode("cp949"))),
            ours[hi:],
        )
    return None


def apply_promotions():
    """글자 동일분을 `parts` 포인터로 승격. 반환: 승격 건수."""
    from derive_text import _dos_file

    cands = jeongbal_strings()
    path = os.path.join(TEXTMAP_DIR, "battle.json")
    tm = json.load(open(path, encoding="utf-8"))
    by_k = {e["k"]: e for e in tm["entries"]}
    n = 0
    for k, ours, _jp in ours_entries():
        e = by_k.get(k)
        if e is None or "ours" not in e:
            continue
        got = split_pointerable(ours, cands)
        if not got:
            continue
        pre, (rel, off, ln), post = got
        if (
            _dos_file(rel)[off : off + ln].decode("cp949") + ""
            != ours[len(pre) : len(ours) - len(post)]
        ):
            continue  # 오프셋 계산 검산 — 안 맞으면 건너뛴다
        parts = []
        if pre:
            parts.append({"ours": pre})
        parts.append({"f": rel, "o": off, "l": ln})
        if post:
            parts.append({"ours": post})
        e.pop("ours")
        e["parts"] = parts
        n += 1
    json.dump(tm, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return n


# ── ②단계 2차: 문안이 다른 것도 정발로 맞춘다 ─────────────────────────────────
# 유저 확정 2026-08-09: "전투문안도 대사처럼 정발로 맞춰야 해."
#
# **서식은 절대 안 건드린다.** `%c`/`%s`/`%d` 는 콜사이트 인자열과 정렬돼야 하는 계약이라
# (배틀도 대사와 같다 — 2026-08-08 아크담 대사에서 꼬리가 깨졌다), 우리 문안의 **한글 몫만**
# 정발 것으로 갈고 서식·부호는 제자리에 둔다. 그래서 파생값의 서식 개수·순서가 **불변**이고,
# 그걸 승격 조건으로 검산한다(안 맞으면 건너뛴다).
#
# 정렬은 **공통 접미**로 한다 — PS1 은 이름을 리터럴로 박고(`호의 효과가 있다.`) 정발은
# 인자로 주입해서(`` `1 의 효과가 있다.``) 앞이 다르고 뒤가 같다. 접미가 4자 이상 겹치면
# 그 뒤를 정발 포인터로 갈고, 안 겹치는 앞부분(이름)은 우리 쪽에 남긴다.
_JB_TRIM = re.compile(r"^(?:[`\\][0-9A-Za-z]|\s)+")


def core_of(t):
    """정발 문자열에서 인자 자리·앞뒤 공백을 뗀다. 반환: (앞 잘린 몫, 본문)."""
    m = _JB_TRIM.match(t)
    lead = m.group() if m else ""
    return lead, t[len(lead) :].rstrip()


def common_tail(a, b, lo=4):
    """a·b 의 공통 접미 길이(한글을 포함해 lo자 이상일 때만)."""
    n = 0
    while n < min(len(a), len(b)) and a[-1 - n] == b[-1 - n]:
        n += 1
    return n if n >= lo and _HANGUL.search(a[len(a) - n :]) else 0


def align_to_jeongbal(ours, cands, min_ratio):
    """(parts, 새 문안) 또는 None. 한글 몫만 정발로 갈고 서식은 그대로 둔다."""
    m = _HANGUL.search(ours)
    if not m:
        return None
    lo, hi = m.start(), max(x.end() for x in _HANGUL.finditer(ours))
    pre, our_core, post = ours[:lo], ours[lo:hi], ours[hi:]
    best = None
    for rel, off, _ln, t in cands:
        if "{" in t or "\\x" in t:  # MONDLL 마크업이 남은 후보는 조각내기 위험
            continue
        lead, body = core_of(t)
        if not body or not _HANGUL.search(body):
            continue
        r = difflib.SequenceMatcher(None, norm(our_core), norm(body)).ratio()
        n = common_tail(our_core, body)
        if r < min_ratio or not n:
            continue
        # ⚠ 정발 본문이 **통째로** 공통 접미여야 한다. 아니면 앞이 겹쳐 중복이 난다
        # (`아무것도 없다` + `아무 것도 없다` → `아무아무 것도 없다` 실측 2026-08-09).
        if len(body) != n:
            continue
        if best is None or r > best[0]:
            best = (r, rel, off + len(lead.encode("cp949")), body, n)
    if best is None:
        return None
    _r, rel, off, body, n = best
    keep = our_core[: len(our_core) - n]  # 이름 등 PS1 리터럴 몫
    parts = []
    if pre + keep:
        parts.append({"ours": pre + keep})
    parts.append({"f": rel, "o": off, "l": len(body.encode("cp949"))})
    if post:
        parts.append({"ours": post})
    return parts, pre + keep + body + post


def apply_alignment(min_ratio=0.80):
    """정발 문안으로 맞춘다. 반환: [(k, 옛 문안, 새 문안)]."""
    from derive_text import _dos_file

    cands = jeongbal_strings() + mondll_strings()
    path = os.path.join(TEXTMAP_DIR, "battle.json")
    tm = json.load(open(path, encoding="utf-8"))
    by_k = {e["k"]: e for e in tm["entries"]}
    out = []
    for k, ours, _jp in ours_entries():
        e = by_k.get(k)
        if e is None or "ours" not in e:
            continue
        got = align_to_jeongbal(ours, cands, min_ratio)
        if not got:
            continue
        parts, new = got
        if re.findall(r"%[scd]", new) != re.findall(r"%[scd]", ours):
            continue  # 서식 계약 — 개수·순서가 바뀌면 승격 안 한다
        src = next(p for p in parts if "f" in p)
        if _dos_file(src["f"])[src["o"] : src["o"] + src["l"]].decode("cp949") not in new:
            continue  # 오프셋 검산
        if new == ours:
            continue  # 글자 동일분은 apply_promotions 관할
        e.pop("ours")
        e["parts"] = parts
        out.append((k, ours, new))
    json.dump(tm, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return out


# ── ③ 몬스터별 전투 메시지를 정발로 (유저 확정 2026-08-09) ────────────────────
# "정발 위주로 가되 맞춤법 띄어쓰기 등은 교정한 상태로." — 대사 트랙과 같은 방침이다.
# 그래서 교정도 같은 엔진(`reinsert_kr_pilot.spell_fix` = `dos_spelling_fixes.json`)을 쓰고,
# 결과 차이는 **낱말 단위 `fix` 쌍**으로 남긴다(문장을 적으면 저작권 규칙 위반).
#
# ⚠ **표기 차이만 자동으로 넘긴다**(`norm()` 이 같은 것). 뜻이 다르면 사람 몫이다 —
# 몬스터 메시지는 서로 비슷해서 유사도만 믿으면 **다른 몬스터의 대사**를 물 수 있다.
_JOSA = r"(?:은\(는\)|이\(가\)|을\(를\))"


def core(s):
    """우리 문안을 (앞 서식, 본문, 꼬리) 로 가른다.

    선두 조사 병기(`은(는)`)는 **PS1 몫**이다 — 이름 주입 뒤에 붙는 자리라 정발엔 없다.
    ⚠ **`MP`·`Gold` 같은 라틴 낱말은 본문에 남긴다**(2026-08-09 유저 지적). 예전엔 "첫 한글
    부터"를 본문으로 잡아서 `MP가 부족하다!` 의 본문이 `가 부족하다` 가 됐고, 정발
    `MP가 모자란다 !` 와 유사도가 바닥이라 **후보에서 탈락**했다. 정발엔 있는데 "짝 없음"
    으로 분류된 것이다 — 분류가 "없다"가 아니라 "내 매처가 못 찾았다" 였다."""
    m = re.match(rf"^(?:%[scd]|\s)*(?:{_JOSA}\s*)?", s)
    lo = m.end() if m else 0
    hi = None
    for i in range(len(s) - 1, lo - 1, -1):
        if _HANGUL.match(s[i]) or s[i].isalnum():
            hi = i + 1
            break
    if hi is None or hi <= lo:
        return None
    return s[:lo], s[lo:hi], s[hi:]


def word_fix(a):
    """정발 조각 → `spell_fix` 결과와의 **낱말 단위** 차이 쌍.

    ⚠ 어절 수가 달라지는 교정(`두마리`→`두 마리`)이 있어 zip 으로는 못 낸다 — difflib 로
    바뀐 구간만 뽑는다. 구간이 2어절을 넘으면 문장급이라 포기한다(저작권 규칙)."""
    b = R.spell_fix(a)
    if a == b:
        return []
    pa, pb = a.split(" "), b.split(" ")
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, pa, pb).get_opcodes():
        if op == "equal":
            continue
        if i2 - i1 > 2 or j2 - j1 > 2:
            return []
        out.append([" ".join(pa[i1:i2]), " ".join(pb[j1:j2])])
    return out


def apply_mondll():
    """몬스터별 메시지를 정발 조각 포인터로 바꾼다. 반환: [(k, 옛, 새)]."""
    from derive_text import _dos_file, _guard

    # ⚠ 두 출처를 **다 본다** — MONDLL 만 보다가 `레벨업했다` 처럼 ED1MAIN 에 짝이 있는
    # 자리를 통째로 놓쳤다(결정표를 만들고 나서야 보였다, 2026-08-09).
    frags = mondll_strings() + jeongbal_strings()
    path = os.path.join(TEXTMAP_DIR, "battle.json")
    tm = json.load(open(path, encoding="utf-8"))
    by = {e["k"]: e for e in tm["entries"]}
    changed = []
    for k, ours, _jp in ours_entries():
        e = by.get(k)
        if e is None or "ours" not in e:
            continue
        got = core(ours)
        if not got:
            continue
        pre, c, post = got
        if len(c) < 4 or "\n" in c:
            continue
        n = mnorm(c)
        cand = None
        for rel, off, _ln, t in frags:
            m = re.match(r"^(?:`[0-9]\s*)+", t)
            lead = m.group() if m else ""
            body_t = t[len(lead) :]
            if not _HANGUL.search(body_t) or mnorm(body_t) != n:
                continue
            cand = (rel, off + len(lead.encode("cp949")), len(body_t.encode("cp949")), body_t)
            break
        if cand is None:
            continue
        rel, off, ln, body_t = cand
        if _dos_file(rel)[off : off + ln].decode("cp949") != body_t:
            continue
        fix = word_fix(body_t)
        post2 = (
            post
            if (post.strip(" ") == "" or not re.search(r"[.!?~…]$", body_t))
            else re.sub(r"^[ .!?~…]+", "", post)
        )
        new = _PUNCT_SP.sub("", pre + R.spell_fix(body_t) + post2)
        if re.findall(r"%[scd]", new) != re.findall(r"%[scd]", ours):
            continue
        parts = []
        if pre:
            parts.append({"ours": pre})
        parts.append({"f": rel, "o": off, "l": ln})
        if post2:
            parts.append({"ours": post2})
        e.pop("ours")
        e["parts"] = parts
        if fix:
            e["fix"] = fix
        e["sha"] = _guard(new)
        if new != ours:
            changed.append((k, ours, new))
    json.dump(tm, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return changed


# ── 결정표: 원문 · 우리 번역 · 정발 후보(교정 적용 최종) ──────────────────────
# 유저 제안 2026-08-09: "표로 만들어서 인게임이 아니라 표만 보고 매칭이 가능할 것 같은데."
# 맞다 — 전투 메시지는 짧고 정형이라 표로 판정이 된다. 그래서 후보를 **채택했을 때 실제로
# 나갈 문안**(맞춤법 교정까지 적용한 최종형)을 같이 보여 준다. 승인은 키 목록 파일로 받는다.
_CAND_N = 3


def candidates(ours, frags, n=_CAND_N):
    """우리 문안에 대한 정발 후보 [(유사도, rel, off, len, 정발본문, 최종 문안)]."""
    got = core(ours)
    if not got:
        return []
    pre, c, post = got
    if len(c) < 3:
        return []
    key = mnorm(c)
    if not key:
        return []
    scored = []
    for rel, off, _ln, t in frags:
        m = re.match(r"^(?:`[0-9]\s*)+", t)
        lead = m.group() if m else ""
        body = t[len(lead) :]
        if not _HANGUL.search(body):
            continue
        r = difflib.SequenceMatcher(None, key, mnorm(body)).ratio()
        if r < 0.45:
            continue
        post2 = (
            post
            if (post.strip(" ") == "" or not re.search(r"[.!?~…]$", body))
            else re.sub(r"^[ .!?~…]+", "", post)
        )
        scored.append(
            (
                r,
                rel,
                off + len(lead.encode("cp949")),
                len(body.encode("cp949")),
                body,
                # ⚠ derive 가 전역으로 부호 앞 공백을 지우므로 **최종 문안도 같게** 만들어야
                # sha 가드가 맞는다(안 맞으면 빌드가 선다 — 설계대로다, 2026-08-09).
                _PUNCT_SP.sub("", pre + R.spell_fix(body) + post2),
                pre,
                post2,
            )
        )
    scored.sort(key=lambda x: -x[0])
    out, seen = [], set()
    for row in scored:
        if row[5] in seen:
            continue
        seen.add(row[5])
        out.append(row)
        if len(out) >= n:
            break
    return out


def write_table():
    """결정표 → work/review/battle_table.md. 반환: 행 수."""
    frags = mondll_strings() + jeongbal_strings()
    rows = []
    deny = _deny()
    for k, ours, jp in ours_entries():
        cs = candidates(ours, frags)
        if cs and k not in deny and not decided(ours, cs[0]):
            rows.append((cs[0][0], k, jp, ours, cs))
    rows.sort(key=lambda r: -r[0])
    os.makedirs(REVIEW_DIR, exist_ok=True)
    p = os.path.join(REVIEW_DIR, "battle_table.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write(f"# 전투 문안 결정표 — 자체 번역 {len(rows)}건 (정발 후보 있는 것만)\n\n")
        f.write("**후보 열은 채택했을 때 실제로 나갈 문안**이다(맞춤법·띄어쓰기 교정 적용 후).\n")
        f.write("**맨 왼쪽 `선택` 칸에 1·2·3 을 적고** 이 파일을 그대로 `--accept` 에 넘긴다:\n\n")
        f.write(
            "```\npython3 tools/past_battle_jeongbal.py --accept work/review/battle_table.md\n```\n\n"
        )
        f.write("빈 칸은 건너뛴다(자체 번역 유지). 터미널에서 하나씩 고르려면 `--pick`.\n\n")
        f.write("| 선택 | 키 | 유사 | JP 원문 | 우리 번역 | ① 정발(최종) | ② | ③ |\n")
        f.write("| --- | --- | --- | --- | --- | --- | --- | --- |\n")

        def cell(x):
            """표 칸용 이스케이프 — 개행·파이프가 표를 깨뜨린다."""
            return x.replace("\\", "\\\\").replace("\n", "\\n").replace("|", "\\|")

        for _r, k, jp, ours, cs in rows:
            cells = [f"`{cell(c[5])}`<br>{c[0]:.2f} {c[1].split('/')[-1]}" for c in cs]
            cells += [""] * (_CAND_N - len(cells))
            f.write(
                f"|  | `{k}` | {cs[0][0]:.2f} | `{cell(jp)}` | `{cell(ours)}` | "
                + " | ".join(cells)
                + " |\n"
            )
    return len(rows), p


def accept(list_path):
    """승인 목록(`키 [후보번호]`)대로 정발 포인터로 바꾼다. 반환: [(k, 옛, 새)]."""
    from derive_text import _dos_file, _guard

    frags = mondll_strings() + jeongbal_strings()
    want = {}
    for ln in open(list_path, encoding="utf-8"):
        if ln.lstrip().startswith("|"):  # 결정표의 `선택` 칸을 그대로 읽는다
            # ⚠ 손으로 고친 표는 칸이 흐트러진다(빈 칸이 더 생기거나 `|1|` 로 붙거나).
            # 그래서 **키 칸을 먼저 찾고** 그 앞의 1/2/3 을 선택으로 본다.
            c = [x.strip().strip("`") for x in ln.strip().strip("|").split("|")]
            ki = next((i for i, x in enumerate(c) if re.fullmatch(r"[0-9a-f]{10}", x)), None)
            if ki is None:
                continue
            sel = next((x for x in c[:ki] if x in ("1", "2", "3")), None)
            if sel:
                want[c[ki]] = int(sel)
            continue
        # 목록 파일: `키 [후보번호]`. ⚠ 표를 넘겨도 되도록 **키 꼴이 아닌 줄은 무시**한다
        # (표의 설명문을 목록으로 읽어 `int('열은')` 로 죽었다, 2026-08-09).
        a = ln.split("#")[0].split()
        if not a or not re.fullmatch(r"[0-9a-f]{10}", a[0]):
            continue
        want[a[0]] = int(a[1]) if len(a) > 1 and a[1].isdigit() else 1
    path = os.path.join(TEXTMAP_DIR, "battle.json")
    tm = json.load(open(path, encoding="utf-8"))
    by = {e["k"]: e for e in tm["entries"]}
    changed, miss = [], []
    for k, ours, _jp in ours_entries():
        if k not in want:
            continue
        e = by.get(k)
        cs = candidates(ours, frags)
        idx = want[k] - 1
        if e is None or "ours" not in e or idx >= len(cs):
            miss.append(k)
            continue
        _r, rel, off, ln_, body, new, pre, post2 = cs[idx]
        if _dos_file(rel)[off : off + ln_].decode("cp949") != body:
            miss.append(k)
            continue
        if re.findall(r"%[scd]", new) != re.findall(r"%[scd]", ours):
            miss.append(k)  # 서식 계약 위반 — 안 넘긴다
            continue
        parts = []
        if pre:
            parts.append({"ours": pre})
        parts.append({"f": rel, "o": off, "l": ln_})
        if post2:
            parts.append({"ours": post2})
        fix = word_fix(body)
        e.pop("ours")
        e["parts"] = parts
        if fix:
            e["fix"] = fix
        e["sha"] = _guard(new)
        changed.append((k, ours, new))
    json.dump(tm, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if miss:
        print(f"  ⚠ 건너뜀 {len(miss)}건(후보 없음·서식 불일치): {miss[:6]}")
    return changed


def pick(min_ratio=0.60, out_path=None):
    """터미널에서 한 행씩 고른다 — 고를 때마다 **즉시 파일에 적어** 중간에 끊어도 안 잃는다."""
    frags = mondll_strings() + jeongbal_strings()
    out_path = out_path or os.path.join(REVIEW_DIR, "battle_accept.txt")
    done = set()
    if os.path.exists(out_path):
        for ln in open(out_path, encoding="utf-8"):
            a = ln.split("#")[0].split()
            if a:
                done.add(a[0])
    rows = []
    deny = _deny()
    for k, ours, jp in ours_entries():
        if k in done or k in deny:
            continue
        cs = candidates(ours, frags)
        if cs and not decided(ours, cs[0]) and cs[0][0] >= min_ratio:
            rows.append((cs[0][0], k, jp, ours, cs))
    rows.sort(key=lambda r: -r[0])
    print(f"고를 행 {len(rows)}건 (유사 {min_ratio}↑, 이미 정한 {len(done)}건 제외)")
    print("1/2/3=채택 · Enter=건너뜀 · q=저장하고 끝\n")
    f = open(out_path, "a", encoding="utf-8")
    n = 0
    for r, k, jp, ours, cs in rows:
        print(f"[{r:.2f}] {k}")
        print(f"  JP  {jp!r}")
        print(f"  우리 {ours!r}")
        for i, c in enumerate(cs, 1):
            print(f"  {i})  {c[5]!r}   ({c[0]:.2f} {c[1].split('/')[-1]})")
        try:
            a = input("  > ").strip().lower()
        except EOFError:
            a = "q"
        if a == "q":
            break
        if a in ("1", "2", "3") and int(a) <= len(cs):
            f.write(f"{k} {a}\n")
            f.flush()
            n += 1
        print()
    f.close()
    print(f"\n채택 {n}건 → {out_path}")
    print(f"반영: python3 tools/past_battle_jeongbal.py --accept {out_path}")
    return n


# ⚠ 일괄 채택을 0.70 으로 돌렸다가 **망가진 것들**이 나왔다(2026-08-09 검산):
#   `은(는) 소멸했다.`      → `은(는) 는 소멸했다.`   조사 중복(정발 조각도 `는` 으로 시작)
#   `썬더하운드C`           → `썬더하운드AC`          몬스터 개체 접미 파괴
#   `Gold를 훔쳤다.`        → `Gold훔쳤다.`           조사 소실
#   `…의 시체에 붉은 약을…` → `…붉은 약을…`           내용 손실
# 유사도만으로는 이 넷을 못 거른다. 아래 가드를 넣고, **최종 판정은 뜻으로 사람이 한다**.
_LEAD_JOSA = re.compile(r"^(?:은|는|이|가|을|를|에게|에|의)\s+")
_MONNAME = re.compile(r"^[가-힣][가-힣 ]{1,10}[A-Z]?$")


def risk(ours, cand):
    """후보를 그대로 채택하면 위험한가 — 표시 문자열(없으면 "")."""
    r = []
    if re.findall(r"%[scd]", cand[5]) != re.findall(r"%[scd]", ours):
        r.append("⚠서식")  # PS1 이 수치를 내려주는데 정발엔 자리가 없다 → 원본을 따른다
    got = core(ours)
    if got:
        w = got[1].split(" ")[0]
        if len(w) >= 2 and w not in cand[4]:
            r.append("⚠이름")  # 첫 어절이 후보에 없다 — 다른 몬스터 조각일 수 있다
    if _LEAD_JOSA.match(cand[4]):
        r.append("⚠조사")  # 정발 조각이 조사로 시작 — 우리 조사와 겹친다
    if _MONNAME.fullmatch(ours.strip()):
        r.append("⚠이름표")  # 몬스터명 자체 — 이름 표(monster_kr) 관할이다
    if len(mnorm(cand[4])) < len(mnorm(got[1] if got else "")) * 0.95:
        r.append("⚠손실")  # 후보가 우리보다 짧다 — 조사·내용이 날아간다
    return " ".join(r)


def _deny():
    """자동 채택 금지 목록 — 유사도가 높은데 뜻이 틀린 자리(사람이 못 박는다)."""
    p = os.path.join(os.path.dirname(TEXTMAP_DIR), "battle_deny.json")
    if not os.path.exists(p):
        return {}
    return json.load(open(p, encoding="utf-8")).get("deny", {})


def decided(ours, cand):
    """**규칙으로 결정이 끝난** 자리인가 — 사유(없으면 "").

    유저 확정 2026-08-09: 서식 불일치와 몬스터 이름표는 원본 방식을 따르기로 했다.
    ⚠ 결정이 끝난 걸 검토 목록에 남기면 "남은 일"이 부풀어 판단이 흐려진다 — 아예 뺀다."""
    if cand is not None and re.findall(r"%[scd]", cand[5]) != re.findall(r"%[scd]", ours):
        return "서식(원본 방식)"
    if _MONNAME.fullmatch(ours.strip()):
        return "몬스터 이름표(monster_kr 관할)"
    return ""


def bulk(min_ratio=0.70):
    """위험 표시가 없는 행을 ①로 일괄 채택. 반환: (반영, 확인목록)."""
    frags = mondll_strings() + jeongbal_strings()
    deny = _deny()
    take, review = [], []
    for k, ours, jp in ours_entries():
        if k in deny:
            continue
        cs = candidates(ours, frags)
        if not cs or decided(ours, cs[0]):
            continue
        rk = risk(ours, cs[0])
        if cs[0][0] >= min_ratio and not rk:
            take.append(k)
        elif cs[0][0] >= 0.60:
            review.append((cs[0][0], k, jp, ours, cs, rk))
    lp = os.path.join(REVIEW_DIR, "battle_bulk.txt")
    with open(lp, "w", encoding="utf-8") as f:
        for k in take:
            f.write(f"{k} 1\n")
    ch = accept(lp)
    review.sort(key=lambda r: -r[0])
    rp = os.path.join(REVIEW_DIR, "battle_review.md")
    with open(rp, "w", encoding="utf-8") as f:
        f.write(f"# 일괄 처리 후 **사람이 볼 것** {len(review)}건 (0.60↑)\n\n")
        f.write("⚠서식 = PS1 이 `%d`/`%s` 를 내려주는데 정발엔 자리가 없다 → **원본을 따른다**.\n")
        f.write("⚠이름 = 첫 어절이 후보에 없다 → **다른 몬스터 조각**일 수 있다.\n\n")
        f.write("| 선택 | 위험 | 키 | 유사 | JP 원문 | 우리 번역 | ① | ② | ③ |\n")
        f.write("| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")

        def cell(x):
            return x.replace("\\", "\\\\").replace("\n", "\\n").replace("|", "\\|")

        for r, k, jp, ours, cs, rk in review:
            cells = [f"`{cell(c[5])}`<br>{c[0]:.2f}" for c in cs] + [""] * (_CAND_N - len(cs))
            f.write(
                f"|  | {rk} | `{k}` | {r:.2f} | `{cell(jp)}` | `{cell(ours)}` | "
                + " | ".join(cells)
                + " |\n"
            )
    return len(ch), len(review), rp


def _split_at_tail(s, n_norm):
    """정규화 기준 뒤 n_norm 글자가 시작하는 **원문 인덱스**. 못 찾으면 None."""
    cnt = 0
    for i in range(len(s) - 1, -1, -1):
        if not re.match(r"[\s.,!?~…]", s[i]) and not re.match(r"`[0-9]", s[i : i + 2]):
            cnt += 1
        if cnt == n_norm:
            return i
    return None


def stitch():
    """**조각 잘림 회수** — 정발 조각이 우리 문안의 꼬리와 맞으면 앞은 우리 몫으로 남기고 잇는다.

    유저 지적 2026-08-09: "조각 잘림·조사 소실은 정발 어투 조합해서 넣을 수 있는 거 아니야?"
    맞다. MONDLL 은 한 메시지가 조각으로 쪼개져 있어 우리 블록의 **뒤쪽만** 덮는 일이 잦고,
    남는 앞부분은 대개 **조사**(`은 `)나 **고유명사**(`호`·`프람` — 정발은 인자로 주입하는데
    PS1 은 리터럴이다)다. 그건 문안이 아니라 우리 몫이니 `parts` 로 갈라 두면 된다.

    ⚠ 앞서 이걸 "앞이 잘리면 제외" 가드로 통째로 버렸다 — **버릴 게 아니라 갈랐어야 했다.**
    """
    from derive_text import _dos_file, _guard

    frags = mondll_strings() + jeongbal_strings()
    path = os.path.join(TEXTMAP_DIR, "battle.json")
    tm = json.load(open(path, encoding="utf-8"))
    by = {e["k"]: e for e in tm["entries"]}
    deny = _deny()
    changed, promoted = [], 0
    for k, ours, _jp in ours_entries():
        e = by.get(k)
        if e is None or "ours" not in e or k in deny:
            continue
        got = core(ours)
        if not got:
            continue
        pre, oc, post = got
        best = None
        for rel, off, _ln, t in frags:
            m = re.match(r"^(?:`[0-9]\s*)+", t)
            lead = m.group() if m else ""
            body = t[len(lead) :]
            if len(body) < 4 or not _HANGUL.search(body):
                continue
            # ⚠ **정규화한 채로** 꼬리를 맞춘다 — 공백·부호 차이 때문에 글자 그대로는 거의
            # 안 맞는다(그렇게 했다가 63건 중 9건만 잡혔다, 2026-08-09).
            nb = mnorm(body)
            no = mnorm(oc)
            if not nb or len(nb) >= len(no) or not no.endswith(nb):
                continue
            cut = _split_at_tail(oc, len(nb))
            if cut is None or cut == 0:
                continue
            if best is None or len(nb) > len(best[3]):
                best = (
                    rel,
                    off + len(lead.encode("cp949")),
                    len(body.encode("cp949")),
                    nb,
                    body,
                    cut,
                )
        if best is None:
            continue
        rel, off, ln, _nb, body, cut = best
        keep = oc[:cut]  # 조사·고유명사 — 우리 몫
        # 꼬리 부호는 정발 조각이 갖고 온다(안 그러면 `효과가 있다..` 처럼 겹친다).
        post2 = (
            post
            if (post.strip(" ") == "" or not re.search(r"[.!?~…]$", body))
            else re.sub(r"^[ .!?~…]+", "", post)
        )
        new = _PUNCT_SP.sub("", pre + keep + R.spell_fix(body) + post2)
        if re.findall(r"%[scd]", new) != re.findall(r"%[scd]", ours):
            continue
        if _dos_file(rel)[off : off + ln].decode("cp949") != body:
            continue
        parts = []
        if pre + keep:
            parts.append({"ours": pre + keep})
        parts.append({"f": rel, "o": off, "l": ln})
        if post2:
            parts.append({"ours": post2})
        fix = word_fix(body)
        e.pop("ours")
        e["parts"] = parts
        if fix:
            e["fix"] = fix
        e["sha"] = _guard(new)
        promoted += 1
        if new != ours:
            changed.append((k, ours, new))
    json.dump(tm, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return promoted, changed


def main():
    cands = jeongbal_strings() + ([] if "--apply" in sys.argv else mondll_strings())
    rows, hit = [], 0
    for k, ours, jp in ours_entries():
        n = norm(ours)
        if not n:
            continue
        scored = []
        for c in cands:
            m = norm(c[3])
            if m:
                scored.append((difflib.SequenceMatcher(None, n, m).ratio(), c))
        best = sorted(scored, key=lambda x: -x[0])[:3]
        if best and best[0][0] >= 0.60:
            hit += 1
        rows.append((k, ours, jp, best))
    if "--apply" in sys.argv:
        print(f"글자 동일 → 포인터 승격 **{apply_promotions()}건**")
        return
    if "--stitch" in sys.argv:
        n, ch = stitch()
        print(f"조각 잇기 **{n}건** 승격 · 그중 문안 변경 {len(ch)}건")
        for _k, a, b in ch[:40]:
            print(f"   {a!r}\n → {b!r}")
        return
    if "--bulk" in sys.argv:
        i = sys.argv.index("--bulk") + 1
        mr = float(sys.argv[i]) if i < len(sys.argv) and sys.argv[i][0].isdigit() else 0.70
        n, m, rp = bulk(mr)
        print(f"일괄 채택 **{n}건**(유사 {mr}↑, 위험 표시 없는 것) · 확인 대상 {m}건 → {rp}")
        return
    if "--pick" in sys.argv:
        i = sys.argv.index("--pick") + 1
        mr = float(sys.argv[i]) if i < len(sys.argv) and sys.argv[i][0].isdigit() else 0.60
        pick(mr)
        return
    if "--table" in sys.argv:
        n, p = write_table()
        print(f"결정표 {n}행 → {p}")
        return
    if "--accept" in sys.argv:
        lp = sys.argv[sys.argv.index("--accept") + 1]
        ch = accept(lp)
        print(f"승인 반영 **{len(ch)}건**")
        for _k, a, b in ch[:10]:
            print(f"   {a!r}\n → {b!r}")
        return
    if "--mondll" in sys.argv:
        ch = apply_mondll()
        print(f"몬스터별 메시지 정발 전환 — 문안 변경 **{len(ch)}건**")
        os.makedirs(REVIEW_DIR, exist_ok=True)
        rp = os.path.join(REVIEW_DIR, "battle_mondll_applied.md")
        with open(rp, "w", encoding="utf-8") as f:
            f.write(f"# 몬스터별 전투 메시지 — 정발 전환 {len(ch)}건 (표기 차이만)\n")
            for k, a, b in ch:
                f.write(f"\n- {k}\n      전: {a!r}\n      후: {b!r}\n")
        print(f"  → {rp}")
        return
    if "--align" in sys.argv:
        i = sys.argv.index("--align") + 1
        mr = float(sys.argv[i]) if i < len(sys.argv) and sys.argv[i][0].isdigit() else 0.80
        ch = apply_alignment(mr)
        print(f"정발 문안으로 맞춤 **{len(ch)}건** (문턱 {mr})")
        os.makedirs(REVIEW_DIR, exist_ok=True)
        rp = os.path.join(REVIEW_DIR, "battle_aligned.md")
        with open(rp, "w", encoding="utf-8") as f:
            f.write(f"# 전투 문안 정발 전환 {len(ch)}건 (문턱 {mr}) — 인게임 확인 대상\n")
            for k, a, b in ch:
                f.write(f"\n- {k}\n      전: {a!r}\n      후: {b!r}\n")
        print(f"  → {rp}")
        return
    print(f"자체 번역 배틀 엔트리 {len(rows)}건 · 정발 후보 0.60↑ **{hit}건**")
    print(f"정발 시스템 문구 코퍼스 {len(cands)}개 (ED1MAIN.EXE 0x{SYS_LO:X}~0x{SYS_HI:X})")
    if "--report" in sys.argv:
        os.makedirs(REVIEW_DIR, exist_ok=True)
        p = os.path.join(REVIEW_DIR, "past_battle_jeongbal.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"# 전투 문안 정발 짝 후보 — 자체 번역 {len(rows)}건 중 {hit}건 유망\n\n")
            f.write("`src` 로 승격할 때는 **서식(`%c`/`%s`/`%d`) 개수·순서**를 반드시 맞춘다.\n")
            for k, ours, jp, best in sorted(rows, key=lambda r: -(r[3][0][0] if r[3] else 0)):
                f.write(f"\n## {k}  (JP: {jp!r})\n")
                f.write(f"- 우리: {ours!r}\n")
                f.writelines(f"  - {r:.2f}  {rel} @0x{o:X} l={ln}  {t!r}\n" for r, (rel, o, ln, t) in best)
        print(f"  → {p}")


if __name__ == "__main__":
    main()
