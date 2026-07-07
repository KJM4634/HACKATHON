#!/usr/bin/env bash
# backend가 http://127.0.0.1:8000 에서 떠 있어야 함:
#   cd backend && uv run uvicorn app.main:app --port 8000
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
FAIL=0

check() {
  local name="$1" expected="$2" actual="$3"
  if [ "$actual" = "$expected" ]; then
    echo "OK   $name (HTTP $actual)"
  else
    echo "FAIL $name (expected $expected, got $actual)"
    FAIL=1
  fi
}

code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health")
check "/health" 200 "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/regions")
check "/api/regions" 200 "$code"

# region_id는 10자리 행정동코드 (LocalDataProvider 기준. 서면/남포동/해운대/광안리)
for region in 2623052000:서면 2611058000:남포동 2635051000:해운대 2650077000:광안리; do
  code_id="${region%%:*}"
  name="${region##*:}"
  for category in 카페 음식점 편의점 미용실; do
    code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/analyze" \
      -H "Content-Type: application/json" \
      -d "{\"region_id\":\"$code_id\",\"category\":\"$category\"}")
    check "/api/analyze ($name, $category)" 200 "$code"
  done
done

code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/analyze" \
  -H "Content-Type: application/json" \
  -d '{"region_id":"9999999999","category":"카페"}')
check "/api/analyze (invalid region_id -> 404)" 404 "$code"

if [ "$FAIL" -eq 0 ]; then
  echo "--- 전체 통과 ---"
else
  echo "--- 실패 있음 ---"
  exit 1
fi
