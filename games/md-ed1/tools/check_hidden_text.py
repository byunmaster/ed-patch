"""추출 도구가 못 보는 SJIS 텍스트를 찾는다 — **보고 전용**(관리자 확정 2026-09-27 밤, check.sh 에서).

    python3 tools/check_hidden_text.py

`scene.py`(대본)·`battle.py`(전투)가 뽑는 스트림 범위 **밖**에 텍스트꼴 SJIS 런이 있으면
번역 파이프라인이 그 글자를 한 번도 못 본다 — `field_names.py`(블록 91 지명 표)가 걸렸던
바로 그 부류다.

🔴 **실패시키지 않는다** — 처음엔 하드 게이트로 짰는데 돌려 보니 script 112/225 · battle 5/110
블록, 1,502건이 걸렸다(상점 대화·필경사 상투구·**본편 스토리 대사**·몬스터 변종 이름 — 전부
사람이 읽는 진짜 문장, 노이즈 아님). `scene.py` 의 스트림 발견 로직(`lea_roots`/`table_roots`)
자체가 못 찾는 참조 방식이 따로 있다는 뜻이라 **대사 라운드(문안 추출 범위 조사) 몫**으로
넘겼다(관리자 확정 2026-09-27 밤, `docs/status.md` 「다음 라운드」 참조) — 지금 실패시키면
그 조사가 끝날 때까지 영원히 빨간불이라 루트 CLAUDE.md 의 「늘 빨간불인 게이트는 아무도 안
본다」와 충돌한다. **건수만 찍어서 줄어드는 걸 보이게 한다.**
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import battle
import common
import field_names
import scene

# 이미 찾아서 고친 「숨은 텍스트」 — 재발 검사가 아니라 원래 있던 자리라 계속 걸린다.
# (블록 번호, 오프셋 범위) — field_names.py 가 이 범위를 직접 패치한다(scene.py 는 여전히 못 본다).
KNOWN = {
    ("script", field_names.BLOCK): [
        (field_names.TABLE_OFF, field_names.TABLE_OFF + len(field_names.ENTRIES) * field_names.STRIDE)
    ],
}


def _script_covered(data: bytes) -> list[tuple[int, int]]:
    mod = scene.parse_module(data)
    return [(s, st.end) for s, st in mod.streams.items()]


def _battle_covered(data: bytes) -> list[tuple[int, int]]:
    out = []
    for rec in battle.records(data):
        out.append((rec["name_at"], rec["name_at"] + len(rec["name"])))
    for _tgt, info in battle.refs(data).items():
        st = info["stream"]
        out.append((st.start, st.end))
    return out


def _find_hidden(data: bytes, covered: list[tuple[int, int]], known: list[tuple[int, int]]) -> list[tuple[int, int]]:
    hidden = []
    for m in archives.SJIS_RUN.finditer(data):
        s, e = m.start(), m.end()
        if any(cs <= s and e <= ce for cs, ce in covered):
            continue
        if any(ks <= s and e <= ke for ks, ke in known):
            continue
        hidden.append((s, e))
    return hidden


def check() -> None:
    rom = common.rom()
    found: dict[tuple[str, int], list[tuple[int, int]]] = {}
    # 블록 92·93 목적지 표 — field_names 가 직접 한글로 바꾼다(위 KNOWN 과 같은 이유, 오프셋은 앵커로 찾는다)
    base0 = archives.ARCHIVES["script"][0]
    for blk in field_names.DEST_JP:
        at = field_names._dest_start(archives.blocks(rom, base0)[blk][1], blk)
        n_cells = len(field_names.DEST_JP[blk])
        KNOWN[("script", blk)] = [(at, at + n_cells * field_names.STRIDE)]

    base = archives.ARCHIVES["script"][0]
    for n, (_s, data, _e) in enumerate(archives.blocks(rom, base)):
        known = KNOWN.get(("script", n), [])
        hidden = _find_hidden(data, _script_covered(data), known)
        if hidden:
            found[("script", n)] = hidden

    for n, (_s, data, _e) in enumerate(battle.blocks(rom)):
        known = KNOWN.get(("battle", n), [])
        hidden = _find_hidden(data, _battle_covered(data), known)
        if hidden:
            found[("battle", n)] = hidden

    if found:
        total = sum(len(h) for h in found.values())
        script_n = sum(1 for arch, _n in found if arch == "script")
        battle_n = sum(1 for arch, _n in found if arch == "battle")
        print(
            f"  숨은 텍스트(추출 도구 범위 밖 SJIS) — script {script_n}/225블록 · "
            f"battle {battle_n}/110블록 · {total}건 (보고 전용, 대사 라운드 몫 — docs/status.md 참조)"
        )
        # 그중 **사전 이름이 든 것** — 목적지 표(블록 92·93, 2026-10-08)처럼 표인데 못 찾은 자리는 이쪽에서 드러난다.
        # 대사 문장(미추출 장면)이 대부분이라 건수만 찍고, 표 꼴(구분자 07 로 이어진 14B 칸)이 보이면 따로 올린다.
        sys.path.insert(0, str(common.ROOT))
        from shared.canon import names as _G

        keys, _ = _G._keys(_G.load("eiyuu"))
        blocks = {
            ("script", n): b for n, (_s, b, _e) in enumerate(archives.blocks(rom, base0))
        } | {("battle", n): b for n, (_s, b, _e) in enumerate(battle.blocks(rom))}
        with_names = sum(
            1
            for key, runs in found.items()
            for s, e in runs
            if _G.find(blocks[key][s:e].decode("cp932", "replace"), keys)
        )
        print(f"    └ 사전 이름이 든 숨은 런 {with_names}건 — 미추출 장면 대사(대사 라운드가 채우면 이름 검사 분모에 든다)")
    else:
        print("  숨은 텍스트 스캔 — script/battle 전부 깨끗함(추출 도구가 못 보는 자리 없음)")


if __name__ == "__main__":
    check()
