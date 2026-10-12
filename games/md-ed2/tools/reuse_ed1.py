"""코드 영역 문안(시스템 메시지)을 md-ed1 문안에서 물려받는다 — **같은 원문일 때만**, 후보 3순위(마스터·관리자 10-12).

    python3 tools/reuse_ed1.py --stats     # 일치 수만
    python3 tools/reuse_ed1.py --apply     # 빈 `ours` 만 채운다(`src` 에 출처) + 목록을 work/review/reuse_ed1.txt 에

저본 순서(관리자 지시): ① 정본 `shared/canon/ed2.json`(system·battle) ② PS1 ED2 문안 ③ **그다음에야** md-ed1 문안. md-ed1 문안은
PS1 ED1 기반이라 ED2 정본과 갈릴 수 있다 — 이 도구로 채운 자리는 `src: "ed1:<주소>"` 로 남아 정본 대조 검사에서 보인다.

원문 키 = 스트림 토큰열의 (글자 | 제어코드) — **참조 오프셋은 뺀다**(롬마다 달라 해시가 안 맞는다). ED1 쪽은 md-ed1 도구를
자식 프로세스로 돌려 읽는다(두 게임이 같은 이름의 모듈 `common`·`scene` 을 가져 한 프로세스에 못 섞는다). ED1 롬은 메인 트리의
`originals/jp/md-ed1` 에서 읽는다(읽기 전용).
"""

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import sysmsg

KEY_SRC = """
def content_key(st):
    out = []
    for t in st.tokens:
        if t.kind == "text":
            out.append(t.raw.decode("cp932", "replace"))
        elif t.kind == "end":
            out.append("<%02x|end>" % t.code)
        elif t.kind == "eof":
            pass
        elif t.ref:
            out.append("<%02x>" % t.code)
        else:
            out.append("<%s>" % t.raw.hex())
    return "".join(out)
"""
exec(KEY_SRC)  # noqa: S102 — ED1 자식 프로세스와 **같은 키 함수**를 쓴다(복사본이 갈리지 않게)

ED1_MAIN = (
    common.ROOT.parents[2]
    if (common.ROOT.parents[2] / "games" / "md-ed1").exists()
    else common.ROOT
)
CHILD = (
    "import sys, json\nsys.path.insert(0, 'tools')\nimport common, sysmsg\n"
    + KEY_SRC
    + "d = common.rom()\nstrs = sysmsg.streams(d)\nout = {}\n"
    "for a, e in strs.items():\n"
    "    out['%06x' % a] = [content_key(e['stream']), [t.target for t in e['stream'].tokens if t.ref]]\n"
    "print(json.dumps(out))\n"
)


def ed1_side() -> tuple[dict, dict]:
    tools = ED1_MAIN / "games" / "md-ed1"
    r = subprocess.run(
        [sys.executable, "-c", CHILD], cwd=tools, capture_output=True, text=True, check=False
    )
    if r.returncode:
        raise SystemExit(f"md-ed1 도구 실행 실패: {r.stderr[-300:]}")
    keys = json.loads(r.stdout)
    ours = json.loads((tools / "textmap" / "sysmsg.json").read_text(encoding="utf-8"))
    return keys, ours


TAGREF = re.compile(r"<([0-9a-f]{2}):([0-9a-f]{1,6})>")


def candidates(d: bytes) -> list[tuple[str, str, str]]:
    """[(ED2 주소, 후보 ours, 출처)] — ED2 스트림 중 ED1 에 같은 원문 + ours 가 있는 것."""
    keys, ours = ed1_side()
    by_key: dict[str, list[str]] = {}
    for a, (k, _refs) in keys.items():
        if ours.get(a, {}).get("ours"):
            by_key.setdefault(k, []).append(a)
    out = []
    for a, e in sysmsg.streams(d).items():
        st = e["stream"]
        k = content_key(st)
        hit = by_key.get(k)
        if not hit:
            continue
        # 같은 원문이 ED1 에 여럿이면(같은 말·다른 문안) **전부 같을 때만** 받는다
        texts = {ours[h]["ours"] for h in hit}
        if len(texts) != 1:
            continue
        txt = next(iter(texts))
        refs2 = [t.target for t in st.tokens if t.ref]
        it = iter(refs2)

        def sub(m, it=it):
            try:
                return f"<{m.group(1)}:{next(it):06x}>"
            except StopIteration:
                return m.group(0)

        txt2 = TAGREF.sub(sub, txt)
        out.append((f"{a:06x}", txt2, f"ed1:{hit[0]}"))
    return out


if __name__ == "__main__":
    d = common.rom()
    cands = candidates(d)
    strs = sysmsg.streams(d)
    smap = json.loads(sysmsg.MAP_JSON.read_text(encoding="utf-8"))
    new = [
        (a, t, s)
        for a, t, s in cands
        if not smap.get(a, {}).get("ours") and not smap.get(a, {}).get("held")
    ]
    print(
        f"  ED2 코드 영역 스트림 {len(strs)} 중 md-ed1 같은 원문 후보 {len(cands)} · 빈 칸에 채울 것 {len(new)}"
    )
    if "--apply" in sys.argv:
        for a, t, s in new:
            smap[a]["ours"] = t
            smap[a]["src"] = s
        sysmsg.MAP_JSON.write_text(json.dumps(smap, ensure_ascii=False, indent=1), encoding="utf-8")
        out = common.REVIEW_DIR / "reuse_ed1.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(f"{a}\t{s}\t{t!r}" for a, t, s in new), encoding="utf-8")
        print(f"  채움 {len(new)} · 목록 {out}")
