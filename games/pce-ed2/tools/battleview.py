"""전투 문구 보기 — 서장 슬라임 전투의 덩이(메시지 38: 나타남 · 이름A · 행동A · 이름B · 행동B)를 **몬스터 하나의 실제 줄**로 바꿔 넣고 실제 전투 로그 창으로 찍는다(마스터 10-19 전수 검수).

⚠ 가짜 부류(덩이 교체): 행동 줄의 `1B` 는 바로 앞 「이름」 줄 글을 끼워 넣는다 — 그래서 나타남(0)·이름A(1)·행동A(2)·이름B(3)·행동B(4) 자리에 **같은 몬스터의** 줄을 넣는다.
몬스터 원래 줄 번호 규약(나타남·이름·행동의 배치)은 몬스터마다 다르지만 로그 창에 뜨는 글은 줄 안에 다 있다. 행동의 대상(아트라스)·피해 수는 슬라임 전투 상태의 값이다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lz
import package
import pceview
from PIL import Image
import hashlib

ENC_PLAN = [("right", 50), ("left", 100), ("right", 100), ("left", 100), ("right", 100)]  # 서장 필드 → 슬라임 조우(결정적, 242프레임째)


def to_encounter(cue: str, bram: str, state_path: str):
    """서장 필드에서 걸어 슬라임과 만나는 순간(전투 번호 `$3233` = 38 — 나타남 줄이 뜨기 전)에 상태를 저장한다."""
    e = pceview.boot_field(cue, bram)
    for b, n in ENC_PLAN:
        e.hold(b)
        for _ in range(n):
            e.run(1)
            if e.peek(0x3233, 1)[0] == 38:
                break
        else:
            continue
        break
    e.hold(None)
    e.save(state_path)
    return e


def synth_chunk(lines5: list[bytes]) -> bytes:
    """[나타남, 이름A, 행동A, 이름B, 행동B] → LZ 덩이."""
    return lz.encode_opt(b"".join(ln + b"\x00" for ln in lines5) + b"\x00" * 8)


def log_crop(img):
    return img[150:214, 14:214]


def fight(e, state: bytes, data: bytes, gl: bytes, out: Path, tag: str, frames: int = 900, step: int = 12) -> list[str]:
    """덩이 교체 전투를 `frames` 프레임 돌리며 로그 창이 바뀔 때마다 찍는다(공격 반복). 찍은 파일 이름들."""
    p = out / "cur.state"
    p.write_bytes(pceview.patch_state(state, data, gl, 38))
    e.load(str(p))
    e.run(2)
    seen: set[str] = set()
    shots: list[str] = []
    stable: list[str] = []
    for i in range(frames // step):
        e.run(step)
        c = log_crop(e.frame_img)
        h = hashlib.md5(c.tobytes()).hexdigest()
        stable = (stable + [h])[-3:]
        if len(stable) == 3 and len(set(stable)) == 1 and h not in seen and pceview.ink(e.frame_img) >= 0:
            seen.add(h)
            f = out / f"{tag}_{len(shots):02d}.png"
            Image.fromarray(e.frame_img[130:214, 14:214]).save(f)
            shots.append(f.name)
        if i % 4 == 3:
            e.press("i", 4, 4)
    return shots
