"""원판 대비 바뀐 바이트 전수 감사 — 「패턴을 찾아 통째로 바꾸는」 재배치가 우연히 같은 바이트의 데이터까지 고치는 부류(SFC II 장 전환 프리징, 11-07) 가드.

두 겹이다:
 ① **본체**(대본·전투 아카이브 밖) — 원판과 다른 바이트가 전부 `build.Rom.ALLOWED` 의 허용 구간(라벨) 안인가. 쓰기는 `Rom.write` 가 라벨로
    막지만, 그 뒤에 버퍼를 직접 만지거나 구간이 넓어져도 최종 이미지를 한 번 더 본다.
 ② **대본 모듈**(225) — 모듈 코드·자료 중 **스트림 밖**에서 바뀐 바이트는 전부 설명돼야 한다: 뿌리 lea 변위 · 표 항목 · 항목 워드 · goto/call 인자
    (재배치가 다시 잰 자리) 또는 **알려진 문자 표**(블록 91·92·93 입장 배너·목적지, 141·161 이름·라벨 — 원문이 SJIS 텍스트인 런)와 `STALE_SHIFT` 블록의 lea 변위.
    설명 안 되는 바이트가 하나라도 있으면 실패.

    python3 check_diff_audit.py [빌드롬]     # 없으면 현재 꼬리표의 빌드
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import common
import scene

# 알려진 문자 표 블록 — 스트림 파서 밖의 SJIS 칸(field_names.py · dict_names) — 런의 원문이 SJIS 텍스트여야 한다
TEXT_TABLE_BLOCKS = {91, 92, 93, 141, 161}


def module_unexplained(n: int, o: bytes, w: bytes) -> list[tuple[int, str]]:
    """한 모듈의 설명 안 되는 변경 — (오프셋, 사유)."""
    mod = scene.parse_module(o)
    inside = bytearray(len(o))
    for s, st in mod.streams.items():
        e = st.end if st.end > 0 else s
        for i in range(s, min(e, len(o))):
            inside[i] = 1
    ok: set[int] = set()
    for ins in list(mod.roots) + list(mod.forced):
        ok.update((ins + 2, ins + 3))
    for t in mod.tables:
        ok.update((t.word, t.word + 1))
    for p in mod.entries:
        ok.update((p, p + 1))
    for st in mod.streams.values():
        for t in st.tokens:
            if t.ref:
                ok.update(range(t.argpos, t.argpos + max(2, len(t.raw) - 1)))
    stale = mod.stale_shift != 0
    bad: list[int] = []
    for i in range(len(o)):
        if i >= len(w):
            return [(i, "새 모듈이 원본보다 짧다")]
        if o[i] != w[i] and not inside[i] and i not in ok:
            bad.append(i)
    out = []
    i = 0
    while i < len(bad):  # 이어진 런으로 묶는다
        j = i
        while j + 1 < len(bad) and bad[j + 1] == bad[j] + 1:
            j += 1
        a, b = bad[i], bad[j] + 1
        if stale and b - a <= 2:
            pass  # STALE_SHIFT 블록의 비뿌리 lea 변위(scene.reassemble 4b)
        elif n in TEXT_TABLE_BLOCKS and all(x >= 0x40 or x in (0x20, 0x07, 0x00) for x in o[a:b]):
            pass  # 알려진 문자 표 — 원문이 SJIS 글자·공백·구분자뿐인 런
        else:
            out.append((a, f"{b - a}B {o[a:b].hex()}→{w[a:b].hex()}"))
        i = j + 1
    return out


def audit_modules(orig: bytes, new: bytes) -> list[str]:
    ob = archives.blocks(orig, archives.ARCHIVES["script"][0])
    nb = archives.blocks(new, archives.ARCHIVES["script"][0])
    errs = []
    for n, ((_, o, _), (_, w, _)) in enumerate(zip(ob, nb, strict=True)):
        for off, why in module_unexplained(n, o, w):
            errs.append(f"블록 {n} +{off:#x}: 스트림 밖 변경이 설명 안 된다 — {why}")
    return errs


def audit_body(orig: bytes, new: bytes, writes: list) -> list[str]:
    """원판과 다른 바이트 ⊆ 빌드가 `Rom.write` 로 쓴 구간의 합집합 — 쓴 적 없는 바이트가 바뀌었으면 실패."""
    mask = bytearray(len(new))
    for _lb, at, ln in writes:
        mask[at : at + ln] = b"\x01" * ln
    errs = []
    i, n = 0, min(len(orig), len(new))
    while i < n:
        if orig[i] == new[i] or mask[i]:
            i += 1
            continue
        j = i
        while j < n and orig[j] != new[j] and not mask[j]:
            j += 1
        errs.append(f"본체 {i:#x}+{j - i}: 쓴 적 없는 바이트가 원판과 다르다")
        i = j
    if len(orig) != len(new):
        errs.append(f"롬 길이가 다르다 {len(orig):#x} → {len(new):#x}")
    return errs


def main() -> int:
    args = [x for x in sys.argv[1:] if not x.startswith("-")]
    p = (
        Path(args[0])
        if args
        else common.BUILD_DIR / common.BUILD_TAG.replace("/", "_") / "ed1-kr.bin"
    )
    if not p.exists():
        print(f"  원판 대비 변경 감사 — 빌드 롬이 없다({p}) — 안 쟀다")
        return 0
    wl = common.OUT_DIR / "write_log.json"
    if not wl.exists():
        print(f"  원판 대비 변경 감사 — 쓰기 기록이 없다({wl}) — 다시 빌드하면 생긴다 — 안 쟀다")
        return 0
    new = p.read_bytes()
    orig = common.rom()
    e1 = audit_body(orig, new, json.loads(wl.read_text(encoding="utf-8")))
    e2 = audit_modules(orig, new)
    print(
        f"  원판 대비 변경 감사 — 본체 허용 구간 밖 {len(e1)} · 대본 모듈 스트림 밖 설명 안 되는 변경 {len(e2)}"
    )
    for e in (e1 + e2)[:40]:
        print("   ✗", e)
    return 1 if e1 or e2 else 0


if __name__ == "__main__":
    sys.exit(main())
