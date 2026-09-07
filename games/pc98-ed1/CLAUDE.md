# CLAUDE.md — PC-98 『드래곤 슬레이어 영웅전설』 (pc98-ed1)

**트랙: [kr]** — 일본 원판 한글 번역 패치. 공용 규칙은 루트 [`CLAUDE.md`](../../CLAUDE.md),
진행 현황은 [`docs/status.md`](docs/status.md), 선행 사례는 [`docs/prior-art.md`](docs/prior-art.md).

## 이 게임이 다른 점

- 🔴 **글꼴이 디스크에 없다 — 본체 CGROM 이다.** 그래서 폰트 작업이 「변환」이 아니라
  **「기계어 + 메모리 배치」**다. 표는 **RAM 세그먼트 0x4000**(캐시 페이지 풀)에 올린다. 새턴·PS1 의 「폰트 파일에 한글 부어 넣기」가
  성립하지 않는다. 대신 이 게임은 CG 윈도우로 **도트를 읽어 자기가 그리므로** 그 루틴을
  후킹한다(`docs/status.md` 2절, 측정은 `tools/probe_font.py`).
  ⇒ **폰트 작업의 무게중심이 「변환」이 아니라 「기계어」에 있다.**
- **파일 시스템이 없다.** FAT 도 디렉터리도 없고 로더가 섹터 번호로 직접 읽는다 ⇒
  파일 교체가 아니라 **섹터 패치**다. 「그 파일만 갈아 끼우면 된다」가 안 통한다.
- **제어코드가 만트라 DOS 정발과 같은 집안**이다(`1E 화자 04` / `01` / `00`).
  만트라가 이 판을 이식했다 — `ps1-ed1+2/tools/extract_dos_kr.py` 의 문법 지식이 붙는다.
  ⚠ **문법이지 문안이 아니다.** 번역은 JP 원문에서 직접 한다(루트 ROADMAP).
- **같은 게임의 완성된 영문 패치가 있다**(Unlicense). 🔴 **문안은 안 본다** — 구조 지식과
  하네스 설계만 가져온다. 이유와 갈리는 자리는 `docs/prior-art.md`.

## 원본

`originals/jp/pc98-ed1/` — d88 3장(Event · Program · Scenario), 2HD 1232KB.
지문·경로 정본은 [`tools/common.py`](tools/common.py). ⚠ **읽기 전용**이고, 쓰기 헬퍼는
재삽입 설계가 서기 전까지 두지 않는다(`docs/patcher-checklist.md` 2).
⚠ **시나리오 디스크는 게임이 세이브를 쓰는 매체다** — 지문이 갈릴 수 있다.

## 도구

```bash
python3 games/pc98-ed1/tools/common.py       # 원본 셋 지문 + d88 → **논리 순서** 평면 이미지
python3 games/pc98-ed1/tools/probe_font.py   # 폰트 소재 판정(CG 루틴 9곳)을 다시 낸다
python3 games/pc98-ed1/tools/scn.py          # 시나리오·전투 디렉터리
python3 games/pc98-ed1/tools/dump_scn.py     # 대본 덤프 (+ 라운드트립)
python3 games/pc98-ed1/tools/dump_sys.py     # Event·Program 문자열 덤프
python3 games/pc98-ed1/tools/tables.py       # 고정 stride 이름 표 후보
python3 games/pc98-ed1/tools/walk_scn.py     # 재삽입이 성립하나 — 도달률 세 층
python3 games/pc98-ed1/tools/free_map.py     # 빈 섹터 지도 (디스크 쪽 자리)
python3 games/pc98-ed1/tools/memmap.py       # 메모리 지도 (폰트 올릴 RAM 자리)
python3 games/pc98-ed1/tools/reuse.py --dict … # 이미 번역한 문안이 얼마나 붙나
python3 games/pc98-ed1/tools/census_sjis.py  # 쓰이는 SJIS 코드 → 한글 앉힐 빈 자리
python3 games/pc98-ed1/tools/font.py --check --preview   # 한글 글리프 표 (16×16, 32B)
sh games/pc98-ed1/check.sh                   # ⭐ 이 게임의 커밋 전 게이트
```

⚠ **덤프는 `work/derived/` 로 나가고 커밋하지 않는다** — 원문이다(루트 「저작권」).

## 좌표 규약 — **평면 이미지 기준이다**

오프셋을 적을 때는 `common.read_d88()` 이 낸 **평면 이미지**(섹터 이어 붙인 1,261,568B)
기준으로 적는다. d88 파일 오프셋도, 영문 패치가 쓰는 NFD 오프셋도 아니다.
⚠ 세 좌표계가 섞이면 **조용히 엉뚱한 자리를 고친다** — 어느 계인지 안 적힌 상수는 못 믿는다.
