"""재배치 장부 — 빌드가 **실제로 한** 재배치(블록·꼬리 옮김 · 포인터 변경 · 쪽 넘김 증감 · 채움/지역 글리프 표 · 프로그램 스텁)를 `relocations.tsv` 로 남긴다.

마스터 10-22 「재배치를 진행한 부분들도 별도로 기록해두자. 정 안되면 나중에 되돌려야할수도 있으니」. 손으로 쓰지 않는다 — 원본(originals)과 새 이미지를 맞대어(`structcheck`)
**빌드 결과에서 자동으로 뽑고**, 프로그램 쪽은 빌드가 남긴 쓰기 장부(`work/review/prog_writes.tsv` — `Writer.spans` 의 라벨·좌표·길이)에서 뽑는다.
원문 바이트·문장은 넣지 않는다 — **좌표 · 종류 · 사유**뿐이다(저작권 규칙).

열: 블록 키 · 종류 · 원래 좌표 · 새 좌표 · 사유 · 엔진 근거 · 되돌리면 생기는 일
종류: 옮김(덩이 시작이 바뀜) · 포인터(메시지 표 항목 값이 바뀜) · 쪽 넘김(`13` 개수 증감) · 채움(0xFF 꼬리 · 지역 글리프 표 자리) · 스텁(프로그램 영역 덮어쓰기)
좌표: 패키지 안 바이트 오프셋 `rel:+0x…`(rel = 데이터 트랙 상대 섹터) · 프로그램은 선형 유저 바이트 `lin:…`.

게이트(`--gate`): 새로 뽑은 장부에 **커밋된 `relocations.tsv` 에 없는 행**이 있으면 실패한다(= 장부에 안 적은 재배치가 빌드에 생겼다). 낡은 행(커밋된 것엔 있는데 지금 빌드엔 없다)도 실패 —
의도한 변화면 `--freeze` 로 갱신하고 커밋한다.

되돌리기 수단: 덩이 옮김·포인터·채움은 **수단 없음** — 번역문이 원본 칸보다 길어 제자리로 못 돌아가고(`repack.repack_in_place` 는 총량이 모자라면 중단), 모든 덩이를 순서대로 다시 깔기
때문이다(`repack.compact`). 쪽 넘김은 번역문 길이가 정한 조판 결과라 블록별 스위치가 없다(되돌리면 칸을 넘는 글이 잘린다). 프로그램 스텁은 모듈별 `apply` 가 한 곳에서 쓰므로
그 모듈 호출을 빼면 원본 바이트로 돌아간다(`build.py` 의 `apply_program`/`*.apply(w)` 줄 — 단 그 모듈이 만드는 기능이 같이 사라진다).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import package
import pceview
import structcheck

LEDGER = common.GAME_DIR / "relocations.tsv"
PROG_WRITES = common.REVIEW_DIR / "prog_writes.tsv"
HEAD = "블록 키\t종류\t원래 좌표\t새 좌표\t사유\t엔진 근거\t되돌리면 생기는 일"

NO_UNDO_CHUNK = "수단 없음 — 번역 덩이가 원본 칸보다 길어 제자리로 못 간다(repack_in_place 는 총량이 모자라면 중단)"
EV_TABLE = "메시지 표(패키지 머리표 항목 4)의 13비트 주소+뱅크 가산으로만 덩이에 닿는다(`$4743` · `$7DA2→$7D84→$5796`, package.py 머리말)"
EV_PAGE = "`13` = 쪽 넘김 대기(대사 해석기 뱅크 0x71 `$672F` 제어 표, dialog.py 머리말) — 쪽마다 키를 기다린다"
NO_UNDO_PAGE = "수단 없음(조판 결과) — 되돌리면 번역문이 한 쪽(6줄)을 넘어 잘린다"


def _off(rel: int, v: int) -> str:
    return f"{rel}:+0x{v:x}"


def rows(iso: str) -> list[tuple]:
    rep = structcheck.analyze(iso)
    out: list[tuple] = []
    # 옮김 — 같은 원본 덩이를 가리키는 항목이 여럿이어도 덩이는 한 번
    done = set()
    for rel, i, a1, a2 in rep.move_rows:
        if (rel, a1) in done:
            continue
        done.add((rel, a1))
        out.append((f"{rel}:덩이@{a1}", "옮김", _off(rel, a1), _off(rel, a2), "촘촘 재배치(repack.compact) — 번역문 덩이를 순서대로 다시 깔았다", EV_TABLE, NO_UNDO_CHUNK))
    for rel, i, a1, a2 in rep.move_rows:
        out.append((f"{rel}:표[{i}]", "포인터", _off(rel, a1), _off(rel, a2), "덩이가 옮겨져 표 항목 값을 새 시작으로 바꿨다", EV_TABLE, NO_UNDO_CHUNK))
    for rel in package.CLEAN:
        pb = bytes(pceview.iso_pkg(iso, rel, 128))
        T, tb = package.msg_table(pb)
        out.append((f"{rel}:표[0]", "포인터", f"{rel}:+0x{T:x}=0", _off(rel, tb[0]), "표 항목 0(원본에선 안 쓰던 0)에 지역 글리프 표 포인터를 쓴다(`build._place_table`)", "항목 0 은 어떤 대사도 부르지 않는다 — 후킹 루틴이 지역 글리프 표를 이 값으로 찾는다(hook.py)", "수단 없음 — 지역 글리프 표가 있어야 번역문 글자가 그려진다(글리프 풀에 안 든 글자)"))
    for rel, a, b, why in rep.fill_rows:
        out.append((f"{rel}:꼬리", "채움", _off(rel, a), _off(rel, b), why, "게임은 덩이의 끝을 모른다 — 디코더가 줄 수로 멈춘다(repack.py 머리말)", NO_UNDO_CHUNK))
    for rel, mi, k, nx, ny in rep.page_rows:
        out.append((f"{rel}:{mi}:{k}", "쪽 넘김", f"13×{nx}", f"13×{ny}", "번역문 길이에 맞춰 쪽(13) 수가 바뀌었다 — 줄 끝 대기는 그대로", EV_PAGE, NO_UNDO_PAGE))
    if PROG_WRITES.exists():
        for ln in PROG_WRITES.read_text(encoding="utf-8").splitlines():
            if not ln or ln.startswith("#"):
                continue
            label, lin, n = ln.split("\t")
            out.append((f"프로그램:{label}", "스텁", f"lin:{lin}", f"lin:{lin}+{n}B", "프로그램·모듈 영역 덮어쓰기(후킹 · 글리프 표 · 문자열 이사)", f"모듈 머리말(라벨 「{label}」)", "그 모듈의 apply 호출을 빼면 원본 바이트 — 기능이 같이 사라진다"))
    return out


def render(rs: list[tuple]) -> str:
    return "\n".join([HEAD] + ["\t".join(r) for r in rs]) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", default=str(common.BUILD_DIR / "pce-ed2" / "ed2.iso"))
    ap.add_argument("--freeze", action="store_true", help="새로 뽑은 장부를 relocations.tsv 에 쓴다")
    ap.add_argument("--gate", action="store_true", help="커밋된 장부와 다르면 실패")
    a = ap.parse_args()
    rs = rows(a.iso)
    kinds: dict[str, int] = {}
    for r in rs:
        kinds[r[1]] = kinds.get(r[1], 0) + 1
    txt = render(rs)
    summary = " · ".join(f"{k} {v}" for k, v in sorted(kinds.items()))
    if a.freeze:
        LEDGER.write_text(txt, encoding="utf-8")
        print(f"  재배치 장부 갱신 [pce-ed2] — {len(rs)}행 ({summary}) → {LEDGER.name}")
        return
    old = LEDGER.read_text(encoding="utf-8") if LEDGER.exists() else ""
    new_set, old_set = set(txt.splitlines()), set(old.splitlines())
    added, gone = sorted(new_set - old_set), sorted(old_set - new_set)
    print(f"  재배치 장부 [pce-ed2] — {len(rs)}행 ({summary}) · 장부에 없는 새 행 {len(added)} · 낡은 행 {len(gone)}")
    for r in added[:8]:
        print("   + ", r[:160])
    for r in gone[:8]:
        print("   − ", r[:160])
    if a.gate and (added or gone):
        print("  ✖ 장부와 빌드가 다르다 — 의도한 재배치면 `python3 tools/relocations.py --freeze` 로 갱신하고 커밋한다(사유·근거 열 확인)")
        sys.exit(1)


if __name__ == "__main__":
    main()
