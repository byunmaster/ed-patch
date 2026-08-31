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
    """반각 가나가 섞였으면 내부 키 — 화면에 안 나온다(`patch_ui._internal_key` 와 같은 규칙)."""
    return any("ｦ" <= c <= "ﾟ" for c in s)


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
        try:
            out[o] = (t, d[t:j].decode("cp932"))
        except UnicodeDecodeError:
            pass
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
        try:
            now = bytes(built[t:j]).decode("cp932")
        except UnicodeDecodeError:
            continue  # 우리 슬롯 코드가 들어갔다 — 번역된 자리다
        if not _has_kana(now) or _internal_key(now):
            continue
        left.append((t, now))
    return left


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
            print(f"  ✅ {path}: 남은 일본어 없다")
            continue
        print(f"  {path}: {len(left)}줄")
        for t, s in left[:40]:
            print(f"     0x{t:06X}  {s!r}")
        if len(left) > 40:
            print(f"     … 그 외 {len(left) - 40}줄")
    mm.close()
    _f.close()
    print(f"\n합계 {total}줄")


if __name__ == "__main__":
    main()
