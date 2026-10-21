"""재배치 장부 — 빌드가 **실제로 한** 재배치를 원본 롬과 빌드 롬을 맞대 자동으로 뽑아 `games/md-ed1/relocations.tsv` 로 남긴다.

왜(마스터 10-22 「재배치를 진행한 부분들도 별도로 기록해두자. 정 안되면 나중에 되돌려야할수도 있으니」):
재배치(블록·꼬리 옮김 · 쪽 넘김 추가 · 채움/패딩 · goto 스텁 · 포인터 변경)는 엔진이 물리적 이어 읽기에 기대는 자리에서 조용히
깨진다(ss-ed3 10-21 FF FF 채움). 어디를 어떻게 옮겼는지 장부가 없으면 되돌릴 수도, 의심할 수도 없다.

원문 바이트·문장은 넣지 않는다 — 좌표·종류·사유만.

열: 블록 키 · 종류(옮김/쪽 넘김/채움/스텁/포인터) · 원래 좌표 · 새 좌표 · 사유 · 엔진 근거 · 되돌리면

- 손으로 쓰지 않는다 — `python3 tools/check_structure.py --freeze` 가 빌드 롬에서 다시 뽑는다.
- 게이트: 빌드 롬에서 뽑은 장부가 커밋된 `relocations.tsv` 와 다르면 실패(**장부에 없는 재배치가 빌드에 있다**).
  의도한 변경이면 `--freeze` 로 갱신하고 diff 를 사유와 함께 검토한다. 구조 대조 검사의 허용 목록(`check_structure.FREE`·`EXEMPT`)과 같은
  분류(종류)를 쓴다.
- 되돌리기: 종류별·블록별로 끄는 스위치는 **없다**(각 행의 마지막 열). 이유는 행마다 적었다.
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import battle
import captions
import common
import sysmsg

LEDGER = common.GAME_DIR / "relocations.tsv"
HEAD = ("블록 키", "종류", "원래 좌표", "새 좌표", "사유", "엔진 근거", "되돌리면")

NO_SWITCH = "되돌리기 수단 없음"
WHY_MOVE_BLOCK = "재압축 크기가 원 자리 칸과 달라 아카이브를 앞에서부터 차례로 다시 깖(넘치면 꼬리 빈 공간)"
EV_ARCHIVE = "대본·전투 색인표(4B×N, 아카이브 기준 상대) 를 새 위치로 다시 씀 — archives.blocks · build.py 아카이브 단계"
WHY_STREAM = "번역문 길이가 원본 스트림 자리보다 달라 스트림을 모듈 끝에 다시 쓰고 변위·뿌리·표를 다시 잼(원본 자리는 0 으로 비움)"
EV_STREAM = "scene.reassemble — 뿌리 lea 변위·goto/call·표 항목 재계산, 끝 코드 사슬·분기 꼬리는 바로 뒤에 붙임(scene._successor); 로더 $18460"
WHY_PAGE = "조판기(build.typeset)가 줄·쪽을 14슬롯·3줄 한도로 다시 나눔 — 쪽 넘김 05 의 개수가 원문과 달라짐"
EV_PAGE = "렌더러 $978C 안에서만 쓰이는 코드 — 끝 코드(00·06·07·0A·0D) 흐름은 그대로(scene.END)"
WHY_COPY = "같은 끝을 나눠 쓰는 접미·사슬 스트림 뒤에 사슬 다음 스트림의 복사본을 둠(이어 읽기가 엉뚱한 곳으로 새지 않게)"
EV_COPY = "scene._successor / reassemble 꼬리 복사본 — 끝 코드(06·07·0A·0D) 뒤 물리적 이어 읽기"
WHY_STUB = "제자리 칸에 새 문안이 안 들어가 본문을 근처·꼬리로 옮기고 제자리엔 goto 3B 만 둠"
EV_STUB = "goto(0F, 16비트 상대) — scene.GOTO; 소비자(참조)가 없어 못 옮기는 자리에 쓴다"
WHY_RELOC = "제자리 묶음이 번역문보다 좁아 스트림을 꼬리 칸으로 옮기고 참조 명령(lea abs.l)의 피연산자를 새 자리로 바꿈"
EV_RELOC = "lea abs.l → 렌더 호출 $60A0 (참조가 절대 주소인 것만 옮길 수 있다 — sysmsg.RELOCATE)"


def _row(key, kind, orig, new, why, ev, revert=NO_SWITCH):
    return (key, kind, orig, new, why, ev, revert)


def _runs(items: list[tuple[int, int, int]]):
    """(번호, 원 시작, 새 시작) 중 움직인 것을 번호가 이어지는 구간으로 묶는다 → (처음, 끝, 원 처음, 원 끝, 새 처음, 새 끝)."""
    out, cur = [], None
    for n, a, b in items:
        if cur and n == cur[1] + 1:
            cur[1], cur[3], cur[5] = n, a, b
        else:
            if cur:
                out.append(tuple(cur))
            cur = [n, n, a, a, b, b]
    if cur:
        out.append(tuple(cur))
    return out


def _archive_rows(orig: bytes, new: bytes, base: int, label: str, kind_name: str) -> list[tuple]:
    ob, nb = archives.blocks(orig, base), archives.blocks(new, base)
    rows = []
    moved = [(n, o[0], b[0]) for n, (o, b) in enumerate(zip(ob, nb, strict=True)) if o[0] != b[0]]
    n_ptr = len(moved)
    rows.append(
        _row(f"{label}-색인표", "포인터", f"{base:#x}+{len(ob)}×4", f"{base:#x}+{len(ob)}×4",
             f"블록 {n_ptr}개의 시작 위치가 달라져 색인표 항목을 다시 씀", EV_ARCHIVE, NO_SWITCH + "(원 자리 방식이 칸에 안 들어간다)")
    )
    tail_lo = max((b[0] for b in nb), default=0)
    for lo, hi, a0, a1, b0, b1 in _runs(moved):
        rows.append(
            _row(f"{label}:{lo:03d}~{hi:03d}", "옮김", f"{a0:#x}(블록 {lo})~{a1:#x}(블록 {hi})", f"{b0:#x}(블록 {lo})~{b1:#x}(블록 {hi})", f"{kind_name} 블록 {lo}~{hi}: {WHY_MOVE_BLOCK}",
                 EV_ARCHIVE, NO_SWITCH)
        )
    del tail_lo
    return rows


def _script_rows(orig: bytes, new: bytes) -> list[tuple]:
    import check_structure as cs

    rows = _archive_rows(orig, new, archives.ARCHIVES["script"][0], "대본", "대본")
    _blocks, _streams, _errs, _tot, per = cs.run(orig, new)
    for n, st in per:
        if st["moved"]:
            rows.append(
                _row(f"대본:{n:03d}", "옮김", f"스트림 {st['moved']}개(원본 자리)", "모듈 끝", WHY_STREAM + f" · 원본 자리 0 채움 {st['zeroed']}B", EV_STREAM)
            )
        if st["copies"]:
            rows.append(_row(f"대본:{n:03d}", "채움", "-", f"꼬리 복사본 {st['copies']}개", WHY_COPY, EV_COPY))
        if st["pg_new"] != st["pg_orig"]:
            rows.append(
                _row(f"대본:{n:03d}", "쪽 넘김", f"05×{st['pg_orig']}", f"05×{st['pg_new']}", WHY_PAGE, EV_PAGE)
            )
    return rows


def _battle_rows(orig: bytes, new: bytes) -> list[tuple]:
    rows = _archive_rows(orig, new, battle.ARCHIVE, "전투", "전투")
    ob, nb = battle.blocks(orig), battle.blocks(new)
    for n, ((_, a, _), (_, b, _)) in enumerate(zip(ob, nb, strict=True)):
        if a == b:
            continue
        for tgt in sorted(battle.refs(a)):
            if tgt + 3 <= len(b) and b[tgt] == 0x0F and a[tgt] != 0x0F:
                disp = struct.unpack(">h", b[tgt + 1 : tgt + 3])[0]
                rows.append(_row(f"전투:{n:03d}", "스텁", f"{tgt:#x}", f"{tgt + 1 + disp:#x}", WHY_STUB, EV_STUB))
    return rows


def _sysmsg_rows(orig: bytes, new: bytes) -> list[tuple]:
    rows = []
    refs = sysmsg.refs(orig)
    for t in sysmsg.RELOCATE:
        for kind, ins in refs.get(t, []):
            if kind == "abs":
                nt = int.from_bytes(new[ins + 2 : ins + 6], "big")
                if nt != t:
                    rows.append(_row(f"시스템:{t:06x}", "옮김", f"{t:#x}", f"{nt:#x}", WHY_RELOC, EV_RELOC))
                    rows.append(_row(f"시스템:{t:06x}", "포인터", f"{ins + 2:#x}(lea 피연산자)", f"{nt:#x}", "옮긴 스트림을 가리키도록 참조 명령 피연산자를 바꿈", EV_RELOC))
    for t in sysmsg.TAIL_JUMP:
        if new[t] == 0x0F and orig[t] != 0x0F:
            disp = struct.unpack(">h", new[t + 1 : t + 3])[0]
            rows.append(_row(f"시스템:{t:06x}", "스텁", f"{t:#x}", f"{t + 1 + disp:#x}", WHY_STUB, EV_STUB))
    return rows


def _caption_rows(orig: bytes, new: bytes) -> list[tuple]:
    rows = []
    for name, ptrs in captions.RELOCATE.items():
        for b, p in ptrs:
            nt = int.from_bytes(new[p : p + 4], "big")
            if nt != b:
                rows.append(
                    _row(f"자막:{name}:{b:06x}", "옮김", f"{b:#x}", f"{nt:#x}", "자막 표가 제자리 영역에 안 들어가 꼬리로 옮기고 표 포인터(lea abs.l)를 바꿈",
                         "워드 스크립트 드라이버 $14E44 — captions.RELOCATE")
                )
                rows.append(_row(f"자막:{name}:{b:06x}", "포인터", f"{p:#x}", f"{nt:#x}", "표 포인터 피연산자 교체", "lea abs.l,a3 — captions.RELOCATE"))
    return rows


def collect(orig: bytes, new: bytes) -> list[tuple]:
    return [*_script_rows(orig, new), *_battle_rows(orig, new), *_sysmsg_rows(orig, new), *_caption_rows(orig, new)]


def to_tsv(rows: list[tuple]) -> str:
    return "\n".join("\t".join(r) for r in (HEAD, *rows)) + "\n"


def kinds(rows: list[tuple]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        out[r[1]] = out.get(r[1], 0) + 1
    return out


def gate(orig: bytes, new: bytes, freeze: bool = False) -> int:
    rows = collect(orig, new)
    text = to_tsv(rows)
    summary = " · ".join(f"{k} {v}" for k, v in sorted(kinds(rows).items()))
    if freeze:
        LEDGER.write_text(text, encoding="utf-8")
        print(f"  재배치 장부 갱신 — {len(rows)}행 ({summary})")
        return 0
    have = LEDGER.read_text(encoding="utf-8") if LEDGER.exists() else ""
    if have == text:
        print(f"  재배치 장부 — 빌드와 일치 {len(rows)}행 ({summary})")
        return 0
    old, now = set(have.splitlines()), set(text.splitlines())
    print(f"  재배치 장부 — 빌드와 다르다(장부에 없는 재배치 {len(now - old)}행 · 빌드에 없는 장부 {len(old - now)}행) ({summary})")
    for r in sorted(now - old)[:15]:
        print("   + ", r.split("\t")[0], r.split("\t")[1], r.split("\t")[2], "→", r.split("\t")[3])
    for r in sorted(old - now)[:15]:
        print("   - ", r.split("\t")[0], r.split("\t")[1], r.split("\t")[2], "→", r.split("\t")[3])
    print("   의도한 변경이면 `python3 tools/check_structure.py --freeze` 로 장부를 갱신하고 diff 를 검토한다")
    return 1
