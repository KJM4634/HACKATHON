import { useEffect, useRef, useState } from "react"
import {
  Coffee,
  CookingPot,
  MapPin,
  MoreHorizontal,
  Sandwich,
  Scissors,
  ShoppingBag,
  Soup,
  UtensilsCrossed,
} from "lucide-react"
import DongMap from "./components/DongMap"
import AnalysisPanel from "./components/AnalysisPanel"
import RegionDetailModal from "./components/RegionDetailModal"
import GridCellDetailPanel from "./components/GridCellDetailPanel"
import QueryBar from "./components/QueryBar"
import { fetchBulkScores, fetchGrid, fetchGridCellDetail, fetchRegions, fetchReport, parseQuery } from "./api"
import { matchesRegionQuery } from "./regionAliases"
import "./App.css"

// "음식점"은 4개 리프 카테고리(한식/중식/분식/기타음식점)를 묶는 1차 탭일 뿐이고,
// 백엔드로 넘어가는 category 값은 항상 리프 값이다(카페/편의점/미용실과 동급) —
// 조사 결과 일식·양식은 표본이 얇아 "기타음식점"에 흡수했다.
const TOP_CATEGORIES = ["카페", "음식점", "편의점", "미용실"]
const FOOD_SUBCATEGORIES = ["한식", "중식", "분식", "기타음식점"]
const TOP_CATEGORY_ICONS = { 카페: Coffee, 음식점: UtensilsCrossed, 편의점: ShoppingBag, 미용실: Scissors }
const FOOD_SUBCATEGORY_ICONS = { 한식: Soup, 중식: CookingPot, 분식: Sandwich, 기타음식점: MoreHorizontal }
const TOP_N = 3

function App() {
  const [topCategory, setTopCategory] = useState(TOP_CATEGORIES[0])
  const [foodSubcategory, setFoodSubcategory] = useState(FOOD_SUBCATEGORIES[0])
  // 실제로 API에 넘기는 값은 항상 리프 카테고리 하나 — "음식점" 탭이 활성이면
  // 그 아래 서브탭 선택값을 쓰고, 아니면 최상위 탭 값 그대로 쓴다.
  const category = topCategory === "음식점" ? foodSubcategory : topCategory
  const [searchQuery, setSearchQuery] = useState("")
  const [regions, setRegions] = useState([]) // 검색 필터링용 행정동 목록(region_id -> 이름)
  const [analysis, setAnalysis] = useState({ status: "idle" })
  const [modal, setModal] = useState({ open: false })
  const [nlQuery, setNlQuery] = useState({ status: "idle" })
  // modal과 분리해서 따로 든다 — onClose가 modal을 {open:false}로 통째로 갈아치우기 때문에,
  // modal 안에 두면 팝업을 닫는 순간 대안 정보가 같이 사라져서 지도에 계속 못 보여준다.
  const [mapConnections, setMapConnections] = useState(null)
  // 행정동 상세를 열면 그 동을 격자로 잘라 지도에 확대해서 보여준다("격자 확대
  // 모드"). modal과 별도로 두는 이유는 위 mapConnections와 같다(닫기 동작이 서로
  // 다른 시점에 일어남 — 격자는 셀 상세를 보다가 "행정동 전체로" 눌러도 유지돼야 함).
  const [gridOverlay, setGridOverlay] = useState(null)
  const [gridCell, setGridCell] = useState({ open: false })
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
    setModal({ open: false }) // 열려있던 행정동 상세도 이전 업종 기준이라 같이 닫음
    setGridOverlay(null)
    setGridCell({ open: false })
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
      // 이어서 쓸 수 있도록 부분 결과를 그대로 채워준다. Gemini는 리프 카테고리
      // (한식/중식/분식/기타음식점 등)만 반환하므로, "음식점" 서브카테고리면 1차
      // 탭도 같이 "음식점"으로 맞춰야 상단 탭 표시가 실제 선택과 어긋나지 않는다.
      if (parsed.category && parsed.category !== category) {
        skipNextResetRef.current = true
        if (FOOD_SUBCATEGORIES.includes(parsed.category)) {
          setTopCategory("음식점")
          setFoodSubcategory(parsed.category)
        } else {
          setTopCategory(parsed.category)
        }
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
    setGridCell({ open: false }) // 다른 동을 열면 이전에 보던 셀 상세는 닫음

    const reportPromise = fetchReport([regionId], effectiveCategory)
      .then((report) => {
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
      })
      .catch((err) => setModal({ open: true, status: "error", regionId, regionName, error: err.message }))

    // 상세 리포트와 별개로(동시에) 그 동을 격자로 잘라 지도에 확대해서 보여준다.
    // 실패해도 상세 패널 자체는 살아있어야 하니 독립적으로 처리한다.
    setGridOverlay({ status: "loading", regionId, category: effectiveCategory })
    const gridPromise = fetchGrid(regionId, effectiveCategory)
      .then((grid) => setGridOverlay({ status: "success", regionId, category: effectiveCategory, ...grid }))
      .catch((err) => setGridOverlay({ status: "error", regionId, category: effectiveCategory, error: err.message }))

    await Promise.all([reportPromise, gridPromise])
  }

  async function openGridCell(cellId) {
    if (!gridOverlay || gridOverlay.status !== "success") return
    const { regionId, category: gridCategory } = gridOverlay
    setGridCell({ open: true, status: "loading", cellId })
    try {
      const detail = await fetchGridCellDetail(regionId, gridCategory, cellId)
      setGridCell({ open: true, status: "success", cellId, detail })
    } catch (err) {
      setGridCell({ open: true, status: "error", cellId, error: err.message })
    }
  }

  function exitGridMode() {
    setModal({ open: false })
    setGridOverlay(null)
    setGridCell({ open: false })
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
            {TOP_CATEGORIES.map((c) => {
              const Icon = TOP_CATEGORY_ICONS[c]
              const active = c === topCategory
              return (
                <button
                  key={c}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  className={`category-tab ${active ? "category-tab-active" : ""}`}
                  onClick={() => setTopCategory(c)}
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

      <div className={`subtab-strip ${topCategory === "음식점" ? "open" : ""}`}>
        <span className="subtab-lead">음식점 &gt;</span>
        <div className="subtabs" role="tablist" aria-label="음식점 서브카테고리 선택">
          {FOOD_SUBCATEGORIES.map((sub) => {
            const Icon = FOOD_SUBCATEGORY_ICONS[sub]
            const active = sub === foodSubcategory
            return (
              <button
                key={sub}
                type="button"
                role="tab"
                aria-selected={active}
                className={`subtab-btn ${active ? "subtab-btn-active" : ""}`}
                onClick={() => setFoodSubcategory(sub)}
              >
                <Icon size={13} strokeWidth={2.25} aria-hidden="true" />
                {sub}
              </button>
            )
          })}
        </div>
        <span className="subtab-note">
          수익성 점수는 4개 서브카테고리가 "외식업 통합 매출" 버킷을 공유합니다 (카페·음식점·주점 매출이 분리되어
          있지 않음)
        </span>
      </div>

      <QueryBar nlQuery={nlQuery} onSubmit={handleNaturalLanguageQuery} />

      <main className="main-layout">
        <section className="map-area">
          <DongMap
            category={category}
            onRegionClick={openRegionDetail}
            highlightRegionIds={analysis.highlightRegionIds}
            connections={mapConnections}
            gridOverlay={gridOverlay}
            onGridCellClick={openGridCell}
          />
        </section>

        <aside className="side-panel">
          {gridCell.open ? (
            <GridCellDetailPanel
              cellDetail={gridCell}
              regionId={gridOverlay?.regionId}
              category={gridOverlay?.category}
              onBack={() => setGridCell({ open: false })}
              onClose={exitGridMode}
              onAlternativeClick={(cellId) => openGridCell(cellId)}
            />
          ) : modal.open ? (
            <RegionDetailModal
              modal={modal}
              category={category}
              onClose={exitGridMode}
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
          <li>
            카페·편의점·미용실은 폐업률을 계산할 표준 데이터가 없고, 음식점 서브카테고리(한식/중식/분식/기타음식점)는 데이터는
            있지만 해당 지역의 표본이 5건 미만이면 신뢰할 수 없어 제외합니다 — 두 경우 모두 경쟁강도는 동일업종 밀집도만으로
            산정합니다.
          </li>
          <li>
            수익성 점수는 카페와 음식점 서브카테고리(한식/중식/분식/기타음식점) 5개 모두 '음식/주점' 매출 버킷(카페+음식점+주점
            통합)을, 편의점은 '유통' 매출 버킷(소매 전체)을 근사값으로 사용합니다 — 업종별로 분리된 매출 데이터가 없어 같은
            지역이면 5개 카테고리의 수익성 숫자가 동일합니다.
          </li>
          <li>
            행정동을 클릭하면 보이는 격자(100~1000m)는 인구·유동인구 데이터가 원래 행정동 단위뿐이라, 그 동의 상가업소
            분포로 다시 한 번 근사해 배분한 것입니다(구 단위→행정동→격자, 2단계 근사) — 그래서 격자 점수는 부산 전체
            기준이 아니라 같은 행정동 안에서의 상대 비교로만 봐주세요.
          </li>
        </ul>
      </details>
    </footer>
  )
}

export default App
