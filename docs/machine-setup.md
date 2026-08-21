# 작업 머신 옮기기 — 체크리스트

이 레포를 새 머신에 세우는 절차. **제1 원칙(빌드는 결정적이어야 한다)이 걸린 작업**이라
순서에 이유가 있다 — 특히 ④를 하기 전에 정본 갱신기를 돌리면 안 된다.

기준 사례: Proxmox LXC(Debian 13 trixie) 이관, 2026-08-09.

## 왜 옮기나 — 실측 근거

|               | Mac (i7-7700HQ)         | NAS (Ryzen 7 5825U)      |
| ------------- | ----------------------- | ------------------------ |
| 코어          | 4C/8T                   | **8C/16T**               |
| 지속 단일코어 | ~3.4–3.6GHz (Kaby Lake) | **4.16–4.42GHz** (Zen 3) |
| RAM           | —                       | 32GB                     |

지속 부하 실측(호스트, `governor=performance`): 8초 4419MHz → 14초 4164MHz. **거의 안 떨어진다.**
단일코어 대략 **1.5배**. mednafen 새턴 코어가 싱글스레드 바운드라 이게 결정적이다.

⚠ **「Mac 에서는 풀스피드가 빠듯했다」는 정정한다**(2026-08-22 재실측). 맥(i7-7700HQ)에서
mednafen 새턴이 **평상시 60fps 로 돌고 빨리감기에서 150fps** 까지 나온다 — 여유가 2.5배다.
PS1 은 같은 자로 250fps(4.2배). 즉 **맥에서 새턴 인게임 QA 가 된다.** dev 로 옮긴 이득은
빌드·배치 같은 기계 작업 쪽이지 「맥에서 새턴이 안 돈다」가 아니다.
· 재는 법: `sh scripts/emu.sh ss-ed1+2` → `Shift+F1` 로 FPS 표시.
· 빨리감기 배속은 **코어 한계**다 — `ffspeed 8` 은 상한일 뿐이고, 영상(softfb↔opengl·확대
  배율)·오디오(`ffnosound`)·블릿 대기(`video.blit_timesync`)를 다 바꿔도 숫자가 안 움직였다.

⚠ 옮기기 전에 호스트에서 확인할 것:

```bash
lscpu | grep -i 'mhz\|model name'
cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor   # performance 여야 한다
taskset -c 0 openssl speed -seconds 15 sha256 >/dev/null 2>&1 &
sleep 8; grep -m1 'cpu MHz' /proc/cpuinfo; sleep 6; grep -m1 'cpu MHz' /proc/cpuinfo; wait
```

저전력 박스는 cTDP 로 부스트가 묶여 있을 수 있다. 지속 클럭이 2GHz대로 주저앉으면 이관 이득이 없다.

## ① 컨테이너 — VM 이 아니라 LXC

LXC 는 커널을 공유해 **CPU 오버헤드가 사실상 0** 이다. KVM VM 은 오버헤드 + 장치 패스스루가
번거롭고, Docker 는 LXC 안에 또 한 겹이다. 격리로 얻을 게 없으니 **YAGNI — LXC 하나면 된다.**

| 항목        | 값                                                                      |
| ----------- | ----------------------------------------------------------------------- |
| 템플릿      | `debian-13-standard` (12 도 무방)                                       |
| 루트 디스크 | **SSD 풀(`local-lvm`), 60GB**                                           |
| 코어        | 전부 (cpulimit 걸지 말 것)                                              |
| 메모리      | 8GB (torch 쓸 거면 16GB)                                                |
| 권한        | unprivileged                                                            |
| 기능        | `nesting=1`                                                             |
| 호스트명    | 범용 작업 박스면 `dev` — 서비스 컨테이너와 나란히 놨을 때 성격이 읽힌다 |

**디스크는 SSD 다.** `work/derived` 에 JSON 이 수백 개고 빌드마다 전부 읽는다 + 에이전트가
grep/find 로 레포를 훑는다 — 소파일 랜덤 읽기가 HDD 에서 제일 아프다. 전체가 18GB
(originals 15 + 레포·vendor·work 3)뿐이라 나눌 이유도 없다.

⚠ SSD 여유가 없어 `originals/` 만 HDD 로 뺄 때는 **unprivileged LXC 의 UID 매핑**을 손봐야 한다.
15GB 아끼자고 그 번거로움을 사는 셈이니, 여유가 있으면 통째로 SSD 에 둔다.

## ② 패키지

```bash
apt install -y git build-essential python3 python3-venv python3-pip pkg-config rsync curl \
  libflac-dev libsndfile1-dev liblzo2-dev libmpcdec-dev libsdl2-dev libzstd-dev gettext
```

- 뒤쪽 여섯은 **mednafen 빌드 의존성**이다.
- ⚠ macOS 에서 필요하던 `flock` 은 **리눅스 기본이라 불필요**하다(루트 `CLAUDE.md` 의 경고는
  macOS 한정이다).

**로케일 — LXC 템플릿은 `LANG=C` 로 나온다.** 그대로 두면 `git log` 의 한국어 커밋 메시지가
`<EB><B3><B4>` 처럼 **바이트로 깨져 보인다**(less 가 UTF-8 을 모르는 것이다 — 데이터는 멀쩡하고
`| cat` 으로 pager 를 우회하면 정상이다). 이 레포는 커밋 메시지·문서·검토표가 전부 한국어라
사실상 필수다.

```bash
printf 'LANG=C.UTF-8\n' > /etc/default/locale
printf 'LANG=C.UTF-8\n' >> /etc/environment   # 비대화형 셸(`ssh dev '명령'`)에도 먹어야 한다
```

- Debian 13 은 `C.UTF-8` 이 기본 포함이라 `locales` 설치·`locale-gen` 이 필요 없다.
- `ko_KR.UTF-8` 까지 갈 이유는 없다 — 도구 메시지가 한국어로 바뀌어 오히려 로그가 섞인다.
- ⚠ **둘 다** 써야 한다. `/etc/default/locale` 만 두면 로그인 셸에서만 먹어서, 에이전트가
  던지는 `ssh dev '명령'` 은 여전히 `C` 다(Node·cargo 링크와 같은 함정이다).

**파이썬** — 빌드 체인이 실제로 쓰는 서드파티는 넷뿐이다:

```bash
python3 -m venv .venv && .venv/bin/pip install pillow capstone numpy scipy
```

- **포매터도 여기 있어야 한다** — `pip install ruff`(레포 규약: `ruff check --fix` + `format`).
  마크다운용 `oxfmt` 는 npm global 이다(아래 Node 절 — `/usr/local/bin` 링크까지 해야 한다).
- **torch·LaBSE(`sentence_transformers`)는 깔지 않는다** — `align_semantic.py` 는 제안
  생성기고 빌드는 커밋된 정본(`align_map.json`)만 읽는다. 없어도 빌드가 도는 걸 검증해
  뒀다(2026-08-04).
- ⚠ `scipy` 를 빠뜨리기 쉽다 — `patch_gfx_title.py` 가 `scipy.ndimage` 로 인페인트를 한다.

**Node — nvm 으로 LTS 를 쓰되 `/usr/local/bin` 에 링크한다.** Claude Code 가 Node 22+ 를
요구하는데 배포판 기본은 뒤처진다(Debian 13 = 20).

```bash
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
. "$HOME/.nvm/nvm.sh" && nvm install --lts && nvm alias default 'lts/*'
NB=$(dirname "$(nvm which default)")
for b in node npm npx corepack; do ln -sfn "$NB/$b" "/usr/local/bin/$b"; done
npm install -g --allow-scripts=@anthropic-ai/claude-code @anthropic-ai/claude-code
```

⚠ **링크가 핵심이다.** nvm 은 `~/.bashrc` 에서 로드되는데 Debian 의 `.bashrc` 는 맨 앞에서
비대화형 셸이면 `return` 한다 — 그래서 `ssh dev '명령'` · 크론 · 스크립트에서는 `node` 를
못 찾는다. 원격에서 에이전트가 명령을 던지는 구성이면 이걸로 바로 막힌다.
⚠ npm 은 postinstall 스크립트를 기본 차단한다 — `--allow-scripts` 없이 깔면 절반만 설치된다.

## ③ 레포·원본·에뮬레이터

1. **레포 클론** + `originals/` 전송(15GB). `originals/` 는 gitignore 라 따라오지 않는다.

   ⚠ **`git config --local` 은 클론에 안 따라온다.** 이 레포는 전 히스토리가
   `byunmaster <byunma@naver.com>` 으로 통일돼 있어(공개 준비) 전역 이름이 다르면 **커밋이
   조용히 그걸로 나간다**. 첫 커밋 전에 `git log --format='%an <%ae>' | sort -u` 로 확인할 것
   (2026-07-31 에 실제로 누락됐다).

2. **emucap 재빌드** — 바이너리라 절대 따라오지 않는다. `vendor/emucap` 은 서브모듈이 아니라
   공개 저장소(`github.com/mcpads/emucap`) 클론이니 **rsync 하지 말고 같은 리비전으로 새로
   클론**한다(1.1GB 중 1.09GB 가 그 머신용 빌드 산출물이다). **둘 다** 지어야 한다:

   ```bash
   sh vendor/emucap/adapters/mednafen/build.sh   # 에뮬레이터(ss·psx·pce·pcfx·md·wswan·ngp 한 바이너리)
   cargo build --release                          # MCP 서버 — emucap-mcp · emucap-track-mcp
   ```

   ⚠ **빌드했다고 등록되는 게 아니다.** emucap MCP 는 **local 스코프**(`~/.claude.json` 의
   프로젝트 경로 키)라 클론에 안 따라오고, 절대경로를 쓰므로 커밋되는 `.mcp.json` 에도 못 넣는다:

   ```bash
   for n in control track; do
     claude mcp add "emucap-$n" -s local -- "$PWD/vendor/emucap/target/release/emucap${n:+-}${n#control}-mcp"
   done   # 실제 바이너리명은 target/release 를 보고 맞춘다
   ```

   ⚠ **리눅스에서는 `vendor/emucap` 워킹트리가 항상 "수정됨"으로 보인다.**
   `adapters/desmume-nds/patches/*.patch` 가 그렇다 — `.gitattributes` 가 `eol=lf` 인데
   저장된 블롭 안에 CRLF 가 섞여 있어, 체크아웃할 때마다 변환돼 원본과 어긋난다. 우리가
   고친 게 아니고 NDS 어댑터라 우리 경로와도 무관하지만, 이대로 두면 **`--ff-only` 당기기가
   막힌다**(2026-08-09 실측). 그 경로만 변환을 끄면 영구히 해결된다:

   ```bash
   printf 'adapters/*/patches/*.patch -text\n' > vendor/emucap/.git/info/attributes
   git -C vendor/emucap checkout -- adapters/
   ```

   ⚠ **MCP 서버는 Rust 라 rustup 이 따로 필요하다**(어댑터 빌드가 이걸 안 만들어 준다).
   Node 와 마찬가지로 `~/.cargo/bin` 은 비대화형 셸에서 안 잡히니 `/usr/local/bin` 에 링크한다.
   ⚠ 빌드 후 **Claude Code 재시작** — MCP 서버·어댑터·바이너리 셋이 엇갈린다.

3. **BIOS** → `~/.mednafen/firmware/` (유저가 제공, **커밋 절대 금지**)

   | 시스템    | 파일                  | 필수?    |
   | --------- | --------------------- | -------- |
   | PS1       | `scph5500.bin`(JP) 등 | **필수** |
   | PC엔진 CD | `syscard3.pce`        | **필수** |
   | 새턴      | `sega_101.bin`(JP)    | 권장     |

   `mednafen.cfg` 는 손댈 필요 없다 — 기본값이 이미 그 파일명을 가리킨다.

4. **타이틀 폰트** → `~/.local/share/fonts/AppleSDGothicNeo.ttc` (BIOS 와 같이 유저가 제공,
   **커밋 절대 금지** — Apple 번들이라 배포 불가다)

   ⚠ **이게 없으면 `patch_gfx_title.py` 가 빌드를 멈춰 세운다** — ④ 검증이 첫 명령에서 죽는다.
   macOS 의 `/System/Library/Fonts/AppleSDGothicNeo.ttc` 를 그대로 복사하면 된다(28MB).
   자리를 바꾸려면 `EIYUU_TITLE_FONT` 로 지정한다.

   ⚠ **다른 폰트로 대체하지 말 것.** 도구가 일부러 폴백 없이 실패한다 — 인게임 확인이 끝난
   타이틀 자형이 말없이 바뀌는 게 제일 나쁘다(2026-07-16 확인분). 경위는 `games/ps1-ed1+2/docs/devlog.md`.

5. **헤드리스 실행** — `SDL_VIDEODRIVER=dummy` + mednafen 은 **`-sound 0`**(ALSA 장치가 없으면
   `SDL_AUDIODRIVER=dummy` 로는 안 되고 사운드 열다 죽는다). emucap MCP 는 TCP 라 원격 제어가
   되고 프레임도 emucap 이 직접 뜬다(screenshot 도구).

   스모크 테스트 — 원본을 물려 모듈이 제대로 잡히는지만 본다:

   ```bash
   SDL_VIDEODRIVER=dummy timeout 12 <mednafen> -sound 0 <cue>   # "Using module: ss(Sega Saturn)"
   ```

⚠ **리눅스는 파일명 대소문자를 가린다.** 일부 `.cue` 가 트랙 파일을 **대문자로** 참조하는데
실제 파일명은 그렇지 않다 — macOS(대소문자 비구분)에서는 열리던 것이 여기서 `Error opening CD`
로 죽는다. 실측: `pce-ed1` 의 `[HCD1020]` 덤프, `pce-ed2` 의 유일 덤프. **originals 는 읽기
전용이라 고치지 않는다** — 같은 폴더의 다른 덤프를 쓰거나(`pce-ed1` 은 `(JP).cue` 가 정상),
필요하면 `work/` 에 경로를 고친 `.cue` 사본을 둔다.

## ④ 검증 — 첫 명령은 빌드다

```bash
python3 games/ps1-ed1+2/tools/build.py
```

**산출물 sha1 을 `games/ps1-ed1+2/docs/status.md` 의 「재현 기준」 표와 대조한다.**
맞으면 이관 성공이자 **결정성 실증**이고, 틀리면 이관 자체가 잘못된 것이라 여기서 잡힌다.
`work/derived` 가 통째로 없으면 덤프 둘만 만들면 된다(`extract_scn.py` · `extract_dos_kr.py`).

> ⚠⚠ **이 대조를 통과하기 전에는 정본 갱신기를 절대 돌리지 말 것** —
> `align_map.py --update` · `assign_pages` · `lock_lines.py --freeze`.
> **그 머신의 동점 결과를 정본으로 승격시킨다**(루트 `CLAUDE.md` 제1 원칙). 검증기를
> 갱신기로 쓰는 셈이고, 회사 빌드와 집 빌드가 갈렸던 사고(2026-08-03)의 재발 경로다.

## ⑤ 인게임 확인은 로컬에 남긴다

원격 화면은 문안 확인엔 되지만 실제 플레이 QA 에는 답답하다. **빌드 산출물만 당겨온다.**

```bash
rsync -avP --include='Eiyuu Densetsu (KR).*' --exclude='*' \
  dev:work/eiyuu-densetsu-patch/games/ps1-ed1+2/work/build/ \
  ~/work/eiyuu-densetsu-patch/games/ps1-ed1+2/work/build/
```

252MB 하나라 기가비트로 3~5초다. ⚠ 당길 때 두 가지를 같이 봐야 한다 —
**`*.failed` 는 받지 말 것**(실패한 빌드는 산출물을 무효화한다) · **sha1 을 찍어 확인할 것**
(`BATTLE_JP=1` 빌드가 **같은 이름으로** 나온다). 낡거나 엉뚱한 이미지를 정상으로 오해하는 게
이 레포의 1급 사고다(루트 `CLAUDE.md` 「빌드 규율」).

SMB/NFS 로 직접 마운트해 여는 것도 되지만 권하지 않는다 — 느리고, 무엇보다 **지금 무엇을
보고 있는지 확인이 약해진다.**
