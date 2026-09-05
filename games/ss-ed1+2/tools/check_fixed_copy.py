"""**고정 길이 복사** 자리를 전수로 훑어, 우리 문안이 그 칸에 맞는지 본다.

    python3 tools/check_fixed_copy.py          # 빌드 이미지를 검사
    python3 tools/check_fixed_copy.py --list   # 자리 목록만 (원본 기준)

## 왜 필요한가 (2026-08-27, 「7격」에서 배웠다)

이 게임은 문자열을 `mov.b @r1+,r3 · add #1,r2 · mov.b r3,@r2` 언롤로 **정확히 N바이트**
퍼 나르는 자리가 많다(ED 9 · ED2 13). N 은 그 자리의 **원본 문자열에 딱 맞춰** 박혀 있다.

    회심  `会心の一撃!!\\n` 13B + NUL = 14B  → 복사 14B (종단까지 들어간다)
    이름  `セリオス`        8B  (NUL 없음)  → 복사 8B  (고정 폭 필드)

그래서 우리 문안이 **1바이트만 어긋나도** 조용히 깨진다:

- **길면** 뒤가 잘린다 — 회심은 NUL 이 잘려 **직전 메시지의 꼬리**가 화면에 이어졌다
  (유저 캡처의 「7격」 = `a7 88a5`).
- **짧으면** 남은 칸에 **옛 바이트가 그대로 남는다**.

🔴 **빌드도 되고 단위 테스트도 통과한다.** 인게임에서 그 상황(회심의 일격 등)을 만나야만
   보이고, 확률에 걸리면 QA 를 몇 바퀴 돌아도 안 나온다. 그래서 정적으로 잡는다.

## 어떻게 재나 — 정본 매핑 없이 **빌드 이미지에서 직접**

원본에서 자리(언롤 길이 · 소스 리터럴)를 찾고, **같은 리터럴을 빌드 이미지에서 다시 읽어**
그것이 가리키는 문자열을 잰다. 포인터가 재배치됐어도 따라간다 — 정본 표를 안 들어도 된다.

⚠ 우리가 **루프로 바꾼 자리**(`patch_crit_copy.py`)는 제약이 없어졌으므로 건너뛴다.
⚠ 소스 후보에 `%d` 같은 인자 문자열이 섞인다. 판정은 **원본과 우리 것의 길이 관계**로만
  하므로(원본이 그 칸에 어떻게 맞았는지를 기준으로 삼는다) 섞여도 오탐이 안 난다.
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import patch_crit_copy

LOAD_BASE = 0x06028000
FILES = ("/ED.BIN", "/ED2.BIN")
UNIT = bytes.fromhex("631472012230")  # mov.b @r1+,r3 · add #1,r2 · mov.b r3,@r2
TAIL = bytes.fromhex("611072012210")  # mov.b @r1,r1 · add #1,r2 · mov.b r1,@r2
MIN_RUN = 4  # 이보다 짧은 언롤은 문자열 복사로 보지 않는다
LOOKBACK = 0x30  # 소스 리터럴을 찾을 앞 범위
MAXLEN = 64  # 문자열 길이를 재는 상한


def _strlen(d, ram, cap=MAXLEN):
    """`ram` 이 가리키는 문자열의 내용 길이. 못 재면 None."""
    off = ram - LOAD_BASE
    if not (0 <= off < len(d) - 1):
        return None
    z = bytes(d[off : off + cap]).find(0)
    return None if z <= 0 else z


def sites(d):
    """`[(언롤 오프셋, 복사 길이, [(리터럴 주소, 소스 주소, 원본 길이)])]`."""
    out, i = [], 0
    while i < len(d) - 6:
        if bytes(d[i : i + 6]) != UNIT:
            i += 2
            continue
        n = 1
        while bytes(d[i + 6 * n : i + 6 * n + 6]) == UNIT:
            n += 1
        if n >= MIN_RUN:
            cap = 1 + n + (1 if bytes(d[i + 6 * n : i + 6 * n + 6]) == TAIL else 0)
            srcs = []
            for pc in range(max(0, i - LOOKBACK), i, 2):
                # ⚠ **`r1` 로 적재한 것만** 소스다 — 언롤이 `mov.b @r1+,r3` 로 읽는다.
                #   앞 범위의 pc 상대 로드를 전부 후보로 보면 남의 인자까지 딸려 와
                #   「원본 61B 인데 칸 5B」 같은 오탐이 난다(실측).
                w = (d[pc] << 8) | d[pc + 1]
                if (w & 0xFF00) != 0xD100:  # mov.l @(disp,pc),r1
                    continue
                lit = ((LOAD_BASE + pc + 4) & ~3) + (w & 0xFF) * 4
                if not (0 <= lit - LOAD_BASE < len(d) - 4):
                    continue
                v = struct.unpack(">I", bytes(d[lit - LOAD_BASE : lit - LOAD_BASE + 4]))[0]
                ln = _strlen(d, v)
                if ln is not None and ln <= cap:  # 칸보다 긴 원본은 그 자리의 소스가 아니다
                    srcs.append((lit, v, ln))
            if srcs:
                out.append((i, cap, srcs))
        i += 6 * n
    return out


def check(fname, orig, built, skip):
    """`([(리터럴, 원본길이, 우리길이, 복사길이, 왜)], [못 잰 리터럴]) — 어긋난 것만."""
    bad, unread = [], []
    for at, cap, srcs in sites(orig):
        if at in skip:
            continue
        for lit, _v, ln in srcs:
            off = lit - LOAD_BASE
            nv = struct.unpack(">I", bytes(built[off : off + 4]))[0]
            our = _strlen(built, nv)
            if our is None:
                # 🔴 **「못 쟀다」와 「볼 게 없다」를 가른다**(2026-09-04). 주소가 파일 밖이면
                #    문자열이 아니라 볼 게 없는 것이지만, `MAXLEN` 안에 NUL 이 없어서 못 쟀다면
                #    그건 **검사를 건너뛴 것**이다. 조용히 넘기면 초록불이 「없다」가 아니라
                #    「안 봤다」가 된다(체크리스트 4-B — 같은 꼴을 `scan_untranslated` 에서
                #    실제로 물렸다). 지금은 0건이라 실패로 안 치고 세어 보고만 한다.
                o2 = nv - LOAD_BASE
                if 0 <= o2 < len(built) - 1 and bytes(built[o2 : o2 + MAXLEN]).find(0) < 0:
                    unread.append(lit)
                continue
            # 🔴 기준은 **원본이 그 칸에 어떻게 맞았나**다.
            #    ⚠ 「우리 것이 짧다」는 결함이 아니다 — 짧으면 NUL 이 함께 복사돼 목적지가
            #      거기서 끊긴다. 오히려 안전하다. 처음엔 이걸 실패로 쳤다가 오탐 9곳을
            #      냈다(이름 여섯 · `ＥＰ` 셋). 늘 빨간불인 게이트는 아무도 안 본다.
            if ln + 1 <= cap:  # 원본이 NUL 까지 넣던 자리 — 우리도 넣어야 한다
                if our + 1 > cap:
                    bad.append((lit, ln, our, cap, "종단이 잘린다 — 직전 내용이 이어진다"))
            elif our > cap:  # 원본이 NUL 없이 꽉 채우던 고정 폭 필드
                bad.append((lit, ln, our, cap, "칸을 넘는다 — 뒤가 잘린다"))
    return bad, unread


def main():
    common.verify_source()
    listing = "--list" in sys.argv
    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    if not listing and not os.path.exists(dst):
        raise SystemExit(f"먼저 빌드한다 — {dst} 가 없다")
    _f, mm = (None, None) if listing else common.open_image(dst)
    files = {} if listing else {p: (lba, s) for p, lba, s in common.iso_files(mm)}

    total, fails = 0, 0
    for fname in FILES:
        orig = common.extract(fname)
        # 우리가 루프로 바꾼 자리는 제약이 없다 — 건너뛴다
        cat, _size = patch_crit_copy.find_copy(orig)
        skip = {at for at, _cap, _s in sites(orig) if cat <= at <= cat + 0x80}
        if listing:
            print(f"=== {fname} ===")
            for at, cap, srcs in sites(orig):
                mark = " (루프로 바꿈)" if at in skip else ""
                print(f"  0x{LOAD_BASE + at:08X} 복사 {cap}B{mark}")
                for _lit, v, ln in srcs:
                    kind = "NUL 포함" if ln + 1 == cap else ("고정 폭" if ln == cap else "-")
                    s = bytes(orig[v - LOAD_BASE :][:ln])
                    try:
                        txt = s.decode("cp932")
                    except UnicodeDecodeError:
                        txt = s.hex()
                    print(f"      0x{v:08X} {txt!r} {ln}B [{kind}]")
            continue
        n = len(sites(orig))
        total += n
        bad, unread = check(fname, orig, common.read_extent(mm, *files[fname]), skip)
        fails += len(bad)
        if unread:
            # ⚠ 「못 쟀다」는 실패가 아니라 **안 본 것**이다 — 조용히 넘기지 않는다
            print(f"  ⚠ {fname}: 길이를 못 잰 자리 {len(unread)}곳 (MAXLEN {MAXLEN}B 안에 NUL 이 없다)")
        if bad:
            print(f"  ❌ {fname}: 고정 복사 {len(bad)}곳이 어긋난다")
            for lit, ln, our, cap, why in bad:
                print(f"     0x{lit:08X}: 원본 {ln}B · 우리 {our}B · 칸 {cap}B — {why}")
        else:
            print(f"  ✅ {fname}: 고정 복사 {n}곳 — 전부 칸에 맞는다")
    if mm:
        mm.close()
        _f.close()
    if fails:
        raise SystemExit(f"고정 길이 복사 {fails}곳이 어긋난다 — 화면이 조용히 깨진다")


if __name__ == "__main__":
    main()
