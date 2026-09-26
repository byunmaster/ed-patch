"""메시지 창 줄 나누기 — 원 prewrap(ED `0x0607CE74` · ED2 `0x06064268`)을 갈아 끼운 규칙의 **기준 구현**.

    python3 tools/msgwrap.py '문장'     # 한 줄 시험 (슬롯 인코딩 없이 cp932 근사)

## 왜 갈아 끼우나 (2026-09-27, devlog)

메시지 창(호출처 58곳 — 전투·보상·상태·확인 창)은 **그리기 전에** prewrap 이 바이트를 세어
`\\n` 을 넣고, 스플리터가 그 `\\n` 으로 줄 버퍼를 가른다. 원 루틴은 일본어용이라:

- **글자 단위로 끊는다** — `레스` / `1`, `세리오스` / `는` 처럼 묶음 한가운데서 갈린다.
- **끊는 자리의 공백을 다음 줄로 넘긴다** — 줄머리 공백.
- **금칙은 SJIS `。` 하나뿐** — 반각 `.` 은 줄머리에 혼자 떨어진다.
- **병기(`은(는)`)를 접기 전 길이로 잰다** — 조사 훅이 그 뒤(그리기)에서 접으므로 병기마다
  4B 를 헛셈해 일찍 넘기고, 29B 경계에 걸친 병기는 반쪽이 다음 줄로 샌다.

그래서 이 자리는 **어절 단위**로 끊고, 병기는 prewrap **앞에서** 접는다(조사 훅의 셋째
진입점 `접기`). 폭 규칙은 원 루틴 그대로다 — 반각 1B = 0.5칸, 전각 2B = 1칸, 글자를 놓을 수
있는 조건은 **줄 누적 < 28B**(그래서 전각이 13.5칸에서 시작하면 14.5칸까지 간다 —
`typeset_scn.wrap` 이 실기로 확인한 규칙과 같다).

## 규칙 (마스터 지시 09-27 여섯 가지 중 이 자리 몫)

1. 끊는 자리는 **반각 공백**이다. 공백은 `\\n` 으로 바뀐다(= 줄머리·줄끝 공백이 안 남는다).
2. **공백 뒤가 숫자면 끊지 않는다** — `레스 1`·`ＨＰ를 112` 는 한 덩이.
   전각 공백(`　`)은 끊는 자리가 아니다 — 붙여 쓰는 이름(`크루즈　마을`)의 풀칠이다.
3. 어절이 한 줄보다 길 때만 글자 단위로 끊고, 그때 줄머리에 닫는 부호가 오면 **앞 글자와
   같이** 내린다(고아 마침표 금지).
4. 자동으로 끊은 직후의 **명시 개행**과 **줄머리 공백**은 버린다(빈 줄 · 줄머리 공백 금지).
   공백 뒤가 숫자인데 그 공백이 넘치면 앞 공백에서 묶음째 내린다.
5. 🔴 **글자는 하나도 안 잃는다** — 출력에서 공백·개행을 빼면 입력과 같다(관리자 09-27:
   PS1 에서 어절 되물림이 30열 줄의 꼬리를 잃었다). `check_invariant` 가 본다.

⚠ 기계어(`patch_msgwrap.py`)는 이 함수를 **한 줄씩 옮긴 것**이다. 여기를 바꾸면 거기도
  바꾸고, 회귀(`tests/test_msgwrap.py`)가 둘을 같은 입력으로 돌려 대조한다.
"""

import sys

LIMIT = 28  # 줄 누적이 이 값 **미만**일 때만 글자를 놓는다 (원 루틴: `col > 28` 이면 넘김)
BUF = 128  # 메시지 버퍼 (호출자 0x0607528C 의 스택 128B) — 종단 포함
STOP = BUF - 4  # 출력이 여기 닿으면 멈춘다 (2B 글자 + 끼워 넣는 개행 + 종단)
ZERO_W = (1, 2, 3, 14)  # 폭 없는 제어(색) — 원 루틴 점프표의 `0x72` 갈래
NL, SP = 0x0A, 0x20
CLOSE_HALF = b".,!?)"
HANG_TAIL = b".,!?)\"'"  # 29열에 앉을 수 있는 반각 꼬리 부호 — PS1 `HANG_TAIL` 과 같다
CLOSE_SJIS = (0x8141, 0x8142, 0x8148, 0x8149, 0x816A, 0x8176, 0x8178, 0x8163)  # 、。？！）」』…


def clen(c):
    """글자 바이트 수 = 폭. 원 루틴(`0x0607D5D4`)과 같은 판정 — ASCII·반각 가나만 1B."""
    return 1 if (0x20 <= c <= 0x7E or 0xA1 <= c <= 0xDF) else 2


def is_close(buf, i):
    c = buf[i]
    if c in CLOSE_HALF:
        return True
    return clen(c) == 2 and i + 1 < len(buf) and ((c << 8) | buf[i + 1]) in CLOSE_SJIS


def wrap(src, stop=STOP, limit=LIMIT, retreat=True):
    """`src`(NUL 전까지) → 줄을 나눈 바이트. ⚠ 기계어와 **같은 순서**로 쓴다.

    `stop` 은 출력 상한 — 기본값이 기계어의 버퍼(128B)다. 씬 창(`typeset_scn.wordwrap`)은
    빌드 때 한 번 도는 파이썬이라 버퍼가 없다 — `None` 으로 푼다(규칙은 같다).
    `limit` 은 한 줄 예산 — 씬 창은 **한 칸 좁게** 쓴다(`typeset_scn.SCN_LIMIT` 주석).
    ⚠ 기계어는 기본값(`LIMIT`)만 안다 — 회귀가 기본값끼리 대조한다.

    `retreat`(규칙 1 — 마지막 공백에서 끊기)는 **대사·씬 전용**이다(마스터 확정 2026-09-27,
    「대사는 어절 단위·로그는 글자 단위」). 메시지 창(로그성)은 `retreat=False` 로 부른다 —
    넘치면 바로 규칙 3(글자 단위, 고아 부호 방지 포함)으로 간다. 숫자 묶음(규칙 2)·줄머리
    공백 금지(규칙 4)는 **retreat 와 무관하게 그대로**다 — 공백은 넘치기 전에만 놓이므로
    글자 단위로 끊어도 줄머리에 남지 않는다.
    """
    src = bytes(src).split(b"\0", 1)[0]
    stop = len(src) * 2 + 4 if stop is None else stop
    out = bytearray()
    used = 0  # 이 줄 누적 폭 (B)
    cand = -1  # 끊을 수 있는 공백의 out 자리
    cused = 0  # 그 공백 앞까지의 누적
    ls = 0  # 이 줄이 시작하는 out 자리
    last = -1  # 이 줄 마지막 글자의 out 자리 (고아 부호용)
    auto = False  # 방금 자동으로 끊었고 그 뒤로 아무것도 안 놓았다
    i = 0
    while i < len(src) and len(out) < stop:
        c = src[i]
        if c == NL:
            i += 1
            if auto:
                continue  # 규칙 4 — 자동 개행 + 명시 개행 = 빈 줄
            out.append(NL)
            used, cand, last, ls = 0, -1, -1, len(out)
            continue
        if c in ZERO_W:
            out.append(c)
            i += 1
            continue
        if c == SP:
            i += 1
            if used == 0 or out[-1] == SP:
                continue  # 규칙 4 — 줄머리 공백 · 겹공백(앞 공백에서 끊으면 뒤 공백이 줄머리에 온다)
            nxt = src[i] if i < len(src) else 0
            digit = 0x30 <= nxt <= 0x39  # 규칙 2 — 공백 뒤 숫자는 묶음
            if used >= limit and digit and cand >= 0:
                out[cand] = NL  # 묶음째 내린다 — `레스` / `1` 이 되지 않게
                used -= cused + 1
                ls, cand = cand + 1, -1
            if used >= limit:
                out.append(NL)  # 공백 자체가 넘친다 — 거기서 끊는다
                used, cand, last, ls, auto = 0, -1, -1, len(out), True
                continue
            if not digit:
                cand, cused = len(out), used
            out.append(SP)
            used += 1
            continue
        n = clen(c)
        # 🔴 **반각 꼬리 부호는 29열까지**(마스터 판정 2026-09-27 — PS1 과 같게). 틀은 29열인데
        #    원 루틴도 드로어도 29열을 통째로 비워 둬, 「…회복되었다」 / 「.」 처럼 부호만 떨어졌다.
        #    PS1 은 엔진 훅(`patch_hang_punct`)으로 반각 꼬리 부호에 그 칸을 열었다 — 새턴도
        #    드로어 훅(`patch_msgwrap.hang_stub`)과 **한 몸**으로 연다. 하나만 켜면 되레 나빠진다.
        lim = limit + 1 if n == 1 and c in HANG_TAIL else limit
        if used >= lim:
            if retreat and cand >= 0:
                out[cand] = NL  # 규칙 1 — 마지막 공백에서 끊는다
                used -= cused + 1
                ls, cand = cand + 1, -1
            if used >= lim:  # 규칙 3 — 어절이 한 줄보다 길다
                if is_close(src, i) and last > ls:
                    # 규칙 3 보강(2026-09-27) — 「!!」·「!?」 같은 **연속** 반각 닫는 부호는
                    # `last`(바로 앞 한 자리)만 보면 부호끼리만 다음 줄에 남는다(고아 — 로그가
                    # 글자 단위로 접히면서 흔해졌다). `out[last]` 자신도 반각 닫는 부호면 **2B**
                    # 더 물러난다 — 이 게임 문안은 부호 앞이 실질적으로 늘 전각(한글) 한 글자라,
                    # 그 앞 글자까지 통째로 데려온다. ⚠ 기계어(`patch_msgwrap.close`)와 같은
                    # **정확히 2바이트 고정 폭** 휴리스틱이다 — 일반 글자폭 계산이 아니다.
                    anchor = last
                    if out[last] in CLOSE_HALF and last - 2 > ls:
                        anchor = last - 2
                        # ⚠ 자리 예산(기계어 556B) 때문에 anchor 가 공백인지는 **안 본다** —
                        # 실측(전 영역 921곳)에서 이 조합이 안 나온다(체크리스트 4-B: 커버리지
                        # 아니라 「지금 값으로 안 나온다」다). 새 문안이 이 조합을 만들면
                        # `check_wrap_rules` 의 줄머리 공백이 잡는다(2026-09-27).
                    out.insert(anchor, NL)  # 앞 글자(들)와 같이 내린다
                    ls = anchor + 1
                    used = len(out) - ls  # ⚠ 바이트 수 — 기계어와 같게(색 코드가 끼면 1B 보수적)
                else:
                    out.append(NL)
                    ls, used = len(out), 0
        out += src[i : i + n]
        last = len(out) - n
        used += n
        auto = False
        i += n
    return bytes(out)


def strip_ws(b):
    return bytes(x for x in b if x not in (NL, SP))


def check_invariant(src, got):
    """규칙 5 — 공백·개행을 뺀 글자가 입력과 같은가. (버퍼를 넘친 입력은 원래 잘린다 — 제외)"""
    src = bytes(src).split(b"\0", 1)[0]
    if len(src) >= STOP:
        return True
    return strip_ws(src) == strip_ws(got)


def lines(b):
    """나눈 결과의 줄들 (바이트)."""
    return bytes(b).split(bytes([NL]))


def width(line):
    """줄 폭(B) — 폭 없는 제어는 뺀다."""
    return sum(1 for x in line if x not in ZERO_W)


if __name__ == "__main__":
    s = sys.argv[1].encode("cp932", "replace")
    for ln in lines(wrap(s)):
        print(f"[{width(ln):2d}] {ln.decode('cp932', 'replace')}")
