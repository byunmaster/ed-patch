"""씬 블록 안의 **메시지**(번역 단위) — 파싱 · 열쇠 · 검토 덤프 · 재삽입.

메시지 = 인터프리터(`$6712`, status.md 3절)가 한 번에 읽는 「열개 → 종료」 구간.
    열개  = `1F 화자 04` · `09 nn`(공용 화자) · 그냥 첫 글자
    본문  = 2바이트 글자 + 텍스트쪽 옵코드(01 줄 · 03/05 페이지 · 04 · 19~20 모드)
    종료  = 00 · 06 · 07
그 밖의 옵코드(0F 점프 · 10 호출 · 11/12 조건 …)가 본문에 끼면 그 앞에서 끊고 `complex` 로 표시한다 —
v0 는 단순 메시지만 번역한다.

🔴 **재삽입은 자리를 안 옮긴다.** 블록 안 포인터(엔티티 표 · 0F/10 피연산자 · 코드의 절대주소)를 다
못 세우므로, 새 바이트는 **원래 메시지 자리에** 쓰고 넘치면 `0F lo hi`(3B) 로 **블록 끝**의 이어쓰기
영역으로 넘긴다. 어떤 기존 주소도 안 바뀐다. 블록은 뱅크 하나(8KB)를 못 넘는다(build.assemble 이 잰다).
⚠ 메시지 **안쪽**을 가리키는 16비트 값이 블록에 있으면 `pinned` — 건드리지 않는다(게이트).

열쇠는 `shared/text/line_key.key`(JP 원문 sha1 앞 16자) — PS1 사전과 같은 열쇠라 문안이 넘어온다.
JP 원문은 `work/derived/messages/` 에만 쓴다(커밋 안 함, 루트 「저작권」).
"""

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import common
from text.line_key import key as jp_key

BASE = 0xA000  # 씬 블록의 논리 주소(인터프리터가 읽는 창)
TERM = {0x00, 0x06, 0x07}
TEXT_OPS = {
    0x01: 1,
    0x03: 1,
    0x04: 1,
    0x05: 1,
    0x1F: 1,
    **{op: 1 for op in range(0x19, 0x21)},
    0x09: 2,
}
OTHER_OPS = {
    0x02: 1,
    0x0D: 1,
    0x0F: 3,
    0x10: 3,
    0x11: 3,
    0x12: 3,
    0x13: 3,
    0x14: 3,
    0x15: 3,
    0x17: 1,
    0x21: 2,
    0x23: 3,
}
JUMP = 0x0F
SJIS_RUN = re.compile(rb"(?:[\x81-\x9f\xe0-\xea][\x40-\xfc]){2,}")
KANA = re.compile(r"[ぁ-んァ-ヶー、。！？]")


def is_lead(b: int) -> bool:
    return b >= 0x24


BRANCH_OPS = frozenset(range(0x0F, 0x16))
"""주소 2바이트를 데리고 다니는 씬 옵코드(0F 점프 · 10 호출 · 11/12 조건 · 13/14 플래그 · 15 기계어) —
`battle.BRANCH_OPS` 와 같은 축. 🔴 **주소 바이트가 유효한 전각 코드면 메시지 머리로 딸려 들어온다**
(devlog 09-07 ③, 씬 6,001 메시지 중 86곳 실측). 거기서 메시지를 열고 번역을 써 넣으면 그 점프가
쓰레기 주소로 가서 **화면이 아니라 진행이 깨진다**(pc98 이 같은 자리에서 물렸다)."""


def branch_operands(block: bytes) -> set[int]:
    """분기 옵코드의 주소 바이트 자리. **주소가 이 블록 안을 가리킬 때만** 센다(`battle.branch_operands`
    와 같은 두 축 — 옵코드인가 + 주소가 블록 안인가. 둘째가 없으면 데이터 `0F`를 통째로 오탐한다)."""
    out = set()
    for i, c in enumerate(block[: len(block) - 2]):
        if c not in BRANCH_OPS:
            continue
        tgt = block[i + 1] | (block[i + 2] << 8)
        if BASE <= tgt < BASE + len(block):
            out.add(i + 1)
            out.add(i + 2)
    return out


@dataclass
class Message:
    start: int
    end: int  # 종료 바이트 포함(exclusive index)
    speaker: str | None
    common: int | None  # 09 nn
    tokens: list  # str(글자들) | ("op", int)
    complex: bool = False
    pinned: bool = False
    terminated: bool = (
        True  # 자기 종료 바이트로 끝나나(아니면 재삽입 때 `0F` 로 다음 자리에 잇는다)
    )
    refs: list = field(default_factory=list)

    @property
    def jp(self) -> str:
        out = []
        for t in self.tokens:
            if isinstance(t, str):
                out.append(t)
            elif t[1] == 0x01:
                out.append("\n")
            elif t[1] in (0x03, 0x05):
                out.append("\f")
        return "".join(out)

    @property
    def key(self) -> str:
        sp = self.speaker or (f"@{self.common}" if self.common is not None else "")
        return jp_key("{c}" + sp + "{c}" + self.jp.replace("\f", ""))


def _decode_pair(b: bytes) -> str:
    try:
        return b.decode("cp932")
    except UnicodeDecodeError:
        return f"[{b.hex()}]"


_KNOWN: frozenset[str] | None = None


def _known_speakers() -> frozenset[str]:
    """정본에 이름이 있는 화자(SJIS 원문 쪽). 짧은 순한자 화자를 필터에서 지킨다."""
    global _KNOWN
    if _KNOWN is None:
        try:
            _KNOWN = frozenset(json.loads(SPEAKERS.read_text()))
        except (OSError, ValueError):
            _KNOWN = frozenset()
    return _KNOWN


class _Run:
    """`SJIS_RUN` 매치처럼 쓰는 런 — 피연산자를 뗀 뒤의 구간."""

    def __init__(self, a: int, b: int, block: bytes):
        self._a, self._b, self._blk = a, b, block

    def start(self) -> int:
        return self._a

    def group(self) -> bytes:
        return self._blk[self._a : self._b]


def _runs(block: bytes, operands: set[int], min_chars: int = 2):
    """대본 런(오프셋 구간) — 분기 주소 바이트(피연산자)를 뺀다.

    🔴 분기 옵코드(`0F lo hi`)의 피연산자가 우연히 유효한 전각 코드면 **바로 뒤 대본과 한 런으로 붙는다**(`0F E9 A0` + 「強情な…」).
    예전엔 런의 첫 글자가 피연산자와 겹치면 런 **통째로** 버려서, 점프 바로 뒤에 오는 대본이 목록에서 사라져 화면에
    일본어로 남았다(scn095 「強情な奴だな！！」 등 10-18, `check_ptr_targets`). 이제 피연산자 두 바이트만 떼고 나머지를 런으로 본다.
    """
    for m in SJIS_RUN.finditer(block):
        a, b = m.start(), m.end()
        while a < b and (a in operands or a + 1 in operands):
            a += 2 if a in operands else b - a  # 피연산자 자리면 2B 떼고, 한 칸 어긋난 겹침이면 런을 버린다
        if (b - a) // 2 >= min_chars:
            yield a, b


def parse(block: bytes) -> list[Message]:
    """열개 후보(화자 머리 `1F` · 공용 화자 `09 nn` · 대본 런)를 앞에서부터 파싱한다."""
    cands = set()
    known = _known_speakers()
    operands = branch_operands(block)  # 분기 주소 바이트 — 메시지 머리로 안 삼는다(devlog 09-07 ③)
    for rs, re_ in _runs(block, operands):
        m = _Run(rs, re_, block)
        # 코드 안의 우연한 한자 두 글자를 거른다 — 셋 이상이거나 가나·부호가 있어야 대본이다
        # 🔴 단 **정본에 있는 화자 이름은 안 버린다.** 순한자 두 글자 화자(「兵士」 등)가 `1F` 없이
        #    서면 이 필터가 통째로 먹는다 — 검사기는 **자기 입력 밖을 못 보므로** 안 운다
        #    (pc98 이 같은 필터로 「呪文」·「装備」를 잃었다, 중계 2026-09-07).
        #    실측: 버려지는 1,595자리 중 `1F` 경로가 624를 건지고, **진짜 손실은 「兵士」 6자리**였다.
        txt = m.group().decode("cp932", "replace")
        if len(m.group()) < 6 and not KANA.search(txt) and txt not in known:
            continue
        cands.add(m.start())
    runs = {rs for rs, _re in _runs(block, operands, min_chars=1)}  # 길이 불문 런(화자 이름은 한두 글자다) — 여기서도 피연산자를 뺀다
    for i in range(len(block) - 3):
        if i in operands:  # 분기 주소 자리에서 화자·공용 머리를 열지 않는다
            continue
        # 화자 머리: 1F + 이름(SJIS 런) + 04, 이름은 14B 이내
        if block[i] == 0x1F and (i + 1) in runs and 0x04 in block[i + 2 : i + 16]:
            cands.add(i)
        # 공용 화자: 09 nn(nn 작다) 뒤에 01+대본 런 또는 대본 런. ⚠ 09 는 6502 ORA # 이기도 하다
        if block[i] == 0x09 and block[i + 1] < 0x40:
            nxt = i + 3 if block[i + 2] == 0x01 else i + 2
            if nxt in cands:
                cands.add(i)
    msgs: list[Message] = []
    covered = 0
    for s in sorted(cands):
        if s < covered:
            continue
        s = _skip_table_tail(block, s, cands)
        msg = _parse_from(block, s)
        if msg is None or not any(isinstance(t, str) for t in msg.tokens) and msg.speaker is None:
            continue
        msgs.append(msg)
        covered = msg.end
    return _split_pinned(block, msgs)


def _word(block: bytes, i: int) -> int | None:
    """i 의 16비트 값이 이 블록 안을 가리키는 주소면 그 오프셋(주소 − BASE), 아니면 None."""
    if i < 0 or i + 1 >= len(block):
        return None
    w = (block[i] | block[i + 1] << 8) - BASE
    return w if 0 <= w < len(block) else None


def _skip_table_tail(block: bytes, s: int, starts: set[int]) -> int:
    """**오름차순 주소 표**(연속 4 워드, 전부 `s` 뒤를 가리킨다) 의 끝 워드가 메시지 머리로 딸려 들어온 경우 2B 건너뛴다.
    표 끝 워드(`93 A1` = $A193)가 우연히 전각 한 글자(「藤」)로 읽혀 메시지 머리에 붙었다(scn095, 10-11) — 그 위에 번역을 쓰면
    표 항목을 덮는다. 둘째 글자부터가 진짜 대본이다.
    (⚠ 글자가 우연히 주소처럼 읽히는 것만으로는 안 된다 — 「お」`82 A8` = $A882 도 블록 안이고 앞이 오름차순 표여도 그렇다(scn032). 끝 워드가 실제 **메시지 머리 후보**를 가리킬 때만 표 꼬리다.)"""
    ws = [_word(block, s - 6), _word(block, s - 4), _word(block, s - 2), _word(block, s)]
    if all(w is not None and w >= s + 2 for w in ws) and ws == sorted(set(ws)) and ws[-1] in starts:
        return s + 2
    return s


def _parse_from(block: bytes, s: int, stop: int | None = None) -> Message | None:
    """`s` 에서 메시지 하나를 읽는다. `stop` 이 있으면 거기서 끊는다(종료 없음) — 그 자리가 토큰 경계가 아니면 None."""
    i = s
    tokens: list = []
    speaker = None
    common = None
    text = []
    in_speaker = False
    complex_ = False
    while i < len(block):
        if stop is not None and i >= stop:
            if i > stop:
                return None  # 2바이트 글자·옵코드 한가운데 — 경계가 아니다
            if text:
                if in_speaker:
                    return None
                tokens.append("".join(text))
            return Message(s, i, speaker, common, tokens, complex_, terminated=False)
        b = block[i]
        if is_lead(b):
            if i + 1 >= len(block):
                return None
            ch = _decode_pair(block[i : i + 2])
            text.append(ch)
            i += 2
            continue
        if text:
            if in_speaker:
                speaker = "".join(text)
            else:
                tokens.append("".join(text))
            text = []
        if b in TERM:
            tokens.append(("op", b))
            i += 1
            return Message(s, i, speaker, common, tokens, complex_)
        if (b == 0x1F or b == 0x09) and (tokens or speaker is not None or common is not None):
            # 화자 전환 — 여기서 메시지를 가른다(종료 없음). 다음 메시지가 이 열개에서 시작한다
            return Message(s, i, speaker, common, tokens, complex_, terminated=False)
        if b == 0x1F:
            in_speaker = True
            i += 1
            continue
        if b == 0x04 and in_speaker:
            in_speaker = False
            i += 1
            continue
        if b == 0x09:
            common = block[i + 1]
            i += 2
            continue
        if b in TEXT_OPS:
            tokens.append(("op", b))
            i += TEXT_OPS[b]
            continue
        # 텍스트 밖 옵코드 — 여기서 끊는다(종료 없음)
        return Message(s, i, speaker, common, tokens, True, terminated=False)
    return None


REF_OPS = {
    0x4C,
    0x20,
}  # 6502 JMP/JSR. ⚠ 스크립트 옵코드(0F·10…)의 피연산자는 코드 안의 `STA $10` 같은 바이트와 겹쳐 소음이라 뺐다 — 메시지 안을 가리키는 스크립트 점프는 v0 가 못 본다(status.md)
SPLIT_PTR = re.compile(
    rb"(?=\xa9(.)\x85(.)\xa9(.)\x85(.))", re.DOTALL
)  # LDA #lo; STA zp; LDA #hi; STA zp+1 (겹침 허용)


def references(block: bytes) -> dict[int, list[int]]:
    """블록 안에서 **그럴듯한 자리**에 있는 블록 내부 주소 참조 → {오프셋: [참조 위치…]}.

    16비트 값 전부를 보면 우연 일치가 메시지의 절반을 pinned 로 만든다(실측 1,604/3,676). 실제 포인터는
    (1) 머리 표(연속된 주소 워드) (2) `LDA #lo; STA zp; LDA #hi; STA zp+1` 분할 즉치 (3) 옵코드·JMP/JSR
    피연산자, 이 셋이다(scn 2 실측).
    """
    refs: dict[int, list[int]] = {}
    n = len(block)

    def add(w, at):
        if BASE <= w < BASE + n:
            refs.setdefault(w - BASE, []).append(at)

    i = 0
    while i + 1 < n:  # (1) 머리 표
        w = block[i] | block[i + 1] << 8
        if w == 0 or BASE <= w < BASE + n:
            add(w, i)
            i += 2
        else:
            break
    for m in SPLIT_PTR.finditer(block):  # (2)
        lo, z1, hi, z2 = (m.group(k)[0] for k in (1, 2, 3, 4))
        if z2 == z1 + 1:
            add(lo | hi << 8, m.start())
    for j in range(n - 2):  # (3)
        if block[j] in REF_OPS:
            add(block[j + 1] | block[j + 2] << 8, j)
    return refs


def _split_pinned(block: bytes, msgs: list[Message]) -> list[Message]:
    """안쪽을 가리키는 참조가 있는 메시지를 **참조 자리에서 조각낸다**(마스터 10-11 「구조문제 해결」).

    · 참조 자리가 토큰 경계가 아니면(2바이트 글자 한가운데) 우연 일치다 — 참조로 안 친다.
    · 경계면 거기서 가른다: 앞 조각은 종료 없는 조각(재삽입 때 `0F` 로 참조 자리에 잇는다), 뒤 조각은 그
      자리에서 새 메시지로 시작한다(참조가 그 머리를 가리키므로 안 움직인다). 글 없는 조각(옵코드만)은 메시지가
      아니라 원본 바이트 그대로 둔다. 갈린 메시지마다 열쇠가 따로라 번역 정본도 조각별로 쓴다.
    """
    refs = references(block)
    out: list[Message] = []
    for m in msgs:
        cuts = sorted(o for o in refs if m.start < o < m.end)
        if not cuts:
            out.append(m)
            continue
        parts: list[Message] = []
        a = m.start
        ok = True
        for cut in cuts:
            frag = _parse_from(block, a, stop=cut) if a == m.start else _parse_from(block, a, stop=cut)
            if frag is None:
                continue  # 경계가 아니다 — 참조가 아닌 우연
            parts.append(frag)
            a = cut
        if not parts:
            out.append(m)
            continue
        last = _parse_from(block, a)
        if last is None or last.end != m.end:
            out.append(m)
            m.pinned = True
            m.refs = [r for o in cuts for r in refs[o]]
            continue
        parts.append(last)
        for frag in parts:
            if frag.speaker is None and frag.common is None and not any(isinstance(t, str) for t in frag.tokens):
                continue  # 글 없는 조각 — 원본 그대로
            out.append(frag)
    return out


def _mark_refs(block: bytes, msgs: list[Message]) -> None:
    refs = references(block)
    for m in msgs:
        for off in range(m.start + 1, m.end):
            if off in refs:
                m.pinned = True
                m.refs.extend(refs[off])


# ─── 번역 정본 ────────────────────────────────────────────────────────────────
SCRIPT_DIR = common.GAME_DIR / "script"
SPEAKERS = SCRIPT_DIR / "speakers.json"


def load_translations(scene_id: int) -> dict[str, dict]:
    p = SCRIPT_DIR / f"scn{scene_id:03d}.json"
    if not p.exists():
        return {}
    msgs = json.loads(p.read_text()).get("messages", {})
    out = {}
    for k, v in msgs.items():
        if "jp" in v:
            # 입장 배너(scn000) — 지명은 **사전(place)이 정본**이고 여기는 원문 지명 + 가운데맞춤 공백(`lead`·`tail`)뿐이다
            import canon  # shared/

            kr = canon.lookup(v["jp"], "place", "ed1")
            if kr is None:
                raise KeyError(f"scn{scene_id:03d} 열쇠 {k}: 사전(place)에 {v['jp']!r} 가 없다")
            v = {**v, "t": v.get("lead", "") + kr + v.get("tail", "")}
        out[k] = v
    return out


def load_speaker_overrides() -> dict[str, str]:
    """`script/speakers.json`(있으면) — 사전·정본 위에 얹는 보충·덮어쓰기. 10-08 에 5줄이 전부 사전·정본에 들어가 파일을 걷었다."""
    return json.loads(SPEAKERS.read_text()) if SPEAKERS.exists() else {}


def load_speakers() -> dict[str, str]:
    """화자 이름 = 인물은 **`shared/glossary`**, 역할군(兵士·神父·道具屋…)은 **`shared/canon`**(speaker)이 정본이다.
    `script/speakers.json` 이 있으면 그 위에 얹는 보충·덮어쓰기.
    """
    import sysbuild  # 지연 임포트 — 순환을 피한다

    out = dict(sysbuild.glossary())
    if SPEAKERS.exists():
        out.update(json.loads(SPEAKERS.read_text()))
    return _Speakers(out)


def _nsp(s: str) -> str:
    """화자 열쇠 비교용 — 공백(반각·전각)을 뗀다. 정본은 「大盗賊 ゲイル」(반각 공백)인데 롬 화자는 「大盗賊ゲイル」·「情報屋　トミー」(전각 공백)라 공백 차이로 놓쳤다(10-20 짝 표 — 화자 28행이 일본어로 남음)."""
    return s.replace(" ", "").replace("\u3000", "")


class _Speakers(dict):
    """화자 이름 → 우리 표기. **공백 없음·반각·전각을 같은 것으로** 보고 찾는다(`.items()` 의 열쇠는 정본 그대로)."""

    def __init__(self, d):
        super().__init__(d)
        self._n = {_nsp(k): v for k, v in d.items()}

    def get(self, k, default=None):
        v = self._n.get(_nsp(k)) if isinstance(k, str) else None
        return v if v is not None else super().get(k, default)

    def __contains__(self, k):
        return isinstance(k, str) and (_nsp(k) in self._n or super().__contains__(k))

    def __getitem__(self, k):
        v = self.get(k)
        if v is None:
            raise KeyError(k)
        return v


# ─── 재삽입 ──────────────────────────────────────────────────────────────────
def protected_terminators(block: bytes) -> set[int]:
    """다른 코드가 **점프해 오는 종료 바이트**의 오프셋 — 넘침 점프(`0F 주소` 3B)가 그 `00` 을 덮으면 안 된다.
    `references` 는 스크립트 `0F` 를 소음이라 뺐지만, 목표가 **어느 메시지의 종료 바이트와 정확히 같은** `0F 주소` 만 골라 본다(우연히 겹칠 확률이 낮다 — 걸려도 비용은 1B)."""
    msgs = parse(block)
    term = {m.end - 1 for m in msgs if m.terminated}
    out = {t for t in term if t in references(block)}
    n = len(block)
    for j in range(n - 2):
        if block[j] == JUMP:
            w = block[j + 1] | block[j + 2] << 8
            if BASE <= w < BASE + n and w - BASE in term:
                out.add(w - BASE)
    return out


def splice(block: bytes, edits: list[tuple[Message, bytes]]) -> bytes:
    """메시지들을 제자리에 쓰고, 넘치면 `0F` 로 블록 끝에 잇는다. 기존 주소는 하나도 안 움직인다."""
    out = bytearray(block)
    guarded = protected_terminators(block)  # 다른 코드가 점프해 오는 종료 바이트(`0F 1E A6` → 옛 메시지의 `00`)
    for m, new in edits:
        if m.pinned:
            raise ValueError(
                f"메시지 +{m.start:#06x} 는 pinned(안쪽 참조) — 자리 규칙으로 못 넣는다"
            )
        # ⚠ complex(텍스트 밖 옵코드 앞에서 끊긴 조각)는 넣을 수 있다 — 종료가 없으니 `0F` 로 원래
        #   옵코드 자리(m.end)에 잇는다. 그 옵코드부터 실행이 그대로 이어진다.
        room = m.end - m.start
        if not m.terminated:
            if len(new) == room:  # 자리를 딱 채우면 뒤 바이트가 곧 이어진다 — 점프가 필요 없다
                out[m.start : m.end] = new
                continue
            nxt = BASE + m.end
            new = new + bytes([JUMP, nxt & 0xFF, nxt >> 8])
        if len(new) <= room:
            out[m.start : m.start + len(new)] = new
            out[m.start + len(new) : m.end] = b"\0" * (room - len(new))
            continue
        if room < 3:
            raise ValueError(f"메시지 +{m.start:#06x} 자리가 {room}B — `0F` 점프(3B)도 못 넣는다")
        # 🔴 **종료 바이트가 다른 곳의 점프 목표면 그 `00` 을 지키고 한 바이트 먼저 끊는다** — 넘칠 때 제자리 끝의 `0F 주소`(3B)가 종료 바이트 자리까지 덮으면, 그 자리로 오던
        #    다른 메시지의 `0F`(예: 씬 12 라우엘의 끝 옵코드 `0F 1E A6` → 옛 메시지의 `00`)가 우리 점프 주소 상위 바이트로 떨어져 뒤 글자를 줄줄이 읽는다(씬 12 「오. 오시합니다」, 마스터 qa 10-22).
        guard = 1 if (m.end - 1) in guarded else 0
        if room - 3 - guard < 0:
            raise ValueError(f"메시지 +{m.start:#06x} 자리가 {room}B — 종료 바이트 보호({guard}B)+`0F` 점프(3B)가 안 들어간다")
        cut = _token_boundary(new, room - 3 - guard)
        tail_addr = BASE + len(out)
        out[m.start : m.start + cut] = new[:cut]
        out[m.start + cut : m.start + cut + 3] = bytes([JUMP, tail_addr & 0xFF, tail_addr >> 8])
        out[m.start + cut + 3 : m.end] = b"\0" * (room - cut - 3)
        out += new[cut:]
    return bytes(out)


def _token_boundary(b: bytes, limit: int) -> int:
    """limit 이하에서 토큰 경계(2바이트 글자·옵코드를 안 가르는 자리)를 찾는다."""
    i = 0
    last = 0
    while i < len(b):
        v = b[i]
        ln = 2 if is_lead(v) else TEXT_OPS.get(v, OTHER_OPS.get(v, 1))
        if i + ln > limit:
            break
        i += ln
        last = i
    return last  # 0 이면 첫 토큰이 안 들어간다 — 자리 머리에 곧바로 `0F` 를 놓는다(자리 ≥ 3B)


def dump_all(found) -> dict:
    out_dir = common.OUT_DIR / "messages"
    out_dir.mkdir(parents=True, exist_ok=True)
    seen = {}
    stats = {"blocks": 0, "messages": 0, "complex": 0, "pinned": 0, "chars": 0, "unique_keys": 0}
    keys = set()
    for c in found:
        for b in c["blocks"]:
            if b["id"] in seen:
                continue
            seen[b["id"]] = True
            msgs = parse(b["data"])
            stats["blocks"] += 1
            rows = []
            for m in msgs:
                stats["messages"] += 1
                stats["complex"] += m.complex
                stats["pinned"] += m.pinned
                stats["chars"] += sum(len(t) for t in m.tokens if isinstance(t, str))
                keys.add(m.key)
                rows.append(
                    {
                        "key": m.key,
                        "start": m.start,
                        "end": m.end,
                        "speaker": m.speaker,
                        "common": m.common,
                        "jp": m.jp,
                        "complex": m.complex,
                        "pinned": m.pinned,
                    }
                )
            (out_dir / f"scn{b['id']:03d}.json").write_text(
                json.dumps(rows, ensure_ascii=False, indent=1)
            )
    stats["unique_keys"] = len(keys)
    return stats


if __name__ == "__main__":
    import containers

    common.verify_originals()
    print(dump_all(containers.scan()))
