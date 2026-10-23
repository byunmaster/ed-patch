"""안내 화면 줄을 **줄마다 화면 정중앙**에 — 그리기 호출의 x 즉값(`mov #imm,r4`)을 줄마다 다시 쓴다.

🔴 **왜 즉값인가** (마스터 10-16 「ss ed3 은 추천으로」 = 화면 정중앙). 안내 화면은 줄마다 `jsr @draw` 로 그리고, 호출마다 시작 x 가
`mov #24,r4`(jsr 지연 슬롯)로 박혀 있다 — 원문은 이 x 를 두고 **앞 공백(ASCII 1칸 = 6px)** 으로 가운데를 흉내 냈고(`center_notice`),
공백은 6px 단위라 줄 중심이 3px 씩 어긋났다(실측: 「디스크２에서 시작합니다」 화면 중심이 135·141·144·147px 로 흩어졌다).
즉값은 **1px 단위**라 규칙 2-8·2-14 C(줄 끝 `. , …` 제외, 반 픽셀은 왼쪽)를 그대로 쓸 수 있다.

⚠ 좌표계 — 에뮬 캡처(프레임 330px, 게임 320px 은 5..324)로 **잰 값**이다:
  · 글자 폭: 한글(2바이트) **12px**, ASCII(숫자·영문·공백) **6px** — 그리기 구조체 `0x06095AB0+62/+64`(워크램)를 직접 읽었다.
  · 글자가 시작하는 프레임 x = 즉값 + 앞 공백 × 6 + **14** — `이 기록은`(즉값 24·앞 공백 14)이 프레임 122 에서 시작하는 것으로 잰다.
  · 화면 정중앙 = 프레임 **165** (330/2). 그러므로 `즉값 = 151 − W/2 − 앞 공백 × 6` (W = 줄 폭 px, 줄 끝 부호 제외).
  ⓘ 글리프는 오른쪽 1px 이 비어 눈에 보이는 중심은 박스 중심보다 0.5px 왼쪽이다(하드서브 `_adv` 와 같은 약속 — 박스 기준).

⚠ **한 호출이 문자열 둘을 번갈아 그리는 자리**(디스크１/２ 변형 · 본체RAM/카트리지 변형 · `%d 번째`/`두 번째` 변형)는 즉값이 하나라서
  **가장 왼쪽 시작점**을 즉값으로 두고 나머지는 앞 공백으로 맞춘다 — 폭 차가 홀수 칸이면 변형 하나가 3px 어긋난다(`errors`).
⚠ **`%2d%s` 로 숫자·문구를 끼우는 합성 줄**(용량 부족 화면 D 의 `본체RAM에 NN…`)은 형식 문자열 + 끼우는 문자열의 폭을 더해 잰다 —
  `%2d` 는 **두 자리 숫자(12px)** 로 센다(100 이상이 되면 폭이 늘어 그 줄만 오른쪽으로 6px 쯤 밀린다).
"""

import math

BASE = 0x06004000  # `/0.BIN` 적재 주소
HANGUL_PX = 12  # 2바이트 글리프 advance
ASCII_PX = 6  # 1바이트 글리프 advance
ORIGIN = 14  # 글자 시작 프레임 x = 즉값 + 앞 공백×6 + ORIGIN
CENTER = 165.0  # 화면 정중앙(프레임 px) — 330/2
TRAIL_PUNCT = (b"\x2e", b"\x2c", b"\x81\x63")  # `.` `,` `…` — 줄 끝에 오면 폭에서 뺀다(규칙 2-8)

#   (즉값 주소 = `mov #imm,r4` 명령 자리, 그 호출이 그리는 문자열 주소들)
#   화면: H 카트리지·본체RAM 백업 · A 디스크 시작/교체 · B 디스크 이동 안내 · C 백업 용량 부족 · E 디스크 확인 · F 백업 준비 안 됨 · G 저장 데이터 관리.
SITES = (
    # H
    (0x06044298, (0x06044158, 0x0604417C)),
    (0x060442C0, (0x060441A4, 0x060441C4)),
    (0x060442C8, (0x060441E8,)),
    (0x060442D0, (0x06044208,)),
    # A
    (0x0604526E, (0x0604517C,)),
    (0x06045280, (0x06045198, 0x060451C0)),
    (0x0604528A, (0x060451E8,)),
    (0x06045292, (0x06045208,)),
    # B
    (0x060453B8, (0x06045308,)),
    (0x060453C0, (0x0604532C,)),
    (0x060453C8, (0x0604534C,)),
    (0x060453D0, (0x06045208,)),
    # C
    (0x0604560A, (0x06045578,)),
    (0x06045612, (0x060455A0,)),
    (0x0604561A, (0x06045208,)),
    # E
    (0x0604636E, (0x060460A8,)),
    (0x06046376, (0x060460C8,)),
    (0x0604637E, (0x060460EC,)),
    (0x06046386, (0x0604610C,)),
    # F
    (0x06046218, (0x06045FC8,)),
    (0x06046220, (0x06045FEC,)),
    (0x06046228, (0x0604600C,)),
    (0x06046230, (0x06046034,)),
    (0x060462A6, (0x06046058,)),
    (0x060462AE, (0x06045FEC,)),
    (0x060462B6, (0x0604600C,)),
    (0x060462BE, (0x06046084,)),
    # G
    (0x06045E26, (0x06045C2C,)),
    (0x06045E2E, (0x06045C58,)),
    (0x06045E36, (0x06045C7C,)),
    # D — 용량 부족으로 이동·저장 불가(합성 줄은 `(형식, (끼우는 문자열…))`)
    (0x06045CF8, (0x06045AA4,)),
    (0x06045D0C, (0x06045AC4, 0x06045AE8)),
    (0x06045D1A, (0x06045B10,)),
    (0x06045D28, (0x06045B38,)),
    (0x06045D58, ((0x06045B74, (0x06045B5C,)),)),
    (0x06045D60, (0x06045B8C,)),
    (0x06045D76, ((0x06045BB0, (0x06045B5C,)),)),
    (0x06045D88, (0x06045B8C,)),
    (0x06045DB0, (0x06045B38,)),
    (0x06045DDC, ((0x06045B74, (0x06045B5C,)), (0x06045BC4, (0x06045B5C,)))),
)


def _off(addr):
    return addr - BASE


def read_x(data, imm_addr):
    """`mov #imm,r4`(`E4 ii`) 의 imm — 부호 있는 8비트."""
    o = _off(imm_addr)
    assert data[o] == 0xE4, (
        f"{imm_addr:#x} 가 `mov #imm,r4` 가 아니다({data[o]:02x}) — 자리를 잘못 짚었다"
    )
    v = data[o + 1]
    return v - 256 if v > 127 else v


def parse(data, addr):
    """문자열 하나 — `{lead, body, width, budget}`. 본문은 앞 공백 뒤부터 첫 제어 바이트(<0x20)까지."""
    o = _off(addr)
    i = o
    while data[i] == 0x20:
        i += 1
    lead = i - o
    j = i
    while data[j] >= 0x20:
        j += 2 if data[j] >= 0x81 else 1
    body = bytes(data[i:j])
    z = j
    while z < len(data) and data[z] == 0:
        z += 1
    return {
        "addr": addr,
        "lead": lead,
        "body": body,
        "tail": bytes(data[j : j + 1]),
        "width": width(body),
        "budget": (j - o) + max(0, z - j - 1),
    }


def width(body):
    """줄 폭(px) — 줄 끝 `. , …` 제외. `%d` 는 한 자리 숫자(6px)로 센다(슬롯 번호)."""
    for p in TRAIL_PUNCT:
        if body.endswith(p):
            body = body[: -len(p)]
            break
    px = 0
    i = 0
    while i < len(body):
        if body[i : i + 2] == b"%d":
            px += ASCII_PX
            i += 2
        elif body[i] >= 0x81:
            px += HANGUL_PX
            i += 2
        else:
            px += ASCII_PX
            i += 1
    return px


def ideal(w):
    """글자 시작 위치(즉값 좌표, 앞 공백 포함) — 박스를 정중앙에, 반 픽셀은 왼쪽(규칙 2-14 C)."""
    return math.floor(CENTER - ORIGIN - w / 2)


def variant(data, entry):
    """사이트가 그리는 문자열 하나 — 정적(`addr`)이거나 합성(`(형식, (끼우는 문자열…))`).

    합성은 `%2d` 를 두 자리 숫자(`00`)로, `%s` 를 끼우는 문자열(앞 공백 포함)로 바꿔 폭을 잰다. 앞 공백은 **형식 문자열**의 것이다."""
    if isinstance(entry, int):
        p = parse(data, entry)
        return {**p, "addr": entry}
    fmt, args = entry
    p = parse(data, fmt)
    text = p["body"].replace(b"%2d", b"00")
    for a in args:
        q = parse(data, a)
        text = text.replace(b"%s", b" " * q["lead"] + q["body"], 1)
    return {**p, "addr": fmt, "width": width(text), "composite": True}


def _owner(entry):
    """앞 공백을 바꿀 수 있는 문자열의 주소 — 합성 줄은 형식 문자열."""
    return entry if isinstance(entry, int) else entry[0]


def _locked():
    """앞 공백을 **못 바꾸는** 문자열 — 한 사이트가 혼자 쓰는 게 아니거나 여러 사이트가 같이 쓰면 즉값만 움직인다."""
    uses = {}
    for _, entries in SITES:
        for e in entries:
            uses[_owner(e)] = uses.get(_owner(e), 0) + 1
    single = {_owner(e) for _, entries in SITES if len(entries) == 1 for e in entries}
    return {a for a, n in uses.items() if n > 1} | single


def plan(data):
    """사이트마다 `{imm_addr, x_old, x_new, strings:[{addr, lead_old, lead_new}], errors:[…]}`."""
    locked = _locked()
    out = []
    for imm_addr, entries in SITES:
        strs = [variant(data, e) for e in entries]
        want = [ideal(s["width"]) for s in strs]
        fixed = [k for k, s in enumerate(strs) if s["addr"] in locked]
        if fixed:  # 앞 공백이 못 박힌 문자열이 즉값을 정한다 — 나머지(이 사이트만 쓰는 변형)가 앞 공백으로 맞춘다
            k0 = fixed[0]
            x = want[k0] - strs[k0]["lead"] * ASCII_PX
        else:
            x = min(want)
        leads = [
            strs[k]["lead"] if k in fixed else max(0, round((want[k] - x) / ASCII_PX))
            for k in range(len(strs))
        ]
        errs = [
            (s["addr"], want[k] - (x + leads[k] * ASCII_PX))
            for k, s in enumerate(strs)
            if want[k] != x + leads[k] * ASCII_PX
        ]
        for k, s in enumerate(strs):
            need = leads[k] + len(s["body"]) + 1
            assert need <= s["budget"] + 1, (
                f"{s['addr']:#x} 앞 공백 {leads[k]} + 본문 {len(s['body'])}B 가 칸({s['budget']}B)을 넘는다"
            )
        assert -128 <= x <= 127, f"{imm_addr:#x} 즉값 {x} 이 범위를 벗어난다"
        out.append(
            {
                "imm_addr": imm_addr,
                "x_old": read_x(data, imm_addr),
                "x_new": x,
                "strings": [
                    {"addr": s["addr"], "lead_old": s["lead"], "lead_new": leads[k]}
                    for k, s in enumerate(strs)
                ],
                "errors": errs,
                "parsed": strs,
            }
        )
    return out


def patch(data):
    """`/0.BIN` bytes → 새 bytes(크기 불변). 즉값과 (변형 자리의) 앞 공백만 바꾼다."""
    out = bytearray(data)
    for p in plan(data):
        o = _off(p["imm_addr"])
        out[o + 1] = p["x_new"] & 0xFF
        for s, ps in zip(p["strings"], p["parsed"], strict=True):
            if s["lead_new"] == s["lead_old"]:
                continue
            a = _off(s["addr"])
            total = ps["lead"] + len(ps["body"]) + 1
            blob = b" " * s["lead_new"] + ps["body"] + ps["tail"]
            assert len(blob) <= ps["budget"] + 1
            out[a : a + max(total, len(blob))] = blob.ljust(max(total, len(blob)), b"\x00")
    return bytes(out)
