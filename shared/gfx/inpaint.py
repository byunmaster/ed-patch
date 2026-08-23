"""결정적 패치 인페인트 — 지운 자리를 같은 그림의 다른 곳에서 떠 온다.

타이틀 화면의 원판 로고를 지우면 그 자리를 메워야 한다. 확산(diffusion) 인페인트는
매끈하게 메워서 **배경 질감이 통째로 사라진다** — PS1 타이틀에서 실측: 세계지도가 큼직한
단색 얼룩이 되고 밝기가 178 → 126 으로 내려앉았다. 그 위에 짙은 테두리의 로고를 얹으면
어두운 데 어두운 게 겹쳐 **테두리가 안 보인다**(유저 QA 2026-08-23 로 발각).

여기서는 지울 자리를 **같은 그림의 성한 곳에서 가장 잘 맞는 조각으로** 메운다. 해안선·섬
같은 결이 살아난다. 2초면 돈다.

⚠ 무작위를 쓰지 않는다(레포 제1 원칙: 빌드는 결정적). 후보를 격자로 전수 훑고 동점은
  좌표순으로 가른다 — 같은 입력이면 어디서 돌려도 같은 바이트가 나온다.
⚠ 원천(`src_ok`)에서 **글자류를 빼야 한다** — 안 빼면 저작권 문구 조각(「1999」)이
  배경에 박힌다(실측).
"""

import numpy as np
from scipy.ndimage import gaussian_filter


def _patches(ok, T, C, stride=2):
    """(y, x) 격자에서 완전히 알려진 (T+2C)² 후보 패치를 모은다."""
    P = T + 2 * C
    H, W = ok.shape
    ys = np.arange(0, H - P + 1, stride)
    xs = np.arange(0, W - P + 1, stride)
    cum = np.cumsum(np.cumsum(ok.astype(np.int32), 0), 1)
    cum = np.pad(cum, ((1, 0), (1, 0)))
    cnt = (
        cum[ys[:, None] + P, xs[None] + P]
        - cum[ys[:, None], xs[None] + P]
        - cum[ys[:, None] + P, xs[None]]
        + cum[ys[:, None], xs[None]]
    )
    gy, gx = np.nonzero(cnt == P * P)
    return np.stack([ys[gy], xs[gx]], 1)


def smooth_fill(img, mask, iters=600):
    """확산 인페인트 — 둘레 값에서 매끄럽게 번진다. 질감은 없고 **밝기만 맞다**."""
    v = img.astype(np.float32).copy()
    v[mask] = img[~mask].mean(0)
    for _ in range(iters):
        acc = np.zeros_like(v)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            acc += np.roll(np.roll(v, dy, 0), dx, 1)
        v[mask] = (acc / 4)[mask]
    return v


def fill(img, mask, src_ok, T=6, C=4, stride=2, match_low=12.0, target_mean=None, smooth_mix=0.0):
    """img(H,W,3) 의 mask 자리를 src_ok 영역의 패치로 메운다.

    🔴 `match_low` 는 **판이 생기는 걸 막는다.** 패치는 질감을 살리지만 밝기를 못 맞춘다 —
      구멍이 크면(실측: 로고 상자의 86%) 참조할 둘레가 모자라 통째로 어두워지고, 그 경계가
      **사각형 판**으로 보인다(실측: 상자 안 212 → 141, 바깥은 그대로. 유저 QA 2026-08-23).
      확산은 반대로 밝기는 맞고 질감을 잃는다. 그래서 **저주파는 확산, 고주파는 패치**로
      섞는다. 0 이면 안 섞는다.
    """
    P = T + 2 * C
    hole = mask.copy()
    out = img.astype(np.float32).copy()
    known = ~mask
    cand = _patches(src_ok & known, T, C, stride)
    if len(cand) == 0:
        return smooth_fill(img, hole)
    bank = np.stack([out[y : y + P, x : x + P] for y, x in cand]).astype(np.float32)
    flat = bank.reshape(len(bank), -1)
    H, W = mask.shape
    todo = [
        (y, x)
        for y in range(0, H - P + 1, T)
        for x in range(0, W - P + 1, T)
        if mask[y + C : y + C + T, x + C : x + C + T].any()
    ]
    for _ in range(40):
        if not todo:
            break
        # 알려진 이웃이 많은 칸부터 (동점은 좌표순) — 무작위 없음
        todo.sort(key=lambda p: (-known[p[0] : p[0] + P, p[1] : p[1] + P].sum(), p[0], p[1]))
        left = []
        for y, x in todo:
            k = known[y : y + P, x : x + P]
            if k.sum() < P * P * 0.35:
                left.append((y, x))
                continue
            tgt = out[y : y + P, x : x + P].astype(np.float32).ravel()
            wt = np.repeat(k.ravel(), 3).astype(np.float32)
            sse = (((flat - tgt) ** 2) * wt).sum(1)
            best = int(np.argmin(sse))
            sel = mask[y + C : y + C + T, x + C : x + C + T]
            out[y + C : y + C + T, x + C : x + C + T][sel] = bank[best][C : C + T, C : C + T][sel]
            mask[y + C : y + C + T, x + C : x + C + T] = False
            known[y + C : y + C + T, x + C : x + C + T] = True
        if len(left) == len(todo):
            break
        todo = [p for p in left if mask[p[0] + C : p[0] + C + T, p[1] + C : p[1] + C + T].any()]
    if match_low:
        low = smooth_fill(img, hole)
        bp = np.dstack([gaussian_filter(out[:, :, c], match_low) for c in range(3)])
        bs = np.dstack([gaussian_filter(low[:, :, c], match_low) for c in range(3)])
        out[hole] = np.clip(out[hole] - bp[hole] + bs[hole], 0, 255)
    if smooth_mix:
        # 🔴 **확산과 섞는다.** 패치만 쓰면 가짜 해안선이 생겨 둘레 지도와 안 이어진다
        #   (유저 지적 2026-08-23 「연결이 어색하다 · 훼손된 것 같다」). 확산은 경계값에서
        #   번져 **이어짐이 보장**되는 대신 질감이 없다. 확산을 주로 하고 패치를 질감으로 얹는다.
        sm = smooth_fill(img, hole)
        out[hole] = out[hole] * (1 - smooth_mix) + sm[hole] * smooth_mix
    if target_mean:
        # 🔴 **메운 자리의 밝기를 부르는 쪽이 정한 값에 맞춘다.** 확산은 구멍 *경계*에서
        #   번지는데, 큰 글자를 지우면 그 경계가 획 사이의 어두운 틈뿐이라 메운 자리가
        #   통째로 어두워진다(실측: 로고 상자 안 133 vs 바깥 190 — 사각형 음영으로 보인다.
        #   유저 인게임 지적 2026-08-23). 참조를 넓혀도, 구멍 둘레에 맞춰도 안 풀린다 —
        #   **상자 바깥 배경**을 기준으로 이득을 맞춰야 그 사각형이 사라진다.
        got = float(out[hole].mean())
        if got > 1:
            out[hole] = np.clip(out[hole] * (target_mean / got), 0, 255)
    return out
