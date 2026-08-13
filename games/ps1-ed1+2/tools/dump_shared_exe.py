#!/usr/bin/env python3
"""**ED.EXE 와 ED2.EXE 가 함께 쓰는 문자열** 대조표 — ED2 트랙을 열기 전에 기반을 다진다.

**왜.** PS1 『1+2』는 한 디스크에 실행파일이 둘이다(`ED.EXE` LBA 257 · `ED2.EXE` LBA 756).
메뉴·시스템·전투 문자열은 **공유가 아니라 사본 두 벌**이라(실측 2026-08-13: 메뉴 블록이
`0xBE290` 과 `0x99C84` 에 바이트까지 동일하게 있다) **ED2 트랙에서 같은 자리를 또 고친다.**
그때 표기가 갈리면 **한 디스크가 두 말을 한다** — 플레이어는 이어서 하는데.

그래서 미리 뽑아 둔다:

- 두 EXE 에 **바이트까지 같은 일본어 문자열** 목록(전수)
- 그 자리에 **우리가 지금 쓰는 ED1 문안**(textmap 파생 — 없으면 아직 안 건드린 자리)
- **ED2 정발이 같은 걸 뭐라 부르는지**(코퍼스 키워드 검색 — 후보다, 판정은 사람이)

⚠ **판정 도구지 게이트가 아니다.** 후보 검색은 어절 기반이라 헛짚는다.
⚠ 산출물은 정발 문안을 담으므로 **`work/review/` 로만** 나간다(커밋 금지).

  python3 tools/dump_shared_exe.py          # 요약
  python3 tools/dump_shared_exe.py -v       # 자리마다
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import common
from common import ORIG_BIN, OUT_DIR, REVIEW_DIR
from derive_text import CLASSES, derive, jkey

# ISO 파일표 실측(2026-08-13) — (LBA, 크기)
EXES = {"ED.EXE": (257, 1021952), "ED2.EXE": (756, 872448)}

# ⚠ **선두 바이트를 0x98 까지만 받는다.** SJIS 제1수준 한자가 0x889F~0x9872 이고 그 위는
# 제2수준(벽자)이라 게임 텍스트에 안 나온다 — 열어 두면 바이너리가 `0劯1覘`·`B裄馞T` 처럼
# 한자로 디코드돼 쏟아진다(실측 2026-08-13: 잡음이 절반이었다).
_SJIS = re.compile(rb"(?:[\x81-\x98][\x40-\x7e\x80-\xfc]|[\x20-\x7e]){3,}")
# ⚠ 바이너리를 SJIS 로 디코드하면 한자처럼 보이는 쓰레기가 쏟아진다 — 두 겹으로 거른다:
#   ① 쓸 수 있는 글자만으로 이루어졌는가 ② 가나·한자가 절반 이상인가
_GOOD = re.compile(r"^[ぁ-んァ-ヴ一-鿿ー、。！？%csd\s0-9A-Za-z…・「」『』【】〜]+$")
_JA = re.compile(r"[ぁ-んァ-ヴ一-鿿]")


def _read(lba, size):
    out = bytearray()
    with open(ORIG_BIN, "rb") as f:
        for s in range((size + 2047) // 2048):
            f.seek((lba + s) * 2352 + 24)
            out += f.read(2048)
    return bytes(out[:size])


def _strings(b):
    out = set()
    for m in _SJIS.finditer(b):
        try:
            s = m.group().decode("cp932").strip()
        except Exception:  # noqa: BLE001 — 바이너리 구간은 그냥 버린다
            continue
        if len(s) >= 3 and _GOOD.match(s) and len(_JA.findall(s)) * 2 >= len(s):
            out.add(s)
    return out


def our_kr():
    """해시키 → 우리 ED1 문안. 네 textmap 클래스를 한 표로 모은다.

    ⚠ `jp_map` 은 **JP 원문으로 조회**하는 래퍼라 순회하면 해시키가 나온다(원문 복원 불가 —
    저작권 때문에 그렇게 설계돼 있다). 그래서 여기서는 **해시키 표를 직접 쓴다**.
    """
    m = {}
    for cls in CLASSES:
        try:
            m.update(derive(cls))
        except Exception as e:  # noqa: BLE001 — 클래스 하나가 없어도 나머지는 본다
            print(f"  – textmap/{cls}: 건너뜀({e.__class__.__name__})")
    # 이름표는 JP 원문이 곧 키다(해시 아님) — 같은 표로 합쳐 둔다.
    import patch_items as I
    import patch_sys_ui as U

    for jp, kr in list(I.NAMES.items()) + list(I.MONSTERS.items()):
        m[jkey(jp)] = kr
    for jp, kr in U.PLACES:
        m[jkey(jp)] = kr
    # ⚠ UI 라벨은 **오프셋으로 키가 잡혀 있다** — JP 가 표에 없다. 원본 EXE 에서 그 자리를
    #   읽어 JP↔KR 을 잇는다. 이러지 않으면 「우리가 이미 옮긴 자리」가 통째로 안 잡힌다.
    ed = _read(*EXES["ED.EXE"])
    for off, kr in U.UI.items():
        jp = ed[off : off + 24].split(b"\x00")[0]
        try:
            m[jkey(jp.decode("cp932"))] = kr
        except Exception:  # noqa: BLE001
            pass
    return m


def ed2_corpus():
    """ED2 정발의 **시스템·전투 문자열** — `ED2MAIN.EXE` 에서 뽑는다.

    ⚠ 처음엔 대사 코퍼스(`work/derived/dos_kr/ED2`, SCENA DLL)를 뒤졌는데 **엉뚱한 대사만
    걸렸다**(`は守りの体制をとった` 에 술집 할아버지 대사가 붙었다). 시스템·전투 문자열은
    대사 DLL 이 아니라 **실행파일**에 있다 — 우리가 대조하려는 층이 애초에 거기다.
    대사는 보조로만 붙인다(같은 낱말이 대사에서 어떻게 쓰이는지 참고).
    """
    rows = []
    exe = os.path.join(common.ROOT, "..", "..", "originals", "kr", "dos-ed2", "ED2MAIN.EXE")
    if os.path.exists(exe):
        b = open(exe, "rb").read()
        pat = re.compile(rb"(?:[\xb0-\xc8][\xa1-\xfe]|[\x20-\x7e]){3,}")
        seen = set()
        for m in pat.finditer(b):
            try:
                t = m.group().decode("euc-kr").strip()
            except Exception:  # noqa: BLE001
                continue
            if len(re.findall(r"[가-힣]", t)) >= 2 and t not in seen:
                seen.add(t)
                rows.append(("ED2MAIN.EXE", t))
    root = os.path.join(OUT_DIR, "dos_kr", "ED2")
    for p in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        d = json.load(open(os.path.join(root, p), encoding="utf-8"))
        for e in d.get("entries", d) if isinstance(d, dict) else d:
            t = e.get("text", "") if isinstance(e, dict) else str(e)
            if t:
                rows.append((p, t))
    return rows


_TOK = re.compile(r"[가-힣]{2,}")


def ed2_candidates(kr, corpus, k=3):
    """우리 ED1 문안의 어절로 ED2 정발에서 같은 뜻을 찾는다 — **후보**다."""
    toks = sorted(set(_TOK.findall(kr)), key=len, reverse=True)[:3]
    if not toks:
        return []
    scored = []
    for f, t in corpus:
        hit = sum(1 for w in toks if w in t)
        if hit:
            scored.append((hit, f, t))
    scored.sort(key=lambda r: (-r[0], len(r[2])))
    return [{"file": f, "text": t[:120]} for _h, f, t in scored[:k]]


def main():
    verbose = "-v" in sys.argv
    sets = {k: _strings(_read(*v)) for k, v in EXES.items()}
    shared = sorted(sets["ED.EXE"] & sets["ED2.EXE"])
    ours = our_kr()
    corpus = ed2_corpus()

    rows, done, todo = [], 0, 0
    for jp in shared:
        kr = ours.get(jkey(jp))
        if kr:
            done += 1
        else:
            todo += 1
        rows.append(
            {
                "jp": jp,
                "ours_ed1": kr,
                "ed2_candidates": ed2_candidates(kr, corpus) if kr else [],
            }
        )

    os.makedirs(REVIEW_DIR, exist_ok=True)
    out = os.path.join(REVIEW_DIR, "shared_exe.json")
    json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"  두 EXE 공유 일본어 문자열: {len(shared)}")
    print(f"    · 우리가 이미 옮긴 자리: {done}")
    print(f"    · 아직 안 건드린 자리:   {todo}")
    print(f"    · ED2 정발 후보가 잡힌 자리: {sum(1 for r in rows if r['ed2_candidates'])}")
    print(f"  → {out} (⚠ 정발 문안 포함 — 커밋 금지)")
    if verbose:
        for r in rows:
            if not r["ours_ed1"]:
                continue
            print(f"\n  JP  {r['jp'][:60]}")
            print(f"  ED1 {r['ours_ed1'][:60]}")
            for c in r["ed2_candidates"][:2]:
                print(f"  ED2? [{c['file']}] {c['text'][:60]}")
    print("\n  ⚠ 게이트가 아니다 — 후보 검색은 어절 기반이라 헛짚는다. 사람이 판정한다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
