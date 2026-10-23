"""구조 대조 정적 검사 — 원본(originals)과 빌드 결과를 **대사 덩이·줄 단위로** 맞대어, 글자 바이트를 뺀 「제어 코드 열」이 어긋나지 않는지 본다.

왜(마스터 10-22 「재배치사고 막는 정적검사」): ss-ed3 에서 재조판 때 대사 끝에 넣은 채움 바이트가 다음 블록 호출을 막아 첫 장면 대사가 통째로 빠졌다.
한 블록씩 띄우는 하네스·qa 로는 안 보이고 연속 재생에서만 드러난다 — **글자가 맞아도 제어 열이 틀리면** 못 잡는다. 이 게임은 덩이를 촘촘히 다시 깔고(`repack.compact`)
표 포인터를 바꾸고 쪽 넘김·채움·지역 글리프 표를 얹으므로 같은 위험이 있다.

검사(전부 **실패**로 친다 — 어긋남 0 이어야 통과):
  S1 메시지 표 — 항목 수 같음 · 항목 0 = 지역 글리프 표 포인터(원본 값 0 → 패키지 안 한 곳) · **같은 원본 덩이를 가리키던 항목은 새 덩이도 같고, 다른 덩이는 다르다**(별칭 보존) ·
     원본이 덩이/끝 표시를 가리키던 항목은 새 것도 덩이/끝 표시
  S2 덩이 이음 — 새 패키지의 모든 덩이가 **다음 덩이 시작에 정확히 닿게** 풀린다(`package.audit` 와 같은 기준 — 길이를 줘서 푼 게 아니라 디코더가 스스로 멈춘 자리) · 끝 표시 하나
  S3 줄 수 — 덩이마다 `00` 으로 끝나는 줄 수가 원본과 같다(엔진은 `00` 을 세어 줄을 고른다)
  S4 제어 열 — 줄마다 **구조 제어의 열**이 원본과 같다(아래 「허용」 외에는 실패). 열에서 빠지는 것: 줄바꿈 `0D` · 가나/이스케이프 전환 `0E` `0F` `08` · 강조 `06` `04`(여백·색 감싸기) ·
     속도 `10` · 멈춤 `11`(별도 규칙). `18 a b c d` 는 `14` + 글 4바이트와 같다(`ctrllines.py` 머리말). 남는 것(`0C` `12` `13` `14` `16` `17` `1A` `1B` `1C` `1D` `1E` `07` …)이 같아야 한다.
  S5 채움·찌꺼기 — 새 줄에 `FF`(채움 바이트)가 글자·제어 자리에 끼지 않는다(글리프의 둘째 바이트로 쓰인 `FF` 는 토큰 안이다)

허용(각각 **규칙으로 검출**하고 개수를 센다 — 장부는 `relocations.tsv`):
  쪽 넘김    번역문이 한 쪽에 안 들어가 `13` 을 더하거나(줄 끝 `13` 상태는 같아야 한다 — 끝 대기가 사라지거나 생기면 실패) 줄여 쪽을 합쳤다(`13` 은 쪽을 넘겨 대기하는 제어)
  틀         `ctrllines` 틀 번역(수령·상점·보물상자·화자 머리줄) — 틀 열쇠가 `data/ctrl_lines.tsv` 에 있는 줄은 틀 구조 검증(`ctrllines.py --verify` — 구조 제어를 `{!N}` 으로 명시하지 않고는 못 버린다)이 대신 본다
  이름 상수  원문 `16 <이름 글자> 1A`(상수 이름 삽입 — 레이시아·리자드맨) 를 한국어 글자로 풀어 쓴 줄 — 변수 자리표(`1B` 등) 없이 글자만 든 경우만
  ※ 멈춤 `11`·속도 `10` 는 열에서 빠진다 — 개수 변화(멈춤을 일부만 살린 패키지)는 `relocations.tsv` 와 빌드 로그(연출 타이밍 제어를 일부만 살린 패키지)가 따로 센다.
"""

import argparse
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import ctrllines
import jptext
import package
import pceview

COS = {0x0D, 0x0E, 0x0F, 0x08, 0x06, 0x04, 0x10, 0x11}  # 열에서 빠지는 제어(줄바꿈 · 모드 · 강조 감싸기 · 속도 · 멈춤)
PAGE = 0x13
NAME_END = 0x1A
NAME_BEG = 0x16


def tokens(line: bytes) -> list[tuple]:
    """줄 → 토큰 열. ('c', 코드, 인자) 제어 · ('g',) 글자 한 칸. `18 a b c d` = `14` + 글 한 토큰(`ctrllines` 머리말)."""
    out: list[tuple] = []
    i = 0
    while i < len(line):
        b = line[i]
        if b == 0x18:
            out.append(("c", 0x14, b""))
            out.append(("g", bytes(line[i + 1 : i + 5])))
            i += 5
            continue
        if b < 0x20:
            n = jptext.ARGS.get(b, 0)
            out.append(("c", b, bytes(line[i + 1 : i + 1 + n])))
            i += 1 + n
            continue
        n = 2 if (0x80 <= b <= 0x9F or b >= 0xE0) else 1
        out.append(("g", bytes(line[i : i + n])))
        i += n
    return out


def skeleton(toks: list[tuple], drop=()) -> list[tuple]:
    return [(t[1], t[2]) for t in toks if t[0] == "c" and t[1] not in COS and t[1] not in drop]


BLANK = {b"\x20", b"\x60", b"\xa0", b"\x81\x40"}  # 여백 글자(전각·반각 공백 · 칸 맞춤)


def terminal_page(toks: list[tuple]) -> bool:
    """줄 끝 대기 — 마지막 제어가 `13` 이고 그 뒤에 여백·줄바꿈 말고 글이 안 온다."""
    for t in reversed(toks):
        if t[0] == "c" and t[1] == 0x0D:
            continue
        if t[0] == "g" and t[1] in BLANK:
            continue
        return t[0] == "c" and t[1] == PAGE
    return False


def const_name_pair_removed(sx: list[tuple], toks_x: list[tuple], sy: list[tuple]) -> bool:
    """원문의 `16 <글자만> 1A` 상수 이름 삽입을 걷어 낸 열이 새 열과 같은가(이름 사이에 제어가 없어야 한다)."""
    out = []
    i = 0
    ctl = [t for t in toks_x]
    # 원문 토큰열에서 16 … 1A 사이가 글자뿐인 구간을 찾아 걷는다
    drop_idx = set()
    for a, t in enumerate(ctl):
        if t[0] == "c" and t[1] == NAME_BEG:
            for b in range(a + 1, len(ctl)):
                if ctl[b][0] == "c":
                    if ctl[b][1] in COS:
                        continue  # 이름 안의 가나 전환(`0E` `0F`)은 글자 모드일 뿐
                    if ctl[b][1] == NAME_END:
                        drop_idx.update((a, b))
                    break
    if not drop_idx:
        return False
    rem = [t for k, t in enumerate(ctl) if k not in drop_idx]
    return skeleton(rem) == sy


def classify(orig: bytes, built: bytes, tmpl_keys: set[str] | None = None) -> str | None:
    """(원문 줄, 새 줄) → 분류 문자열, 허용 밖이면 None."""
    tx, ty = tokens(orig), tokens(built)
    if any(t[0] == "g" and t[1][:1] == b"\xff" for t in ty) and not any(t[0] == "g" and t[1][:1] == b"\xff" for t in tx):
        return None  # S5 채움 바이트(`FF`)가 글자·제어 자리에 끼었다(글리프 뒤 바이트로 쓰인 `FF` 는 토큰 안이라 걸리지 않는다)
    sx, sy = skeleton(tx), skeleton(ty)
    if sx == sy:
        return "동일" if terminal_page(tx) == terminal_page(ty) else None
    fx, fy = skeleton(tx, (PAGE,)), skeleton(ty, (PAGE,))
    if fx == fy:
        return "쪽 넘김" if terminal_page(tx) == terminal_page(ty) else None
    if const_name_pair_removed(sx, tx, sy):
        return "이름 상수"
    if tmpl_keys is not None:
        try:
            k = ctrllines.key_of(ctrllines.parse(orig, False)[0])
        except Exception:
            k = None
        if k in tmpl_keys:
            return "틀"
    return None


@dataclass
class Report:
    chunks_total: int = 0
    chunks_checked: int = 0
    lines_total: int = 0
    lines_checked: int = 0
    cat: Counter = field(default_factory=Counter)
    fails: list[str] = field(default_factory=list)
    page_rows: list[tuple] = field(default_factory=list)  # (rel, 메시지, 줄, 원본 13 수, 새 13 수)
    move_rows: list[tuple] = field(default_factory=list)  # (rel, 항목 번호, 원래 시작, 새 시작)
    fill_rows: list[tuple] = field(default_factory=list)  # (rel, 시작, 끝, 설명)


def _lines(pkg: bytes, a: int, b: int) -> list[bytes]:
    d, _pos = package.decode_chunk(pkg, a, b)
    return d.split(b"\x00")


def check_package(rel: int, po: bytes, pb: bytes, rep: Report, tmpl_keys) -> None:
    T0, to = package.msg_table(po)
    Tb, tb = package.msg_table(pb)
    tag = f"패키지 {rel}"
    if T0 != Tb or len(to) != len(tb):
        rep.fails.append(f"{tag}: S1 메시지 표 위치·길이가 다르다 ({T0},{len(to)}) → ({Tb},{len(tb)})")
        return
    co = dict(package.chunks(po))
    cb = {a: b for a, b in package.chunks(pb) if a != tb[0]}  # 항목 0 = 지역 글리프 표(덩이가 아니다)
    sent_o = [a for a in co if po[a : a + 8] == package.SENTINEL]
    sent_b = [a for a in cb if pb[a : a + 8] == package.SENTINEL]
    if len(sent_o) != 1 or len(sent_b) != 1:
        rep.fails.append(f"{tag}: S2 끝 표시가 하나가 아니다 (원본 {len(sent_o)} · 새 {len(sent_b)})")
        return
    # S2 덩이 이음 — 각 덩이가 다음 시작에 정확히 닿는가(길이를 주지 않고 디코더가 스스로 멈춘 자리)
    for a, b in cb.items():
        if pb[a : a + 8] == package.SENTINEL:
            continue
        _d, pos = package.decode_chunk(pb, a, b)
        if pos != b:
            rep.fails.append(f"{tag}: S2 덩이 {a} 가 {pos} 에서 끝나 다음 시작 {b} 에 안 닿는다")
    # S1 표 — 항목 0 · 별칭 · 덩이 종류
    z0 = (to[0] != 0)
    if to[0] != 0:
        rep.fails.append(f"{tag}: S1 원본 표 항목 0 이 0 이 아니다({to[0]})")
    if not (T0 < tb[0] < len(pb)):
        rep.fails.append(f"{tag}: S1 새 표 항목 0(지역 글리프 표 포인터) {tb[0]} 이 패키지 밖이다")
    seen_o: dict[int, int] = {}
    seen_b: dict[int, int] = {}
    for i in range(1, len(to)):
        a1, a2 = to[i], tb[i]
        if a1 == 0:
            if a2 != 0:
                rep.fails.append(f"{tag}: S1 항목 {i} 가 원본에서 비었는데(0) 새 표엔 값이 있다({a2})")
            continue
        if a1 not in co:
            continue  # 덩이가 아닌 값(표 뒤 자료를 가리키는 항목) — 이 게임엔 없다
        if a2 not in cb:
            rep.fails.append(f"{tag}: S1 항목 {i} 의 새 값 {a2} 가 덩이 시작이 아니다")
            continue
        if (a1 in sent_o) != (a2 in sent_b):
            rep.fails.append(f"{tag}: S1 항목 {i} 의 끝 표시 여부가 다르다")
            continue
        if a1 in seen_o and seen_o[a1] != a2:
            rep.fails.append(f"{tag}: S1 같은 원본 덩이({a1})를 가리키던 항목이 새 덩이로 갈렸다 ({seen_o[a1]} ≠ {a2})")
        seen_o.setdefault(a1, a2)
        if a2 in seen_b and seen_b[a2] != a1:
            rep.fails.append(f"{tag}: S1 다른 원본 덩이({seen_b[a2]}·{a1})가 같은 새 덩이({a2})로 합쳐졌다")
        seen_b.setdefault(a2, a1)
        if a1 != a2:
            rep.move_rows.append((rel, i, a1, a2))
    # S3·S4·S5 줄 단위
    for a1, a2 in seen_o.items():
        if a1 in sent_o:
            continue
        rep.chunks_total += 1
        lo, lb = _lines(po, a1, co[a1]), _lines(pb, a2, cb[a2])
        rep.lines_total += len(lo)
        if len(lo) != len(lb):
            rep.fails.append(f"{tag}: S3 덩이 {a1}→{a2} 줄 수가 다르다 ({len(lo)} → {len(lb)})")
            continue
        rep.chunks_checked += 1
        mi = next(i for i in range(1, len(to)) if to[i] == a1)
        for k, (x, y) in enumerate(zip(lo, lb, strict=True)):
            rep.lines_checked += 1
            c = classify(x, y, tmpl_keys)
            if c is None:
                rep.fails.append(f"{tag}: S4 메시지 {mi} 줄 {k} 의 제어 열이 허용 밖으로 어긋난다 — 원본 {skeleton(tokens(x))} · 새 {skeleton(tokens(y))}")
                continue
            rep.cat[c] += 1
            if c == "쪽 넘김":
                nx = sum(1 for t in tokens(x) if t[0] == "c" and t[1] == PAGE)
                ny = sum(1 for t in tokens(y) if t[0] == "c" and t[1] == PAGE)
                rep.page_rows.append((rel, mi, k, nx, ny))
    # 채움 — 새 패키지의 마지막 덩이 끝 뒤 0xFF 구간
    last_b = max(b for a, b in cb.items() if pb[a : a + 8] != package.SENTINEL)
    s = sent_b[0]
    e = s
    while e < len(pb) and pb[e] == 0xFF:
        e += 1
    rep.fill_rows.append((rel, last_b, e, "끝 표시 + 0xFF 꼬리(지역 글리프 표 앞까지)"))
    del z0


def analyze(iso: str) -> Report:
    rep = Report()
    tmpl = set(ctrllines.table())
    for rel in package.CLEAN:
        po = bytes(common.track_data(rel, 128))
        pb = bytes(pceview.iso_pkg(iso, rel, 128))
        check_package(rel, po, pb, rep, tmpl)
    return rep


def summary(rep: Report) -> str:
    cat = " · ".join(f"{k} {v}" for k, v in sorted(rep.cat.items()))
    return (
        f"  구조 대조 [pce-ed2] — 덩이 {rep.chunks_checked}/{rep.chunks_total} · 줄 {rep.lines_checked}/{rep.lines_total} · 어긋남 {len(rep.fails)}"
        f" ({cat})"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", default=str(common.BUILD_DIR / "pce-ed2" / "ed2.iso"))
    ap.add_argument("--gate", action="store_true", help="어긋남이 있으면 실패(종료 1)")
    a = ap.parse_args()
    rep = analyze(a.iso)
    print(summary(rep))
    for f in rep.fails[:40]:
        print("  ✖", f)
    if a.gate and rep.fails:
        sys.exit(1)


if __name__ == "__main__":
    main()
