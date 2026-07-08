import { useEffect, useRef, useState } from "react"
import { Coffee, MapPin, Scissors, ShoppingBag, UtensilsCrossed } from "lucide-react"
import DongMap from "./components/DongMap"
import AnalysisPanel from "./components/AnalysisPanel"
import RegionDetailModal from "./components/RegionDetailModal"
import QueryBar from "./components/QueryBar"
import { fetchBulkScores, fetchRegions, fetchReport, parseQuery } from "./api"
import { matchesRegionQuery } from "./regionAliases"
import "./App.css"

const CATEGORIES = ["카페", "음식점", "편의점", "미용실"]
// 업종 문자열 자체는 백엔드/자연어 질의 파싱과 그대로 맞춰야 해서 바꾸지 않고,
// 렌더링에만 쓰는 아이콘을 별도 맵으로 둔다.
const CATEGORY_ICONS = { 카페: Coffee, 음식점: UtensilsCrossed, 편의점: ShoppingBag, 미용실: Scissors }
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
          setAnalysis({
            status: "error",
            error: `"${query}"와 일치하는 지역이 없습니다. 검색창은 공식 행정동명 위주로 찾으니, 위 자연어 질의창에 "${query}에 카페 차릴 건데 어디가 좋아?"처럼 문장으로 물어보세요.`,
          })
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

      // 지역이 정확히 1곳으로 특정됐으면 TOP-N 목록이 아니라 그 지역의 상세
      // 화면(게이지+바차트+대안비교+지도연결)으로 바로 들어간다 — 사용자가
      // 특정 지역을 콕 집어 물었는데 카드 하나만 달랑 뜨고 클릭을 한 번 더
      // 해야 하는 건 어색하다. 이미 점수가 높아 대안이 없으면 그 사실 자체가
      // 정답이라, 억지로 다른 지역을 끼워 넣지 않는다.
      setNlQuery({ status: "success", message: parsed.message })
      const match = parsed.region_matches[0]
      await openRegionDetail(match.region_id, match.행정동명, parsed.category)
    } catch (err) {
      setNlQuery({ status: "error", message: err.message })
    }
  }

  async function openRegionDetail(regionId, regionName, overrideCategory) {
    const effectiveCategory = overrideCategory ?? category
    setModal({ open: true, status: "loading", regionId, regionName })
    try {
      const report = await fetchReport([regionId], effectiveCategory)
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
        <span className="logo-group">
          <span className="logo-icon" aria-hidden="true">
            <MapPin size={15} strokeWidth={2.5} />
          </span>
          <span className="logo">여기차려</span>
        </span>
        <div className="topbar-controls">
          <div className="category-tabs" role="tablist" aria-label="업종 선택">
            {CATEGORIES.map((c) => {
              const Icon = CATEGORY_ICONS[c]
              const active = c === category
              return (
                <button
                  key={c}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  className={`category-tab ${active ? "category-tab-active" : ""}`}
                  onClick={() => setCategory(c)}
                >
                  <Icon size={15} strokeWidth={2.25} aria-hidden="true" />
                  {c}
                </button>
              )
            })}
          </div>
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
          {modal.open ? (
            <RegionDetailModal
              modal={modal}
              category={category}
              onClose={() => setModal({ open: false })}
              onAlternativeClick={(regionId) => openRegionDetail(regionId)}
            />
          ) : (
            <AnalysisPanel analysis={analysis} onCardClick={(regionId) => openRegionDetail(regionId)} />
          )}
        </aside>
      </main>

      <DataNoticeFooter />
    </div>
  )
}

// 리포트마다 반복되던 데이터 한계 문구(구 단위 인구 추정, 접근성 데이터 없음 등)를
// Gemini 프롬프트에서 빼고 여기 한 곳에 모아뒀다 — 개별 리포트는 그 지역만의
// 분석에 집중하고, 데이터 출처가 궁금한 사람만 펼쳐보면 된다.
function DataNoticeFooter() {
  return (
    <footer className="data-notice-footer">
      <details>
        <summary>본 서비스는 다음과 같은 데이터 특성을 참고하여 분석합니다</summary>
        <ul className="data-notice-list">
          <li>배후인구는 행정동 실측치가 아니라 소속 구 전체 인구를 그대로 적용한 추정치입니다 (인구세대현황이 시군구 단위까지만 존재).</li>
          <li>
            접근성(대중교통 정류장·집객시설 근접도) 데이터가 없어 점수 산출에서 제외했고, 나머지 세 지표(배후수요·경쟁강도·수익성)
            가중치를 원래 비율대로 재분배했습니다.
          </li>
          <li>카페·편의점·미용실 등 일부 업종은 폐업률을 계산할 표준 데이터가 없어, 경쟁강도는 동일업종 밀집도만으로 산정합니다.</li>
          <li>
            수익성 점수는 카페·음식점은 '음식/주점' 매출 버킷(카페+음식점+주점 통합)을, 편의점은 '유통' 매출 버킷(소매 전체)을
            근사값으로 사용합니다 — 업종별로 분리된 매출 데이터가 없습니다.
          </li>
        </ul>
      </details>
    </footer>
  )
}

export default App
