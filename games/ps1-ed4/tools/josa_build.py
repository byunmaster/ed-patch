"""조사 병기 처리 — 빌드 쪽(판정부는 `shared/text/josa_rt.py`) + 훅에 줄 자료.

번역 문안엔 변수(아이템 이름·숫자) 뒤 조사를 병기(`을(를)` · `이(가)` · `은(는)`)로 쓴다. 빌드가 이걸
- **조각 첫머리**(= 변수 바로 뒤, 끼움 토막): 런타임 **표지 글자**(사설 영역)로 — 훅이 직전 글리프의 받침으로 실제 조사 글리프로 갈아 끼운다.
- **그 밖**(고정 글 뒤): 앞 글자 받침으로 지금 확정한다(못 정하면 병기 그대로 — 병기가 오판보다 안전하다).
`과(와)` · `(으)로` 표지는 대본에 한 번도 안 나와서(10-24 실측) 훅이 셋만 다룬다 — 나오면 여기서 멈춘다.
"""

from shared.text import josa_rt

N_MARK = 3  # 은/는 · 이/가 · 을/를
MARK_CHARS = [m[0] for m in josa_rt.MARKERS[:N_MARK]]
MARK_GLYPHS = "".join(c for m in josa_rt.MARKERS[:N_MARK] for c in (m[1], m[2]) if c)
EXTRA_CHARS = "".join(MARK_CHARS) + MARK_GLYPHS  # 정본 자리·굽기에 항상 넣는 글자


def _guard(s):
    for bad in (josa_rt.MARKERS[3][0], josa_rt.MARKERS[4][0]):
        if bad in s:
            raise SystemExit("🔴 과/와 · (으)로 표지가 쓰였다 — 훅이 이 둘을 안 다룬다")
    return s


def rigid(texts):
    """끼움 토막(조각마다 한 줄) — 조각 첫머리 병기는 표지로."""
    return [_guard(josa_rt.convert(t)) for t in texts]


def flex(texts):
    """합쳐 조판하는 쪽 — 모든 병기를 앞 글자 받침으로 확정한다(첫 조각 앞에 글이 없으면 병기 그대로)."""
    out, prefix = [], ""
    for t in texts:
        res, last = [], 0
        for m in josa_rt._TOKEN.finditer(t):
            res.append(t[last : m.start()])
            res.append(josa_rt.fix_in(prefix + t, len(prefix) + m.start(), m.group(0)))
            last = m.end()
        res.append(t[last:])
        s = "".join(res)
        out.append(s)
        prefix += s
    return out


def markers(table):
    """[(표지 코드, 받침 있을 때 코드, 없을 때 코드)] × 3 — 글리프 배정표에서. 없으면 KeyError."""
    return [(table[m[0]], table[m[1]], table[m[2]]) for m in josa_rt.MARKERS[:N_MARK]]


def batchim_bits(table, n_codes):
    """받침 비트표(코드마다 1비트 — 받침 있음/ㄹ 포함) — 훅의 `LAST` 판정용. 한글 음절 + 숫자(읽는 소리)만 1 이 선다."""
    bits = bytearray((n_codes + 7) // 8)
    for ch, code in table.items():
        if code >= n_codes:
            continue
        k = josa_rt.klass(ch)
        if k:
            bits[code >> 3] |= 1 << (code & 7)
    # 숫자 글리프는 원본 전각 숫자 코드 — 정본 표에 없으니 코드표에서 찾는다
    import hangul

    rev = hangul.reverse_charmap()
    for d, k in josa_rt.DIGIT_BATCHIM.items():
        if k:
            for ch in (d, chr(ord(d) - 0x30 + 0xFF10)):
                if ch in rev and rev[ch] < n_codes:
                    bits[rev[ch] >> 3] |= 1 << (rev[ch] & 7)
    return bytes(bits)
