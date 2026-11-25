"""번역 에이전트 결과(스테이징 파일) 정리 — 기계적으로 고칠 수 있는 것만 고치고 나머지를 보고한다.

    python3 tools/agent_merge.py <입력.txt> [<출력.txt>]    # 정리본을 쓰고 고친 건수·남은 의심 줄을 보인다

고치는 것: 문장 맨 앞 `… 말`→`…말`(규칙 2-11) · ASCII `~`→`～` · `...`→`…` · 같은 멤버 안 중복 색인(앞 것만 남긴다) · 줄 끝 공백 아닌 앞뒤 불필요 공백(끼움 토막 `~` 은 모르므로 **앞뒤 공백은 건드리지 않는다**).
보고만: 허용 글자 밖 문자 · `～.` 겹침 · `…` 뒤 붙은 글자.
"""

import re
import sys

OK = re.compile(r"[가-힣0-9A-Za-z .,!?…～()'\"「」『』·:;\-]")


def main(argv):
    src = argv[1]
    dst = argv[2] if len(argv) > 2 else src
    out, seen, fixed, dup, sus = [], set(), 0, 0, []
    cur = ""
    for ln in open(src, encoding="utf-8").read().split("\n"):
        if ln.startswith("## "):
            cur, seen = ln, set()
            out.append(ln)
            continue
        m = re.match(r"^(\d+) (.*)$", ln)
        if not m:
            if ln.strip():
                out.append(ln)
            continue
        i, t = m.group(1), m.group(2)
        if i in seen:
            dup += 1
            continue
        seen.add(i)
        n = t
        n = n.replace("...", "…").replace("~", "～")
        n = re.sub(r"^… (?=\S)", "…", n)
        if n != t:
            fixed += 1
        bad = {c for c in n if not OK.match(c)}
        if bad:
            sus.append(f"{cur[3:]} #{i} 글자 {''.join(sorted(bad))}")
        if "～." in n:
            sus.append(f"{cur[3:]} #{i} ～.")
        out.append(f"{i} {n}")
    open(dst, "w", encoding="utf-8").write("\n".join(out) + "\n")
    print(f"{src}: 고침 {fixed} · 중복 {dup} · 의심 {len(sus)}")
    for s in sus[:20]:
        print("  ?", s)


if __name__ == "__main__":
    main(sys.argv)
