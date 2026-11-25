# games/ps1-ed4 — [kr] PS1 영웅전설 IV 『朱紅い雫』 한글패치

트랙 **kr** (일본 원판 한글 번역). 루트 규칙은 `../../CLAUDE.md`, 이 파일엔 이 게임 것만 둔다. 원본 `originals/jp/ps1-ed4` (SLPS-01540).

**0.1.0 선공개 라운드**: 대본 번역은 끝났고(24,474/24,499 조각) 검수·말투·조판을 다듬는 중이며, 출시 전 마스터 확인을 받는다. 현황·남은 일은 `docs/status.md`, 겪은 일은 `docs/devlog.md`.

- **ED3 와 같은 GMF 엔진**이지만 **이 폴더가 독립 코드베이스**다 — 공용(`shared/disc` · `shared/ps1`: MODE2 섹터 쓰기·GMF 아카이브·TIZ·TIM) 위에 얇게 선다. ps1-ed3 의 도구는 읽기만 하고 import 하지 않는다
  (ED3 쪽 ED4 몫 — `charmap_ed4` · `hangul_map_ed4` · `script/ed4` · `DISCS["ed4"]` — 은 ED3 전환 때 지운다. 지식이 두 곳에 있는 동안은 이 폴더의 `charmap.json`·`hangul_map.json` 이 ED4 정본이다).
- ⚠ **ED3 규약으로 ED4 를 읽지 않는다**: 대본이 든 멤버는 표 규격 356(풀 규격 125 는 문자열 없는 이벤트 자료)이고, 폰트는 열 교환 없음·몸통 1~11행, 카나 탈락 집합이 다르고(`textenc.DROPPED`), 그림은 ED3 의 gmfz(RLE)가 아니라 **TIZ**(`shared.ps1.tiz`)다.
- 커밋 전: `sh scripts/check.sh` → 이 폴더의 `check.sh`(무변경 왕복 = 원본과 바이트 같음 · 결정성 · 쓰기 가드 · 재삽입 시험 · 화면 일본어 기준선).
- 시험 빌드(`probe.py` 등)는 꼬리표 `ED_BUILD_TAG=test-<무엇>` 로 굽고 쓰고 나면 지운다(마스터 목록에 안 나온다).
- 원본 문안을 문서·주석·테스트에 옮기지 않는다(저작권) — 시험 문안은 글리프 자리 정본 글자로 지은 무의미한 열이다.
