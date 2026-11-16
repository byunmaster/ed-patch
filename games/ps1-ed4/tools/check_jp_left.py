"""화면 일본어 잔존 게이트(기준선 래칫) — 이미지의 대본 조각 중 **가나·한자가 든 조각 수**가 기준선보다 **늘면 실패**.

    python3 tools/check_jp_left.py [--image 경로] [--freeze]

🔴 번역 전(지금)의 기준선 = 원본 전량이다. 번역이 진행되면 수가 줄고, 줄면 `--freeze` 로 기준선을 내린다(래칫).
늘면 — 재삽입이 조용히 조각을 원문으로 되돌렸거나(`size`·`fmt_drop` 탈락) 정본이 깨졌다는 뜻이라 서 있는 자리에서 막는다
(루트 CLAUDE.md 「화면에 나가는 바이트를 게이트로 본다」 — 빌드도 단위 테스트도 통과하는 부류).
⚠ 이건 **대본**만 잰다 — 실행파일 문자열(UI)·그림 글자는 아직 범위 밖이다(`status.md`).
`--image` 를 안 주면 원본을 잰다(= 기준선 자체의 재현). 제품 이미지는 `--image` 로.
"""

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import hangul
import textenc

from shared.ps1 import gmf_arc
from shared.ps1 import gmf_script as scriptmap

BASELINE = os.path.join(common.ROOT, "jp_left_baseline.json")


def is_jp(ch):
    o = ord(ch)
    if (
        o == 0x30FB
    ):  # 「・」 — 우리 「·」(가운뎃점)이 원판 점 글리프로 앉는 자리다. 일본어가 아니라 부호
        return False
    return 0x3040 <= o <= 0x30FF or 0x4E00 <= o <= 0x9FFF or ch == "々"


def screen_map():
    """{코드: 화면에 나가는 글자} — 원본 코드표 위에 **한글 자리 정본을 덮는다**.

    🔴 한글이 앉은 자리는 원래 한자 코드라, 원본 코드표로만 읽으면 한글을 한자로 센다(시험 빌드가 줄어들지 않았다).
    """
    m = dict(textenc.charmap())
    for ch, code in hangul.load().items():
        m[code] = ch
    return m


def original_codes():
    """{(아카이브, 멤버): [조각 코드열…]} — 원본 대본 덤프(`derived/script`). 바뀐 조각과 안 바뀐 조각을 가르는 기준이다."""
    out = {}
    for p in glob.glob(os.path.join(common.OUT_DIR, "script", "*.json")):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        out[(d["archive"], d["member"])] = [s["codes"] for s in d["segments"]]
    return out


def scan(image=None):
    """{segments: 가나·한자가 든 조각 수, chars: 그 글자 수, total: 전체 조각 수}

    🔴 **안 바뀐 조각은 원본 코드표로, 바뀐 조각은 한글 자리를 덮은 표로 읽는다** — 한글이 앉은 자리는 원래 한자 코드라 바뀐 조각을 원본 표로 읽으면 한글을 한자로 세고,
    안 바뀐 조각을 덮은 표로 읽으면 (한글 자리로 뺏긴 코드의) 일본어를 한글로 세어 **남은 일본어가 줄어 보인다**(10-24 번역 시작 때 기준선이 배정 수를 따라 흘렀다).
    """
    seg = chars = total = 0
    cm_raw = textenc.charmap()
    cm = screen_map()
    orig = original_codes()
    with common.open_disc(image) as d:
        for path, lba, size in d.files():
            if "/SC" not in path or not path.endswith(common.ARCHIVE_EXT) or size < 64:
                continue
            data = d.read_extent(lba, size)
            try:
                _, ents = gmf_arc.arc_parse(data)
            except gmf_arc.ArchiveError:
                continue
            for nm, off, sz in ents:
                if "\\BIN\\" not in nm or not nm.endswith(".BIN") or sz < 8:
                    continue
                base = orig.get((path, nm))
                for k, (_, codes) in enumerate(scriptmap.parse(data[off : off + sz])["segments"]):
                    total += 1
                    same = base is not None and k < len(base) and list(codes) == base[k]
                    m = cm_raw if same else cm
                    n = sum(1 for c in codes if c in m and is_jp(m[c]))
                    if n:
                        seg += 1
                        chars += n
    return {"segments": seg, "chars": chars, "total": total}


# 일본어가 남아도 되는 UI 자리 — **사유가 있는 예외만**(마스터 10-24 「일본어 0」). 시작·끝 오프셋(끝 미포함)과 사유.
UI_EXCEPT = [
    (0x72350, 0x7268A, "글리프 코드표 — 글자가 아니라 코드 대응표(화면에 안 그려진다)"),
]


def product_image():
    """(경로, 사유) — 제품 빌드가 있고 문안 입력보다 새것이면 그 경로, 아니면 (None, 사유)."""
    img = common.build_bin()
    if not os.path.exists(img):
        return None, "제품 빌드가 없다(`build_kr.py`)"
    t = os.path.getmtime(img)
    inputs = glob.glob(os.path.join(common.ROOT, "script", "*.json"))
    inputs += [
        os.path.join(common.ROOT, n)
        for n in ("ui_ed4.json", "narration_ed4.json", "hangul_map.json", "halfwidth_map.json")
    ]
    newest = max((os.path.getmtime(p) for p in inputs if os.path.exists(p)), default=0)
    if newest > t:
        return None, "제품 빌드가 문안보다 낡았다(다시 굽는다)"
    return img, ""


def ui_left():
    """([(오프셋, 원문)…] 예외 밖 미번역 UI 자리, [(오프셋, 사유)…] 예외) — 가나·한자가 든 자리만. `ui_ed4.json` + 정본 고유명사로 번역이 앉은 자리는 뺀다."""
    import uitext

    exe = bytes(common.read_file(common.EXE_PATH))
    ss = uitext.sites(exe)
    have = uitext.rows_for(ss)
    left, exc = [], []
    for off, s in sorted(ss.items()):
        if off in have or not any(is_jp(c) for c in s["jp"]):
            continue
        why = next((w for a, b, w in UI_EXCEPT if a <= off < b), None)
        (exc if why else left).append((off, why or s["jp"]))
    return left, exc


# 🔴 실행파일 텍스트 영역 훑기(11-05 관리자 판정) — `ui_ed4.json` 에 안 올라간 문자열은 위 `ui_left` 가 못 센다(수확 목록 밖 215조각이 제품에 일본어로 남았다).
# 영역: 메뉴 근처 0xA00~0x1000 · 문안 표 0x6D000~0x7B000. 글리프 코드표(0x72350~0x7268A)는 뺀다. 조각 = 0xFFFF 로 끝나는 코드열.
EXE_TEXT_AREAS = ((0xA00, 0x1000), (0x6D000, 0x7B000))
EXE_SKIP = ((0x72350, 0x7268A),)
# 일본어가 남아도 되는 **죽은 사본** — 사유가 있는 것만(관리자 11-05 「죽은 사본은 사유와 함께 예외 장부」). (시작, 끝(미포함), 사유)
EXE_DEAD = [
    (
        0xA38,
        0xA8C,
        "표 0xA38 아이템 메뉴 구조체 — 사용처 패치(마스터 B)로 둘째 동굴(`halfwidth.ITEM_STRUCT`)에 한글 구조체를 따로 싣고 읽는 기준을 돌렸다. 옛 자리는 읽히지 않는 사본. "
        "근거(11-05): 정적 — 원본에서 이 자리를 읽는 코드는 0x800256C4 한 곳(lui+addiu)이고 제품엔 그 참조가 없다 · "
        "동적 — 옛 자리를 0x7000 으로 덮고 보기·사용·교체·버리기 흐름을 돌려도 화면이 원본과 같고(차이 0.0), 양성 대조로 새 구조체를 덮으면 부메뉴 라벨·결과 메시지가 깨진다(헤드리스 drc=disabled, 읽기 BP 가 아니라 독약 시험)",
    ),
]


def exe_left(image):
    """[(오프셋, 원문)…] 제품 실행파일 텍스트 영역에서 한글 자리가 아닌 **가나**가 든 조각 — 일본어로 남은 것.

    한글은 원래 한자·기호·가나 슬롯 일부(ヵ·ヶ·ヲ 포함)를 빌려 앉으므로 `hangul_map` 코드는 가나로 안 센다(제품이 그 코드를 쓰는 한 한글이다).
    """
    import struct

    cm = textenc.charmap()
    hset = set(hangul.load().values())
    with common.open_disc(image) as d:
        exe = None
        for path, lba, size in d.files():
            if path.endswith("SLPS_015.40"):
                exe = d.read_extent(lba, size)
    n = len(exe) // 2 * 2
    w = struct.unpack_from(f"<{n // 2}H", exe, 0)
    out, start = [], 0
    for k, c in enumerate(w):
        if c != 0xFFFF:
            continue
        seg, off = w[start:k], start * 2
        start = k + 1
        if not (3 <= len(seg) <= 40) or not any(a <= off < b for a, b in EXE_TEXT_AREAS):
            continue
        if any(a <= off < b for a, b in EXE_SKIP) or any(a <= off < b for a, b, _w in EXE_DEAD):
            continue
        unk = sum(1 for x in seg if x not in cm)
        kana = sum(1 for x in seg if x not in hset and x in cm and "\u3040" <= cm[x] <= "\u30ff")
        if unk > 0.3 * len(seg) or kana < (2 if len(seg) <= 6 else 3) or kana < 0.25 * len(seg):
            continue
        out.append((off, "".join(cm.get(x, "?") for x in seg)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image")
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument(
        "--strict", action="store_true", help="제품 빌드가 없거나 낡았으면 실패(배포 전)"
    )
    a = ap.parse_args()
    image = a.image
    if image is None:
        # 🔴 원본 디스크를 재면 항상 「일본어 24,438조각」이라 아무것도 못 막는다(11-05 발견) — 제품 빌드를 잰다
        image, why = product_image()
        if image is None:
            print(f"제품 빌드를 안 쟀다 — {why}" + (" 🔴" if a.strict else ""))
            return 1 if a.strict else 0
    got = scan(image)
    left, exc = ui_left()
    got["ui"] = len(left)
    exe_rows = exe_left(image)
    got["exe"] = len(exe_rows)
    if a.freeze:
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump(got, f, indent=1)
        print(f"기준선을 {got} 로 박았다")
        return 0
    if not os.path.exists(BASELINE):
        print("🔴 기준선이 없다 — `--freeze` 로 먼저 박는다")
        return 1
    with open(BASELINE, encoding="utf-8") as f:
        base = json.load(f)
    if got["total"] != base["total"]:
        print(f"🔴 조각 총수가 다르다 {got['total']} (기준선 {base['total']}) — 구조가 바뀌었다")
        return 1
    up = (
        got["segments"] > base["segments"]
        or got["chars"] > base["chars"]
        or got["ui"] > base.get("ui", 10**9)
        or got["exe"] > base.get("exe", 10**9)
    )
    print(
        f"UI 일본어 잔존 — 예외 밖 {len(left)}자리 · 사유 있는 예외 {len(exc)}자리"
        + (" 🔴" if left else "")
    )
    for off, jp in left[:20]:
        print(f"  0x{off:06X} {len(jp)}자")
    print(
        f"화면 일본어 잔존 — 조각 {got['segments']:,}/{got['total']:,} · 글자 {got['chars']:,} "
        f"(기준선 {base['segments']:,} · {base['chars']:,})" + (" 🔴 늘었다" if up else "")
    )
    print(
        f"실행파일 텍스트 영역 일본어 조각 — {got['exe']} (기준선 {base.get('exe', '없음')})"
        + (" 🔴 늘었다" if got["exe"] > base.get("exe", 10**9) else "")
    )
    if got["exe"] > base.get("exe", 10**9):
        for off, jp in exe_rows[:20]:
            print(f"  0x{off:06X} {len(jp)}자")
    if not up and (
        got["segments"] < base["segments"]
        or got["chars"] < base["chars"]
        or got["exe"] < base.get("exe", 10**9)
    ):
        print("  ↓ 줄었다 — `--freeze` 로 기준선을 내린다(래칫)")
    return 1 if up else 0


if __name__ == "__main__":
    sys.exit(main())
