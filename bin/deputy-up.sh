#!/usr/bin/env bash
# deputy-up.sh - 출근 전 무인 운영 기동
#
# 사용법:  ./deputy-up.sh [프로젝트경로]
# 하는 일: 점검 → 절전 차단 → 멤버별 백그라운드 세션 기동(목표 부착)
set -euo pipefail

PROJECT="${1:-$PWD}"
cd "$PROJECT"

# PATH 에 설치돼 있으면 그걸 쓰고, 아니면 이 스크립트 옆의 것을 쓴다
if command -v deputy >/dev/null 2>&1; then
  DEPUTY="$(command -v deputy)"
else
  DEPUTY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/deputy"
fi
CFG=".deputy/deputy.json"

[ -f "$CFG" ] || { echo "deputy-up: $PROJECT 에 .deputy/deputy.json 이 없습니다. 'deputy init' 을 먼저 실행하세요."; exit 1; }

echo "=== 1/4 점검 ==="
if ! "$DEPUTY" doctor; then
  echo
  echo "차단 항목이 있습니다. 고친 뒤 다시 실행하세요."
  echo "(그래도 강행하려면 DEPUTY_FORCE=1 를 붙이세요)"
  [ "${DEPUTY_FORCE:-0}" = "1" ] || exit 1
fi

echo
echo "=== 2/4 절전 차단 ==="
if pgrep -x caffeinate >/dev/null; then
  echo "  이미 실행 중"
else
  caffeinate -dimsu &
  echo "  caffeinate 시작 (pid $!)"
fi

echo
echo "=== 3/4 세션 기동 ==="
MEMBERS=$(python3 -c "import json;print(' '.join(m['name'] for m in json.load(open('$CFG'))['members']))")

for M in $MEMBERS; do
  BRIEF=$(python3 -c "
import json
m=[x for x in json.load(open('$CFG'))['members'] if x['name']=='$M'][0]
print(m.get('brief','') or '(역할 미지정)')")
  OWNS=$(python3 -c "
import json
m=[x for x in json.load(open('$CFG'))['members'] if x['name']=='$M'][0]
print(', '.join(m.get('owns',[])) or '(담당 미지정)')")

  read -r -d '' PROMPT <<EOF || true
너는 deputy 세션 '$M' 이다. 역할: $BRIEF
담당 디렉터리: $OWNS — 이 밖의 파일은 절대 수정하지 않는다.

작업 방식. 매 턴 이 순서를 지킨다.
1. 먼저 \`deputy next\` 를 실행한다. 무엇을 할지는 이 출력이 정한다. 스스로 정하지 않는다.
2. 출력의 지시를 그대로 수행한다. 우선순위가 이미 정렬되어 있다.
3. 리뷰를 요청받으면 형식적으로 동의하지 말고 실제로 코드를 읽고 판단한다.
   근거 없는 AGREE 는 합의를 무의미하게 만든다. 우려가 있으면 OBJECT 나 AMEND 를 쓴다.
4. 제안할 때는 반드시 대안을 하나 이상 비교하고, 완료 기준을 명령과 기대 출력으로 쓴다.
5. 작업 중 문제를 발견하면 판단한다. 부모의 완료 기준을 이것 없이 만족시킬 수 없다면
   \`deputy derive <부모번호>\` 로 파생 이슈를 만든다. 아니면 독립 이슈이거나 그냥 노트다.
   파생 이슈는 자식을 가질 수 없고, 부모당 3개를 넘길 수 없다.
6. 부모와 파생 이슈를 모두 끝낸 뒤에야 다음 최상위 작업으로 넘어간다.
   \`deputy done <번호> --close --result "..."\` 로 기록하고 다시 1번으로 간다.

금지 사항.
- 담당 밖 파일 수정
- main/master 브랜치로 push
- 배포, 마이그레이션, 시크릿 조작
- 이견이 남았는데 deputy claim --force 로 밀어붙이기

막히면 멈추지 말고 \`deputy note <번호> "무엇에 막혔는지"\` 로 이슈에 남긴다.
사람은 출근해 있고 폰으로 GitHub 이슈를 본다. 이슈 코멘트가 유일한 보고 채널이다.

시작한다. 지금 바로 \`deputy next\` 를 실행하라.
EOF

  echo "  → $M 기동 중..."
  DEPUTY_MEMBER="$M" claude --bg --name "deputy-$M" "$PROMPT" >/dev/null 2>&1 || {
    echo "     실패. 수동으로 실행하세요:"
    echo "     DEPUTY_MEMBER=$M claude --bg --name deputy-$M \"...\""
  }
done

echo
echo "=== 4/4 완료 ==="
echo "  세션 관제:  claude agents      (Ctrl+T 로 각 세션을 고정하세요 - F-03)"
echo "  진행 상황:  deputy status  또는 폰에서 GitHub 이슈"
echo "  퇴근 후:    deputy status && gh pr list"
echo
echo "각 세션에 목표를 걸어두려면 agent view 에서 붙어 다음을 입력하세요:"
echo "  /goal deputy next 가 후보 이슈 없음을 보고하고, 내가 착수한 이슈가 모두 닫혔다."
echo "        매 턴 deputy next 를 실행한 기록이 대화에 있어야 한다. 60턴을 넘기면 중단한다."
