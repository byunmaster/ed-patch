"""🔴 **빌드가 결정적인가** — 같은 입력이면 같은 바이트가 나오는지 실제로 잰다.

    python3 tools/check_determinism.py          # 두 번 굽고 sha1 을 맞댄다
    python3 tools/check_determinism.py --keep   # 두 번째 산출물을 남긴다(조사용)

레포 **제1 원칙**이다(루트 CLAUDE.md) — 결과가 환경이나 회차를 타면 **버그를 재현할 수 없어
조사 자체가 불가능**해진다. PS1 은 진작 이 도구를 갖고 있었는데 새턴은 없었다(2026-09-05).

## 무엇을 지우고 다시 만드나

- **빌드 이미지** — `patch_title` 이 원본에서 사본을 새로 뜬다. 체인 전량이 다시 돈다.
- **`work/derived/scn_shortfall.json`** — `patch_scn` 이 매 회차 **제안**하는 값이다.
  🔴 빌드는 정본(`scn_expand.json`)만 읽어야 한다. 제안이 결과를 바꾸면 **회차마다 이미지가
     달라진다** — 실제로 그렇게 진동한 적이 있다(2026-08-31, devlog 55).

⚠ **덤프(`scn_jp/`·`ui_jp.json`·`title_jp.json`)는 안 지운다** — 원본에서 파생될 뿐이고,
  지우면 체인이 그걸 만들지 않아 그냥 죽는다(재생성은 `dump_*.py` 몫이다).

## 어디가 위험한가 — 배치

이 게임의 재삽입은 **자리를 고르는 일**이다(FFD · 인접 병합 · 고정점). 파이썬 `dict`/`set`
순회가 한 자리라도 새면 **회차마다 다른 자리에 깔린다.** 그래서 정렬 키를 전부 `(-크기,
오프셋)` 처럼 **전순서**로 두는데, 이 도구가 그 약속을 실제로 지키는지 본다.
"""

import hashlib
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common

IMG = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
PROPOSAL = os.path.join(common.OUT_DIR, "scn_shortfall.json")
GATE = os.path.join(os.path.dirname(common.GAME_DIR), "..", "scripts", "check.sh")


def sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def build():
    """체인을 통째로 돌린다 — 실패하면 그 자리에서 멈춘다(산출물은 이미 무효화돼 있다)."""
    r = subprocess.run(
        ["sh", os.path.abspath(GATE)],
        cwd=os.path.dirname(os.path.dirname(common.GAME_DIR)),
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode:
        print(r.stdout[-2000:])
        raise SystemExit("빌드가 실패했다 — 결정성을 재기 전에 그걸 먼저 고친다")


def main():
    common.verify_source()
    if not os.path.exists(IMG):
        print("  1회차 — 이미지가 없어 먼저 굽는다")
        build()
    a = sha1(IMG)
    print(f"  1회차 sha1 {a}")

    os.remove(IMG)
    if os.path.exists(PROPOSAL):
        os.remove(PROPOSAL)  # 제안은 지운다 — 빌드는 정본만 읽어야 한다
    print("  2회차 — 이미지와 제안을 지우고 체인을 다시 돌린다")
    build()
    b = sha1(IMG)
    print(f"  2회차 sha1 {b}")

    if a != b:
        raise SystemExit(
            "🔴 **두 회차의 바이트가 다르다** — 배치 어딘가가 `dict`/`set` 순회를 타고 있다.\n"
            "   정렬 키가 전순서인지 본다(`patch_scn._place` · `migrate` · `patch_ui.sys_pack`)."
        )
    print("  ✅ 두 번 구워 **바이트 동일** — 빌드는 결정적이다")


if __name__ == "__main__":
    main()
