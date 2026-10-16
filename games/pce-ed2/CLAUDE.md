# CLAUDE.md — PC엔진 CD-ROM² 『드래곤 슬레이어 영웅전설 II』 (pce-ed2)

**트랙: [kr]** — 일본 원판(HCD2033, Hudson) 한글 번역 패치. 공용 규칙은 루트 [`CLAUDE.md`](../../CLAUDE.md), 진행 현황은
[`docs/status.md`](docs/status.md). **자매 게임 [`games/pce-ed1/`](../pce-ed1/CLAUDE.md) 이 같은 플랫폼의 선행 작업이다** —
BIOS 글꼴 후킹 · 컨테이너 · 음성 자막 기전 · 조판 · 게이트를 먼저 읽는다(거기 함정이 다 적혀 있다).
🔴 대사 문안을 쓰거나 검수하기 전에 스킬 `rpg-translate` 와 루트 `docs/translation-rules.md` 를 연다(정책 문서는 번역 라운드에서 만든다).

## 이 게임이 ED1 과 다른 점 (2026-10-12 조사)

- **Super CD-ROM²** — 시스템 카드 3.00(「SUPER CD-ROM² SYSTEM VER. 3.00」 화면). 데이터 트랙 **49,154섹터(~100MB)**, 오디오 22트랙(ED1 은 데이터 10,072섹터 + 복제 트랙 1).
- **IPL 이 다르다** — rel 2 ×3섹터 → `$3000`, 실행 `$3A00`(ED1 은 rel 2 ×20 → `$4000`). 그 뒤 rel 4098 ×32섹터가 뱅크 0x68 로 올라온다.
- 🔴 **데이터 트랙 안에 거울이 있다** — rel 2~12,285 가 rel +36,864 에 한 벌 더(rel 0·1 만 다름). 게임이 어느 쪽을 읽는지 미확정 → 패치는 둘 다 고칠 각오.
- 컨테이너 구조는 **ED1 과 다르다**(ED1 `containers.scan` 이 앞 16,384섹터에서 0건) — 새로 조사한다.

## 원본 · 좌표

`originals/jp/pce-ed2/` — redump `.cue`+`.iso`(2352B raw, 24트랙, 297,978섹터). 지문·상수 정본은 [`tools/common.py`](tools/common.py).
⚠ 읽기 전용. **좌표는 ED1 과 같은 「데이터 트랙 상대 섹터(rel)」**(트랙 2 시작 = 파일 섹터 3,371 = rel 0) — 규약은 [`../pce-ed1/CLAUDE.md`](../pce-ed1/CLAUDE.md) 「좌표 규약」.
에뮬 실행용은 `work/emu/ed2.cue` + `ED2_T12.ISO`(트랙 1~2 만 잘라 낸 123MB 사본 — emucap 이 절대경로·심볼릭 cue 를 거부하고 /mnt 는 다른 파일시스템이라 하드링크도 안 된다). **쓰고 지운다**(디스크 여유 부족).

```bash
python3 games/pce-ed2/tools/common.py   # 원본 지문 + IPL + 거울 확인
sh games/pce-ed2/check.sh               # 이 게임의 커밋 전 게이트(지금은 입력 지문까지)
```
