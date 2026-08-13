#!/usr/bin/env python3
"""화면에 **나가면 안 되는 바이트열**을 센다 — 마크업 유출·조사 병기 노출.

**왜.** 다른 검출기들은 「있어야 할 것이 있는가」(창 수·인자·일본어 잔존)를 보는데, 이건
**「없어야 할 것이 없는가」**를 본다. mcpads 패처의 `validate_translations` 가 *"a small set of
forbidden Korean strings must never appear"* 로 같은 자리를 지킨다(2026-08-11 흡수).

⚠ **반드시 바이트 층에서 본다.** 페이지 문자열에는 센티널(`\\ue000` 개행 마커 · `\\x1b` 수치
주입 · `은(는)` 병기)이 **정상적으로** 들어 있다 — 거기서 세면 98건이 나오는데 전부 오탐이다
(실측 2026-08-11). 인코딩을 지나 실제로 블록에 실리는 바이트만이 화면이다.

검사 항목:

- **마크업 유출**(`{n}`·`{p}`·`{spk}`) — 정발 마크업이 안 걷힌 채 나갔다
- **이스케이프 리터럴**(`\\xNN`) — 제어코드가 글자로 나갔다
- **조사 병기**(`(는)`·`(가)`) — ⚠ 이건 **전부 오류가 아니다**. 런타임 조사 훅이 표시 직전에
  줄이므로 대사 렌더러 위에서는 정상이다. 문제는 **훅이 안 타는 자리**다 — 상점 프롬프트에서
  실제로 새어 나왔고(2026-07-27 유저 QA `해독초은 (는)`), 그래서 종류를 갈라 보고한다.

  python3 tools/check_forbidden.py         # 요약
  python3 tools/check_forbidden.py -v      # 자리마다
"""

import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import hangul_map
import reinsert_kr_pilot as R


def _josa_re():
    """`(는)`·`(가)` 를 게임 인코딩 바이트로 — 병기는 이 두 꼴만 쓴다."""
    alt = b"|".join(re.escape(hangul_map.syllable_sjis(c).to_bytes(2, "big")) for c in ("는", "가"))
    return re.compile(rb"\((?:" + alt + rb")\)")


BAN = {
    "마크업 유출": re.compile(rb"\{(n|p|/?spk)\}"),
    "이스케이프 리터럴": re.compile(rb"\\x[0-9A-Fa-f]{2}"),
}


# ── 리포에 남으면 안 되는 것: 정발 번역문 ────────────────────────────────────
# 화면 바이트가 아니라 **커밋되는 파일**을 본다. 축이 다르지만 묻는 것은 같다 —
# 「없어야 할 것이 없는가」.
#
# **왜.** `[kr] 문장급 문안은 코드에 임베드 금지`(CLAUDE.md)인데, 새는 자리가 문안 파일만이
# 아니었다(2026-08-13 전수). `align_overrides` 의 `subs` 는 **찾을 문자열이 곧 정발 원문**
# 이었고, `note` 는 판단 근거로 대사를 인용했고, **조판 테스트 픽스처**에도 실제 대사가
# 들어 있었다 — 마지막 것은 문안 파일만 훑어서는 영영 안 잡힌다.
#
# 기준은 **정발 코퍼스**다(초안이 아니라). 초안은 `work/` 라 머신에 없을 수 있는데 코퍼스는
# 빌드가 항상 만든다. 코퍼스가 없으면 검사를 건너뛴다(원본 없는 머신에서 게이트가 죽지 않게).
#
# ⚠ **관용·상투 표현은 안 센다.** 저작권은 창작적 **표현**을 보호하는데 인사·응대 상투구는
# 그 선을 못 넘는다 — `왕자님. 어서 오십시오.` 는 원문을 옮기면 누가 해도 그 근처라
# **표현의 선택지가 없다**. 그런 자리는 우리가 다시 써도 같은 말이 나오므로, 잡아 봐야
# 고칠 수가 없다(유저 판정 2026-08-13: "관용적인 표현은 코드에 넣고, 번역자의 노력이 들어간
# 대사만 포인터로").
#
# ⚠ **20자는 법적 경계가 아니라 기계적 선이다.** 실측으로 그 위아래가 성격이 갈렸다 —
# 미만은 전부 인사·응대(19건), 이상은 전부 실제 문장(7건)이었다. 애매하면 **사람이 본다**.
#
# ⚠ **낮게 잡으면 게이트가 죽는다.** 12자로 두면 상투구 19건이 영구히 걸려 늘 빨간불이 되고,
# 그러면 진짜 유출이 섞여도 묻힌다(CLAUDE.md 「늘 빨간불이면 아무도 안 본다」).
MIN_LEN = 20
SCAN_EXT = (".json", ".py", ".md", ".sh", ".html")
# ⚠ **레포 상대경로로 비교한다.** 절대경로로 하면 레포가 `/root/work/...` 같은 자리에 있을 때
# `work` 가 **모든 디렉터리에 매칭돼** 검사가 통째로 건너뛰어진다 — 게이트가 조용히
# 초록불이 된다(2026-08-13 실측, 일부러 심은 문장을 못 잡아 발견했다).
SKIP_DIR = (".git", "work", ".local", "originals", "vendor", ".venv", "node_modules")
# 우리 문안인데 코퍼스에도 있는 자리 — 근거를 적고 통과시킨다.
ALLOW = {
    # 아이템 획득 안내는 게임 전역 공용 시스템 문구라 정발과 같은 말이 될 수밖에 없다.
    "을(를) 손에 넣었습니다.",
    "는{p}을(를) 발견했습니다.",
}


def _corpus_lines():
    """정발 코퍼스의 문장 집합 — 마크업·제어를 벗기고 길이로 거른다."""
    import glob
    import json

    from common import OUT_DIR

    out = set()
    for f in glob.glob(os.path.join(OUT_DIR, "dos_kr", "**", "*.json"), recursive=True):
        try:
            doc = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        ents = doc.get("entries") if isinstance(doc, dict) else doc
        if not isinstance(ents, list):
            continue
        for e in ents:
            if not isinstance(e, dict):
                continue
            try:
                t = R.corpus_text(e.get("text", ""))
            except Exception:
                continue
            for seg in re.split(r"\{p\}", t):
                # ⚠ **화자 마크업을 뗀 본문도 코퍼스로 친다.** 코퍼스는 `{spk}병사{/spk} 이봐…`
                # 인데 우리 정본(`script/*.json`)의 `t` 는 **본문만** 담는다 — 마크업만 지우면
                # `병사` 가 본문 앞에 눌어붙어, 본문이 정발과 한 글자도 다르지 않아도 축자
                # 일치가 안 나 **조용히 통과한다**. 실측 4건 보고 → 169건(2026-08-13).
                for s in {seg, re.sub(r"^\s*\{spk\}[^{}]*\{/spk\}", "", seg)}:
                    s = re.sub(r"\{[^}]*\}", "", s)
                    s = re.sub(r"\\x[0-9A-Fa-f]{2}", "", s).strip()
                    # ⚠ **한글이 없으면 문안이 아니다** — `..............` 같은 부호 덩어리가
                    # 길이만으로 걸려 오탐을 만든다(실측 12곳). 저작권 대상은 표현이지 부호가
                    # 아니다.
                    if len(s) >= MIN_LEN and s not in ALLOW and re.search(r"[가-힣]{3,}", s):
                        out.add(s)
    return out


def scan_repo(verbose=False):
    """커밋되는 파일에 정발 번역문이 있는가."""
    lines = _corpus_lines()
    if not lines:
        print("  ⏭ 정발 코퍼스가 없어 건너뜀(원본이 있는 머신에서 검사된다)")
        return 0
    # tools → 게임 → games → 레포 루트
    root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    bad = 0
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR]
        for f in files:
            if not f.endswith(SCAN_EXT):
                continue
            path = os.path.join(dirpath, f)
            try:
                data = open(path, encoding="utf-8").read()
            except Exception:
                continue
            hit = [s for s in lines if s in data]
            if hit:
                bad += len(hit)
                rel = os.path.relpath(path, root)
                print(f"      ⚠ {rel}: 정발 번역문 {len(hit)}건")
                for h in hit[:3] if verbose else hit[:1]:
                    print(f"           {h[:56]!r}")
    print(
        f"  {'✅ 리포에 정발 번역문 없음' if not bad else f'⚠ 정발 번역문 {bad}건'}"
        + (
            ""
            if not bad
            else "\n      → 문안은 `align_map` 포인터로, 손댄 부분만 `subs_at` 오프셋으로 둔다"
        )
    )
    return bad


def scan(verbose=False):
    josa = _josa_re()
    bad = collections.defaultdict(list)
    kinds = collections.Counter()
    n = 0
    for name, eid, _jp, cand, t in R.iter_candidates():
        n += 1
        for k, rx in BAN.items():
            if m := rx.search(cand):
                bad[k].append((name, eid, m.group(0)))
        if josa.search(cand):
            stock = isinstance(t, tuple) and t and t[0] == "__stock__"
            kinds["정형 블록(훅 대상 — 정상)" if stock else "대사(훅 확인 필요)"] += 1
            if not stock:
                bad["조사 병기 — 대사"].append(
                    (name, eid, R.render_bytes(cand, ctrl=False)[:48].replace("\n", " "))
                )
    print(f"화면 바이트 검사 — 재삽입 블록 {n}개")
    for k in BAN:
        v = bad.get(k, [])
        print(f"  {'⚠' if v else '✅'} {k:<16} {len(v)}건")
        for nm, e, g in v[: (None if verbose else 3)]:
            print(f"        {nm} jp{e}: {g!r}")
    print(f"  · 조사 병기 방출 {sum(kinds.values())}건 — {dict(kinds)}")
    for nm, e, g in bad.get("조사 병기 — 대사", [])[: (None if verbose else 6)]:
        print(f"        {nm} jp{e}: {g!r}")
    print(
        "\n⚠ 조사 병기는 **훅이 타면 정상**이다 — 정형 블록은 1·2장 QA 로 확인됐다."
        "\n  대사 쪽은 인게임에서 병기가 그대로 보이는지 확인할 것(상점 프롬프트에서 실제로 샜다)."
    )
    return sum(len(v) for k, v in bad.items() if k in BAN)


if __name__ == "__main__":
    v = "-v" in sys.argv
    # 두 축을 한 진입점에서 본다 — 화면 바이트(`scan`)와 커밋되는 파일(`scan_repo`).
    sys.exit(1 if (scan(v) + scan_repo(v)) else 0)
