# 공개 레포 점검 — 리포에 원본이 남지 않게

이 저장소는 **공개돼 있다**(`byunmaster/ed-patch`, 2026-10-07). 예전엔 작업 레포는 비공개로 두고
산출물 전용 공개 레포 `ed-patch` 에 패처 HTML 만 내보냈는데, 10-07 에 작업 레포가 그 이름을
이어받아 공개됐고(옛 출력 레포는 지웠다 — 사본은 `.local/keep/archive`) 커밋 이력도 정리 없이
그대로 공개했다(마스터 판정 A). 그래서 소스·산출물 어디에도 원저작물의 축자 복제가 없어야 한다.

원칙은 하나다: **원본은 소장자의 디스크에만 있고, 리포에는 "어디를 어떻게 바꾸는지"와
"제대로 된 원본이 맞는지 확인할 해시"만 둔다.**

## 배포 경로 (2026-10-07)

- **사이트** — `patcher/site/` 를 main 에 머지하면 `.github/workflows/pages.yml` 이 GitHub Pages 로
  굽는다(진행 상황·배포 정보 정본은 `site.json`). 릴리스 이벤트는 main 기준으로 다시 띄운다
  (Pages 환경이 main 배포만 받는다). 미리보기는 `python3 patcher/site/build_site.py --out .local/cache/site`.
- **[kr] 패치 파일** — 게임의 `make_dist.py` 가 `work/dist/` 에 xdelta·BPS 를 만들고,
  `.local/ship/release/<태그>/` 로 옮겨 릴리스(`<게임>-<트랙>-v<버전>`)에 첨부한다. 워크플로가
  릴리스에서 받아 페이지 옆에 둔다. **git 에는 안 들어간다.**
- **표지·게임 화면** — 릴리스 `site-covers` 의 PNG(로컬 원본은 `.local/ship/site-covers/`).
- 원격에는 `main` 과 릴리스 태그만 둔다 — 게임 브랜치는 올리지 않는다.
- ⚠ 옛 `scripts/patcher.sh deploy`(출력 레포 main 을 강제로 덮어쓰던 갈래)는 걷었다 — 이 레포가
  그 이름을 이어받아, 남겨 두면 한 번에 이 레포 main 이 패처 파일 하나로 덮인다.

## 트랙별로 지키는 방식

### [kr] 번역 문안 — 자체 번역(포인터 체계는 버렸다)

- 문장급 문안(팔콤 일문 · 만트라 정발 번역)은 **코드·JSON에 임베드하지 않는다.**
- `games/*/textmap/*.json` 은 **우리 번역**(`ours`)을 담는다. 정발 원본의 **위치
  포인터**(`{f, o, l}`)를 쓰던 자리는 `tools/derive_text.py` 가 빌드 때 `originals/kr/`
  에서 문안을 꺼내 왔는데, ⚠ **2026-08-18 자체 번역 전환으로 kr 트랙은 그 길을 안 쓴다**
  (ED1·ED2 EXE 문안의 정발 포인터는 0 이다). 포인터 방식은 [fix] 트랙과 옛 자료에만 남는다.
  → 점검은 **`ours` 쪽**을 본다: 우리 문안이 정발을 베끼지 않았나
  (`games/ps1-ed1+2/tools/check_forbidden.py` — 게임 게이트에 물려 있다). 10-04 실측: PS1 대사
  20자↑ 일치 1.4% · 30자↑ 0줄.
- JP 원문 키는 sha1 해시(`k`, `sha`)라 원문을 복원할 수 없다.
- 단어 수준 명칭·라벨(아이템·몬스터·지명·메뉴)은 저작권 대상이 아니라 코드에 둬도 된다.
- **문서·주석·테스트·정본의 원문 문장**은 `scripts/check/check_copyright.py`(래칫, 10-09)가 막는다 — 정본은 라벨·시스템·
  전투 정형 문구만 두고 대사는 두지 않는다(대사 172키를 걷었다). 정발 맞춤법 교정쌍도 **우리 문안에 실제로 걸리는 것만**
  남긴다(PS1 3,066 → 33 — 나머지는 정발 문장 조각이었다).

### [fix] 패치 스펙 — 스키마 v2 (원본 바이트 없음)

- `games/*/patches/*.json`은 **우리가 쓴 값(`to`)과 해시만** 담는다. 항목은
  `{file, offset, to}`, 파일 단위로 `{size, sha1_from, sha1_to}`.
- 이 JSON은 `patcher/build.py`가 웹 패처 HTML에 **통째로 인라인**해 공개
  배포한다. 그래서 원본 바이트 필드(`from`)를 되살리면 그 순간 상용 바이너리
  조각을 재배포하는 게 된다.
- 검증은 파일 전체 sha1로 한다 — 구간 비교보다 오히려 엄격하다(스펙이 안 건드리는
  자리가 달라도 잡아낸다).
- 대신 복원은 차분 역적용이 불가능하므로 **백업 기반**이다(`apply_patch.py`가 적용 시
  `<파일>.orig`를 남긴다).

> 이력: 2026-07-30 이전 스키마(v1)는 `from`에 원본 바이트를 담았고, 그게 공개
> 페이지에 822B 실려 나가고 있었다. 스키마 v2로 전환하며 제거했다.

## 패처를 다른 게임으로 넓힐 때 — 경계선

`patcher/build.py`는 `games/*/patches/*.json`을 스캔하므로 게임이 늘면 그 게임의
`kind == "fix"` 패치가 같은 페이지에 자동으로 실린다. 다만 **아무 패치나 이 형식으로
담으면 안 된다.**

| 이 형식(스키마 v2 인라인)으로 OK | 다른 경로가 필요                  |
| -------------------------------- | --------------------------------- |
| 파일 단위 · 희소 변경            | 디스크 이미지 · 대량 변경         |
| `to` 바이트가 **우리가 쓴 값**   | `to` 바이트가 **원저작물 파생**   |
| 예: dos-ed2 [fix], 향후 mod,     | 예: PS1/새턴 이미지 한글패치 [kr] |
| 정발 윈도우판 `ED3_DT*.dat` 류   |                                   |

PS1 영웅전설 1+2를 실측한 수치(2026-07-30):

```
252,498,960B 중 다른 바이트 1,235,791B (0.49%) / 연속 구간 3,555개
→ to 를 hex 로 담으면 스펙만 2.5MB (현재 페이지 전체가 130KB)
```

세 가지가 걸린다:

1. **크기** — 페이지가 130KB → 3MB 가 된다.
2. **런타임** — 페이지는 `arrayBuffer()`로 통째로 읽고 `.BAK`를 쓰고 다시 전체를 쓴다.
   252MB면 RAM 500MB+·I/O 750MB고, WebCrypto 는 스트리밍 digest 가 없어 sha1 검증에
   전체 버퍼가 필요하다. `.bin` 파일명이 덤프마다 달라 basename 매칭과도 안 맞는다.
3. **이력(결정적)** — `patches/*.json`은 **커밋되는 파일**이다. 패치는 버전마다 통째로 바뀌는
   바이너리 성격이라 git 이력에 쌓이면 거둬들일 수 없고 레포가 불어난다. ⚠ 종전 근거는 「[kr]의
   `to` 바이트는 정발 문안 전량」이었는데, **2026-08-18 자체 번역 전환으로 맞지 않게 됐다**(문안은
   우리 번역이다).

→ **[kr]은 xdelta/BPS 를 `work/`(gitignore) 빌드 산출물로 만들고, 배포 시점에 페이지가
그걸 싣는다.** 릴리스물이 번역을 담는 것은 번역패치의 본질이라 문제없지만, git 에는
들어가지 않는다(위 「배포 경로」 — 릴리스 첨부 → Pages 워크플로가 받아 싣는다).

## 배포 전 체크리스트

```bash
# 1. 패치 스펙에 원본 바이트가 없는지
grep -rn '"from"' games/*/patches/*.json          # 0건이어야 한다

# 2. 빌드 산출물(공개 페이지)에도 없는지
sh scripts/patcher.sh build
grep -c '"from"' .local/cache/patcher/index.html  # 0 이어야 한다

# 3. 문안·코드·주석에 정발 문장이 박혀 있지 않은지 (게임 게이트가 돌린다)
python3 games/ps1-ed1+2/tools/check_forbidden.py

# 4. 추적되는 파일 중 게임 데이터가 섞였는지
git ls-files | grep -iE '\.(bin|cue|iso|img|chd|mdf|exe|dll|dat)$'   # 0건이어야 한다

# 5. 로컬 절대경로가 남았는지
git grep -n "/Users/" -- . ':!docs/publishing.md'  # 0건이어야 한다
```

### 지문 표기 — 넷을 다 적는다 (2026-08-11)

`python3 games/ps1-ed1+2/tools/release_manifest.py` 가 원본·결과의 **CRC32 / MD5 / SHA-1 /
SHA-256** 을 뽑아 붙여 쓸 표까지 낸다.

⚠ **받는 사람이 자기 원본이 맞는지 확인할 방법이 있어야 한다.** 웹 패처는 sha1 하나로 게이트를
걸지만 손에 든 도구가 사람마다 다르다(Flips=CRC32 · 파일 관리자=MD5 · 우리 패처=SHA-1) —
하나만 적으면 대조를 못 한다. 해시는 저작물이 아니라 지문이라 공개해도 원본이 복원되지 않는다.

⚠ **빌드도 원본을 확인한다** — `common.verify_source` 가 크기·sha1 을 보고 다르면 빌드를
세운다(오프셋·LBA 가 전부 그 덤프에 결박돼 있어, 다른 리비전이면 **실패 없이 망가진 이미지가
나온다**). 알고도 계속하려면 `ALLOW_NONCANONICAL_SRC=1`.

## 웹 패처 회귀 확인

스펙 형식을 바꾸면 CLI 패처와 웹 패처를 **둘 다** 확인한다. 원본은 소장본에서
임시 디렉터리로 복사해 쓰고, originals는 건드리지 않는다.

```bash
# CLI: 적용 → 멱등 → 복원 한 바퀴
mkdir -p /tmp/edtest/SCENA && cp originals/kr/dos-ed2/SCENA/F_50{1,2}.DLL /tmp/edtest/SCENA/
python3 games/dos-ed2/tools/apply_patch.py games/dos-ed2/patches/issue-1-suel-boat-tour.json /tmp/edtest --check
python3 games/dos-ed2/tools/apply_patch.py games/dos-ed2/patches/issue-1-suel-boat-tour.json /tmp/edtest
python3 games/dos-ed2/tools/apply_patch.py games/dos-ed2/patches/issue-1-suel-boat-tour.json /tmp/edtest --revert

# 웹: 빌드한 HTML에서 판정 로직을 떼어내 실제 원본으로 돌린다
#   inspect(원본) == "ready" / inspect(applyTo(원본)) == "applied"
#   sha1(applyTo(원본)) == sha1_to / 변조본·크기 다름 == "mismatch"
sh scripts/patcher.sh serve      # 브라우저 확인 (127.0.0.1 — file:// 로는 안 된다)
```

## 남겨 둔 경계

- 리버싱 노트(디스어셈블 발췌·오프셋 표)는 공개 전 「얼마나 상세한가」가 미결이었는데, 손대지 않고 그대로
  공개했다(10-07).
- `docs/reference/_inventory/`(카페 게시판 원본 덤프)는 타인 게시글이라 gitignore 를 유지한다.
