"""**빌드 이미지에 남은 일본어**를 전수로 훑는다 — 「무엇이 아직 안 됐나」의 정본.

    python3 tools/scan_untranslated.py            # 본체 둘 (ED.BIN · ED2.BIN)
    python3 tools/scan_untranslated.py --mon      # + 몬스터 파일
    python3 tools/scan_untranslated.py --scn      # + 씬 파일 (본편 대사)
    python3 tools/scan_untranslated.py --all      # ⭐ **전부** — 화면에 나가는 것의 정본

🔴 **`--all` 이 「전부」를 안 뜻하던 시절이 있었다**(~2026-08-30). 본체 + 몬스터까지만이고
   **씬 파일 93개(본편 대사)를 안 봤는데**, 그 상태로 낸 「합계 0줄」이 status 에 「✅ 남은
   일본어 0줄」로 올라가 **다 끝난 것처럼 읽혔다.** `--scn` 으로 돌리니 **31줄**이 나왔다.
   ⇒ 이름이 커버리지를 속이면 아무도 의심하지 않는다(체크리스트 4-B). `--all` 은 전부다.

## 왜 필요한가

지금까지 미번역은 **유저가 인게임에서 만나야** 드러났다 — 회심의 일격, ED2 전투 HUD,
세이브 없는 슬롯. 확률이나 특정 경로에 걸리면 QA 를 몇 바퀴 돌아도 안 나온다.

⚠ `check_fixed_copy.py` 는 「칸에 맞나」만 본다. **「번역이 됐나」는 아무도 안 봤다.**

## 무엇을 일본어로 치나

**가나**(히라가나·가타카나, 반각 포함)가 든 문자열. 한자만 있는 것은 세지 않는다 —
숫자 단위나 기호로 남는 자리가 있고, 우리가 굳이 안 바꾸는 것도 있다.

## 무엇을 빼나 — 이게 이 도구의 값이다

    ① **반각 가나 내부 키** (`ｴﾙｱｽﾀ`·`ﾙﾃﾞｨｱT`·`ｲｼｭ/ｲｽ`) — 화면에 안 나온다. 건드리면 부순다.
    ② **코드·데이터 안의 우연한 SJIS** — 포인터가 안 가리키는 자리는 문자열이 아니다.
    ③ **씬 파일** (기본) — 본편 대사는 아직 착수 전이라 통째로 일본어인 게 정상이다.

그래서 **포인터가 가리키는 자리**만 문자열로 친다. `ED2MON*` 처럼 코드와 텍스트가 NUL
없이 붙은 파일에서 특히 중요하다.
⚠ 적재 주소는 파일군마다 다르다(`dump_scn.BASES`) — 상수를 쓰면 한 곳도 안 잡힌다.
"""

import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import dump_scn

MAIN = ["/ED.BIN", "/ED2.BIN"]
MON = [f"/BIN/ED2MON{i:02d}.BIN" for i in range(1, 11)]
MAXLEN = 96


def _has_kana(s):
    """전각 가나가 있나. ⚠ **반각 가나는 안 센다** — 내부 키다(위 ① 주석)."""
    return any("぀" <= c <= "ヿ" for c in s)


def _internal_key(s):
    """반각 가나가 섞였으면 내부 키 — 화면에 안 나온다(`patch_ui._internal_key` 와 같은 규칙).

    🔴 **단 히라가나가 있으면 문장이다**(2026-09-27). 레벨업 배분 문구 「%dﾎﾟｲﾝﾄ力を高められます。」
       가 반각 `ﾎﾟｲﾝﾄ` 때문에 내부 키로 걸러져 **화면에 일본어가 남았는데 0줄**이었다(마스터 화면).
       내부 키(`ｲｼｭﾀ～ｲｽﾞｰ`·`ｳｲﾙ～城`)는 한자·물결은 섞여도 **히라가나는 안 쓴다.**
    """
    return any("ｦ" <= c <= "ﾟ" for c in s) and not any("ぁ" <= c <= "ゟ" for c in s)


def _decode(raw, capped):
    """cp932 로 읽는다. 못 읽으면 None — **우리 슬롯 코드가 들어간 자리**라는 뜻이다.

    🔴 **길이 상한에서 자른 것은 예외다**(2026-09-03). `MAXLEN` 에서 끊으면 두 바이트
       글자의 한복판일 수 있고, 그러면 **일본어가 그대로인 자리를 「번역됐다」로 넘긴다.**
       실측: `ED1SCN27` 0x5A9C(127B)가 96B 에서 잘려 조용히 빠져 있었다 — 화면엔
       「クリスタル水族館へ ようこそ !」가 그대로 떠 있는데 검사기는 0줄이라고 했다.
    ⚠ SJIS 는 최대 2바이트라 **한 바이트만 물러서면** 충분하다.
    """
    try:
        return raw.decode("cp932")
    except UnicodeDecodeError:
        pass
    if not capped:
        return None
    try:
        return raw[:-1].decode("cp932")
    except UnicodeDecodeError:
        return None


def strings(d, base):
    """`{포인터 오프셋: (대상 오프셋, 문자열)}` — **포인터가 가리키는 자리**만.

    🔴 **키가 포인터 자리다.** 재삽입은 문자열을 옮기고 **포인터를 갱신**하므로, 빌드에서
       같은 걸 보려면 **그 포인터를 다시 읽어** 따라가야 한다. 원본 오프셋을 그대로 읽으면
       옮겨 간 자리의 **원문 잔재**를 보고 「아직 일본어」로 오보한다(실측 2026-08-27:
       329줄 중 상당수가 그랬다).
    """
    out = {}
    seen = set()
    for o in range(0, len(d) - 3, 2):
        v = struct.unpack(">I", d[o : o + 4])[0]
        if not (base <= v < base + len(d)):
            continue
        t = v - base
        if t in seen:
            continue
        seen.add(t)
        j = t
        while j < len(d) and d[j] != 0 and j - t < MAXLEN:
            j += 1
        got = _decode(bytes(d[t:j]), j - t >= MAXLEN)
        if got is not None:
            out[o] = (t, got)
    return out


def scan(path, mm, files):
    """`[(오프셋, 남은 일본어)]` — 빌드 이미지 기준."""
    base = dump_scn.base_for(os.path.basename(path))
    assert base, path
    built = bytes(common.read_extent(mm, *files[path]))
    orig = bytes(common.extract(path))
    left = []
    for o, (t, _jp) in sorted(strings(orig, base).items()):
        # ⚠ **빌드에서 포인터를 다시 읽는다** — 재삽입이 자리를 옮겼으면 그게 지금 자리다
        nv = struct.unpack(">I", bytes(built[o : o + 4]))[0]
        t = nv - base if base <= nv < base + len(built) else t
        j = t
        while j < len(built) and built[j] != 0 and j - t < MAXLEN:
            j += 1
        now = _decode(bytes(built[t:j]), j - t >= MAXLEN)
        if now is None:
            continue  # 우리 슬롯 코드가 들어갔다 — 번역된 자리다
        if not _has_kana(now) or _internal_key(now):
            continue
        left.append((t, now))
    return left


# 🔴 **가나로만 판정하면 한자만 든 문자열이 원리적으로 빠진다**(2026-09-06). 우리 슬롯도
#    한자로 디코드되므로 「가나가 없다 = 번역됐다」가 아니다. 그래서 축을 하나 더 둔다 —
#    **빌드와 원본의 바이트를 자리마다 대조**해 「안 건드린 자리」를 센다. 한자든 가나든 걸린다.
#
# ⚠ 그냥 세면 늘 빨간불이라 아무도 안 본다 — **알고 남긴 것**을 여기 적고 뺀다.
#    적을 때는 **왜 남기는지**를 같이 적는다. 「그냥 원래 그랬다」는 사유가 아니다.
KEEP = {
    # 「メニュートップ」를 그리고 **무한 루프로 끝나는 개발자 화면**의 글자 둘.
    # 함수 시작(ED `0x4CBB4` · ED2 `0x03B930`)이 리터럴 포인터 0 · bsr/bra 0 — **도달 불가**.
    # 뜻을 모르는 채 옮기면 화면에 엉뚱한 글자가 박히고, 애초에 안 뜬다(유저 판단 2026-09-06).
    "闘": "도달 불가한 개발자 화면(メニュートップ)",
    "働": "도달 불가한 개발자 화면(メニュートップ)",
}
# SJIS 로 우연히 읽히는 **코드·자료**를 거른다.
# ⚠ 「셋 이상 이어진 것」으로 걸렀더니 **홑글자 한자가 빠졌다** — 바로 그 `闘`·`働` 을
#   못 잡는다. 길이가 아니라 **구성**으로 가른다: 전부 일본어 글자여야 한다.
#   그러면 `CAﾃy7烙`(ASCII 섞임) · `ﾐ臥`(반각 가나) 같은 바이너리는 빠지고,
#   `ＭＧ１４`(전각 라틴·숫자, 방침상 안 옮긴다)도 빠진다.
_JP1 = re.compile(r"[ぁ-ゟ゠-ヿ一-鿿]")
_JPOK = re.compile(r"^[ぁ-ゟ゠-ヿ一-鿿、。・ー〜「」　\n]+$")


def _pure_jp(s):
    return bool(_JP1.search(s) and _JPOK.match(s))


def untouched(path, mm, files):
    """**원본 바이트 그대로 남은** 자리 → `[(오프셋, 원문)]`. 가나 판정의 사각지대를 메운다."""
    import patch_scn

    got = patch_scn.load(path)
    if not got or path not in files:
        return []
    base, ent = got
    lba, size = files[path]
    built = common.read_extent(mm, lba, size)
    out = []
    for e in ent:
        jp, pa = e.get("text"), e.get("ptr_at")
        if not jp or not pa or jp in KEEP or _internal_key(jp):
            continue
        if not _pure_jp(jp):
            continue  # 서식·파일명·전각 라틴·바이너리는 대상이 아니다
        p = int(pa[0], 16)
        if p + 4 > len(built):
            continue
        at = int.from_bytes(built[p : p + 4], "big") - base
        if not (0 <= at < len(built)):
            continue
        j = built.find(b"\x00", at)
        if built[at:j] == bytes.fromhex(e["raw_hex"]):
            out.append((at, jp))
    return out


def main():
    common.verify_source()
    paths = list(MAIN)
    every = "--all" in sys.argv
    if every or "--scn" in sys.argv or "--mon" in sys.argv:
        paths += MON
    if every or "--scn" in sys.argv:
        _f0, mm0 = common.open_image()
        paths += sorted(p for p, _l, _s in common.iso_files(mm0) if "SCN" in p)
        mm0.close()
        _f0.close()
    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    if not os.path.exists(dst):
        raise SystemExit(f"먼저 빌드한다 — {dst} 가 없다")
    _f, mm = common.open_image(dst)
    files = {p: (lba, s) for p, lba, s in common.iso_files(mm)}

    total = 0
    for path in paths:
        if path not in files:
            continue
        left = scan(path, mm, files)
        total += len(left)
        if not left:
            # ⚠ **깨끗한 파일은 한 줄도 안 찍는다** — 93파일이면 초록 93줄이 게이트 로그를
            #    덮어 정작 봐야 할 줄이 밀려난다(실측 2026-09-06). 합계만 남긴다.
            continue
        print(f"  {path}: {len(left)}줄")
        for t, s in left[:40]:
            print(f"     0x{t:06X}  {s!r}")
        if len(left) > 40:
            print(f"     … 그 외 {len(left) - 40}줄")
    # ── 바이트 대조 축 (가나 판정이 못 보는 자리)
    kept = 0
    for path in paths:
        if path not in files:
            continue
        for at, jp in untouched(path, mm, files):
            kept += 1
            print(f"  🔴 {path} 0x{at:06X} 원본 바이트 그대로 — {jp[:40]!r}")
    mm.close()
    _f.close()
    mark = "✅" if not (total or kept) else "🔴"
    print(
        f"  {mark} 파일 {len(paths)} — 남은 일본어 {total}줄 · 바이트가 원본 그대로인 자리 "
        f"{kept} (알고 남긴 것 {len(KEEP)}종 제외)"
    )
    # 🔴 **남은 일본어도 실패다**(2026-09-27). 전엔 바이트 대조만 실패로 쳐서, 가나가 남아도 종료 코드가
    #    0 이었다 — 그리고 `check.sh` 의 `step` 은 ✅ 줄만 보여 주므로 🔴 합계 줄이 **통째로 가려졌다.**
    #    실측: 사전 스냅숏 시험 빌드가 일본어를 남긴 채 「✅ 커밋해도 되는 상태」로 끝났다.
    if total:
        raise SystemExit(f"남은 일본어 {total}줄 — 위 목록")
    if kept:
        raise SystemExit("원본 바이트 그대로인 자리가 있다 — 옮기거나 `KEEP` 에 사유와 함께 적는다")


if __name__ == "__main__":
    main()
