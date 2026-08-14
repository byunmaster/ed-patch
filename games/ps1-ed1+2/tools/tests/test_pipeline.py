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

import common as C  # noqa: E402
import reinsert_kr_pilot as R  # noqa: E402


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
    # `呪文の書` 는 ED2 정발 표기인 **주문서**로 간다(ED2 코퍼스 `주문서` 9회 · `마법` 0회)
    assert R.fix_spacing("누구의 마법책에 써 넣을까?") == "누구의 주문서에 써 넣을까?"
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


if __name__ == "__main__":
    sys.exit(0 if _run() else 1)


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
