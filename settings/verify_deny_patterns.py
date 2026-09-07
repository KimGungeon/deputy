"""settings/project-settings.json, .claude/settings.json 의 deny 패턴 검증.

Bash(...) 래퍼를 벗기고 안쪽 스펙에만 ':*' 뒤 리터럴 문자 검사를 적용한다.
래퍼를 안 벗기면 닫는 괄호 ')' 가 '.+' 에 매치되어 정상 규칙까지 오탐한다.
"""
import json
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TARGETS = ["settings/project-settings.json", ".claude/settings.json"]

# 브랜치명이 커맨드 문자열에 아예 안 나타나는 형태 (#8). 로컬이 main/master 에
# 체크아웃돼 있으면 이 커맨드들은 그쪽에 push 되지만 기존 main/master 리터럴
# 패턴에는 안 걸린다.
IMPLICIT_BRANCH_PUSH_FORMS = [
    "git push",
    "git push origin",
    "git push --all",
    "git push --all origin",
    "git push --mirror origin",
]


def bad_patterns(deny_list):
    bad = []
    for p in deny_list:
        m = re.match(r"^Bash\((.*)\)$", p)
        spec = m.group(1) if m else p
        if re.search(r":\*.+", spec):
            bad.append(p)
    return bad


def spec_to_regex(spec):
    """Bash 룰의 매칭 규칙(공식 문서): '*' 없는 룰은 정확히 그 문자열과만 일치.
    '*' 는 공백 포함 임의 텍스트에 매치, 룰 전체가 앵커된다."""
    parts = spec.split("*")
    return re.compile("^" + ".*".join(re.escape(p) for p in parts) + "$")


def uncovered_forms(deny_list):
    specs = []
    for p in deny_list:
        m = re.match(r"^Bash\((.*)\)$", p)
        specs.append(m.group(1) if m else p)
    regexes = [spec_to_regex(s) for s in specs]
    uncovered = []
    for cmd in IMPLICIT_BRANCH_PUSH_FORMS:
        if not any(rx.match(cmd) for rx in regexes):
            uncovered.append(cmd)
    return uncovered


def main():
    ok = True
    for path in TARGETS:
        d = json.load(open(path, encoding="utf-8"))
        deny = d["permissions"]["deny"]

        bad = bad_patterns(deny)
        if bad:
            ok = False
            print(f"FAIL {path}: 정규식 문법 위반 {bad}")
        else:
            print(f"OK {path}: 정규식 문법")

        uncovered = uncovered_forms(deny)
        if uncovered:
            ok = False
            print(f"FAIL {path}: 암시적 브랜치 push 미차단 {uncovered}")
        else:
            print(f"OK {path}: 암시적 브랜치 push(#8) 전부 차단")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
