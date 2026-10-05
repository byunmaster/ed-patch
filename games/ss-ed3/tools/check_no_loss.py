"""**글 소실 없음** 불변식 — 구운 이미지를 되읽어 우리 문안이 **한 글자도 빠짐없이** 들어갔나.

    python3 games/ss-ed3/tools/check_no_loss.py

🔴 **조판·재삽입은 글자를 조용히 잃을 수 있다**(관리자 공유 2026-09-27). ps1-ed3+4 는
빌드가 대사 꼬리를 폭 한도로 잘라 버리고 있었는데 **검사기는 0 건**이었다 — 검사기들이
「넣으려던 문안」만 보고 「이미지에 들어간 것」은 안 봤기 때문이다.
이 게임에도 문안을 만지는 단계가 여럿이다 — `fix_orphans`(공백↔개행) · `center_narration`
(앞 공백) · `reinsert.fit`(뒤 패딩) · `wrap_desc`(설명 어절 접기) · 예산 초과 시 **원문 유지**.
⇒ 여기서는 **이미지 쪽에서** 본다: 이미지의 바이트를 한글 배정표로 되풀어 **공백·개행을 뺀
글자열**이 `script/` 의 그것과 같은가. 같지 않으면 어디서든 글자가 빠진(또는 섞인) 것이다.

⚠ 공백·개행·페이지(`\\f`)는 **빼고** 견준다 — 조판 단계들이 바꾸는 것이 딱 그것들이라서다.
⚠ 예산을 넘어 **원문을 그대로 둔** 조각도 소실로 센다 — 빌드는 경고만 내고 지나가므로
   화면에는 일본어가 뜬다. 이미 아는 것은 `KNOWN` 에 이유와 함께 적는다.
ⓘ 무비·음성 자막은 **그림·자막 트랙**이라 여기 없다 — 폭은 `movie_hardsub` 가 본다.
⚠ 이미지가 없으면 건너뛴다(구운 적 없는 트리에서 늘 빨간불이면 아무도 안 본다).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build
import check_build_discs as B
import check_sys_coverage as SC
import common as C
import hangul_map as H
import mapfile as M
import param as P
import reinsert as R
import reinsert_desc as RD
import reinsert_sys as RS
import typeset as T

from shared.text import sjis

#   이미 알고 둔 소실 — `(갈래, 열쇠)`: 이유. 비어 있는 것이 정상이다.
KNOWN = {}


def glyphs(s):
    """견줄 꼴 — 공백·개행·페이지를 뺀 글자열(전각 공백 포함)."""
    return "".join(ch for ch in s if not ch.isspace() and ch != "　")


def reverse(*tables):
    """`{SJIS 2바이트: 한글}` — 배정표를 거꾸로."""
    out = {}
    for t in tables:
        for ch, idx in t.items():
            out[bytes(sjis.sjis_of_index(idx))] = ch
    return out


def decode(body, rev):
    """이미지 바이트 → 글자열. 배정 슬롯은 한글로, 나머지는 `mapfile.text_of` 그대로."""
    out, i = [], 0
    while i < len(body):
        two = bytes(body[i : i + 2])
        if two in rev:
            out.append(rev[two])
            i += 2
            continue
        #   🔴 주입 토큰(`01 <번호>`)이 먼저다 — 번호가 인쇄 가능한 바이트면 글자로 읽힌다
        if body[i] == M.CTRL_INJECT and i + 1 < len(body):
            out.append(M.text_of(body[i : i + 2]))
            i += 2
            continue
        #   ⚠ 반각 부호·숫자는 직접 푼다 — `text_of` 는 문맥 없이 한 바이트만 받으면
        #     `<20>`·`<2E>` 로 적는다(첫 판이 이것 때문에 3 만 건을 소실로 셌다)
        if 0x20 <= body[i] < 0x7F:
            out.append(chr(body[i]))
            i += 1
            continue
        #   나머지(제어·SJIS)는 원래 디코더에 맡긴다
        step = 2 if M.is_sjis_pair(body, i) else 1
        out.append(M.text_of(body[i : i + step]))
        i += step
    return "".join(out)


def check_maps(disc, img, files, rev):
    """대사 블록 — 원본의 블록 자리(오프셋·길이)에서 이미지를 읽어 되푼다."""
    bad, n = [], 0
    with C.open_disc(disc) as d:
        orig = {name: (lba, size) for name, lba, size in d.files()}
    for name, (lba, size) in files.items():
        ok, stem = C.is_map_file(name)
        if not ok:
            continue
        script, _ = R.load_script(stem)
        if not script:
            continue
        with C.open_disc(disc) as d:
            src = d.read_extent(*orig[name])
        got = B.read_extent(img, lba, size)
        blocks = M.blocks(src)
        for key, kr in script.items():
            blk = blocks[int(key)]
            body = got[blk["off"] : blk["off"] + len(blk["body"])]
            if blk["off"] == M.NAME_OFF:
                #   맵 이름은 원문보다 길게 쓸 수 있다(`reinsert.NAME_MAX`) — NUL 까지 읽는다
                body = got[blk["off"] : got.index(b"\x00", blk["off"])]
            n += 1
            if glyphs(decode(body, rev)) != glyphs(kr):
                bad.append((f"{stem}[{key}]", kr, decode(body, rev)))
    return n, bad


def check_desc(img, files, rev):
    """설명문 — `PARAM.BIN` 두 영역을 NUL 로 갈라 색인대로 견준다."""
    lba, size = files[P.PATH]
    got = B.read_extent(img, lba, size)
    src = P.load()
    tables = RD.table()
    bad, n = [], 0
    for name, area in RD.AREAS:
        kr = tables.get(name) or {}
        parts_src = src[area[0] : area[1]].split(b"\x00")
        parts_got = got[area[0] : area[1]].split(b"\x00")
        idx = 0
        for raw, now in zip(parts_src[:-1], parts_got[:-1], strict=False):
            if not raw:
                continue
            try:
                if raw.decode("shift_jis").isascii():
                    continue
            except UnicodeDecodeError:
                continue
            s = kr.get(str(idx))
            idx += 1
            if s is None:
                continue
            n += 1
            txt = decode(now, rev).replace(T.DESC_NL, "")
            if glyphs(txt) != glyphs(s):
                bad.append((f"{name}[{idx - 1}]", s, txt))
    return n, bad


def check_sys(img, files):
    """시스템 문자열 — 표의 **원문이 이미지에 남아 있으면** 소실이다(화면에 일본어가 뜬다).

    ⚠ 「우리 값이 이미지에 있나」로 보면 안 된다(첫 판이 13 건을 헛짚었다) — 셋이 정상인데
    값이 안 보인다: ① **더 긴 문자열에 흡수된 키**(`買いました` 는 `%sを⏎買いました` 안에만
    있다) ② **같은 원문의 다른 키에 가려진 키**(백업 안내 — 앞 공백 판이 먼저 들어가 `\\x00`
    판은 찾을 자리가 없다) ③ **다른 꼴로 저장된 원문**(장 제목). 그래서 원문 쪽에서 본다 —
    `reinsert_sys` 와 같은 파서로 읽은 문자열 + 원문 바이트열 그대로, 둘 다.
    """
    tbl = RS.table()
    ok = SC.accepted()
    bad, n = [], 0
    for f in RS.FILES:
        if f not in files:
            continue
        got = B.read_extent(img, *files[f])
        strs = RS.S.strings(got, RS.S.load_base(f))
        for s in strs:
            _lead, jp = RS.split_lead(RS.S.text_of(s["raw"]))
            if jp in tbl:
                bad.append((jp, tbl[jp], f"{f} +{s['off']:#x} 에 원문이 남았다"))
        #   ⚠ 짧은 원문(`設定`)은 **사유를 적어 받아들인 문자열 안**에서도 걸린다 — 개발자 메뉴
        #     `Level設定くん` 이 실제로 그랬다(첫 판이 이걸 소실로 셌다). 그 안의 일치는 뺀다.
        #   ⚠ 받아들임 대장의 오프셋은 **원본** 파싱 기준이다 — 구운 이미지를 파싱하면 그 문자열이
        #     안 잡힌다(한글로 바뀐 이웃이 경계를 흔든다). 그래서 구간은 원본에서 읽는다.
        with C.open_disc(1) as d:
            orig = d.read(f)
        spans = [
            (s["off"], s["off"] + len(s["raw"]))
            for s in RS.S.strings(orig, RS.S.load_base(f))
            if f"{f}:{s['off']}" in ok
        ]
        for jp, kr in tbl.items():
            pat = jp.encode("shift_jis")
            if len(pat) < 4:
                continue
            at = got.find(pat)
            while at >= 0 and any(a <= at < b for a, b in spans):
                at = got.find(pat, at + 1)
            if at >= 0:
                bad.append((jp, kr, f"{f} +{at:#x} 에 원문 바이트가 남았다"))
    n = len(tbl)
    #   같은 자리를 두 길로 잡으면 두 번 세인다
    seen, out = set(), []
    for b in bad:
        if b[0] not in seen:
            seen.add(b[0])
            out.append(b)
    return n, out


def main():
    rev_main = reverse(H.load())
    rev_desc = reverse(H.load(), H.load_low())
    total, fails = 0, []
    for disc in (1, 2):
        img = build.out_paths(disc)[0]
        if not os.path.exists(img):
            print(f"  ⏭ disc{disc} 이미지 없음 — 건너뛴다")
            continue
        files = {name: (lba, size) for name, lba, size, *_ in build.patched(disc)}
        for what, (n, bad) in (
            ("대사", check_maps(disc, img, files, rev_main)),
            ("설명", check_desc(img, files, rev_desc)),
            ("시스템", check_sys(img, files)),
        ):
            bad = [b for b in bad if (what, b[0]) not in KNOWN]
            total += n
            fails += [(disc, what, *b) for b in bad]
            print(f"  disc{disc} {what:<4} {n:>6} 건 · 소실 {len(bad)}")
    for disc, what, key, want, got in fails[:40]:
        print(f"  ❌ disc{disc} {what} {key}\n     문안 {want!r}\n     이미지 {got!r}")
    if fails:
        print(f"\n🔴 글 소실 {len(fails)} — 이미지에 문안이 다 안 들어갔다")
        return 1
    print(f"✅ 글 소실 없음 ({total:,} 건, 공백·개행 제외 글자열 일치)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
