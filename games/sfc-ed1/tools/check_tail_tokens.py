#!/usr/bin/env python3
"""**문장 끝 사전 토큰 덤프** 검사 — 번역문의 쪽 끝에 사전 토큰이 원문에 없던 만큼 더 붙어 있나.

    python3 tools/check_tail_tokens.py            # 검사(기준선보다 늘면 실패)
    python3 tools/check_tail_tokens.py --freeze   # 기준선 갱신(처음 박을 때·줄었을 때만)

## 왜 있나 (2026-10-18)

번역 정본의 토큰 계약(`textmap.check_tokens`)은 「토큰이 전부, 같은 순서로 들어 있는가」만 본다. `tm-draft`(PS1 문안을
기계로 끌어온 초안)는 PS1 문안에 사전 토큰 자리가 없어 **토큰을 문장 맨 끝에 한꺼번에 덤프**했고, 계약은 위치를 안 봐서
통과했다. 최종 롬에서 `…않았어요.` 뒤에 `D0 37 E0`(몬스터)이 붙어 이름이 한 번 더 찍힌다 — 원문 본체는 `D0 xx E0` 가 6개뿐인데
한글 롬 새 뱅크엔 313개다.

규칙: 쪽(`<FF>` `<FE>` `<E0>` `<E4>`) 끝에 연달아 오는 사전·치환 토큰 중 **원문의 같은 쪽 끝 열에 없던 것**이 있으면 위반
(원문이 이름으로 끝나는 문장·어순 이동은 허용). 쪽 수가 안 맞는 조각은 건너뛴다(다른 게이트 몫).
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: E402,F401,I001  (common 보다 먼저 — shared/text 와 이름이 겹친다)
import common  # noqa: E402
import units  # noqa: E402

BASELINE = common.GAME_DIR / "textmap" / "tail_tokens_baseline.json"
BOUNDARY = re.compile(r"<E0>|<E4>|<FF>|<FE>")
RUN = re.compile(r"((?:\{D[0-9A-F]:[0-9A-F]{2}\}|\{D[0-9A-F]\})+)\s*$")
# 명시 예외 — 조각 id: 사유. 덤프가 아니라 정당한 꼴로 디코드로 확인한 것만 둔다.
EXEMPT = {
    "8b1b5382f1a0": "원문 「{D5:24}ございました。」(사전 문장 뒤에 글이 이어짐)을 번역문이 「정말 {D5:24}」(사전 문장 =「고맙습니다」)로 닫는다 — 문장 끝 낱말이다",
    "711d54575fa9": "원문 「{あんりがとう}　ごぜーました。」(사전 문장 뒤에 글이 이어짐)을 번역문이 「참말 {D5:33}」(사전 문장 =「고맙습죠.」)으로 닫는다 — 문장 끝 낱말이다",
}
BOUND_CODES = (0xE0, 0xE4, 0xFF, 0xFE)
BLANKS = (0xCF, 0x10, 0x0A, 0x0D, 0x83, 0x84, 0x0C, 0x0F, 0x0E)  # 줄바꿈 · 공백 · 문장 끝 부호(。、!?…) 글자 코드 — 「{사전 문장}!」 처럼 부호가 뒤따르는 정당한 꼴


def kr_runs(kr: str) -> list[list[str]]:
    """번역문의 쪽 끝 토큰 열 — 경계(`<E0>` 등) 하나마다 직전의 사전·치환 토큰 열(없으면 [])."""
    out = []
    pos = 0
    for m in BOUNDARY.finditer(kr):
        page = kr[pos : m.start()]
        r = RUN.search(page.rstrip("\n"))
        out.append(re.findall(r"\{D[0-9A-F]:[0-9A-F]{2}\}|\{D[0-9A-F]\}", r.group(1)) if r else [])
        pos = m.end()
    return out


def jp_runs(items) -> list[list[str]]:
    """원문 항목 열의 쪽 끝 토큰 열 — `kr_runs` 와 같은 경계에서."""
    out = []
    run: list[str] = []
    for it in items:
        if it.kind in ("dict", "subst"):
            run.append(units.token_of(it))
        elif it.kind == "ctrl" and it.code in BOUND_CODES:
            out.append(run)
            run = []
        elif it.kind == "ctrl":
            pass  # 다른 제어(`<EE>` 네이티브 호출 등)는 열을 끊지 않는다 — 인자로 쓰는 사전 토큰이 뒤따른다
        elif it.kind == "char" and it.code in BLANKS:
            pass  # 줄바꿈·공백은 열을 끊지 않는다(KR 쪽은 끝 공백을 떼고 센다 — 부호는 KR 에서도 사전 문장 뒤에 붙으므로 같다)
        else:
            run = []
    return out


def violations(jp: list[list[str]], kr: list[list[str]]) -> list[int]:
    """쪽 번호 목록 — 번역문 쪽 끝 열에 **원문 쪽 끝 열에 없던** 토큰이 있는 쪽(덤프). 사전 토큰끼리 자리를 바꾼 것(번역문 열 ⊆ 원문 열)은
    어순 이동이라 허용한다. 쪽 수가 다르면 [] (이 검사의 몫이 아니다)."""
    if len(jp) != len(kr):
        return []
    return [i for i, (a, b) in enumerate(zip(jp, kr, strict=True)) if set(b) - set(a)]


LABEL_END = re.compile(r"[가-힣.!?…~)]\s*<E3>[^<]*<E1>(?:<[^>]*>)*(?:<E0>|<E4>|<FF>|<FE>)")


def label_at_end(kr: str) -> bool:
    """글 **뒤에** 화자 이름표(`<E3>…<E1>`)가 쪽 끝으로 붙은 꼴 — `tm-draft` 가 이름표를 본문 뒤로 보냈다(122조각, 10-18).
    원문은 `<E3>이름⏎<E1>본문` 이라 화면에서 화자 줄이 빠지고 빈 이름표 창이 남는다."""
    return bool(LABEL_END.search(kr))


def scan() -> dict[str, list[int]]:
    rom = common.rom_bytes()
    items, us = units.extract(rom)
    tm = json.loads((common.GAME_DIR / "textmap" / "segments.json").read_text(encoding="utf-8"))
    # 조각 → 항목 열(extract 가 낸 단위와 같은 끊기)
    segs = {}
    cur = []
    for k, it in enumerate(items):
        if cur and common.off2snes(it.off) >> 16 != common.off2snes(cur[-1].off) >> 16:
            segs_add(segs, cur)
            cur = []
        cur.append(it)
        if (it.kind == "ctrl" and it.code in (0xE0, 0xE4)) or k == len(items) - 1:
            segs_add(segs, cur)
            cur = []
    bad = {}
    for sid, seg in segs.items():
        v = tm.get(sid)
        if not v or not v.get("kr") or sid in EXEMPT:
            continue
        vio = violations(jp_runs(seg), kr_runs(v["kr"]))
        if vio:
            bad[sid] = vio
    return bad


def segs_add(segs: dict, cur: list) -> None:
    import hashlib

    raw = b"".join(bytes([x.code]) + x.args for x in cur)
    segs.setdefault(hashlib.sha1(raw).hexdigest()[:12], list(cur))


def main() -> int:
    tm = json.loads((common.GAME_DIR / "textmap" / "segments.json").read_text(encoding="utf-8"))
    lab = sorted(k for k, v in tm.items() if v.get("kr") and label_at_end(v["kr"]))
    if lab:
        print(f"  ⛔ 이름표가 글 뒤로 간 조각 {len(lab)}: {lab[:10]}")
        return 1
    bad = scan()
    base = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}
    new = sorted(set(bad) - set(base))
    print(f"문장 끝 토큰 덤프 검사: 위반 {len(bad)}조각 (기준선 {len(base)})")
    if "--freeze" in sys.argv:
        BASELINE.write_text(json.dumps(bad, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print("  기준선을 갱신했다 (늘리는 용도가 아니다)")
        return 0
    if new:
        print(f"  ⛔ 기준선에 없는 위반 {len(new)}조각: {new[:10]}")
        return 1
    if len(bad) < len(base):
        print("  (줄었다 — --freeze 로 기준선을 내린다)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
