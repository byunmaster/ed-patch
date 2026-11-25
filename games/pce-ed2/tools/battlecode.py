"""본편 밖 패키지(배틀 테스트 씬 16·17 — 개발자 전투 시험 장면)의 코드 영역 일본어 문장 — 본편 번역 파이프라인(`package.CLEAN`)을 타지 않아 따로 쓴다.

같은 문장이 본편 코드(514·386·1026)에서는 `codestr.SPECS` 로 번역돼 있다 — 같은 문안·같은 틀(0xFF 패딩으로 옮기고 BIT 포인터만 돌린다)을 그대로 쓴다.
글자는 정적 풀에 들어가야 한다(지역 글리프 없음) — `collect` 가 수집 단계에서 글자를 풀에 넣는다. 11-06 일본어 런 게이트 확대에서 발견(관리자 지시: 미번역은 객관 결함).
"""

import codestr
import common
from codestr import END, NAME, NUM, STYLE, Spec

SPECS = (
    # 씬 16(rel 2050): 「{이름}が共鳴している」 — 514 와 같은 문장·같은 문안
    Spec(2050, 0xDE, 0x147, 18, "4ecdd74481b6", 0x1FE, (NAME, "이(가) 공명하고 있다.", END)),
    # 씬 17(rel 2178): 「防御力が▢ ▢さがった」 — 386·514·1026 과 같은 문안. 패딩 0x2E1(31B)
    Spec(2178, 0x2AF, 0x2B2, 23, "b9a5afb4d8a1", 0x2E1, ("방어력이", STYLE, NUM, " 내려갔다.", END)),
)


def collect(tab) -> None:
    """수집 단계 — 이 문장들의 글자를 정적 풀에 넣는다."""
    for sp in SPECS:
        for p in codestr._flat(sp):
            if isinstance(p, str):
                tab.enc(p)


def apply(w, tab) -> None:
    for rel in sorted({sp.rel for sp in SPECS}):
        pkg = common.track_data(rel, 128)
        nb = bytearray(pkg)
        codestr.apply(rel, pkg, nb, tab, SPECS)
        i = 0
        while i < len(pkg):  # 바뀐 덩이마다 한 번씩 쓴다(쓰기 장부 · 무변경 대조)
            if nb[i] == pkg[i]:
                i += 1
                continue
            j = i
            while j < len(pkg) and (nb[j] != pkg[j] or (j + 1 < len(pkg) and nb[j + 1] != pkg[j + 1])):
                j += 1
            w.put(rel * common.USER + i, bytes(nb[i:j]), bytes(pkg[i:j]), f"배틀 테스트 코드 문장 {rel}+{i:#x}")
            i = j
