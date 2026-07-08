import { useEffect, useRef, useState } from "react"
import DongMap from "./components/DongMap"
import AnalysisPanel from "./components/AnalysisPanel"
import RegionDetailModal from "./components/RegionDetailModal"
import QueryBar from "./components/QueryBar"
import { fetchBulkScores, fetchRegions, fetchReport, parseQuery } from "./api"
import { matchesRegionQuery } from "./regionAliases"
import "./App.css"

const CATEGORIES = ["카페", "음식점", "편의점", "미용실"]
const TOP_N = 3

function App() {
  const [category, setCategory] = useState(CATEGORIES[0])
  const [searchQuery, setSearchQuery] = useState("")
  const [regions, setRegions] = useState([]) // 검색 필터링용 행정동 목록(region_id -> 이름)
  const [analysis, setAnalysis] = useState({ status: "idle" })
  const [modal, setModal] = useState({ open: false })
  const [nlQuery, setNlQuery] = useState({ status: "idle" })
  // modal과 분리해서 따로 든다 — onClose가 modal을 {open:false}로 통째로 갈아치우기 때문에,
  // modal 안에 두면 팝업을 닫는 순간 대안 정보가 같이 사라져서 지도에 계속 못 보여준다.
  const [mapConnections, setMapConnections] = useState(null)
  const skipNextResetRef = useRef(false) // 자연어 질의가 업종을 바꿀 때, 아래 idle 리셋 이펙트가 로딩 상태를 덮어쓰지 않도록

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
    if (skipNextResetRef.current) {
      skipNextResetRef.current = false
      return
    }
    setAnalysis({ status: "idle" })
    setMapConnections(null) // 업종이 바뀌면 이전 업종 기준 대안도 더 이상 유효하지 않음
  }, [category])

  async function handleAnalyze(overrideCategory, overrideSearchQuery) {
    const effectiveCategory = overrideCategory ?? category
    const effectiveSearch = overrideSearchQuery ?? searchQuery

    setAnalysis({ status: "loading" })
    try {
      const bulk = await fetchBulkScores(effectiveCategory)
      let candidates = bulk.scores

      const query = effectiveSearch.trim()
      if (query) {
        const nameById = new Map(regions.map((r) => [r.region_id, r.행정동명]))
        candidates = candidates.filter((c) => {
          const name = nameById.get(c.region_id)
          return name ? matchesRegionQuery(name, query) : false
        })
        if (candidates.length === 0) {
          setAnalysis({ status: "error", error: `"${query}"와 일치하는 지역이 없습니다.` })
          return
        }
      }

      const topRegionIds = [...candidates]
        .sort((a, b) => b.total_score - a.total_score)
        .slice(0, TOP_N)
        .map((c) => c.region_id)

      const report = await fetchReport(topRegionIds, effectiveCategory)
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

  async function handleNaturalLanguageQuery(text) {
    setNlQuery({ status: "loading" })
    try {
      const parsed = await parseQuery(text)

      // 파악한 만큼은 항상 반영한다 — 모호하거나 실패해도 기존 드롭다운/검색으로
      // 이어서 쓸 수 있도록 부분 결과를 그대로 채워준다.
      if (parsed.category && parsed.category !== category) {
        skipNextResetRef.current = true
        setCategory(parsed.category)
      }
      if (parsed.region_matches.length === 1) {
        setSearchQuery(parsed.region_matches[0].행정동명)
      }

      if (parsed.needs_clarification) {
        setNlQuery({ status: "clarification", message: parsed.message })
        return
      }

      setNlQuery({ status: "success", message: parsed.message })
      await handleAnalyze(parsed.category, parsed.region_matches[0].행정동명)
    } catch (err) {
      setNlQuery({ status: "error", message: err.message })
    }
  }

  async function openRegionDetail(regionId, regionName) {
    setModal({ open: true, status: "loading", regionId, regionName })
    try {
      const report = await fetchReport([regionId], category)
      const candidate = report.candidates[0]
      setModal({
        open: true,
        status: "success",
        regionId,
        regionName,
        candidate,
        reportText: report.report_text,
        isFallback: report.is_fallback,
      })
      // 대안이 있으면(팝업을 닫아도) 지도에 연결선을 계속 보여준다 — 사용자가 팝업을
      // 닫고 지도에서 대안 위치를 직접 둘러볼 수 있게. 없으면(고득점) 이전에 다른
      // 지역을 보다가 남아있던 연결선도 지운다.
      setMapConnections(
        candidate.alternatives.length > 0 ? { origin: candidate.region, alternatives: candidate.alternatives } : null
      )
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
            onClick={() => handleAnalyze()}
            disabled={analysis.status === "loading"}
          >
            {analysis.status === "loading" ? "분석 중…" : "분석하기"}
          </button>
        </div>
      </header>

      <QueryBar nlQuery={nlQuery} onSubmit={handleNaturalLanguageQuery} />

      <main className="main-layout">
        <section className="map-area">
          <DongMap
            category={category}
            onRegionClick={openRegionDetail}
            highlightRegionIds={analysis.highlightRegionIds}
            connections={mapConnections}
          />
        </section>

        <aside className="side-panel">
          <AnalysisPanel analysis={analysis} onCardClick={(regionId) => openRegionDetail(regionId)} />
        </aside>
      </main>

      <RegionDetailModal
        modal={modal}
        category={category}
        onClose={() => setModal({ open: false })}
        onAlternativeClick={(regionId) => openRegionDetail(regionId)}
      />
    </div>
  )
}

export default App
