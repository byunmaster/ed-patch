# CLAUDE.md — 메가드라이브 『ドラゴンスレイヤー 英雄伝説II』 (md-ed2)

**트랙: [kr]** — 일본 원판(G-5544, Sega 1994) 한글 번역 패치. 공용 규칙은 루트
[`CLAUDE.md`](../../CLAUDE.md), 진행 현황은 [`docs/status.md`](docs/status.md), 경위는
[`docs/devlog.md`](docs/devlog.md). **먼저 [`../md-ed1/CLAUDE.md`](../md-ed1/CLAUDE.md) ·
[`status.md`](../md-ed1/docs/status.md) · [`devlog.md`](../md-ed1/docs/devlog.md) 를 읽는다** — 같은 엔진이고
ED1 이 겪은 함정이 거기 있다.

## 문안 방침

**대사 번역(P4)은 진행 중이다 — 완료 판정은 마스터 확인 대기**(옛 문구 「다음 라운드」는 낡았다, `docs/status.md` 「P4 진행」이 정본).
저본은 정본(`shared/canon`) → PS1 ED2 에서 원문이 같은 문장 → 나머지는 비슷하게 직접 번역(원문과 다르면 원문 — md-ed1 과 같은 규칙).
정본 `script/<블록>-<모듈>.json` 289개(항목 5,945 · `ours` 채움 4,211 — 10-18 실측), 제품 롬 바이트로는 텍스트 스트림 5,213 중 한글만 3,937 · 일본어만 1,001(대부분 코드 바이트 오탐).

## ED1 과 다른 점 (2026-10-12 첫 조사)

- 원본은 **`.zip` 안의 plain BIN** 2MB (ED1 은 압축 없는 `.bin`). `tools/common.py` 의 `rom()` 이 zip 에서 읽는다.
- 🔴 **꼬리 빈 공간이 없다** — 마지막 LZ 블록이 0x1FF71E 에서 끝나고 FF 는 2,270B 뿐이다(ED1 은 81KB).
  4MB 확장은 SRAM(0x200001~) 겹침으로 불가. 우리 LZ 인코더는 원본 압축보다 약해서 **대본을 안 바꾸고
  다시 눌러도 +8.7KB** 다 → 재삽입 설계 전에 인코더 개선(최적 파싱)이나 공간 확보가 필요하다.
- 🔴 **대본 블록 하나 = 씬 모듈 넷**이다. 분할 표 `0x19DC3C`(블록당 BE16×4). 씬 모듈은 356개, 최대 8,720B.
- 엔진 코드는 ED1 과 같은 것이 **다른 주소**에 있다(LZ 디컴프레서 0xE04 ← 0xC9E, 렌더러 0xB738 ← 0x978C,
  ARGS 표 0xBF9A ← 0x9FE2, 씬 로더 0x1A41C~). ED1 의 후킹 주소를 그대로 옮기지 않는다.
- **글꼴은 ED1 과 바이트까지 같다**(색인 0xF41C2 ← 0x1A54D2, 리소스 6개 앞 0x17190 바이트 비교 일치).

## 도구

```bash
python3 games/md-ed2/tools/common.py     # 원본 지문 + 헤더 체크섬 + 꼬리
python3 games/md-ed2/tools/archives.py   # 아카이브 분모 · 대본 씬 모듈 356
python3 games/md-ed2/tools/scene.py      # 스트림 3,468 · 화자 태그 도달 · 항등 재조립
sh games/md-ed2/check.sh                 # ⭐ 커밋 전 게이트
```
