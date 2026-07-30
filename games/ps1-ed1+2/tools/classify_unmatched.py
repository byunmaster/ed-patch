"""미매칭 JP 블록 분류 — 정발 회수 가능(정렬이 놓침) vs 신규 번역 필요.

크루즈 구간처럼 '아직 일본어'인 미매칭 블록을 플레이 QA 전에 갈라둔다. 각 미매칭 JP를
정발 KR 풀에 LaBSE로 재임베딩해 best-match 코사인으로 판정한다.

**전-게임 풀 대조**: 씬 풀(align_semantic이 쓰는 same-scene 제약)만 보면, 정발 대사가 다른
씬 테이블에 들어간 경우(파일명 씬규칙 오귀속·리메이크 재배치)를 '신규'로 오분류한다. 그래서
전 ED1 테이블을 후보로 놓고, 회수처가 다른 씬이면 [cross-scene]으로 표시한다.

사용: python3 tools/classify_unmatched.py ED1 1 36 566
출력: out/review/unmatched_<game>SCN<n>_<lo>-<hi>.md (+ 요약 stdout)
"""

import json
import os
import sys

from align_jp_kr import DOS_KR_DIR, load_jp_scene, norm_body
from common import OUT_DIR, REVIEW_DIR, ROOT

HI_SIM = 0.55  # 이상 = 회수가능(강한 정발 대응)
MID_SIM = 0.45  # 이상 = 경계, 미만 = 신규


def scene_of_table(stem):
    """파일명 T_0Nx → 씬 N+1 (load_kr_scene의 규칙 역산). 규칙 밖이면 None."""
    return int(stem[2]) + 1 if len(stem) >= 3 and stem[2].isdigit() else None


def load_all_kr(game):
    """게임 전체 정발 KR 블록(씬 무관) → [{table, id, speaker, body, scene}]."""
    dir_ = os.path.join(DOS_KR_DIR, game)
    out = []
    for fname in sorted(os.listdir(dir_)):
        if not fname.endswith(".json") or fname.startswith(("_", "._")):
            continue
        scene = scene_of_table(fname[:-5])
        doc = json.load(open(os.path.join(dir_, fname), encoding="utf-8"))
        cur = None
        for e in doc["entries"]:
            if e["kind"] != "block" or "no_body" in e["flags"]:
                continue
            if e["speaker"]:
                cur = e["speaker"]
            body = norm_body(e["text"])
            if body.strip():
                out.append(
                    {
                        "table": doc["table_id"],
                        "id": e["entry_id"],
                        "speaker": cur,
                        "body": body,
                        "scene": scene,
                    }
                )
    return out


def main():
    game = sys.argv[1] if len(sys.argv) > 1 else "ED1"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    lo = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    hi = int(sys.argv[4]) if len(sys.argv) > 4 else 10**9

    align = json.load(open(os.path.join(OUT_DIR, "align", f"{game}_SCN{n}.json"), encoding="utf-8"))
    # align_overrides로 이미 회수된 블록(빌드엔 번역됨)은 제외 — 진짜 미번역만 분류
    ov = json.load(open(os.path.join(ROOT, "align_overrides.json"), encoding="utf-8")).get(
        f"{game}SCN{n}", {}
    )
    ovk = {int(k) for k in ov if k.isdigit()}
    un = {i for i in align["jp_unmatched"] if lo <= i <= hi and i not in ovk}
    covered = sum(1 for i in align["jp_unmatched"] if lo <= i <= hi and i in ovk)
    jp_un = [b for b in load_jp_scene(game, n) if b["id"] in un and b["body"].strip()]
    kr = load_all_kr(game)
    print(
        f"{game}SCN{n} [{lo}~{hi}]: 미매칭 중 진짜 미번역 {len(un)} (본문有 {len(jp_un)}, "
        f"오버라이드 기회수 {covered} 제외), 전 {game} 정발 풀 {len(kr)}"
    )

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("sentence-transformers/LaBSE")
    je = model.encode([b["body"] for b in jp_un], normalize_embeddings=True)
    ke = model.encode([b["body"] for b in kr], normalize_embeddings=True)
    sim = je @ ke.T

    # 같은 씬 후보만 True인 마스크(신뢰도 높음). cross-scene은 정발 씬규칙 오귀속·범용대사
    # 오매칭 위험이 커, 더 높은 문턱(XSCENE_SIM)을 넘겨야 회수로 인정한다.
    XSCENE_SIM = 0.62
    same = [kr[j]["scene"] == n for j in range(len(kr))]
    rec, mid, new = [], [], []
    for i, b in enumerate(jp_un):
        row_sim = sim[i]
        ks = max(range(len(kr)), key=lambda j: row_sim[j] if same[j] else -1)
        ss = float(row_sim[ks]) if any(same) else -1
        kg = int(row_sim.argmax())
        sg = float(row_sim[kg])
        # 채택 점수: same-scene 우선, cross-scene은 XSCENE_SIM 넘을 때만 승격
        if sg >= XSCENE_SIM and sg > ss and kr[kg]["scene"] != n:
            s, kk, xscn = sg, kg, True
        else:
            s, kk, xscn = ss, ks, False
        row = (b, s, kr[kk], xscn)
        (rec if s >= HI_SIM else mid if s >= MID_SIM else new).append(row)

    xs = sum(1 for r in rec + mid if r[3])
    print(
        f"  회수가능(≥{HI_SIM}): {len(rec)}  경계({MID_SIM}~{HI_SIM}): {len(mid)}  "
        f"신규(<{MID_SIM}): {len(new)}  [그중 cross-scene 회수: {xs}]"
    )

    os.makedirs(REVIEW_DIR, exist_ok=True)
    outp = os.path.join(REVIEW_DIR, f"unmatched_{game}SCN{n}_{lo}-{hi}.md")
    with open(outp, "w", encoding="utf-8") as f:
        for title, rows in [("회수가능", rec), ("경계(확인 필요)", mid), ("신규 번역 필요", new)]:
            f.write(f"\n## {title} ({len(rows)})\n\n")
            for b, s, kb, xscn in sorted(rows, key=lambda r: -r[1]):
                jt = b["body"].replace("\n", " ")[:60]
                f.write(f"- jp{b['id']} ({s:.2f}) `{jt}`\n")
                if s >= MID_SIM:
                    tag = f" [씬{kb['scene']}]" if xscn else ""
                    kt = kb["body"].replace("\n", " ")[:50]
                    f.write(f"    → {kb['table']}#{kb['id']}{tag} `{kt}`\n")
    print(f"  → {outp}")


if __name__ == "__main__":
    main()
