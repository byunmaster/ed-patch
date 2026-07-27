"""
재삽입기: ED1 전 씬(SCN1~6)의 고신뢰 정렬 블록을 DOS 한국어로 교체한 이미지 빌드.

씬별로 (README '재삽입 전략' 그대로):
 1. 앵커(점프 테이블) 고정 재배치 — 앵커와 겹치는 블록 pinned, 사이만 대사 reflow
 2. 코드의 lui+addiu/ori 텍스트 포인터를 새 주소로 패치 (lo>=0x8000이면 hi+1 보정)
 3. 한글 폰트(ED.EXE) 탑재 + 섹터 재패킹/EDC 재계산 → 한 이미지에 6씬 + 폰트

안전장치:
 - PILOT_IDENTITY=1: 번역 0건으로 돌려 원본과 바이트 동일 확인 (기계 정확성 검증)
 - PILOT_FIXED=1: 블록별 원본 길이 고정(무이동), PILOT_SCN=ED1SCN3: 특정 씬만
 - 앵커/블록 중간 참조/크기 초과/인코딩 불가는 해당 블록 번역 제외 후 보고
 - 공유 lui의 hi 충돌 시 해당 블록 제외 후 재배치 (수렴까지 반복)

입력: out/scn_jp/EDxSCNn.json + out/align/EDx_SCNn.json + out/dos_kr/ED1/*.json
출력: work/Eiyuu Densetsu (KR Pilot).bin/.cue
"""

import bisect
import json
import os
import re
import shutil
import sys

import hangul_map
from common import (
    MIPS_ADDIU,
    MIPS_LW,
    MIPS_ORI,
    OUT_DIR,
    WORK_DIR,
    extract,
    iter_lui_pairs,
    write_cue,
    write_user_data,
)
from common import ORIG_BIN as SRC

# 공통 줄바꿈 유틸(레포 root의 shared/를 경로에 추가)
_REPO = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
sys.path.insert(0, os.path.join(_REPO, "shared"))
from text.krwrap import wrap_pages as kr_wrap_pages  # noqa: E402

ED_LBA, ED_SIZE = 257, 1021952  # ED.EXE (폰트 탑재 대상)
OVERLAY_RAM_BASE = 0x8016A000  # SCN 오버레이 로드 주소 (ED1 전 씬 공통, 참조 커버리지로 검증)
# ED1 씬별 (이름, LBA, size) — extract_scn.py SCN_FILES. text_end는 scn_jp JSON에서 씬별로.
SCN_FILES = [
    ("ED1SCN1", 1183, 206260),
    ("ED1SCN2", 1284, 217940),
    ("ED1SCN3", 1391, 199084),
    ("ED1SCN4", 1489, 134184),
    ("ED1SCN5", 1555, 171392),
    ("ED1SCN6", 1639, 100270),
]
MC = b"\x25\x63"  # %c
PS = b"\x25\x73"  # %s (런타임 이름 주입)
PD = b"\x25\x64"  # %d (런타임 수치 주입)
WRAP = 14.0  # 줄 폭 (슬롯 기준). 실측 확정(2026-07-19 스크린샷 2회): 14.0슬롯은 렌더,
# 14.5(반각 온점 포함)는 엔진이 부호만 다음 줄로 꺾음 → 한계 14.0. (07-09 "~14.5" 실측은
# 부호를 잉크 폭으로 오판한 것 — 폭은 슬롯 기준: 한글/전각=1, 공백·반각 부호=0.5)
LINES_PER_PAGE = 6  # 창당 줄 **하드 리밋**(2026-07-22 유저 실측): 6줄까지 정상 렌더,
# **7줄이면 글자가 대사창을 뚫고 나간다**. 절대 초과 금지 — 담을 곳이 없으면 창 수를
# 늘려(꼬리 잘림 감수) 넘기지, 한 창에 욱여넣지 않는다.

DST = os.path.join(WORK_DIR, "Eiyuu Densetsu (KR Pilot).bin")
DST_CUE = os.path.join(WORK_DIR, "Eiyuu Densetsu (KR Pilot).cue")

HANGUL = re.compile(r"[가-힣]")
# 인라인 \x09 = 정발의 **이름 주입 자리**(JP의 %s에 대응). 조판 파이프라인을 통과시키려고
# 센티널 1글자로 들고 다니다가 encode_ext에서 %s 바이트로 방출한다. 공백으로 지우면
# 이름이 사라지고("이름은 .") %s 개수가 줄어 씬이 정지한다(2026-07-23).
NAME_SENT = "\x1a"
NAME_SLOTS = 4.0  # %s 자리 폭 추정(세리오스=4) — 조판 폭 계산용


class SkipBlock(Exception):
    pass


# ── 한국어 → 게임 바이트 (hangul_map 확장: 구두점·숫자·라틴은 전각 SJIS) ────
def encode_ext(text):
    out = bytearray()
    for ch in text:
        if ch == NAME_SENT:  # 이름 주입 자리 → %s 방출
            out += PS
        elif ch == " ":
            out.append(0x20)
        elif ch in HALF_PUNCT or ch.isascii() and ch.isalnum():
            # 반각 부호·숫자·알파벳 — 1바이트 경로(0.5슬롯). JP 원본도 "400"·"Gold"를
            # 1바이트 ASCII로 저장·렌더(jp1172 실증 = 글리프 존재 보증, 유저 제안 07-26)
            out.append(ord(ch))
        elif ch == "\n":
            out.append(0x0A)
        elif ch in hangul_map.SYL_INDEX:
            out += hangul_map.syllable_sjis(ch).to_bytes(2, "big")
        else:
            if 0x21 <= ord(ch) <= 0x7E:  # ASCII → 전각
                ch = chr(ord(ch) + 0xFEE0)
            try:
                b = ch.encode("cp932")
            except UnicodeEncodeError:
                raise SkipBlock(f"인코딩 불가: {ch!r}") from None
            if len(b) != 2 or not 0x81 <= b[0] <= 0x84:
                raise SkipBlock(f"글리프 범위 밖: {ch!r}")
            out += b
    return bytes(out)


def jp_has_header(raw):
    """JP 블록이 화자 헤더(%c이름%c 0x0A)로 시작하는가 — 헤더 유무로 구조가 갈린다.
    ED1SCN1 실측: 헤더 O 514블록(%c 대개 3), 헤더 X 848블록(%c 대개 1, 내레이션류).
    헤더 없는 블록에 우리가 헤더를 붙이면 %c가 2개 초과 생산돼 꼬리 창이 잘린다."""
    if raw[:2] != MC:
        return False
    j = raw.find(MC, 2)
    return j > 0 and j + 2 < len(raw) and raw[j + 2] == 0x0A


def jp_header_is_fmt(raw):
    """JP 화자 헤더가 `%c%s%c`(런타임 이름 주입)인가 — 리터럴 이름 헤더와 구분.

    주인공은 플레이어가 이름을 정하므로 엔진이 %s로 주입한다. 우리가 리터럴("세리오스")로
    박으면 ①이름 설정이 무시되고 ②%s가 사라져 엔진 인자 소비가 어긋나 씬이 정지한다
    (2026-07-23 fmt_drop 실측: 대상 77블록 중 59가 이 케이스)."""
    if not jp_has_header(raw):
        return False
    j = raw.find(MC, 2)
    return PS in raw[2:j]


def jp_ctrl_runs(raw):
    """연속 %c 런(2개 이상)의 개수 — 화자 헤더·페이지/색 전환 같은 **제어 시퀀스** 표지."""
    n = i = 0
    while i < len(raw) - 3:
        if raw[i : i + 2] == MC and raw[i + 2 : i + 4] == MC:
            n += 1
            while i < len(raw) - 1 and raw[i : i + 2] == MC:
                i += 2
            continue
        i += 2 if raw[i : i + 2] == MC else 1
    return n


def jp_inline_fmt_windows(raw):
    """JP 블록에서 **인라인 화자 헤더가 `%c%s%c`(런타임 이름)인 창 번호** 집합.

    구조: 창 구분 `%c` 바로 뒤에 다시 `%c이름%c 0x0A`가 오면 그 창은 화자가 바뀐 창이다.
    주인공이 대답하는 창이 이 형태(`%s`)라, 빠뜨리면 화자 표시가 사라질 뿐 아니라
    %s 개수가 줄어 씬이 정지한다(SCN1 eid 17 = 성문 병사 ↔ 주인공 대답).
    리터럴 이름 인라인 헤더(14곳)는 이미 개수가 맞아 건드리지 않는다."""
    out, total = set(), 0
    if jp_has_header(raw):
        i = raw.find(MC, 2) + 3
    else:
        i = 0
    win = 0
    while True:
        k = raw.find(MC, i)
        if k < 0:
            break
        if raw[k + 2 : k + 4] == MC:  # %c%c → 인라인 헤더
            e = raw.find(MC, k + 4)
            if e > 0 and raw[e + 2 : e + 3] == b"\x0a":
                # 이 %c는 **앞 창을 닫고**, 뒤따르는 헤더는 **다음 창**의 것이다(off-by-one 주의).
                win += 1
                total += 1
                if PS in raw[k + 4 : e]:
                    out.add(win + 1)
                i = e + 3
                continue
        win += 1
        i = k + 2
    return total, out


def jp_windows(text):
    """JP 블록의 창 수 — ({c}화자{c})? 본문 {c} 반복 구조 파싱. 엔진은 창 수를
    원본 기준으로 고정하므로(계약, 07-19 실측) 병합 상한으로 쓴다."""
    toks = text.split("{c}")
    n, i = 0, 0
    if toks and toks[0] == "":
        i = 1
    while i < len(toks):
        seg = toks[i]
        if i + 1 < len(toks) and "{n}" not in seg and len(seg) <= 10 and seg.strip():
            i += 1  # 화자 헤더 스킵
            seg = toks[i]
        if seg.strip():
            n += 1
        i += 1
    return max(n, 1)


# ── 정발 줄바꿈 해소 ────────────────────────────────────────────────────────
# 정발(DOS) 대사의 {n}은 **DOS 화면 폭에 맞춘 표시용 줄바꿈**이지 문장 구조가 아니다.
# 그대로 존중하면 우리 폭(14슬롯)에서 고아 줄이 생기고, 이어붙이면 어절 중간 분리가
# 망가진다("말아주시옵"+"소서"). → 빌드 시 한 번 **공백/붙임으로 확정**하고 자유 재줄바꿈.
# 판정(전 코퍼스 7187곳 실측): 뒤 토큰이 단독으로 자주 등장=띄움(4805) vs 합친 형태가
# 코퍼스에 존재=붙임(214). **기본값 띄움**, 합친 형태가 어휘에 있으면 붙임.
_VOCAB = None
_TOK_STRIP = ".,!?\"'()「」…·"
# 어절 첫머리에 올 수 없는 어미·조사 조각 — 이걸로 시작하는 "단어"는 앞 어절의 꼬리다.
_ENDING_FRAGS = {
    "소서",
    "시옵소서",
    "니다",
    "습니다",
    "사옵니다",
    "나이다",
    "옵니다",
    "사옵나이다",
    "세요",
    "어요",
    "아요",
    "지요",
    "시오",
    "십시오",
    "이다",
    "였다",
    "겠다",
    "하다",
    "했다",
    "니까",
    "습니까",
    "사옵니까",
    "군요",
    "네요",
    "구나",
    "는데",
    "지만",
    # 확장(2026-07-22) — 단독 어휘와 겹치는 것(보다·하고·해서)은 오붙임 위험이라 제외
    "라네",
    "로세",
    "구려",
    "시게",
    "겠지",
    "았다",
    "었다",
    "리라",
    "으리라",
    "노라",
    "도다",
    "시고",
    "으시고",
    "라고",
    "라는",
    "이며",
    "이고",
    "이라",
    "잖아",
    "거야",
    "건가",
    "는가",
    "더구나",
    "더군요",
    "에서",
    "에게",
    "부터",
    "까지",
    "처럼",
    "으로",
}


def _dos_vocab():
    """DOS 한국어 전 코퍼스의 단독 토큰 집합(어절 사전) — {n} 붙임/띄움 판정용."""
    global _VOCAB
    if _VOCAB is None:
        _VOCAB = set()
        import glob

        for f in glob.glob(os.path.join(OUT_DIR, "dos_kr", "ED1", "*.json")):
            doc = json.load(open(f, encoding="utf-8"))
            entries = doc.get("entries", []) if isinstance(doc, dict) else doc
            for e in entries:
                if not isinstance(e, dict):
                    continue
                clean = re.sub(r"\{[^}]*\}|\\x[0-9A-F]{2}", " ", e.get("text", ""))
                for tok in clean.split():
                    tok = tok.strip(_TOK_STRIP)
                    if tok:
                        _VOCAB.add(tok)
    return _VOCAB


_BREAK_FIXES = None
_SPLIT_FIXES = None
_LINE_OVERRIDES = None


def _load_break_doc():
    global _BREAK_FIXES, _SPLIT_FIXES, _LINE_OVERRIDES
    if _BREAK_FIXES is None:
        path = os.path.join(os.path.dirname(OUT_DIR), "dos_break_fixes.json")
        try:
            doc = json.load(open(path, encoding="utf-8"))
        except FileNotFoundError:
            doc = {}
        _BREAK_FIXES = {tuple(p) for p in doc.get("join", [])}
        _SPLIT_FIXES = {tuple(p) for p in doc.get("split", [])}
        # JSON의 "\n"을 의도적 개행 마커(HARD_NL)로 — 일반 페이지 개행과 구분(protect_hard)
        _LINE_OVERRIDES = [(a, b.replace("\n", HARD_NL)) for a, b in doc.get("line_overrides", [])]


def _break_fixes():
    """사람이 확정한 어절 중간 분리 예외(dos_break_fixes.json) — 자동 판정 보정."""
    _load_break_doc()
    return _BREAK_FIXES


def _split_fixes():
    """vocab 오판으로 붙는 걸 강제로 띄우는 예외(지시관형사 '이' 등)."""
    _load_break_doc()
    return _SPLIT_FIXES


def _line_overrides():
    """특정 대사 개별 개행 교정(고유 구절 → HARD_NL 삽입). 문장 리플로우가 못 지운다."""
    _load_break_doc()
    return _LINE_OVERRIDES


def resolve_dos_breaks(t):
    """{n}을 공백 또는 붙임으로 확정한다(정발 표시 줄바꿈 제거).

    ⚠ 하드 개행(\\n) 보존 방식은 폐기(유저 결정 07-27): ①DOS는 자동 줄바꿈보다 더 자주
    끊고 개행 앞 잔여 공백까지 남아 블록마다 수십 바이트씩 커져 빠듯한 버퍼(SCN4/6 ~120B
    여유, SCN2 1블록 손실)를 초과했고 ②DOS는 조사·명사 경계 어디서나 끊어(왕자님|이) 정작
    원하는 배치도 안 나온다. → {n}은 공백으로 해소하고 엔진 자동 줄바꿈에 맡긴다. 눈에 띄는
    대사의 개행은 개별 override로 잡는다(전역 하드개행 금지)."""
    vocab = _dos_vocab()
    fixes = _break_fixes()
    splits = _split_fixes()
    parts = t.split("{n}")
    out = parts[0]
    for nxt in parts[1:]:
        pa, pb = out.split(), nxt.split()
        a = pa[-1].strip(_TOK_STRIP) if pa else ""
        b = pb[0].strip(_TOK_STRIP) if pb else ""
        # split 예외는 vocab보다 우선 — 합친 형태가 코퍼스에 있어도 강제로 띄운다
        # (지시관형사 '이'가 조사로 오판돼 "왕자님이"로 붙는 걸 "왕자님 이 비밀탈출구"로).
        # 그 외: 합친 형태가 어절 사전에 있거나, 뒤 조각이 어절 첫머리에 올 수 없는 어미면
        # 어절 중간 분리 → 붙임("말아주시옵"+"소서"). 나머지는 어절 경계 = 공백.
        join = (
            (a, b) not in splits
            and a
            and b
            and ((a + b) in vocab or b in _ENDING_FRAGS or (a, b) in fixes)
        )
        out += ("" if join else " ") + nxt
    for a, b in _line_overrides():  # 특정 대사 개별 개행 교정(고유 구절 → HARD_NL)
        out = out.replace(a, b)
    return out


def _kr_pages(t):
    """KR 텍스트의 실질 페이지 수(한글 있는 {p} 세그먼트)."""
    return sum(
        1 for seg in t.split("{p}") if HANGUL.search(re.sub(r"\{[^}]*\}|\\x[0-9A-F]{2}", "", seg))
    )


def splice_placeholder_pages(entry, table, kr_entry, target=None):
    """DOS 꼬리 `{p}\\x09{end}` = 다음 엔트리(화자 없는 연속 대사)를 주입하는 플레이스홀더.

    그 페이지를 다음 엔트리 본문으로 병합한다(연쇄 가능 — A_633은 3연쇄). 미처리 시
    한글 없는 페이지로 드랍돼 **인게임 빈 대사창**이 뜬다(성문 이벤트 T_000#8+#9 실측,
    2026-07-19). 인라인 \\x09(이름 주입 = JP %s 자리)는 별도 과제 — QA 메모 참조."""
    if os.environ.get("PILOT_NOSPLICE") == "1":
        return entry, []  # 진단(먹통 bisect): 분할 병합 비활성 — 병합이 소프트락 원인인지 격리
    t, eid = entry["text"], entry["entry_id"]
    consumed = []
    while target is None or _kr_pages(t) < target:  # 창 수 계약: JP 창 수까지만 병합
        try:
            nxt = kr_entry(table, eid + 1)
        except KeyError:
            break
        if t.endswith("\\x09{end}"):
            # 화자 없는 연속(주입 응답) — \x09 페이지를 다음 엔트리 본문으로 교체
            if nxt["text"].startswith("{spk}"):
                break
            t = t[: -len("\\x09{end}")] + nxt["text"]
        elif t.endswith("{p}"):
            # 꼬리가 빈 페이지 구분자 — 다음 엔트리가 다음 페이지(화자 교대 포함).
            # JP 1블록 : DOS N엔트리 분할(병사끼리 jp19 = #11+#12 실측 07-19)
            if not HANGUL.search(re.sub(r"\{[^}]*\}|\\x[0-9A-F]{2}", "", nxt["text"])):
                break  # 빈 몸통(#13류)은 병합하지 않음
            t = t + nxt["text"]
        else:
            break
        eid += 1
        consumed.append((table, eid))
    entry["text"] = t
    return entry, consumed


# ── DOS 블록 텍스트 → (화자, 페이지 목록) ───────────────────────────────────
# 맞춤법 정규화(07-26 유저 요청 "띄어쓰기·맞춤법 검수") — 정발 코퍼스의 관형형 붙여쓰기를
# 표준으로: ㄴ/ㄹ 받침 + 의존명사 것("죽인것"), 대명사+것("내것·네것·제것"), ㄹ 받침 +
# 수(있/없)("드릴수 있"), ㄹ 받침 + 때("왔을때"). 합성 대명사 "이것·그것·저것"은 제외(표준).
_JONG_N_L = (4, 8)  # ㄴ, ㄹ


def _jong(ch):
    return (ord(ch) - 0xAC00) % 28 if "가" <= ch <= "힣" else -1


def fix_spacing(t):
    t = re.sub(r"(?<![가-힣])([내네제])것", r"\1 것", t)  # 받침 없는 대명사(내것→내 것)
    t = re.sub(
        r"([가-힣])것",
        lambda m: m.group(1) + " 것" if _jong(m.group(1)) in _JONG_N_L else m.group(0),
        t,
    )
    t = re.sub(
        r"([가-힣])수(?=\s*(있|없))",
        lambda m: m.group(1) + " 수" if _jong(m.group(1)) == 8 else m.group(0),
        t,
    )
    # 때/때문/때까지 모두 표준은 선행 체언·관형형과 띄어쓰기 — ㄹ 받침 뒤만(보수적)
    t = re.sub(
        r"([가-힣])때", lambda m: m.group(1) + " 때" if _jong(m.group(1)) == 8 else m.group(0), t
    )
    return t


# ── 직함 띄어쓰기 등 맞춤법 교정(dos_spelling_fixes.json) ───────────────────────
# 정발 문맥·문안은 유지, 문법/맞춤법만 교정(유저 방침 07-27). 인명 뒤 직함은 띄운다
# (세리오스왕자 → 세리오스 왕자). 인명은 화자맵에서 자동 파생 → 지명/복합어 오탐 자동 배제
# (세금대신에=instead, 해적선장=역할명은 인명 아니라 손 안 댐).
_SPELL_RULES = None


def _spell_rules():
    """(직함결합 정규식, space쌍, replace쌍) 컴파일 — 이름은 화자맵에서 파생."""
    global _SPELL_RULES
    if _SPELL_RULES is None:
        path = os.path.join(os.path.dirname(OUT_DIR), "dos_spelling_fixes.json")
        try:
            doc = json.load(open(path, encoding="utf-8"))
        except FileNotFoundError:
            doc = {}
        titles = doc.get("titles", [])
        names = set(doc.get("names_extra", []))
        for v in _speaker_map().values():  # 화자맵 값에서 인명 파생
            toks = v.strip().split()
            if len(toks) >= 2 and toks[-1] in titles:  # "디나 공주" → 디나
                names.add(" ".join(toks[:-1]))
            elif len(toks) == 1 and re.fullmatch(r"[가-힣]+", v.strip()):
                names.add(v.strip())
        rx = None
        if names and titles:
            name_alt = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
            rx = re.compile(rf"({name_alt})({'|'.join(map(re.escape, titles))})")
        _SPELL_RULES = (rx, doc.get("space", []), doc.get("replace", []))
    return _SPELL_RULES


def spell_fix(t):
    rx, space, replace = _spell_rules()
    if rx:
        t = rx.sub(r"\1 \2", t)  # 인명+직함 → 띄움
    for a, b in space:  # 인명 사전으로 못 잡는 명시적 띄어쓰기(어딘가의왕자 등)
        t = t.replace(a + b, a + " " + b)
    for a, b in replace:  # 단순 오타/맞춤법 리터럴 치환
        t = t.replace(a, b)
    return t


def parse_kr(entry):
    t = entry["text"]
    # 표기 통일: 정발 코퍼스의 '엘아스터'(소수 표기)는 전 대사 '엘아스타'로
    # (JP 원음·ED2 정발·오프닝 근거, 유저 확정 07-13 — 지명 트랙과 동일 판정. 07-26 전수 적용)
    t = t.replace("엘아스터", "엘아스타")
    # 'クルスの村' 직역 '크루즈의 마을'은 정발 내부에서도 '크루즈 마을'이 지배적(유저 지적 07-26)
    t = t.replace("크루즈의 마을", "크루즈 마을")
    # 선두 화자 마크업(+선행 opcode 노이즈) 제거. ⚠ `^.*?{/spk}`(구현 1기)는 본문 어디든
    # 처음 나오는 {/spk}까지 삼킨다 — 화자 없는 1페이지 뒤에 화자 페이지가 이어지면
    # 1페이지가 통째로 증발한다("고마와. 퍼거슨" 소실, eid 23 화자창 오배정의 진짜 원인).
    # 선두가 {spk}이거나, {/spk} 앞에 본문({n}/{p}/한글)이 없을 때만 잘라낸다.
    if t.startswith("{spk}"):
        t = re.sub(r"^\{spk\}.*?\{/spk\}", "", t, count=1)
    else:
        m = re.search(r"\{/spk\}", t)
        if m and not re.search(r"\{[np]\}|[가-힣]", t[: m.start()]):
            t = t[m.end() :]
    t = resolve_dos_breaks(t).replace("{end}", "")  # 정발 표시 줄바꿈 해소(위 주석)
    # 맞춤법/띄어쓰기 교정은 {n} 해소 **뒤**에 — 어절이 {n} 경계에 걸린 경우("드릴수{n}있"의
    # 릴수→릴 수)도 잡으려면 개행이 공백/붙임으로 확정된 후여야 한다(유저 지적 07-27).
    t = fix_spacing(t)
    t = spell_fix(t)  # 직함 띄어쓰기 등 맞춤법 교정(dos_spelling_fixes.json)
    # 상점 인사·흐름의 분기 마커(\x07=도구점, {p}\x06=무기점) 뒤 come-again 꼬리 제거 — PS1은
    # come-again이 별도 블록이라 인사 인라인 노출은 잘못(도구점·무기점 모두, 유저 QA 07-27).
    # 마커가 있어야 매칭 → 마커 없는 별도 come-again 블록("또 들러 주십시요")은 보존.
    t = re.sub(r"(?:\{p\})?\\x0[67]또 ?[들와찾][^\\{]*?주십[시쇼][요오]?\.?", "", t)
    # \xNN 제어코드(프롬프트 대기 등)는 공백으로 — 무공백 제거 시 앞뒤 발화가 붙음
    # ("합니다\x07또 들러주십시요"). ⚠ \x03 두 곳은 인라인 플레이스홀더 의심(QA 메모).
    t = t.replace("\\x09", NAME_SENT)  # 이름 주입 자리 보존(아래 일괄 치환보다 먼저)
    t = re.sub(r"\\x[0-9A-F]{2}", " ", t)
    # 병합으로 들어온 인라인 화자({spk}X{/spk})는 페이지 헤더로 보존 — JP의 %c화자%c 재현
    t = re.sub(r"\{spk\}(.*?)\{/spk\}", "\x11\\1\x12", t)
    # 짝 안 맞는 고아 {spk}/{/spk}(DOS 추출기 마크업 잔여, ED1 122블록)는 제거 —
    # 안 지우면 "을 장비하였습니다.{/spk}"처럼 태그가 화면에 글자로 새어나온다(T_001 아이템 장비 실측).
    t = t.replace("{spk}", " ").replace("{/spk}", " ")
    # 종결부호 앞 공백·개행 일괄 제거(유저 승인 2026-07-24): 정발 "어서 !!"식 공백은
    # 14슬롯 폭에서 느낌표만 다음 줄로 넘어가는 고아를 만든다 — 부호를 앞말에 붙인다.
    t = re.sub(r"[ \n]+(?=[!?])", "", t)
    pages = []
    for seg in t.split("{p}"):
        inline_spk = None
        m = re.match(r"\s*\x11([^\x12]*)\x12", seg)
        if m:
            inline_spk = m.group(1).strip() or None
            seg = seg[m.end() :]
        seg = seg.replace("\x11", " ").replace("\x12", " ")
        seg = re.sub(r"[^\S\n]+", " ", seg).strip()  # 개행 외 공백만 정리(줄바꿈 유지)
        m = HANGUL.search(seg)
        if not m:
            continue
        # 선두 opcode 잔여 노이즈 절삭 — 단 숫자·부호는 본문이다("10년전"의 10, 이름 창
        # 뒤에 오는 ". 왕자"의 온점이 잘려나간 실측 07-26). 선두 NAME_SENT는 기존대로
        # 잘라낸다(%s 헤더 블록의 이름자리 중복 — 남기면 %s 초과 방출 = 인자 소비 어긋남).
        if m.start() < 4 and not re.fullmatch(r"[0-9 .,!?]*", seg[: m.start()]):
            seg = seg[m.start() :]
        pages.append((inline_spk, seg))
    if not pages:
        raise SkipBlock("본문 없음")
    return entry["speaker"], pages


# 반각(1바이트) 부호(2026-07-19 인게임 확정): .,!?는 공백과 같은 1바이트 경로로 내보내
# 0.5슬롯 렌더 — 대사 렌더러의 1바이트 글리프 지원 스크린샷 검증. 이에 따라 전각 잉크
# 여백이 사라져 "부호 뒤 공백 제거" 조판 규칙은 폐지(공백 유지가 자연스러움 — 유저 판정).
# ()는 07-26 추가 — 전각 （）의 내부 여백이 "이 (가)"처럼 벌어져 보임(유저 QA, 인게임 검증 대기).
HALF_PUNCT = ".,!?()"


def cell_w(ch):
    """엔진 슬롯 폭 — encode_ext와 1:1 (1바이트=0.5, 2바이트 전각=1)."""
    if ch == NAME_SENT:
        return NAME_SLOTS  # %s는 런타임 이름 — 평균 길이로 근사
    return 0.5 if ch == " " or ch in HALF_PUNCT or (ch.isascii() and ch.isalnum()) else 1.0


# 의도적 개행 마커 — line_overrides가 삽입한다. 일반 페이지 경계 개행(\n)과 구분해
# 이 마커가 있는 창에서만 protect_hard를 켜(문장 리플로우가 override를 지우지 못하게).
# PUA 문자 사용(제어문자 \x1c~\x1f는 Python regex \s에 걸려 공백 정리 때 사라진다).
HARD_NL = "\ue000"


def wrap_page(text, width=WRAP, target=None, max_lines=None):
    """공통 줄바꿈 유틸(shared/text/krwrap.wrap_pages): 원문 {n} 줄바꿈을 존중하고
    폭(WRAP) 넘는 줄만 재줄바꿈 + 금칙 + 짧은조각 병합, 창(3줄)은 문장 그룹 단위로
    packing해 문장이 창 경계에 반반 걸리지 않게 한다(3줄 초과 문장만 재줄바꿈).
    부호 정리(07-19 갱신): 부호 앞 공백만 제거, 뒤 공백은 유지 — 반각 부호 전환으로
    "온점·쉼표 뒤 공백 제거" 규칙 폐지. 줄바꿈 v2 + 반각 부호 인게임 검증 완료.
    HARD_NL 마커가 있으면 하드개행으로 변환하고 protect_hard를 켠다(개별 개행 override)."""
    protect = HARD_NL in text
    text = text.replace(HARD_NL, "\n")
    return kr_wrap_pages(
        text,
        width,
        max_lines or LINES_PER_PAGE,
        target_pages=target,  # 창 수 계약: 지정 시 정확히 target개 창으로 분배
        break_char="\n",
        cell_width=cell_w,
        strip_before=".,!?",
        strip_after="",  # 부호 뒤 공백 유지 — 반각 부호 전환으로 공백 제거 규칙 폐지(07-19, 유저 판정)
        protect_hard=protect,
        det_orphan=True,  # 줄 끝 홀로 남은 지시관형사(이/그/저)를 다음 줄 명사로 내림(재배치, 바이트 불변)
    )


# ── 원본 템플릿 채우기 ──────────────────────────────────────────────────────
# 재설계(2026-07-23): 정발 문장을 우리 마음대로 N조각으로 쪼개고 제어코드를 재배치하는 대신,
# **JP 블록의 제어 골격을 그대로 두고 본문 창 자리에만 정발 문장을 채운다.**
# %c는 창 구분자가 아니라 색상 등 **제어 인자를 소비하는 escape**라(데미지 sprintf 인자가
# (2, 이름, 1)인 것으로 확증), 위치를 옮기면 색이 문장 중간에서 바뀌고 공백이 사라진다.
def parse_template(raw):
    """JP 블록 → 토큰열. ('c',)/('s',)/('d',)=제어, ('nl',)=개행, ('t',bytes)=텍스트."""
    out, i, buf = [], 0, bytearray()

    def flush():
        if buf:
            out.append(("t", bytes(buf)))
            buf.clear()

    while i < len(raw):
        two = raw[i : i + 2]
        if two == MC:
            flush()
            out.append(("c",))
            i += 2
            continue
        if two == PS:
            flush()
            out.append(("s",))
            i += 2
            continue
        if two == PD:
            flush()
            out.append(("d",))
            i += 2
            continue
        if raw[i] == 0x0A:
            flush()
            out.append(("nl",))
            i += 1
            continue
        if raw[i] == 0x00:
            i += 1
            continue  # 꼬리 4바이트 정렬 패딩
        # ⚠ SJIS 2바이트 선두는 0x81~0x9F / 0xE0~0xEF 뿐이다. 0xA1~0xDF는 **반각 가타카나
        # 1바이트**라, 0x81~0xEF로 뭉뚱그리면 `･`(0xA5) 등에서 파싱이 밀려 뒤의 %c를 삼킨다.
        lead = 0x81 <= raw[i] <= 0x9F or 0xE0 <= raw[i] <= 0xEF
        n = 2 if (lead and i + 1 < len(raw)) else 1
        buf += raw[i : i + n]
        i += n
    flush()
    return out


def template_windows(tpl):
    """`%c`를 경계로 창 분할 → [(kind, tokens)]. kind = name|body|empty.

    **이름 창 판정**: 창 안에 텍스트(또는 %s) 하나뿐이고 개행이 없으며 **다음 창이 nl로 시작**.
    이 판정을 빼면 여러 줄을 각각 창으로 세어버린다(1차 프로토타입 실패 원인)."""
    segs, cur = [], []
    for tok in tpl:
        if tok[0] == "c":
            segs.append(cur)
            cur = []
        else:
            cur.append(tok)
    segs.append(cur)
    out = []
    for k, seg in enumerate(segs):
        payload = [t for t in seg if t[0] in ("t", "s", "d")]
        if not payload:
            out.append(("empty", seg))
            continue
        nxt = segs[k + 1] if k + 1 < len(segs) else []
        is_name = (
            len(payload) == 1
            and payload[0][0] in ("t", "s")
            and not any(t[0] == "nl" for t in seg)
            and nxt
            and nxt[0][0] == "nl"
        )
        out.append(("name" if is_name else "body", seg))
    return out


def _tpl_name(jp_bytes, speaker, first):
    """템플릿 이름창의 KR 이름 바이트. 화자맵(JP 이름→정발명) 우선 — 다중 화자 블록에서
    두 번째 화자를 정렬 화자로 덮어쓰면 오표기가 되므로, 정렬 화자 폴백은 **첫 이름창만**."""
    try:
        kr = _speaker_map().get(jp_bytes.decode("cp932"))
    except UnicodeDecodeError:
        kr = None
    if kr:
        return encode_ext(kr)
    if first and speaker:
        return encode_ext(speaker)
    raise SkipBlock("이름창 화자 미해결")


# ── 글자 주입 %c쌍 (0x5C 이스케이프) ───────────────────────────────────────
# 팔콤 툴체인은 둘째 바이트가 0x5C('\')인 SJIS 글자(ソ 등)를 문자열에 못 쓰고 `%c%c`+
# 인자(0x83, 0x5C)로 주입한다 — eid 20 콜사이트 디스어셈블로 실증(sprintf 0x800CC740,
# 인자열 2·이름·1·0x83·0x5C·8·2·0x83·0x5C·1·8·8·2·이름·1·6). 즉 **%c 하나 = 인자 1바이트를
# 버퍼에 주입**이고, 창 전환·색도 제어 바이트(1~14) 주입으로 구현된다. 번역 절차:
#  ① 오버라이드 `inject_pairs: [[raw오프셋, 주입바이트hex], …]` — 쌍을 주입 글자로 치환한
#     정본 JP로 템플릿을 만들고(이름 ファーガソン 완성 → 화자맵 적용), 쌍 %c%c는 해당 창
#     꼬리에 되돌려 인자 소비를 보존한다(같은 전이 구간 안 이동이라 인자 순서 불변).
#  ② SCN_ARG_PATCHES — 콜사이트 즉치(0x83/0x5C)를 0x20(공백)으로 바꿔 꼬리 %c%c가
#     공백 2개(비가시)를 그리게 한다. **해당 블록이 실제 번역될 때만 적용**(JP 유지 시 원본).
INJECT_PAIRS = {}  # eid → [(off, bytes)] — load_translations가 씬마다 재구축
SCN_ARG_PATCHES = {
    # eid 20 개구멍 Q&A: li t2,0x83 / li t0,0x5C → 0x20 (RAM 0x8017D920/24)
    ("ED1SCN1", 20): [(0x13920, 0x240A0020), (0x13924, 0x24080020)],
}

# ── 이름 헤더 스텁 — 원판이 이름 없이 띄우는 콜사이트에 헤더 사본을 물린다 ──
# jp1169 실측(HANDOFF 07-26 밤 4): 이벤트에 두 진입점이 있고 변형 B(1169 단독)는 인자를
# 8 하나만 공급해 이름 헤더를 붙일 수 없다. 해법: 진입점 2워드를 `j 스텁`으로 바꾸고,
# 확장 영역의 스텁이 변형 A와 동일한 인자열(2·이름ptr·1·8)을 만들어 **헤더 붙은 사본
# 블록**(역시 확장 영역)으로 sprintf를 호출한 뒤 flush 시퀀스로 복귀한다. 인자를 스텁이
# 직접 공급하므로 구조 계약이 자기완결 — 변형 A가 이 진입점을 통과해도 안전하다.
# ⚠ resume·call_off는 원본 콜사이트 좌표(불변). 이름 소스는 변형 A가 쓰는 런타임 버퍼.
NAME_STUBS = {
    ("ED1SCN1", 1169): {
        "call_off": 0x2A398,  # 변형 B 진입점(move a0,s0 / lui a1) → j stub / nop
        "resume": 0x801943AC,  # flush 시퀀스(addiu a0,sp,0x20 …)로 복귀
        "name_ptr": 0x801157AC,  # %s 인자 — 변형 A와 동일한 이름 버퍼
        "sprintf": 0x800CC740,
    },
}


def strip_inject_pairs(raw, pairs):
    """주입 `%c%c` 쌍을 실제 글자로 치환한 정본 JP와, 쌍을 되돌릴 창 번호 목록을 반환."""
    tails, out, shift = [], raw, 0
    for off, byts in sorted(pairs):
        pos = off - shift
        assert out[pos : pos + 4] == MC + MC, f"inject_pairs 오프셋 불일치 @{off:#x}"
        tails.append(out[:pos].count(MC))
        out = out[:pos] + byts + out[pos + 4 :]
        shift += 4 - len(byts)
    return out, tails


def reinsert_pairs(blk, tails):
    """치환했던 `%c%c` 쌍을 재조립본의 같은 창 꼬리에 복원 — 인자 소비·%c 총수 보존."""
    segs = blk.split(MC)
    for w in tails:
        segs[w] = segs[w] + MC + MC
    return MC.join(segs)


# ── 정형(定型) 시스템 블록 — 보물상자 열기·재조사 ──────────────────────────
# 같은 JP 사본이 전 씬에 다수(열기 26 + 재조사 3)라 정렬 대신 **JP 원문 매칭**으로 일괄
# 번역한다. 문장은 정발 C_00B#0(열기+재조사 결합 엔트리)에서 파생 — 코드 임베드 금지.
# 아이템명 %s의 조사는 동적 주입이라 병기 "이(가)"(전투 메시지와 같은 계열).
# 제외: 선두에 포인터 테이블이 섞인 사본(이동·재작성 불가)과 不思議な 변형(3장, A_624 계열)
# — stock_kind가 %s 시작 + 정확 구조(%c 2개)만 잡아 자연히 걸러진다.
STOCK = "__stock__"  # translations 마커 — 핀·제외·통계를 기존 경로에 태우기 위해 등록
STOCK_KINDS = {}  # {eid: kind} — 씬 단위(load_translations가 재구축). 포인터 dedup용.
# 침묵 블록(본문이 ・・・ 뿐)은 본문을 JP 통과시키되 **이름창만 번역**한다 — 그냥 두면
# 화자명까지 セリオス로 남는다(유저 QA 07-26). 템플릿에 빈 페이지를 넘겨 골격+이름만 재조립.
NAMEONLY = "__nameonly__"
_CHEST = None


def _chest_texts():
    """C_00B#0 → (열기 전반부, 열기 후반부, 재조사 1창, 재조사 2창) — DOS 파생 캐시."""
    global _CHEST
    if _CHEST is None:
        doc = json.load(
            open(os.path.join(OUT_DIR, "dos_kr", "ED1", "C_00B.json"), encoding="utf-8")
        )
        t = next(e for e in doc["entries"] if e["entry_id"] == 0)["text"].removesuffix("{end}")
        opn, _, re_ = t.partition("\\x07")  # \x07 = 열기/재조사 경계(프롬프트 대기)
        a, _, b2 = opn.partition("\\x06\\x0E`3")  # \x0E`3 = 아이템명+조사 주입 자리
        re1, _, re2 = re_.partition("{p}")
        re1 = re1.replace("\\x0B`2", "").strip()  # \x0B`2 = 이름 주입 자리(우리는 %s 방출)
        _CHEST = (
            a.replace("{n}", "\n").strip(),
            b2.strip(),
            re1.replace("{n}", "\n"),
            re2.strip(),
        )
    return _CHEST


_SJIS_OPEN = "宝箱を開けました".encode("cp932")
_SJIS_OPEN_END = "が入っていました。".encode("cp932")
_SJIS_RECHECK = "もう一度調べてみました".encode("cp932")
_SJIS_FUSHIGI = "不思議な".encode("cp932")  # 신비한 보물상자 변형(3장) — 문안이 달라 제외


def stock_kind(raw):
    t = raw.rstrip(b"\x00")
    if not t.startswith(PS) or t.count(MC) != 2 or t.count(PD) or _SJIS_FUSHIGI in t:
        return None
    if _SJIS_OPEN in t and t.endswith(_SJIS_OPEN_END) and t.count(PS) == 2:
        return "open"
    if _SJIS_RECHECK in t and t.endswith(MC) and t.count(PS) == 1:
        return "recheck"
    return None


def stock_build(raw):
    """정형 블록 KR 재조립(구조 = 원본과 동일한 %c/%s 순서). 아니면 None."""
    kind = stock_kind(raw)
    if kind is None:
        return None
    a, b2, re1, re2 = _chest_texts()
    if kind == "open":
        # [%s]는 …열었습니다.\n…안에는\n [%c][%s][%c]이(가)\n들어 있었습니다.
        first, _, rest = a.partition("\n")
        head = "\n".join(wrap_page(NAME_SENT + "는 " + first)[0])
        return encode_ext(head + "\n" + rest + "\n") + MC + PS + MC + encode_ext("이(가)\n" + b2)
    # recheck: [%s]는 상자를 다시 한번\n살펴 보았습니다.[%c]역시…[%c]
    p1 = "\n".join(wrap_page(NAME_SENT + "는 " + re1)[0])
    p2 = "\n".join(wrap_page(re2)[0])
    return encode_ext(p1) + MC + encode_ext(p2) + MC


# ── 상점 가격 확인 프롬프트(정형) ────────────────────────────────────────────
# `{c}%s{c}は{n}%d Gold になるけど{n}それでも よろしいですか？{n}{c}` — %d가 본문 창
# 인라인이라 build_from_template 채우기로는 %d가 유실된다. STOCK처럼 %c/%s/%d 순서를 그대로
# 재현하는 전용 빌더로 KR을 심는다(은(는)은 조사 훅이 아이템명 받침 보고 교정).
SHOP_PRICE = "__shop_price__"
_SJIS_NARU = "になるけど".encode("cp932")


def is_shop_price(raw):
    t = raw.rstrip(b"\x00")
    return PS in t and PD in t and b"Gold" in t and _SJIS_NARU in t and t.count(MC) == 3


def shop_price_build(raw):
    """상점 가격 프롬프트 KR 재조립(%c/%s/%d 순서 = 원본).

    조사 훅은 대사 렌더러(0x800B2054)만 걸려 상점 프롬프트엔 안 탄다(유저 QA 07-27
    "해독초은 (는)" 병기 노출). %s(아이템명)는 런타임 주입이라 받침을 알 수 없어 은(는)을
    정적 확정할 수 없다 → 조사를 **고정 단어 '값은'**에 붙여 자연스러움을 살린다(받침 있는
    '값'에 은 고정이라 아이템 무관). "햇불 값은 %d Gold가 되는데 괜찮으시겠습니까?\""""
    return (
        MC
        + PS
        + MC
        + encode_ext(" 값은")
        + b"\x0a"
        + PD
        + encode_ext(" Gold가 되는데")
        + b"\x0a"
        + encode_ext("괜찮으시겠습니까?")
        + b"\x0a"
        + MC
    )


# ── ED.EXE 도너 공간 — size 퇴출 블록의 이주지 ─────────────────────────────
# ED.EXE는 상주라 SCN 오버레이의 lui/addiu 참조를 이쪽 RAM 주소로 돌리면 그대로 읽힌다
# (순수 데이터 이동 — 코드 훅·런타임 비용 없음). 도너 = ED.EXE 데이터 세그먼트의 미사용
# 0런 16개(총 ~8.3KB). 안전성 검증(2026-07-26): ①원본·현빌드 양쪽 0 ②ED.EXE+전 SCN
# 디스어셈블에서 포인터(addiu/ori)·절대 접근(lui+lw/sw 등) 참조 0건 — 주변은 개별 주소로
# 참조되는 CPU 데이터 세그먼트(374건)라 통짜 DMA 아님 ③필드·전투 세이브스테이트 RAM
# 덤프에서 전 구간 0 유지(런타임 버퍼 아님). 갱신 시 같은 3중 검증을 반복할 것.
DONOR_RUNS = [  # (ED.EXE file offset lo, hi) — RAM = off - 0x800 + 0x80010000
    # (0x0BF5DC, 0x0BF7E8) · (0x0C105C, 0x0C1268) — 조사 훅 예약(patch_josa_hook, 07-27)
    (0x0C2B1C, 0x0C2D28),
    (0x0C620C, 0x0C6418),
    (0x0C821C, 0x0C8428),
    (0x0C8F4C, 0x0C9158),
    (0x0CA1AC, 0x0CA3B8),
    (0x0CB1AC, 0x0CB3BC),
    (0x0CC97C, 0x0CCB88),
    (0x0CF71C, 0x0CF92C),
    (0x0D236C, 0x0D2578),
    (0x0D568C, 0x0D5898),
    (0x0D7C9C, 0x0D7EA8),
    (0x0D997C, 0x0D9B88),
    (0x0DD71C, 0x0DD928),
    (0x0E1E5C, 0x0E2068),
]
ED_EXE_RAM = 0x80010000 - 0x800  # RAM = file_off + 이 값

# ── 오버레이 확장(근본 해결, 07-26 밤) ─────────────────────────────────────
# 엔진은 SCN을 **ISO 파일시스템 경로**(`\BIN\ED1SCN1.BIN;1` @ED.EXE 0xC3F4~)로 로드한다
# — 디렉토리 레코드의 LBA·size만 고치면 커진 파일을 그대로 읽어 0x8016A000에 올린다.
# 절차: 파일 꼬리에 확장 영역(씬 전용 도너)을 붙이고, 커진 파일은 DUMMY.;1(LBA 91700,
# 31.7MB 패딩)에 재배치 + BIN 디렉토리 레코드 패치(main). 이미지 크기 불변.
# RAM 상한: 필드·전투 덤프 실측에서 0x801A0000에 2.3KB 사용 섬 — 그 직전까지만 확장.
# (TearRing-Saga-KOR의 파일 재배치 기법 참조 — 유저 제공 2026-07-26)
OVERLAY_RAM_LIMIT = 0x801A0000
SCN_EXTRA_MAX = 16384  # 씬당 확장 상한(수요 기반 — 전 씬 부족 합계 ~22KB, 씬별로 충분)
DUMMY_LBA = 91700  # 재배치 목적지(DUMMY.;1 시작). 순차 할당.
BIN_DIR_LBA = 1182  # \BIN 디렉토리 레코드 섹터


def scn_extra(name, file_size):
    """씬별 확장 바이트 — RAM 상한과 정책 상한의 최소."""
    cap = (OVERLAY_RAM_LIMIT - OVERLAY_RAM_BASE) - file_size
    return max(0, min(cap, SCN_EXTRA_MAX)) & ~3


# 씬 순서대로 소비하는 전역 할당기(SCN1이 QA 최전선이라 우선권). main()이 리셋.
_donor_cursor = []


def donor_reset():
    _donor_cursor.clear()
    _donor_cursor.extend([lo, hi] for lo, hi in DONOR_RUNS)


def donor_alloc(size):
    """4B 정렬 first-fit. 반환 ED.EXE 파일 오프셋 또는 None(고갈)."""
    size = size + (-size % 4)
    for run in _donor_cursor:
        if run[1] - run[0] >= size:
            off = run[0]
            run[0] += size
            return off
    return None


# 부호 전용 창(침묵 「・・・」 등) 판정 — 번역할 내용이 없어 JP 바이트를 그대로 통과시킨다.
_PUNCT_WIN = re.compile(r"[\s・･。、．，…‥！？!?ーｰ─\-]*\Z")


def _tpl_punct_only(seg):
    txt = b"".join(t[1] for t in seg if t[0] == "t")
    if not txt:
        return False
    try:
        return bool(_PUNCT_WIN.fullmatch(txt.decode("cp932")))
    except UnicodeDecodeError:
        return False


def build_from_template(raw, speaker, pages, max_lines=None):
    """JP 골격을 그대로 두고 본문 창에 정발 문장을 채워 블록을 만든다.

    제어 토큰(%c/%s/%d)은 **바이트 그대로** 방출하므로 구조 충실도가 100%가 되고,
    여분 %c·개행을 안 만들어 바이트도 줄어든다.

    채우기 모드(2026-07-24 — 화자/색 오배정 QA로 재설계):
      ① 정발 페이지 수 == 본문 창 수 → **1:1 배정**(창=화자·색 단위이므로 이것이 정본)
      ② 페이지 수 == 부호 전용 창(침묵 ・・・)을 뺀 창 수 → 부호 창은 JP 통과 + 1:1
      ③ 불일치 + 제어 시퀀스 블록(%c 런 존재) → **포기**(균형 분배는 화자·색 경계를
         무시하고 문장을 흩뿌린다 — 세리오스 창에 퍼거슨 대사가 든 실측 QA) → JP 유지
      ④ 불일치 + 단순 블록(단일 화자 연속 창) → 기존 균형 분배(창 수 계약 유지)"""
    wins = template_windows(parse_template(raw))
    body_idx = [k for k, (kind, _) in enumerate(wins) if kind == "body"]
    # %s/%d만 있고 텍스트가 없는 창(이름 주입 창 — `%c%s%cが仲間に…`)은 절대 채우면 안
    # 된다(서식 지정자 유실 = 인자 소비 어긋남). 후보에서 제외해 골격 그대로 방출(eid 1174).
    body_idx = [
        k
        for k in body_idx
        if any(t[0] == "t" for t in wins[k][1]) or not any(t[0] in "sd" for t in wins[k][1])
    ]
    if not body_idx:
        raise SkipBlock("본문 창 없음")
    # 채움 제외(JP 통과) 창: 부호 전용(침묵 ・・・) + 토큰 없는 빈 창(종단 %c%c 사이).
    punct = {
        k
        for k in body_idx
        if _tpl_punct_only(wins[k][1]) or not any(t[0] == "t" for t in wins[k][1])
    }
    fill = [k for k in body_idx if k not in punct]
    if not fill and pages:
        raise SkipBlock("채울 본문 창 없음")
    has_name = any(kind == "name" for kind, _ in wins)
    lim = max_lines or (LINES_PER_PAGE - 1 if has_name else LINES_PER_PAGE)

    def one_page(pg):
        c = wrap_page(pg, target=1, max_lines=lim)
        if len(c) != 1:
            raise SkipBlock("페이지 창 초과")
        return c[0]

    def _after_name_inject(k):
        """직전 창이 인라인 %s 주입 창(텍스트 없는 body) — 이 창의 첫 줄은 주입된 이름과
        같은 줄에 이어지므로 이름 폭을 조판 계산에 넣어야 한다(동료 합류 온점 고아 실측 07-26)."""
        return (
            k > 0
            and wins[k - 1][0] == "body"
            and any(t[0] == "s" for t in wins[k - 1][1])
            and not any(t[0] == "t" for t in wins[k - 1][1])
        )

    def fill_page(k, pg):
        if _after_name_inject(k):
            lines = one_page(NAME_SENT + pg)  # 이름 폭(NAME_SLOTS)을 첫 줄에 반영
            lines[0] = lines[0].lstrip(NAME_SENT).lstrip()
            return lines
        return one_page(pg)

    # 1:1 배정 후보 목록: ①정발 {p} 페이지 그대로 ②인라인 화자를 독립 창 내용으로 전개.
    # ②는 색 괄호 스팬 대응 — eid 28 장비 3종 `%c(2)王家のつるぎ%c(3)を装備…`의 아이템명
    # 창을 DOS 인라인 헤더({spk}왕가의 검{/spk})가 정확히 채운다(콜사이트 인자 실증).
    lists = [[(pg, False) for _, pg in pages]]
    if any(spk for spk, _ in pages):
        exp = []
        for spk, pg in pages:
            if spk:
                exp.append((spk, True))
            exp.append((pg, False))
        lists.append(exp)
    complex_blk = jp_ctrl_runs(raw) > 0 and len(fill) >= 2  # 다중 화자·색 전환 = 배정 근거 필수
    # 이름만 번역(NAMEONLY, pages=[]): 본문은 전부 punct/빈 창 통과 — 채울 것 없이 골격 방출.
    chunks, nl_wins = ({}, set()) if not pages else (None, set())
    for lst in lists:
        targets = body_idx if len(lst) == len(body_idx) else fill if len(lst) == len(fill) else None
        if targets is None or len(body_idx) < 2:
            continue
        try:
            trial, spk_wins = {}, []
            for k, (pg, is_spk) in zip(targets, lst, strict=True):
                trial[k] = fill_page(k, pg)
                if is_spk:
                    spk_wins.append(k)
            chunks = trial
            # 전개 창(아이템명 등)은 각자 새 줄에서 시작 — 붙여 쓰면 렌더러 자동 줄바꿈이
            # 이름 중간을 자른다(장비 3연속 실측, 유저 QA). 첫 창은 창 선두라 개행 불필요.
            nl_wins = set(spk_wins[1:])
            break
        except SkipBlock:
            chunks = None
    if chunks is None:
        if complex_blk:
            raise SkipBlock(f"창-페이지 불일치({len(pages)}!={len(fill)})")
        # 색 스팬 가드(균형 분배 한정): 개행이 전혀 없는 본문 창이 다른 창과 병존하면 그 %c는
        # 페이지 경계가 아니라 본문 중간의 색/아이템명 스팬일 가능성이 높다 — 균형 분배가
        # 문장을 스팬 경계에 흩뿌리므로 포기한다. 진짜 페이지는 nl을 하나는 가진다.
        if len(body_idx) >= 2 and any(not any(t[0] == "nl" for t in wins[k][1]) for k in fill):
            raise SkipBlock("본문 창 색 스팬 의심")
        joined = "\n".join(pg for _, pg in pages)
        if len(fill) == 1 and _after_name_inject(fill[0]):
            cl = [fill_page(fill[0], joined)]  # 이름 폭 반영(단일 창 — 균형 경로)
        else:
            cl = wrap_page(joined, target=len(fill), max_lines=lim)
        if len(cl) != len(fill):
            raise SkipBlock(f"창 분배 실패({len(cl)}!={len(fill)})")  # 용량 초과 = 정발 문장이 김
        chunks = dict(zip(fill, cl, strict=True))

    parts, name_i = [], 0
    for k, (kind, seg) in enumerate(wins):
        b = bytearray()
        if kind == "body" and k in chunks:
            # 이름 헤더 뒤 개행만 골격으로 유지(이름이 창의 1줄 점유). 이름 없는 창의
            # 선두 개행은 빈 첫 줄로 렌더된다(eid 30 "알았어" 실측, 유저 QA 07-24) → 제거.
            if k in nl_wins:
                b += b"\x0a"
            elif seg and seg[0][0] == "nl" and k > 0 and wins[k - 1][0] == "name":
                b += b"\x0a"
            b += encode_ext("\n".join(chunks[k]))
            # 다음 창이 인라인 %s 주입 창(텍스트 없는 body)이면 이름 앞 공백 —
            # 한국어는 "제 이름은 류난"처럼 띄어야 한다(JP는 무공백, eid 1164 실측 07-26)
            if (
                k + 1 < len(wins)
                and wins[k + 1][0] == "body"
                and any(t[0] == "s" for t in wins[k + 1][1])
                and not any(t[0] == "t" for t in wins[k + 1][1])
            ):
                b += b"\x20"
        else:
            for t in seg:
                if t[0] == "nl":
                    b += b"\x0a"
                elif t[0] == "s":
                    b += PS
                elif t[0] == "d":
                    b += PD
                elif t[0] == "t":
                    b += _tpl_name(t[1], speaker, name_i == 0) if kind == "name" else t[1]
            if kind == "name":
                name_i += 1
        parts.append(bytes(b))
    blk = MC.join(parts)
    pad = 4 - len(blk) % 4 or 4
    return blk + b"\x00" * pad


def build_block(speaker, pages, target=None, header=True, hdr_fmt=False, inline_fmt=()):
    """PS1 블록 재구성: %c 화자 %c 0A 본문(페이지는 %c 구분) %c + 4바이트 정렬 00패딩.

    target(=JP 창 수)이 주어지면 **정확히 target개 창**으로 조판한다(창 수 계약).
    이때 {p} 경계는 하드 개행 힌트로만 남기고 창 경계는 target에 맞춰 다시 잡는다 —
    부족(=빈 창·소프트락)도 초과(=꼬리 잘림)도 안 나게 하는 게 우선이기 때문.
    인라인 화자(%c화자%c)가 있는 블록은 화자가 창 선두를 점유해야 해서 target 조판을
    적용하지 않고 기존 {p} 단위 조판을 쓴다(소수 — 초과 감수)."""
    # 화자 이름은 창의 **첫 줄을 차지**한다(2026-07-22 유저 실측) — 헤더 있는 블록의
    # 본문 상한은 6이 아니라 5. 6줄로 조판하면 이름+6줄=7줄이 되어 창을 뚫는다.
    body_lines = LINES_PER_PAGE - 1 if header else LINES_PER_PAGE
    if inline_fmt:
        body_lines -= 1  # 인라인 화자 줄 확보(해당 블록 전체에 보수적으로 적용)
    has_inline = any(spk for spk, _ in pages)
    if target and not has_inline:
        text = "\n".join(pg for _, pg in pages)  # {p} 경계 → 개행(정발 호흡 힌트)
        parts = [
            encode_ext("\n".join(lines))
            for lines in wrap_page(text, target=target, max_lines=body_lines)
        ]
    else:
        parts = []
        for inline_spk, page in pages:
            for j, lines in enumerate(wrap_page(page, max_lines=body_lines)):
                seg = encode_ext("\n".join(lines))
                if j == 0 and inline_spk:
                    seg = MC + encode_ext(inline_spk) + MC + b"\x0a" + seg
                parts.append(seg)
    # 인라인 화자 헤더(%c%s%c): JP가 그 창에서 화자를 바꿨다는 뜻 — 창 번호를 맞춰 방출한다.
    # 창 수 계약으로 KR 창 수 == JP 창 수라 창 번호가 1:1 대응한다.
    if inline_fmt:
        parts = [
            (MC + PS + MC + b"\x0a" + seg) if (k + 1) in inline_fmt else seg
            for k, seg in enumerate(parts)
        ]
    body = MC.join(parts)
    # 원본 구조를 그대로 따른다: 헤더 없는 블록(내레이션류 848개)에 헤더를 붙이면
    # %c가 2개 초과 생산돼 꼬리 창이 통째로 잘린다(2026-07-22 실측).
    # 화자 헤더: 원본이 %c%s%c(런타임 이름 주입)면 **그대로 %s를 방출**한다. 리터럴로 바꾸면
    # 플레이어가 정한 이름이 무시되고, %s가 줄어 엔진 인자 소비가 어긋나 씬이 정지한다.
    head = (MC + (PS if hdr_fmt else encode_ext(speaker)) + MC + b"\x0a") if header else b""
    blk = head + body + MC
    pad = 4 - len(blk) % 4 or 4
    return blk + b"\x00" * pad


# ── 포인터 참조 수집 (공용 iter_lui_pairs 사용) ─────────────────────────────
def find_refs(data, text_end):
    """lui+addiu/ori 쌍으로 텍스트 영역을 가리키는 참조: [(addiu_off, lui_off, op, addr)]."""
    return [
        (imm_off, lui_off, op, addr)
        for imm_off, lui_off, op, addr in iter_lui_pairs(data, (MIPS_ADDIU, MIPS_ORI))
        if OVERLAY_RAM_BASE <= addr < OVERLAY_RAM_BASE + text_end
    ]


def patch_word_imm(buf, off, imm):
    wd = int.from_bytes(buf[off : off + 4], "little")
    buf[off : off + 4] = ((wd & 0xFFFF0000) | (imm & 0xFFFF)).to_bytes(4, "little")


def hi_lo(addr, op):
    lo = addr & 0xFFFF
    hi = (addr >> 16) + (1 if op == MIPS_ADDIU and lo >= 0x8000 else 0)
    return hi, lo


def compute_anchors(data, text_end):
    """텍스트 영역 내 lui+lw로 참조되는 데이터 테이블(점프 테이블 등)의 바이트 범위.

    코드가 절대주소로 읽으므로 절대 이동 금지 앵커다. 재배치 멈춤의 원인
    (2026-07-09 emucap 규명)이 바로 이 테이블이 대사에 밀려 어긋난 것.
    각 lui+lw base에서 오버레이 포인터(또는 null 슬롯)가 이어지는 동안을 테이블로 보고,
    인접 범위는 병합. 큰 쪽으로 근사(테이블을 조금 크게 잡으면 안전, 작으면 위험)."""
    lo, hi = OVERLAY_RAM_BASE, OVERLAY_RAM_BASE + len(data)  # 오버레이 전체 범위 (파일 크기)
    bases = {
        addr - OVERLAY_RAM_BASE
        for _, _, _, addr in iter_lui_pairs(data, (MIPS_LW,))
        if 0 <= addr - OVERLAY_RAM_BASE < text_end
    }

    def is_entry(v):
        return lo <= v < hi or v == 0  # 오버레이 포인터 또는 null 슬롯

    ranges = []
    for b in sorted(bases):
        if b % 4:
            continue  # 워드 정렬 안 된 우연 일치는 무시
        o = b
        while o + 4 <= text_end and is_entry(int.from_bytes(data[o : o + 4], "little")):
            o += 4
        if o > b:
            ranges.append((b, o))
    merged = []
    for s, e in sorted(ranges):
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def build_candidate(raw, t, eid):
    """번역 후보 바이트 생성 + 구조 계약 가드. 반환 (cand, None) 또는 (None, 제외사유).

    reflow_run(재배치)과 도너 2단계(build_scene)가 공유하는 단일 경로 — 가드 목록:
    - encode: 조판/인코딩 실패
    - ctrl_seq: 원본 %c 런을 build_block이 재현 못 함(색·화자 오배정 방지, 템플릿 성공분 면제)
    - window_deficit: %c 부족 = 과잉읽기 소프트락(치명)
    - fmt_drop: %s/%d 부족 = 인자 소비 어긋남(씬 정지)"""
    from_tpl = False
    # 주입 %c쌍 블록: 쌍을 실제 글자로 치환한 정본 JP로 템플릿을 만들고 뒤에 복원
    raw_t, tails = raw, None
    if eid in INJECT_PAIRS:
        raw_t, tails = strip_inject_pairs(raw, INJECT_PAIRS[eid])
    if t[0] is STOCK:
        # 정형 블록: 전용 빌더가 원본 %c/%s 순서를 그대로 재현 — 템플릿 가드 면제,
        # 아래 %c·%s/%d 계약 가드는 공통으로 통과시킨다.
        cand, from_tpl = stock_build(raw), True
        if cand is not None:
            cand += b"\x00" * (-len(cand) % 4 or 4)
    elif t[0] is SHOP_PRICE:  # 상점 가격 프롬프트: %d 인라인 보존 전용 빌더
        cand, from_tpl = shop_price_build(raw), True
        cand += b"\x00" * (-len(cand) % 4 or 4)
    elif t[0] is NAMEONLY:
        # 침묵 블록: 빈 페이지로 템플릿 — 본문(・・・)은 JP 통과, 이름창만 화자맵 번역
        try:
            cand, from_tpl = build_from_template(raw, "", []), True
        except SkipBlock:
            return None, "encode"
    else:
        try:
            # 원본 골격 채우기를 우선한다 — 제어 토큰을 그대로 방출해 구조 충실도가
            # 100%가 되고 여분 %c·개행이 없어 바이트도 크게 준다(전 씬 -22%).
            # 용량 초과(정발 문장이 창보다 김)면 기존 재조판으로 폴백해 커버리지를 지킨다.
            try:
                cand = build_from_template(raw_t, t[0], t[1])
                from_tpl = True
                if tails:
                    cand = reinsert_pairs(cand, tails)
            except SkipBlock:
                if tails:
                    raise  # 주입 쌍 블록은 build_block이 창 번호를 재현 못 함 — JP 유지
                cand = build_block(*t)
        except SkipBlock:
            return None, "encode"
    # 창 수 계약: 엔진은 블록당 %c 세그먼트를 **원본 수만큼** 읽는다. KR이 원본보다
    # 적으면 종단을 못 만나고 뒤 데이터까지 읽어 깨진 글자를 뿌리며 무한 대기(소프트락)
    # — 1장 탈출→월드맵 먹통의 증상. 초과는 꼬리 잘림(표시 손실)이라 허용, 부족만 제외.
    # 제어 시퀀스 계약: 원본의 연속 %c 런(화자 헤더·페이지/색 전환)은 우리가 재현하는
    # 인라인 헤더 수만큼만 감당한다. 그보다 많으면 텍스트를 N조각으로 강제 분할하면서
    # 제어 인자가 밀려 **대사가 엉뚱하게 쪼개지고 색이 문장 중간에서 바뀐다**(eid 27 실측).
    # **템플릿 성공 블록은 이 가드를 통과한다** — 제어 토큰을 바이트 그대로 방출하므로
    # 구조가 원본과 동일하고, 이름창도 화자맵으로 개별 번역된다(_tpl_name). 가드는
    # build_block 폴백(구조를 재생산하는 쪽)에만 필요하다.
    if cand is not None and not from_tpl:
        n_runs = jp_ctrl_runs(raw)
        _, inline_fmt = jp_inline_fmt_windows(raw)
        # ⚠ 비교 대상은 인라인 헤더 "총개수"가 아니라 **우리가 실제로 방출하는 %s 헤더 수**다.
        # 리터럴 이름 헤더(%c퍼거슨%c)는 재현하지 못하므로 총개수와 비교하면 그냥 통과해
        # 텍스트가 엉뚱하게 쪼개진다(eid 23 실측: 왕자님|부탁이라, 지는|머든지).
        if n_runs > len(inline_fmt):
            return None, "ctrl_seq"
    if cand is not None and cand.count(MC) < raw.count(MC):
        return None, "window_deficit"
    # %s·%d 계약: 서식 지정자는 흐름 제어(런타임 이름/수치 주입) — 재조립본에서 줄면
    # 엔진의 인자 소비가 어긋난다. 현 조판은 인라인 화자(%c%s%c)를 보존하지 못하므로
    # (build_block이 첫 화자만 방출) 누락 블록은 번역 제외(JP 유지). 근본 해결은
    # %s 바이트 방출 + 인라인 화자 헤더 보존(HANDOFF "후속(대사 구조)" 항목).
    if cand is not None and (
        cand.count(b"\x25\x73") < raw.count(b"\x25\x73")
        or cand.count(b"\x25\x64") < raw.count(b"\x25\x64")
    ):
        return None, "fmt_drop"
    return cand, None


def reflow_run(region, run, run_start, run_end, translations, excluded, fixed, layout):
    """자유 구간 [run_start, run_end)(앵커 사이)에 자유 블록들을 재배치.

    총량이 구간 크기를 넘으면 성장폭 큰 번역부터 제외(size). fixed=True면
    블록별 원본 길이 고정(짧으면 00패딩). 남는 공간은 00패딩 — 앵커 위치 불변."""
    run_space = run_end - run_start
    news = []
    for b in run:
        new, eid = b["raw"], b["eid"]
        if eid in translations and eid not in excluded:
            cand, reason = build_candidate(b["raw"], translations[eid], eid)
            if reason:
                excluded[eid] = reason
            if cand is not None:
                if fixed:
                    if len(cand) <= len(b["raw"]):
                        new = cand + b"\x00" * (len(b["raw"]) - len(cand))
                    else:
                        excluded[eid] = "size"
                else:
                    new = cand
        news.append(new)
    if not fixed:
        while sum(len(x) for x in news) > run_space:
            cands = [
                k
                for k, b in enumerate(run)
                if b["eid"] in translations and b["eid"] not in excluded and news[k] != b["raw"]
            ]
            if not cands:
                raise SystemExit(f"자유 구간 0x{run_start:X} 수용 불가 (원본조차 초과?)")
            # 퇴출 선택 = best-fit: 초과분을 덮는 최소 성장 블록 하나를 고른다(있으면).
            # 최대 성장 우선은 초과 4B에 성장 44B 블록을 내보내는 낭비가 있었다(1111 실측
            # 07-26 — +4B 블록 하나로 충분했다). 덮는 블록이 없으면 최대 성장 폴백.
            # (오버라이드 우선 보호 실험은 역효과 — 자동 블록을 전부 내보내고도 결국 최대
            # 성장 블록을 퇴출해 소블록 100여 개만 잃었다.)
            over = sum(len(x) for x in news) - run_space
            grow = lambda k: len(news[k]) - len(run[k]["raw"])  # noqa: E731
            fit = [k for k in cands if grow(k) >= over]
            k = min(fit, key=grow) if fit else max(cands, key=grow)
            excluded[run[k]["eid"]] = "size"
            news[k] = run[k]["raw"]
    assert sum(len(x) for x in news) <= run_space, "run 초과"
    pos = run_start
    for b, new in zip(run, news, strict=True):
        region[pos : pos + len(new)] = new
        layout.append((b["off"], len(b["raw"]), pos, len(new), b["eid"]))
        pos += len(new)
    for p in range(pos, run_end):  # 앞선 축소분 → 00패딩(다음 앵커 위치 고정)
        region[p] = 0


# ── 메인 ────────────────────────────────────────────────────────────────────
def _load_overrides():
    """사람 검수 교정(align_overrides.json). 없으면 빈 dict."""
    path = os.path.join(os.path.dirname(OUT_DIR), "align_overrides.json")
    if not os.path.exists(path):
        return {}
    return json.load(open(path, encoding="utf-8"))


_SPEAKER_MAP = None


def _speaker_map():
    """JP 화자 → 정발 화자 대응표(out/align/ED1_speakers.json). 정렬 채택 판정용."""
    global _SPEAKER_MAP
    if _SPEAKER_MAP is None:
        path = os.path.join(OUT_DIR, "align", "ED1_speakers.json")
        try:
            _SPEAKER_MAP = json.load(open(path, encoding="utf-8"))["map"]
        except (FileNotFoundError, KeyError):
            _SPEAKER_MAP = {}
    return _SPEAKER_MAP


def accept_pair(p):
    """정렬쌍 채택 여부 — **화자 일치가 유사도보다 강한 신호**다(2026-07-23 실측).

    LaBSE 유사도만 쓰면 ①점수는 높은데 화자가 틀린 쌍이 채택돼 엉뚱한 대사가 나가고
    (전 씬 113건 — 유저가 반복 보고한 "상관없는 대사") ②화자가 맞는데 점수 미달로
    버려지는 쌍이 생긴다(309건). 그래서 화자 대응이 확인되면 그걸 우선한다.
      화자 일치 → low_sim이어도 채택 / 화자 불일치 → 무플래그여도 제외
      화자 정보가 없거나 매핑에 없으면 → 기존 플래그 기준으로 판정
    """
    if not p.get("jp"):
        return False
    jp_sp = p["jp"].get("speaker")
    kr_sp = (p.get("kr") or {}).get("speaker")
    if jp_sp and kr_sp:
        expect = _speaker_map().get(jp_sp)
        if expect:
            return expect == kr_sp
    return not p.get("flags")


def load_translations(align_name, scn_name):
    """정렬 고신뢰 쌍(+ 사람 검수 오버라이드) → {jp_entry_id: (화자, 페이지들)}."""
    INJECT_PAIRS.clear()  # 씬 단위 상태 — 오버라이드 inject_pairs가 재구축
    align = json.load(open(os.path.join(OUT_DIR, "align", f"{align_name}.json"), encoding="utf-8"))
    jp_doc = json.load(open(os.path.join(OUT_DIR, "scn_jp", f"{scn_name}.json"), encoding="utf-8"))
    # 창 수 계약의 단위는 엔진이 실제로 세는 **raw %c 개수**다(인라인 화자 헤더의 %c 포함).
    # 우리 블록의 %c = parts + 2(화자헤더 2 + 종단 1 - join 1)이므로 target = jp_mc - 2로 잡으면
    # 재조립본의 %c 총수가 원본과 정확히 일치한다. (jp_windows()는 의미상 창 수라 병합 상한용.)
    jp_win, jp_hdr_name = {}, {}
    for e in jp_doc["entries"]:
        if e.get("raw_hex"):
            raw = bytes.fromhex(e["raw_hex"])
            mc, hdr = raw.count(MC), jp_has_header(raw)
            _, inline_fmt = jp_inline_fmt_windows(raw)
            # W = mc - 2*블록헤더 - 2*(우리가 방출하는 %s 인라인 헤더)
            # ⚠ 리터럴 인라인 헤더는 방출하지 않는다 — 그 몫은 창을 하나 더 만들어 %c 개수를
            #   맞추는 기존 동작을 유지해야 한다(빼버리면 %c가 모자라 window_deficit이 된다).
            jp_win[e["entry_id"]] = (
                max(1, mc - (2 if hdr else 0) - 2 * len(inline_fmt)),
                hdr,
                jp_header_is_fmt(raw),
                inline_fmt,
            )
            if hdr and not jp_header_is_fmt(raw):
                try:
                    jp_hdr_name[e["entry_id"]] = raw[2 : raw.find(MC, 2)].decode("cp932")
                except UnicodeDecodeError:
                    pass
    kr_cache = {}

    def resolve_spk(jp_id, spk):
        """DOS 엔트리에 화자가 없을 때의 폴백: %s 헤더·헤더 없는 블록은 이름을 방출하지
        않으므로 빈 화자 OK, 리터럴 헤더는 화자맵(JP 이름→정발명)으로 해결. 둘 다 아니면
        기존대로 SkipBlock(화자 없음)."""
        if spk:
            return spk
        _, hdr, hdr_fmt, _ = jp_win.get(jp_id, (None, True, False, set()))
        if hdr_fmt or not hdr:
            return ""
        kr = _speaker_map().get(jp_hdr_name.get(jp_id))
        if not kr:
            raise SkipBlock("화자 없음")
        return kr

    def kr_entry(table, eid):
        if table not in kr_cache:
            doc = json.load(
                open(os.path.join(OUT_DIR, "dos_kr", f"{table}.json"), encoding="utf-8")
            )
            kr_cache[table] = {e["entry_id"]: e for e in doc["entries"]}
        return kr_cache[table][eid]

    out, skipped = {}, {}
    consumed_all, src_of = set(), {}
    for p in align["pairs"]:
        if not accept_pair(p):
            continue
        entry = dict(kr_entry(p["kr"]["table"], p["kr"]["entry_id"]))
        entry, consumed = splice_placeholder_pages(
            entry, p["kr"]["table"], kr_entry, target=jp_win.get(p["jp"]["entry_id"], (None,))[0]
        )
        consumed_all.update(consumed)
        src_of[p["jp"]["entry_id"]] = (p["kr"]["table"], p["kr"]["entry_id"])
        entry["speaker"] = p["kr"]["speaker"]  # 승계 화자 반영
        try:
            spk, pages = parse_kr(entry)
            spk = resolve_spk(p["jp"]["entry_id"], spk)
            out[p["jp"]["entry_id"]] = (spk, pages) + jp_win.get(
                p["jp"]["entry_id"], (None, True, False, set())
            )
        except SkipBlock as e:
            skipped[str(e)] = skipped.get(str(e), 0) + 1

    # 플레이스홀더 병합에 소비된 연속 엔트리의 단독 쌍 제거 — 화자 없는 연속 대사가
    # 다른 JP 블록에 오매칭돼 같은 대사가 두 번 나오는 것 방지(jp110↔T_000#9 실측 07-19)
    dup = [j for j, src in src_of.items() if src in consumed_all and j in out]
    for j in dup:
        del out[j]
    if dup:
        print(f"  병합 소비 엔트리의 단독 쌍 {len(dup)}건 제외(중복 방지): jp={dup[:8]}")

    # 사람 검수 오버라이드: align보다 우선 (틀린 짝 교정 or 신규 추가)
    applied = 0

    def chain_text(table, item):
        """체인 항목 → 텍스트. int=엔트리 전체, "id#k"=그 엔트리의 k번째 {p} 페이지만.
        (페이지 슬라이스는 정발 엔트리 경계가 JP 블록 경계와 어긋날 때 — eid 27 잔소리 서두)"""
        base, _, pi = str(item).partition("#")
        t = kr_entry(table, int(base))["text"].removesuffix("{end}")
        if pi:
            t = t.split("{p}")[int(pi)]
        return t if t.endswith("{p}") else t + "{p}"

    for jp_id_str, ov in _load_overrides().get(scn_name, {}).items():
        if jp_id_str.startswith("_"):
            continue
        if ov.get(
            "exclude"
        ):  # 오배정 확정인데 올바른 짝이 정발에 없는 블록 — 정렬 쌍 제거(JP 유지)
            out.pop(int(jp_id_str), None)
            continue
        if "inject_pairs" in ov:  # 주입 %c쌍 좌표(사람이 콜사이트 인자로 확정) — 상단 주석 참조
            INJECT_PAIRS[int(jp_id_str)] = [(o, bytes.fromhex(h)) for o, h in ov["inject_pairs"]]
        if "ours" in ov:
            # 정발에 대응 문장이 없는 블록의 신규 번역(우리 문안 — textmap의 ours와 같은 지위).
            entry = {"text": ov["ours"], "speaker": ov.get("speaker")}
        elif "chain" in ov:
            entry = dict(kr_entry(ov["table"], ov["entry_id"]))
            # 명시적 체인: 사람이 확정한 엔트리 나열을 {p} 페이지로 이어붙인다.
            # (자동 splice는 빈 엔트리에서 끊겨 다화자 이벤트 체인을 못 잇는다 — T_001#20 실측)
            entry["text"] = "".join(chain_text(ov["table"], it) for it in ov["chain"])
            # 사람 확정 자구 교정(유실 부호 등 — 정발 원문 변경은 유저 승인 기록 필수)
            for a, b in ov.get("subs", ()):
                entry["text"] = entry["text"].replace(a, b)
        else:
            entry = dict(kr_entry(ov["table"], ov["entry_id"]))
            entry, _ = splice_placeholder_pages(
                entry, ov["table"], kr_entry, target=jp_win.get(int(jp_id_str), (None,))[0]
            )
        entry["speaker"] = ov.get("speaker") or entry.get("speaker")
        try:
            spk, pages = parse_kr(entry)
            final_spk = resolve_spk(int(jp_id_str), ov.get("speaker") or spk)
            out[int(jp_id_str)] = (final_spk, pages) + jp_win.get(
                int(jp_id_str), (None, True, False, set())
            )
            applied += 1
        except SkipBlock as e:
            # 사람이 지정한 교정이 조용히 사라지면 안 된다 — 반드시 보고
            print(f"경고: {scn_name} 오버라이드 jp={jp_id_str} 적용 실패 ({e}) — 수정 필요")

    # 정형 시스템 블록(보물상자): 정렬과 무관하게 JP 원문 매칭으로 일괄 등록.
    # translations에 넣어 핀 판정·size 제외·통계를 기존 경로 그대로 태운다.
    # ⚠ 정렬 쌍이 이미 잡은 사본도 **덮어쓴다** — DOS 쪽 아이템 주입 자리(\x06\x0E`N)를
    # parse_kr가 재현 못 해 fmt_drop으로 빠지거나 주입 자리가 깨진 채 나가기 때문.
    STOCK_KINDS.clear()
    n_price = 0
    for e in jp_doc["entries"]:
        if e.get("raw_hex"):
            raw = bytes.fromhex(e["raw_hex"])
            kind = stock_kind(raw)
            if kind:
                out[e["entry_id"]] = (STOCK,)
                STOCK_KINDS[e["entry_id"]] = kind
            elif is_shop_price(raw):  # 상점 가격 프롬프트(%d 인라인) — 전용 빌더
                out[e["entry_id"]] = (SHOP_PRICE,)
                n_price += 1
    if STOCK_KINDS:
        print(f"  정형 블록(보물상자) {len(STOCK_KINDS)}건 등록")
    if n_price:
        print(f"  상점 가격 프롬프트 {n_price}건 등록")

    # 침묵 블록(리터럴 헤더 + 본문 전부 부호/빈 창): 이름창만 번역 등록. 그냥 두면
    # 화자명까지 セリオス로 남는다(유저 QA 07-26). 크기 중립이라 공간 압박 없음.
    n_no = 0
    for e in jp_doc["entries"]:
        if not e.get("raw_hex") or e["entry_id"] in out:
            continue
        raw = bytes.fromhex(e["raw_hex"])
        if not jp_has_header(raw) or jp_header_is_fmt(raw):
            continue
        try:
            wins = template_windows(parse_template(raw))
        except Exception:
            continue
        body = [w for kind, w in wins if kind == "body"]
        if body and all(_tpl_punct_only(w) or not any(tk[0] == "t" for tk in w) for w in body):
            out[e["entry_id"]] = (NAMEONLY,)
            n_no += 1
    if n_no:
        print(f"  침묵 블록(이름만 번역) {n_no}건 등록")
    return out, skipped, applied


def rebuild(
    scn_entries, data, translations, excluded, anchors, text_end, fixed=False, referenced_eids=None
):
    """앵커(테이블) 고정 재배치. 반환: (region, old→new 오프셋 매핑 블록 목록).

    앵커와 겹치는 블록은 pinned(원본 위치·바이트 그대로) — 테이블 보존.
    나머지 자유 블록은 앵커 사이 구간에서만 재배치(reflow_run). 앵커는 절대 안 움직여
    lui+lw 절대참조가 유효하게 유지된다. fixed=True는 블록별 원본 길이 고정."""
    blocks = []
    for e in scn_entries:
        off = int(e["file_offset"], 16)
        raw = bytes.fromhex(e["raw_hex"])
        assert data[off : off + len(raw)] == raw, f"scn_jp raw 불일치 @{e['entry_id']}"
        blocks.append({"off": off, "raw": raw, "eid": e["entry_id"]})

    def hits_anchor(s, e):
        return any(s < ae and a_s < e for a_s, ae in anchors)

    for b in blocks:
        # 이동 안전성: 갱신 가능한 포인터(addiu/ori — find_refs가 갱신)로 참조되지도, 번역되지도
        # 않는 블록은 절대주소/상대접근으로만 읽히므로 **이동하면 그 참조가 stale**해진다.
        # (2026-07-22 규명: 침실→월드맵 먹통의 원인 = 미참조 2바이트 값 테이블@0x757E가 대사
        # 패킹에 밀려 캐릭터 이동 스크립트가 깨짐. 앵커는 lui+lw 포인터테이블만 잡아 이 테이블을
        # 놓쳤다.) → 미참조·비번역 블록은 핀 고정. 보존율 943/947(99.6%), 위험 이동 0.
        unref = (
            referenced_eids is not None
            and b["eid"] not in translations
            and b["eid"] not in referenced_eids
        )
        b["pinned"] = hits_anchor(b["off"], b["off"] + len(b["raw"])) or unref
        if b["pinned"] and b["eid"] in translations:
            excluded[b["eid"]] = "anchor_overlap"

    region = bytearray(data[:text_end])  # 앵커·pinned는 원본 그대로 유지
    layout = []
    i, n = 0, len(blocks)
    while i < n:
        if blocks[i]["pinned"]:
            b = blocks[i]
            layout.append((b["off"], len(b["raw"]), b["off"], len(b["raw"]), b["eid"]))
            i += 1
            continue
        j = i
        while j < n and not blocks[j]["pinned"]:
            j += 1
        run = blocks[i:j]
        run_start = run[0]["off"]
        run_end = blocks[j]["off"] if j < n else text_end
        reflow_run(region, run, run_start, run_end, translations, excluded, fixed, layout)
        i = j
    return bytes(region), layout


def build_scene(name, lba, size, identity, fixed):
    """한 SCN 오버레이를 번역·재배치·포인터 패치. 반환: (patched_bytes, stats_str).

    identity=True면 검증만(원본과 바이트 동일 확인, 반환 bytes=None)."""
    data = extract(lba, size)
    scn = json.load(open(os.path.join(OUT_DIR, "scn_jp", f"{name}.json"), encoding="utf-8"))
    entries = scn["entries"]
    text_end = int(scn["source"]["text_end"], 16)
    align_name = name.replace("SCN", "_SCN")  # ED1SCN1 → ED1_SCN1

    # PILOT_TEXT_IDENTITY: 폰트·포인터는 그대로 두고 대사 재삽입만 끈다(원본 SCN 텍스트).
    # 먹통 진단용 — "대사 재삽입 vs ED.EXE쪽 패치" 분할(원본 SCN + 폰트 + 나머지 패치 전부).
    text_identity = os.environ.get("PILOT_TEXT_IDENTITY") == "1"
    translations, skipped, applied = (
        ({}, {}, 0) if identity or text_identity else load_translations(align_name, name)
    )
    refs = find_refs(data, text_end)
    anchors = compute_anchors(data, text_end)

    block_offs = sorted(
        (int(e["file_offset"], 16), e["entry_id"]) for e in entries if e["kind"] != "gap"
    )
    offs_only = [o for o, _ in block_offs]

    def owner(off):
        i = bisect.bisect_right(offs_only, off) - 1
        return block_offs[i], off - block_offs[i][0]

    excluded = {}
    # 진단용 선별 제외: PILOT_EXCLUDE_EIDS="ED1SCN1:26,27,29;ED1SCN2:8" — 소프트락 이분에
    # 쓰는 임시 스위치(해당 eid는 번역 제외 = JP 유지). differential 빌드 반복이 빠르다.
    diag = os.environ.get("PILOT_EXCLUDE_EIDS")
    if diag:
        for part in diag.split(";"):
            scn_n, _, ids = part.partition(":")
            if scn_n == name and ids:
                for i in ids.split(","):
                    excluded[int(i)] = "diag"
    referenced_eids = set()  # addiu/ori(find_refs가 갱신)로 참조되는 블록 = 이동해도 안전
    for _, _, _, addr in refs:
        (_, eid), delta = owner(addr - OVERLAY_RAM_BASE)
        referenced_eids.add(eid)
        if delta and eid in translations:
            excluded[eid] = "mid_block_ref"

    # 정형 블록 dedup: size로 퇴출된 보물상자 사본은 내용이 동일한 생존 사본으로 **포인터만
    # 리타깃**한다(공간 소모 0으로 전 사본 번역 — 곶의 동굴 사본 퇴출 실측 07-26). 블록 선두
    # 참조(delta 0)만 대상 — 원본 바이트는 제자리에 남으므로 delta 참조는 그대로 안전하다.
    def compute_stock_alias():
        if fixed or identity:
            return {}
        masters, alias = {}, {}
        for s_eid, kind in STOCK_KINDS.items():
            if s_eid in translations and s_eid not in excluded:
                masters.setdefault(kind, s_eid)
        for s_eid, kind in STOCK_KINDS.items():
            if excluded.get(s_eid) == "size" and kind in masters:
                alias[s_eid] = masters[kind]
        return alias

    # 공유 lui 충돌 해소 루프
    for _ in range(5):
        region, layout = rebuild(
            entries, data, translations, excluded, anchors, text_end, fixed, referenced_eids
        )
        newoff = {eid: (no, oo) for oo, _, no, _, eid in layout}
        stock_alias = compute_stock_alias()
        lui_need, conflict = {}, None
        for addiu_off, lui_off, op, addr in refs:
            if addiu_off < text_end or lui_off < text_end:
                continue  # 텍스트 영역 내 우연 일치 — 패치 단계와 동일 필터 (오탐 충돌 방지)
            (_, eid), delta = owner(addr - OVERLAY_RAM_BASE)
            if delta == 0 and eid in stock_alias:
                eid = stock_alias[eid]
            hi, _ = hi_lo(OVERLAY_RAM_BASE + newoff[eid][0] + delta, op)
            if lui_off in lui_need and lui_need[lui_off][0] != hi:
                conflict = (eid, lui_need[lui_off][1])
                break
            lui_need[lui_off] = (hi, eid)
        if not conflict:
            break
        for eid in conflict:
            if eid in translations:
                excluded[eid] = "shared_lui_conflict"
    else:
        raise SystemExit(f"{name}: 공유 lui 충돌 미수렴")
    if stock_alias:
        print(f"  정형 블록 dedup {len(stock_alias)}건 → 생존 사본으로 리타깃")

    # ── 도너 2단계: size 퇴출 블록을 ED.EXE 도너로 이주 ──────────────────────
    # 오버레이 레이아웃(위에서 수렴 완료)은 건드리지 않는다 — 블록의 원본 JP 바이트는
    # 제자리에 남고, 참조(delta 0 — mid_block_ref는 이미 배제)만 도너 RAM 주소로 돌린다.
    # 공유 lui가 다른 블록과 얽힌 참조는 hi가 갈리므로 이주 불가(잔류).
    donor_placed = {}  # eid -> (kind, off, cand)  kind: "ext"(오버레이 꼬리) | "ed"(ED.EXE 0런)
    ext_used = 0
    ext_base = len(data)
    ext_cap = scn_extra(name, len(data)) if not identity and not fixed else 0
    if not identity and not fixed and (DONOR_RUNS or ext_cap):
        raw_by_eid = {
            e["entry_id"]: bytes.fromhex(e["raw_hex"]) for e in entries if e.get("raw_hex")
        }
        lui_owner = {}  # lui_off -> set((eid, delta0?)) — 텍스트 영역 밖 갱신 대상 참조만
        eid_refs = {}  # eid -> [(addiu_off, lui_off, op)] (delta 0)
        for addiu_off, lui_off, op, addr in refs:
            if addiu_off < text_end or lui_off < text_end:
                continue
            (_, r_eid), r_delta = owner(addr - OVERLAY_RAM_BASE)
            lui_owner.setdefault(lui_off, set()).add((r_eid, r_delta == 0))
            if r_delta == 0:
                eid_refs.setdefault(r_eid, []).append((addiu_off, lui_off, op))
        cands = []
        # mid_block_ref도 이주 가능(07-26): 원본 JP 바이트가 오버레이 제자리에 남으므로
        # 내부(delta) 참조는 그대로 유효하고, 선두(delta 0) 참조만 도너 번역본으로 돌린다.
        # (jp59 실측 — 꼬리 4B를 가리키는 내부 참조 때문에 영구 JP로 남던 블록의 해법)
        for eid, reason in excluded.items():
            if reason not in ("size", "mid_block_ref") or eid in stock_alias:
                continue
            t = translations.get(eid)
            if not t or t[0] is STOCK or eid not in eid_refs:
                continue
            cand, fail = build_candidate(raw_by_eid[eid], t, eid)
            if cand is not None:
                cands.append((eid, cand, reason))
        # mid_block_ref 우선(도너 말곤 구제 불가·희소) → 그다음 큰 블록 우선 —
        # 장문 스토리 대사(라우엘 연설류)가 QA 체감의 최전선
        for eid, cand, _r in sorted(cands, key=lambda x: (x[2] != "mid_block_ref", -len(x[1]))):
            # 이 블록 선두 참조들의 lui가 "이 블록 delta0 참조"만 섬겨야 한다 — 같은 블록의
            # 내부(delta) 참조와 공유돼도 hi가 갈린다(이주지 vs 오버레이 본문).
            if any(lui_owner[lo_] != {(eid, True)} for _, lo_, _ in eid_refs[eid]):
                continue  # 공유 lui — hi 충돌 위험
            sz4 = len(cand) + (-len(cand) % 4)
            if ext_used + sz4 <= ext_cap:  # 씬 전용 확장 영역 우선(용량 큼)
                donor_placed[eid] = ("ext", ext_base + ext_used, cand)
                ext_used += sz4
            else:
                off = donor_alloc(len(cand))
                if off is None:
                    continue  # 풀 고갈(더 작은 블록은 들어갈 수 있으니 계속)
                donor_placed[eid] = ("ed", off, cand)
            del excluded[eid]

    # 이름 헤더 스텁: 헤더 사본 블록 + MIPS 스텁을 확장 영역에 배치(콜사이트 교체는 아래
    # 포인터 패치 뒤 — 같은 워드를 ref 패처가 만지므로 마지막에 덮어써야 한다)
    ext_custom = []  # (ext 내 오프셋, bytes)
    stub_patches = []  # (call_off, [words])
    if not identity and not fixed:
        for (scn, eid), cfg in NAME_STUBS.items():
            if scn != name:
                continue
            t = translations.get(eid)
            if not t or eid in excluded or t[0] in (STOCK, NAMEONLY):
                continue
            try:
                blk = build_block(t[0], t[1], header=True, hdr_fmt=True)
            except SkipBlock:
                print(f"  경고: jp{eid} 이름 스텁 — 헤더 블록 조판 실패, 미적용")
                continue
            if blk.count(MC) != 3 or blk.count(PS) != 1:
                # 스텁 인자열(2·이름·1·8)과 %c/%s 소비가 정확히 맞아야 한다 — 본문이 다창으로
                # 쪼개지면(%c 초과) 인자가 밀리므로 포기(원판 그대로 이름 없이 표시)
                print(f"  경고: jp{eid} 이름 스텁 — 구조 불일치(mc={blk.count(MC)}), 미적용")
                continue
            need = len(blk) + (-len(blk) % 4) + 14 * 4
            if ext_used + need > ext_cap:
                print(f"  경고: jp{eid} 이름 스텁 — 확장 공간 부족, 미적용")
                continue
            blk_off = ext_base + ext_used
            ext_used += len(blk) + (-len(blk) % 4)
            stub_off = ext_base + ext_used
            ext_used += 14 * 4
            blk_addr = OVERLAY_RAM_BASE + blk_off
            lo = blk_addr & 0xFFFF
            hi = ((blk_addr >> 16) + (1 if lo >= 0x8000 else 0)) & 0xFFFF
            np_ = cfg["name_ptr"]
            words = [
                0x02002021,  # move a0, s0 (원본 진입점 1워드 재현)
                0x3C050000 | hi,  # lui   a1, hi(헤더 블록)
                0x24A50000 | lo,  # addiu a1, a1, lo
                0x24060002,  # addiu a2, zero, 2   (%c: 이름색 ON)
                0x3C070000 | (np_ >> 16),  # lui   a3, hi(이름 버퍼)
                0x24E70000 | (np_ & 0xFFFF),  # addiu a3, a3, lo    (%s)
                0x24020001,  # addiu v0, zero, 1   (%c: 색 OFF)
                0xAFA20010,  # sw    v0, 0x10(sp)
                0x24020008,  # addiu v0, zero, 8   (%c: 창 종단)
                0xAFA20014,  # sw    v0, 0x14(sp)
                0x0C000000 | ((cfg["sprintf"] >> 2) & 0x3FFFFFF),  # jal sprintf
                0,  # nop (delay)
                0x08000000 | ((cfg["resume"] >> 2) & 0x3FFFFFF),  # j resume(flush)
                0,  # nop (delay)
            ]
            ext_custom.append((blk_off - ext_base, blk))
            ext_custom.append(
                (stub_off - ext_base, b"".join(w.to_bytes(4, "little") for w in words))
            )
            stub_addr = OVERLAY_RAM_BASE + stub_off
            stub_patches.append((cfg["call_off"], [0x08000000 | ((stub_addr >> 2) & 0x3FFFFFF), 0]))
            print(
                f"  이름 스텁: jp{eid} — 헤더 사본@ext+0x{blk_off - ext_base:X}, 진입점 0x{cfg['call_off']:X} 후킹"
            )

    # 파일 재조립 + 포인터 패치 (코드 영역만). 확장 영역은 파일 꼬리에 덧붙인다.
    out_file = bytearray(data)
    out_file[:text_end] = region
    if ext_used:
        ext_blob = bytearray(ext_used)
        for kind, off, cand in donor_placed.values():
            if kind == "ext":
                ext_blob[off - ext_base : off - ext_base + len(cand)] = cand
        for rel, bs in ext_custom:
            ext_blob[rel : rel + len(bs)] = bs
        out_file += ext_blob
        assert OVERLAY_RAM_BASE + len(out_file) <= OVERLAY_RAM_LIMIT, f"{name} 확장 RAM 상한 초과"
    patched = 0
    for addiu_off, lui_off, op, addr in refs:
        if addiu_off < text_end or lui_off < text_end:
            continue  # 텍스트 영역 내 우연 일치는 패치 대상 아님
        (_, eid), delta = owner(addr - OVERLAY_RAM_BASE)
        if delta == 0 and eid in stock_alias:
            eid = stock_alias[eid]
        if delta == 0 and eid in donor_placed:
            kind, off, _c = donor_placed[eid]
            new_addr = (OVERLAY_RAM_BASE + off) if kind == "ext" else (off + ED_EXE_RAM)
        else:
            new_addr = OVERLAY_RAM_BASE + newoff[eid][0] + delta
        if fixed:
            assert new_addr == addr, f"{name} fixed 모드에서 주소 이동: {addr:#x}→{new_addr:#x}"
            continue
        hi, lo = hi_lo(new_addr, op)
        patch_word_imm(out_file, lui_off, hi)
        patch_word_imm(out_file, addiu_off, lo)
        patched += 1

    # 주입 %c쌍 블록의 콜사이트 인자 패치(0x83/0x5C→공백) — 번역이 실제로 들어갈 때만.
    # 블록이 제외돼 JP가 남으면 원본 인자를 보존해야 ソ가 그대로 나온다.
    for (scn, eid), patches in SCN_ARG_PATCHES.items():
        if scn == name and eid in translations and eid not in excluded:
            for off, word in patches:
                out_file[off : off + 4] = word.to_bytes(4, "little")

    # 이름 스텁 콜사이트 교체 — ref 패처가 같은 워드(lui)를 만진 뒤에 덮어써야 한다.
    # 교체 다음의 죽은 lui/addiu 워드(j가 건너뜀)는 ref 패치 잔해가 남아도 무해.
    for call_off, words in stub_patches:
        for i, w in enumerate(words):
            out_file[call_off + 4 * i : call_off + 4 * i + 4] = w.to_bytes(4, "little")

    if identity:
        assert bytes(out_file) == data, f"{name}: 아이덴티티 라운드트립 실패"
        return None, f"{name}: 라운드트립 OK (포인터 {patched}건 = 원본 동일)", {}

    n_tr = sum(1 for _, _, _, _, eid in layout if eid in translations and eid not in excluded)
    used = sum(nl for _, _, _, nl, _ in layout)
    parse_skip = f", 파싱제외 {sum(skipped.values())}" if skipped else ""
    ov = f", 검수교정 {applied}" if applied else ""
    n_ext = sum(1 for k, _, _ in donor_placed.values() if k == "ext")
    n_ed = len(donor_placed) - n_ext
    donor_s = ""
    if donor_placed:
        donor_s = f", 이주 {len(donor_placed)}블록(확장 {n_ext}·ED도너 {n_ed})"
    if ext_used:
        donor_s += f", 파일 +{len(out_file) - len(data)}B"
    stats = (
        f"{name}: 재삽입 {n_tr}블록 (후보 {len(translations)}, 제외 {len(excluded)}"
        f"{sorted(set(excluded.values()))}{parse_skip}{ov}{donor_s}, 포인터 {patched}건, "
        f"사용 0x{used:X}/0x{text_end:X})"
    )
    return out_file, stats, {off: cand for k, off, cand in donor_placed.values() if k == "ed"}


def main():
    identity = os.environ.get("PILOT_IDENTITY") == "1"  # 번역 0건 라운드트립 검증 모드
    fixed = os.environ.get("PILOT_FIXED") == "1"  # 길이 고정 모드 (블록 무이동 — 포인터 격리)
    only = os.environ.get("PILOT_SCN")  # 특정 씬만 (예: ED1SCN1). 미지정=전 씬
    if not os.path.exists(SRC):
        raise SystemExit(
            "원본 이미지 없음 — originals/ps1-eiyuu12/에 .bin/.cue를 복사한 뒤 재실행\n"
            f"  기대 경로: {os.path.relpath(SRC, os.path.dirname(OUT_DIR))}"
        )
    scenes = [s for s in SCN_FILES if not only or s[0] == only]
    if not scenes:
        raise SystemExit(f"PILOT_SCN={only} 는 SCN_FILES에 없음")

    built = {}  # lba → patched bytes
    donor_all = {}  # ED.EXE file off → bytes (전 씬 공용 풀)
    layout_manifest = {}  # name → {lba, size} (재배치 반영 — 하류 도구용)
    dir_moves = []  # (파일명;1, new_lba, new_size)
    dummy_cursor = DUMMY_LBA
    donor_reset()
    total_tr = 0
    for name, lba, size in scenes:
        out_file, stats, donor = build_scene(name, lba, size, identity, fixed)
        print(stats)
        if out_file is not None:
            if len(out_file) > size:
                # 확장 → DUMMY 영역으로 재배치(원본 섹터에 안 들어감). 디렉토리 레코드 패치.
                new_lba = dummy_cursor
                dummy_cursor += (len(out_file) + 2047) // 2048
                dir_moves.append((f"{name}.BIN;1", new_lba, len(out_file)))
                built[new_lba] = out_file
                layout_manifest[name] = {"lba": new_lba, "size": len(out_file)}
                print(f"  {name}: {size}→{len(out_file)}B, LBA {lba}→{new_lba} (DUMMY 재배치)")
            else:
                built[lba] = out_file
                layout_manifest[name] = {"lba": lba, "size": size}
            total_tr += int(stats.split("재삽입 ")[1].split("블록")[0])
        donor_all.update(donor)
    if identity:
        print("전 씬 아이덴티티 라운드트립 OK")
        return
    print(f"\n총 재삽입 {total_tr}블록 ({len(built)}씬)")
    if donor_all:
        cap = sum(hi - lo for lo, hi in DONOR_RUNS)
        used_d = sum(len(c) + (-len(c) % 4) for c in donor_all.values())
        print(f"도너 사용 {used_d}/{cap}B ({len(donor_all)}블록)")

    # 폰트 + 이미지 기록 (전 씬 + ED.EXE 폰트를 한 이미지에)
    import hangul_font  # numpy/PIL 의존 — 빌드 단계에서만 필요

    print("Galmuri11 폰트 변환·탑재 중...")
    glyphs = hangul_font.convert_chars(hangul_map.SYLLABLES)
    font_block = b"".join(glyphs[ch] for ch in hangul_map.SYLLABLES)
    base_off = hangul_map.slot_ed_offset(0)

    suffix = " Fixed" if fixed else ""
    dst = DST.replace("Pilot", "Pilot" + suffix) if fixed else DST
    dst_cue = DST_CUE.replace("Pilot", "Pilot" + suffix) if fixed else DST_CUE
    os.makedirs(WORK_DIR, exist_ok=True)
    shutil.copyfile(SRC, dst)
    with open(dst, "r+b") as f:
        ed = bytearray(extract(ED_LBA, ED_SIZE))
        ed[base_off : base_off + len(font_block)] = font_block
        # 도너 블록 기록 — 대상 구간이 원본에서 0인지 확인(다른 패치와의 충돌 가드)
        for off, cand in sorted(donor_all.items()):
            assert all(b == 0 for b in ed[off : off + len(cand)]), (
                f"도너 구간 비어있지 않음 @0x{off:X}"
            )
            ed[off : off + len(cand)] = cand
        if donor_all:
            print(f"도너 블록 {len(donor_all)}개 → ED.EXE 0런")
        print(f"ED.EXE: 섹터 {write_user_data(f, ED_LBA, ed)}개 수정 (폰트+도너)")
        for lba, out_file in built.items():
            print(f"  LBA {lba}: 섹터 {write_user_data(f, lba, out_file)}개 수정")
        # 재배치된 씬의 BIN 디렉토리 레코드 패치(LBA·size, 양 엔디언) — 엔진은 ISO 경로로
        # 로드하므로 이거면 커진 파일을 그대로 읽는다(ED.EXE 0xC3F4~ 경로 문자열 실증).
        if dir_moves:
            bdir = bytearray(extract(BIN_DIR_LBA, 2048, path=dst))
            for fname, new_lba, new_size in dir_moves:
                want = fname.encode("ascii")
                i, hit = 0, False
                while i < len(bdir) and bdir[i]:
                    nlen = bdir[i + 32]
                    if bdir[i + 33 : i + 33 + nlen] == want:
                        bdir[i + 2 : i + 6] = new_lba.to_bytes(4, "little")
                        bdir[i + 6 : i + 10] = new_lba.to_bytes(4, "big")
                        bdir[i + 10 : i + 14] = new_size.to_bytes(4, "little")
                        bdir[i + 14 : i + 18] = new_size.to_bytes(4, "big")
                        hit = True
                        break
                    i += bdir[i]
                assert hit, f"BIN 디렉토리에 {fname} 없음"
                print(f"  디렉토리 갱신: {fname} → LBA {new_lba}, {new_size}B")
            write_user_data(f, BIN_DIR_LBA, bdir)
    json.dump(
        layout_manifest,
        open(os.path.join(OUT_DIR, "scn_layout.json"), "w", encoding="utf-8"),
        indent=1,
    )
    write_cue(dst_cue, os.path.basename(dst))
    print(f"완료:\n  {dst}\n  {dst_cue}")


if __name__ == "__main__":
    main()
