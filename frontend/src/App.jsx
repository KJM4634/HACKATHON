import { useEffect, useState } from "react"
import DongMap from "./components/DongMap"
import AnalysisPanel from "./components/AnalysisPanel"
import RegionDetailModal from "./components/RegionDetailModal"
import { fetchBulkScores, fetchRegions, fetchReport } from "./api"
import "./App.css"

const CATEGORIES = ["카페", "음식점", "편의점", "미용실"]
const TOP_N = 3

function App() {
  const [category, setCategory] = useState(CATEGORIES[0])
  const [searchQuery, setSearchQuery] = useState("")
  const [regions, setRegions] = useState([]) // 검색 필터링용 행정동 목록(region_id -> 이름)
  const [analysis, setAnalysis] = useState({ status: "idle" })
  const [modal, setModal] = useState({ open: false })

  useEffect(() => {
    let cancelled = false
    fetchRegions()
      .then((data) => !cancelled && setRegions(data))
      .catch(() => !cancelled && setRegions([])) // 검색은 안 되더라도 나머지 기능은 그대로 동작해야 함
    return () => {
      cancelled = true
    }
  }, [])

  // 업종이 바뀌면 이전 업종 기준 분석 결과는 더 이상 유효하지 않으므로 비운다
  useEffect(() => {
    setAnalysis({ status: "idle" })
  }, [category])

  async function handleAnalyze() {
    setAnalysis({ status: "loading" })
    try {
      const bulk = await fetchBulkScores(category)
      let candidates = bulk.scores

      const query = searchQuery.trim()
      if (query) {
        const nameById = new Map(regions.map((r) => [r.region_id, r.행정동명]))
        candidates = candidates.filter((c) => nameById.get(c.region_id)?.includes(query))
        if (candidates.length === 0) {
          setAnalysis({ status: "error", error: `"${query}"와 일치하는 지역이 없습니다.` })
          return
        }
      }

      const topRegionIds = [...candidates]
        .sort((a, b) => b.total_score - a.total_score)
        .slice(0, TOP_N)
        .map((c) => c.region_id)

      const report = await fetchReport(topRegionIds, category)
      setAnalysis({
        status: "success",
        top3: report.candidates,
        reportText: report.report_text,
        isFallback: report.is_fallback,
        highlightRegionIds: topRegionIds,
      })
    } catch (err) {
      setAnalysis({ status: "error", error: err.message })
    }
  }

  async function openRegionDetail(regionId, regionName) {
    setModal({ open: true, status: "loading", regionId, regionName })
    try {
      const report = await fetchReport([regionId], category)
      setModal({
        open: true,
        status: "success",
        regionId,
        regionName,
        candidate: report.candidates[0],
        reportText: report.report_text,
        isFallback: report.is_fallback,
      })
    } catch (err) {
      setModal({ open: true, status: "error", regionId, regionName, error: err.message })
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <span className="logo">여기차려</span>
        <div className="topbar-controls">
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <input
            type="text"
            placeholder="지역 검색 (예: 서면)"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAnalyze()}
          />
          <button
            className="analyze-button"
            onClick={handleAnalyze}
            disabled={analysis.status === "loading"}
          >
            {analysis.status === "loading" ? "분석 중…" : "분석하기"}
          </button>
        </div>
      </header>

      <main className="main-layout">
        <section className="map-area">
          <DongMap
            category={category}
            onRegionClick={openRegionDetail}
            highlightRegionIds={analysis.highlightRegionIds}
          />
        </section>

        <aside className="side-panel">
          <AnalysisPanel analysis={analysis} onCardClick={(regionId) => openRegionDetail(regionId)} />
        </aside>
      </main>

      <RegionDetailModal modal={modal} category={category} onClose={() => setModal({ open: false })} />
    </div>
  )
}

export default App
