#!/usr/bin/env python3
"""메시지 포인터 표의 목표가 **번역 단위 목록(본체 구간) 안에 있는가** — 구조 게이트.

    python3 tools/check_targets.py            # 검사
    python3 tools/check_targets.py --freeze   # 기준선을 줄어든 만큼 내린다(래칫 — 늘리는 방향은 없다)

## 왜 있나 (2026-10-18)

화면 일본어 게이트(`check_jp_left`)는 **단위 목록 안에서** 빈 문안만 센다. 목록에 없는 문장은 분모에도 안 들어가
영원히 초록이다(sfc-ed2 가 같은 구멍을 찾았다). 여기가 그 구멍이었다 — 메인 표 2,906개 중 **101개가 본체
`$07:A721~$0B:FD04` 밖**(`$05:CDFF~E77B` 71 · `$1E:CA12~CE80` 28 · `$1E:90E1`·`$1E:9D7D` 2)을 가리키고, 번역
단위(`units.extract`)는 본체 구간만 훑어 이 101개가 통째로 일본어로 남았다. 옛 devlog 가 「뱅크 $05·$1E 는 코드가
섞여 있다」며 걷어낸 건 가나 런 통계의 오진이었다(표 목표가 실제로 그 자리를 가리킨다).

게이트 = 본체와 `text.EXTRA_REGIONS`(반입한 본체 밖 구간) **둘 다 밖인** 목표의 **기준선**(`textmap/targets_outside.json`)보다 늘면 실패.
남은 기준선 4개는 문안이 아니다 — main[1277]·main[2880] = `$1E:9D7D`·`$1E:90E1`(`CALL_NATIVE` 로 시작하는 코드), alt1[0]·alt2[0] = 표 자신을 가리키는 더미.
⚠ 롬 바이트에서 가나 런을 세는 방식은 쓰지 않는다 — 가나 코드가 코드·그래픽과 섞여 잡음이 너무 크다
(5자↑ 런 17,196 중 문장을 가를 수 없었다). 표 목표라는 구조 근거가 정확하다.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: E402,I001  (common 보다 먼저 — shared/text 와 이름이 겹친다)
import common  # noqa: E402

BASELINE = common.GAME_DIR / "textmap" / "targets_outside.json"


def outside(pointers: list[int], lo: int, hi: int, extra=()) -> list[int]:
    """SNES 24비트 목표 중 [lo, hi) 와 `extra` 구간들 밖인 것의 인덱스 목록."""
    spans = [(lo, hi), *extra]
    return [i for i, p in enumerate(pointers) if not any(a <= p < b for a, b in spans)]


def scan(rom: bytes) -> dict[str, list[int]]:
    out = {}
    for name in text.MSG_TABLES:
        ps = text.msg_pointers(name, rom)
        out[name] = outside(ps, text.TEXT_START, text.TEXT_END, text.EXTRA_REGIONS)
    return out


def main() -> int:
    freeze = "--freeze" in sys.argv
    got = scan(common.rom_bytes())
    base = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}
    n = sum(len(v) for v in got.values())
    nb = sum(len(v) for v in base.values())
    new = {k: sorted(set(v) - set(base.get(k, []))) for k, v in got.items()}
    new = {k: v for k, v in new.items() if v}
    print(f"표 목표 검사: 본체 밖 목표 {n}개 (기준선 {nb}) · " + " ".join(f"{k} {len(v)}" for k, v in got.items()))
    if freeze:
        BASELINE.write_text(json.dumps(got, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("  기준선을 갱신했다 (늘리는 용도가 아니다 — 처음 박을 때와 줄었을 때만)")
        return 0
    if new:
        print(f"  ⛔ 기준선에 없는 본체 밖 목표 — 번역 단위 목록에 안 든 문장이다: {new}")
        return 1
    if n < nb:
        print("  (줄었다 — --freeze 로 기준선을 내린다)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
