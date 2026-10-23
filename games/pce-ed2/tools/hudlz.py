"""ED2 그래픽 압축(LZSS 변종) 해제기 — 본 프로그램 뱅크 0x68 의 `$57AC` 루틴과 같은 규칙(10-16 HUD 판 추적, `docs/status.md` 「남은 일」 4).

규칙(코드 읽기 + 해제 결과가 HUD 타일로 풀리는 것으로 확인):
    링 256B · 처음엔 0 · 쓰기 포인터 0xEF
    비트는 **MSB 먼저**, 바이트가 바닥나면 스트림에서 새 제어 바이트를 읽는다(`$5763`)
    비트 1 = 날바이트 1개(스트림에서 읽어 링과 출력에 쓴다)
    비트 0 = 오프셋 1바이트(링 안 절대 위치)를 읽고, 길이는 **니블 읽기**(`$5776`): 처음 부르면 스트림에서 바이트를 읽어 윗니블, 다음에 아랫니블 → 길이 = 니블 + 2
⚠ pce-ed1 의 `hud_lz` 는 길이를 **비트 흐름에서** 읽는 다른 변종이라 이 스트림을 못 푼다(노이즈로 풀린다).
"""


def decode(src: bytes, pos: int, nbytes: int) -> tuple[bytes, int]:
    """(풀린 바이트, 끝 위치)."""
    ring = bytearray(256)
    ptr = 0xEF
    out = bytearray()
    bits, flag, nib = 1, 0, None

    def byte():
        nonlocal pos
        v = src[pos]
        pos += 1
        return v

    while len(out) < nbytes:
        c = bits & 1  # `LSR $35` — 1 이면 새 제어 바이트
        bits >>= 1
        if c:
            flag = byte()
            bits |= 0x80
        bit = flag >> 7
        flag = (flag << 1) & 0xFF
        if bit:
            v = byte()
            ring[ptr] = v
            ptr = (ptr + 1) & 0xFF
            out.append(v)
        else:
            off = byte()
            if nib is None:
                v = byte()
                nib = v & 0x0F
                n = v >> 4
            else:
                n, nib = nib, None
            for _ in range(n + 2):
                v = ring[off]
                off = (off + 1) & 0xFF
                ring[ptr] = v
                ptr = (ptr + 1) & 0xFF
                out.append(v)
    return bytes(out[:nbytes]), pos


def encode(data: bytes) -> bytes:
    """`decode` 의 역 — 최적 파싱(1/16 바이트 단위 비용, 니블 짝 상태를 기억한다).
    링 규칙: 출력 k 번째 바이트는 링 자리 `(0xEF + k) & 0xFF` 에 쓰인다 → 복사 원천은 이전 출력 `j`(거리 ≤ 256, 앞쪽은 0 으로 채운 256B)의 `(0xEF + j) & 0xFF`.
    비용: 플래그 비트 2 · 날바이트 16 · 복사 16(오프셋) + 니블(짝 첫 번째 16 · 둘째 0)."""
    n = len(data)
    pad = bytes(256) + data  # 앞 256B 는 링의 처음 0
    INF = 1 << 60
    # dp[i][p]: i 바이트까지 냈고 니블 대기 상태 p(0 없음 · 1 대기)일 때 최소 비용, 그 직전 선택
    dp = [[INF, INF] for _ in range(n + 1)]
    prev: list[list[tuple | None]] = [[None, None] for _ in range(n + 1)]
    dp[0][0] = 0
    for i in range(n):
        for p in (0, 1):
            c0 = dp[i][p]
            if c0 >= INF:
                continue
            # 날바이트
            c = c0 + 18
            if c < dp[i + 1][p]:
                dp[i + 1][p] = c
                prev[i + 1][p] = (i, p, "L", 0, 0)
            # 복사: 같은 값이 앞쪽(거리 1~256)에 있는 모든 j 에서 최장 일치
            best = {}
            for j in range(max(0, i - 256), i):  # 출력 인덱스 j (pad 좌표로는 j+256)
                L = 0
                while L < 17 and i + L < n and pad[j + 256 + L] == pad[i + 256 + L]:
                    L += 1
                if L >= 2 and L not in best:
                    best[L] = j
            # 앞 256B 0 채움(출력 인덱스 음수) — 데이터가 0 으로 시작하는 구간
            for jj in range(i - 256, 0):
                if jj < i - 256:
                    continue
                L = 0
                while L < 17 and i + L < n and pad[jj + 256 + L] == pad[i + 256 + L]:
                    L += 1
                if L >= 2 and L not in best:
                    best[L] = jj
            for L, j in best.items():
                # L 이하 모든 길이도 같은 원천으로 가능
                for l2 in range(2, L + 1):
                    nib = 16 if p == 0 else 0
                    c = c0 + 2 + 16 + nib
                    np_ = 1 if p == 0 else 0
                    if i + l2 <= n and c < dp[i + l2][np_]:
                        dp[i + l2][np_] = c
                        prev[i + l2][np_] = (i, p, "C", j, l2)
    p = 0 if dp[n][0] <= dp[n][1] else 1
    toks = []
    i = n
    while i > 0:
        pi, pp, kind, j, l2 = prev[i][p]
        toks.append((kind, j, l2, data[pi] if kind == "L" else 0))
        i, p = pi, pp
    toks.reverse()
    out = bytearray()
    flag_pos = None
    bits_left = 0
    nib_pos = None  # 윗니블을 쓴 바이트 자리(아랫니블 대기)

    def put_bit(b):
        nonlocal flag_pos, bits_left
        if bits_left == 0:
            flag_pos = len(out)
            out.append(0)
            bits_left = 8
        bits_left -= 1
        out[flag_pos] |= b << bits_left

    for kind, j, l2, lit in toks:
        if kind == "L":
            put_bit(1)
            out.append(lit)
        else:
            put_bit(0)
            out.append((0xEF + j) & 0xFF)
            if nib_pos is None:
                nib_pos = len(out)
                out.append((l2 - 2) << 4)
            else:
                out[nib_pos] |= l2 - 2
                nib_pos = None
    return bytes(out)
