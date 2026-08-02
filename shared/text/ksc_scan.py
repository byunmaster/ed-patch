"""한국어 DOS 게임 바이너리에서 **KSC-5601(cp949) 문장을 긁어내는** 공용 스캐너.

컨테이너 포맷을 몰라도 된다 — 맞춤법·띄어쓰기 검수의 산출물은 리터럴 치환쌍이라
블록 구조·엔트리 번호가 필요 없다. 그래서 정식 추출기가 없는 타이틀도 이걸로
바로 검수할 수 있다(ED3/ED4 처럼 `AFLB DAT` 컨테이너를 아직 안 판 경우).

⚠ 정식 텍스트 파이프라인 대용이 **아니다**. 이식·재삽입에는 블록 구조가 필요하니
게임별 추출기를 따로 판다. 이건 어디까지나 문안 검수용 코퍼스다.

CLI
  python3 -m text.ksc_scan <디렉터리> --name ED3 --out <검토 디렉터리>
  python3 -m text.ksc_scan <디렉터리> --name ED3 --report   # 캐시로 보고서만
"""

import argparse
import glob
import json
import os
import re
import sys

if __package__ in (None, ""):  # 직접 실행 대비
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from text import spellcheck as sc
else:
    from . import spellcheck as sc

HANGUL = re.compile(r"[가-힣]")
# 문장 끝 — 종결부호 뒤. 정발은 ` !!` 처럼 부호 앞을 띄우므로 부호를 다 삼킨다.
SENT_END = re.compile(r"(?<=[.!?…])(?=\s)|(?<=[.!?…])$")
# 스캔 잔재: 제어 인자 한 글자가 문장에 끼어든다(정식 추출기가 없으니 더 흔하다).
RESIDUE = re.compile(r"^[^\s.가-힣0-9]\s+|(?<=\s)[A-Za-z](?=\s|$)")
MIN_SYL = 4  # 이만큼 이상 한글 음절이 이어져야 문장 후보


# ⚠ cp949 전체(0x81~0xFD 선두)를 받으면 **임의 바이너리가 한글로 디코드된다** — 확장완성형
# 영역이 넓어서 `㉣뉩맘덟냇` 같은 쓰레기가 쏟아진다(실측). 정발 DOS 문안은 KS X 1001
# 완성형(선두 0xB0~0xC8)만 쓰므로 거기로 좁힌다. 우연히 4음절이 이어질 확률은 ~1.6e-6.
def _is_lead(b):
    return 0xB0 <= b <= 0xC8


def _is_trail(b):
    return 0xA1 <= b <= 0xFE


def runs(buf):
    """바이너리 → cp949 로 읽히는 텍스트 런(한글 {MIN_SYL}음절 이상)."""
    out, i, n = [], 0, len(buf)
    while i < n:
        if not (i + 1 < n and _is_lead(buf[i]) and _is_trail(buf[i + 1])):
            i += 1
            continue
        j, syl = i, 0
        while j < n:
            if j + 1 < n and _is_lead(buf[j]) and _is_trail(buf[j + 1]):
                syl += 1
                j += 2
            elif buf[j] in (0x20, 0x21, 0x2C, 0x2E, 0x3F) or 0x30 <= buf[j] <= 0x39:
                j += 1  # 문장 안에 섞이는 공백·부호·숫자
            else:
                break
        if syl >= MIN_SYL:
            try:
                t = buf[i:j].decode("cp949")
            except UnicodeDecodeError:
                t = buf[i:j].decode("cp949", "ignore")
            if HANGUL.search(t):
                out.append(t)
        i = max(j, i + 2)
    return out


def sentences(paths):
    """{문장: 등장 횟수} — 파일 목록에서 긁어 문장으로 쪼개고 센다."""
    uniq = {}
    for p in paths:
        for t in runs(open(p, "rb").read()):
            for s in SENT_END.split(t):
                s = re.sub(r"\s+", " ", RESIDUE.sub(" ", s.strip()).strip()).strip()
                if len(HANGUL.findall(s)) >= MIN_SYL:
                    uniq[s] = uniq.get(s, 0) + 1
    return uniq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="스캔할 디렉터리")
    ap.add_argument("--name", required=True, help="타이틀 이름(ED3 등) — 산출물 접두")
    ap.add_argument("--out", required=True, help="검토 산출물 디렉터리(gitignore 아래)")
    ap.add_argument("--glob", default="*.DAT", help="파일 패턴")
    ap.add_argument("--chunk", type=int, default=900)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--known", help="이미 반영된 replace 를 가진 JSON(중복 제외용)")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    paths = [p for p in sorted(glob.glob(os.path.join(a.src, a.glob))) if os.path.isfile(p)]
    uniq = sentences(paths)
    keys = sorted(uniq)
    meta = {s: {"n": c, "inject": False} for s, c in uniq.items()}
    print(f"{a.name}: 파일 {len(paths)} · 문장 {len(keys)}종")

    cache_p = os.path.join(a.out, f"{a.name}_spell_cache.json")
    cache = json.load(open(cache_p, encoding="utf-8")) if os.path.exists(cache_p) else {}

    def save(c):
        json.dump(c, open(cache_p, "w", encoding="utf-8"), ensure_ascii=False)

    parts = sc.chunks(keys, a.chunk)
    n_new = len([p for p in parts if "\n".join(p) not in cache])
    print(f"  청크 {len(parts)}개 · 캐시 {len(parts) - n_new} · 요청 {0 if a.report else n_new}")
    if not a.report:
        sc.fetch(parts[: a.limit] if a.limit else parts, cache, jobs=a.jobs, on_save=save)

    changed, pairs, skewed = sc.collate(parts, cache, meta)
    known = json.load(open(a.known, encoding="utf-8")).get("replace", []) if a.known else []
    auto, manual, dropped = sc.classify(pairs, known)
    open(os.path.join(a.out, f"{a.name}_spell_report.md"), "w", encoding="utf-8").write(
        sc.report(f"{a.name} 맞춤법 검사 결과", len(keys), changed, auto, manual, dropped, skewed)
    )
    json.dump(
        {"auto": [[x, y] for x, y, _ in auto], "manual": [[x, y] for x, y, _ in manual]},
        open(os.path.join(a.out, f"{a.name}_spell_pairs.json"), "w", encoding="utf-8"),
        ensure_ascii=False,
        indent=1,
    )
    print(f"  → {a.name}_spell_report.md · A급 {len(auto)} · B급 {len(manual)}")


if __name__ == "__main__":
    main()
