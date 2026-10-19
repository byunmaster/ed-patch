"""PS1 재사용 덧붙임 — 원문에 없는 이웃 문장이 한글에 딸려 오지 않았나.

    python3 tools/check_ps1_extra.py            # 목록
    python3 tools/check_ps1_extra.py --check    # 게이트 (걸린 게 있으면 실패)

왜 필요한가: PS1 번역은 PS1 창(원문 한 덩이) 단위로 붙어 있어, MD 쪽 쪽·스트림과 창 경계가 어긋나면 이웃 문장이
통째로 딸려 온다(2026-10-20 style 검수: 크레아 왕비 대사 머리에 「…워프2 주문을 외웠다.」 · 병사 대사에 「썩 저리
물러가라!!」 · 여관 돈 모자람 끝에 「그럼 편히 쉬십시오.」). 빌드·조판·이름 검사는 이걸 못 본다 — 문장이 멀쩡한 한국어다.

세 갈래를 잰다(대본 `script/NNN.json` 의 `ours` ↔ 원판 롬에서 런타임으로 읽은 같은 번호의 원문. 원문은 레포에 없다):
  A. 한글 문장이 PS1 창(원문 `ps1-ed1+2/work/derived/scn_jp`)에서 왔고, 그 창의 같은 순번 원문 문장이 MD 원문과
     거의 안 겹친다(글자 두 쌍 포함률 < 0.2, 6자↑).
  B. 한글 문장이 **원문이 없는** PS1 창(변수 이름이 든 시스템 문구)에서 왔다 — 원문 대조가 불가능해 승인표에 있어야 한다.
  C. 한글 문장이 같은 씬의 **다른 스트림 전체**와 같고, 그 스트림 원문이 이 스트림 원문에 거의 안 들어 있다(< 0.5)
     — 창이 두 스트림을 합쳐 두 번 나오는 꼴.
승인표 `games/md-ed1/ps1_extra_exceptions.json` 의 `approved` 는 **사람이 원문과 맞대어 본 오탐**만 든다
(키 = `갈래|씬NNN:오프셋|문장`) — 새로 걸리면 고치거나, 맞대어 본 뒤에 추가한다.

⚠ 한계: 문장 쪼개기는 종결부호(. ! ?) 기준이라 부호 없는 한 줄 덧붙임은 못 본다. A 는 PS1 창과 한글 문장 수가 같은
창만 순번으로 짝 짓는다. 분모를 줄이지 않으려고 출처(`src`)는 가리지 않는다(scene:p4 · glossary · ps1:* 전부).
"""

import collections
import glob
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import common
import pairdump

EXC = common.GAME_DIR / "ps1_extra_exceptions.json"
COV_A = 0.2  # A: 같은 순번 PS1 원문 문장이 MD 원문에 이만큼도 안 들어 있다
COV_C = 0.5  # C: 다른 스트림 원문이 이 스트림 원문에 이만큼도 안 들어 있다
MIN_KR = 5  # 한글 문장 최소 글자(공백 뺀 길이)
MIN_JP = 6  # A 의 원문 문장 최소 글자


def jn(s: str) -> str:
    """원문 대조 키 — 부호·공백·표현 계층을 걷어낸 NFKC."""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\\x([0-9A-Fa-f]{1,2})", lambda m: chr(int(m.group(1), 16)), s)
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\{c\}[^{}]*\{c\}", "", s)
    s = re.sub(r"\{[^}]*\}|<[^>]*>|%[a-z]|\\n|【[^】]*】|¶|⏎", "", s)
    s = re.sub(r"[。、！？!?,.・]", "", s)
    return re.sub(r"[\s　･·・…‥]", "", s)


def jsents(s: str) -> list[str]:
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\\x([0-9A-Fa-f]{1,2})", lambda m: chr(int(m.group(1), 16)), s)
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\{c\}[^{}]*\{c\}", "", s)
    s = re.sub(r"\{n\}|¶|⏎", "", s)
    s = re.sub(r"\{[^}]*\}|<[^>]*>|【[^】]*】", "", s)
    return [jn(x) for x in re.split(r"[。！？!?]+", s) if jn(x)]


def kn(s: str) -> str:
    return re.sub(r"[\s¶⏎.,!?…~\"“”'’‘「」\-]|\{[^}]*\}|<[0-9a-f]+>|【[^】]*】", "", s)


def ksents(s: str) -> list[str]:
    s = re.sub(r"\{[^}]*\}|<[0-9a-f]+>|【[^】]*】", "", s).replace("¶", " ").replace("⏎", " ")
    return [kn(x) for x in re.split(r"[.!?]+", s) if len(kn(x)) >= MIN_KR]


def cov(a: str, b: str) -> float:
    g = [a[i : i + 2] for i in range(len(a) - 1)]
    return sum(1 for x in g if x in b) / len(g) if g else 1.0


def ours_text(t: str) -> str:
    """대본 `ours` → 평문. 화자 머리·제어코드를 걷고 쪽 넘김(\\f)은 공백."""
    t = re.sub(r"<1e>.*?<04>", "", t, flags=re.DOTALL)
    t = t.replace("\f", " ")
    return re.sub(r"<[^>]*>", " ", t)


def ps1_corpus() -> list[tuple]:
    import ps1_reuse  # PS1 워크트리가 없으면 여기서 멈춘다(원문 코퍼스 없이 재면 가짜 초록)

    base = ps1_reuse.PS1
    files = sorted(glob.glob(str(base / "work" / "derived" / "scn_jp" / "ED1SCN*.json")))
    if not files:
        raise SystemExit(f"PS1 원문 코퍼스 없음: {base}/work/derived/scn_jp — 안 쟀다(통과 아님)")
    ents = []
    for f in files:
        scn = Path(f).stem
        j = json.loads(Path(f).read_text(encoding="utf-8"))
        k = json.loads((base / "script" / f"{scn}.json").read_text(encoding="utf-8"))
        for e in j["entries"]:
            if e.get("kind") == "header" or not e.get("text"):
                continue
            kv = k.get(str(e["entry_id"]))
            if not (kv and kv.get("t")):
                continue
            t = kv["t"].replace("{p}", " ")
            ents.append((jn(e["text"]), jsents(e["text"]), ksents(t)))
    return ents


def load_exceptions() -> set[str]:
    if not EXC.exists():
        return set()
    return {x["key"] for x in json.loads(EXC.read_text(encoding="utf-8")).get("approved", [])}


def md_rows() -> dict[str, list[tuple[str, str, str]]]:
    """{씬번호: [(번호, 원문 평문, 한글 평문)]} — 원문은 원판 롬 모듈에서 런타임으로 읽는다."""
    orig = common.rom()
    ob = archives.blocks(orig, archives.ARCHIVES["script"][0])
    out: dict[str, list] = {}
    for f in sorted(glob.glob(str(common.GAME_DIR / "script" / "*.json"))):
        sc = int(Path(f).stem)
        om = ob[sc][1]
        for off, e in json.loads(Path(f).read_text(encoding="utf-8")).get("streams", {}).items():
            ours = e.get("ours", "")
            if not ours:
                continue
            jp = " ".join(pairdump.walk_pages(om, int(off, 16), False))
            out.setdefault(f"{sc:03d}", []).append((f"씬{sc:03d}:{off}", jp, ours_text(ours)))
    return out


def scan() -> tuple[int, list[str], list[str]]:
    ents = ps1_corpus()
    idx: dict[str, list[int]] = collections.defaultdict(list)
    for n, e in enumerate(ents):
        for s in e[2]:
            idx[s].append(n)
    exc = load_exceptions()
    hits: list[tuple[str, str]] = []  # (키, 설명)
    total = 0
    for lst in md_rows().values():
        full = {num: kn(kr) for num, _o, kr in lst}
        for num, jp, kr in lst:
            total += 1
            mj = jn(jp)
            for s in ksents(kr):
                # A · B — PS1 창에서 온 문장
                for n in idx.get(s, [])[:6]:
                    pj, pjs, pks = ents[n]
                    if not pj:
                        hits.append((f"B|{num}|{s}", "PS1 창에 원문이 없어 대조 불가"))
                        break
                    if pj in mj:
                        break
                    if len(pks) == len(pjs) and s in pks:
                        js = pjs[pks.index(s)]
                        if len(js) >= MIN_JP and js not in mj and cov(js, mj) < COV_A:
                            hits.append(
                                (
                                    f"A|{num}|{s}",
                                    f"PS1 원문 문장이 원판에 없다(포함률 {cov(js, mj):.2f})",
                                )
                            )
                        break
                # C — 다른 스트림 전체와 같은 문장
                if len(s) >= 7 and full[num] != s:
                    for num2, jp2, _kr2 in lst:
                        if num2 != num and full[num2] == s and cov(jn(jp2), mj) < COV_C:
                            hits.append(
                                (
                                    f"C|{num}|{s}",
                                    f"{num2} 의 전체 문안과 같은데 그쪽 원문이 여기 없다",
                                )
                            )
                            break
    seen: set[str] = set()
    bad, ok = [], []
    for key, why in hits:
        if key in seen:
            continue
        seen.add(key)
        (ok if key in exc else bad).append(f"{key} — {why}")
    stale = sorted(exc - seen)
    return total, bad, [f"승인표에 있는데 이제 안 걸린다(지워도 된다): {k}" for k in stale] + []


def main() -> None:
    total, bad, stale = scan()
    print(f"  PS1 덧붙임 — 대본 스트림 {total} · 걸림 {len(bad)} · 승인표 낡은 항목 {len(stale)}")
    for b in bad:
        print(f"    ❌ {b}")
    for s in stale:
        print(f"    ⚠ {s}")
    if "--check" in sys.argv and bad:
        raise SystemExit(
            "PS1 덧붙임 검사 실패 — 원문에 없는 문장을 지우거나, 원문과 맞대어 본 오탐이면 승인표에 올린다"
        )


if __name__ == "__main__":
    main()
