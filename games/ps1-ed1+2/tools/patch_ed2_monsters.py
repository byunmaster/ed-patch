#!/usr/bin/env python3
"""ED2 몬스터 이름(`ED2MON0~5.BIN`) 한글화 — **제자리 치환만** 한다.

레코드는 **[이름들][대사들][능력치표]** 반복이고 이름은 레코드 머리에 붙어 있다. 구조와
그 근거는 `docs/ed2-status.md`, 원문↔정발 짝짓기는 `tools/ed2_monster_review.py`.

**정본은 `textmap/monsters_ed2.json`** 이고 이 패처는 그것만 읽는다. 짝짓기(음차 유사도)는
제안이라 빌드 경로에 두지 않는다 — 두면 결과가 환경을 탄다(레포 제1원칙).

⚠ **개체 접미는 반각으로 쓴다**(`スライムＡ` → `슬라임A`). ED1 에서 이미 반각으로 통일했고
(전각이면 이름표 폭이 어긋난다), 덤으로 1바이트가 남아 제자리에 들어갈 여지가 커진다.

⚠ **넘치면 꼬리로 재배치한다**(2026-09-13, 마스터 QA 052). 예전엔 건너뛰고 보고만 했는데
그러면 그 자리에 원문이 그대로 남아 화면에 깨진 글자가 나간다 — `patch_ed2_monster_lines.py`
의 것을 그대로 재사용한다(아래 임포트 참조).

  python3 tools/patch_ed2_monsters.py --plan   # 무엇이 들어가고 무엇이 남는지
  python3 tools/patch_ed2_monsters.py          # 이미지에 적용
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import hangul_map as H
from common import BUILD_DIR, ROOT, extract, write_user_data
from ed2_monster_review import JP, MON, SUFFIX, decode_sjis, records
from ed2_monster_review import strings as jp_strings

# 이름 슬롯 초과분 재배치 — 새로 짜지 않고 patch_ed2_monster_lines 의 것을 그대로 쓴다
# (2026-09-13, 마스터 QA 052 — 이름 표엔 재배치 경로가 아예 없어 "초과"가 곧 미적용이었다.
# `overlay_refs`/`_relocate`/`BASE` 는 같은 ED2MON 오버레이를 보는 같은 도구라 100% 재사용
# 가능하다 — 재구현하면 같은 판단이 두 곳에 갈린다).
from patch_ed2_monster_lines import BASE as _MON_LINES_BASE
from patch_ed2_monster_lines import _relocate as _mon_lines_relocate
from patch_ed2_monster_lines import _update_dir_size as _mon_lines_update_dir_size
from patch_ed2_monster_lines import overlay_refs as _mon_overlay_refs

assert _MON_LINES_BASE == 0x8014A000  # 이름 표·대사 표가 같은 오버레이 베이스를 본다는 전제

IMG = f"{BUILD_DIR}/Eiyuu Densetsu (KR).bin"
CANON = os.path.join(ROOT, "textmap", "monsters_ed2.json")

JP = re.compile(r"[ぁ-んァ-ヴ一-鿿]")
CTL = re.compile(r"[\x00-\x1f]")
_PUA = re.compile(r"[-]")  # cp932 가 미정의 바이트를 매핑하는 자리(`_recover_swallowed` 참조)
DIALOG = re.compile(r"[。！？…、」『%\n]")
NAME_MAX = 14

# 전각 접미 → 반각. `′`·`”` 는 분열체 구분이라 살린다(`赤スライムＡ′`).
HALF = {chr(0xFF21 + i): chr(ord("A") + i) for i in range(26)}


def _enc(kr):
    """한글은 슬롯 SJIS, 나머지(숫자·영문·부호)는 원래 SJIS — 전투 패처와 같은 관용."""
    out = bytearray()
    for ch in kr:
        if "가" <= ch <= "힣":
            out += H.encode_kr(ch)
        else:
            out += ch.encode("shift_jis")
    return bytes(out)


# 🔴 **이름이 능력치 인덱스 바이트와 한 구간에 삼켜진다**(2026-09-12, 마스터 QA `032`
# 「ルンバットＡ」만 일본어로 남음). `jp_strings()` 는 **널 종단 구간 전체**를 한 번에
# 디코드한다 — 이름 바로 앞의 스킬/능력치 인덱스에 SJIS 미정의 바이트(`0xFF`)가 섞이면
# **그 구간 전체가 디코드 실패로 버려져 이름째 사라진다.** `モーンガーＡ` 류(디코드는
# 되지만 잡음이 한자로 읽히는 경우, `_drop_noise_prefix` 가 처리)와는 **다른 실패
# 모드**다 — 이쪽은 디코드 자체가 안 된다. 실측 9종: 룬뱃트A·토프스A·촉수요충A·
# 조리아드A·자콘A·요마화포A·지헤드A·그롤A·뇌랑(전부 ED2MON1~5).
#
# ⚠ **접미는 반각도 있다**(2026-09-13, 마스터 QA `047` — レミングプラスA 가 통째로
# 일본어). 위 예제 9종은 전부 전각(Ａ-Ｄ)이라 접미를 그렇게만 받았는데, 이 종은
# 반각 `A`(0x41)다 — 표기가 레코드마다 안 갈렸다.
_NAME_LIKE = re.compile(r"^[ァ-ヶー・゛゜一-鿿]{2,%d}[Ａ-ＦA-F]?$" % NAME_MAX)


def _recover_swallowed(buf, start, end):
    """`jp_strings()` 가 디코드 실패로 통째로 버린 구간에서 이름만 건진다.

    ⚠ **2바이트 보폭만으론 부족하다**(2026-09-13, 마스터 QA `047` 로 추가 실측).
    잡음 길이가 시작점 기준 **홀수**면 2바이트 보폭이 진짜 경계를 건너뛴다
    (レミングプラスA — 노이즈가 7바이트라 짝수 보폭이 그 앞 글자 `レ` 하나를 놓치고
    `ミングプラスA` 에서 멈췄다). ⇒ **바이트 전수**로 후보를 모으고, **정본에 정확히
    있는 것만** 받는다(`_NAME_LIKE` 모양만 보면 잡음도 몇 개 통과한다 — 정본 대조가
    진짜 안전장치다). 값은 비싸 보여도 이 구간은 실패 판정된 것만 도니 전체 스캔 대비
    작다. 실측: 기존 9종 + 이 반각 1종 = 10종, 새 잡음 0건(전수 검증).
    """
    canon = _canon_jp()

    def _strict(b):
        # `decode_sjis` 는 자기 안에서 최대 4바이트를 더 건너뛰고 성공 자리를 돌려주는데
        # 그 만큼을 호출자에게 안 알려준다 — 이 함수는 이미 바깥 `k` 루프로 1바이트씩
        # 건너뛰며 전수를 돌므로, 안에서 또 건너뛰면 실제 시작(`k`+내부건너뜀)이 보고값
        # (`k`)보다 뒤로 밀려 이름 앞쪽이 잘려 심긴다(2026-09-13, 마스터 QA — 토프스A가
        # 「스A」로 읽힘. `03 04 FF 3C` 잡음 4B를 안에서 건너뛰어 k=0x13fc를 보고했지만
        # 진짜 시작은 0x1400이었다). 여기서는 항상 건너뛰기 0(엄격 디코드)만 쓴다.
        # ⚠ **cp932 는 미정의 바이트(`0xFF` 등)를 에러 대신 PUA 문자로 매핑한다**(파이썬
        # 코덱 특성) — `UnicodeDecodeError` 를 안 던지니 위 "안에서 건너뛰기" 문제와
        # 별개로 **이 자리에서도 잡음이 섞인 채 "성공"으로 보인다**. 통째로 순수 JP 인
        # 것만 받는다(`CTL`·PUA 섞이면 잡음이 남은 것).
        try:
            s = b.decode("cp932")
        except UnicodeDecodeError:
            return None
        if not s or CTL.search(s) or _PUA.search(s):
            return None
        return s if JP.search(s) else None

    out = []
    i = start
    while i < end - 1:
        if buf[i] == 0:
            i += 1
            continue
        j = buf.find(b"\x00", i)
        if j < 0 or j > end:
            break
        span = j - i
        if 2 <= span <= 80:
            s = _strict(buf[i:j])
            if not s:
                cands = []
                for k in range(i + 1, j):
                    s2 = _strict(buf[k:j])
                    if s2 and _NAME_LIKE.match(s2):
                        stem = SUFFIX.sub("", s2)
                        if stem in canon:
                            cands.append((k, s2))
                if cands:
                    out.append(cands[0])
        i = j + 1
    return out


_CANON_JP = None


def _canon_jp():
    """정본(`textmap/monsters_ed2.json`) JP 키 집합 — 지연 로드, 프로세스당 한 번."""
    global _CANON_JP
    if _CANON_JP is None:
        with open(CANON, encoding="utf-8") as f:
            _CANON_JP = set(json.load(f))
    return _CANON_JP


def _recover_embedded(buf, start, end, covered):
    """대사 틈에 **단독으로 박힌** 이름 — 유일보스는 [이름들] 머리 없이 대사 중간에 이름이
    낀다(2026-09-13, `037` プルダーム 실측: `はてれている。` 다음에 `プルダーム` 가 그대로
    끼고, 레코드 첫 문자열부터 `%c%s%c` 서식 대사다). `name_strings` 는 이름 구간이
    **서식 대사를 만나면 끝난다**고 보고 첫 문자열에서 바로 멈추는데(정상 개체엔 맞는
    규칙), 이 레코드처럼 **이름 앞에 대사가 먼저 오면** 통째로 못 본다.

    안전장치 — **정본에 완전일치하는 이름**만 줍는다. 대사 조각을 이름으로 오인하지
    않기 위해서다(부분일치·유사도는 안 쓴다).
    """
    canon = _canon_jp()
    out = []
    for off, text in jp_strings(buf, start, end):
        if any(o <= off < o + s for o, s in covered):
            continue
        sfx = SUFFIX.search(text)
        stem = text[: sfx.start()] if sfx else text
        if stem not in canon:
            continue
        j = buf.find(b"\x00", off)
        nxt = j
        while nxt < end and buf[nxt] == 0:
            nxt += 1
        head = j - len(text.encode("cp932", "replace"))
        out.append((head, nxt - head, text))
    return out


def name_strings(buf, start, end):
    """레코드 머리의 이름 문자열 — [(오프셋, 슬롯 바이트, 원문)].

    ⚠ 슬롯은 **다음 문자열이 시작하는 자리까지**다(널 패딩 포함). 널 하나만 보면 뒤에 남는
    패딩을 못 쓰는데, 한글이 SJIS 보다 길어지는 이름이 많아 그 1~2바이트가 당락을 가른다.

    ⚠ 검토표와 **같은 스캐너**를 쓴다. 여기서 직접 훑으면 이름 사이에 낀 쓰레기 바이트에서
    스캔이 끊겨 뒤쪽 이름을 통째로 놓친다(실측: 302건이 36건으로 줄었다).
    """
    out = []
    for off, text in jp_strings(buf, start, end):
        if len(text) > NAME_MAX or DIALOG.search(text) or CTL.search(text):
            break  # 이름 구간은 대사를 만나면 끝난다
        j = buf.find(b"\x00", off)
        nxt = j
        while nxt < end and buf[nxt] == 0:
            nxt += 1
        # ⚠ 스캔 시작이 아니라 **실제 문자열 시작**을 쓴다 — 앞에 잡음 바이트가 붙은 자리가
        # 있어(`ff 82 8f 50` + `モーンガーＡ`) 그대로 쓰면 잡음 위에 덮어쓴다.
        head = j - len(text.encode("cp932", "replace"))
        out.append((head, nxt - head, text))
    # ⚠ **`covered` 는 (오프셋, 슬롯 크기) 다 — (오프셋, 끝오프셋) 이 아니다.** 이 아래
    # 두 소비자(줄 158·`_recover_embedded`)가 `o <= off < o + s` 로 읽어 `s` 를 크기로
    # 쓴다. 예전엔 `(o, o + s)`(끝오프셋)를 넣어 `o + (o+s)` 라는 거대한 가짜 범위가
    # 나왔다 — 첫 이름 뒤 레코드 전체가 "이미 덮였다"고 오판돼, **대사 뒤에 다시 나오는
    # 이름(D·E·F 등)이 `_recover_embedded` 에서 조용히 걸러졌다**(2026-09-13 실측:
    # 鋼鉄アリＤ·Ｅ·Ｆ 등 6곳이 이 버그로 화면에 일본어로 남아 있었다 — `check_scn_jp_left`
    # 의 ED2MON 편입으로 처음 드러났다).
    # 삼켜진 이름을 되찾아 합친다 — 이미 잡힌 자리와 안 겹칠 때만.
    covered = {(o, s) for o, s, _t in out}
    for k, text in _recover_swallowed(buf, start, end):
        if any(o <= k < o + s for o, s in covered):
            continue
        j = buf.find(b"\x00", k)
        nxt = j
        while nxt < end and buf[nxt] == 0:
            nxt += 1
        out.append((k, nxt - k, text))
    covered = {(o, s) for o, s, _t in out}
    out.extend(_recover_embedded(buf, start, end, covered))
    out.sort(key=lambda x: x[0])
    return _drop_noise_prefix(out)


def _drop_noise_prefix(items):
    """같은 레코드의 **깨끗한 형제**로 잡음 접두를 걷어낸다(검토표와 같은 규칙).

    `襲モーンガーＡ` 는 앞 데이터의 꼬리가 한자로 읽힌 것이고, 형제 `モーンガーＢ` 가
    깨끗하다. 안 걷어내면 정본에서 못 찾아 그 이름만 일본어로 남는다.

    ⚠ 오프셋·슬롯도 같이 민다 — 잡음 바이트 위에 덮어쓰면 그 자리의 데이터가 깨진다.
    """
    stems = {SUFFIX.sub("", t) for _o, _s, t in items}
    out = []
    for off, slot, text in items:
        st = SUFFIX.sub("", text)
        short = min((x for x in stems if x != st and st.endswith(x)), key=len, default=None)
        if short:
            drop = len(st[: -len(short)].encode("cp932", "replace"))
            off, slot, text = off + drop, slot - drop, text[len(st) - len(short) :]
        out.append((off, slot, text))
    return out


def plan():
    """([(lba, 오프셋, 원문, KR, 슬롯)], 넘치는 것, 정본에 없는 것)."""
    with open(CANON, encoding="utf-8") as f:
        canon = json.load(f)
    fit, over, none = [], [], []
    for group, (lba, size) in sorted(MON.items()):
        buf = bytes(extract(lba, size))
        for s, e in records(buf):
            for off, slot, jp in name_strings(buf, s, e):
                sfx = SUFFIX.search(jp)
                stem = jp[: sfx.start()] if sfx else jp
                tail = "".join(HALF.get(c, c) for c in (sfx.group() if sfx else ""))
                kr = canon.get(stem)
                if kr is None:
                    none.append((group, off, jp))
                    continue
                kr += tail
                # 🔴 **널 1개로는 부족하다**(2026-09-13, 마스터 QA 052 — "모래두더지Ｂ"
                # 뒤에 다음 엔트리 "모"가 잡음으로 그려짐). 원본은 전각 접미(2B)+널 2개인데
                # 우리 반각 접미(1B)로 1바이트가 남아, 이름이 슬롯을 거의 채우면(모래두더지
                # 5음절=10B) 그 1바이트가 **널 하나뿐**이 된다 — 종단 판정이 반각(2바이트)
                # 단위로 보이는 자리라 `41 00`(반각 'A'+널 1)을 0이 아닌 하프워드로 읽고
                # 다음 엔트리까지 그려버린다. **널 2개를 요구**해 이런 자리를 "초과"로
                # 밀어 재배치 경로(`relocate`)를 타게 한다.
                (fit if len(_enc(kr)) + 2 <= slot else over).append((lba, off, jp, kr, slot))
    return fit, over, none


def _dedup_over(over):
    """`over` 를 (lba,off) 로 중복 제거 — `records()`가 보스류 레코드를 두 겹으로 보는
    자리가 있어 같은 곳이 두 번 들어온다(main()·check_original_diff.py 공용 관용)."""
    by_lba = {}
    for lba, off, jp, kr, slot in over:
        by_lba.setdefault(lba, {})[off] = (off, jp, kr, slot)
    return by_lba


def relocation_ref_spans(lba):
    """이 lba에서 052 재배치가 실제로 고쳐 쓴 **명령어**(lui/addiu) 자리 — [(s,e)].

    `check_original_diff.py`가 재사용한다(2026-09-13, 마스터 QA 052 빌드 실패 — 이 자리는
    텍스트가 아니라 MIPS 명령어인데, 원본↔빌드 diff 게이트가 근처 스탯 바이트를 SJIS
    히라가나로 오디코드해 "혼재"로 오탐했다). 명령어 워드 자체를 타이트한 span 으로
    등록해 두면 그 게이트가 그리디 확장 대신 이 span 을 쓰게 되어 오탐이 사라진다.
    """
    _fit, over, _none = plan()
    moves = sorted(_dedup_over(over).get(lba, {}).values())
    if not moves:
        return []
    size = next(s for lb, s in MON.values() if lb == lba)
    orig = bytes(extract(lba, size))
    refs, _lui_use = _mon_overlay_refs(orig)
    spans = []
    for off, _jp, _kr, _slot in moves:
        for imm_off, lui_off, _op in refs.get(off, []):
            spans.append((imm_off, imm_off + 4))
            spans.append((lui_off, lui_off + 4))
    return spans


# 소환 메시지 뒤에 붙는 **독립 전각 접미** — (2026-09-14, 마스터 QA 053).
# `%c%s%c은(는) 동료를 불렀다.` 바로 뒤에 소환된 개체의 접미 글자만 단독 문자열로
# 남아 있다(이름표 스캔 밖 — DIALOG("%") 문자를 만나면 스캔이 끝나서 못 본다).
# 🔴 **전 버퍼 스캔은 안 한다**(2026-09-14 실측 — 스탯/포인터 이진 자료 안에서 우연히
# `82 60~63`(전각 A~D) 패턴과 일치하는 자리가 이미지 전체 기준 190곳이나 나와, 그중
# 8곳이 **완전한 이진 반복 구조**(같은 레코드가 여덟 번 되풀이)로 확인됐다 — 스캐너로는
# 텍스트와 자료를 못 가른다. 마스터가 몬스터 구간(0x560000~0x5a0000) 전각 A~D 14곳을
# 손으로 문맥까지 갈라 **좌표 둘**만 남겼다(나머지 4는 012 — 아직 미번역인 분열 메시지
# 안에 든 것이라 012 를 고치면 저절로 없어진다. 8은 이진 자료, 손대면 안 된다).
# ⇒ **KISS — 스캐너 대신 좌표 둘을 박는다.** 034 와 같은 방식으로 원본 바이트를
# assert 해 안전장치를 공짜로 얻는다.
STRAY_SUFFIX = (
    (1, 0xAC8, b"\x82\x63", b"D"),  # ED2MON1 — "동료를 불렀다." 뒤 Ｄ
    (1, 0xACC, b"\x82\x62", b"C"),  # 바로 이어 Ｃ
)


def fix_stray_fullwidth_suffix(buf, group):
    """buf(bytearray, 제자리 수정) 안의 STRAY_SUFFIX 좌표를 반각으로 — 고친 수 반환."""
    n = 0
    for g, off, full, half in STRAY_SUFFIX:
        if g != group:
            continue
        assert buf[off : off + 2] == full, (
            f"ED2MON{group} 소환 접미 슬롯 불일치 @0x{off:X}: {buf[off : off + 2].hex()} != {full.hex()}"
        )
        buf[off] = half[0]
        buf[off + 1] = 0
        n += 1
    return n


# 슬라임 분열 메시지 — (2026-09-14, 마스터 QA 012). ED2MON0 안에 "%cAと%cBになった。"
# (A·B 로 분열했다) 다음에 분열 변형 넷(Ａ’·Ａ”·Ｂ’·Ｂ”)이 **이름 중간에 색전환 %c 가
# 낀 채로**(`赤スラ%c%cイムＡ’` — "スラ"와 "イム" 사이) 따로 있다. `name_strings()`는
# DIALOG("%")를 만나면 스캔을 끝내 이 넷을 못 본다 — 같은 어간의 **일반** 변형(Ａ·Ｂ, %c
# 없이 매끈한 것)은 이미 정상 번역돼 있으니(레코드 표), 그 결과를 그대로 본뜬다.
# ⚠ **직접 좌표 패치다** — 이 넷은 이름표 스캔 경로 밖이라 `plan()`이 원리상 못 본다.
# 슬롯 안에 들어가므로(19/17B ≤ 24/20B) 재배치도 필요 없다.
SPLIT_SLIME_MSGS = (
    # (group, off, 원본 바이트, 새 바이트)
    (
        0,
        0x1DC,
        bytes.fromhex("2563 90d4 8358 8389 2563 2563 8343 8380 8260 8166 2563".replace(" ", "")),
        bytes.fromhex("2563 8dd1 90b8 8f5c 8bf1 2563 2563 90d1 4181 6625 63".replace(" ", "")),
    ),
    (
        0,
        0x1F4,
        bytes.fromhex("2563 90d4 8358 8389 8343 8380 8260 8168 2563".replace(" ", "")),
        bytes.fromhex("2563 8dd1 90b8 8f5c 8bf1 90d1 4181 6825 63".replace(" ", "")),
    ),
    (
        0,
        0x208,
        bytes.fromhex("2563 90d4 8358 8389 2563 2563 8343 8380 8261 8166 2563".replace(" ", "")),
        bytes.fromhex("2563 8dd1 90b8 8f5c 8bf1 2563 2563 90d1 4281 6625 63".replace(" ", "")),
    ),
    (
        0,
        0x220,
        bytes.fromhex("2563 90d4 8358 8389 8343 8380 8261 8168 2563".replace(" ", "")),
        bytes.fromhex("2563 8dd1 90b8 8f5c 8bf1 90d1 4281 6825 63".replace(" ", "")),
    ),
)


# "A와B가 되었다" — 원문 `と`(붙여쓰기, 일본어는 공백이 없어도 된다)를 그대로 옮겨
# "A와B"로 붙어 나갔다(마스터 QA 2026-09-14, 012 화면 확인 중 발견). 한국어는 "A와 B"로
# 띄어 쓴다.
# 🔴 **이 함수를 이 스크립트 자기 루프 안에서 부르지 않는다** — `patch_ed2_monster_lines.py`
# 가 뒤에 돌면서 같은 자리("と"→"와")를 **자기 대사 스캔으로 다시 번역**해 공백을
# 지운다(2026-09-14 실측: 여기서 공백을 넣어도 뒤 스크립트가 "90 6c 00 00"으로 되쓴다).
# ⇒ **build.py 맨 끝에서, 두 스크립트가 다 돈 뒤 한 번만** 부른다(아래 `finalize_connector_space`).
# 그 시점엔 "82 c6"(미번역) 이든 "90 6c"(번역됨) 이든 이미 결정돼 있으니 **둘 다 받는다.**
CONNECTOR_SPACE = ((0, 0x1B8, {b"\x82\xc6", b"\x90\x6c"}, b"\x90\x6c\x20"),)  # ED2MON0 — 와 뒤 공백


def finalize_connector_space():
    """build.py 맨 끝에서 한 번 — CONNECTOR_SPACE 자리에 공백을 끼운다(이미 끼워져
    있으면 조용히 넘어간다 — 멱등). 고친 수 반환."""
    n = 0
    for group, off, jp_variants, kr in CONNECTOR_SPACE:
        lba, size = MON[group]
        cap = (size + 2047) // 2048 * 2048
        buf = bytearray(extract(lba, cap, path=IMG))
        if buf[off : off + len(kr)] == kr:
            continue  # 이미 공백까지 들어가 있다(재실행 등) — 멱등
        cur = bytes(buf[off : off + 2])
        assert cur in jp_variants, f"ED2MON{group} 접속사 슬롯 불일치 @0x{off:X}: {cur.hex()}"
        assert buf[off + 2 : off + len(kr)] == b"\x00" * (len(kr) - 2), (
            f"ED2MON{group} 접속사 뒤 여유 없음 @0x{off:X}"
        )
        buf[off : off + len(kr)] = kr
        with open(IMG, "r+b") as f:
            write_user_data(f, lba, bytes(buf), label=f"ED2MON{group} 접속사 공백")
        n += 1
    return n


def fix_split_slime_msgs(buf, group):
    """buf(bytearray, 제자리 수정) 안의 SPLIT_SLIME_MSGS 좌표를 번역 — 고친 수 반환."""
    n = 0
    for g, off, jp, kr in SPLIT_SLIME_MSGS:
        if g != group:
            continue
        assert buf[off : off + len(jp)] == jp, (
            f"ED2MON{group} 분열 메시지 슬롯 불일치 @0x{off:X}: {buf[off : off + len(jp)].hex()}"
        )
        buf[off : off + len(jp)] = kr.ljust(len(jp), b"\x00")
        n += 1
    return n


def main():
    fit, over, none = plan()
    if "--plan" in sys.argv:
        for _lba, off, jp, kr, slot in fit:
            print(f"  {off:#07x} [{slot:>3}B] {jp} → {kr}")
        # ⚠ **실제 재배치와 같은 중복 제거를 쓴다**(`_dedup_over`) — 여기서 다르게 세면
        # 계획과 실행이 어긋난다(`records()`가 보스류 레코드를 두 겹으로 보는 자리가 있다).
        seen_over = {(lba, off): v for lba, d in _dedup_over(over).items() for off, v in d.items()}
        for off, jp, kr, slot in sorted(seen_over.values()):
            print(f"  ⚠ 넘침 {off:#07x} [{slot}B] {jp} → {kr} ({len(_enc(kr)) + 2}B 필요)")
        for group, off, jp in none:
            print(f"  ⚠ 정본에 없음 ED2MON{group} {off:#07x} {jp}")
        print(f"\n제자리 {len(fit)} · 넘침 {len(seen_over)}(중복제거 전 {len(over)}) · 정본에 없음 {len(none)}")
        return 0

    by_lba = {}
    for lba, off, _jp, kr, slot in fit:
        by_lba.setdefault(lba, []).append((off, kr, slot))
    over_by_lba = _dedup_over(over)
    total = 0
    moved_total = 0
    patch_total = 0
    for group, (lba, size) in sorted(MON.items()):
        cap = (size + 2047) // 2048 * 2048
        buf = bytearray(extract(lba, cap, path=IMG))  # 섹터 정렬 크기로 읽는다(꼬리 여유 보존)
        n_stray = fix_stray_fullwidth_suffix(buf, group) + fix_split_slime_msgs(buf, group)
        patch_total += n_stray
        if lba not in by_lba and lba not in over_by_lba:
            if n_stray:
                with open(IMG, "r+b") as f:
                    total += write_user_data(f, lba, bytes(buf), label=f"ED2MON{group} 전각 접미 정리")
            continue
        for off, kr, slot in by_lba.get(lba, []):
            b = _enc(kr) + b"\x00"
            buf[off : off + slot] = b + b"\x00" * (slot - len(b))
        moves = sorted(over_by_lba.get(lba, {}).values())
        content_len = size
        if moves:
            # ⚠ **`_relocate`의 자연스러운 1널 종단으로 충분하다**(2026-09-14 정정 —
            # 마스터가 원본 전수로 확인: 재배치 안 된 정상 항목(토프스·레밍플러스 등)도
            # 전부 `XX 00` 하나뿐이다. 이전에 "2널이 필요하다"고 보고 반각 공백을 끼워
            # 넣었던 시도는 **그 자체가 새 결함**이었다 — 공백(0x20)이 이름 뒤 종단
            # 자리를 차지해 "모래두더지A " 처럼 화면에 빈칸이 보이고, 정렬상 널이
            # 아예 없던 두 자리(모래두더지C·육지해파리B)는 종단 자체가 사라져 뒤 자료를
            # 그대로 그렸다. `_relocate`를 있는 그대로 쓴다 — 재구현하지 않는다).
            # ⚠ **"실제 쓰인 끝" 뒤에 붙인다** — cap 그대로 넘기면 `_relocate`가 널 패딩
            # 전부를 "이미 쓰인 것"으로 보고 그 뒤에 이어 붙여 섹터를 넘긴다
            # (patch_ed2_monster_lines._apply_sha_table 과 같은 관용, 2026-09-13 실측).
            used = max((k for k in range(len(buf) - 1, -1, -1) if buf[k]), default=-1) + 1
            used = (used + 3) & ~3
            orig = bytes(extract(lba, size))  # overlay_refs 대조 기준(원본, 빌드 아님)
            new_buf, _touched = _mon_lines_relocate(bytes(buf[:used]), orig, moves)
            content_len = len(new_buf)  # 논리 길이 — 디렉터리 크기는 이걸 쓴다(cap 이 아니다)
            assert content_len <= cap, f"ED2MON{group}: 재배치 꼬리가 섹터 여유({cap}B)를 넘었다"
            buf = bytearray(new_buf.ljust(cap, b"\x00"))
            moved_total += len(moves)
        with open(IMG, "r+b") as f:
            total += write_user_data(f, lba, bytes(buf), label=f"ED2MON{group} 몬스터 이름")
            if content_len != size:
                # ⚠ **뒤에 도는 `patch_ed2_monster_lines.py` 가 이 lba 를 안 건드리면**(이
                # 그룹에 대사 재배치가 하나도 없으면) 디렉터리 크기가 여기서 안 갱신된 채
                # 남는다 — 우리가 늘렸으면 우리가 직접 갱신한다(같은 함수 재사용, 재구현 아님).
                _mon_lines_update_dir_size(f, group, content_len)
    if moved_total:
        print(f"  이름 슬롯 초과 {moved_total}건 → 꼬리로 재배치")
    if patch_total:
        print(f"  좌표 직접 패치 {patch_total}건(053·012)")
    print(
        f"ED2MON: 섹터 {total}개 수정 — 몬스터 이름 {len(fit)}건 제자리"
        f" (재배치 {moved_total} · 좌표 패치 {patch_total} · 정본에 없음 {len(none)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
