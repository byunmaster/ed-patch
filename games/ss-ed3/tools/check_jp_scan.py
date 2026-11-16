"""화면 일본어 「전체 훑기」 — 굽은 이미지의 파일 전부를 문자 코드 열로 훑어 **정본에 안 등록된** 일본어 런을 센다 (관리자 11-05, ps1-ed4 가 낸 구멍).

    python3 games/ss-ed3/tools/check_jp_scan.py            # 개수 · 목록
    python3 games/ss-ed3/tools/check_jp_scan.py --check    # 장부(script/jp_scan_accept.json) 밖 새 런 → rc 1
    python3 games/ss-ed3/tools/check_jp_scan.py --freeze   # 지금 목록을 장부로(사유는 손으로)

런 = Shift-JIS 히라가나 3자↑ 또는 가타카나 4자↑ 연속. 그래픽·무비·음원(`.FON`·`/CPK`·`/SAP`·`/SND`·`/END`)은 안 훑는다
(바이트열이 우연히 가나 코드처럼 읽힌다). 장부 열쇠 = `파일:런` — 사유는 「디버그 전용(일반 플레이에서 안 뜬다)」 · 「바이너리 우연」 중 하나다.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

ACCEPT = os.path.join(C.GAME_DIR, "script", "jp_scan_accept.json")
SKIP = ("/CPK", "/SAP", "/SND", "/END")
RUN = re.compile(rb"(?:\x82[\x9f-\xf1]){3,}|(?:\x83[\x40-\x96]){4,}")


def scan(disc=1):
    path = os.path.join(C.BUILD_DIR, f"Shiroki Majo (KR) (Disc {disc}).bin")
    if not os.path.exists(path):
        return None
    out = []
    d = C.Disc(path, user_off=C.USER_OFF)
    for name, lba, size in d.files():
        if name.endswith(".FON") or name.startswith(SKIP):
            continue
        for m in RUN.finditer(d.read_extent(lba, size)):
            out.append(f"{name}:{m.group().decode('shift_jis', 'replace')}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--freeze", action="store_true")
    a = ap.parse_args()
    got = scan()
    if got is None:
        print("  ⓘ 화면 일본어 전체 훑기는 못 쟀다 — 빌드 이미지가 없다")
        return
    acc = set()
    if os.path.exists(ACCEPT):
        with open(ACCEPT, encoding="utf-8") as fh:
            acc = set(json.load(fh).get("accept", []))
    new = sorted({k for k in got if k not in acc})
    print(f"  화면 일본어 전체 훑기 — 런 {len(got)} · 장부 {len(acc)} · 장부 밖 {len(new)}")
    if a.freeze:
        with open(ACCEPT, encoding="utf-8") as fh:
            doc = json.load(fh) if os.path.exists(ACCEPT) else {"_why": "", "reasons": {}}
        doc["accept"] = sorted(set(got))  # 래칫 — 번역돼 사라진 런은 장부에서도 뺀다
        with open(ACCEPT, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        print(f"  장부 → {len(doc['accept'])} (새 파일은 reasons 에 사유를 적는다)")
        return
    for k in new[:15]:
        print(f"    새 런 {k}")
    if a.check and new:
        print("  ❌ 정본에 없는 일본어 런이 있다 — 번역·등록하거나 장부에 사유로 둔다")
        sys.exit(1)
    if a.check:
        print("  ✅ 화면 일본어 전체 훑기 — 장부 밖 새 런 없음")


if __name__ == "__main__":
    main()
