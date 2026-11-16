"""조판 결과 전수 계수 게이트(공통 번역 규칙 2-1·2-3·2-4·2-5·2-6·2-7·2-16 ③) — **실제로 굽는 바이트**(`script_kr.page_plan` 결과)를 쪽·줄로 풀어 센다.

    python3 tools/check_typeset.py [list]

축(객관 결함은 0 이어야 한다):
  첫 칸 공백(2-5)   줄(24칸 단위) 머리가 공백인데 줄에 글이 있다
  고아 부호(2-3)    줄 머리가 닫는·끝 부호(`. , ! ? ) 」 』`)다 — 앞 줄에서 떨어져 나온 부호
  빈 줄 개행(2-4)   쪽 한복판에 글자 없는 줄(꽉 찬 줄 뒤 개행·빈 조각)
  부호 뒤 공백(2-1) `, . ! ?` 바로 뒤에 한글·영문이 붙음(숫자 소수점·`?!` 겹침 제외)
  부호 앞 공백(2-2) · ?…·!… 순서(2-12) · …뒤 공백(2-11, 음절 끊기·인용 조사 예외)
  넘침(2-7)         `typeset.over_limit_pages` — 줄이 사라질 수 있는 쪽
  낱말 속 접힘(2-6) 줄 머리가 용언 어간(해·하·했…)인데 앞 줄이 연결어미·조사 아닌 한글로 끝나고 꽉 참 — 「대신 / 해 주는」꼴
한 줄 문장(2-10)   한 줄(24칸)에 들어가는 문장이 같은 쪽 안에서 두 줄로 갈림 — 조판기가 고칠 수 있는 쪽(흐름 조판)은 0 이어야 한다. 끼움 연산이 낀 토막·공유 조각·쪽 3줄 한도로
                    못 고치는 쪽은 `typeset_baseline.json` 의 남김 수(래칫 — 늘면 실패)로 둔다.
쉼표(2-13)         「뺀다」 부류(접속부사 · 주제·부사어 뒤 · 짧은 연결어미 뒤 · 줄 끝) 후보 수 — 규칙 예시와 꼴이 똑같은 것은 문안에서 뺐고, 남은 것(남기는 부류와 애매한 것)은 부류별 수를 `typeset_baseline.json` 에 사유와 함께 둔다(래칫).
여러 창 균등 분배(2-16 ③ — 마지막 창 한 어절 · 쪽 끝 한 어절 고아 · 창 줄 수 치우침)는 `linemetrics.py` 가 세므로 여기선 그 값(h·h2·a·b)을 같이 찍는다.
색(4-6): ED4 는 글자 열 안에 색 코드가 없다 — 색·연출은 스크립트 구간 연산이고 재삽입이 글자 표만 갈아 끼우므로 원판 바이트 그대로다. 누락·번짐 0 은 `check_ctrl_codes.py` 가 바이트로 대조한다(여기선 안 센다).
UI 문자열(`ui_ed4.json`)은 부호 뒤 공백만 본다(칸 맞춤 공백이 있는 표라 머리 공백은 안 본다).
양성 대조(`selftest`)가 가짜 줄에서 각 축을 잡는지 먼저 확인한다.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", ".."))
import build
import glob
import linemetrics
import script_kr
import typeset

CLOSERS = set(".,!?)」』:;")
SPACE_BEFORE = re.compile(r"(?<=[가-힣A-Za-z0-9]) +(?=[,.!?])")  # 2-2 부호 앞 공백
Q_ELLIPSIS = re.compile(r"[?!]…")  # 2-12 물음표·느낌표 뒤 말줄임
ELL_GLUE = re.compile(r"(?<=[가-힣])…(?=[가-힣A-Za-z0-9])")  # 2-11 말줄임 뒤 말이 바로 이어짐
ELL_OK_NEXT = re.compile(r"…(라고|요|냐|라|이라|고)")  # 인용·종결 조사는 붙인다
ELL_CHAIN = re.compile(r"[가-힣]…[가-힣]…|([가-힣])…\1")  # 한 낱말을 음절마다 끊어 말함 · 같은 소리 되풀이(예외)
PUNCT_GLUE = re.compile(r"[,.!?](?=[가-힣A-Za-z])")
SUFFIX_HEAD = re.compile(r"^(해|하|했|해서|해야|하며|하여|하고|하면|한다|합니다|해도)( |$)")
# 줄 머리가 용언 어미 한 글자여도 앞 줄이 제 낱말로 끝난 경우(닫은 목록) — (앞 줄 끝 어절, 뒷 줄 머리 어절)
SPLIT_OK = set()
JOINT_END = set("고면는도서며데니라만을를이가은에")  # 앞 줄이 연결어미·조사로 끝나면 제 어절이다(「일이라고는 / 해도」)


def chunks(text, cols=typeset.COLS):
    return [text[k : k + cols] for k in range(0, len(text), cols)]


def line_defects(lines):
    """한 쪽의 줄 목록 → [(축, 줄)] — 빈 조각은 None."""
    out = []
    body = [ln for ln in lines if ln is not None]
    for n, ln in enumerate(body):
        if not ln.strip():
            if 0 < n < len(body) - 1 or (n < len(body) - 1 and any(x.strip() for x in body[n + 1 :])):
                if any(x.strip() for x in body[:n]) and any(x.strip() for x in body[n + 1 :]):
                    out.append(("빈 줄", ln))
            continue
        if ln[0] == " ":
            out.append(("첫 칸 공백", ln))
        if ln.lstrip()[0] in CLOSERS and any(x.strip() for x in body[:n]):  # 쪽 첫 줄의 단독 부호(원판 조각이 부호 하나뿐)는 고아가 아니다
            out.append(("고아 부호", ln))
        m = PUNCT_GLUE.search(ln)
        if m and not re.search(r"\d[.,]\d", ln[max(0, m.start() - 1) : m.end() + 1]):
            out.append(("부호 뒤 공백", ln))
        m2 = ELL_GLUE.search(ln)
        if m2 and not ELL_CHAIN.search(ln) and not ELL_OK_NEXT.match(ln[m2.start() :]):
            out.append(("…뒤 공백(2-11)", ln))
        if SPACE_BEFORE.search(ln.rstrip()):
            out.append(("부호 앞 공백", ln))
        if Q_ELLIPSIS.search(ln):
            out.append(("?…·!… 순서", ln))
        if n and SUFFIX_HEAD.match(ln.lstrip()):
            prev = body[n - 1].rstrip()
            if prev and "가" <= prev[-1] <= "힣" and prev[-1] not in JOINT_END and len(body[n - 1]) >= typeset.COLS - 1 and (prev.split(" ")[-1], ln.split(" ")[0]) not in SPLIT_OK:
                out.append(("낱말 속 접힘", prev[-8:] + "|" + ln[:8]))
    return out


BASELINE = os.path.join(HERE, "..", "typeset_baseline.json")
PUA = re.compile("[\ue000-\uf8ff]")  # 끼움 연산 자리표시(이름·수)
_CONJ = r"(?:그리고|그러나|하지만|그래서|그런데|그러면|그럼|또한|다만|그래도|따라서|그러니까|그러므로|한편|게다가|더구나|하긴)"
_TIME = r"(?:지금|이제|오늘|내일|어제|그때|처음|먼저|우선|역시|정말|사실|실은|물론|결국|아직|이미|벌써|예전|옛날|언젠가|요즘|최근|아까|방금|혹시|아마|분명|확실히|결코|전혀|도저히)"
_ST = r"(?:^|(?<=[.?!…] ))"  # 문장 머리
COMMA_RE = {
    "접속부사 뒤": re.compile(_ST + _CONJ + ","),
    "주제·부사어 뒤": re.compile(_ST + r"(?:(?:\S+ ){0,2}\S*(?:은|는|에는|에서는|에게는|으로는|로는|에도|까지는|부터는)|" + _TIME + r"(?:에|에는|은|는|도)?),"),
    "짧은 연결어미 뒤": re.compile(_ST + r"(?:\S+ ){0,2}\S*(?:하고|하며|으며|하여|해서|이며|였고|었고|했고|받으며|면서|서|고|며),"),
}
COMMA_SKIP = re.compile(r"(?:아이고|에고|어이고|이고|나이고),")


def comma_counts():
    """{부류: 수} — 대본 조각(`script/*.json`)의 쉼표 후보. 줄 끝은 굽는 줄에서 센다(`measure`)."""
    cnt = {k: 0 for k in COMMA_RE}
    for f in sorted(glob.glob(os.path.join(HERE, "..", "script", "*.json"))):
        with open(f, encoding="utf-8") as fh:
            for v in json.load(fh)["segments"].values():
                t = v.get("kr") or ""
                for k, rx in COMMA_RE.items():
                    cnt[k] += sum(1 for m in rx.finditer(t) if not COMMA_SKIP.search(m.group(0)))
    return cnt


def measure():
    members = build.identity_gate({})
    rows_all = script_kr.load_all()
    found = []
    pages = 0
    resid = {"문장 갈림 남김(끼움·공유 조각)": 0, "문장 갈림 남김(쪽 3줄 한도)": 0, "줄 끝 쉼표": 0}
    for key, rows in rows_all.items():
        mem = members[key]
        texts, _ = script_kr.page_plan(mem, rows)
        for msg in typeset.windows(mem):
            for pg in msg:
                if not pg or any(i not in texts for i in pg if rows.get(i, {}).get("kr")):
                    continue
                pages += 1
                lines = []
                for i in pg:
                    t = texts.get(i, "")
                    lines.extend(chunks(t) if t else [None])
                for ax, ln in line_defects(lines):
                    found.append((ax, key[1], pg[0], ln))
                body = [x.rstrip() for x in lines if x and x.strip()]
                resid["줄 끝 쉼표"] += sum(1 for x in body[:-1] if x.endswith(","))
                bad = typeset.one_line_sentences(body, final=pg is msg[-1])
                if bad:
                    if getattr(pg, "rigid", False) or any(PUA.search(x) for x in body):
                        resid["문장 갈림 남김(끼움·공유 조각)"] += len(bad)
                    elif typeset._sentence_lines(body, typeset.COLS, len(pg)) != body:
                        found.append(("한 줄 문장 갈림(2-10)", key[1], pg[0], " / ".join(body)))
                    else:
                        resid["문장 갈림 남김(쪽 3줄 한도)"] += len(bad)
        seg_lens = {i: len(t) for i, t in texts.items()}
        for pg, i in typeset.over_limit_pages(mem, seg_lens):
            found.append(("넘침", key[1], pg[0], f"조각 {i}"))
    ui = json.load(open(os.path.join(HERE, "..", "ui_ed4.json"), encoding="utf-8"))["strings"]
    for off, v in ui.items():
        kr = v.get("kr") or ""
        m = PUNCT_GLUE.search(kr)
        if m and not re.search(r"\d[.,]\d", kr[max(0, m.start() - 1) : m.end() + 1]):
            found.append(("부호 뒤 공백(UI)", off, 0, kr))
    resid.update({"쉼표: " + k: v for k, v in comma_counts().items()})
    return pages, found, resid


def baseline_problems(resid):
    """남김 수 래칫 — 늘었으면 [사유], 줄었으면 알림(freeze)."""
    base = json.load(open(BASELINE, encoding="utf-8"))["남김"]
    bad, down = [], []
    for k, v in resid.items():
        b = base.get(k, {}).get("수")
        if b is None:
            bad.append(f"기준선에 없는 부류 「{k}」(수 {v})")
        elif v > b:
            bad.append(f"「{k}」 {v} > 기준선 {b}")
        elif v < b:
            down.append(f"{k} {b}→{v}")
    return bad, down


def selftest():
    assert typeset.one_line_sentences(["가나다 라마바", "사아자."]) and not typeset.one_line_sentences(["가나다.", "라마바 사아자."])
    assert COMMA_RE["접속부사 뒤"].search("그래서, 뭐 좀 썼어?") and not COMMA_RE["접속부사 뒤"].search("그래서 뭐 좀 썼어?")
    assert COMMA_RE["주제·부사어 뒤"].search("이 섬에는, 뭔가 있다.") and COMMA_RE["주제·부사어 뒤"].search("먼저, 조사해 오게.")
    assert COMMA_RE["짧은 연결어미 뒤"].search("바스터도 죽고, 루티스는") and not COMMA_RE["짧은 연결어미 뒤"].search("바스터도 죽고 루티스는")
    assert ("첫 칸 공백", " 가나") in line_defects([" 가나"])
    assert any(a == "고아 부호" for a, _ in line_defects(["가나다라", ". 마바"]))
    assert any(a == "빈 줄" for a, _ in line_defects(["가나", "   ", "다라"]))
    assert any(a == "부호 뒤 공백" for a, _ in line_defects(["가나,다라"]))
    assert not line_defects(["가나, 다라.", "마바 1.5배"])
    assert any(a == "부호 앞 공백" for a, _ in line_defects(["가나 ."]))
    assert any(a == "?…·!… 순서" for a, _ in line_defects(["가나?…"]))
    assert any(a.startswith("…뒤") for a, _ in line_defects(["잠을 못…아"]))
    assert not line_defects(["닿…지…않…는…다…", "컬리야…라고 해"])
    assert any(a.startswith("낱말 속") for a, _ in line_defects(["가" * 23 + "대신", "해 주는"]))
    assert not line_defects(["가나다", "해 주는"])  # 앞 줄이 짧으면(어절 끝) 후보 아님


def main(argv):
    selftest()
    pages, found, resid = measure()
    bad_base, down = baseline_problems(resid)
    cnt = {}
    for ax, *_ in found:
        cnt[ax] = cnt.get(ax, 0) + 1
    print("남김(기준선 안) " + " · ".join(f"{k} {v}" for k, v in resid.items()))
    for b in bad_base:
        print("  ✗", b)
    if down:
        print("⚠ 기준선보다 줄었다 — typeset_baseline.json 의 수를 내린다: " + ", ".join(down))
    lm, _ = linemetrics.measure()
    print(f"조판 전수 {pages}쪽 · 양성 대조 ✓ · " + (" · ".join(f"{k} {v}" for k, v in sorted(cnt.items())) or "결함 0"))
    print("2-16 ③ 지표(linemetrics) " + " · ".join(f"{k}={lm[k]}" for k in ("a", "b", "h", "h2")))
    if len(argv) > 1 and argv[1] == "list":
        for ax, m, i, ln in found:
            print(f"  {ax}\t{m}\t{i}\t{ln!r}")
    else:
        for ax, m, i, ln in found[:30]:
            print(f"  ✗ {ax} {m} 조각 {i}: {ln!r}")
    return 1 if (found or bad_base) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
