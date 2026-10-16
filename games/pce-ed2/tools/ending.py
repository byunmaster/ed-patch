"""엔딩 스태프롤(패키지 41 = rel 5250) — 분야 라벨 · 엔딩 대사 번역과 한글 글리프 후킹.

엔딩 패키지는 **LZ 가 아닌 평문 스트림**(`0D 0A` 줄바꿈 · `09` 들여쓰기 · `/*` 쪽 넘김)을 BG 타일로 굴리는 자체 렌더러를 가진다(2026-10-13 실측):
  · 문자열 시작 = `JSR $7251; BIT $5C88`(인라인 포인터, 패키지 오프셋 0x14FF) — 스트림 = 오프셋 0x1C88 부터 0x2F23(0 채움)까지.
  · 글자는 `$72A4` 루프가 읽는다: `$E0↑ · $80~$9F` = 2바이트(`$F9`=리드 · `$F8`=트레일 → `$73FA` → `$749D` → BIOS `EX_GETFNT`(`JSR $E060`, 오프셋 0x34A1)),
    `$A0~$DF` = 반각 가나 1바이트, `$20~$7F` = ASCII, `<$20` = 제어. BIOS 가 `($FA)` 에 12×12(24B, 행당 2B)를 돌려준다.
  → 정본의 글리프 후킹(뱅크 0x6C `$60D2`)은 이 패키지의 직접 호출을 못 잡는다. 패키지 안에 **자체 후킹**을 둔다: `JSR $E060` 의 피연산자를 우리 루틴으로 바꾸고,
    리드 `F0` 이면 자체 글리프 표(24B 씩)에서 `($FA)` 로 복사, 아니면 `JMP $E060`.
  · 한글 라벨은 원문보다 길어 스트림을 **0xFF 패딩(오프셋 0x3FF4~)** 으로 옮긴다(BIT 피연산자 수정). 비운 원래 자리(0x1C88~)에 글리프 표, 0 채움(0x2F23~)에 후킹 루틴.
문안은 스태프롤 표(`LABELS` — 게임 폴더가 갖는다, 정본·후보 대상 아님: CLAUDE.md) · 이름(사람·회사·배역)은 원문 그대로(규칙 3-7).
"""

import hashlib
import json
import os
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import asm
import common
import font

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import canon

PKG_REL = 5250
U = common.USER
TEXT_OFF, TEXT_END = 0x1C88, 0x2840  # 🔴 스트림 끝은 0x2840 이다 — 그 뒤(0x2863~)는 대사가 아니라 **끝 장면(지구·위성) 팔레트·타일 자료**다. 예전엔 0x2F23 까지를 스트림으로 보고 글리프 표로 덮어 끝 장면이 붉게 변했다(원판은 정상, 마스터 10-15 유튜브 대조 — 자막 끈 기준 롬에서도 붉었던 건 이 패치 탓이었다)
BIT_OFF = 0x14FF  # `2C 88 5C` 의 피연산자
BIT_OLD = bytes([0x88, 0x5C])
NEW_TEXT_OFF = 0x4010  # 0xFF 패딩(0x3FF4~0x5E00) 안
HOOK_OFF = 0x2F23  # 0 채움(540B)
TABLE_OFF = TEXT_OFF  # 비운 원래 스트림 자리 — 글리프 표(24B × n)
SEAM_OFF = 0x34A2  # `JSR $E060` 의 피연산자
SEAM_OLD = bytes([0x60, 0xE0])
BIOS_GETFNT = 0xE060
LEAD = font.LEAD0
TRAIL0 = font.TRAIL0
BASE = 0x4000  # 패키지 오프셋 → 논리 주소(5개 뱅크가 `$4000~$DFFF` 에 이어 붙는다)

# 분야 라벨 · 배역 직함 — 원문(cp932 로 읽은 줄 본문) → 한국어. 이름(사람 · 회사 · 배역명)은 안 넣는다.
LABELS = {
    "スタッフ": "스태프",
    "制作･総指揮": "제작・총지휘",
    "ﾌﾟﾛｸﾞﾗﾑ": "프로그램",
    "ｵﾘｼﾞﾅﾙ ﾌﾟﾛｸﾞﾗﾑ": "오리지널 프로그램",
    "ｼｽﾃﾑﾌﾟﾛｸﾞﾗﾑ": "시스템 프로그램",
    "ﾊﾞﾄﾙﾌﾟﾛｸﾞﾗﾑ": "배틀 프로그램",
    "ｼﾅﾘｵﾌﾟﾛｸﾞﾗﾑ": "시나리오 프로그램",
    "ﾋﾞｼﾞｭｱﾙﾌﾟﾛｸﾞﾗﾑ": "비주얼 프로그램",
    "ｱｼｽﾄ": "어시스트",
    "ｻｳﾝﾄﾞ": "사운드",
    "作曲": "작곡",
    "編曲": "편곡",
    "録音ｽﾀｼﾞｵ": "녹음 스튜디오",
    "ﾐｷｼﾝｸﾞｴﾝｼﾞﾆｱ": "믹싱 엔지니어",
    "ｱｼｽﾀﾝﾄｴﾝｼﾞﾆｱ": "어시스턴트 엔지니어",
    "ｻｳﾝﾄﾞﾌﾟﾛﾃﾞｭｰｽ": "사운드 프로듀스",
    "ｻｳﾝﾄﾞﾌﾟﾛﾃﾞｭｰｻｰ": "사운드 프로듀서",
    "ｻｳﾝﾄﾞｴﾝｼﾞﾆｱ": "사운드 엔지니어",
    "ﾅﾚｰｼｮﾝ協力": "내레이션 협력",
    "ｹﾞｰﾑ･ｸﾞﾗﾌｨｯｸ": "게임 그래픽",
    "ｵﾘｼﾞﾅﾙ･ﾃﾞｻﾞｲﾝ": "오리지널 디자인",
    "ｸﾞﾗﾌｨｯｸ･ﾁｰﾌ": "그래픽 치프",
    "ﾏｯﾌﾟBG": "맵 BG",
    "ﾓﾝｽﾀｰ": "몬스터",
    "ﾏｯﾌﾟｷｬﾗ": "맵 캐릭터",
    "ﾋﾞｼﾞｭｱﾙ･ｸﾞﾗﾌｨｯｸ": "비주얼 그래픽",
    "絵ｺﾝﾃ": "콘티",
    "作画監督": "작화 감독",
    "原画": "원화",
    "ﾋﾞｼﾞｭｱﾙ･ﾃﾞﾓ": "비주얼 데모",
    "ｵﾘｼﾞﾅﾙ･ｼﾅﾘｵ": "오리지널 시나리오",
    "ｼﾅﾘｵ再構成": "시나리오 재구성",
    "声優出演": "성우 출연",
    "ﾅﾚｰｼｮﾝ": "내레이션",
    "村長": "촌장",
    "ｽﾍﾟｼｬﾙ･ｻﾝｸｽ": "스페셜 땡스",
    "ﾃﾞﾊﾞｯｸﾞ": "디버그",
    "制作進行": "제작 진행",
    "ﾃﾞｨﾚｸﾀｰ": "디렉터",
    "ｱﾄﾞﾊﾞｲｻﾞｰ": "어드바이저",
    "ﾌﾟﾛﾃﾞｭｰｻｰ": "프로듀서",
    "ｽｰﾊﾟｰﾊﾞｲｻﾞｰ": "슈퍼바이저",
    "ｴｸﾞｾﾞｸﾃｨﾌﾞﾌﾟﾛﾃﾞｭｰｻｰ": "이그제큐티브 프로듀서",
    "制作協力": "제작 협력",
    "制作・著作": "제작・저작",
    "ﾄﾞﾗｺﾞﾝｽﾚｲﾔｰ英雄伝説": "드래곤 슬레이어 영웅전설",
}
# 사람·회사 이름 — 원문 줄 본문 → 한글(외래어표기법, 마스터 10-16 규칙 3-7). 확신 「높음」만(`data/staff_names.json`). 영어로 된 것(J.D.K · CD-AUDIO …)은 그대로 둔다.
NAMES = json.loads((common.GAME_DIR / "data" / "staff_names.json").read_text(encoding="utf-8"))["names"]
# 엔딩 대사 두 줄 — 줄 번호(스트림 안 0 기준) → (원문 줄 sha1 앞 12자리, 한국어). 원문은 저작물이라 글로 안 적고 지문으로만 확인한다.
SENTENCES = {5: ("6cb1c062ad63", "작은 태양은 언젠가 아버지를 넘어"), 7: ("bdb9390c18cb", "커다란 태양으로 빛나리라.")}


# 앞 전각 공백 덜기(마스터 10-14 「두번째 줄이 너무 오른쪽으로 쏠렸는데」「첫번째줄도 조금 왼쪽」) — 첫 줄 x 28 → 16, 둘째 줄 100 → 64(줄 폭 152px, 계단 간격 유지).
INDENT_CUT = {5: 1, 7: 3}


# 스태프롤 화면 폭 모형(2026-10-14 실측 — 시험 롬 캡처): 줄 시작 x=124, `09` 16px · 전각 공백 `81 40` 12px · ASCII(공백 포함) 8px · 한글 12px.
# 화면 폭 256 이지만 오른쪽 끝 글자는 잘려 보이므로(마스터 10-14: 「프로듀ㅅ」) 줄 끝을 248px 안에 둔다.
X0, TAB_PX = 124, 16
# 줄 끝 한계 252(마스터 10-16): 시험 롬 실화면 — 끝 252 까지 글자가 온전히 그려지고(잉크 x249) 오른쪽 끝 열에 잔상이 없다. 글리프는 12px 인데 타일 8px 격자에서 시작 x 가 늘 0 또는 4(mod 8)라 안 잘린다.
# (10-14 「프로듀ㅅ」 잘림은 끝이 256 을 넘은 줄이었을 가능성 — 한계를 248 로 잡았던 근거)
LINE_LIMIT = 252
STAFF_SHIFT = 8  # 스태프롤 쪽 전체를 왼쪽으로 당기는 px(마스터 10-16 D안: 라벨 132 · 이름 148 — 이름이 라벨보다 +16 인 원판 규칙을 지키며 104px 이름도 끝 252 안).
# ⚠ 12px(C안: 라벨 128 · 이름 144)은 4px 앞 여백을 못 만들어 엔진 시작 열(BAT 열 15→14)을 당겨야 하는데, 그러면 열 14 의 그림 타일(왼쪽 틀의 오른쪽 세로 테두리 x116~122)이 글자 타일·칸 지우기에 덮여 **틀이 지워진다**(원판 대비 843~1372px/쪽, 시험 롬 실측). 앞 여백만으로 만드는 8px 이하만 쓴다.
FORCE_SPLIT = {"어시스턴트 엔지니어", "이그제큐티브 프로듀서"}  # 길이는 들어가지만 마스터가 두 줄을 원한 라벨(10-14 · 이그제큐티브 프로듀서는 10-16 — 한 줄이면 128px 가 라벨 열에서 왼쪽 그림 틀 바로 옆까지 와 닿는다)
LABEL_WORDS = {"女神": "여신"}  # 배역 직함 속 낱말(정본에 없다 — 관리자 후보)


def _pre_px(pre: bytes) -> int:
    px, i = 0, 0
    while i < len(pre):
        if pre[i] == 0x09:
            px += TAB_PX
        elif pre[i] == 0x20:
            px += 8
        elif pre[i] == 0x81 and pre[i + 1 : i + 2] == b"\x40":
            px += 12
            i += 1
        i += 1
    return px


def _vpx(pre: bytes) -> int:
    """당김(`STAFF_SHIFT`)을 뺀 앞 여백 px — 줄 시작 x = 124 + 이 값(화면 기준). 앞 여백이 0 인 줄은 그대로."""
    return max(0, _pre_px(pre) - STAFF_SHIFT)


def _compose(px: int) -> bytes:
    """앞 여백 px → 바이트(탭 16 · 공백 8 · 전각 공백 12 로 가장 적은 개수). 4 · 5~7 · 9~11 은 못 만든다 — 가장 가까운 윗값(8 · 12)으로."""
    best: dict[int, list[int]] = {0: []}
    for v in range(1, px + 9):
        c = [best[v - t] + [t] for t in (16, 12, 8) if v - t in best]
        if c:
            best[v] = min(c, key=lambda a: (len(a), -a.count(16)))
    if px not in best:
        px = next(v for v in range(px + 1, px + 9) if v in best)
    out = bytearray()
    for t in sorted(best[px], reverse=True):
        out += {16: b"\x09", 12: b"\x81\x40", 8: b"\x20"}[t]
    return bytes(out)


def _emit_pre(ctrl: bytes, vpx: int) -> bytes:
    """화면 기준 앞 여백 vpx → 스트림 바이트."""
    return ctrl + _compose(vpx)


# 반각 부호(마스터 10-16 「문장부호는 반각」) — 1바이트로 그려 8px. 괄호는 BIOS 영문 글꼴이 굵은 「[ ]」 모양이라 패키지 안 ASCII 글리프 표(`ASCII_TABLE`)의 `(` `)` 자리를 우리 글꼴 괄호로 바꿔 쓰고,
# 가운뎃점은 원판 반각 가나 점(`A5`, 가나 표의 이미 있는 글리프)을 쓴다.
HALF = {"（": 0x28, "）": 0x29, "・": 0xA5, "(": 0x28, ")": 0x29}
ASCII_TABLE = 0x3AC5  # 패키지 안 ASCII 글리프 표(문자 − 0x20 번째 16B, 위 12행이 글자) — 렌더러 `$7640`


def paren_glyphs() -> dict[int, bytes]:
    """우리 글꼴 괄호(3px)를 8px 칸 **안쪽 가장자리**로 민 글리프 — `(` 는 칸 오른쪽(열 4~6) · `)` 는 왼쪽(열 1~3). 글자 쪽으로 붙어 괄호 밖이 비지 않는다(pce-ed1 방식)."""
    out = {}
    for ch, shift in (("(", 4), (")", 1)):
        g = font.glyph(ch)
        rows = []
        for y in range(12):
            v = int.from_bytes(g[y * 2 : y * 2 + 2], "big") >> 8  # 왼쪽 8열
            rows.append((v >> shift) & 0xFF)
        out[ord(ch)] = bytes(rows) + bytes(4)
    return out


def _text_px(ko: str) -> int:
    """줄 폭(px) — 끝 괄호 `)` 의 오른쪽 빈 4px 는 잉크가 아니라서 뺀다(한계 판정은 잉크 끝 기준)."""
    w = sum(8 if ch in HALF else 12 if ord(ch) >= 0x80 else 8 for ch in ko)
    return w - 4 if ko.endswith(("）", ")")) else w


def _fit_pre(pre: bytes, w: int) -> bytes | None:
    """줄 끝이 한계를 넘으면 앞 공백을 줄인다(제어 바이트는 그대로, `09` → 모자란 만큼 `20`). 시작 x 124 에서도 못 들어가면 None."""
    avail = LINE_LIMIT - X0 - w
    v = _vpx(pre)
    ctrl = bytes(b for b in pre if b < 0x20 and b != 0x09)
    if v <= avail:
        return pre if not STAFF_SHIFT else _emit_pre(ctrl, v)
    if avail < 0:
        return None
    a = avail // TAB_PX
    b = (avail - a * TAB_PX) // 8
    return _emit_pre(ctrl, a * TAB_PX + b * 8)


def _name_indents(lines, replaced, sentences, x0=None):
    """쪽마다 이름 줄(원판 앞 여백 ≥ 32px = `09 09`)의 시작을 한 자리로 맞춘다 — 원판 규칙(라벨 +1 탭, 쪽 안 이름 시작 x 고정)을 되살린다.
    가장 긴 이름이 줄 끝 한계(LINE_LIMIT)를 넘으면 그 쪽의 이름 줄 전부를 같은 만큼 왼쪽으로(8px 단위) 당긴다. 상대 들여쓰기(사운드 팀 +8 · J.D.K +16)는 그대로.
    → ({줄 번호: 새 앞 여백 px}, {줄 번호: 그 쪽의 당김 px(≤0)})"""
    x0 = X0 if x0 is None else x0
    out, deltas = {}, {}
    page, members = [], []
    for i, l in enumerate(list(lines) + [b"/*"]):
        if i in replaced and i not in sentences:
            members.append(i)
            pre, ko, _suf = replaced[i]
            if _pre_px(pre) >= 32:
                page.append((i, _vpx(pre), _text_px(ko)))
        if l.startswith(b"/*"):
            delta = 0
            if page:
                slack = min(LINE_LIMIT - x0 - w - px for _i, px, w in page)
                delta = min(0, slack // 8 * 8)
                for j, px, _w in page:
                    out[j] = px + delta
            for j in members:
                deltas[j] = delta
            page, members = [], []
    return out, deltas


def _cast_name(key: str) -> str | None:
    """성우 출연의 배역 이름(반각 가나) → 정본 인명. 정본에 없는 낱말은 `LABEL_WORDS`."""
    n = unicodedata.normalize("NFKC", key.replace("\u3000", " "))
    for v in dict.fromkeys([n, n.replace("2", "２"), n.replace("大盗賊", "大盗賊 ")]):
        for cat in ("person", "place", "speaker", "ui", "monster"):
            r = canon.lookup(v, cat, "ed2")
            if r:
                return r
    for word, ko in LABEL_WORDS.items():
        if n.startswith(word):
            r = canon.lookup(n[len(word) :], "person", "ed2")
            if r:
                return f"{ko} {r}"
    return None


def _lines(stream: bytes):
    return stream.split(b"\r\n")


def _split_line(l: bytes):
    """줄 → (앞 제어·여백, 본문, 뒤 제어)."""
    i = 0
    while i < len(l):
        if l[i] < 0x20 or l[i] == 0x20:
            i += 1
        elif l[i] == 0x81 and i + 1 < len(l) and l[i + 1] == 0x40:
            i += 2
        else:
            break
    j = len(l)
    while j > i and l[j - 1] < 0x20:
        j -= 1
    return l[:i], l[i:j], l[j:]


def _enc(text: str, idx: dict[str, int]) -> bytes:
    out = bytearray()
    for ch in text:
        if ch == " ":
            out.append(0x20)
        elif ch in HALF:
            out.append(HALF[ch])
        elif ord(ch) < 0x80:
            out.append(ord(ch))
        else:
            out += bytes([LEAD, TRAIL0 + idx[ch]])
    return bytes(out)


def build(pkg: bytes) -> tuple[bytes, list[str]]:
    """원본 패키지 → (새 스트림 바이트, 쓰는 글자 목록). 이름 줄은 바이트 그대로."""
    stream = pkg[TEXT_OFF:TEXT_END]
    lines = _lines(stream)
    first_bin = next(i for i, l in enumerate(lines) if b"\x1a" in l)  # 이 줄부터는 제어 코드열 — 건드리지 않는다
    replaced: dict[int, tuple[bytes, str, bytes]] = {}
    keys = [_split_line(l)[1].decode("cp932", errors="replace") for l in lines[:first_bin]]
    cast_lo, cast_hi = keys.index("声優出演"), keys.index("ﾅﾚｰｼｮﾝ")
    for i, l in enumerate(lines[:first_bin]):
        pre, body, suf = _split_line(l)
        if i in SENTENCES:
            sha, ko = SENTENCES[i]
            assert hashlib.sha1(l).hexdigest()[:12] == sha, (i, hashlib.sha1(l).hexdigest()[:12])
            cut = INDENT_CUT.get(i, 0) * 2
            assert pre.count(b"\x81\x40") * 2 >= cut and pre[:cut] == b"\x81\x40" * (cut // 2) or not cut, pre
            pre = pre[cut:]
            replaced[i] = (pre, ko, suf)
            continue
        key = body.decode("cp932", errors="replace")
        if key in LABELS:
            replaced[i] = (pre, LABELS[key], suf)
        elif key in NAMES:
            if _pre_px(pre) == 24:  # 제작 협력 쪽 이름 다섯은 원판에서도 다른 쪽보다 8px 왼쪽(탭+공백)이었다 — 마스터 10-16 「마지막도 다른 페이지들보다 왼쪽」: 이름 열(탭 둘)로 맞춘다
                pre = bytes(b for b in pre if b < 0x20 and b != 0x09) + b"\x09\x09"
            # 이름 앞 제어코드 01 · 02 · 03(嶽·榊·澤 외자 글리프) · 05 06(「株」)는 원문 글자를 그리는 것이라 한글 줄에선 뗀다 — 남기면 한글 앞에 한자가 하나 더 찍힌다(시험 롬 실측)
            replaced[i] = (bytes(b for b in pre if b not in (1, 2, 3, 5, 6)), NAMES[key], suf)
        elif cast_lo < i < cast_hi and pre.startswith(b"\x09") and not pre.startswith(b"\x09\x09") and body:
            ko = _cast_name(key)  # 배역 이름은 번역한다(마스터 10-14) — 성우 이름(`09 09` 줄)은 원문 그대로
            if ko:
                replaced[i] = (pre, ko, suf)
    chars = sorted({ch for _p, ko, _s in replaced.values() for ch in ko if ord(ch) >= 0x80 and ch not in "・（）"})
    assert len(chars) <= 220, len(chars)
    idx = {ch: k for k, ch in enumerate(chars)}
    name_px, _page_delta = _name_indents(lines[:first_bin], replaced, SENTENCES)
    out: list[bytes | None] = []
    for i, l in enumerate(lines):
        if i not in replaced:
            if STAFF_SHIFT and i < first_bin:  # 한글로 안 바꾼 줄(CD-AUDIO · PSG · ADPCM · J.D.K)도 같은 만큼 당긴다 — 안 당기면 쪽 안 라벨 열이 어긋난다(마스터 10-16)
                _pre, _body, _suf = _split_line(l)
                if _body and not l.startswith(b"/*"):
                    l = _emit_pre(bytes(b for b in _pre if b < 0x20 and b != 0x09), _vpx(_pre)) + _body + _suf
            out.append(l)
            continue
        pre, ko, suf = replaced[i]
        if i in SENTENCES:  # 오프닝 대사 두 줄은 당기지 않는다(엔진 당김만 되돌린다)
            out.append(pre + _enc(ko, idx) + suf)
            continue
        if i in name_px and name_px[i] >= 0 and ko not in FORCE_SPLIT:
            ctrl = bytes(b for b in pre if b < 0x20 and b != 0x09)
            out.append(_emit_pre(ctrl, name_px[i]) + _enc(ko, idx) + suf)
            continue
        fit = _fit_pre(pre, _text_px(ko))
        if fit is not None and ko not in FORCE_SPLIT:
            out.append(fit + _enc(ko, idx) + suf)
            continue
        # 시작 x 124 에서도 넘는다(드래곤 슬레이어 영웅전설 148px) · 줄이 길어 끝이 잘린다 — 낱말 사이에서 두 줄로 나눈다(말은 줄이지 않는다, 3-6).
        # 위 빈 줄은 그대로 두고 아래 줄들이 한 줄씩 밀린다(마스터 10-14 「빈줄 없애지 말고 아래로 밀기」)
        words = ko.split(" ")
        cut = next(k for k in range(1, len(words)) if _text_px(" ".join(words[:k])) >= _text_px(ko) // 2 - 4)
        a, b = " ".join(words[:cut]), " ".join(words[cut:])
        fit = _fit_pre(pre, max(_text_px(a), _text_px(b)))
        assert fit is not None, ko
        out.append(fit + _enc(a, idx))
        out.append(fit + _enc(b, idx) + suf)
    return b"\r\n".join(x for x in out if x is not None), chars


def hook_code(table_addr: int, n_low: int, table2_adj: int) -> bytes:
    """글리프 번호 < n_low 는 `table_addr` 표, 이상은 `table2_adj`(= 둘째 표 주소 − 24 × n_low) 를 더한다."""
    a = asm.Asm(BASE + HOOK_OFF)
    a.op("LDA", "zp", 0xF9)
    a.op("CMP", "imm", LEAD)
    a.op("BNE", "rel", "orig")
    a.op("LDA", "zp", 0xF8)
    a.op("SEC")
    a.op("SBC", "imm", TRAIL0)
    a.op("TAX")  # X = 글리프 번호
    a.op("STA", "zp", 0xEC)
    a.op("STZ", "zp", 0xED)
    a.op("ASL", "zp", 0xEC)
    a.op("ROL", "zp", 0xED)  # 2k
    a.op("TXA")
    a.op("CLC")
    a.op("ADC", "zp", 0xEC)
    a.op("STA", "zp", 0xEC)
    a.op("BCC", "rel", "m3")
    a.op("INC", "zp", 0xED)  # 3k
    a.label("m3")
    for _ in range(3):
        a.op("ASL", "zp", 0xEC)
        a.op("ROL", "zp", 0xED)  # 24k
    a.op("CPX", "imm", n_low)
    a.op("BCS", "rel", "hi")
    a.op("CLC")
    a.op("LDA", "zp", 0xEC)
    a.op("ADC", "imm", table_addr & 0xFF)
    a.op("STA", "zp", 0xEC)
    a.op("LDA", "zp", 0xED)
    a.op("ADC", "imm", table_addr >> 8)
    a.op("STA", "zp", 0xED)
    a.op("BRA", "rel", "cpy")
    a.label("hi")
    a.op("CLC")
    a.op("LDA", "zp", 0xEC)
    a.op("ADC", "imm", table2_adj & 0xFF)
    a.op("STA", "zp", 0xEC)
    a.op("LDA", "zp", 0xED)
    a.op("ADC", "imm", (table2_adj >> 8) & 0xFF)
    a.op("STA", "zp", 0xED)
    a.label("cpy")
    a.op("LDY", "imm", 23)
    a.label("cp")
    a.op("LDA", "izpy", 0xEC)
    a.op("STA", "izpy", 0xFA)
    a.op("DEY")
    a.op("BPL", "rel", "cp")
    a.op("RTS")
    a.label("orig")
    a.op("JMP", "abs", BIOS_GETFNT)
    return a.bytes()


def writes(pkg: bytes):
    """[(선형 오프셋, 새 바이트, 기대 원본, 라벨)] — `pkg` = 원본 패키지 96,256B."""
    new_text, chars = build(pkg)
    new_text += bytes(0)
    table = b"".join(font.glyph(ch) for ch in chars)
    base = PKG_REL * U
    assert len(new_text) <= 0x5E00 - NEW_TEXT_OFF, len(new_text)
    n_low = (TEXT_END - TEXT_OFF) // 24  # 원래 스트림 자리에 들어가는 글리프 수 — 나머지는 새 스트림 뒤(0xFF 패딩)에 둔다
    table_lo, table_hi = table[: n_low * 24], table[n_low * 24 :]
    table2_off = NEW_TEXT_OFF + len(new_text)
    assert table2_off + len(table_hi) <= 0x5E00, (table2_off, len(table_hi))
    hook = hook_code(BASE + TABLE_OFF, n_low, (BASE + table2_off - 24 * n_low) & 0xFFFF)
    assert len(hook) <= 540, len(hook)
    new_bit = (BASE + NEW_TEXT_OFF).to_bytes(2, "little")
    seam = (BASE + HOOK_OFF).to_bytes(2, "little")
    out = [
        (base + NEW_TEXT_OFF, new_text, b"\xff" * len(new_text), "엔딩 스태프롤 새 스트림"),
        (base + BIT_OFF, new_bit, BIT_OLD, "엔딩 스트림 포인터"),
        (base + TABLE_OFF, table_lo, pkg[TABLE_OFF : TABLE_OFF + len(table_lo)], "엔딩 한글 글리프 표(앞)"),
        (base + table2_off, table_hi, b"\xff" * len(table_hi), "엔딩 한글 글리프 표(뒤)"),
        (base + HOOK_OFF, hook, bytes(len(hook)), "엔딩 글리프 후킹 루틴"),
        (base + SEAM_OFF, seam, SEAM_OLD, "엔딩 EX_GETFNT 이음매"),
    ]
    for code, gl in paren_glyphs().items():  # 반각 괄호 글리프(`(` `)`)
        o = ASCII_TABLE + (code - 0x20) * 16
        out.append((base + o, gl, pkg[o : o + 16], f"엔딩 반각 괄호 글리프 {chr(code)}"))
    return out, {"chars": len(chars), "text": len(new_text), "hook": len(hook)}


def apply(w) -> dict:
    if os.environ.get("ED_STAFF_OFF"):  # 시험용 — 스태프롤 패치를 빼 원판 동작과 대조한다(10-15 끝 장면 빨강 원인 가르기)
        print("  엔딩 스태프롤: ED_STAFF_OFF — 건너뜀")
        return {}
    pkg = common.track_data(PKG_REL, 47)
    spans, info = writes(pkg)
    for linear, new, expect, label in spans:
        w.put(linear, new, expect, label)
    print(f"  엔딩 스태프롤: 글자 {info['chars']} · 스트림 {info['text']}B · 후킹 {info['hook']}B")
    return info
