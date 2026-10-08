"""공용 이름 검사 어댑터 — **ED3 문안 전체**를 `(자리, 원문 줄, 우리 줄|None, 갈래)` 로 낸다.

    python3 scripts/check/check_names.py --game ps1-ed3+4 --list

🔴 **이름을 안 든다**(마스터 2026-10-07). 사전은 `shared/glossary/names.py` + `shared/glossary/ed3.json`
이 보고, 여기는 **원문을 읽어 우리 줄과 짝짓기만** 한다.

⚠ **ED3 디스크만이다.** `shared/glossary/ed3.json` 만 있고 ED4 사전은 아직 없다(`TITLE = "ed3"`).
ED4 는 보류(마스터 2026-09-15)이기도 하다 — ED4 사전이 생기면 어댑터를 디스크별로 가른다.

## 두 층

- **씬 대사** — `script.members("ed3")`(원본 ISO 에서 그 자리에서 푼 조각 원문)와 `script.load("ed3")`
  (커밋된 번역 정본). 번역 안 된 조각은 **None** 으로 낸다(분모가 거짓말을 안 하게 — 지금 165/33,975줄).
- **UI 문안**(메뉴·HUD·전투·시스템 메시지·주문 설명·메모) — `uitext.sites("ed3")`(실행파일에서 푼 원문)와
  `uitext.load("ed3")`(커밋된 정본). 미번역은 None.

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

TITLE = "ed3"  # 작품 사전 — shared/glossary/ed3.json (ED3 디스크만)
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


def pairs():
    """[(자리, 원문 줄, 우리 줄|None, 갈래)] — ED3 문안 전체. 미번역 줄도 None. 갈래: 씬 대사 dialog · UI 문안 slot."""
    yield from _scene_pairs()
    yield from _ui_pairs()
