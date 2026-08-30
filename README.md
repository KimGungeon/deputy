# deputy

여러 Claude Code 세션이 **사람 없이 토론하고 합의하며** 일하게 만드는 도구.
출근해 있는 8시간 동안 사이드 프로젝트가 스스로 굴러가는 것을 목표로 한다.

상태는 전부 **GitHub 이슈**에 있다. 로컬에 숨은 저장소가 없다.
회사에서 폰으로 GitHub 앱만 열면 진행 상황이 보이고, 코멘트 한 줄로 개입할 수 있다.

| deputy 개념 | GitHub |
|---|---|
| 작업 단위 | 이슈 |
| 토론 | 이슈 코멘트 |
| 합의 상태 | 라벨 `deputy:next / agreed / revise / wip / blocked` |
| 착수자 | assignee |
| 완료 | 이슈 close |

로컬 파일은 `.deputy/deputy.json` 하나뿐이고, 이건 상태가 아니라 **설정**이다
(누가 어느 디렉터리를 담당하는지). 저장소에 커밋해서 공유한다.

---

## 설치

`deputy` 는 프로젝트에 종속되지 않는다. **한 번 설치하고, 저장소마다 `deputy init` 한 줄**이면 된다.

### 방법 A — 플러그인 (권장)

```
/plugin marketplace add KimGungeon/deputy
/plugin install deputy@deputy-kit
```

플러그인이 활성화되면 `bin/` 이 자동으로 PATH 에 올라가고 스킬도 함께 설치된다.
프로젝트에서는 `deputy init --no-skills` 만 하면 된다. 팀원도 위 두 줄이면 끝난다.

개발 중에는 설치 없이 시험할 수 있다:

```bash
claude --plugin-dir /path/to/deputy
```

### 방법 B — 전역 심볼릭 링크

플러그인 없이 CLI 만 쓰려면:

```bash
./bin/deputy self-install            # ~/.local/bin/deputy 로 링크
export PATH="$HOME/.local/bin:$PATH" # 셸 설정에 추가
```

링크로 설치해도 자기 패키지 경로를 찾아내므로 스킬·설정 스니펫이 그대로 동작한다.

### 방법 C — 프로젝트에 벤더링

저장소마다 독립적으로 두고 싶으면 `deputy/` 를 통째로 복사한 뒤 `bin/deputy` 를 직접 호출한다.

---

## 프로젝트에 적용

설치 방법과 무관하게, **어느 저장소에서든 이 한 줄**이다.

```bash
cd ~/아무-프로젝트
deputy init
```

멤버를 지정하지 않으면 **저장소 구조를 스캔해서 자동으로 제안**한다.
`git ls-files` 로 추적 중인 파일만 보므로 `node_modules` 같은 것은 애초에 들어오지 않는다.
`src/` `packages/` 같은 껍데기 디렉터리는 한 단계 더 들어가고, `tests/api` 는 `src/api` 에
자동으로 붙는다. 확장자가 없는 실행 파일은 shebang 으로 언어를 판단한다.

먼저 어떻게 나뉘는지만 보려면 (아무것도 바꾸지 않는다):

```bash
deputy scan
deputy scan --members 3
```

**담당은 지배적인 디렉터리에만 준다.** 남는 디렉터리를 억지로 나눠 갖지 않고 무주지로
남긴다. 담당 경계가 흐려지느니 아무도 안 갖는 편이 낫기 때문이다. 무주지를 건드려야 하는
작업은 제안 단계에서 그 사실이 드러나고, 다른 세션이 리뷰에서 판단한다.

직접 정하고 싶으면 여전히 명시할 수 있다:

```bash
deputy init --member "api:src/api,tests/api:백엔드 API 와 그 테스트" \
            --member "web:src/web,src/components:프론트엔드 UI"
```

`deputy init` 이 하는 일:

1. `.deputy/deputy.json` — 멤버와 담당 디렉터리
2. GitHub 라벨 5종 생성
3. `.claude/skills/` 에 스킬 설치 (`--no-skills` 로 생략)
4. `.claude/settings.json` 병합 — 샌드박스, `main` push 차단, 허용 명령
5. `~/.claude/settings.json` 병합 — 리밋 자동 재개, 세션 간 메시지 수신

**기존 설정을 덮어쓰지 않는다.** 리스트는 합집합, 딕셔너리는 재귀 병합, 값이 이미 있는
키는 그대로 둔다. 바꾸기 전에 `.bak` 을 남기고, 권장값과 다른 기존값은 화면에 알려준다.
두 번 돌려도 결과가 같다.

그다음 두 가지를 직접 해야 한다.

- `.deputy/deputy.json` 에서 각 멤버의 `owns` 와 `brief` 를 채운다.
  **담당이 겹치면 두 세션이 같은 파일을 고쳐 충돌한다.** `deputy doctor` 가 겹침을 잡아준다.
- GitHub 에 작업 이슈를 만들어 둔다. 세션은 여기서 다음 할 일을 고른다.
  제목 한 줄짜리도 괜찮다 — 근거는 세션이 제안하며 채운다.
  **열린 이슈가 없으면 세션이 할 일을 못 찾는다.**

```bash
deputy doctor     # 무인 운영 전 점검
```

---

## 하루 운영

### 출근 전

```bash
cd ~/내-사이드-프로젝트
/path/to/deputy/bin/deputy-up.sh
```

이 스크립트가 하는 일:

1. `deputy doctor` 로 점검 — 차단 항목이 있으면 기동하지 않는다
2. `caffeinate -dimsu` 실행 — 맥이 잠들면 세션도 멈춘다
3. 멤버별 백그라운드 세션 기동 (역할·담당·금지사항이 담긴 프롬프트 부착)

기동 후 `claude agents` 로 붙어서 각 세션에 목표를 건다.
**Ctrl+T 로 세션을 고정**하지 않으면 유휴 1시간 뒤 정리된다.

```
/goal deputy next 가 후보 이슈 없음을 보고하고, 내가 착수한 이슈가 모두 닫혔다.
      매 턴 deputy next 를 실행한 기록이 대화에 있어야 한다. 60턴을 넘기면 중단한다.
```

`/remote-control` 을 켜두면 폰에서 세션에 직접 말을 걸 수 있다.

### 회사에서

GitHub 이슈만 보면 된다. 개입은 **이슈 코멘트**로 한다.
세션은 매 턴 사람의 코멘트를 최우선(0순위)으로 읽고 반영한다.

### 퇴근 후

```bash
deputy status          # 전체 현황
gh pr list           # 올라온 작업
deputy log -n 40       # 무슨 논의가 있었는지
```

---

## 세션이 도는 방식

각 세션은 매 턴 `deputy next` 를 실행하고 그 지시를 따른다. 우선순위는 고정되어 있다.

| 순위 | 내용 | 왜 이 순서인가 |
|---|---|---|
| 0 | 사람이 남긴 코멘트 | 유일한 외부 신호다 |
| 1 | 내가 해야 할 리뷰 | 내가 안 하면 남이 막힌다 |
| 2 | 내가 진행 중인 작업 (파생 이슈 먼저) | 벌여놓고 안 끝내는 게 가장 나쁘다 |
| 3 | 내 제안의 판정 | 합의됐으면 착수, 이견이면 수정 |
| 4 | 새 작업 제안 | 위가 전부 비었을 때만 |

### 합의는 교착하지 않는다

| 판정 | 뜻 |
|---|---|
| `CLAIM` | 착수 가능 |
| `REVISE` | 이견 있음. 제안을 고친다 |
| `ESCALATE` | 수정 한도 초과. 범위를 좁혀 진행하고 근거를 남긴다 |
| `WAIT` | 리뷰 대기. **멈추지 않고** 사전 조사를 한다 |

45분 내 리뷰가 없으면 기권 처리되어 자동 진행된다.
수정 2회 후에도 이견이 남으면 범위를 좁혀 강행한다.
**어떤 조합에서도 영구 대기 상태가 생기지 않는다** (로직 테스트로 검증됨).

### 파생 이슈

작업 중 문제를 발견하면 세 질문을 순서대로 던진다.

1. 안 고쳐도 부모의 완료 기준이 통과하나? → **예면 독립 이슈**
2. 안 고친 채 부모를 닫아도 안전한가? → **예면 독립 이슈**
3. 둘 다 아니오 → **파생 이슈**

```bash
deputy derive <부모번호> --why "무엇을 발견했나" \
                      --blocks "왜 부모가 이것 없이 끝날 수 없나" \
                      --done-when "무엇이 참이면 끝인가"
```

- **깊이 1단계** — 파생은 자식을 못 가진다. 무한 증식을 원천 차단한다
- **부모당 3개** — 넘으면 부모의 범위 설정이 틀린 것이다. 코멘트만 남기고 넘어간다
- **합의를 거치지 않는다** — 파생은 선택이 아니라 이미 합의된 완료 기준이 강제하는 사실이다.
  대신 부모 본문에 체크리스트로 드러나 사람과 다른 세션이 즉시 본다
- 부모는 파생이 모두 닫히기 전에 닫히지 않는다. 단, 거기서 대기하지 않고 `deputy next` 로 넘어간다

---

## 명령

| 명령 | 하는 일 |
|---|---|
| `deputy scan` | 저장소 구조를 훑어 멤버 구성 제안 (변경 없음) |
| `deputy next` | 지금 무엇을 할지 (매 턴 실행) |
| `deputy propose <n>` | 이슈를 다음 작업으로 제안 |
| `deputy review <n>` | 남의 제안 검토 |
| `deputy consensus <n>` | 합의 판정 확인 |
| `deputy claim <n>` | 합의된 작업 착수 |
| `deputy derive <n>` | 파생 이슈 생성 |
| `deputy done <n>` | 완료 처리 |
| `deputy note <n>` | 이슈에 메모 |
| `deputy status` | 전체 현황 |
| `deputy doctor` | 무인 운영 전 점검 |

---

## 무인 운영 실패 모드 대응

`deputy doctor` 가 자동 점검하는 것:

| 코드 | 실패 모드 | 점검 |
|---|---|---|
| F-01 | 맥이 잠들어 세션 정지 | `caffeinate` 실행 여부, 전원 연결 |
| F-04 | 세션 간 메시지 보류 후 만료 | `crossSessionInbound` 설정 |
| F-05 | 리밋에서 정지 | `autoContinueAtUsageLimit` 설정 |
| — | 담당 디렉터리 겹침 → 파일 충돌 | `owns` 교집합 |
| — | 열린 이슈 없음 → 할 일 못 찾음 | 후보 이슈 수 |
| — | 배정만 남고 라벨 없는 미아 이슈 | 어떤 경로에서도 안 보이는 이슈 탐지 |

`deputy doctor` 는 차단 항목이 있으면 종료코드 1을 반환하고, `deputy-up.sh` 가 기동을 멈춘다.

F-03(백그라운드 세션 유휴 1시간 정리)은 `claude agents` 에서 **Ctrl+T 고정**으로 직접 막아야 한다.

---

## 팀 공유

방법 A 로 저장소를 올려두면 팀원은 두 줄로 전부 설치한다.

```
/plugin marketplace add <owner>/deputy
/plugin install deputy@deputy-kit
```

비공개 저장소도 된다. `.claude-plugin/plugin.json` 의 `version` 을 올리면 업데이트가 전달된다.
개발 중에는 설치 없이 `claude --plugin-dir /path/to/deputy` 로 바로 시험할 수 있다.

---

## 안전

`settings/project-settings.json` 이 다음을 강제한다.

- Bash 샌드박스 — 쓰기는 작업 디렉터리로 제한, `~/.aws/credentials`·`~/.ssh` 읽기 차단,
  `GITHUB_TOKEN`·`NPM_TOKEN` 환경변수 차단
- `main`/`master` push 거부, force push 거부, `gh release`·`gh secret` 거부

세션 프롬프트에도 금지사항이 박혀 있다: 담당 밖 파일 수정, 배포, 마이그레이션,
이견이 남은 상태에서 `--force` 로 밀어붙이기.
