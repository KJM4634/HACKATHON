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

for region in seomyeon nampo haeundae gwangalli; do
  for category in 카페 음식점 편의점 미용실; do
    code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/analyze" \
      -H "Content-Type: application/json" \
      -d "{\"region_id\":\"$region\",\"category\":\"$category\"}")
    check "/api/analyze ($region, $category)" 200 "$code"
  done
done

code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/analyze" \
  -H "Content-Type: application/json" \
  -d '{"region_id":"seoul","category":"카페"}')
check "/api/analyze (invalid region_id -> 404)" 404 "$code"

if [ "$FAIL" -eq 0 ]; then
  echo "--- 전체 통과 ---"
else
  echo "--- 실패 있음 ---"
  exit 1
fi
