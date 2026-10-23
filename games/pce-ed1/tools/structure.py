"""씬 블록 **구조 대조 + 재배치 장부** — 빌드가 실제로 한 재배치를 단계마다 잡아 장부(`relocations.tsv`)로 뽑고, 제어 코드 열이 원본과 같은 구조인지 대조한다
(마스터 10-22 「재배치사고 막는 정적검사」 — ss-ed3 에서 대사 끝에 넣은 채움 바이트(FF FF)가 다음 블록 호출을 막아 첫 장면 대사가 통째로 빠졌다).

씬 블록은 번역 단계(`translate`) → 직접 편집(`edits`) → 나레이션 게이트(`narr`) → 음성 시각표(`sched`) → 대사창 모양 자막(`gwin`) → 동적 글리프 머리(`dyn`) 순으로 바뀐다.
`build.py` 가 단계마다 `BlockRec.add(이름, 전, 후)` 를 부르면 여기서 단계별 차이를 분류한다 — **장부는 손으로 쓰지 않고** 그 기록에서만 나온다.

대조(위반 = 빌드 실패):
  · 번역 단계: 원본 메시지(`messages.parse`)마다 새 바이트가 **같은 구조**여야 한다 — 열개(`1F 화자 04` · `09 nn`)가 같은 종류, 본문에는 글자·텍스트 옵코드(`TEXT_OPS`)·`0F` 점프만,
    종료 바이트(`00`·`06`·`07`)는 **원본의 종료 바이트와 같은 값**(종료가 있던 메시지) · 종료 없던 조각은 `0F` 로 원래 끝(`m.end`)에 되돌아가거나 자리를 딱 채운다.
    제자리에 안 들어가 꼬리로 이은 조각은 꼬리를 따라가 **같은 규칙**으로 끝나야 한다. 종료 뒤 남는 칸은 **0 만**(채움 — FF 같은 다른 값 금지).
  · 메시지 밖 바이트가 바뀐 자리(조사 조각·한 글자 화자 머리)는 알려진 패턴(제자리 교체 · 꼬리 이음 + 원래 자리 뒤로 복귀 점프)만 허용한다.
  · 꼬리(블록 끝에 덧붙은 바이트)는 **어느 점프·스텁이 가리키는 조각**이어야 한다 — 아무도 안 가리키는 덧붙임은 위반.
  · 모든 `0F` 가 가리키는 주소는 블록 안이고, 번역 단계의 점프는 꼬리 조각 시작 또는 원본 메시지 끝뿐이다.

장부 열: 블록 키 · 종류 · 수 · 원래 좌표 · 새 좌표 · 사유 · 엔진 근거 · 되돌리면. 원문 바이트·문장은 넣지 않는다(좌표·종류·사유만).
게이트(`check_relocations.py`)는 커밋된 `relocations.tsv` 와 비교해 **장부에 없는 (블록, 종류) 가 새로 생기면** 실패시킨다.
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import messages as M

BASE = M.BASE
TERM = M.TERM
TEXT_OPS = M.TEXT_OPS
JUMP = M.JUMP
SLOT_OPS = frozenset({0x0B, 0x0E})  # 슬롯(이름·아이템 삽입) 옵코드 — 메시지 밖 조사 조각 꼬리에만 나온다(translate._orphan_patches)

# 종류별 사유·엔진 근거·되돌리면 — 장부 열 값(상수). 엔진 근거 = 디스어셈블 주소(status.md 3절 · 각 모듈 머리 주석).
KINDS = {
    "꼬리 이음": (
        "번역이 원문 자리보다 길어 블록 끝으로 잇는다(`0F lo hi`)",
        "씬 인터프리터 $6712 가 0F 를 만나면 피연산자 주소로 점프해 읽는다(messages.splice · status 3절)",
        "되돌리기 수단 없음 — 원문 자리에 안 들어가는 번역이라(문안을 자리 안으로 줄이는 것 외엔 방법 없음)",
    ),
    "복귀 점프": (
        "종료 없는 조각(화자 전환·옵코드 앞에서 끊긴 메시지)을 새 바이트 뒤 `0F` 로 원래 끝(`m.end`)에 잇는다",
        "씬 인터프리터 $6712 — 0F 점프(messages.splice)",
        "되돌리기 수단 없음 — 새 바이트 길이가 원문과 달라 점프 없이는 뒤 바이트가 이어지지 않는다",
    ),
    "채움": (
        "번역이 원문 자리보다 짧아 종료 바이트 뒤 남는 칸을 0 으로 채운다",
        "종료 바이트(00·06·07) 뒤는 인터프리터가 읽지 않는다 — 메시지가 거기서 끝난다($6712)",
        "원 자리 방식으로 굽는 스위치 없음(번역 길이가 곧 채움 길이) — 문안을 원문 길이에 맞출 때만 사라진다",
    ),
    "조각 이음": (
        "메시지 밖 조각(슬롯 옆 조사 · 한 글자 화자 머리)이 자리보다 길어 꼬리로 잇고 복귀 점프를 단다",
        "씬 인터프리터 $6712 — 0F 점프(translate.apply_orphans)",
        "되돌리기 수단 없음 — 동적 조사 토큰/화자 표기가 원문 바이트보다 길다",
    ),
    "제자리 교체": (
        "원문 바이트를 같은 자리·같은 길이 안의 우리 바이트로 바꾼다(조사 토큰·직접 편집 등)",
        "같은 길이 교체라 흐름 불변(translate.apply_orphans · build.apply_edits)",
        "단계별 끄기 스위치 없음 — 바이트 목록(`_orphan_patches`/edits)에서 항목을 지우면 원문으로 돌아간다",
    ),
    "스텁": (
        "나레이션 게이트·음성 시각표·대사창 모양 자막·동적 글리프가 게이트/머리를 우리 코드로 돌리고 블록 끝에 스텁을 단다",
        "narration_gates.patch_block · voice_sched.patch_block · gwin_rt.patch_block · glyphdyn.attach(블록 머리 점프 $A000, 10-11 BP)",
        "환경변수/목록으로 끄는 스위치 없음(씬 ID 목록: narration_gates.SITES/ALWAYS · voice_sched.scene_ids · gwin_rt.build_specs · glyphdyn) — 그 목록에서 빼면 원 흐름",
    ),
    "이사": (
        "컨테이너 총량이 칸을 넘어 트랙 끝 빈 구간으로 옮기고 참조표(rel 42 뱅크)를 새 자리로 고친다",
        "containers 참조표 + build.patch_ref_table(되읽기: verify_readback)",
        "되돌리기 수단 없음 — 번역 총량이 원래 칸(섹터 수)보다 커서 옮겨야 들어간다(문안·꼬리 줄이기로만 사라진다)",
    ),
    "포인터": (
        "이사한 컨테이너의 참조표 항목(rel · 섹터 수)을 새 값으로 고친다",
        "containers.REF_TABLE_OFF · build.patch_ref_table",
        "이사를 되돌릴 때만 같이 돌아간다",
    ),
}


class StructureError(Exception):
    pass


class BlockRec:
    """블록 하나의 단계별 기록 — `add(이름, 전, 후)` 를 단계마다 부른다(안 바뀐 단계는 무시)."""

    def __init__(self, rel: int, sid: int, orig: bytes):
        self.rel, self.sid, self.orig = rel, sid, orig
        self.stages: list[tuple[str, bytes, bytes]] = []

    def add(self, name: str, before: bytes, after: bytes) -> None:
        if before != after:
            self.stages.append((name, before, after))

    @property
    def final(self) -> bytes:
        return self.stages[-1][2] if self.stages else self.orig


def diff_ranges(a: bytes, b: bytes) -> list[tuple[int, int]]:
    """공통 길이 안에서 다른 바이트의 연속 구간 [start, end)."""
    out: list[tuple[int, int]] = []
    n = min(len(a), len(b))
    i = 0
    while i < n:
        if a[i] != b[i]:
            j = i
            while j < n and a[j] != b[j]:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def _walk(buf: bytes, i: int, limit: int, base_len: int, where: str, viol: list[str], slot_ops: bool = False):
    """`i` 에서 메시지 본문을 읽는다. 돌려주는 값 = (끝 종류, 끝 위치, 점프 목적지 또는 종료 바이트).
    끝 종류: `term`(종료 바이트) · `jump`(0F) · `end`(limit 도달 — 종료도 점프도 없이 자리를 채움). 본문에 낯선 옵코드가 있으면 위반."""
    while i < min(limit, len(buf)):
        b = buf[i]
        if b >= 0x24:
            i += 2
            continue
        if b in TERM:
            return "term", i + 1, b
        if b == JUMP:
            if i + 2 >= len(buf):
                viol.append(f"{where}: 0F 점프 피연산자가 블록 끝에 걸린다(+{i:#x})")
                return "bad", i, None
            tgt = (buf[i + 1] | buf[i + 2] << 8) - BASE
            if not 0 <= tgt < len(buf):
                viol.append(f"{where}: 0F 가 블록 밖을 가리킨다(+{i:#x} → {tgt:#x}, 블록 {len(buf):#x}B)")
                return "bad", i, None
            return "jump", i + 3, tgt
        if b in TEXT_OPS:
            i += TEXT_OPS[b]
            continue
        if slot_ops and b in SLOT_OPS:  # 슬롯 옆 조사 조각(`0B … 0E`) — 이름 삽입 옵코드(1B 짜리)
            i += 1
            continue
        viol.append(f"{where}: 본문에 낯선 옵코드 {b:02X} (+{i:#x})")
        return "bad", i, None
    return "end", i, None


def _opening_ok(orig_msg: M.Message, new: bytes, where: str, viol: list[str]) -> None:
    """열개가 원본과 같은 종류인가 — 화자(1F … 04) / 공용(09 nn) / 없음."""
    if orig_msg.speaker is not None:
        if not new or new[0] != 0x1F:  # 04 는 이름이 길면 꼬리 조각 안에 있을 수 있다(0F 로 이어짐)
            viol.append(f"{where}: 화자 열개(1F …)가 없다")
    elif orig_msg.common is not None:
        if len(new) < 2 or new[0] != 0x09 or new[1] != orig_msg.common:
            viol.append(f"{where}: 공용 화자 열개 09 {orig_msg.common:02X} 가 다르다")
    else:
        if new and new[0] in (0x1F, 0x09):
            viol.append(f"{where}: 원본에 없던 화자 열개가 생겼다")


def _check_translate(rec: BlockRec, before: bytes, after: bytes, viol: list[str], rows: list, claimed: list):
    """번역 단계 — 메시지마다 구조 대조 + 종류 분류. `claimed` 에 꼬리 조각 구간을 더한다."""
    sid = f"{rec.rel}:{rec.sid}"
    L = len(before)
    msgs = M.parse(before)
    spans = [(m.start, m.end) for m in msgs]
    kinds = defaultdict(list)
    guarded = M.protected_terminators(before)  # 다른 코드가 점프해 오는 종료 바이트
    for m in msgs:
        seg_old = before[m.start : m.end]
        seg = after[m.start : m.end]
        if seg == seg_old:
            continue
        where = f"{sid} +{m.start:#06x}"
        if m.terminated and (m.end - 1) in guarded and after[m.end - 1] != before[m.end - 1]:
            viol.append(
                f"{where}: 종료 바이트(+{m.end - 1:#06x})가 다른 코드의 점프 목표인데 {after[m.end - 1]:02X} 로 바뀌었다(원본 {before[m.end - 1]:02X}) — 그리로 오는 흐름이 뒤 글자를 읽는다"
            )
        _opening_ok(m, seg, where, viol)
        kind, end, info = _walk(after, m.start, m.end, L, where, viol)
        if kind == "bad":
            continue
        if kind == "term":
            exp = m.tokens[-1][1] if m.terminated and m.tokens and isinstance(m.tokens[-1], tuple) else None
            if m.terminated and exp is not None and info != exp:
                viol.append(f"{where}: 종료 바이트가 {info:02X} — 원본은 {exp:02X}")
            if not m.terminated:
                viol.append(f"{where}: 종료 없던 조각에 종료 바이트 {info:02X} 가 생겼다(뒤 바이트가 안 이어진다)")
            pad = after[end : m.end]
            if any(pad):
                viol.append(f"{where}: 종료 뒤 남는 칸에 0 이 아닌 바이트가 있다({pad.hex()[:24]}) — 채움은 0 만")
            if m.end - end > 0:  # 길이가 딱 맞으면 채움이 없다(제자리 번역 — 재배치 아님)
                kinds["채움"].append((m.start, m.end - end))
        elif kind == "jump":
            tgt = info
            if tgt >= L:  # 꼬리 이음
                kinds["꼬리 이음"].append((m.start, tgt))
                _follow_tail(after, tgt, L, m, where, viol, claimed)
                pad = after[end : m.end]
                if any(pad):
                    viol.append(f"{where}: 점프 뒤 남는 칸에 0 이 아닌 바이트가 있다({pad.hex()[:24]})")
            elif tgt == m.end and not m.terminated:
                kinds["복귀 점프"].append((m.start, tgt))
                pad = after[end : m.end]
                if any(pad):
                    viol.append(f"{where}: 점프 뒤 남는 칸에 0 이 아닌 바이트가 있다({pad.hex()[:24]})")
            else:
                viol.append(f"{where}: 0F 목적지가 꼬리도 원래 끝(m.end={m.end:#x})도 아니다({tgt:#x})")
        else:  # end — 자리를 딱 채움
            if m.terminated:
                viol.append(f"{where}: 종료가 있던 메시지가 종료 없이 자리만 채웠다")
    # 메시지 밖 변경 — 조사 조각·한 글자 화자 머리. 메시지 칸 안의 바이트는 위에서 봤으니 빼고, 칸 밖에서 이어진 변경만 묶는다
    inside = bytearray(L)
    for s_, e_ in spans:
        for i in range(s_, min(e_, L)):
            inside[i] = 1
    n_ = min(L, len(after))
    i = 0
    while i < n_:
        if before[i] != after[i] and not inside[i]:
            j = i
            while j < n_ and before[j] != after[j] and not inside[j]:
                j += 1
            a, b = i, j
            where = f"{sid} +{a:#06x}(메시지 밖)"
            new = after[a:b]
            if new[0] == JUMP:
                tgt = (after[a + 1] | after[a + 2] << 8) - BASE
                if tgt < L:
                    viol.append(f"{where}: 조각 점프가 꼬리가 아니다({tgt:#x})")
                else:
                    kinds["조각 이음"].append((a, tgt))
                    # 꼬리 조각 — 새 바이트 + `0F` 복귀. 복귀 목적지 = 원래 조각 바로 뒤(바뀐 3B 뒤 ~ 원본 조각 길이 ≤ 4B)
                    kind, end, info = _walk(after, tgt, len(after), L, where, viol, slot_ops=True)
                    if kind != "jump" or not (b <= info <= b + 4):
                        viol.append(f"{where}: 조각 꼬리가 원래 자리 뒤({b:#x}~{b + 4:#x})로 되돌아가지 않는다")
                    else:
                        claimed.append((tgt, end))
            else:
                kinds["제자리 교체"].append((a, b - a))
            i = j
        else:
            i += 1
    for k, v in kinds.items():
        rows.append((sid, k, v))


def _follow_tail(after: bytes, tgt: int, L: int, m: M.Message, where: str, viol: list[str], claimed: list):
    """꼬리 조각을 따라간다 — 종료 있던 메시지는 종료 바이트(원본과 같은 값)로, 종료 없던 조각은 `0F` → `m.end` 로 끝나야 한다."""
    seen = 0
    i = tgt
    while seen < 8:
        seen += 1
        kind, end, info = _walk(after, i, len(after), L, where, viol)
        if kind == "bad":
            return
        claimed.append((i, end))
        if kind == "term":
            exp = m.tokens[-1][1] if m.terminated and m.tokens and isinstance(m.tokens[-1], tuple) else None
            if m.terminated and exp is not None and info != exp:
                viol.append(f"{where}: 꼬리 조각 종료 바이트 {info:02X} — 원본은 {exp:02X}")
            if not m.terminated:
                viol.append(f"{where}: 종료 없던 조각의 꼬리가 종료 바이트로 끝났다")
            return
        if kind == "jump":
            if info == m.end and not m.terminated:
                return
            if info >= L:
                i = info  # 꼬리 안에서 또 점프(조각 연결)
                continue
            viol.append(f"{where}: 꼬리 조각이 엉뚱한 곳({info:#x})으로 점프한다(원래 끝 {m.end:#x})")
            return
        viol.append(f"{where}: 꼬리 조각이 종료도 점프도 없이 끝난다")
        return
    viol.append(f"{where}: 꼬리 점프가 8번을 넘게 이어진다")


def analyze_block(rec: BlockRec):
    """블록 하나 → (장부 행 목록, 위반 목록). 행 = (블록 키, 종류, 좌표 목록)."""
    sid = f"{rec.rel}:{rec.sid}"
    rows: list = []
    viol: list[str] = []
    claimed: list[tuple[int, int]] = []  # 단계가 덧붙인 꼬리 중 어딘가가 가리키는 조각
    L = len(rec.orig)
    for name, before, after in rec.stages:
        if name == "translate":
            _check_translate(rec, before, after, viol, rows, claimed)
        else:
            kind = "제자리 교체" if name == "edits" else "스텁"
            rngs = diff_ranges(before, after)
            if len(after) > len(before):
                rngs.append((len(before), len(after)))
            if rngs:
                rows.append((sid, f"{kind}", [(a, b - a) for a, b in rngs]))
            # 단계가 덧붙인 꼬리는 그 단계 소유다(스텁 코드·표) — 점프 대조는 안 한다(코드)
            if len(after) > len(before):
                claimed.append((len(before), len(after)))
        # 단계 사이에 줄어드는 일은 없어야 한다(덧붙이기만)
        if len(after) < len(before):
            viol.append(f"{sid}: {name} 단계가 블록을 줄였다({len(before)}→{len(after)}B)")
    final = rec.final
    # 덧붙은 꼬리가 모두 어느 조각·스텁에 속하나(아무도 안 가리키는 덧붙임 금지)
    if len(final) > L:
        cov = bytearray(len(final) - L)
        for a, b in claimed:
            for i in range(max(a, L), min(b, len(final))):
                cov[i - L] = 1
        gaps = [i for i, v in enumerate(cov) if not v]
        if gaps:
            viol.append(f"{sid}: 꼬리 {len(gaps)}B(+{L + gaps[0]:#x}~)를 아무 점프·스텁도 가리키지 않는다")
    return rows, viol


def verify_all(recs: dict, total_blocks: int, moves: dict | None = None):
    """전체 → (장부 행, 위반 목록, 요약). `recs` = {(rel, sid): BlockRec}."""
    ledger: list[tuple] = []
    viol: list[str] = []
    compared = 0
    for (rel, sid), rec in sorted(recs.items()):
        compared += 1
        r, v = analyze_block(rec)
        ledger += r
        viol += v
    for rel, (new_rel, n_sec) in sorted((moves or {}).items()):
        ledger.append((f"{rel}", "이사", [(rel, new_rel)]))
        ledger.append((f"{rel}", "포인터", [(rel, new_rel)]))
    summary = {"compared": compared, "total": total_blocks, "violations": len(viol)}
    return ledger, viol, summary


def ledger_tsv(ledger: list[tuple]) -> str:
    """장부 → TSV(블록 키 · 종류 · 수 · 원래 좌표 · 새 좌표 · 사유 · 엔진 근거 · 되돌리면). 좌표는 앞 6개만 적고 `…` 로 줄인다."""
    lines = ["# 블록 키\t종류\t수\t원래 좌표\t새 좌표\t사유\t엔진 근거\t되돌리면"]
    by = defaultdict(list)
    for blk, kind, coords in ledger:
        by[(blk, kind)] += coords
    for (blk, kind), coords in sorted(by.items(), key=lambda kv: (_key(kv[0][0]), kv[0][1])):
        why, engine, undo = KINDS[kind]
        if kind in ("꼬리 이음", "복귀 점프", "조각 이음"):
            old = ",".join(f"+{a:#x}" for a, _t in coords[:6]) + (" …" if len(coords) > 6 else "")
            new = ",".join(f"+{t:#x}" for _a, t in coords[:6]) + (" …" if len(coords) > 6 else "")
        elif kind in ("채움", "제자리 교체", "스텁"):
            old = ",".join(f"+{a:#x}({n}B)" for a, n in coords[:6]) + (" …" if len(coords) > 6 else "")
            new = old
        else:  # 이사·포인터 — (옛 rel, 새 rel)
            old = f"rel {coords[0][0]}"
            new = f"rel {coords[0][1]}"
        lines.append("\t".join([blk, kind, str(len(coords)), old, new, why, engine, undo]))
    return "\n".join(lines) + "\n"


def _key(blk: str):
    return tuple(int(x) if x.isdigit() else 0 for x in blk.split(":"))


# ── 전투 컨테이너(`battle.py`) — 문구 단위 구조 대조 ───────────────────────────────────────────────
# 전투 블록의 문구는 `battle.msg_units` 가 가르는 단위(본문 + 종단 바이트)이고, `battle.patch_msgs` 가 ① 제자리(딱 맞게 · 짧으면 `0F` 로 원래 종단 자리에 되돌아가고 0 채움)
# ② 넘치면 머리 `0F <꼬리>` + 꼬리(본문 + `0F` 복귀)로 쓴다. 종단 바이트(`01`·`0A`·`02` …)는 **문장 끝이 아니라 다음 바이트로 이어지는 제어코드**라
# 원래 자리(`off + len(본문)`)에 그대로 남아야 한다. 이름칸(레코드 16B · 간접 이름 문자열)은 글자 + `06` + 0 채움이다.

_BATTLE_INLINE = frozenset({0x01, 0x02, 0x04, 0x0B, 0x0E, 0x1E, 0x1F, 0x20, 0x22})


def _bwalk(buf: bytes, i: int, limit: int, where: str, viol: list[str]):
    """전투 문구 읽기 — 글자(≥0x24 2B) · 낀 제어코드(`INLINE_OPS`)를 지나 종단(그 밖의 <0x24) 또는 `0F` 에서 선다. (종류, 위치, 값)."""
    while i < min(limit, len(buf)):
        b = buf[i]
        if b >= 0x24:
            i += 2
            continue
        if b == JUMP:
            if i + 2 >= len(buf):
                viol.append(f"{where}: 0F 피연산자가 블록 끝에 걸린다(+{i:#x})")
                return "bad", i, None
            return "jump", i + 3, (buf[i + 1] | buf[i + 2] << 8)
        if b in _BATTLE_INLINE:
            i += 1
            continue
        return "term", i + 1, b
    return "end", i, None


def analyze_battle_block(key: str, O: bytes, N: bytes, load_addr: int):
    """블록 하나 → (장부 행, 위반). `key` = `rel:블록번호`."""
    import battle

    rows: list = []
    viol: list[str] = []
    L = len(O)
    units = battle.msg_units(O)
    spans = []
    kinds = defaultdict(list)
    claimed: list[tuple[int, int]] = []
    for u in units:
        off, body, term, room = u["off"], u["body"], u["term"], u["room"]
        blen = len(body)
        spans.append((off, off + room))
        if N[off : off + room] == O[off : off + room]:
            continue
        where = f"{key} +{off:#06x}"
        end_body = off + blen
        simple = False
        if N[off] == JUMP:  # 머리 점프 — 꼬리로 이은 문구
            tgt = (N[off + 1] | N[off + 2] << 8) - load_addr
            if not L <= tgt < len(N):
                viol.append(f"{where}: 머리 0F 가 꼬리를 못 가리킨다({tgt:#x}, 원본 {L:#x}B)")
                continue
            kind, end, val = _bwalk(N, tgt, len(N), where, viol)
            if kind == "bad":
                continue
            if kind == "jump":
                back = val - load_addr
                # 본문 3B 미만 조각은 종단까지 꼬리에 두므로 종단 다음(off + room)으로, 그 밖은 원래 종단 자리(end_body)로
                want = u["back"] - load_addr if u.get("back") is not None else (end_body if blen >= 3 else off + room)
                if back != want:
                    viol.append(f"{where}: 꼬리가 원래 흐름({want:#x})이 아닌 {back:#x} 로 되돌아간다")
                claimed.append((tgt, end))
            elif kind == "term":  # 본문이 3B 미만인 조각 — 꼬리에 종단까지 쓰고 그 뒤 `0F` 로 원래 자리 뒤(off + room)로 되돌아간다
                k2, e2, v2 = _bwalk(N, end, len(N), where, viol)
                if k2 != "jump" or v2 - load_addr != off + room:
                    viol.append(f"{where}: 꼬리의 종단 뒤 복귀 점프가 원래 자리 뒤({off + room:#x})가 아니다")
                if term is not None and val != term:
                    viol.append(f"{where}: 꼬리 종단 {val:02X} — 원본은 {term:02X}")
                claimed.append((tgt, e2))
            else:
                viol.append(f"{where}: 꼬리가 종료도 점프도 없이 끝난다")
            # 머리 3B 뒤 ~ 본문 끝은 0(원래 종단 바이트는 남는다)
            pad_end = end_body if (term is not None and blen >= 3 and u.get("back") is None) else off + room
            if any(N[off + 3 : pad_end]):
                viol.append(f"{where}: 머리 점프 뒤 남는 칸에 0 이 아닌 바이트가 있다")
            if term is not None and blen >= 3 and u.get("back") is None and N[end_body] != term:
                viol.append(f"{where}: 원래 종단 바이트 {term:02X} 가 제자리에 없다({N[end_body]:02X})")
            kinds["꼬리 이음"].append((off, tgt))
            continue
        kind, end, val = _bwalk(N, off, off + room, where, viol)
        if kind == "bad":
            continue
        if kind == "jump":  # 글 + `0F` 로 원래 종단 자리에 되돌아간다(짧은 번역)
            back = val - load_addr
            if back != end_body:
                viol.append(f"{where}: 제자리 점프가 원래 종단 자리({end_body:#x})가 아닌 {back:#x} 로 간다")
            if any(N[end : end_body]):
                viol.append(f"{where}: 점프 뒤 남는 칸에 0 이 아닌 바이트가 있다")
            if term is not None and N[end_body] != term:
                viol.append(f"{where}: 원래 종단 바이트 {term:02X} 가 제자리에 없다({N[end_body]:02X})")
            kinds["복귀 점프"].append((off, end_body))
        elif kind == "term":  # 글 + 종단(이름칸 · 딱 맞음)
            if term is not None and val != term:
                viol.append(f"{where}: 종단 바이트가 {val:02X} — 원본은 {term:02X}")
            pad = N[end : off + room]
            if any(pad):
                viol.append(f"{where}: 종단 뒤 남는 칸에 0 이 아닌 바이트가 있다({pad.hex()[:24]})")
            if off + room - end > 0:
                kinds["채움"].append((off, off + room - end))
        else:  # end — 자리를 딱 채웠다(종단이 낀 제어코드와 같은 값이면 지나쳐 끝에 닿는다) — 종단 바이트는 원래 자리에 그대로여야 한다
            if term is not None and (end < end_body or N[end_body] != term):
                viol.append(f"{where}: 종단이 있던 문구가 자리를 채웠는데 종단 바이트 {term:02X} 가 제자리에 없다")
    # 레코드 이름칸 · 간접 이름 — 유닛 밖 변경은 레코드의 이름 칸(NAME_OFF..+NAME_LEN)과 이름 꼬리만 허용
    n_rec = len(battle.records(O))
    ok = bytearray(L)
    for s_, e_ in spans:
        for i in range(s_, min(e_, L)):
            ok[i] = 1
    for r in battle.records(O):
        for i in range(r["off"] + battle.NAME_OFF, min(r["off"] + battle.REC, L)):
            ok[i] = 1
    bad = [i for i in range(min(L, len(N))) if O[i] != N[i] and not ok[i]]
    if bad:
        viol.append(f"{key}: 문구 단위·이름칸 밖 바이트가 바뀌었다(+{bad[0]:#x} 외 {len(bad) - 1}곳)")
    # 꼬리 — 아무도 안 가리키는 덧붙임 금지
    if len(N) > L:
        cov = bytearray(len(N) - L)
        for a, b in claimed:
            for i in range(max(a, L), min(b, len(N))):
                cov[i - L] = 1
        gaps = [i for i, v in enumerate(cov) if not v]
        if gaps:
            viol.append(f"{key}: 꼬리 {len(gaps)}B(+{L + gaps[0]:#x}~)를 아무 점프도 가리키지 않는다")
    for k, v in kinds.items():
        rows.append((key, k, v))
    return rows, viol


def verify_battle(recs: list):
    """전투 컨테이너 블록 전체 → (장부 행, 위반, 요약). `recs` = `battle.STRUCT_RECS`."""
    import battle

    ledger: list = []
    viol: list[str] = []
    for rel, bi, O, N in recs:
        r, v = analyze_battle_block(f"{rel}:b{bi}", O, N, battle.LOAD_ADDR)
        ledger += r
        viol += v
    return ledger, viol, {"compared": len(recs), "total": len(recs), "violations": len(viol)}


# ── 시스템 메시지(`sysbuild` · 뱅크 0x6D) — 제어 열 대조 ─────────────────────────────────────────
# 단위 = `sysstrings.read_sysmsg` (앞 옵코드 `lead` + 본문 + 뒤 옵코드 `tail`). 우리가 쓴 흐름을 **읽는 쪽(씬 인터프리터)처럼** 따라가며 — 글자는 지나고 `0F` 점프는
# 따라가고(원래 꼬리에 있던 `0F` 는 옵코드로 센다) — 만나는 옵코드가 원본의 `lead + tail` 과 **같은 값·같은 차례**인지 본다. 짧아져 다음 단위로 흐르는 조각의
# `0F 다음주소`, 옮겨 싣기(`spill` — 다른 단위의 남는 칸·선언한 빈 공간)가 모두 이 읽기로 따라진다. 낯선 옵코드가 먼저 나오면 위반.
_SYS_WINDOWS = ((0x8000, 0x6D), (0xC000, 0x74))


def _sys_read(banks: dict, addr: int, n: int) -> bytes:
    for base, bk in _SYS_WINDOWS:
        if base <= addr < base + 0x2000:
            return banks[bk][addr - base : addr - base + n]
    return b""


def analyze_sysmsg(units: list, banks: dict, join_next_line: dict | None = None):
    """units = 원본 `read_sysmsg()`, banks = {뱅크: 우리 이미지의 그 뱅크 바이트(8KB)}. → (장부 행, 위반)."""
    import sysstrings as SS

    join = join_next_line or {}
    viol: list[str] = []
    rows: list = []
    terminal = {0x00, 0x03, 0x06, 0x07, 0x0A, 0x0D}
    for u in units:
        n_lead = len(u["lead"])
        body_jumps = set(re.findall(r"\{(0F[0-9A-F]{4})\}", u.get("jp", "")))
        want = [bytes.fromhex(t) for t in u["lead"] + u["tail"]]
        if u["addr"] in join and want and want[-1] == b"\x01":
            want = want[:-1]  # 마스터 10-10 — 꼬리의 개행 `01` 을 일부러 뺐다(JOIN_NEXT_LINE)
        i = u["addr"]
        k = 0
        followed = 0
        steps = 0
        ok = True
        while k < len(want) and steps < 400:
            steps += 1
            b0 = _sys_read(banks, i, 1)
            if not b0:
                viol.append(f"sysmsg {u['addr']:04X}: 읽다가 우리가 모르는 주소 {i:#06x} 에 닿았다")
                ok = False
                break
            b = b0[0]
            exp = _sys_read(banks, i, len(want[k]))
            if exp == want[k]:  # 원본이 이 자리에 둔 옵코드(`sysstrings` 토큰화 기준 — 0x24 이상 1B 옵코드도 거기 든다)
                k += 1
                i += len(exp)
                continue
            if b >= 0x24:
                i += 2
                continue
            ln = SS.OPLEN.get(b, 1)
            tok = _sys_read(banks, i, ln)
            if tok == want[k]:
                k += 1
                i += ln
                continue
            if b == JUMP and ln == 3 and tok.hex().upper() in body_jumps and k >= n_lead:  # 원본 본문에 든 `0F` — 원본도 같은 자리에 둔 옵코드라 지나간다(이음 점프가 아니다)
                i += ln
                continue
            if b == JUMP and ln == 3:  # 원래 꼬리의 점프가 아니면 우리가 단 이음 점프 — 따라간다
                tgt = tok[1] | tok[2] << 8
                followed += 1
                i = tgt
                continue
            if k >= n_lead:  # 본문 안의 옵코드(`06` 이름 끝 · `01` 줄바꿈 · `04` 화자 끝 …) — 본문은 문안 토큰이라 값만 맞는지는 번역 검사 몫, 여기선 지나간다
                i += ln
                continue
            if b in terminal:
                viol.append(f"sysmsg {u['addr']:04X}: 기대한 옵코드 {want[k].hex()} 전에 종료 {b:02X} 가 나왔다")
                ok = False
                break
            viol.append(f"sysmsg {u['addr']:04X}: 원본에 없던 옵코드 {tok.hex()} 가 끼었다(기대 {want[k].hex()})")
            ok = False
            break
        if ok and k < len(want):
            viol.append(f"sysmsg {u['addr']:04X}: 옵코드 열을 다 못 따라갔다({k}/{len(want)})")
        if ok and followed:
            rows.append((f"6D:{u['addr']:04X}", "꼬리 이음", [(u["off"], followed)]))
    return rows, viol


def analyze_label_separators(orig_bank: bytes, new_bank: bytes, lo: int, hi: int, moved: dict | None = None):
    """메뉴 라벨 구역 — 라벨은 `00` 개수로 찾으므로 구분자(`00`)의 자리가 원본과 같아야 한다(문서화된 한 칸 이동만 `moved={옛: 새}` 로 허용)."""
    viol: list[str] = []
    moved = moved or {}
    o_sep = {i for i in range(lo, hi) if orig_bank[i] == 0}
    n_sep = {i for i in range(lo, hi) if new_bank[i] == 0}
    exp = {moved.get(i, i) for i in o_sep}
    if exp != n_sep:
        lost = sorted(exp - n_sep)[:5]
        extra = sorted(n_sep - exp)[:5]
        viol.append(f"라벨 구분자(00) 자리가 원본과 다르다: 사라진 {[hex(x) for x in lost]} · 늘어난 {[hex(x) for x in extra]}")
    return viol


def iso_banks(iso, banks=(0x6D, 0x74)) -> dict:
    """구운 이미지에서 본 프로그램 뱅크(rel 34 + (뱅크−0x68)×4, 4섹터)를 읽는다."""
    import common

    out = {}
    with open(iso, "rb") as f:
        for bk in banks:
            rel = 34 + (bk - 0x68) * 4
            buf = bytearray()
            for r in range(rel, rel + 4):
                f.seek((common.T2_SECTOR + r) * common.RAW + common.USER_OFF)
                buf += f.read(common.USER)
            out[bk] = bytes(buf)
    return out


# 대조가 짚었지만 의도 여부가 확정 안 된 어긋남 — 키 = 위반 문장 머리. 여기 있으면 실패 대신 알림(보고 후 판정). 비우는 게 목표다.
PENDING: dict[str, str] = {}


def verify_sys(iso, orig_track_banks: dict | None = None):
    """시스템 메시지(뱅크 0x6D) 단위 제어 열 + 라벨 구분자. → (장부 행, 위반, 보류, 요약)."""
    import sysbuild
    import sysstrings as SS

    ours = iso_banks(iso)
    units = SS.read_sysmsg()
    rows, viol = analyze_sysmsg(units, ours, sysbuild.JOIN_NEXT_LINE)
    ob = SS.bank_bytes(0x6D)
    viol += analyze_label_separators(ob, ours[0x6D], SS.LABELS[0], SS.LABELS[1], {0x16F8: 0x16FA})  # 전투 설정 「도망친다」 칸 경계 한 칸 이동(sysbuild, 10-08)
    pend = [v for v in viol if any(v.startswith(k) for k in PENDING)]
    hard = [v for v in viol if v not in pend]
    return rows, hard, pend, {"compared": len(units), "total": len(units)}
