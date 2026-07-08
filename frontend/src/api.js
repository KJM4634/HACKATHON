export const API_BASE = "http://localhost:8000"

async function request(url, options, fallbackMessage) {
  let res
  try {
    res = await fetch(url, options)
  } catch {
    // fetch 자체가 던지는 실패(TypeError: Failed to fetch)는 서버 다운/CORS/네트워크
    // 단절 등을 뜻함 — 브라우저의 영문 원문 대신 사용자가 이해할 수 있는 문구로 바꾼다
    throw new Error(`${fallbackMessage}: 서버에 연결할 수 없습니다. 백엔드가 켜져 있는지 확인해주세요.`)
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail ? `${fallbackMessage}: ${body.detail}` : `${fallbackMessage} (HTTP ${res.status})`)
  }
  return res.json()
}

export function fetchBulkScores(category) {
  const url = `${API_BASE}/api/scores?${new URLSearchParams({ category })}`
  return request(url, undefined, "점수 조회 실패")
}

export function fetchAnalyze(regionId, category) {
  return request(
    `${API_BASE}/api/analyze`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ region_id: regionId, category }),
    },
    "분석 실패"
  )
}

export function fetchRegions() {
  return request(`${API_BASE}/api/regions`, undefined, "지역 목록 조회 실패")
}

export function fetchReport(regionIds, category) {
  return request(
    `${API_BASE}/api/report`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ region_ids: regionIds, category }),
    },
    "리포트 생성 실패"
  )
}

export function parseQuery(query) {
  return request(
    `${API_BASE}/api/parse-query`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    },
    "질의 분석 실패"
  )
}
