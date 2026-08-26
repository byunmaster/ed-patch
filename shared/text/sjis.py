"""SJIS ↔ JIS X 0208 좌표 — 「글리프 슬롯을 코드로 가리키는」 계산의 정본.

**둘째 소비자가 실재해서 올렸다** — 새턴 ED1+2(`11KANJI.FON`)와 새턴 ED3(`KANJI12.FON`)가
**같은 색인 규칙**을 쓴다: `(구−1)×94 + (점−1)`. 기하만 다르고(22B vs 18B) 이 층은 같다.

한글 삽입 수법이 이 계산 위에 선다 — **원본이 안 쓰는 글리프 슬롯을 덮어쓰고, 문안은 그
슬롯을 가리키는 SJIS 코드로 인코딩**한다. 그래서 「색인 → SJIS」가 정확해야 하는데,
🔴 **여기가 틀리면 화면에만 엉뚱한 글자가 나오고 빌드도 테스트도 통과한다.**
그래서 왕복(`문자 → 색인 → SJIS == 원래 바이트`)을 회귀로 못 박아 둔다.

⚠ **게임이 실제로 쓰는 계산과 맞는지는 게임마다 확인한다** — 표준을 따르는 게 보통이지만
아닌 구현이 있다(PS1 ED1+2 의 가나 블록이 커스텀 색인이었다). 게임 쪽에 검산기를 둔다.
"""

KANJI_KU = 16  # JIS 제1수준 한자가 시작하는 구
KU_LEN = 94  # 한 구의 점 수


def jis_index(ch):
    """문자 → 글리프 색인 `(구−1)×94 + (점−1)`. JIS 밖이면 `None`.

    EUC-JP 로 구/점을 얻는다 — JIS 와 같은 좌표계라 변환이 곧 조회다.
    """
    try:
        b = ch.encode("euc_jp")
    except UnicodeEncodeError:
        return None
    if len(b) != 2:
        return None
    return (b[0] - 0xA1) * KU_LEN + (b[1] - 0xA1)


def ku_ten(index):
    """색인 → `(구, 점)` (둘 다 1부터)."""
    ku, ten = divmod(index, KU_LEN)
    return ku + 1, ten + 1


def sjis_of_index(index):
    """글리프 색인 → 그 슬롯을 가리키는 SJIS 2바이트.

    ⚠ 둘째 구간의 선행 바이트는 **`0xE0`** 이다. 새턴 ED1+2 의 사본은 `0xC1` 로 적혀
    있었는데(반각 가나 범위라 SJIS 선행 바이트가 아니다), 그 게임이 구 47 위를 쓴 적이
    없어 **한 번도 안 터졌다.** 공용으로 올리며 전 구역 왕복을 걸었더니 1,386 슬롯이
    어긋나 바로 드러났다 — 사본을 그냥 옮겼으면 그대로 물려받았을 자리다.
    """
    ku, ten = ku_ten(index)
    c1 = 0x81 + (ku - 1) // 2 if ku <= 62 else 0xE0 + (ku - 63) // 2
    c2 = (ten + 0x3F + (1 if ten >= 64 else 0)) if ku % 2 else (ten + 0x9E)
    return bytes((c1, c2))


def kanji_start(ku=KANJI_KU):
    """한자 구역이 시작하는 색인 — 빈 슬롯을 고를 때의 하한.

    ⚠ 앞쪽 구(기호·가나·로마자)는 손대지 않는 게 안전하다. 시스템 문구·UI 가 그 자리를
    쓰는데 덤프에 안 잡힌 소재가 남아 있을 수 있고, 창 폭 계산이 그 코드를 반각으로
    보는 구현도 있다(새턴 ED1+2 에서 실제로 걸린 논점이다).
    """
    return (ku - 1) * KU_LEN


# ── 역방향: 바이트 → 사람이 읽는 문안 ────────────────────────────────────────
# 🔴 **이게 없어서 열다섯 번을 손으로 짰다**(2026-08-26, 새턴 ED1+2 전투 QA).
#    디버깅의 9할이 「이 바이트가 화면에 뭘로 나오나」인데, 슬롯 코드는 cp932 로 풀면
#    엉뚱한 한자가 나와서 **매번 인라인 디코더를 다시 썼다.** 인코더만 공용에 있고
#    디코더가 없던 게 이유다 — 짝을 맞춘다.
# ⚠ 게임의 슬롯 정본(`hangul_map*.json`)을 받아서 쓴다. 공용은 계산만 안다.


def by_code(table):
    """`{문자: 색인}` → `{SJIS 2바이트(int): 문자}`. 디코더가 쓰는 역인덱스."""
    return {int.from_bytes(sjis_of_index(i), "big"): ch for ch, i in table.items()}


def is_lead(b):
    """SJIS 2바이트 문자의 선행 바이트인가."""
    return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xEF


def decode(data, table=None, *, stop_at_nul=True, raw="<{:02x}>"):
    """바이트 → 문안. 우리 슬롯이면 그 글자, 아니면 cp932, 그것도 아니면 `raw` 로 찍는다.

    `table` 은 `{문자: 색인}`(게임 슬롯 정본) 또는 이미 뒤집힌 `{코드: 문자}` 둘 다 받는다.

    ⚠ **제어 바이트를 버리지 않는다** — `%c` 색코드가 1바이트로 들어앉는 자리가 있어,
      지우면 「왜 색이 갈리나」를 못 본다. `<01>` 처럼 그대로 보여 준다.
    ⚠ `stop_at_nul=False` 로 두면 종단 뒤까지 읽는다 — 「뒤에 뭐가 붙어 있나」를 볼 때 쓴다.
    """
    if table and isinstance(next(iter(table)), str):
        table = by_code(table)
    codes = table or {}
    out, i = [], 0
    while i < len(data):
        b = data[i]
        if b == 0:
            if stop_at_nul:
                break
            out.append(raw.format(b))
            i += 1
            continue
        if is_lead(b) and i + 1 < len(data):
            code = (b << 8) | data[i + 1]
            ch = codes.get(code)
            if ch is None:
                try:
                    ch = data[i : i + 2].decode("cp932")
                except UnicodeDecodeError:
                    ch = raw.format(b) + raw.format(data[i + 1])
            out.append(ch)
            i += 2
        else:
            out.append(chr(b) if 0x20 <= b < 0x7F else raw.format(b))
            i += 1
    return "".join(out)
