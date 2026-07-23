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
        elif ch in HALF_PUNCT:  # 반각 부호 실험 — 공백과 같은 1바이트 경로
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


def _break_fixes():
    """사람이 확정한 어절 중간 분리 예외(dos_break_fixes.json) — 자동 판정 보정."""
    global _BREAK_FIXES
    if _BREAK_FIXES is None:
        path = os.path.join(os.path.dirname(OUT_DIR), "dos_break_fixes.json")
        try:
            doc = json.load(open(path, encoding="utf-8"))
            _BREAK_FIXES = {tuple(p) for p in doc.get("join", [])}
        except FileNotFoundError:
            _BREAK_FIXES = set()
    return _BREAK_FIXES


def resolve_dos_breaks(t):
    """{n}을 공백 또는 붙임으로 확정한다(정발 표시 줄바꿈 제거)."""
    vocab = _dos_vocab()
    fixes = _break_fixes()
    parts = t.split("{n}")
    out = parts[0]
    for nxt in parts[1:]:
        pa, pb = out.split(), nxt.split()
        a = pa[-1].strip(_TOK_STRIP) if pa else ""
        b = pb[0].strip(_TOK_STRIP) if pb else ""
        # 합친 형태가 어절 사전에 있거나, 뒤 조각이 **어절 첫머리에 올 수 없는 어미**면
        # 어절 중간 분리 → 공백 없이 붙인다("말아주시옵"+"소서"는 합친 형태가 코퍼스에
        # 없어 사전만으론 못 잡는다). 그 외는 어절 경계로 보고 공백(실측 다수).
        join = a and b and ((a + b) in vocab or b in _ENDING_FRAGS or (a, b) in fixes)
        out += ("" if join else " ") + nxt
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
def parse_kr(entry):
    t = entry["text"]
    t = re.sub(r"^.*?\{/spk\}", "", t, count=1)  # 화자 마크업(+선행 opcode 노이즈) 제거
    t = resolve_dos_breaks(t).replace("{end}", "")  # 정발 표시 줄바꿈 해소(위 주석)
    # \xNN 제어코드(프롬프트 대기 등)는 공백으로 — 무공백 제거 시 앞뒤 발화가 붙음
    # ("합니다\x07또 들러주십시요"). ⚠ \x03 두 곳은 인라인 플레이스홀더 의심(QA 메모).
    t = t.replace("\\x09", NAME_SENT)  # 이름 주입 자리 보존(아래 일괄 치환보다 먼저)
    t = re.sub(r"\\x[0-9A-F]{2}", " ", t)
    # 병합으로 들어온 인라인 화자({spk}X{/spk})는 페이지 헤더로 보존 — JP의 %c화자%c 재현
    t = re.sub(r"\{spk\}(.*?)\{/spk\}", "\x11\\1\x12", t)
    # 짝 안 맞는 고아 {spk}/{/spk}(DOS 추출기 마크업 잔여, ED1 122블록)는 제거 —
    # 안 지우면 "을 장비하였습니다.{/spk}"처럼 태그가 화면에 글자로 새어나온다(T_001 아이템 장비 실측).
    t = t.replace("{spk}", " ").replace("{/spk}", " ")
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
        seg = seg[m.start() :] if m.start() < 4 else seg  # 선두 opcode 잔여 노이즈 절삭
        pages.append((inline_spk, seg))
    if not pages:
        raise SkipBlock("본문 없음")
    return entry["speaker"], pages


# 반각(1바이트) 부호(2026-07-19 인게임 확정): .,!?는 공백과 같은 1바이트 경로로 내보내
# 0.5슬롯 렌더 — 대사 렌더러의 1바이트 글리프 지원 스크린샷 검증. 이에 따라 전각 잉크
# 여백이 사라져 "부호 뒤 공백 제거" 조판 규칙은 폐지(공백 유지가 자연스러움 — 유저 판정).
HALF_PUNCT = ".,!?"


def cell_w(ch):
    """엔진 슬롯 폭 — encode_ext와 1:1 (1바이트=0.5, 2바이트 전각=1)."""
    if ch == NAME_SENT:
        return NAME_SLOTS  # %s는 런타임 이름 — 평균 길이로 근사
    return 0.5 if ch == " " or ch in HALF_PUNCT else 1.0


def wrap_page(text, width=WRAP, target=None, max_lines=None):
    """공통 줄바꿈 유틸(shared/text/krwrap.wrap_pages): 원문 {n} 줄바꿈을 존중하고
    폭(WRAP) 넘는 줄만 재줄바꿈 + 금칙 + 짧은조각 병합, 창(3줄)은 문장 그룹 단위로
    packing해 문장이 창 경계에 반반 걸리지 않게 한다(3줄 초과 문장만 재줄바꿈).
    부호 정리(07-19 갱신): 부호 앞 공백만 제거, 뒤 공백은 유지 — 반각 부호 전환으로
    "온점·쉼표 뒤 공백 제거" 규칙 폐지. 줄바꿈 v2 + 반각 부호 인게임 검증 완료."""
    return kr_wrap_pages(
        text,
        width,
        max_lines or LINES_PER_PAGE,
        target_pages=target,  # 창 수 계약: 지정 시 정확히 target개 창으로 분배
        break_char="\n",
        cell_width=cell_w,
        strip_before=".,!?",
        strip_after="",  # 부호 뒤 공백 유지 — 반각 부호 전환으로 공백 제거 규칙 폐지(07-19, 유저 판정)
    )


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


def reflow_run(region, run, run_start, run_end, translations, excluded, fixed, layout):
    """자유 구간 [run_start, run_end)(앵커 사이)에 자유 블록들을 재배치.

    총량이 구간 크기를 넘으면 성장폭 큰 번역부터 제외(size). fixed=True면
    블록별 원본 길이 고정(짧으면 00패딩). 남는 공간은 00패딩 — 앵커 위치 불변."""
    run_space = run_end - run_start
    news = []
    for b in run:
        new, eid = b["raw"], b["eid"]
        if eid in translations and eid not in excluded:
            try:
                cand = build_block(*translations[eid])
            except SkipBlock:
                excluded[eid] = "encode"
                cand = None
            # 창 수 계약: 엔진은 블록당 %c 세그먼트를 **원본 수만큼** 읽는다. KR이 원본보다
            # 적으면 종단을 못 만나고 뒤 데이터까지 읽어 깨진 글자를 뿌리며 무한 대기(소프트락)
            # — 1장 탈출→월드맵 먹통의 증상. 초과는 꼬리 잘림(표시 손실)이라 허용, 부족만 제외.
            # 제어 시퀀스 계약: 원본의 연속 %c 런(화자 헤더·페이지/색 전환)은 우리가 재현하는
            # 인라인 헤더 수만큼만 감당한다. 그보다 많으면 텍스트를 N조각으로 강제 분할하면서
            # 제어 인자가 밀려 **대사가 엉뚱하게 쪼개지고 색이 문장 중간에서 바뀐다**(eid 27 실측).
            # 원본 구조를 그대로 채우는 재설계 전까지는 그런 블록을 번역에서 제외한다.
            if cand is not None:
                n_runs = jp_ctrl_runs(b["raw"])
                _, inline_fmt = jp_inline_fmt_windows(b["raw"])
                # ⚠ 비교 대상은 인라인 헤더 "총개수"가 아니라 **우리가 실제로 방출하는 %s 헤더 수**다.
                # 리터럴 이름 헤더(%c퍼거슨%c)는 재현하지 못하므로 총개수와 비교하면 그냥 통과해
                # 텍스트가 엉뚱하게 쪼개진다(eid 23 실측: 왕자님|부탁이라, 지는|머든지).
                if n_runs > len(inline_fmt):
                    excluded[eid] = "ctrl_seq"
                    cand = None
            if cand is not None and cand.count(MC) < b["raw"].count(MC):
                excluded[eid] = "window_deficit"
                cand = None
            # %s·%d 계약: 서식 지정자는 흐름 제어(런타임 이름/수치 주입) — 재조립본에서 줄면
            # 엔진의 인자 소비가 어긋난다. 현 조판은 인라인 화자(%c%s%c)를 보존하지 못하므로
            # (build_block이 첫 화자만 방출) 누락 블록은 번역 제외(JP 유지). 근본 해결은
            # %s 바이트 방출 + 인라인 화자 헤더 보존(HANDOFF "후속(대사 구조)" 항목).
            if cand is not None and (
                cand.count(b"\x25\x73") < b["raw"].count(b"\x25\x73")
                or cand.count(b"\x25\x64") < b["raw"].count(b"\x25\x64")
            ):
                excluded[eid] = "fmt_drop"
                cand = None
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
            k = max(cands, key=lambda k: len(news[k]) - len(run[k]["raw"]))
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
    align = json.load(open(os.path.join(OUT_DIR, "align", f"{align_name}.json"), encoding="utf-8"))
    jp_doc = json.load(open(os.path.join(OUT_DIR, "scn_jp", f"{scn_name}.json"), encoding="utf-8"))
    # 창 수 계약의 단위는 엔진이 실제로 세는 **raw %c 개수**다(인라인 화자 헤더의 %c 포함).
    # 우리 블록의 %c = parts + 2(화자헤더 2 + 종단 1 - join 1)이므로 target = jp_mc - 2로 잡으면
    # 재조립본의 %c 총수가 원본과 정확히 일치한다. (jp_windows()는 의미상 창 수라 병합 상한용.)
    jp_win = {}
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
    kr_cache = {}

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
            if not spk:
                raise SkipBlock("화자 없음")
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
    for jp_id_str, ov in _load_overrides().get(scn_name, {}).items():
        if jp_id_str.startswith("_"):
            continue
        entry = dict(kr_entry(ov["table"], ov["entry_id"]))
        entry, _ = splice_placeholder_pages(
            entry, ov["table"], kr_entry, target=jp_win.get(int(jp_id_str), (None,))[0]
        )
        entry["speaker"] = ov.get("speaker") or entry.get("speaker")
        try:
            spk, pages = parse_kr(entry)
            final_spk = ov.get("speaker") or spk
            if not final_spk:  # 메인 경로와 동일 가드 — 화자 없는 블록은 대사로 승격 불가
                raise SkipBlock("화자 없음")
            out[int(jp_id_str)] = (final_spk, pages) + jp_win.get(
                int(jp_id_str), (None, True, False, set())
            )
            applied += 1
        except SkipBlock as e:
            # 사람이 지정한 교정이 조용히 사라지면 안 된다 — 반드시 보고
            print(f"경고: {scn_name} 오버라이드 jp={jp_id_str} 적용 실패 ({e}) — 수정 필요")
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

    # 공유 lui 충돌 해소 루프
    for _ in range(5):
        region, layout = rebuild(
            entries, data, translations, excluded, anchors, text_end, fixed, referenced_eids
        )
        newoff = {eid: (no, oo) for oo, _, no, _, eid in layout}
        lui_need, conflict = {}, None
        for addiu_off, lui_off, op, addr in refs:
            if addiu_off < text_end or lui_off < text_end:
                continue  # 텍스트 영역 내 우연 일치 — 패치 단계와 동일 필터 (오탐 충돌 방지)
            (_, eid), delta = owner(addr - OVERLAY_RAM_BASE)
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

    # 파일 재조립 + 포인터 패치 (코드 영역만)
    out_file = bytearray(data)
    out_file[:text_end] = region
    patched = 0
    for addiu_off, lui_off, op, addr in refs:
        if addiu_off < text_end or lui_off < text_end:
            continue  # 텍스트 영역 내 우연 일치는 패치 대상 아님
        (_, eid), delta = owner(addr - OVERLAY_RAM_BASE)
        new_addr = OVERLAY_RAM_BASE + newoff[eid][0] + delta
        if fixed:
            assert new_addr == addr, f"{name} fixed 모드에서 주소 이동: {addr:#x}→{new_addr:#x}"
            continue
        hi, lo = hi_lo(new_addr, op)
        patch_word_imm(out_file, lui_off, hi)
        patch_word_imm(out_file, addiu_off, lo)
        patched += 1

    if identity:
        assert bytes(out_file) == data, f"{name}: 아이덴티티 라운드트립 실패"
        return None, f"{name}: 라운드트립 OK (포인터 {patched}건 = 원본 동일)"

    n_tr = sum(1 for _, _, _, _, eid in layout if eid in translations and eid not in excluded)
    used = sum(nl for _, _, _, nl, _ in layout)
    parse_skip = f", 파싱제외 {sum(skipped.values())}" if skipped else ""
    ov = f", 검수교정 {applied}" if applied else ""
    stats = (
        f"{name}: 재삽입 {n_tr}블록 (후보 {len(translations)}, 제외 {len(excluded)}"
        f"{sorted(set(excluded.values()))}{parse_skip}{ov}, 포인터 {patched}건, "
        f"사용 0x{used:X}/0x{text_end:X})"
    )
    return out_file, stats


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
    total_tr = 0
    for name, lba, size in scenes:
        out_file, stats = build_scene(name, lba, size, identity, fixed)
        print(stats)
        if out_file is not None:
            built[lba] = out_file
            total_tr += int(stats.split("재삽입 ")[1].split("블록")[0])
    if identity:
        print("전 씬 아이덴티티 라운드트립 OK")
        return
    print(f"\n총 재삽입 {total_tr}블록 ({len(built)}씬)")

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
        print(f"ED.EXE: 섹터 {write_user_data(f, ED_LBA, ed)}개 수정 (폰트)")
        for lba, out_file in built.items():
            print(f"  LBA {lba}: 섹터 {write_user_data(f, lba, out_file)}개 수정")
    write_cue(dst_cue, os.path.basename(dst))
    print(f"완료:\n  {dst}\n  {dst_cue}")


if __name__ == "__main__":
    main()
