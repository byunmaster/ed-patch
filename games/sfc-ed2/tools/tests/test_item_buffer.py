"""아이템 이름 15B 패치 — 소비자 루프(`$C0:D9FB`·`$C0:DD18`)를 파이썬으로 옮겨 새 표 꼴(16B 칸)에서 줄 버퍼가 맞게 나오는지 본다.

원본 롬 없이 돈다. 모델은 `patches.py` 의 스텁 논리 그대로다: 끝 토큰 `06` 이거나 색인 14 에서 멈춘다.
"""

import unittest

PAIR = b"\x80\x00"


def consume_a(buf: bytes) -> bytes:
    """`$C0:D9E9` — 줄 버퍼 16B(+0 종단). 반환 = dest[1..16]."""
    x = 0
    while buf[x : x + 2] == PAIR:  # 앞쪽 `80 00` 쌍 건너뛰기(16비트 비교)
        x += 2
    dest, y = {}, 1
    while True:
        b = buf[x]
        dest[y] = b
        if b == 0x06:
            break  # (`$80` 뒤 `06` 예외는 이 시험 이름에 없다)
        if x == 14:
            y += 1
            break  # 15B 꽉 찬 이름 — 끝 토큰 없이 끝낸다
        x += 1
        y += 1
    if buf[x] == 0x06:
        while y != 0x10:  # 패딩 `$20` — 원본과 같다
            dest[y] = 0x20
            y += 1
            if y > 0x10:
                raise AssertionError("패딩 루프가 안 끝난다")
        dest[y] = 0
    else:
        y = 0x10
        dest[y] = 0
    return bytes(dest[i] for i in range(1, 0x11) if i in dest)


class ItemBuffer(unittest.TestCase):
    def rec(self, payload: bytes) -> bytes:
        if len(payload) == 15:
            return payload + b"\x00"
        pad = 14 - len(payload)
        return PAIR * (pad // 2) + payload + (b" " if pad % 2 else b"") + b"\x06\x00"

    def test_short_name_unchanged(self):
        name = b"\x81\x10\x81\x11"  # 전각 둘
        out = consume_a(self.rec(name)[:15])
        self.assertTrue(out.startswith(name))
        self.assertEqual(len(out), 16)
        self.assertEqual(out[len(name) :].strip(b"\x20\x00\x06"), b"")

    def test_full_15_bytes(self):
        name = b"\x81\x10" * 7 + b"\x20"
        out = consume_a(self.rec(name)[:15])
        self.assertEqual(out[:15], name)
        self.assertEqual(out[15:], b"\x00")  # dest[16] = 0 종단

    def test_odd_pad_goes_behind(self):
        name = b"\x81\x10" * 6 + b"\x20"  # 13B → 앞 쌍 없이 뒤 공백
        self.assertEqual(self.rec(name)[:15], name + b" " + b"\x06")


if __name__ == "__main__":
    unittest.main()
