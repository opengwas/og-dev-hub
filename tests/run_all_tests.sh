#!/usr/bin/env bash
# Run every suite: each tests/**/test_*.py as a script, one at a time, from the
# repository root, printing how long each took. A suite's fixture modules sit
# beside it (`architecture_fixtures.py`), which running it as a script puts on
# its import path. Exits 1 if any suite fails.
set -u
cd "$(dirname "$0")/.."
now() { date +%s.%N; }
elapsed() { awk -v a="$1" -v b="$(now)" 'BEGIN { printf "%.1f", b - a }'; }
failed=()
started=$(now)
while IFS= read -r suite; do
    t0=$(now)
    if python3 "$suite"; then status=ok; else status=FAILED; failed+=("$suite"); fi
    printf '%-64s %-6s %6ss\n' "$suite" "$status" "$(elapsed "$t0")" >&2
done < <(find tests -name 'test_*.py' -type f | sort)
printf 'all suites %ss\n' "$(elapsed "$started")" >&2
if ((${#failed[@]})); then
    printf 'FAILED: %s\n' "${failed[@]}" >&2
    exit 1
fi
