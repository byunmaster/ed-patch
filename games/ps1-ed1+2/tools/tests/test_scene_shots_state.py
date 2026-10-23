"""대사 보기 하네스의 상태 캐시가 **다른 롬으로 만든 상태를 되살리지 않는지** 못 박는다(ps1-ed3 10-20 사고 — 「줄」이 「앗」)."""

import os
import pathlib
import sys
import tempfile

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from scene_shots import shots as S


def _mk(d, name="pre_talk.state"):
    p = os.path.join(d, name)
    with open(p, "wb") as f:
        f.write(b"x")
    return p


def test_mismatched_rom_discards_states():
    with tempfile.TemporaryDirectory() as d:
        S.check_state_meta(d, "a" * 40)
        p = _mk(d)
        S.check_state_meta(d, "b" * 40)  # 다른 롬
        assert not os.path.exists(p)


def test_same_rom_keeps_states():
    with tempfile.TemporaryDirectory() as d:
        S.check_state_meta(d, "a" * 40)
        p = _mk(d)
        S.check_state_meta(d, "a" * 40)
        assert os.path.exists(p)


def test_missing_meta_is_not_trusted():
    with tempfile.TemporaryDirectory() as d:
        p = _mk(d)  # 메타 없는 옛 캐시
        S.check_state_meta(d, "a" * 40)
        assert not os.path.exists(p)


def test_image_sha1_covers_whole_file():
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "x.bin")
        with open(f, "wb") as fh:
            fh.write(b"\0" * (20 << 20))
        a = S.image_sha1(f)
        with open(f, "r+b") as fh:
            fh.seek(18 << 20)  # 앞 16MB 밖
            fh.write(b"\1")
        assert S.image_sha1(f) != a


if __name__ == "__main__":
    for k, v in sorted(globals().items()):
        if k.startswith("test_"):
            v()
            print(f"  ok  {k}")
