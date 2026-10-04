#!/usr/bin/env python3
"""사본 개수 게이트 — "고치는 원본 바이트열이 이미지에 N곳인데 바뀐 게 N곳 미만이면 실패".

오늘 하루(2026-09-15) 일곱 번 겪은 사고의 공통 축: **사본이 둘 이상인데 하나만
고쳤다**(034 상태 라벨 · 051 전각/반각 지명 · 012 접속사 공백 · ED2.EXE 미검사 ·
반각 글리프 표 ED2.EXE 사본 · ED1SCN5 재배치 전 죽은 사본에 씀). `lui`/`addiu` 참조
추적은 SCN 데이터(텍스트+포인터가 섞여 있다)에선 우연히 다 걸려 못 쓴다(devlog
"⑧ SCN 데이터 구조에 코드용 도구를 그대로 대면 반대 결론이 난다"). **내용물을
직접 센다** — 오늘 마스터가 쓴 방법이다.

⚠ 이 게이트는 "지금 손대는 표들만"(글꼴 표 · 지명 슬롯) 다룬다 — 상태 라벨·아이템표는
이미 각자 개별 dual-copy 좌표를 명시적으로 assert 하고 있어 구조적으로 이미 안전하다
(034·058ⓐ). 전부를 이 게이트 하나로 일반화하는 건 다음 라운드 과제로 남긴다.

baseline: 각 항목의 "허용 잔존 개수"는 여기 상수에 이유와 함께 적는다 — 죽은 사본을
알고 남겨둔 것과 놓친 것을 구분해야 게이트가 계속 쓸모 있다.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hangul_map as H
from common import BUILD_DIR, extract

IMG = f"{BUILD_DIR}/Eiyuu Densetsu (KR).bin"


def _enc(s):
    return b"".join(H.encode_kr(c) for c in s)


# 065 — ED2SCN10·ED2SCN13 안 경로 라벨 원문(반각 JP). 마스터가 화면에서 "이슈타～이즈"를
# 보고 발견 — ED2.EXE 표는 이미 번역돼 있었는데 SCN 오버레이 안 사본을 놓쳤었다.
# ⚠ **ED2SCN10 은 재배치된 씬**이라 재배치 전 옛 정적 LBA(2233)에 **죽은 사본**이
# 그대로 남는다(ED1SCN5 와 같은 부류, 2026-09-15 확인) — 살아있는 재배치 후 LBA
# (`scn_layout.json`)만 고쳤고 죽은 옛 자리는 아무도 안 읽어 해가 없다. 그래서
# 허용치가 0이 아니라 **죽은 사본에서 나오는 개수**다(패턴마다 ED2SCN10 옛 자리
# 출현 횟수 — ED2SCN13 은 재배치가 안 된 씬이라 죽은 사본이 없다).
_ROUTE_LABEL_JP = (
    ("이슈타~이즈", bytes.fromhex("b2bcadc08160b2bddeb0"), 6),
    ("이슈타~아훌", bytes.fromhex("b2bcadc08160b1ccd9"), 0),
    ("이즈~성", bytes.fromhex("b2bddeb081608fe9"), 0),
    ("큐베라~성", bytes.fromhex("b7adcdded781608fe9"), 0),
    ("큐베라~윌", bytes.fromhex("b7adcdded78160b3b2d9"), 4),
    ("윌~베른", bytes.fromhex("b3b2d98160cdded9dd"), 0),
    ("아훌~성", bytes.fromhex("b1ccd981608fe9"), 0),
    ("윌~성", bytes.fromhex("b3b2d981608fe9"), 2),
    ("큐베라~프로스", bytes.fromhex("b7adcdded78160ccdfdbbd"), 6),
)
PATTERN_BASELINE = (
    *(
        (
            f"경로 라벨 원문(SCN 사본) — {name}",
            pat,
            dead_n,
            (
                "065 — ED2SCN10·ED2SCN13 살아있는 자리는 전량 번역 완료"
                "(patch_scn_route_labels). 허용치는 ED2SCN10 재배치 전 죽은 옛 LBA(2233)의"
                "출현 횟수 — 그 이상이면 세 번째(살아있는) 사본이 있다는 뜻이다."
            ),
        )
        for name, pat, dead_n in _ROUTE_LABEL_JP
    ),
)


def _place_name_jp2kr():
    """patch_scn_headers 가 쓰는 것과 같은 지명·인명 표 — 정본을 두 곳에 안 든다."""
    import patch_sys_ui as P

    jp2kr = {}
    for jp, kr in P.PLACES + P.SCN_PLACES + P._ed2_scn_places():
        jp2kr.setdefault(jp, kr)
    for jp, kr, _ in P.CHAR_NAMES:
        jp2kr.setdefault(jp, kr)
    return jp2kr


def check_place_name_jp_residual(data, *, verbose=False):
    """지명·인명 **전량**의 JP 원문이 이미지 전체에 몇 곳 남았나 — 명단이 아니라 내용 기준.

    마스터 QA(2026-09-15)로 ED2SCN7@0x885f 가 "죽었다"던 게 실은 살아 있던 게 드러난
    뒤 일반화 지시(관리자). `patch_scn_headers` 는 **씬별로** 구조 조건(①~⑥)에 맞는
    자리만 고친다 — 그 조건에 안 걸리는 자리가 있으면 이 스캔이 **이미지 전체**에서
    잡아낸다(분모를 "우리가 아는 자리"로 좁히지 않는다, 오늘의 반복 교훈).

    🔴 **진단 도구이지 게이트가 아니다** — 실제로 돌려 보니 96종 중 다수(특히 대사에
    자주 나오는 인물명 — セリオス 329·ゲイル 330·リュナン 182 등)가 수백 곳씩 잡힌다.
    ⚠ 처음엔 이 중 "슬롯형"(뒤에 널 4B+ 이어짐) 111곳이 진짜 미patch 자리일까 걱정했는데,
    **`_live_lba_of()` 로 라이브 LBA 교차검증하니 111 → 0** 이었다(전부 재배치로 버려진
    옛 LBA 안의 죽은 사본 — ED2SCN1 재배치 전 자리에 몰려 있었다). 검증 방법 자체도
    반대 방향(이미 번역된 "곶의동굴" KR 표기가 라이브 LBA 넷에 정확히 걸리는지)으로
    맞대봤다. ⇒ 96종 전부를 문맥 단위로 가르는 건 여전히 범위 밖이지만, **라이브 LBA
    필터만으로 잡음 대부분이 빠진다** — 새 증상을 만나면 이 목록에서 라이브만 추려
    먼저 본다. 이 함수는 **사람이 훑어볼 후보 목록**을 낸다.
    """
    jp2kr = _place_name_jp2kr()
    hits = []
    for jp, kr in jp2kr.items():
        jb = jp.encode("shift_jis")
        n = data.count(jb)
        if n:
            hits.append((jp, kr, jb, n))
    if verbose or hits:
        print(f"  ℹ 지명·인명 JP 원문 잔존 후보(전체 이미지 스캔, {len(jp2kr)}종 중, 게이트 아님):")
        if not hits:
            print("    없음")
        for jp, kr, jb, n in hits:
            print(f"    {jp!r}→{kr!r} — {n}곳 (0x{jb.hex()})")
    return hits


# ── 라이브 LBA 교차검증 — 재배치로 버려진 옛 사본을 죽은 것으로 걸러낸다 ──────────
_SECTOR = 2352
_USER_OFF = 24
_USER_SIZE = 2048


def _live_ranges():
    """{이름: (lba시작, 섹터수)} — SCN 전부 + ED.EXE·ED2.EXE. `_scn_layout()` 이 이미
    재배치 후 라이브 LBA만 준다 — 죽은 옛 LBA는 여기 안 나온다."""
    import patch_hangul_glyph_table as G
    import patch_sys_ui as P

    ranges = {}
    for name, lba, size in P._scn_layout():
        ranges[name] = (lba, -(-size // _USER_SIZE))
    for exe, (lba, size, _base) in G.EXES.items():
        ranges[exe] = (lba, -(-size // _USER_SIZE))
    return ranges


def _live_lba_of(raw_offset, ranges):
    """이미지 전체 바이트 오프셋 → 그 자리가 속한 라이브 파일 이름(없으면 None).

    ⚠ **정렬을 가정하지 않는다**(RE 실측 2026-09-15 — 0x885F 가 홀수 주소라 8B
    정렬 스캔에서 빠졌었다). `raw_offset // SECTOR` 는 섹터 경계와 무관하게 항상
    맞는 LBA 를 낸다 — sync/header/EDC 영역(사용자 데이터 밖)에 걸리면 파일이 없다.
    """
    lba = raw_offset // _SECTOR
    rem = raw_offset % _SECTOR
    if not (_USER_OFF <= rem < _USER_OFF + _USER_SIZE):
        return None
    for name, (start, n_sec) in ranges.items():
        if start <= lba < start + n_sec:
            return name
    return None


# 표기를 갈아 치운 이력 — "옛 표기가 남았나"는 JP 잔존 스캔이 원리적으로 못 본다
# (이미 한글이라서). ED2SCN7@0x885f 사고(마스터 QA 2026-09-15)로 처음 등록했다 —
# **표기를 바꿀 때마다 여기 한 줄 추가한다**(관리자 지시). 라이브 LBA 필터를 거치므로
# 재배치로 버려진 옛 사본은 자동으로 안 걸린다.
SUPERSEDED_SPELLINGS = (
    (
        "늑대의입",
        "늑대입",
        (
            "058 이전 축약형(전각 3음절, '의' 누락). 반각 10곳을 다 채운 뒤에도 ED2SCN7"
            "@0x885f 하나가 이 옛 표기인 채 라이브였다 — find_refs 가 SCN 자기 파일 안"
            "lui+addiu 만 봐서 EXE 쪽 참조를 놓쳤다(devlog ⑬)."
        ),
    ),
)


def check_superseded_spellings(data, *, verbose=False):
    """`SUPERSEDED_SPELLINGS` 에 등록된 옛 표기가 **라이브 자리**에 남았는지 — 0이어야 정상.

    `check_place_name_jp_residual` 의 반대편이다 — 그쪽은 "JP 원문이 남았나"(아직
    한글이 아닌 자리)를, 이쪽은 "이미 한글인데 우리가 버린 예전 값인가"(0x885f 부류)를
    본다. 둘 다 있어야 "번역 안 됨"과 "낡은 번역"을 같이 잡는다.
    """
    ranges = _live_ranges()
    results = []
    for canon, old, reason in SUPERSEDED_SPELLINGS:
        ob = _enc(old)
        s = 0
        live_offs = []
        while True:
            i = data.find(ob, s)
            if i < 0:
                break
            if _live_lba_of(i, ranges) is not None:
                live_offs.append(i)
            s = i + 1
        if verbose or live_offs:
            print(f"  {old!r}(→{canon!r} 로 바뀜) — 라이브 잔존 {len(live_offs)}곳")
        if live_offs:
            results.append((f"{old!r}→{canon!r}", len(live_offs), reason))
    return results


def check_route_label_separator(*, verbose=False):
    """065 경로 라벨 구분자(줄표) — **물리 칸 18개 전부**를 되읽는다.

    🔴 **RE 가 닫히기 전에 남긴 지적**(2026-09-15) — 이전 readback 은 "9종"(전각 표,
    textmap 유래)만 봤는데, 실제로는 같은 라벨이 표 **셋 + 글리프 한 자리**에 흩어져
    있다(전각 9 · 반각 ASCII `HALFWIDTH_ROUTE_LABELS` 6 · 반각 ASCII `ROUTE_LABELS_2`
    2 · 반각 글리프코드 1 = 18칸). "9종 재확인"이 초록이어도 **못 본 아홉 칸**이
    조용히 물결표로 돌아갈 수 있다 — 관리자가 지적한 "4-F: 없다는 결론이 아니라 물음"의
    실례다. 세 표를 **각자의 정본 상수에서 직접 가져와** 되읽는다(오프셋을 여기 다시
    적지 않는다 — 이 파일이 네 번째 사본이 되는 걸 피한다).
    """
    import patch_ed2_battle as PB
    import patch_ed2_sys as PS
    import patch_hangul_glyph_table as G
    from battle_text import B
    from derive_text import jp_map

    buf = extract(PB.ED2_LBA, PB.ED2_SIZE, path=IMG)
    problems = []
    checked = 0

    # 전각 9 — patch_ed2_battle 이 빌드 때 쓰는 것과 같은 스캔으로 오프셋·원문을 다시
    # 얻는다(원본 기준이라 항상 같은 9곳이 나온다), KR 은 build 의 조회 순서(plan())와
    # 똑같이 textmap 셋에서 찾는다.
    orig = extract(PB.ED2_LBA, PB.ED2_SIZE)
    ed2_map, items_map = jp_map("battle_ed2"), jp_map("items_battle")
    for fo, jp in sorted(PB.strings(orig).items()):
        if "～" not in jp:
            continue
        kr = ed2_map.get(jp) or B.get(jp) or items_map.get(jp)
        if kr is None or "-" not in kr:
            continue
        checked += 1
        kb = PB._enc(kr) + b"\x00"
        actual = bytes(buf[fo : fo + len(kb)])
        if actual != kb:
            problems.append(f"전각 0x{fo:X} {kr!r} — 기대 {kb.hex()} 실제 {actual.hex()}")

    # 반각 ASCII 8 — HALFWIDTH_ROUTE_LABELS(6) + ROUTE_LABELS_2(2)
    for off, _jp, kr in (*PS.HALFWIDTH_ROUTE_LABELS, *PS.ROUTE_LABELS_2):
        checked += 1
        kb = PS._enc(kr) + b"\x00"
        actual = bytes(buf[off : off + len(kb)])
        if actual != kb:
            problems.append(f"반각ASCII 0x{off:X} {kr!r} — 기대 {kb.hex()} 실제 {actual.hex()}")

    # 반각 글리프코드 1 — 0xAB10(큐베라-프로스, 062 조각 코드)
    off = 0xAB10
    kb = bytes(G.ROUTE_CODES) + b"\x00"
    checked += 1
    actual = bytes(buf[off : off + len(kb)])
    if actual != kb:
        problems.append(f"반각글리프 0x{off:X} — 기대 {kb.hex()} 실제 {actual.hex()}")

    if verbose or problems:
        print(f"  경로 라벨 구분자 되읽기 — {checked}칸 확인, 문제 {len(problems)}건")
    return problems


def check():
    import patch_hangul_glyph_table as G

    problems = []
    remaining = G.count_unbaked()
    if remaining:
        problems.append(f"반각 글리프 표(ED.EXE+ED2.EXE) — 미굽 칸 {remaining}개 남음")

    with open(IMG, "rb") as f:
        data = f.read()

    check_place_name_jp_residual(data)  # 진단 전용 — 게이트 아님(위 docstring)

    superseded_hits = check_superseded_spellings(data)
    for label, n, reason in superseded_hits:
        problems.append(f"버린 옛 표기가 라이브 자리에 남음 — {label} {n}곳 · {reason}")

    problems.extend(check_route_label_separator())

    for label, pattern, allowed, reason in PATTERN_BASELINE:
        n = data.count(pattern)
        if n > allowed:
            problems.append(f"{label} — 잔존 {n}곳(허용 {allowed}) · {reason}")
        elif n < allowed:
            # 허용치보다 적게 남으면 baseline이 낡은 것 — 죽은 사본이 살아났거나
            # baseline을 갱신 안 한 것이니 알려야 한다(조용히 통과시키지 않는다).
            print(f"  ℹ {label} — 잔존 {n}곳(허용치 {allowed}보다 적음, baseline 갱신 검토)")

    if problems:
        print("❌ 사본 개수 게이트 실패:")
        for p in problems:
            print(f"   - {p}")
        return False
    print(f"✅ 사본 개수 게이트 통과 (글꼴 표 · {len(PATTERN_BASELINE)}개 패턴)")
    return True


if __name__ == "__main__":
    sys.exit(0 if check() else 1)
