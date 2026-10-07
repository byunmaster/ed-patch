# ED1·ED2 진행 현황 (PS1 영웅전설 1+2)

**이 문서 하나만 읽으면 이어서 작업할 수 있게 쓴다.** 누가(어떤 세션·어떤 도구가) 오든
"지금 어디까지 됐고 · 다음에 뭘 하고 · 어떻게 시작하는지"를 여기서 얻는다.
ED1·ED2 는 한 이미지라 현재 상태는 **이 문서 한 곳**에 모았다(ED2 쪽 [ed2-status.md](ed2-status.md)
는 편 고유의 열린 항목과 지난 라운드 기록).

- **방침·규칙**은 여기 쓰지 않는다 → [policy.md](policy.md)
- **완료된 작업의 경위**도 여기 쓰지 않는다 → 커밋 히스토리 · [devlog.md](devlog.md) ·
  [reference/our-findings.md](../../../docs/reference/our-findings.md)
- 여기엔 **현재 상태 + 남은 일만** 둔다. 다 하면 지운다.

마지막 갱신: 2026-10-07 (**v1.0.0 배포 완료 · 라운드 졸업 · 핫픽스·제보 이슈 때만 움직인다**).

## 📦 상태 — v1.0.0 이 배포됐다

**`game/ps1-ed1+2` 는 main 에 머지됐고 v1.0.0 은 10-07 에 공개됐다.** 이 게임은 라운드에서 졸업했다 —
이제 **핫픽스·제보 이슈**가 들어올 때만 고친다. **배포는 이슈를 모아 한 번에** 한다(마스터 지시 10-07,
지금 릴리스 파일을 새로 만들지 않는다). 푸시·릴리스는 마스터 몫이고 게임 브랜치는 원격에 안 올린다.

| 항목 | 값 |
| --- | --- |
| 배포판 v1.0.0 이미지 sha1 | `aa240a91ce9c04567cc7a1d83ecc0d302ac5c55d` (252,498,960 B) |
| 원본(JP BIN) sha1 | `269032ba730f4dbe80b798a2c4c3b415e094f359` |
| 배포 차분(v1.0.0) | `work/dist/ps1-ed1+2-kr-v1.0.0.xdelta` · `.bps` · `manifest.md` — **v1.0.0 것이다.** 핫픽스 뒤에 새로 만들지 않았다 |
| 핫픽스 반영 이미지 sha1 | `d88c75bad2bff3155b9831beaa205bc19b651c6f` (10-07, `work/build/ps1-ed1-2`) — 아래 「핫픽스 대기」가 들어 있다 |
| 게이트 | `sh scripts/check.sh` — ✅ (브랜치 범위의 「정본 사전」은 사전 커밋이 main 에 들어가면 사라진다) |

다시 만들기: `python3 tools/build.py` → `python3 tools/make_dist.py <버전>` (xdelta3 필요: `apt-get install xdelta3`).
`work/dist/` 는 gitignore 라 머신을 안 따라간다.

### 핫픽스 대기 — 다음 배포(v1.0.1)에 같이 나간다

v1.0.0 뒤에 고친 것(전부 로컬 커밋, main 에는 마스터 확인 뒤). 이미지 sha1 은 `git log` 끝 커밋 기준으로 `work/build/ps1-ed1-2` 에서 잰다.

- **옛 몬스터 이름 22곳**(`battle.json`·`items_battle.json`) + **마스터 판정 다섯**(炎の剣=불의 검 · ガイド=가이드(본문 포함) · バルアズス島=바라즈스섬 · 「민첩성」 · 盗賊=**도둑**: 화자 77 · SPEAKER_DICT · 화자맵 덮어쓰기까지).
- **세이브**(セーブ=「세이브」, 시스템 문구 6곳) · 판정표 「사전대로」(나이프·루디아 마을·부하·약) · 이름 검사 예외 승인(마스터 판정표 D5).
- **지명**: 대사 속 「~ 항구」 띄어쓰기 50곳(ED1 42·ED2 8) · 그로스토스성·바라즈스섬·보아드해운 붙임 · `PLACES` 狼の口 를 정본 「늑대의입」으로(빌드 전용 짧은 꼴 `BUILD_SHORT`) · 지명 칸은 원문 꼴 그대로(리셸 `SLOT_OVERRIDE` 걷음).
- **ED2SCN4:519·558 「란도」** — 이름이 방출 바이트에서 빠져 있던 것(원문은 이름이 본문 안 색칠 글자인 고정 문장)을 원문대로 복원.
- 도구: 이름 검사 어댑터 `tools/names_corpus.py` · 게임 게이트가 실패한 검사의 꼬리를 찍음 · `check_name_echo` 보정.

### 열린 이슈

기계로 닫을 수 있는 축은 다 닫혔다(화면 일본어 0 · 구조 계약 · 되읽기 · 결정성). 남은 건 **정적으로 못 가리는 위험**이다:

1. **ED1 엔진 스텁(`stub_eager_nl`)은 ED1 에서 에뮬 검증을 못 했다** — ED2 전투에서 29열 꽉 찬 줄 뒤 빈 줄이 사라지는 것만 확인했다.
   ED1 일반 대사를 길게 걸어 보는 확인이 남았다.
2. **위치를 읽는 스크립트** — `FIXED_RUNS` 로 묶지 않은 구간 중 블록 위치에 반응하는 것은 정적으로 못 찾는다(크루즈 아침 자동이동 류).
3. **ED1SCN2 석비 프리징(과거)** — 근원이 확정되지 않았다. 석비 문안은 화면에 정상으로 나온다(10-05 마스터 확인).
   핀(`FIXED_RUNS["ED1SCN2"]` 866·898·919)은 비용이 0 이라 걸어 둔 채다 — 급하면 빼도 된다.
   ⚠ 증상 모양(소프트락/완전 정지)으로 이 부류를 배제하지 않는다 — [our-findings.md](../../../docs/reference/our-findings.md) 「소프트락 디버깅」 0번.
4. **빌타라는 나무인간과 같은 그림·능력치로 나온다** — 원판 화면 대조를 못 했다(원판 편성 코드가 같은 값을 넣는 것으로 보인다).
5. **이름 검사**(공용 `scripts/check/check_names.py` + 어댑터 `tools/names_corpus.py`): 표 5개는 테스트가, 문장 속 이름은 이 검사가 사전과 대조한다(어긋남 0 · 승인 예외 `names_exceptions.json`).
   ⚠ **안 보는 구간**: 오프닝·엔딩 내레이션(`textmap/opening*`·`ending*` — 원문이 해시 키) · ED2MON 몬스터 대사 · 그림 글자(HUD 이름표) · EXE 시스템 문자열 일부.
6. **ED2 4장 라누라 술집(리더=란도) 실화면 확인** — 안 했다(바이트만 확인). 라누라(ED2SCN4 용의 축제) 술집 바텐더에게 말을 걸어 마시면 **「란도의 ＨＰ가 N 회복되었다」**(이름이 색칠된 첫 조각)가 떠야 한다. ⚠ **리더가 란도일 때만** 나오는 고정 문장이다(마스터).
7. **다음 라운드 후보**(상세는 [ed2-status.md](ed2-status.md)): 줄 끝에서 이름이 갈리는 것(「보아드⏎해운」) ·
   블록 가운데 「키 대기 뒤 새 줄」(`%c\n`) 빌더 보강 · 몬스터 대사 표 재배치 경로(`_apply_sha_table`) · 폭 게이트를 조립 경로 안에 심기 ·
   `check_log_register` 를 **EXE 문자열**까지 넓히기(ED1 `の中には` 1곳이 부류 규칙 밖에 있다 — ED1 전용) ·
   RE 셋(034 몬스터창 상태이상 라벨 · 038 제니 조형 · 042 전투 각성 메시지 조사 훅).
8. 마스터가 훑어볼 만한 곳: 6줄 창, ED2 보물상자. **2회차 인게임 QA 는 하지 않는다**(마스터 10-05 「시간상 힘들다」) —
   대신 정적 전수 점검으로 닫았다(`devlog.md` 10-05).

### 다시 시작하는 법

- 🔴 **첫 명령은 빌드다** — 아래 「시작하기」.
- **세이브**: `/root/save/ps1-ed1+2/` (카드1 = `.0.mcr`, 카드2 = `.1.mcr`). 이미지 해시 이름
  (`Eiyuu Densetsu (KR).<해시>.{0,1}.mcr`)으로 emucap `sav` 폴더에 복사한다 — 빌드를 갈면 이름이 바뀐다.
  과거 QA 재현용 카드와 설명은 `.local/work/inbox/ps1-ed1+2/세이브-설명.txt`(다시 만들 수 없는 자료다).
- **부팅 순서**(mednafen/emucap): 타이틀 → start(10프레임) → 편 고르기(좌 ED1 · 우 ED2) → circle → 이어하기 → 카드 → 슬롯 → circle 두 번.
  **세이브스테이트는 쓰지 않는다**(옛 코드가 되살아난다) — 카드 로드만. ED2 슬롯 3(「그로스토스성」)은 전투 직전이라 전투 문안을 보기 좋다.
- **문안을 고쳤으면**: `sh scripts/check.sh` → 확정 락 위반이면 **바뀐 블록 집합 안인지 확인한 뒤**
  `lock_lines.py --relock <씬> <eid…> --why …` (목록이 8건씩 잘려 나오니 반복) → 조판 지문이 떴으면 `--freeze` → 재빌드.
- **고유명사**: 사전(`shared/glossary` · `shared/lore`)은 **main 에서 마스터 확인 뒤에만** 고친다. 새 이름 표를 게임 폴더에 만들지 않는다.
  사전과 갈리면 후보를 관리자에게 올린다.

## 문안이 어디서 오는가 — **정본이 전부다**

화면에 나가는 블록은 하나도 빠짐없이 `script/` 의 `t` 에서 온다 — `align_map`·`align_overrides` 는 **문안을 안 나른다.**
다만 그 표를 지우면 안 된다: **구조 지시**(`inject_pairs`·`nl_after`·`fold_name`·`trail_nl`·`blank`)가 아직 거기 있다.

|      |                                                                                      |
| ---- | ------------------------------------------------------------------------------------ |
| 정본 | `script/ED1SCN*.json` — `{"1100": {"t": "…", "s": "병사"}}`. **커밋된다**(우리 문안) |
| 초안 | `work/review/draft_ED1SCN*.json` — 옮기기 전 화면 문안. **커밋 금지**(정발)          |
| 검증 | `script_draft.py --verify` — 초안을 그대로 넣었을 때 같은 바이트가 나오는가          |

문안은 **JP 원문에서 우리가 쓴다**(자체 번역 ED1·ED2 100% — `audit_provenance`). 전 씬에서 오역 100종 이상을 고쳤고 유형은
[mistranslation-patterns.md](../../../docs/reference/mistranslation-patterns.md) 에 모았다(게임 무관).

⚠ **판정 규율** — 문안을 쓸 때 **반드시 JP 원문과 뜻이 맞는지 본다.** 고친 자리는 `note` 에 원문 근거를 남긴다.
⚠ **원문이 같으면 문안도 같아야 한다**(역할군은 마을마다 다른 사람이라 예외) — `python3 tools/check_dup_jp.py [씬]` 은 판정용이다.
⚠ **화자는 원문 헤더가 정답이다** — `check_speakers`.
⚠ **저작권 축은 이력으로 가른다** — 유사도로는 못 가른다(`tools/audit_provenance.py`). 동일 = 베낌이 아니다(상투 문구는 수렴한다).

## 시작하기 — 첫 명령은 빌드다

```bash
cd games/ps1-ed1+2
python3 tools/build.py        # → work/build/<브랜치 꼬리표>/Eiyuu Densetsu (KR).bin/.cue
```

**통과하면 그대로 작업을 시작하면 된다.** 머신이 바뀌었든 파생물이 낡았든 상관없다.
**`work/` 는 통째로 지워도 된다** — `rm -rf work/` 후 재빌드가 **바이트 동일**이다(`check_determinism.py`).
원본 덤프(`extract_scn` · `extract_dos_kr`)는 `build.py` 가 매번 새로 뜬다. 정렬 파일(`work/derived/align`)이 없으면
빈 배정으로 진행한다(있으나 없으나 sha1 동일 — `test_align_file_is_optional_so_work_can_be_wiped`).

⚠ `align_jp_kr.py`(전체)·`past_align_semantic.py` 는 **제안 도구 전용**이다 — 돌리면 그 파일들이 생기지만 빌드는 안 읽는다.
빌드가 **확정 락 위반**으로 멈췄다면 문안이 바뀐 것이다 — 절차는 [policy.md](policy.md).

## 현재 수치 (`sh scripts/check.sh` 가 한 번에 낸다)

| 축 | 상태 |
| --- | --- |
| 번역 정본 | ED1 5,029 · ED2 7,060 블록 · 문안 출처 **자체 번역 100%**, 정발 잔재 0 |
| 화면 일본어 | **0곳** (`check_scn_jp_left` — 이미지에서 참조를 따라간다, `build.py` 에 물려 있다) · 전투 0 |
| 조판 | 고아·빈 줄 0 · 블록 경계 0 · 창 줄 수 초과 0 · 런타임 줄넘김 ①~④·⑦~⑨ 빌드 0건 |
| 물리 배치 | 파일 15 · LBA/크기 차이 0 · 겹침 0 · 쓴 자리 되읽기 어긋남 0 |
| 확정 락 | ED1 6씬(SCN1 942 · SCN2 984 · SCN3 1,048 · SCN4 731 · SCN5 935 · SCN6 301 — 09-08 실측). 지금 락의 값은 「확정」이 아니라 **파이프라인 회귀 탐지**다 |
| 번역 진행률 | 99.5% — 남은 21은 전부 이름·지명 플레이트(`patch_sys_ui` 관할)라 대사는 0. `status.py` 의 옛 「85%」는 분모가 표·제어 블록까지 세던 것 |
| 정적 QA | SOURCE · STATIC_BINARY · RC_BUILD · RC_READBACK 전부 PASS → [static-qa-report.md](static-qa-report.md) |
| 사전(`line_dict`) | 열쇠는 `shared/text/line_key` 하나가 정본이다 — 새턴이 이걸로 줄을 받아 간다 |

⚠ 진행률은 **도구가 정본**이다 — `python3 tools/status.py` · `--maps`.

## ⚠ emucap — 띄우는 경로에 심볼릭 링크를 두지 말 것

CUE **구성원 경로에 심볼릭 링크가 있으면 승인이 거부**된다. 메인 트리의 `games/<게임>/work/build` 는 워크트리로 가는 링크라
**메인 트리 경로로 띄우면 막힐 수 있다.** 워크트리 안 경로로 띄운다(`emu.sh` 가 그러니 평소엔 무방하다).
`get_rom_info` 는 런치 전에 CUE 와 구성원 전부의 SHA-256 을 세대에 묶어 보고한다(낡은 이미지를 정상으로 오해하는 사고를 조인다).
emucap 을 올린 세션엔 **Claude Code 재시작**이 필요하다. **PS1 을 띄울 수 있는지는 `launch_plan` 에 묻는다**(파일 시스템 추정으로
「환경이 없다」고 적었다가 정정한 적이 있다). 외부 의존물의 최신 여부는 여기 안 적는다 — `sh scripts/check-updates.sh` 가 정본이다.

## 인게임 QA 하는 법

⚠ **정발을 나란히 켜지 않는다.** 볼 것은 「이 문장이 원문의 뜻이고 읽기 좋은가」다.

```bash
python3 tools/script_dump.py ED1SCN1        # 대본(JP 원문 ↔ 우리 문안) → work/review/
python3 tools/check_tail_cut.py             # 창 수·줄 수 초과
python3 tools/check_line_breaks.py          # 줄 갈림
python3 tools/check_forbidden.py            # 마크업 유출·조사 병기 노출
python3 tools/spellcheck_render.py --report # 화면 문안 맞춤법
python3 tools/scn_callgraph.py              # 코드가 부르는 맵을 벗어난 배정(폴백 구간용)
python3 tools/check_scn_jp_left.py          # 일본어 잔존(ED1 은 0 이어야 한다)
```

## 문서 지도

| 찾는 것              | 어디                                                                          |
| -------------------- | ----------------------------------------------------------------------------- |
| 작업 규칙·트랙 구조  | 루트 [CLAUDE.md](../../../CLAUDE.md) · 게임 [CLAUDE.md](../CLAUDE.md)         |
| 방침·마스터 확정 결정 | [policy.md](policy.md)                                                        |
| UI 자리·정렬 잣대    | [ui-canon.md](ui-canon.md) — **이식판 공통**(메뉴·메시지·HUD·전투·오프닝·타이틀) |
| 대사 파이프라인 전모 | [text-pipeline.md](text-pipeline.md)                                          |
| 재사용 가능한 발견   | [our-findings.md](../../../docs/reference/our-findings.md)                    |
| 표기 편차 대장       | [jeongbal-deviations.md](jeongbal-deviations.md)                              |
| 트랙별 경위          | [devlog.md](devlog.md) (오프닝 폰트 · 조사 훅 · NPC 바인딩 · 타이틀 · 1장 QA) |
| 공개 전 점검         | [publishing.md](../../../docs/publishing.md)                                  |
