#!/usr/bin/env python3
"""ED2 전투·컷신 창(`textmap/battle_ed2.json`·`battle.json`)의 **엔진 자동개행 부작용**을
전수로 잰다 — 첫칸공백·고아 꼬리·`\\n`과 자동개행 충돌.

**왜.** 이 표는 대사 트랙과 달리 krwrap 을 안 탄다 — `%c` 로 감싼 문자열을 그대로 태우면
PS1 엔진이 런타임에 **29 반각칼럼**에서 스스로 줄바꿈한다(`check_battle_wrap.py` 가 ED1
쪽 "꼬리 1~2칼럼" 만 본다; 이 도구는 ED2 대상이고 축이 다르다). 036·037·038·039(마스터
QA 2026-09-22) 를 손으로 고치다 **직접 두 번 밟았다** — 내가 짠 시뮬레이터 출력에
첫칸공백이 그대로 찍혀 있었는데 못 보고 넘어갔다(036), `\\n` 을 자동개행 경계(정확히
29칼럼)에 겹쳐 박아 빈 줄이 생겼다(039). 그래서 **사람 눈이 아니라 이 도구로 본다.**

**모델**(check_battle_wrap.py 와 같은 `cols()` — 한글·전각=2, 나머지=1):
문자 하나씩 반각칼럼을 누적하다 ①추가하면 29 를 넘는 문자를 만나면 그 앞에서 줄을 끊고
②원문에 박힌 `\\n` 을 만나면 무조건 끊는다. **검증**: 이 모델로 036 원문(쉼표 있음)을
돌리면 실제 화면(28·28·2, 마스터 스크린샷과 픽셀까지 일치)이 나온다 — 화면 실측으로
맞춘 모델이다.

**잡는 것 셋**:
  A 첫칸공백  — 줄바꿈 뒤 첫 글자가 공백(원문 공백이 다음 줄로 밀려 남음)
  B 고아 꼬리 — 줄이 3개 이상인데 마지막 줄이 아주 짧다(≤4칼럼) — 별도 창으로
                넘어가면 그 창에 그 짧은 내용만 혼자 남는다(036 원 증상)
  C `\\n` 충돌 — 원문에 박힌 `\\n` **바로 앞**이 이미 정확히 29칼럼(자동개행 경계와
                겹친다) — 039 에서 빈 줄이 생긴 그 자리. 원인은 아직 완전히는 안
                풀었다(에뮬 RE 필요) — 그래서 "겹치지 않게 피한다"만 기계적으로 본다.

⚠ **게이트가 아니다** — 스캔만으로는 문장을 고치거나 재배치해야 하는 자리도 섞여 있어
사람 확인이 낫다고 판단할 수 있다. 다만 **A(첫칸공백)·B(고아 꼬리)는 `--apply` 로 기계
처리가 된다** — 마스터 요청(2026-09-23 "처리까지 할 순 없어?")으로 추가했다. 단어(공백)
경계에서만 자르고 안전폭(28칼럼, 29 대신 1칸 여유를 둬 C 유형 충돌 자체를 구조적으로
피한다) 안에 눌러 담는 **낱말 단위 재래핑**이다 — 뜻·낱말은 한 글자도 안 바꾸고 줄
경계만 옮긴다. 부호(.!?,)는 앞말에 붙인다(기존 `_PUNCT_SP` 관용과 동일). C(`\\n` 충돌)는
**손을 안 댄다** — 기존 개행이 번역자의 의도적 문단 구분일 수 있어 재래핑이 그 구조를
지운다(재래핑하면 A·B 도 같이 없어지니 `--apply` 가 C 도 부수적으로 고치긴 한다, 다만
의도 파괴 여지가 있어 전량 확인은 권한다).

  python3 tools/check_battle_grid_wrap.py [-v]
  python3 tools/check_battle_grid_wrap.py --apply [-v]   # A·B(부수적으로 C 도) 재래핑, sha 갱신까지
"""

import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXTMAP_DIR = os.path.join(ROOT, "textmap")
COLS = 29
SAFE = 28  # --apply 재래핑 목표폭 — 29 대신 써서 C 유형(29칼럼 경계 충돌) 자체를 피한다
TABLES = ("battle_ed2.json", "battle.json")

_CTRL = re.compile(r"%c|%s|%d|[\x17\x1a\x1b]")
_PUNCT_SP = re.compile(r"[ \n]+(?=[!?,]|\.(?!\.))")  # derive_text.py 의 관용과 동일
_NAMEPLATE = re.compile(r"^(%c[^%]{1,10}%c\n)")


def cols(s):
    return sum(2 if ord(c) > 0x2000 else 1 for c in s)


def strip_ctrl(s):
    """`%c`(창 경계)는 폭 0 으로 완전히 지운다 — 그 자리에서 줄이 안 끊긴다(이름판
    분리는 실제로 별도 `\\n` 이 옆에 있어 그걸로 갈린다). `%s`·`%d` 는 폭을 모르니
    이 축(고정 문자열)에서는 애초에 안 나온다 — 나오면 스캔 대상에서 뺀다."""
    return _CTRL.sub("", s)


def wrap(body):
    """char-greedy, `\\n` 은 무조건 끊음 — 036 실측으로 검증된 모델."""
    cur, line, lines = 0, "", []
    for ch in body:
        if ch == "\n":
            lines.append(line)
            line, cur = "", 0
            continue
        w = 2 if ord(ch) > 0x2000 else 1
        if cur + w > COLS:
            lines.append(line)
            line, cur = "", 0
        line += ch
        cur += w
    lines.append(line)
    return lines


def scan_entry(raw):
    """`ours` 원문(1건, `\\n` 포함 가능) → 문제 목록. 이름판(`%c이름%c\\n`)은 뺀다
    — 그 뒤 첫 `\\n` 까지는 씬 진입 헤더라 29칼럼 축 밖이다."""
    s = strip_ctrl(raw)
    # 이름판 접두(있으면) 떼기 — `%c` 를 지웠으니 이제 문자열 맨 앞 조각 + 첫 \n 로 판별.
    # 이름판은 항상 "이름\n" 으로 시작해 본문과 갈린다(정본 관용, patch_ed2_battle.py 참조).
    body = s
    if "\n" in s:
        head, rest = s.split("\n", 1)
        if head and cols(head) <= 12:  # 이름판은 짧다 — 본문 첫 줄과 헷갈릴 일 없음
            body = rest
    if "%" in body:  # 여전히 남은 치환자(%s 등) — 길이를 몰라 이 축에서 못 잰다
        return []
    # 조사 훅 이어붙임 조각(예: "은(는) 기묘한…") — 실제로는 **앞 조각(괴물 이름 등)에
    # 이어 붙어 렌더**되니 이 조각 혼자 0칸부터 잰 결과는 무효다. 이 표에 실제로
    # 나오는 조사 병기 넷만 본다(과하게 넓히면 진짜 문장의 조사 낱말과 헷갈린다).
    if re.match(r"^(은\(는\)|이\(가\)|을\(를\)|와\(과\))", body):
        return []
    # 제목·크레딧 카드(장 구분·엔딩 등)는 **의도된 가운데 정렬**이라 뺀다 — 공백 여럿을
    # 연달아 써서 맞추는 관용이고, 우리가 잡으려는 "밀려난 공백 딱 하나"와는 다르다.
    if re.search(r"  ", body):  # 공백 2개 이상 연속 = 정렬용, 자동개행 부작용이 아니다
        return []
    lines = wrap(body)
    probs = []
    for i, l in enumerate(lines):
        # 밀려난 공백은 **정확히 하나**다(원문 낱말 구분자 하나가 넘어온 것) — 여럿이면
        # 위에서 이미 걸렀어야 정상이니 방어적으로 한 번 더 본다.
        if i > 0 and l.startswith(" ") and not l.startswith("  "):
            probs.append(f"A 첫칸공백 line{i}: {l!r}")
    if len(lines) >= 3 and cols(lines[-1]) <= 4 and lines[-1].strip():
        probs.append(f"B 고아 꼬리({cols(lines[-1])}칼럼): {lines[-1]!r}")
    # C — 원문에서 실제 "\n" 위치 찾아, 그 앞 조각이 정확히 COLS 인지 본다(축적 기준
    # body 시작부터). wrap() 은 이미 한 번 끊었으니 원문을 직접 다시 훑는다.
    # ⚠ **뒤에 실제 글자가 이어질 때만** 잰다 — 문자열 맨 끝(그 뒤로 렌더될 내용이
    # 없는 `\n`)은 겹쳐도 눈에 보이는 빈 줄이 안 생긴다(039 는 뒤에 "건네고…"가
    # 이어졌기 때문에 문제였다).
    cur = 0
    for i, ch in enumerate(body):
        if ch == "\n":
            if cur == COLS and body[i + 1 :].strip():
                probs.append(f"C \\n 충돌 @{i}: 직전이 정확히 {COLS}칼럼(자동개행 경계와 겹침)")
            cur = 0
            continue
        cur += 2 if ord(ch) > 0x2000 else 1
    return probs


def word_wrap(body, safe=SAFE):
    """낱말(공백) 경계에서만 자르는 재래핑 — `\\n` 도 공백처럼 접어 통째로 다시 흐른다.
    부호 앞은 `_PUNCT_SP` 로 붙여 **낱말이 부호 하나만 남고 혼자 도는 것**(365a7b88c2·
    c8840d339f 실측)을 막는다. 반환은 `\\n` 으로 이은 줄 목록 — 낱말·부호 자체는 원문과
    바이트까지 같다(순서·간격만 바뀐다).

    ⚠ **원문의 `\\n` 이 공백 없이(단어 한가운데를) 자르는 자리면 이 함수가 속는다**
    (920c7bec3b 실측 — 원문이 "가까워졌\\n습니다"(공백 없음, 원 번역자가 칸 부족으로
    어절 중간을 억지로 끊은 자리)였는데, 여기서 `\\n`→공백으로 접어 "가까워졌 습니다"
    가 됐다 — 없던 공백이 생겨 오탈자처럼 보였다). **`--apply -v` 로 전 건 사람이
    한 번은 봐야 한다** — 자동 검산(`scan_entry` 재확인)은 "칸을 넘는지"만 보지
    "말이 되는지"는 못 본다. 잡히면 그 항목만 손으로 다시 잇는다(위 사례가 선례)."""
    flat = _PUNCT_SP.sub("", body.replace("\n", " "))
    words = [w for w in flat.split(" ") if w]
    lines, cur, curcol = [], "", 0
    for w in words:
        wc = cols(w)
        add = wc + (1 if cur else 0)
        if curcol + add > safe:
            lines.append(cur)
            cur, curcol = w, wc
        else:
            cur = cur + (" " if cur else "") + w
            curcol += add
    lines.append(cur)
    return "\n".join(lines)


def rewrap_entry(raw):
    """`ours` 원문 통째로 → 재래핑된 `ours`. 이름판(`%c이름%c\\n`)·꼬리 `%c` 는 그대로
    두고 **본문만** 다시 흐른다. 반환이 `None` 이면 이 형태는 못 다룬다(예: 남은 `%s`)."""
    m = _NAMEPLATE.match(raw)
    prefix = m.group(1) if m else ""
    rest = raw[len(prefix) :]
    suffix = "%c" if rest.endswith("%c") else ""
    body = rest[: -len(suffix)] if suffix else rest
    if "%" in body:
        return None
    return prefix + word_wrap(body) + suffix


_DERIVE_PUNCT_SP = re.compile(r"[ ]+(?=[!?,]|\.(?!\.))")  # derive_text.py 의 정본 그대로 — sha 가드는 이거라야 맞는다


def guard(s):
    return hashlib.sha1(_DERIVE_PUNCT_SP.sub("", s).encode("utf-8")).hexdigest()[:8]


def apply_fixes(verbose=False):
    """A·B(부수적으로 C 도) 자동 재래핑 — textmap 파일을 직접 고치고 `sha` 도 갱신한다."""
    total = 0
    for tbl in TABLES:
        path = os.path.join(TEXTMAP_DIR, tbl)
        if not os.path.exists(path):
            continue
        doc = json.load(open(path, encoding="utf-8"))
        n = 0
        for e in doc.get("entries", ()):
            if "ours" not in e:
                continue
            if not scan_entry(e["ours"]):
                continue
            new_ours = rewrap_entry(e["ours"])
            if new_ours is None or new_ours == e["ours"]:
                continue
            remaining = scan_entry(new_ours)
            if remaining:  # C 류처럼 재래핑으로 못 없앤 것 — 손대지 않는다(사람 판정)
                if verbose:
                    print(f"  ⏭ {tbl}:{e['k']} 재래핑해도 남음: {remaining}")
                continue
            if verbose:
                print(f"  ✎ {tbl}:{e['k']}\n      전: {e['ours']!r}\n      후: {new_ours!r}")
            e["ours"] = new_ours
            e["sha"] = guard(new_ours)
            n += 1
        if n:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, indent=1)
                f.write("\n")
        print(f"  {tbl}: {n}건 재래핑")
        total += n
    print(f"  ✅ 전투/컷신 창 자동 재래핑 {total}건 — 재빌드·check_battle_grid_wrap 재확인 필요")
    return total


def scan(verbose=False):
    hits = []
    for tbl in TABLES:
        path = os.path.join(TEXTMAP_DIR, tbl)
        if not os.path.exists(path):
            continue
        doc = json.load(open(path, encoding="utf-8"))
        for e in doc.get("entries", ()):
            if "ours" not in e:
                continue
            probs = scan_entry(e["ours"])
            if probs:
                hits.append((tbl, e["k"], e["ours"], probs))
    for tbl, k, ours, probs in hits if verbose else hits[:10]:
        print(f"  {tbl}:{k}")
        for p in probs:
            print(f"      {p}")
    if len(hits) > 10 and not verbose:
        print(f"  … 외 {len(hits) - 10}건 더(`-v` 로 전량)")
    print(f"  {'✅' if not hits else '⚠'} 전투/컷신 창 자동개행 부작용 {len(hits)}건")
    return len(hits)


if __name__ == "__main__":
    if "--apply" in sys.argv:
        apply_fixes("-v" in sys.argv)
        sys.exit(0)
    scan("-v" in sys.argv)  # ⚠ 게이트가 아니다(check_battle_wrap.py 와 같은 관용) — 항상 0
