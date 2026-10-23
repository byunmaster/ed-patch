"""재배치 장부 — 빌드가 실제로 한 재배치(블록·꼬리 옮김 · goto 스텁 · 포인터 변경 · 공백 채움 · 코드 패치)를 좌표·종류·사유만으로 기록한다.

원문 바이트·문장은 넣지 않는다. 빌드가 `add()` 로 쌓고 `write_build()` 가 work/build/<꼬리표>/relocations.build.tsv 에 쓴다.
커밋되는 장부 `games/md-ed2/relocations.tsv` 는 `struct_check.py --ledger` 가 이 파일 + 쪽 넘김 행(원판과 구운 롬의 05 수 차이)으로 만든다.
게이트: 구운 빌드의 장부가 커밋된 장부와 다르면(= 장부에 없는 재배치가 빌드에 생겼다) 실패한다.
"""

from pathlib import Path

COLS = ("블록 키", "종류", "원래 좌표", "새 좌표", "사유", "엔진 근거", "되돌리면 생기는 일")
LOG: list[tuple] = []
CTX = {"key": ""}

# 엔진 근거 — 주소는 ED2 롬(원판) 기준. 렌더러 $B738: 제어 바이트(<$20·≥$EB)는 $B8CC → jsr $BF58 디스패처(인자 표 $BF9A)
EVID_VM = "렌더러 $B738 → 제어 바이트 $B8CC → jsr $BF58 디스패처 · 0F goto/10 call 2B 상대 변위 · 뿌리 lea 변위(scene.reassemble)"
EVID_PAGE = "렌더러 $B738 → 디스패처 $BF58 의 05 핸들러(쪽 넘김·▼ 대기) — 번역이 쪽 나눔을 정한다"
EVID_FILL = "렌더러 $B738 가 0x20(공백)을 글자로 그린다 · 스트림 끝은 00/06/07/0A/0D 만"
EVID_BATTLE = "전투 메시지도 같은 렌더러 $B738·디스패처 $BF58 · lea/자료 A 워드가 스트림을 가리킨다(battle.plan_block)"
EVID_PATCH = "battle.patch_boss_block — 원본 루틴 바이트 확인 후 덮는다 · 자기 수정(move.w d0,(a2))"
UNDO_NONE = "되돌리기 수단 없음 — 번역 글이 원래 칸보다 길어 원 자리에 못 들어간다(되돌리면 글이 잘리거나 이웃 스트림을 덮는다)"
UNDO_PAGE = "되돌리기 수단 없음 — 쪽 나눔은 정본 문안(script/·textmap/)의 \\f 에 있다. 되돌리려면 그 문안을 고친다"
UNDO_POINTER = "옮김과 한 묶음 — 옮김을 못 되돌리면 포인터도 그대로(되돌리기 수단 없음)"
UNDO_FILL = "되돌리기 수단 없음 — 칸을 지키는 채움이라 빼면 뒤 스트림 시작이 당겨져 이어 읽기가 끊긴다"
UNDO_PATCH = "되돌리기 수단 없음 — 원본 4B 덮어쓰기 루틴은 한글 칸·받침에 안 맞아 못 쓴다(원 자리 방식이 불가)"


def begin(key: str) -> None:
    CTX["key"] = key


def add(kind: str, old, new, why: str, evid: str, undo: str, key: str | None = None) -> None:
    f = lambda v: "" if v is None else (f"{v:#06x}" if isinstance(v, int) else str(v))  # noqa: E731
    LOG.append((key or CTX["key"], kind, f(old), f(new), why, evid, undo))


def reset() -> None:
    LOG.clear()
    CTX["key"] = ""


def rows() -> list[tuple]:
    return sorted(set(LOG))


def write_tsv(path: Path, rs: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["\t".join(COLS)] + ["\t".join(r) for r in rs]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_tsv(path: Path) -> list[tuple]:
    t = path.read_text(encoding="utf-8").split("\n")
    return [tuple(l.split("\t")) for l in t[1:] if l]
