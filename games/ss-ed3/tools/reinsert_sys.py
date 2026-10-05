"""본체·시스템 문자열을 이미지에 써 넣는다 — **NUL 종료 문자열**.

    python3 games/ss-ed3/tools/reinsert_sys.py --check

대사(`reinsert.py`)와 규칙이 다르다. 여기는 표라서 **문자열마다 종료 NUL 이 있고 뒤에
패딩이 따라온다** — 그래서 원문보다 **조금 길어져도 된다**:

    예산 = 원문 바이트 + (뒤따르는 NUL 개수 − 1)     ← 종료자 1개는 반드시 남긴다

⚠ 늘리는 건 **패딩 안에서만**이다. 넘치면 다음 문자열의 첫 바이트를 먹고, 그 문자열을
   가리키는 포인터는 그대로라 **화면에만 엉뚱한 글자가 나온다.**
🔴 **포인터는 안 고친다** — 문자열 **시작 위치를 안 옮기기** 때문이다. 옮기기 시작하면
   `/0.BIN` 안의 BE32 132 곳을 전부 다시 계산해야 한다(`docs/status.md` 3절).

문안은 `script/system.json` — **자체 번역**이다. 고유명사 정본(`glossary_manual.json`)과
자리가 다르다: 정발 표기를 따르는 건 고유명사뿐이고, 대사·챕터는 우리가 옮긴다
(유저 확정 2026-08-24).
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import hangul_map as H
import strtab as S

SYSTEM = os.path.join(C.GAME_DIR, "script", "system.json")
# ⚠ **인명·지명 표는 안 고친다.** 그 이름들은 **대사 안에서** 쓰이므로 표만 고치면
#   대사와 갈린다 — 대사 쪽이 정본이다. 그래서 여기 오는 건 화면 문구뿐이다.


def table():
    """`{JP: KR}` — `script/system.json` 의 모든 갈래를 합친다(`_` 로 시작하는 키는 뺀다)."""
    if not os.path.exists(SYSTEM):
        return {}
    with open(SYSTEM, encoding="utf-8") as f:
        doc = json.load(f)
    out = {}
    for k, v in doc.items():
        if not k.startswith("_") and isinstance(v, dict):
            out.update(v)
    return out


def chapter_keys():
    """메뉴 맨 위 **챕터 바**에 나가는 JP 키 — 내린 판을 쓰되 이유가 다르다(아래 🔴)."""
    if not os.path.exists(SYSTEM):
        return set()
    with open(SYSTEM, encoding="utf-8") as f:
        return set(json.load(f).get("chapter", {}))


#   🔴 **시스템 표는 0 행을 자르는 창(스탯)에 나간다** — 그래서 기본이 아니라 **한 행 내린
#     판**으로 인코딩한다(`hangul_map.LOW_PATH`). 안 그러면 초성 윗 가로획이 날아간다.
#   🔴 **챕터 바도 내린 판이다**(마스터 10-05 「장 카드가 위 1px 아래 2px — 위 2 아래 1 이어야」).
#     챕터 바는 0 행을 안 자르니 기본 글리프(위 2·아래 1)로 두었는데(09-03), 그 뒤 전투 배너 글자를
#     1px 올린 패치(`patch_ui_center.TEXT_Y`, 09-30)가 **같은 그리기 함수라 챕터 바도 1px 올렸다.**
#     ⇒ 챕터 바 글자를 내린 판으로 보내 그 1px 을 상쇄한다(위 2·아래 1 로 복귀).
def encoder(jp, low=None, chapters=None):
    """그 문자열을 인코딩하는 함수 — 시스템 표 전부 내린 판(챕터 바 포함)."""
    if low:
        return lambda t: H.encode_kr(t, table={**H.load(), **low})
    return H.encode_kr


def budget(data, s):
    """그 문자열이 쓸 수 있는 바이트 — 뒤따르는 NUL 패딩까지, 종료자 1개는 남긴다."""
    e = s["off"] + len(s["raw"])
    pad = 0
    while e + pad < len(data) and data[e + pad] == 0:
        pad += 1
    return len(s["raw"]) + max(0, pad - 1)


_LEAD = re.compile(r"^(?:<[0-9A-F]{2}>)+")


def split_lead(text):
    """선행 **제어 표기**(`<09>` 등)와 몸통을 가른다. 제어는 그대로 두고 몸통만 바꾼다.

    ⚠ 이게 없으면 **한 자리를 조용히 놓친다** — 최종장이 `<09>最終章…` 꼴이라 표의 키와
    안 맞았다(실측 7/8).
    🔴 **들여쓰기 공백은 몸통에 남긴다**(2026-08-25). 안내 문구는 앞 공백으로 **중앙 정렬**을
    하는데, 한국어는 길이가 달라 원문 들여쓰기를 그대로 쓰면 정렬이 틀어진다. 게다가
    예산이 빡빡해(여유 1B 인 자리도 있다) **들여쓰기를 줄여 몸통을 늘려야** 하는 경우가
    있다 — 그러려면 공백이 우리 손에 있어야 한다. 그래서 키도 값도 **공백을 포함**한다.
    """
    m = _LEAD.match(text)
    return (m.group(0), text[m.end() :]) if m else ("", text)


#   🔴 **예산이 모자란 문자열은 옮겨 쓴다**(마스터 10-05 「재배치로 가자. 최대한 원문을 살려야지」). 자리 뒤에 다른 문자열이 바로 붙어
#   제자리 확장이 안 되는 것 — 그 문자열을 가리키는 **포인터가 하나뿐**이면 죽은 디버그 메뉴 구역의 칸으로 옮기고 포인터만 바꾼다
#   (원자리는 NUL 로 비운다). 칸은 `subtitle_stub.RELOC`(32B) — 크레딧 코드 구역이 그 앞에서 끝나게 단언이 지킨다.
#   ⚠ 포인터가 하나가 아니면 멈춘다 — 다른 데서 읽는 포인터를 놓치면 **옛 자리를 읽어 빈 문자열**이 나온다.
RELOC_AT = 0x06018A10
RELOC_LEN = 32
RELOCATABLE = {"/0.BIN": ("戦闘に勝った！\x00",)}  # 화면에 나가는 문구라 원문을 살리려고 옮기는 것들(키 = JP 원문 + 종결자)


def _relocate(out, s, raw, base):
    """문자열 `s` 를 `RELOC_AT` 로 옮기고 그 포인터 하나를 바꾼다. 못 하면 `None`(사유)."""
    if len(raw) + 1 > RELOC_LEN:
        return f"옮길 칸({RELOC_LEN}B)보다 길다({len(raw) + 1}B)"
    if base is None:
        return "포인터 베이스를 모른다"
    old = (base + s["off"]).to_bytes(4, "big")
    refs = [i for i in range(0, len(out) - 3, 4) if out[i : i + 4] == old]
    if len(refs) != 1:
        return f"포인터가 {len(refs)}개다(하나여야 한다)"
    at = RELOC_AT - base
    out[at : at + RELOC_LEN] = raw + b"\x00" * (RELOC_LEN - len(raw))
    out[refs[0] : refs[0] + 4] = RELOC_AT.to_bytes(4, "big")
    return None


def patch(data, name, tbl):
    """`(새 bytes, 넣은 수, [(JP, 사유)])` — 파일 크기 불변."""
    out = bytearray(data)
    done, bad = 0, []
    seen = set()
    low, chapters = H.load_low(), chapter_keys()
    for s in S.strings(data, S.load_base(name)):
        lead, jp = split_lead(S.text_of(s["raw"]))
        kr = tbl.get(jp)
        if kr is None:
            continue
        seen.add(jp)
        raw = encoder(jp, low, chapters)(lead + kr)
        b = budget(data, s)
        if len(raw) > b:
            if jp + "\x00" in RELOCATABLE.get(name, ()):
                why = _relocate(out, s, raw, S.load_base(name))
                if why is None:
                    out[s["off"] : s["off"] + b + 1] = b"\x00" * (b + 1)  # 원자리는 비운다
                    done += 1
                    continue
                bad.append((jp, f"예산 {b}B 를 {len(raw) - b}B 넘고 옮길 수도 없다: {why}"))
                continue
            bad.append((jp, f"예산 {b}B 를 {len(raw) - b}B 넘는다"))
            continue
        # 남는 자리는 NUL 로 덮는다 — 원문 꼬리가 남으면 화면에 붙어 나온다.
        # ⚠ **덮는 구간은 예산 전체(`b`) + 종료자**다. `len(raw)+1` 만 덮으면 문안이 그보다
        #   길 때 뒤를 밀어내 **파일이 커진다**(실측 2026-08-25: 3B 늘어 단언이 울었다).
        span = b + 1
        out[s["off"] : s["off"] + span] = raw + b"\x00" * (span - len(raw))
        done += 1
    # ── 파서가 못 본 자리를 한 번 더 ────────────────────────────────────────────
    # ⚠ `strtab` 은 **NUL 로 끊고 선행 제어를 벗기는** 파서라, 앞에 길이 바이트(`0x06` 등)가
    #   붙은 표를 지나친다(실측: 스탯의 `経験値`). 「몇 바이트 넘기고 다시 본다」로 파서를
    #   넓히는 건 **이미 재 보고 버린 길**이다 — 마커 0.6% 얻고 쓰레기 2,633 개를 얻는다
    #   (`docs/status.md` 3 절). 그래서 파서는 그대로 두고, **표에 있는데 못 찾은 것만**
    #   그 바이트열 그대로 뒤져 넣는다. 찾는 대상이 이미 정해져 있으니 오탐이 안 는다.
    #   🔴 **긴 것부터 넣는다.** 짧은 항목이 먼저 들어가면 그것을 품는 **긴 문자열이
    #     더는 안 걸린다** — 실측 2026-08-31: `売りました。` 가 먼저 박혀
    #     `%sを<0D>売りました。` 가 못 붙었고, 화면에 **「약초を 팔았습니다.」** 로 나왔다.
    for jp, kr in sorted(tbl.items(), key=lambda kv: -len(kv[0])):
        #   🔴 **`seen` 으로 거르면 안 된다.** 앞 단계가 그 문자열을 **한 자리에서** 바꿨다고
        #     해서 다른 자리까지 바뀐 게 아니다 — 같은 이름이 표 여럿에 들어 있다.
        #     실측 2026-08-27: `/0.BIN` 0x76c60 의 이름 목록에서 `クリス`·`シャーラ` 는
        #     바뀌었는데 **`ジュリオ` 만 일본어로 남아** HP 창에 그대로 떴다(유저 스크린샷).
        #     앞 단계가 이미 바꾼 자리는 **그 바이트열이 없어져** 여기서 안 걸린다 —
        #     그러니 전부 훑어도 두 번 바뀌지 않는다.
        _ = seen
        # ⚠ 종료자는 NUL 만이 아니다 — 메시지 계열은 0x10(끝) · 0x0F(페이지)로
        #   닫는다. 그래서 **키에 종료자까지 적고** 여기서는 그 바이트열 그대로 찾는다.
        pat = jp.encode("shift_jis")
        if not pat.endswith((b"\x00", b"\x10", b"\x0f")):
            pat += b"\x00"
        raw = encoder(jp, low, chapters)(kr)
        at = out.find(pat)
        while at >= 0:
            pad = 0
            while at + len(pat) + pad < len(out) and out[at + len(pat) + pad] == 0:
                pad += 1
            span = len(pat) + pad  # 이 만큼이 우리 자리(종료자 + 뒤 패딩까지)
            room = span - 1  # 종료자 한 개는 남긴다
            if len(raw) <= room:
                # ⚠ **교체 길이는 `span` 이다** — 예산(`room`)만 보고 `len(pat)` 만큼 덮으면
                #   문안이 그보다 길 때 파일이 늘어난다(실측: 3B 늘어 단언이 울었다).
                out[at : at + span] = raw + b"\x00" * (span - len(raw))
                done += 1
            else:
                bad.append((jp, f"예산 {room}B 를 {len(raw) - room}B 넘는다"))
            at = out.find(pat, at + span)

    assert len(out) == len(data), (len(out), len(data))
    return bytes(out), done, bad


FILES = ("/0.BIN", "/RLTPRG.BIN", "/BLACK.BIN")


def terminator_mismatch(tbl):
    """**원문은 있는데 종결 바이트가 안 맞아** 안 붙는 키들.

    🔴 이게 없으면 키 하나가 **조용히 안 붙는다.** 실측 2026-08-31:
      `経験値%dと\r%dゴアを手に入れた！` 에 `\x10` 을 빼먹었더니 폴백이 찾는 바이트열이
      `…！\x00` 이 되어 못 찾았고, 그 문자열을 **품고 있던 짧은 키**
      (`%dゴアを手に入れた！\x10`)가 뒷부분만 먹어 화면에 **「経験値２０と / 7 고아를
      얻었다!」** 로 나왔다. 빌드도 게이트도 초록이었다 — 「넣음 N」만 세고
      **무엇이 안 들어갔는지**를 안 봤기 때문이다.

    ⓘ 「어디에도 없는 키」는 안 센다 — `chapter_line`·`word` 처럼 **MAP 쪽 문안**이
      같은 파일에 섞여 있어 늘 빨간불이 된다. 여기서 보는 건 **이 파일에 원문이
      분명히 있는데 안 붙는** 자리뿐이다.
    """
    out = []
    with C.open_disc(1) as d:
        raws = {}
        for n, lba, size in d.files():
            if n in FILES:
                raws[n] = d.read_extent(lba, size)
    for jp in tbl:
        _, body = split_lead(jp)
        try:
            txt = body.encode("shift_jis")
        except UnicodeEncodeError:
            continue
        pat = txt if txt[-1:] in (b"\x00", b"\x10", b"\x0f") else txt + b"\x00"
        #   ⚠ **어느 파일에서도** 정확 일치가 없을 때만 운다 — 한 파일에 긴 낱말의
        #     일부로만 들어 있는 경우가 있다(`ルーレ` ⊂ `ルーレット`).
        where = [n for n, b in raws.items() if txt in b]
        if where and not any(pat in b for b in raws.values()):
            out.append((where[0], jp))
    return out


def main():
    tbl = table()
    if not tbl:
        print("⏭ 넣을 문안이 없다 (script/system.json)")
        return
    done = 0
    bad = []
    with C.open_disc(1) as d:
        for n, lba, size in d.files():
            if n not in FILES:
                continue
            b = d.read_extent(lba, size)
            _, k, err = patch(b, n, tbl)
            done += k
            bad += err
    miss = terminator_mismatch(tbl)
    print(f"문안 {len(tbl)}  넣음 {done}  실패 {len(bad)}  종결 안 맞음 {len(miss)}")
    for jp, why in bad:
        print(f"  ❌ {jp!r} — {why}")
    for n, jp in miss:
        print(f"  ❌ {n} 에 원문은 있는데 안 붙는다 (종결 바이트) — {jp!r}")
    if bad or miss:
        raise SystemExit(1)
    print("✅ 전부 들어간다")


if __name__ == "__main__":
    main()
