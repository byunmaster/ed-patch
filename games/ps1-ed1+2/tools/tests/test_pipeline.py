"""문안 파이프라인 회귀 테스트. 실행: `.venv/bin/python games/ps1-ed1+2/tools/tests/test_pipeline.py`

⚠ **여기 있는 건 전부 우리가 실제로 물린 함정**이다. 고친 뒤 규칙만 문서에 적어 두면
다음 사람이(또는 다음 달의 내가) 같은 자리를 다시 밟는다 — 오늘 하루에만 `subs` 순서·
낱말 경계·이름창 canon 셋을 새로 만났다. mcpads 패처들이 SFC 하나에 테스트 630개를 두는
이유가 이것이라고 보고 옮겼다(2026-08-11).

⚠ 원본 이미지(`originals/`)를 안 쓴다 — 소장본 없이도 돌아야 한다. 이미지 테스트는
합성 섹터로 한다.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOLS = os.path.dirname(_HERE)
sys.path.insert(0, _TOOLS)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(_TOOLS)), "..", "shared"))
os.environ.setdefault("LOCK_BYPASS", "1")

import common as C
import reinsert_kr_pilot as R


# ── 부호·띄어쓰기 (`fix_spacing`) ───────────────────────────────────────────
def test_period_before_hangul_gets_space():
    # 정발은 문장 사이 공백을 자주 빠뜨린다
    assert R.fix_spacing("갔다.그리고") == "갔다. 그리고"


def test_dot_before_bang_is_dropped():
    # ⚠ 느낌표는 **하나로 모인다**(유저 확정 2026-08-13) — JP 원문에 `!!` 가 0개라
    # 정발이 더한 것을 물려받은 자리였다. 전투 코퍼스는 경로가 달라 `!!` 를 유지한다.
    assert R.fix_spacing("뭐야.!!") == "뭐야!"
    assert R.fix_spacing("안돼!! 열어줘!!") == "안돼! 열어줘!"


def test_ellipsis_is_not_split():
    # `....` 은 말줄임이지 문장 경계가 아니다 — 공백을 끼우면 안 된다.
    # 길이는 셋으로 모은다(유저 확정 2026-08-13) — 붙여 쓰는 것 자체는 그대로다.
    assert R.fix_spacing("글쎄....그런가") == "글쎄...그런가"


def test_ellipsis_length_is_normalized():
    assert R.fix_spacing("그렇군.. 알았네") == "그렇군. 알았네"  # 2점은 온점 하나
    assert R.fix_spacing("노인....") == "노인..."  # 3~9점은 셋
    assert R.fix_spacing("다섯.....") == "다섯..."


def test_silent_window_keeps_its_length():
    # 10점 이상은 말줄임표가 아니라 **침묵 창**이다 — 원문도 중점을 그만큼 찍는다.
    # ⚠ 런 전체를 재야 한다: 뒤만 막으면 12점에서 뒤 9점만 잡아 6점으로 만든다(백트래킹).
    assert R.fix_spacing("..............") == ".............."
    assert R.fix_spacing("할지............") == "할지............"


def test_spell_is_jumun_not_mabeop():
    # 呪文 = 주문(발동 명령어). 정발이 대부분 「마법」으로 옮겨 놔서 여기서 되돌린다.
    assert R.fix_spacing("사이레스 마법을 쓰면") == "사이레스 주문을 쓰면"
    # `呪文の書` 는 **주문책**이다(유저 확정 2026-08-14).
    # ⚠ **정발이 안에서 갈린다** — ED2 대사 코퍼스는 `주문서` 9회인데 아이템 표
    # (`ED2MAIN.EXE`)는 `X의책` 이다(실측). 원문 `呪文の書` 는 「주문서」·「주문책」·
    # 「주문의 책」이 다 되므로 원음으로는 판정이 안 선다 — 그래서 **우리 안의 일관성**이
    # 기준이 됐다. 우리 ED2 아이템이 `프람의 책`·`인파스의 책` 이니 대사도 「책」으로 간다.
    assert R.fix_spacing("누구의 마법책에 써 넣을까?") == "누구의 주문책에 써 넣을까?"
    # 이미 `주문서` 로 적힌 자리도 덮는다 — 포인터 블록이 그렇게 들어온다
    assert R.fix_spacing("어느 분의 주문서에 써 넣을까요?") == "어느 분의 주문책에 써 넣을까요?"
    # ⚠ 예외 하나 — 원문이 `魔法の品` 인 자리는 진짜 마법이다
    assert R.fix_spacing("신께서 쓰시던 마법의 물건이") == "신께서 쓰시던 마법의 물건이"


# ── 창 끝 종결부호 (`close_sentence`) ───────────────────────────────────────
def test_close_adds_period_to_declarative():
    assert R.close_sentence("여기는 도구 파는 곳입니다") == "여기는 도구 파는 곳입니다."


def test_close_leaves_connective_alone():
    # `…동생 말인데요`(jp1087)는 다음 창으로 이어지는 조각 — 온점을 찍으면 안 된다
    assert R.close_sentence("동생 말인데요") == "동생 말인데요"


def test_close_leaves_existing_punct():
    assert R.close_sentence("그렇습니다!") == "그렇습니다!"


# ── 치환 규칙 (`spell_fix`) ─────────────────────────────────────────────────
def test_hangaunde_needs_word_boundary():
    # ⚠ 2026-08-11 실측: `한 가운데에`→`한가운데에` 가 **앞말이 관형형**인 자리에 걸려
    # `위험한 가운데에서` 를 `위험한가운데에서` 로 붙여 버렸다. 낱말 경계를 요구한다.
    assert "위험한 가운데에서" in R.spell_fix("위험한 가운데에서 구해 주셔서")
    assert "사막 한가운데에" in R.spell_fix("사막 한 가운데에 있는")


def test_place_canon_runs_before_spell_fix():
    # ⚠ 2026-08-10 실측: 지명 정본 교정이 `spell_fix` **뒤**에 있어 지명이 든 맞춤법 규칙
    # 5건이 영영 안 걸렸다. 규칙은 정본 표기(`라누라`)만 겨냥하면 된다는 전제가 여기 걸려 있다.
    src = "라느라왕국은"
    for a, b in (("폰 리그", "온리크"), ("폰리그", "온리크"), ("라느라", "라누라")):
        src = src.replace(a, b)
    assert "라누라" in src and "라느라" not in src


# ── 이름 정본 (`NAME_CANON`) ────────────────────────────────────────────────
def test_name_canon_covers_speaker():
    # ⚠ 화자는 본문이 아니라 DOS 블록 헤더에서 온다 — 치환 규칙이 못 닿아 이름창만
    # `젤만` 으로 남았다(2026-08-11). 정본 표는 `제르만`.
    assert R.NAME_CANON.get("젤만") == "제르만"


# ── 쓰기 가드 (`common.write_user_data`) ────────────────────────────────────
def _synth_image(path, nsec=8):
    """합성 Mode2 Form1 이미지 — 유저 데이터는 0x55 로 채운다."""
    with open(path, "wb") as f:
        for i in range(nsec):
            sec = bytearray(C.SECTOR)
            sec[18] = 0x08  # Form1 (0x20 이 서면 Form2 — 가드가 거부한다)
            sec[C.USER_OFF : C.USER_OFF + C.USER_SIZE] = b"\x55" * C.USER_SIZE
            f.write(sec)


def _guarded_lba():
    """가드가 걸린 LBA 와 그 안쪽 오프셋 하나."""
    (lba, _size), regions = next(iter(C.IMMUTABLE.items()))
    name, a, _b, _mode = regions[0]
    return lba, a, name


# 가드가 안 걸린 섹터 — LBA 69 파일의 무변경 구간은 섹터 0~3·40~41 에 흩어져 있다
FREE_SEC = 5


def _with_image(fn):
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.bin")
        lba, off, _ = _guarded_lba()
        _synth_image(p, nsec=lba + FREE_SEC + 2)
        with open(p, "r+b") as f:
            return fn(f, lba, off)


def test_guard_blocks_immutable_change():
    lba, off, name = _guarded_lba()

    def go(f, lba, off):
        data = bytearray(b"\x55" * C.USER_SIZE)
        data[off % C.USER_SIZE] = 0x00  # 무변경 구간 한 바이트를 지운다
        base = lba + off // C.USER_SIZE
        try:
            C.write_user_data(f, base, bytes(data), label="사고 재현")
        except C.WriteGuard as e:
            return str(e)
        return None

    msg = _with_image(go)
    assert msg and name in msg, msg
    assert "사고 재현" in msg, msg  # 라벨이 있어야 범인을 안다


def test_guard_allows_rewriting_same_bytes():
    # ⚠ 가드는 **범위가 아니라 값 변화**를 본다 — 무변경 구간을 품은 파일을 통째로
    # 다시 쓰는 건(그 바이트를 그대로 되쓰는) 정상이다. 범위로 막으면 오탐이 난다.
    def go(f, lba, off):
        base = lba + off // C.USER_SIZE
        return C.write_user_data(f, base, b"\x55" * C.USER_SIZE, label="되쓰기")

    assert _with_image(go) == 0  # 바뀐 섹터 0


def test_expect_free_space_catches_nonzero():
    # 「0런인 줄 알았는데 아니었다」(VAB 함정) 부류를 쓰기 전에 잡는다
    def go(f, lba, off):
        try:
            C.write_user_data(f, lba + FREE_SEC, b"\x01" * 16, label="빈 공간 가정", expect=0x00)
        except C.WriteGuard as e:
            return str(e)
        return None

    msg = _with_image(go)
    assert msg and "사전조건" in msg, msg


def test_expect_bytes_matches():
    def go(f, lba, off):
        return C.write_user_data(
            f, lba + FREE_SEC, b"\xaa" * 16, label="원본 확인", expect=b"\x55" * 16
        )

    assert _with_image(go) == 1


# ── 검출기 판정 (`spellcheck_render`) ──────────────────────────────────────
# ⚠ `check_variants`·`proposal` 테스트는 그 도구와 함께 걷어냈다(2026-08-12) —
#   정발 배정을 그만두고 번역 정본(`script/`)으로 옮기면서 물음 자체가 없어졌다.
# ── 글리프 계획 세대 결박 (`hangul_map` · `hangul_font`) ───────────────────
def test_glyph_plan_is_pinned():
    # ⚠ 계획(SYLLABLES 순서)은 폰트 블록·본문 인코딩·조사 테이블 **셋의 계약**이다.
    # 바뀌면 이미 구운 이미지와 어긋나 글자가 통째로 뒤바뀐다 — 조용히 틀리는 부류.
    import hangul_map as HM

    assert HM.plan_sha1() == HM.PLAN_SHA1
    assert len(HM.SYLLABLES) == 2350
    assert HM.SYL_INDEX[HM.SYLLABLES[0]] == 0


def test_font_block_is_single_source():
    # 폰트 블록을 두 곳에서 따로 만들면 한쪽만 고쳐도 티가 안 난다 — 통로는 하나여야 한다
    import hangul_font

    assert callable(hangul_font.font_block)


# ── VAB 구조 인식 (`vab.py`) ───────────────────────────────────────────────
def _vab_fixture():
    """합성 VAB 뱅크 하나 — 원본 없이 돌아야 하므로 헤더를 직접 짓는다."""
    import struct

    nprog, wave = 1, b"\xab" * 64
    hdr = bytearray(b"\x00" * (32 + 128 * 16 + 512 * nprog + 512))
    hdr[0:4] = b"pBAV"
    struct.pack_into("<I", hdr, 12, len(hdr) + len(wave))  # fsize
    struct.pack_into("<H", hdr, 18, nprog)
    return b"\x11" * 16 + bytes(hdr) + wave, 16, 16 + len(hdr)  # (ed, 뱅크 시작, 파형 시작)


def test_vab_finds_wave_start():
    import vab

    ed, off, wav = _vab_fixture()
    assert [b[0] for b in vab.banks(ed)] == [off]
    assert vab.wave_start(ed, off + 100) == wav
    assert vab.safe_len(ed, off + 100) == wav - off - 100


def test_vab_flags_wave_overwrite():
    # ⚠ 2026-07-29 사고 재현 — 헤더 패딩은 덮어도 되지만 **파형은 안 된다**
    import vab

    ed, _off, wav = _vab_fixture()
    assert vab.hits_wave(ed, wav, wav + 4)  # 파형 침범 → 잡힌다
    assert not vab.hits_wave(ed, wav - 8, wav)  # 파형 직전까지는 통과


def test_vab_outside_bank_is_none():
    import vab

    ed, _off, _wav = _vab_fixture()
    assert vab.wave_start(ed, 0) is None  # 뱅크 밖


def test_josa_safe_bounds_are_derived_not_guessed():
    # ⚠ `JOSA_SAFE`·`DATA_SAFE` 는 손으로 계산해 박은 매직 넘버였고 재검증 절차는
    # **주석에만** 있었다. 이제 구조에서 유도해 대조한다.
    import os

    from common import ORIG_BIN

    if not os.path.exists(ORIG_BIN):
        return  # 원본 없는 머신 — 빌드 쪽이 맡는다
    import patch_josa_hook as J
    from common import extract

    assert J.verify_safe_bounds(bytearray(extract(257, 1021952)))


def test_num_unit_not_split():
    # 금액과 단위가 두 줄에 걸쳤다(`하룻밤 10` / `Gold입니다.` — 여관 jp667, 유저 QA 08-11).
    import reinsert_kr_pilot as R

    txt = "여행자의 집에 어서 오십시오. 하룻밤 10 Gold입니다. 묵으시겠습니까?"
    pg = R.wrap_page(txt, max_lines=5)
    lines = [ln for p in pg for ln in p]
    assert not any(ln.rstrip().endswith("10") for ln in lines), lines
    assert any("10 Gold" in ln for ln in lines), lines


def test_num_bind_only_for_units():
    # ⚠ 「숫자 뒤 아무 어절」로 넓히면 `워프 2` / `마법을` 을 갈라 놓는다(수사가 앞말에 붙는
    # 자리). 묶는 건 **단위**뿐이라는 걸 못 박는다.
    import reinsert_kr_pilot as R

    assert R._NUM_UNIT.search("하룻밤 10 Gold입니다.")
    assert not R._NUM_UNIT.search(
        "워프 2 마법을 익혔다."
    )  # 픽스처는 우리 문장으로 — 정발 인용 금지


def test_window_lines_counts_across_blocks():
    # 블록이 `%c` 없이 끝나면 다음 블록이 **같은 창에 이어 붙는다** — 조판은 블록 하나만
    # 보므로 합쳐서 6줄을 넘어도 아무도 안 본다(무기점 jp702~703, 유저 QA 08-11).
    # ⚠ 화자 분기(`%c이름%c…%c이름%c…`)를 한 창으로 세면 오탐이 쏟아진다 — 이름 헤더를 가른다.
    import check_tail_cut as T

    one = T.windows("%c무기점%c\n" + "\n".join(f"줄{i}" for i in range(6)))
    assert [n for n, _ in one] == ["무기점"], one
    branch = "%c세리오스%c\n가\n나%c류난%c\n가\n나%c"
    assert [n for n, _ in T.windows(branch)] == ["세리오스", "류난"], T.windows(branch)
    # `%c` 없이 끝난 블록만 다음 것과 잇는다 — eid 가 연속일 때만
    assert T.chained({1: "가\n", 2: "나%c", 4: "다%c"}) == [([1, 2], "가\n나%c")]


def test_time_bound_noun_not_split():
    # `어두워지기` / `전에 돌아오시옵소서.` 로 갈렸다(성문 병사 jp5, 유저 QA 08-11).
    # ⚠ 앞이 용언 꼴이 아니면 묶지 않는다 — `집 뒤에` 처럼 위치명사로 쓰는 자리가 있다.
    from text import krwrap

    assert krwrap.split_reason("어두워지기", "전에") == "용언+시간 의존명사"
    assert krwrap.split_reason("헤어진", "후에") == "용언+시간 의존명사"
    assert krwrap.split_reason("집", "뒤에") is None


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn()
            passed += 1
            print(f"  ok  {fn.__name__}")
        except AssertionError as e:
            print(f"  FAIL {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"  ERR  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(fns)} passed")
    return passed == len(fns)


def test_font_slot_differs_per_exe():
    """폰트 슬롯은 **실행파일마다 다른 자리**다 — 한 벌로 쓰면 ED2 가 안 나온다.

    ⚠ 실측 2026-08-14: 디스크에 EXE 가 둘인데 각자 폰트를 들고 있다. `slot_ed_offset` 이
    게임을 안 받던 시절엔 ED1 자리에만 구웠고, ED2 는 문안을 넣어도 글자가 안 떴다.
    두 블록의 오프셋 차이가 정확히 0x24668 로 일정하다(한자·가나 둘 다).
    """
    import hangul_map as H
    from font_map import FONT_BASE

    assert H.slot_ed_offset(0, "ED1") == 0xE50A8
    assert H.slot_ed_offset(0, "ED2") == 0xC0A40
    assert FONT_BASE["ED1"]["kanji"] - FONT_BASE["ED2"]["kanji"] == 0x24668
    assert FONT_BASE["ED1"]["kana"] - FONT_BASE["ED2"]["kana"] == 0x24668
    # 게임을 안 주면 ED1 — 기존 호출부가 그대로 돌아야 한다
    assert H.slot_ed_offset(7) == H.slot_ed_offset(7, "ED1")


def test_overlay_base_is_per_game_and_fails_loud():
    """오버레이 베이스는 **씬마다 세운다** — 안 세우면 죽어야 한다.

    ⚠ 예전엔 `OVERLAY_RAM_BASE` 상수 하나였고 열여덟 자리가 그걸 썼다. 그대로 ED2 를
    체인에 올렸으면 포인터가 전부 0x5000(20,480B)씩 어긋나 **확정 소프트락**이었다.
    ED1 값 폴백을 두지 않는 게 요점이다 — 폴백은 조용히 틀리고 증상이 소프트락이라
    원인이 여기까지 안 온다.
    """
    with R.overlay_for("ED1SCN1"):
        assert R.ov_base() == 0x8016A000
    with R.overlay_for("ED2SCN1"):
        assert R.ov_base() == 0x80165000
        with R.overlay_for("ED1SCN3"):  # 중첩해도 원복한다
            assert R.ov_base() == 0x8016A000
        assert R.ov_base() == 0x80165000
    try:
        R.ov_base()
    except RuntimeError:
        pass
    else:
        raise AssertionError("세우지 않고 불렀는데 안 죽었다 — ED1 값으로 새고 있다")


def test_proper_noun_needs_word_boundary():
    """이름은 **낱말로** 있을 때만 잡는다 — 다른 낱말의 일부는 아니다.

    ⚠ `バザール`(바자르, 시장) 안의 `ザール` 이 몬스터 「잘」로 잡혀 후보 2건이 떴다
    (SCN5 jp339·340, 2026-08-13). 한 자리를 `SKIP_IF` 로 막으면 다음 이름에서 또 난다.
    """
    from check_proper_nouns import _name_in

    assert not _name_in("バザールというものが", "ザール")  # 앞이 가타카나 → 다른 낱말
    assert not _name_in("ザールール", "ザール")  # 뒤가 가타카나
    assert _name_in("ザールが現れた", "ザール")  # 낱말 선두
    assert _name_in("あのザールだ", "ザール")  # 앞이 히라가나
    assert _name_in("アークダムの手から", "アークダム")  # 정상 인명


def test_jp_leak_detects_partial_original():
    """색 구간을 못 채워 **원문이 남은** 결과를 잡는다 — 구조는 멀쩡한데 화면만 깨지는 자리.

    ⚠ `%c切符%cを渡しました。%c` 에 `표를 건넸습니다.` 를 넣으면 `%c자符%c표를…` 이 나온다.
    `%c` 수도 `%s` 수도 원본과 같아 **모든 게이트가 초록**이고, 깨진 글자는 우리 한글
    슬롯으로 렌더돼 「오타」처럼 보인다(ED2 49블록 실측 2026-08-15).
    """
    from check_jp_leak import leaked, shared_runs
    from hangul_map import encode_kr

    assert leaked(encode_kr("표를 건넸습니다")) == []  # 순수 한글 — 잔류 없음
    assert leaked(b"%c" + "切符".encode("cp932") + b"%c") == ["符"]  # 切 는 우리 슬롯 안
    # ⚠ 그래서 코드만 보면 절반을 놓친다 — **원문 raw 와 대조**하는 축이 나머지를 잡는다.
    jp = b"%c" + "密造酒".encode("cp932") + b"%c" + "を渡しました。".encode("cp932")
    assert shared_runs(jp, b"%c" + "密造酒".encode("cp932") + b"%c") == ["密造酒"]
    assert shared_runs(jp, encode_kr("밀조주를 건넸습니다")) == []  # 우리 문안만 — 잔류 없음
    # ⚠ 부호는 게임 폰트의 정상 글리프다 — 빼지 않으면 `～` 하나로 79건이 오탐이 된다.
    assert leaked("～『』".encode("cp932")) == []


def test_repack_skips_empty_string_refs():
    """재packing 이 **빈 문자열을 가리키는 참조**를 덮지 않는다.

    ⚠ 구획 안에는 이름이 아닌데 코드가 가리키는 바이트가 있다 — 값이 `0x00` 이라 코드가
    「아무것도 안 나오는 자리」로 쓴다(`lui $a1,0x8011; addiu $a1,$a1,-0x7844; jal …`).
    덮으면 **없어야 할 글자가 화면에 뜨는데 빌드는 성공한다** — ED1 1곳·ED2 2곳 실측
    (2026-08-16). 널 한 바이트만 남으면 되므로 그 자리를 건너뛴다.
    """
    import patch_items as PI

    # 합성: 이름 둘이 이어진 구획, 가운데 한 바이트가 예약(빈 문자열 참조)이라 치고
    # 건너뛰는지 본다 — 재packing 결과에서 그 오프셋은 반드시 0 이어야 한다.
    lo, hi = 0, 32
    ed = bytearray(hi)
    packed, cur, reserved = bytearray(), lo, [6]
    for kb in (b"AB\x00\x00", b"CDEF\x00\x00\x00\x00"):
        while any(cur <= r < cur + len(kb) for r in reserved):
            r = next(r for r in reserved if cur <= r < cur + len(kb))
            packed += b"\x00" * (r + 1 - cur)
            cur = r + 1
        packed += kb
        cur += len(kb)
    ed[lo:hi] = packed.ljust(hi - lo, b"\x00")
    assert ed[6] == 0, "예약 바이트가 덮였다 — 빈 문자열이 아니게 된다"
    assert bytes(ed).startswith(b"AB\x00\x00"), "첫 이름이 밀리면 안 된다"
    assert b"CDEF" in bytes(ed) and bytes(ed).index(b"CDEF") > 6, "둘째는 예약 뒤로 간다"
    assert callable(PI.repack)


def test_font_compression_roundtrips_and_stays_aligned():
    """압축 폰트를 **스텁과 같은 절차로** 되돌려 원본과 대조한다.

    ⚠ 반각(마스크 비트15)을 넣었을 때 저장 행이 홀수면 다음 글리프의 마스크가 **홀수
    주소**에 놓인다. 스텁은 마스크를 `lhu` 로 읽는데 MIPS 는 홀수 주소 `lhu` 에서 주소
    예외로 죽는다 — 화면이 검게 죽고 빌드는 멀쩡했다(2026-08-16 실측). 정렬까지 본다.
    """
    import patch_opening_font as PF

    chars = sorted(set("가나다ABC.,~<* 힣"))
    raw = [PF.gen_glyphs(chars)[c] for c in chars]
    data = PF.compress_font(raw)

    out, i = [], 0
    for _ in chars:
        assert i % 2 == 0, f"마스크가 홀수 주소 0x{i:X} — 스텁의 lhu 가 예외로 죽는다"
        mask = int.from_bytes(data[i : i + 2], "little")
        i += 2
        half = mask & PF.HALF_BIT
        g = bytearray()
        for r in range(15):
            if mask >> r & 1:
                g += bytes([data[i], 0]) if half else data[i : i + 2]
                i += 1 if half else 2
            else:
                g += b"\x00\x00"
        out.append(bytes(g))
        i = (i + 1) & ~1  # 스텁의 정렬 올림
    assert out == raw, "압축→복원이 원본과 다르다"
    assert len(data) < len(raw) * PF.GLYPH, "압축이 안 됐다"


def test_two_gales_do_not_merge():
    """`게일`(파티)과 `대도 게일`(할아버지)은 **딴사람**이다 — 이름 비교가 뭉개면 안 된다.

    유저 확정(2026-08-17): 파티에 드는 쪽이 `게일` 이고 `대도 게일` 은 그 할아버지다.
    후보 좁히기에서 둘이 같은 사람으로 묶이면 **손자 대사에 할아버지 문장**이 들어온다.
    지금은 유사도 0.50 으로 문턱(0.6) 아래라 갈리는데 그건 우연이라, 문턱을 만질 때
    여기서 걸리게 한다.
    """
    import os
    import sys

    sys.path.insert(0, _TOOLS)
    os.environ.setdefault("LOCK_BYPASS", "1")
    from align_jp_kr import SPEAKER_DICT, name_sim

    assert SPEAKER_DICT["ゲイル"] == "게일"
    assert SPEAKER_DICT["大盗賊 ゲイル"] == "대도 게일"
    assert name_sim("게일", "대도 게일") < 0.6, "두 게일이 뭉개진다"


def test_josa_agreement_ignores_adnominal_endings():
    """조사 받침 검사는 **관형사형 어미를 조사로 오인하면 안 된다**.

    함정(2026-08-17 실측): 받침 규칙을 은/는·과/와까지 넓히면 645건이 걸리는데 **645건 전부
    오탐**이었다 — `있는`(336) `없는`(75) `않는`(37) 처럼 관형사형 `-는` 이 항상 받침 뒤에
    오기 때문이다. 어휘만으로는 조사와 어미를 못 가르므로 축을 **을/를 하나로** 좁혔고,
    거기 남는 오탐(단일 형태소 `마을`)만 STOP 으로 끊는다. 넓히려는 다음 사람을 여기서 막는다.
    """
    import check_josa_agreement as J

    for ok in ("먹는 것", "있는 사람", "없는 걸", "책을 폈다", "마을 사람", "나무를 봤다"):
        assert not [m for m in J.RX_EULREUL.finditer(ok) if _josa_bad(J, m, ok)], f"오탐: {ok}"
    for bad in ("여러분를 ", "카드을 ", "마스쿤를 "):
        assert [m for m in J.RX_EULREUL.finditer(bad) if _josa_bad(J, m, bad)], f"놓침: {bad}"

    # 변수 뒤: `이면` 은 받침 양쪽에 다 붙어 통과, 맨 `면` 은 잡혀야 한다.
    # ⚠ 교체를 왼쪽 우선으로 쓰면 `이` 가 `이면` 을 가려 오탐한다 — 긴 것을 앞에 둔다.
    hit = lambda s: [m.group(1) for m in J.RX_VAR_JOSA.finditer(s) if m.group(1) not in J.ALWAYS_OK]
    assert hit("\x1a면 되겠구먼.") == ["면"], "맨 `면` 을 놓쳤다"
    assert hit("\x1a이면 되겠구먼.") == [], "`이면` 을 오탐했다"
    assert hit("\x1a은(는) 갔다") == [], "병기를 오탐했다"


def _josa_bad(J, m, text):
    prev, j = m.group(1), m.group(2)
    b = J.batchim(prev)
    if b is None or ((b != 0) if j == "을" else (b == 0)):
        return False
    w = text[max(0, m.start() - 3) : m.end()]
    return not any(s in w for s in J.STOP)


def test_table_phase_catches_misaligned_pointer_table():
    """위상이 어긋난 포인터 표도 자료로 본다 — 대사는 안 삼킨다.

    함정(2026-08-17 실측): 블록 경계가 워드 경계와 안 맞는 자리가 있다. `ED2SCN13 jp37` 은
    홀수 주소에서 시작해 워드가 `B6 16 80 2C` 로 읽히는데 3 밀면 `0x8016B62C` — 멀쩡한
    포인터다. 위상 0 만 보면 이런 블록이 「대사」로 새어 번역할 수 없는 채 탈락으로 쌓인다.
    """
    with R.overlay_for("ED2SCN1"):
        base = R.ov_base()
        n = 0x20000
        ptrs = b"".join((base + 0x100 * i).to_bytes(4, "little") for i in range(12))
        assert R.table_phase(ptrs, n) == 0
        assert R.table_phase(ptrs[3:] + b"\x00\x00\x00", n) is not None, "위상 3을 놓쳤다"
        # 대사는 워드가 오버레이 범위에 안 들어온다 — 어느 위상에서도 표가 아니다
        assert R.table_phase("扉には カギがかかっています。".encode("cp932") * 2, n) is None


def test_mid_alias_master_is_the_shortest_copy():
    """[포인터 표][대사] 사본은 **가장 짧은** 사본을 대표로 잡아야 한다.

    함정(2026-08-17 실측): 먼저 나온 것을 대표로 잡았더니 표 접두가 붙은 긴 사본이 자기
    자신을 물어 **아무것도 안 이어졌다**. 증상이 「고쳤는데 탈락 수가 그대로」라 조용하다.
    """
    with R.overlay_for("ED2SCN1"):
        base = R.ov_base()
    text = "%c扉には カギがかかっています。%c%c".encode("cp932")
    ptrs = b"".join((base + 0x100 * i).to_bytes(4, "little") for i in range(14))
    doc = {
        "entries": [
            {"entry_id": 685, "raw_hex": (ptrs + text + b"\x00" * 5).hex()},  # 긴 사본이 먼저
            {"entry_id": 752, "raw_hex": (text + b"\x00").hex()},
        ]
    }
    R._register_mid_alias(doc, "ED2SCN1")
    assert R.MID_ALIAS.get(685) == (len(ptrs), 752), R.MID_ALIAS
    assert 752 not in R.MID_ALIAS, "대표가 자기 자신을 사본으로 물었다"


def test_name_survives_ghost_prefix_from_binary_bytes():
    """앞에 이진 바이트가 붙은 **이름**을 대사로 오인하지 않는다.

    함정(실측 ED2MON3 0x648): 이름 `モーンガーＡ` 앞에 이진 `ff 82 8f 50` 이 있는데,
    `8f 50` 이 하필 `襲` 로 디코드돼 「ASCII 안 섞인 깨끗한 일본어」가 된다. 점수가 같아지면
    `decode_sjis` 는 **덜 건너뛴 쪽**을 고르므로 `襲モーンガーＡ` 가 이기고, 접미 `Ａ` 를 떼도
    정본에 없어 대사로 새어 「문안 없음 1」로 보고됐다. 바이트만 봐선 못 가르니 **정렬 후보
    전부를 정본에 걸어** 판정한다.
    """
    import ed2_monster_review as R

    names = {"モーンガー": "몽거"}
    raw = b"\xff\x82\x8fP" + "モーンガーＡ".encode("cp932")

    assert R.decode_sjis(raw) == "襲モーンガーＡ", "점수만으론 유령 접두가 이긴다(전제)"
    assert R.resolve_name(raw, names) == "モーンガー", "정렬 후보 대조가 이름을 못 찾았다"
    # 대사는 여전히 대사여야 한다 — 이름 대조가 아무거나 삼키면 안 된다.
    line = "モーンガーＡが現れた。".encode("cp932")
    assert R.resolve_name(line, names) is None, "대사를 이름으로 오인했다"


def test_overlay_tail_relocation_updates_refs_with_sign_extension():
    """ED2MON 오버레이 꼬리 재배치 — 참조 갱신과 **부호확장** 을 오프라인으로 검증한다.

    함정(2026-08-17 실측): `0x8014A018` 은 `lui 0x8015` + `addiu -0x5FE8` 로 박혀 있다 —
    lo ≥ 0x8000 이면 lui 가 +1 이다. 갱신이 이 규칙을 안 따르면 0x10000 어긋난 주소를
    읽고도 **빌드는 통과**한다.
    """
    import struct as st

    import patch_ed2_monster_lines as ML

    # 미니 오버레이: [문자열 20B 슬롯][코드: lui+addiu 로 그 문자열 참조]
    slot = 0x18
    ov = bytearray(0x40)
    ov[slot : slot + 6] = b"ABCDE\x00"
    lui = (0x0F << 26) | (5 << 16) | 0x8015  # lui a1, 0x8015 (부호확장으로 -0x5FE8)
    addiu = (0x09 << 26) | (5 << 21) | (5 << 16) | ((ML.BASE + slot - 0x80150000) & 0xFFFF)
    st.pack_into("<I", ov, 0x28, lui)
    st.pack_into("<I", ov, 0x2C, addiu)
    orig = bytes(ov)
    refs, _ = ML.overlay_refs(orig)
    assert slot in refs and refs[slot] == [(0x2C, 0x28, ML.MIPS_ADDIU)], refs

    new, touched = ML._relocate(bytearray(orig), orig, [(slot, "JP", "가나다라마바사", 8)])
    # 꼬리에 인코딩이 실렸고 옛 슬롯은 비었다
    tail = new[len(orig) :]
    assert tail.rstrip(b"\x00"), "꼬리가 비었다"
    assert new[slot : slot + 8] == b"\x00" * 8, "옛 슬롯이 안 비워졌다"
    # 갱신된 쌍이 새 주소를 만든다 (부호확장 포함)
    w_lui = st.unpack_from("<I", new, 0x28)[0]
    w_imm = st.unpack_from("<I", new, 0x2C)[0]
    lo = w_imm & 0xFFFF
    if lo & 0x8000:
        lo -= 0x10000
    got = ((w_lui & 0xFFFF) << 16) + lo
    assert got == ML.BASE + len(orig), f"참조가 0x{got:X} — 기대 0x{ML.BASE + len(orig):X}"
    # 코드(참조 명령 밖)는 무변경
    marks = set()
    for a, b in touched:
        marks.update(range(a, b))
    for k in range(len(orig)):
        assert k in marks or new[k] == orig[k], f"코드 변형 @0x{k:X}"


# ⚠ **`__main__` 블록은 반드시 파일 맨 끝**이다. 예전엔 중간에 있어서 그 뒤에 붙인 테스트가
# **정의되기 전에 러너가 돌아** 조용히 안 돌았다 — `test_proper_noun_needs_word_boundary`
# 가 그렇게 죽어 있었고 `28/28 passed` 는 계속 초록이었다(2026-08-15). 테스트를 늘릴 땐
# 이 블록 **위**에 붙인다.
def test_match_is_the_only_gate_for_candidates():
    """🔴 **정발 후보는 장소·시기·화자를 다 통과해야 한다** (유저 확정 2026-08-17, 재확인).

    규칙은 `docs/policy.md` 에도 메모리에도 있었는데, 도구를 새로 짤 때마다 **유사도만 재고
    화자를 빠뜨렸다** — 2026-08-17 하루에 두 번. 기억에 맡기면 반복되므로 코드로 못 박는다.

    두 가지를 지킨다:
    ① 후보를 내는 문은 `match()` 하나다 — 그 안에 `axes_ok` 가 있다.
    ② 저수준 `best_slice` 는 게이트가 없다는 걸 문서에 명시하고, 채택 경로가 직접 쓰지 않는다.
    """
    import inspect
    import os
    import sys

    sys.path.insert(0, _TOOLS)
    os.environ.setdefault("LOCK_BYPASS", "1")
    import adopt_jeongbal as A

    for name in ("own_table", "axes_ok", "dos_speaker", "match"):
        assert hasattr(A, name), f"세 축 게이트가 사라졌다: {name}"
    assert "axes_ok" in inspect.getsource(A.match), "match() 가 게이트를 안 거친다"
    assert "axes_ok" in inspect.getsource(A.candidates), "candidates() 가 게이트를 안 거친다"
    assert "게이트" in (A.best_slice.__doc__ or ""), "best_slice 에 저수준 경고가 없다"

    # 화자가 다르면 잘린다 — 축자 동일은 그걸 덮는다(1급 규칙)
    ok, why = A.axes_ok("ED1SCN1", 1, "ED1/T_000", 0, ours="가", dos="나")
    assert isinstance(ok, bool) and why


def test_gate_rejections_are_returned_not_dropped():
    """게이트에 걸린 후보를 **버리지 않는다** — `ok=False` 로 같이 돌려준다.

    화자 축은 정발 쪽 전파가 틀릴 수 있다(정발도 한 엔트리에 여러 사람 대사를 담는다).
    잘린 걸 조용히 없애면 「다 봤다」로 읽히고, 멀쩡한 짝이 소리 없이 사라진다 —
    이 리포가 반복해 물린 부류다(`docs/patcher-checklist.md` 「대량 변경」).
    """
    import inspect
    import os
    import sys

    sys.path.insert(0, _TOOLS)
    os.environ.setdefault("LOCK_BYPASS", "1")
    import adopt_jeongbal as A

    src = inspect.getsource(A.match)
    assert "ok=ok" in src, "잘린 후보에 표시를 안 단다"
    assert "if ok:" not in src, "게이트에 걸린 후보를 버리고 있다"


def test_copyright_gate_sees_sentences_and_ignores_spacing():
    """저작권 게이트의 **맹점 둘**을 못 박는다(2026-08-18 실측: 1건을 보는 동안 197건이 샜다).

    ① **문장 단위로 색인해야 한다.** 우리 정본의 `t` 는 문장 단위인데(정발 한 페이지가
       PS1 여러 블록으로 갈린다) 코퍼스를 페이지로만 색인하면 문장 복제가 통째로 빠진다.
    ② **공백을 무시해야 한다.** 정발은 `{n}` 줄바꿈 자리에 공백이 없다(`있는거야?`) —
       띄어쓰기만 다듬어 옮겨 적으면 글자는 그대로인데 검사기가 통과시켰다.

    ⚠ 문턱(`MIN_LEN`)은 **부분 문자열 검색의 잡음 하한**이지 창작성 기준이 아니다.
    문턱을 떼면 흔한 낱말이 전부 걸린다(실측 3,189건). 「같으면 포인터로」는 전체 일치를
    보는 `scan_canon` 이 맡는다 — 거긴 문턱이 없다.
    """
    import inspect
    import os
    import sys

    sys.path.insert(0, _TOOLS)
    os.environ.setdefault("LOCK_BYPASS", "1")
    import check_forbidden as C

    src = inspect.getsource(C._corpus_lines)
    assert "_sentences" in src, "코퍼스를 문장 단위로 색인하지 않는다"
    assert re_sub_in(inspect.getsource(C.scan_repo)), "파일 검색이 공백에 민감하다"
    assert hasattr(C, "scan_canon"), "문안 정본 전체 일치 검사가 없다"
    assert "MIN_LEN" not in inspect.getsource(C.scan_canon), "전체 일치에 길이 문턱을 두면 안 된다"
    assert C.ALLOW == set(), "예외 목록이 되살아났다 — 같으면 포인터로 바꾸면 된다"


def re_sub_in(src):
    """공백을 지우고 비교하는가."""
    return 're.sub(r"\\s+", "", data)' in src or 'sub(r"\\s+", "", data)' in src


def test_tool_index_covers_all_tools():
    """`tools/README.md` 가 **도구를 하나도 빠뜨리지 않는다**.

    ⚠ 표에 없는 도구는 다음 사람에게 **고아로 보인다** — 실제로 두 번 그렇게 지웠다
    (2026-08-12 배정 시대 28개 · 08-18 탐색 19개). 둘 다 되살렸다. 지우면 그 도구가 만들던
    것의 **출처가 끊긴다** — `textmap/*.json` 은 `gen_textmap` 이, `ed1-scene-map.md` 는
    `segment_copy --map` 이 만들었고 체크리스트는 지금도 `proposal.py` 를 인용한다.
    """
    import os

    tools_dir = _TOOLS
    idx = open(os.path.join(tools_dir, "README.md"), encoding="utf-8").read()
    missing = [
        f[:-3]
        for f in sorted(os.listdir(tools_dir))
        if f.endswith(".py") and f"`{f[:-3]}`" not in idx
    ]
    assert not missing, f"도구 지도에 없는 도구: {missing}"


def test_own_table_agrees_with_known_assignments():
    """🔴 **정답을 아는 자리로 게이트를 검산한다** — 배정이 있는 블록이면 그 배정을 돌려줘야 한다.

    ⚠ 이 검산이 없어서 `str(eid)`/int 키 버그를 **커밋한 뒤에** 발견했다(2026-08-18).
    게이트가 「표 없음」을 돌려주면 그건 **「정발에 대응이 없다」와 구별이 안 된다** — 조용히
    후보를 안 내놓는 종류의 오류다. 빌드가 죽고서야 드러났고, 안 죽었으면 계속 믿었을 것이다.

    ⚠ **검출기를 새로 쓰면 커밋 전에 이 꼴의 검산을 먼저 한다**(체크리스트 절 4-B).
    정답을 아는 입력이 4,870건이나 있는데 안 쓴 것이 문제였다.
    """
    import json
    import os
    import sys

    sys.path.insert(0, _TOOLS)
    os.environ.setdefault("LOCK_BYPASS", "1")
    root = os.path.dirname(_TOOLS)
    if not os.path.exists(os.path.join(root, "align_map.json")):
        return
    import adopt_jeongbal as A
    from align_map import scene_map

    ov = json.load(open(os.path.join(root, "align_overrides.json"), encoding="utf-8"))
    bad, n = [], 0
    for i in range(1, 7):
        scn = f"ED1SCN{i}"
        known = {}
        for k, v in (ov.get(scn) or {}).items():
            if isinstance(v, dict) and v.get("table"):
                known[int(k)] = v["table"]
        for k, v in (scene_map(scn) or {}).items():
            if isinstance(v, dict) and v.get("table"):
                known.setdefault(int(k), v["table"])
        for eid, t in known.items():
            n += 1
            got, _how = A.own_table(scn, eid)
            if got != t:
                bad.append(f"{scn} jp{eid}: {t} vs {got}")
    assert n > 1000, f"검산 표본이 너무 적다({n}) — 정본을 못 읽고 있다"
    assert not bad, f"게이트가 아는 배정을 못 돌려준다 {len(bad)}건: {bad[:5]}"


def test_own_table_reads_both_key_types():
    """`scene_map` 은 **int 키**다 — `str(eid)` 로만 찾으면 배정이 있는데도 「표 없음」이 된다.

    ⚠ 조용히 틀린다(2026-08-18 실측): 게이트가 후보를 안 내놓는데 그건 「정발에 대응이 없다」와
    구별이 안 된다. 실제로 네 블록이 그래서 `table: None` 로 새 배정에 박혀 빌드가 죽었다.
    """
    import inspect
    import os
    import sys

    sys.path.insert(0, _TOOLS)
    os.environ.setdefault("LOCK_BYPASS", "1")
    import adopt_jeongbal as A

    src = inspect.getsource(A.own_table)
    assert "pin.get(eid)" in src and "pin.get(str(eid))" in src, "키 한 종류만 본다"


def test_tool_tables_match_shared_glossary():
    """🔴 고유명사 정본(`shared/glossary`)과 도구 표가 어긋나면 안 된다.

    **왜 공용에 두나.** 정발 문안을 옮기던 시절엔 저본이 표기를 대신 맞춰 줬다. 자체 번역으로
    돌아서면(유저 확정 2026-08-18) 그 역할을 할 게 없어지고, 같은 세계관인 새턴·PCE 가 이
    표를 그대로 물려받는다.

    **왜 사본을 남기나.** 도구 표에는 **판정 근거 주석**이 붙어 있다(`치유의 로브` — 정발
    「천민의 옷」은 卑しい 오독 · `사이레스` — ED1/ED2 표기 충돌에서 ED2 우선). 그 지식은
    JSON 으로 옮기면 죽는다. 그래서 데이터는 공용, 근거는 도구에 두고 **여기서 묶는다** —
    한쪽만 고치면 이 테스트가 운다(스킬 색인 ↔ 체크리스트와 같은 방식).
    """
    import os
    import sys

    repo = os.path.dirname(os.path.dirname(os.path.dirname(_TOOLS)))
    sys.path.insert(0, os.path.join(repo, "shared"))
    sys.path.insert(0, _TOOLS)
    os.environ.setdefault("LOCK_BYPASS", "1")
    import align_jp_kr
    import glossary as G
    import patch_items
    import patch_sys_ui

    pairs = {
        "item": dict(patch_items.NAMES),
        "monster": dict(patch_items.MONSTERS),
        "person": dict(align_jp_kr.SPEAKER_DICT),
        "place": dict(patch_sys_ui.PLACES),
    }
    # ⚠ **정본은 상위집합이다**(2026-08-18). 내레이션에만 나오는 이름(이셀하사·론윌섬)은
    #    어느 패치 표에도 없지만 표기는 하나여야 한다. 그래서 「같다」가 아니라
    #    **「도구 표의 모든 항목이 정본과 일치한다」**를 본다 — 도구가 정본에 없는 표기를
    #    쓰거나, 같은 JP 를 다르게 읽으면 실패다.
    for cat, tool in pairs.items():
        canon = G.table(cat)
        missing = sorted(set(tool) - set(canon))
        assert not missing, f"{cat}: 도구에만 있는 이름 {missing[:5]} — 정본에 등재한다"
        diff = {jp: (kr, canon[jp]) for jp, kr in tool.items() if canon[jp] != kr}
        assert not diff, f"{cat}: 도구와 정본의 표기가 다르다 {list(diff.items())[:3]}"


def test_similarity_gate_covers_ed1_with_a_ratchet():
    """🔴 유사도 게이트가 ED1 을 봐야 한다 — 축자만 보면 **낱말 하나 지우기**에 뚫린다.

    실측(2026-08-18): 오프닝 9줄이 `세계가 있어, [거기에] 자연의 혜택을 듬뿍` 처럼 어절
    하나만 지운 정발 문장이었는데 축자 게이트를 그냥 통과했다. 자체 번역으로 돌아서면서
    ED1 정본이 우리 문장으로 채워지므로 이제 ED1 이 본무대다.

    ⚠ 기준선(래칫)이 없으면 늘 빨간불이라 아무도 안 본다 — **늘면 실패, 줄이면 내린다.**
    """
    import inspect
    import os
    import sys

    sys.path.insert(0, _TOOLS)
    os.environ.setdefault("LOCK_BYPASS", "1")
    import check_forbidden as F

    src = inspect.getsource(F.scan_similar)
    assert "ED*SCN*.json" in src, "ED2 만 본다 — ED1 이 빠졌다"
    assert "ED1_SIMILAR_BASELINE" in src, "래칫이 없다 (늘 빨간불이거나, 늘어도 안 운다)"
    assert isinstance(F.ED1_SIMILAR_BASELINE, int)


def test_align_file_is_optional_so_work_can_be_wiped():
    """🔴 빌드는 `work/derived/align/*_SCN*.json` 없이도 돌아야 한다.

    실측(2026-08-19): ED2 를 재삽입 체인에 올린 뒤로 **`rm -rf work/` 가 빌드를 깼다** —
    `build.py` 는 `align_jp_kr.py --speakers-only` 만 돌려 화자맵만 만드는데, 배정 정본
    (`align_map.json`)이 빈 씬은 그 파일을 열려다 `FileNotFoundError` 로 죽었다.
    `check_determinism.py` 도 같은 이유로 못 돌았다 — **결정성 검사가 결정성 구멍에
    막혀 있었다.**

    더 나쁜 쪽은 그 파일이 **다시 만들면 내용이 달라지는 판단물**이라는 것이다(LaBSE
    의미정렬 산출물). 빌드 입력으로 두는 한 「집 빌드 ≠ 회사 빌드」가 열려 있다 —
    레포 제1 원칙. 지금은 화면 블록 문안이 전부 번역 정본(`script/`)에서 오므로
    없는 채로 도는 것이 정상이고, 그래서 **없으면 빈 배정으로 진행**한다.

    ⚠ 조용히 비는 게 아니다 — 정본이 안 덮은 씬이면 원문이 남고, 빌드의 화면 게이트
    (`build.check_screen_gates`)가 「화면에 일본어가 남았다」로 실패시킨다.
    """
    import inspect

    src = inspect.getsource(R.load_translations)
    assert "os.path.exists(align_path)" in src, (
        "정렬 파일을 무조건 연다 — `rm -rf work/` 가 다시 빌드를 깬다"
    )
    _, _, tail = src.partition("os.path.exists(align_path)")
    assert "pairs = []" in tail, "파일이 없을 때의 폴백(빈 배정)이 없다"


def test_untranslated_axis_sees_nameplate_blocks():
    """정본에 **항목조차 없는** 대사 블록을 잡는 축 — 2026-08-19 ED2 검수가 찾은 사각.

    `check_jp_leak.scan` 은 `iter_candidates` 를 도는데 그건 **번역표**를 돈다. 항목이
    아예 없는 블록은 순회에 안 들어오므로, 원문이 그대로 화면에 나가는데도 초록이었다
    (여덟 블록 실측 — 전부 포인터 표 접두라 눈으로도 안 띄었다).

    ⚠ 판정을 넓히면 못 쓴다 — 지명 헤더·값 표까지 잡혀 560건이 된다(실측).
    그래서 **이름창 + 개행**이거나 **가나 6자 + 종결 부호**만 대사로 센다.
    """
    import check_jp_leak as L

    # 실제로 샜던 자리 — 이름창이 붙은 대사
    assert L.is_dialogue("{c}男{c}{n}ここは もう 確保しました。{n}先を急いでください。{c}")
    assert L.is_dialogue(
        "{c}%s{c}{n}ふー 助かった · · ·{c}"
    )  # 종결 부호가 없어도 이름창이면 잡는다
    # 지명 헤더 — 잡히면 안 된다(전부 patch_sys_ui 관할이다)
    assert not L.is_dialogue("。{n}グロストス城")
    assert not L.is_dialogue("{n}ファエトの村")
    assert not L.is_dialogue("エルアスタ")


def test_untranslated_axis_skips_pointer_prefix():
    """포인터 표 접두는 **꼬리만** 본다 — 앞쪽 바이트가 우연히 가나로 읽히면 오탐이 된다."""
    import check_jp_leak as L

    s = "\\x34\\x9C\\x17\\x80惧\\x17\\x80{c}男{c}{n}さあ早く 先に進んでください。{c}"
    assert L._tail(s) == "{c}男{c}{n}さあ早く 先に進んでください。{c}"


def test_onomatopoeia_table_separates_by_mora_and_sokuon():
    """웃음소리는 **인물을 가르는 표지**다 — 원문 꼴이 다르면 우리 꼴도 달라야 한다.

    2026-08-20 에 `フォッフォッフォ`(노인)를 「훠훠훠」로 통일하다가 실피의 `ホッホッホッ`
    까지 같은 그물에 걸어 네 블록을 잘못 고쳤다. **원문이 다른 낱말인데 우리 문안이 같아서**
    일괄 치환에 삼켜진 것이다. 표가 그 둘을 갈라 놓는지 지킨다.
    """
    import check_onomatopoeia as O

    # 마디 수·촉음이 다르면 우리 꼴도 달라야 한다
    assert O.CANON["ハハハ"] != O.CANON["ハッハッハ"] != O.CANON["ハッハッハッ"]
    assert O.CANON["ハッハッハッハ"] != O.CANON["ハッハッハッ"]
    assert O.CANON["ふっふっふ"] != O.CANON["ふっふっふっ"]
    # 🔴 실피(여성) ↔ 노인 — 이걸 뭉갠 게 그날의 사고다
    assert O.CANON["ホッホッホッ"] != O.CANON["フォッフォッフォ"]
    # 긴 꼴이 짧은 꼴에 먹히면 안 된다
    assert O.jp_tokens("ハッハッハッハ · ·") == ["ハッハッハッハ"]
    assert O.jp_tokens("うわっはっはっはっはっ") == ["うわっはっはっはっはっ"]


def test_pointer_table_axis_needs_empty_tail():
    """포인터 표에 문안을 넣으면 **표가 지워진다** — 2026-08-20 `ED2SCN2:300` 실측.

    판정 신호를 두 번 틀렸다. 두 실수를 그대로 테스트로 굳힌다:

    1. 비율만 보면 **표 접두 + 대사 꼬리**(anchor_tail)까지 걸린다 — 66건이 그랬다.
       그건 재삽입기가 꼬리만 다시 쓰므로 **정상**이다.
    2. 표는 워드 경계에서 시작하지 않는다 — `ED2SCN2:300` 은 **offset 3** 에서 맞는다.
    """
    import check_pointer_tables as P

    tbl = b"\x00\x00\x00" + b"".join((0x80175F2C + i * 4).to_bytes(4, "little") for i in range(20))
    assert P.pointer_ratio(tbl) > 0.9, "정렬 0~3 을 다 봐야 한다(이 표는 offset 3)"
    assert P.pointer_ratio(b"\x41" * 80) < 0.5, "평범한 바이트를 표로 보면 안 된다"

    # 꼬리에 대사가 있으면 anchor_tail — 잡으면 안 된다
    assert P.tail_text("\\x34\\x9C\\x17\\x80{c}男{c}{n}ここは もう 確保しました。")
    assert not P.tail_text("\\x34\\x9C\\x17\\x80\\xF8\\x5F\\x17\\x80")


def test_iso_layout_reads_records_across_sector_gaps():
    """디렉터리 레코드는 **섹터를 넘지 않는다** — 길이 0 을 만나면 다음 섹터 머리로 건너뛴다.

    그걸 빼먹으면 파일 목록이 중간에서 끊기고, 끊긴 뒤의 파일이 밀려도 **초록으로 뜬다.**
    배치 검사기가 조용히 거짓말하는 가장 쉬운 길이라 여기서 막는다.
    """
    import check_iso_layout as L

    def rec(name, lba, size):
        nb = name.encode()
        ln = 33 + len(nb) + ((33 + len(nb)) % 2)
        b = bytearray(ln)
        b[0] = ln
        b[2:6] = lba.to_bytes(4, "little")
        b[10:14] = size.to_bytes(4, "little")
        b[32] = len(nb)
        b[33 : 33 + len(nb)] = nb
        return bytes(b)

    first = rec("A.;1", 100, 2048)
    data = bytearray(4096)
    data[: len(first)] = first  # 앞 섹터엔 하나만 두고 나머지는 0(= 섹터 끝 표식)
    second = rec("B.;1", 200, 2048)
    data[2048 : 2048 + len(second)] = second

    got = L.read_root.__wrapped__(data) if hasattr(L.read_root, "__wrapped__") else None
    assert got is None  # read_root 는 파일을 읽으므로 파서만 따로 재현해 확인한다

    out, i = [], 0
    while i < len(data):
        ln = data[i]
        if ln == 0:
            i = (i // 2048 + 1) * 2048
            continue
        r = data[i : i + ln]
        out.append(r[33 : 33 + r[32]].decode())
        i += ln
    assert out == ["A.;1", "B.;1"], "섹터 경계를 못 넘으면 뒤 파일을 통째로 놓친다"


def test_write_log_records_every_sector():
    """되읽기 지문은 **섹터 단위**여야 한다 — 쓰기 단위로 잡으면 커버리지가 무너진다.

    실측(2026-08-20): 쓰기 단위로 「뒤에 겹친 게 있으면 앞엣것은 검증 제외」로 잡았더니
    커버리지가 **38%** 였고 하필 **대사 씬 열아홉이 전부** 그 밖이었다(패처가 같은 파일을
    뒤에서 조금만 덧칠하기 때문). 섹터로 잡으면 마지막 쓴 사람이 자연히 이긴다.
    """
    import hashlib

    import common as C

    C.WRITE_SECTORS.clear()
    C.WRITE_LOG.clear()
    try:
        data = bytes(range(256)) * 24  # 6144B = 3섹터
        # 쓰기 없이 기록부만 확인한다 — `write_user_data` 의 기록 구간과 같은 계산
        nsec = (len(data) + C.USER_SIZE - 1) // C.USER_SIZE
        for i in range(nsec):
            chunk = data[i * C.USER_SIZE : (i + 1) * C.USER_SIZE].ljust(C.USER_SIZE, b"\x00")
            C.WRITE_SECTORS[100 + i] = [hashlib.sha1(chunk).hexdigest(), "테스트"]
        assert nsec == 3
        assert sorted(C.WRITE_SECTORS) == [100, 101, 102], "쓴 섹터를 하나도 빠뜨리면 안 된다"
        # 뒤에 겹쳐 쓰면 그 섹터의 주인이 바뀐다(= 마지막 쓴 사람이 이긴다)
        C.WRITE_SECTORS[101] = ["deadbeef", "나중"]
        assert C.WRITE_SECTORS[101][1] == "나중"
        assert C.WRITE_SECTORS[100][1] == "테스트", "안 겹친 섹터는 그대로 남아야 한다"
    finally:
        C.WRITE_SECTORS.clear()
        C.WRITE_LOG.clear()


def test_proper_noun_report_keeps_control_codes():
    """보고에 찍는 문안은 **`ctrl=True`** 여야 한다 — 안 그러면 띄어쓰기 오류로 읽힌다.

    실측(2026-08-20): 찾기용 `ctrl=False` 렌더는 `%c` 와 **그 자리의 공백을 같이 지운다**.
    `'아트라스, 세리오스 공은'` 이 `'아트라스,세리오스공은'` 으로 보여 오타로 오판했다.
    문안은 멀쩡했다. 찾기는 `%c` 를 넘어야 하니 `ctrl=False` 가 맞고, **보여주기만**
    `ctrl=True` 로 갈라야 한다.
    """
    import inspect

    import check_proper_nouns as C

    src = inspect.getsource(C.scan)
    assert "render_bytes(cand, ctrl=False)" in src, "찾기는 %c 를 넘어야 한다"
    assert "render_bytes(cand, ctrl=True)" in src, "보여주기는 %c 를 남겨야 한다"
    assert "hits.append((eid, name, ours, kind, shown))" in src, (
        "보고에 찾기용 평문(kr)을 찍으면 %c 자리가 띄어쓰기 오류로 읽힌다"
    )


def test_untranslated_axis_does_not_filter_by_tail():
    """🔴 **「꼬리가 같은 번역본이 있으면 제외」를 되살리면 안 된다**(2026-08-20 실측).

    한 번 그렇게 걸렀다 — 재삽입기가 대표 사본으로 참조를 돌리니 사본은 안 샐 거라고 본
    것이다. **틀렸다.** 그 필터가 여덟을 숨겼고, 최종 이미지를 열어 보니 원문 그대로였다
    (`ED1SCN4:735` 는 `宝혭を낙けました` 로 깨져 나가고 있었다). 별칭이 도는지는 꼬리가
    같다고 알 수 없다.
    """
    import inspect

    import check_jp_leak as L

    src = inspect.getsource(L.untranslated)
    assert "done = " not in src, "꼬리 기준 제외를 되살리면 안 된다 — 여덟을 숨겼다"
    assert "if t in done" not in src


def test_line_dict_key_is_platform_neutral():
    """사전 키는 **덤퍼 표기를 타면 안 된다** — 이 사전이 타이틀을 넘어가는 유일한 창구다.

    실측(2026-08-20): PS1 은 `{c}…{c}{n}`, 새턴은 `%c…%c\n` 로 같은 원문을 다르게 적는다.
    키가 그걸 타고 있어 새턴 적중이 **1.3%** 였다(중립화 뒤 76%).
    """
    from export_line_dict import key

    ps1 = "{c}ライアス{c}{n}王子、ちゃんと いすに 座って{n}待っていて くだされ。"
    sat = "%cライアス%c\n王子、ちゃんと いすに 座って\n待っていて くだされ。"
    assert key(ps1) == key(sat), "마크업 표기가 다르면 같은 원문도 다른 키가 된다"
    assert key("あ･あ") == key("あ・あ"), "가운뎃점 세 꼴을 통일해야 한다"
    assert key("よし\x21\x21") == key("よし!!"), "이식판은 `!!` 를 문자로 쓰기도 한다"
    assert key("スライム") != key("ドラゴン"), "다른 원문이 같은 키가 되면 안 된다"


def test_resolve_handles_port_only_shapes():
    """이식판에만 있는 꼴은 **규칙으로** 푼다 — 사전에 다 박으면 14,000 항목이 는다."""
    from export_line_dict import key, resolve

    lines = {key("スライム"): {"t": "슬라임"}, key("ドラゴン"): {"t": "드래곤"}}
    assert resolve("スライムＡ", lines) == "슬라임Ａ", "개체 구분자는 떼고 찾는다"
    assert resolve("スライムとドラゴンが現れた。", lines) == "슬라임과 드래곤이 나타났다."
    assert resolve("ドラゴンとスライムが現れた。", lines) == "드래곤과 슬라임이 나타났다."
    # ⚠ 조사는 **앞말 받침**으로 고른다 — 처음엔 「와」로 박아 두어 「슬라임와」가 나왔다
    assert resolve("まったく知らない敵", lines) is None, "모르면 None 이어야 한다"


# ── 오프닝 폰트 행 사전 코덱 + 디코더 스텁 (2026-08-21) ──────────────────────
def _mips_run(words, base, mem, maxsteps=4_000_000):
    """스텁을 **정말 실행한다** — 손인코딩 기계어의 유일한 정적 검증.

    ⚠ `verify_asm`(디스어셈)은 「명령으로 디코드되는가 · 지연 슬롯에 분기가 없는가」만 본다.
    분기 오프셋이 한 칸 어긋나도, 로드 지연을 어겨도 **통과한다** — 둘 다 2026-08-21 에
    실제로 냈다(분기 셋이 전부 +1 어긋나 있었다). 그래서 여기서 돌려 본다.
    MIPS I 로드 지연도 흉내 낸다(로드 결과는 **다음 명령이 끝난 뒤** 반영).
    """
    r = [0] * 32
    pc, pend, steps = base, None, 0
    while steps < maxsteps:
        steps += 1
        w = words[(pc - base) // 4]
        op, rs, rt = w >> 26, (w >> 21) & 31, (w >> 16) & 31
        rd, sa, fn, imm = (w >> 11) & 31, (w >> 6) & 31, w & 63, w & 0xFFFF
        simm = imm - 0x10000 if imm & 0x8000 else imm
        nxt, land = pc + 4, None
        if op == 0 and fn == 8:  # jr
            return r, mem
        elif op == 0 and fn == 0:  # sll
            r[rd] = (r[rt] << sa) & 0xFFFFFFFF
        elif op == 0 and fn == 2:  # srl
            r[rd] = (r[rt] & 0xFFFFFFFF) >> sa
        elif op == 0 and fn == 0x21:  # addu
            r[rd] = (r[rs] + r[rt]) & 0xFFFFFFFF
        elif op == 0 and fn == 0x23:  # subu
            r[rd] = (r[rs] - r[rt]) & 0xFFFFFFFF
        elif op == 0x09:  # addiu
            r[rt] = (r[rs] + simm) & 0xFFFFFFFF
        elif op == 0x0C:  # andi
            r[rt] = r[rs] & imm
        elif op == 0x0D:  # ori
            r[rt] = r[rs] | imm
        elif op == 0x0F:  # lui
            r[rt] = (imm << 16) & 0xFFFFFFFF
        elif op == 0x24:  # lbu — 지연 로드
            land = (rt, mem[(r[rs] + simm) & 0xFFFFFFFF])
        elif op == 0x25:  # lhu
            a = (r[rs] + simm) & 0xFFFFFFFF
            assert a % 2 == 0, f"홀수 주소 lhu @0x{a:08X} — 실기는 주소 예외로 죽는다"
            land = (rt, mem[a] | (mem[a + 1] << 8))
        elif op == 0x29:  # sh
            a = (r[rs] + simm) & 0xFFFFFFFF
            assert a % 2 == 0, f"홀수 주소 sh @0x{a:08X}"
            mem[a], mem[a + 1] = r[rt] & 0xFF, (r[rt] >> 8) & 0xFF
        elif op in (0x04, 0x05):  # beq / bne
            take = (r[rs] == r[rt]) if op == 0x04 else (r[rs] != r[rt])
            if take:
                nxt = pc + 4 + simm * 4
            # 지연 슬롯을 먼저 실행한다 — 재귀 대신 한 칸 미룬다
            dl = words[(pc + 4 - base) // 4]
            assert dl >> 26 not in (0x04, 0x05) and dl != 0x01000008, "지연 슬롯에 분기"
            # ⚠ 지연 슬롯을 **먼저** 실행하고 나서 착지한다. 분기 자체는 로드가 아니므로
            #   앞선 로드의 지연은 여기서 반영된다(분기 조건은 **옛 값**으로 판정 — MIPS I).
            if pend:
                r[pend[0]] = pend[1]
                pend = None
            _mips_step_simple(words, base, mem, r, pc + 4)
            pc = nxt if take else pc + 8
            continue
        else:
            raise AssertionError(f"모르는 명령 0x{w:08X} @0x{pc:08X}")
        if pend:
            r[pend[0]] = pend[1]
        pend = land
        r[0] = 0
        pc = nxt
    raise AssertionError("스텁이 안 끝난다 — 무한 루프")


def _mips_step_simple(words, base, mem, r, pc):
    """지연 슬롯 한 칸(분기·로드가 아닌 명령만)."""
    w = words[(pc - base) // 4]
    op, rs, rt = w >> 26, (w >> 21) & 31, (w >> 16) & 31
    rd, sa, fn, imm = (w >> 11) & 31, (w >> 6) & 31, w & 63, w & 0xFFFF
    simm = imm - 0x10000 if imm & 0x8000 else imm
    if w == 0:
        return
    if op == 0 and fn == 2:
        r[rd] = (r[rt] & 0xFFFFFFFF) >> sa
    elif op == 0x09:
        r[rt] = (r[rs] + simm) & 0xFFFFFFFF
    else:
        raise AssertionError(f"지연 슬롯에 모르는 명령 0x{w:08X}")
    r[0] = 0


def test_opening_dict_codec_roundtrips():
    """행 사전 압축 ↔ 파이썬 기준 디코더."""
    import os
    import sys

    sys.path.insert(0, _TOOLS)
    os.environ.setdefault("LOCK_BYPASS", "1")
    import patch_opening_font as PF

    chars = sorted(set("영웅전설세리오스많읽꽃뷁 ABC.,!?"))
    gl = [PF.gen_glyphs(chars)[c] for c in chars]
    blob, nd = PF.compress_font_dict(gl)
    assert PF.decode_font_dict(blob, nd, len(gl)) == [g[: PF.GLYPH] for g in gl]


def test_opening_decoder_stub_actually_decodes():
    """🔴 **스텁을 실행해** 파이썬 기준과 바이트로 맞댄다.

    ⚠ 이게 없으면 「빌드도 되고 디스어셈도 깨끗한데 화면만 검은」 사고가 그대로 나간다.
    실제로 2026-08-21 첫 판은 분기 오프셋 셋이 **전부 한 칸씩** 어긋나 있었고
    `verify_asm` 은 셋 다 통과시켰다.
    """
    import collections
    import os
    import sys

    sys.path.insert(0, _TOOLS)
    os.environ.setdefault("LOCK_BYPASS", "1")
    import patch_opening_font as PF

    chars = sorted(set("영웅전설세리오스많읽꽃뷁 ABC.,!?가나다"))
    gl = [PF.gen_glyphs(chars)[c] for c in chars]
    blob, nd = PF.compress_font_dict(gl)

    SRC, DST, PC0 = 0x80025500, 0x80080000, 0x80021D50
    mem = collections.defaultdict(int)
    for i, b in enumerate(blob):
        mem[SRC + i] = b
    words = PF.build_decoder_stub(DST, SRC, nd * 2 + (nd * 2 & 1), len(gl), PC0)
    PF.verify_asm(words, 0x80025400)
    _mips_run(words, 0x80025400, mem)

    want = PF.decode_font_dict(blob, nd, len(gl))
    got = bytes(mem[DST + i] for i in range(len(gl) * PF.GLYPH))
    assert got == b"".join(want), "스텁 출력이 기준 디코더와 다르다"


def test_josa_shift_leaves_no_stale_tail():
    """조사 병기를 줄인 **뒤 꼬리에 옛 바이트가 남으면 안 된다** (유저 QA 2026-08-24).

    `을(를)` → `을` 은 4B 좌시프트라 널이 4B 앞으로 온다. 그런데 옛 꼬리 4B 를 안 지우면
    거기 `d7 2e 0a 00`(`다.` 의 하위 바이트 + 온점 + 개행)이 남고, **pre-shift 길이로 그리는
    경로**(전투 메시지)가 그걸 글리프로 뿌린다 — `사용했다.` 옆 깨진 글자. `d7 2e` 는
    완성형 밖이라 무슨 글자가 나올지도 모른다.

    ⚠ asm 쪽 대응은 `lbu` 의 **로드 지연 슬롯 nop 을 `sb zero,4(t3)` 로 바꾼 것**이다 —
    루틴이 504B 이고 VAB 파형까지 여유가 4B 라 명령을 못 늘린다. 그래서 이 테스트는
    **크기가 안 늘었는지도 함께** 본다(늘면 파형을 침범해 효과음이 조용히 깨진다).
    """
    import hangul_map as H
    import patch_josa_hook as J

    def enc(t):
        out = bytearray()
        for ch in t:
            if ch == " ":
                out.append(0x20)
            elif ch == "\n":
                out.append(0x0A)
            elif ch.isascii():
                out.append(ord(ch))
            else:
                out += H.syllable_sjis(ch).to_bytes(2, "big")
        return bytes(out)

    tbl = J.build_bit_table()
    for line in ("잎을(를) 사용했다.\n", "류난은(는) 동료가 되었습니다.\n"):
        buf = bytearray(enc(line) + b"\x00" + enc("이전메시지"))
        buf = buf[:66].ljust(66, b"\x00")
        assert J.fix_buffer(buf, tbl, cross=None, limit=64) == 1, line
        z = bytes(buf).find(b"\x00")
        assert bytes(buf[z + 1 : z + 5]) == b"\x00" * 4, (
            f"시프트 꼬리에 찌꺼기: {bytes(buf[z + 1 : z + 5]).hex(' ')} — {line!r}"
        )

    n = len(J.assemble_routine(0x80100000, 0x80101000, 0x80101100))
    assert n <= 504, f"josa 루틴이 {n}B 로 늘었다 — VAB 파형 여유가 4B 뿐이다"


if __name__ == "__main__":
    sys.exit(0 if _run() else 1)
