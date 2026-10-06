"""개발용 옵션 — 환경변수가 없으면 아무것도 안 한다(배포 빌드 보호) · 켜면 이자벨 HP 만 바뀐다. 원본 없이 돈다(가짜 PARAM)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import dev_options as D
import param as P


def fake():
    b = bytearray(0x9000)
    base, st, n = P.ENEMY
    for k in range(n):
        name = D.ENEMY_NAME if k == 28 else f"X{k}"
        rec = name.encode("shift_jis")
        b[base + k * st : base + k * st + len(rec)] = rec
    b[base + 28 * st + D.HP_OFF : base + 28 * st + D.HP_OFF + 2] = (5000).to_bytes(2, "big")
    return bytes(b)


class DevOptions(unittest.TestCase):
    def tearDown(self):
        os.environ.pop(D.ENV_ISABEL_HP, None)

    def test_off_by_default_changes_nothing(self):
        os.environ.pop(D.ENV_ISABEL_HP, None)
        b = fake()
        self.assertEqual(D.patch_param(b), b)

    def test_on_changes_only_isabel_hp(self):
        os.environ[D.ENV_ISABEL_HP] = "1"
        b = fake()
        out = D.patch_param(b)
        diff = [i for i in range(len(b)) if b[i] != out[i]]
        base, st, _ = P.ENEMY
        self.assertEqual(diff, [base + 28 * st + D.HP_OFF, base + 28 * st + D.HP_OFF + 1])  # HP 두 바이트만
        self.assertEqual(int.from_bytes(out[base + 28 * st + D.HP_OFF : base + 28 * st + D.HP_OFF + 2], "big"), 1)


if __name__ == "__main__":
    unittest.main()
