"""
의미 기반 정렬기 — **되살린 도구다**(2026-08-14).

도구 정리(83 → 55) 때 지웠는데, ED1 배정 정본을 만든 게 이것이라 ED2 를 열자 다시 필요해졌다.
구조 정렬기(`align_jp_kr`)의 제안을 사람이 검증한 ED2SCN1 104건과 대조하니 **정확도 14%**
였고(일치 15 · 다름 67 · 제안 없음 22), 그 수치만 보고 「배정을 버린다」고 판단할 뻔했다.
⚠ **도구를 지울 때 「무엇을 만들던 도구였는지」가 같이 지워진다.**

의존물은 리포에 없다 — `pip install torch sentence-transformers scipy`(데비안·CPU 로 된다).
⚠ 이 도구의 출력은 **제안**이다. 받아들인 결과는 `align_map.json`(커밋되는 정본)에 박고
빌드는 정본만 읽는다 — LaBSE 동점이 머신마다 갈려 빌드가 달라진 적이 있다(레포 제1원칙).

 — 다국어 임베딩(LaBSE)으로 PS1 일문 ↔ DOS 한국어를 번역쌍 매칭.

구조 신호(화자·길이·순서)만 보는 align_jp_kr.py는 같은 화자의 변형 대사를 swap한다
(시녀 '깨우기'↔'저녁식사', 둘 다 score>4). 여기서는 문장 '의미'를 임베딩해 코사인
유사도로 매칭 — "이 일본어의 번역인 한국어"를 직접 찾으므로 swap이 사라진다.
LaBSE는 번역쌍 찾기(bitext mining) 전용 다국어 모델.

전략:
 1. 씬 대응·화자 매핑은 align_jp_kr.py 재사용 (같은 씬의 KR 후보로 제약)
 2. JP·KR 본문을 LaBSE로 임베딩 → 코사인 유사도 행렬
 3. 화자 일치 소폭 보너스(같은 화자 변형끼리는 의미로 갈림)
 4. Hungarian(scipy)로 KR 기준 최적 1:1 배정 (PS1이 더 많아 JP 다수는 미매칭)
 5. 임계 미만·저유사도는 flags — align_jp_kr와 동일 스키마

의존성(레포 비포함): pip install --user sentence-transformers
출력: out/align/<게임>_SCN<n>.json (재삽입기·past_review_align이 그대로 소비)
"""

import json
import os
import sys

from align_jp_kr import GAMES, build_speaker_map, load_jp_scene, load_kr_scene
from common import OUT_DIR

ALIGN_DIR = os.path.join(OUT_DIR, "align")
MODEL_NAME = "sentence-transformers/LaBSE"
ACCEPT = 0.45  # 코사인 하한 (LaBSE 번역쌍은 보통 0.6+, 오정렬은 낮음)
CONFIDENT = 0.60  # 이상이면 고신뢰, 미만은 low_sim flag
SPK_BONUS, SPK_PENALTY = 0.08, 0.04  # 화자 일치/불일치 가산 (의미가 주, 화자는 보조)


def get_model(device=None):
    """LaBSE 로더 — 임베딩을 쓰는 도구는 전부 이걸 거친다.

    ⚠ device 기본값이 cpu인 이유: 지정 안 하면 torch가 MPS를 자동선택하는데, Intel Mac +
    소용량 dGPU에서는 VRAM 상한(~3.4GB)이 LaBSE 배치에 모자라 `MPS backend out of memory`로
    죽는다. 여유 있는 머신은 `EMB_DEVICE=mps`(또는 cuda)로 올려 쓴다.
    """
    from sentence_transformers import SentenceTransformer

    device = device or os.environ.get("EMB_DEVICE", "cpu")
    print(f"모델 로드: {MODEL_NAME} (device={device}, 최초 1회 다운로드)")
    return SentenceTransformer(MODEL_NAME, device=device)


def align_scene(model, game, n, spk_map):
    jp_blocks = load_jp_scene(game, n)
    kr_tables = load_kr_scene(game, n)
    kr_blocks = [dict(b, table=t) for t, bs in kr_tables.items() for b in bs]
    if not jp_blocks or not kr_blocks:
        return None

    je = model.encode([b["body"] for b in jp_blocks], normalize_embeddings=True)
    ke = model.encode([b["body"] for b in kr_blocks], normalize_embeddings=True)
    sim = je @ ke.T  # (nJP, nKR) 코사인

    # 화자 일치 보너스 (의미가 주, 화자는 tie-break 보조)
    for i, jb in enumerate(jp_blocks):
        mj = spk_map.get(jb["speaker"]) if jb["speaker"] else None
        if not mj:
            continue
        for k, kb in enumerate(kr_blocks):
            if kb["speaker"]:
                sim[i, k] += SPK_BONUS if mj == kb["speaker"] else -SPK_PENALTY

    # KR 기준 최적 1:1 배정 (Hungarian, 유사도 최대화). PS1이 더 많아 JP 다수 미매칭.
    from scipy.optimize import linear_sum_assignment

    ki, ji = linear_sum_assignment(-sim.T)  # 행=KR, 열=JP
    pairs, matched_jp = [], set()
    for k, i in zip(ki, ji, strict=True):
        s = float(sim[i, k])
        if s < ACCEPT:
            continue  # 이 KR 블록은 씬 안에 대응 JP가 없음(리메이크 삭제분 등)
        jb, kb = jp_blocks[i], kr_blocks[k]
        matched_jp.add(jb["id"])
        pairs.append(
            {
                "jp": {"entry_id": jb["id"], "speaker": jb["speaker"]},
                "kr": {"table": kb["table"], "entry_id": kb["id"], "speaker": kb["speaker"]},
                "score": round(s, 3),
                "flags": [] if s >= CONFIDENT else ["low_sim"],
            }
        )
    matched_kr = {(p["kr"]["table"], p["kr"]["entry_id"]) for p in pairs}
    for kb in kr_blocks:
        if (kb["table"], kb["id"]) not in matched_kr:
            pairs.append(
                {
                    "jp": None,
                    "kr": {"table": kb["table"], "entry_id": kb["id"], "speaker": kb["speaker"]},
                    "score": 0,
                    "flags": ["unmatched_kr"],
                }
            )
    return {
        "scene": f"{game}SCN{n}",
        "method": "semantic-labse",
        "jp_blocks": len(jp_blocks),
        "kr_blocks": len(kr_blocks),
        "kr_tables": sorted(kr_tables),
        "matched": len(matched_jp),
        "pairs": pairs,
        "jp_unmatched": [b["id"] for b in jp_blocks if b["id"] not in matched_jp],
    }


def main():
    """`python3 tools/past_align_semantic.py [ED2 …]` — 인자로 **게임을 제한**한다.

    ⚠ 인자를 안 주면 전 게임을 다시 만든다. ED1 은 배정 정본(`align_map.json`)이 커밋돼
    있어 빌드가 여기를 안 읽지만, 그래도 **한 트랙 작업이 다른 트랙 파생물을 갈아엎는 일은
    막는다** — 2026-08-03 에 그렇게 하루를 태웠다(같은 화자의 변형 대사가 swap 됐다).
    """
    only = {a for a in sys.argv[1:] if not a.startswith("-")}
    os.makedirs(ALIGN_DIR, exist_ok=True)
    model = get_model()
    for game, (_, n_scn) in GAMES.items():
        if only and game not in only:
            continue
        if not os.path.isdir(os.path.join(OUT_DIR, "dos_kr", game)):
            continue
        # 화자 인벤토리 (게임 전체) → 매핑표 (align_jp_kr 로직 재사용)
        jp_spk, kr_spk = set(), set()
        for n in range(1, n_scn + 1):
            jp_spk |= {b["speaker"] for b in load_jp_scene(game, n) if b["speaker"]}
            for blocks in load_kr_scene(game, n).values():
                kr_spk |= {b["speaker"] for b in blocks if b["speaker"]}
        spk_map, _ = build_speaker_map(jp_spk, kr_spk)

        for n in range(1, n_scn + 1):
            doc = align_scene(model, game, n, spk_map)
            if doc is None:
                continue
            # 생성자 표시 — align_jp_kr(구조 신호 초안)가 이 정본을 덮어쓰지 못하게 하는 표식.
            # 2026-08-03: 다른 머신에서 work/derived 를 복구하며 align_jp_kr 를 인자 없이 돌려
            # 의미정렬을 통째로 날렸고, 같은 화자의 변형 대사가 swap 돼 하루를 태웠다.
            doc["generator"] = "past_align_semantic"
            with open(os.path.join(ALIGN_DIR, f"{game}_SCN{n}.json"), "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, indent=1)
            low = sum(1 for p in doc["pairs"] if "low_sim" in p["flags"])
            pct = 100 * doc["matched"] // max(doc["kr_blocks"], 1)
            print(
                f"  {game}SCN{n}: JP {doc['jp_blocks']} / KR {doc['kr_blocks']} "
                f"→ 매칭 {doc['matched']} (KR 대비 {pct}%, low_sim {low})"
            )


if __name__ == "__main__":
    main()
