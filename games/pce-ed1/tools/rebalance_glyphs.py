"""상주 글리프 칸 재배치 — 빡빡한 씬 컨테이너가 동적 글리프(블록 꼬리 스텁 + 비트맵)를 안 싣게 한다.

🔴 왜: 컨테이너는 16섹터(4뱅크)를 넘으면 5뱅크를 먹어 캐시 칸(14)이 모자란다(10-24 구엔의탑 — devlog). 원판에 없던 5뱅크를
막으려면 컨테이너 바이트를 줄여야 하는데, 문안은 못 줄이고 동적 글리프 꼬리가 컨테이너당 1~2KB 를 차지한다.
⇒ 빡빡한 컨테이너가 쓰는 본문 글자를 상주로 올리고, 상주 칸은 **이름·UI·시스템 같은 늘 상주 글자(`forced_chars`) 밖의, 빡빡한
컨테이너가 안 쓰는 글자 중 쓰는 씬이 적은 것**과 맞바꾼다(제자리 교체 — 앞 코드 번호는 그대로).
⚠ ASCII 는 안 건드린다(반각 글자 테스트·훅이 번호로 찾는다). 정본(`glyph_order.json`)은 세이브에 남는 **이름 글자**의 순서를 지키려는 것이다 — 늘 상주 글자는 안 건드리므로 이름은 안 흔들린다.

    python3 games/pce-ed1/tools/rebalance_glyphs.py          # 정본에 쓴다(되풀이해도 같은 결과)
    python3 games/pce-ed1/tools/rebalance_glyphs.py --check  # 바뀔 게 있나만(0/1)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import containers
import glyphdyn
import translate

CANON = common.GAME_DIR / "script" / "glyph_order.json"
TIGHT = (1284, 1348)  # 글자를 상주로 올려 줄 컨테이너(절대 보호) — 동적 글리프 없이도 4뱅크를 넘기 쉬운 것
PROTECT = ()  # 글자를 올려 주진 않지만 이 컨테이너가 쓰는 글자는 내주지 않는다
NEAR = (1332,)  # 그다음으로 빡빡한 컨테이너 — 내줄 글자를 고를 때 이쪽 블록이 쓰는 글자는 뒤로 미룬다  # 4뱅크를 넘기 쉬운 씬 컨테이너(rel) — 넘는 양이 큰 순이 아니라 번호순


def main(check: bool) -> int:
    doc = json.loads(CANON.read_text())
    canon = doc["order"]
    forced = glyphdyn.forced_chars()
    ids = glyphdyn.body_scene_ids()
    use: dict[str, set[int]] = {}
    for i in ids:
        for ch in translate.body_chars(i):
            use.setdefault(ch, set()).add(i)
    cont = {b["id"]: c["rel"] for c in containers.scan() for b in c["blocks"]}
    tight_use: set[str] = set()
    need: dict[str, int] = {}
    for i in ids:
        if cont.get(i) in PROTECT:
            tight_use |= translate.body_chars(i)
        if cont.get(i) in TIGHT:
            chars = translate.body_chars(i)
            tight_use |= chars
            for ch in chars - set(canon):
                need[ch] = need.get(ch, 0) + 1
    give = sorted((c for c in canon if c not in forced and c not in tight_use and not c.isascii()), key=lambda ch: (sum(cont.get(i) in NEAR for i in use.get(ch, ())), len(use.get(ch, ())), ch))
    first = {ch for i in ids if cont.get(i) == TIGHT[-1] for ch in translate.body_chars(i)}  # 마지막(가장 빡빡한) 컨테이너의 글자 먼저
    want = sorted(need, key=lambda ch: (ch not in first, -need[ch], ch))
    pos = {c: i for i, c in enumerate(canon)}
    new = list(canon)
    for d, n in zip(give, want, strict=False):
        new[pos[d]] = n
    if new == canon:
        print("재배치할 것 없음")
        return 0
    if check:
        print(f"재배치 {sum(a != b for a, b in zip(new, canon, strict=True))}칸 남음")
        return 1
    doc["order"] = new
    CANON.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    print(f"재배치 {sum(a != b for a, b in zip(new, canon, strict=True))}칸 (빡빡한 컨테이너 {TIGHT})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--check" in sys.argv))
