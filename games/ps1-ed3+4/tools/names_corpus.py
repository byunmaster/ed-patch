"""공용 이름 검사 어댑터 — **ED3 문안 전체**를 `(자리, 원문 줄, 우리 줄|None, 갈래)` 로 낸다.

    python3 scripts/check/check_names.py --game ps1-ed3+4 --list

🔴 **이름을 안 든다**(마스터 2026-10-07). 정본은 `shared/canon`(잣대 `canon/names.py` + 고유명사 `canon/nouns/ed3.json`)
이 보고, 여기는 **원문을 읽어 우리 줄과 짝짓기만** 한다.

⚠ **ED3 디스크만이다**(`TITLE = "ed3"`). ED4 고유명사는 정본 `nouns/ed4.json` 에 있으나 ED4 는 보류(마스터 2026-09-15) — 열 때 어댑터를 디스크별로 가른다.

## 두 층

- **씬 대사** — `script.members("ed3")`(원본 ISO 에서 그 자리에서 푼 조각 원문)와 `script.load("ed3")`
  (커밋된 번역 정본). 번역 안 된 조각은 **None** 으로 낸다(분모가 거짓말을 안 하게 — 지금 165/33,975줄).
- **UI 문안**(메뉴·HUD·전투·시스템 메시지·주문 설명·메모) — `uitext.sites("ed3")`(실행파일에서 푼 원문)와
  `uitext.load("ed3")`(커밋된 정본). 미번역은 None.

- **실행파일 낱말·문장 풀**(`exe:0x…`) — 표·빈틈의 닻을 가리지 않고 구역의 읽히는 문자열 전부. UI 정본에 든 것은 위 `ui:` 로 이미 나오니 뺀다.

🔴 **안 보는 구간**(어댑터가 못 닿는 곳):
- 그림 속 글(타이틀·오프닝·엔딩·크레딧 — `narration_ed3.json` 은 우리 문안만 있고 원문은 그림이다).
- 타이틀 「이어서 하기」 화면(BIOS 폰트 — SLPS 의 슬롯 지명 표는 `patch_title_font` 가 사전으로 채운다).
- 대사 밖 이름이 **그림으로만** 나오는 자리.

⚠ **원본 이미지가 있어야 돈다**(빌드는 불필요) — 원문은 디스크에서, 우리 문안은 커밋된 JSON 에서 온다.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import script as S
import uitext as U

TITLE = "ed3"  # 작품 정본 — shared/canon/nouns/ed3.json (ED3 디스크만)
_DISC = "ed3"
CANON_GATE = True  # 정본(shared/canon) 어긋남을 실패로 친다 — 사전 적용 2단계 전환 끝(10-08)
DIALOG, SLOT = "dialog", "slot"  # 갈래 — 대사는 지명 띄어쓰기까지 잰다, UI(표·메뉴·이름 칸)는 무시한다(마스터 10-07)


def _scene_pairs():
    canon = S.load(_DISC)
    for archive, member, segs in S.members(_DISC):
        have = canon.get((archive, member), {})
        key = S.key_of(archive, member)
        for i, jp in segs:
            if not jp.strip():
                continue
            kr = have.get(i, {}).get("kr")
            yield f"scn:{key}[{i}]", jp, (kr or None), DIALOG


def _ui_pairs():
    _, sites = U.sites(_DISC)
    have = U.load(_DISC)
    for off, s in sorted(sites.items()):
        kr = have.get(off, {}).get("kr")
        yield f"ui:0x{off:06X}", s["jp"], (kr or None), SLOT


def _exe_pairs():
    """실행파일 **낱말·문장 풀** 전체 중 UI 정본이 안 든 것 — 월드맵 장소 패널(`ディーネ`)이 이 분모 밖이라 검사를 빠져나갔다(마스터 실기 10-08).

    표가 가리키든 안 가리키든(빈틈의 닻 포함) 구역(`dump_names.REGIONS`)의 **읽히는 문자열**(미해독 한자 `�` 가 없는 것)을 낸다.
    우리 줄은 사전 값(없으면 None = 미번역 분모). 이름 갈래(person·item·spell·monster·place·rank)와 읽을거리(menu·text)를 같이 센다.
    """
    import importlib.util
    import struct

    import dump_names
    import exetext
    import textenc

    # ⚠ 공용 검사기 경로엔 옛 패키지 `shared/glossary` 가 있어 이름 `glossary` 가 가려질 수 있다 — 게임 쪽 모듈은 경로로 연다.
    spec = importlib.util.spec_from_file_location("ed3_glossary", os.path.join(os.path.dirname(os.path.abspath(__file__)), "glossary.py"))
    glossary = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(glossary)

    exe = U.exe_bytes(_DISC)
    _, sites = U.sites(_DISC)
    words = dict(glossary.flat(_DISC))
    reg = sorted(dump_names.REGIONS[_DISC].items())
    for i, (st, kind) in enumerate(reg):
        if kind == "noise":
            continue
        end = reg[i + 1][0] if i + 1 < len(reg) else st + 0x400
        p = st
        while p < end:
            codes, _t = exetext.raw_string(exe, p)
            if codes is None:
                break
            if codes and p not in sites:
                jp = textenc.decode(codes, _DISC)
                if jp.strip() and "�" not in jp:
                    yield f"exe:0x{p:06X}", jp, (words.get(jp) or None), SLOT
            p += 2 * (len(codes) + 1)
            while p < end and exetext.is_term(struct.unpack_from("<H", exe, p)[0]):
                p += 2


def pairs():
    """[(자리, 원문 줄, 우리 줄|None, 갈래)] — ED3 문안 전체. 미번역 줄도 None. 갈래: 씬 대사 dialog · UI 문안 slot · 실행파일 낱말 풀 slot."""
    yield from _scene_pairs()
    yield from _ui_pairs()
    yield from _exe_pairs()
