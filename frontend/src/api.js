export const API_BASE = "http://localhost:8000"

export async function fetchBulkScores(category) {
  const url = `${API_BASE}/api/scores?${new URLSearchParams({ category })}`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`점수 조회 실패: ${res.status}`)
  return res.json()
}

export async function fetchAnalyze(regionId, category) {
  const res = await fetch(`${API_BASE}/api/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ region_id: regionId, category }),
  })
  if (!res.ok) throw new Error(`분석 실패: ${res.status}`)
  return res.json()
}
