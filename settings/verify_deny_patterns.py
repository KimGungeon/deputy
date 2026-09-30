"""settings/project-settings.json, .claude/settings.json 의 deny 패턴 검증.

Bash(...) 래퍼를 벗기고 안쪽 스펙에만 ':*' 뒤 리터럴 문자 검사를 적용한다.
래퍼를 안 벗기면 닫는 괄호 ')' 가 '.+' 에 매치되어 정상 규칙까지 오탐한다.
"""
import json
import re
import sys

TARGETS = ["settings/project-settings.json", ".claude/settings.json"]


def bad_patterns(deny_list):
    bad = []
    for p in deny_list:
        m = re.match(r"^Bash\((.*)\)$", p)
        spec = m.group(1) if m else p
        if re.search(r":\*.+", spec):
            bad.append(p)
    return bad


def main():
    ok = True
    for path in TARGETS:
        d = json.load(open(path, encoding="utf-8"))
        bad = bad_patterns(d["permissions"]["deny"])
        if bad:
            ok = False
            print(f"FAIL {path}: {bad}")
        else:
            print(f"OK {path}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
