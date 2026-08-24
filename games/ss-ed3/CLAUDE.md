# CLAUDE.md — 새턴 『백의 마녀 — 또 하나의 영웅전설』 (ss-ed3)

**트랙: [kr]** — 일본 원판 한글 번역 패치. 공용 규칙은 루트 [`CLAUDE.md`](../../CLAUDE.md),
진행 현황은 [`docs/status.md`](docs/status.md).

## 이 게임이 다른 점

- **디스크가 둘인데 게임 데이터는 한 벌이다.** 공통 811 파일이 전부 바이트 동일이고,
  갈리는 건 무비(`/CPK`)·음성(`/SAP`)·음악(`/SND/MUS`)·엔딩 그림(`/END*`)뿐이다.
  → **문안·재삽입은 한 벌만 만들고 두 장에 같이 쓴다.** `common.check_discs()` 가 매번 본다.
- **허드슨 이식이라 `ss-ed1+2`(GMF) 의 도구가 안 붙는다.** 물려받는 건 플랫폼 층
  (`shared/disc` · MODE1/2352 · SH-2)과 `shared/` 뿐이고, 컨테이너·스크립트·폰트는 별개다.
- **ED1+2 의 번역 저본이 한 줄도 안 붙는다.** 다른 작품이라 `line_dict.json` 이 안 통한다 —
  44만 자를 새로 번역한다. 그래서 **판정이 안 드는 구간(구조·폰트·시스템)을 먼저** 판다.
- **정발에서 가져오는 건 「표기」뿐이다** (유저 확정 2026-08-24). 문안은 자체 번역이라
  **대사 저본이 아예 필요 없다** — 정발과 대조할 일도 없다. 필요한 건 루트 「기본 방침」의
  ⚠ 한 줄뿐이다: **고유명사·용어 표기는 정발을 유지한다**(향수가 방침이고 원음 환원은
  교정이 아니다). 그러니 정발에서 뽑을 것은 **인명·지명·아이템·몬스터·용어의 표기 목록**
  이고, 그건 단어 수준이라 저작권 대상이 아니다(루트 「저작권」이 명시한다).
  - 저본은 **만트라 DOS 정발**(`originals/kr/dos-ed3`, `ED3_DT*.DAT` 평문)로 확정.
    윈도우 정발(`kr/win-ed3`)은 안 본다.
  - 자리는 `shared/glossary/` — ED1+2 가 쓰는 그 정본에 ED3 열을 더한다.

## 원본

`originals/jp/ss-ed3/` — MODE1/2352, 2 디스크. 지문·경로 정본은
[`tools/common.py`](tools/common.py). ⚠ **읽기 전용**이고, 쓰기 헬퍼는 재삽입 설계가
서기 전까지 두지 않는다(`docs/patcher-checklist.md` 2).

## 도구

```bash
python3 games/ss-ed3/tools/common.py            # 원본 지문 + 2디스크 계약
python3 games/ss-ed3/tools/dump_map.py          # MAP*.BIN 88개 덤프 (+ 라운드트립)
python3 games/ss-ed3/tools/dump_sys.py          # 본체·시스템 문자열 덤프
python3 games/ss-ed3/tools/font.py              # 폰트 기하 · 한글 슬롯 여유
python3 games/ss-ed3/tools/typeset.py           # 조판 계약을 그 자리에서 다시 잰다
python3 games/ss-ed3/tools/hangul_map.py        # 한글 배정 (--freeze 로만 갱신)
python3 games/ss-ed3/tools/build_font.py        # KANJI12.FON 에 한글 굽기
python3 games/ss-ed3/tools/reinsert.py --check  # 문안이 길이 보존으로 들어가나
python3 games/ss-ed3/tools/build.py             # ⭐ 테스트 이미지 (1.9초)
sh games/ss-ed3/check.sh                        # 이 게임의 커밋 전 게이트
```

🔴 **`hangul_map.json` 은 파생물이 아니라 정본이다.** 소재를 더 열면 빈 슬롯이 밀려
**이미 넣은 문안이 전부 다른 글자로 읽힌다.** `--freeze` 로만 갱신하고 그때 다시 굽는다.

⚠ **`work/derived/` 는 커밋하지 않는다** — 원문이 들어 있다(루트 「저작권」).
