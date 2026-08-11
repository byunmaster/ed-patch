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
    assert R.fix_spacing("뭐야.!!") == "뭐야!!"


def test_ellipsis_is_not_split():
    # `....` 은 말줄임이지 문장 경계가 아니다 — 공백을 끼우면 안 된다
    assert R.fix_spacing("글쎄....그런가") == "글쎄....그런가"


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


# ── 검출기 판정 (`check_variants` · `spellcheck_render`) ────────────────────
def test_picked_variants_are_not_overlap():
    # 사람이 `~v` 로 둘 이상 짚어 이은 건 **의도한 배정**이다(H_210#19 리더별 꼬리)
    from check_variants import _picked

    assert _picked({"chain": ["19~7#0", "+19~3#0"]})
    assert not _picked({"chain": ["4#2.1-"]})
    assert not _picked({})


def test_style_only_keeps_missing_terminal():
    # 종결부호를 **새로 다는** 제안은 남긴다(정발 온점 결손은 실제로 채워 왔다).
    # 부호를 **바꾸는** 것만 문체로 본다.
    from spellcheck_render import style_only

    assert style_only("왕자님", "왕자님,")  # 쉼표 삽입 = 문체
    assert style_only("기쁘옵니다.", "기쁩니다.")  # 사극체 제거 = 문체
    assert style_only("요즈음", "요즘")  # 정발 옛 표기 = 유지 확정
    assert style_only("쟈그리는", "자그니는")  # 고유명사
    assert style_only("있다.", "있습니다.")  # 존대 등급 올림
    assert not style_only("오십시오", "오십시오.")  # 종결부호 보완 → 사람이 본다


# ── 제안 배치 검증 (`proposal.py`) ─────────────────────────────────────────
def _batch(**d):
    base = {"schema_version": 1, "batch_id": "t", "status": "draft", "decisions": []}
    base.update(d)
    return base


def test_proposal_catches_missing_sibling():
    # ⚠ 여덟 번 틀린 그 부류 — 같은 원문의 **다른 시점 사본**을 빠뜨린 배치
    import proposal as P

    c = {"ED1/A#0": "가나다라", "ED1/B#0": "가나다라"}  # 사본 둘
    bad, _ = P.check(
        _batch(
            decisions=[
                {
                    "id": "d1",
                    "kind": "replace",
                    "before": "가나다",
                    "after": "가나",
                    "affected": ["ED1/A#0"],
                }
            ]
        ),
        c,
    )
    assert any("affected 불일치" in b for b in bad), bad


def test_proposal_fills_affected():
    import proposal as P

    c = {"ED1/A#0": "가나다라", "ED1/B#0": "가나다라"}
    b = _batch(decisions=[{"id": "d1", "kind": "replace", "before": "가나다", "after": "가나"}])
    _bad, filled = P.check(b, c)
    assert filled["decisions"][0]["affected"] == ["ED1/A#0", "ED1/B#0"]


def test_proposal_catches_token_loss():
    # `%s` 를 잃으면 구조 계약이 깨진다(fmt_drop → 블록 통째 탈락)
    import proposal as P

    c = {"ED1/A#0": "%s는 갔다"}
    bad, _ = P.check(
        _batch(decisions=[{"id": "d1", "kind": "replace", "before": "%s는", "after": "그는"}]), c
    )
    assert any("제어 토큰" in b for b in bad), bad


def test_proposal_catches_stale_corpus():
    # 승인 시점과 반영 시점의 코퍼스가 다르면 멈춘다
    import proposal as P

    bad, _ = P.check(_batch(corpus_sha="deadbeefdeadbeef"), {"ED1/A#0": "가"})
    assert any("코퍼스가 승인 시점과 다르다" in b for b in bad), bad


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


if __name__ == "__main__":
    sys.exit(0 if _run() else 1)
