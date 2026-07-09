import { useEffect, useState } from "react"
import { fetchGridCellReport } from "../api"
import { scoreToColor } from "../colorScale"
import "./RegionDetailModal.css"

const BREAKDOWN_LABELS = [
  { key: "배후수요", label: "배후수요" },
  { key: "경쟁강도", label: "경쟁강도" },
  { key: "수익성", label: "수익성" },
]

// 행정동 상세(RegionDetailModal)와 같은 자리(사이드 패널)에 끼워지는, 격자 셀
// 전용 패널. Track A는 일부러 안 넣는다(행정동 단위로 학습된 모델이라 격자에는
// 안 맞음, 설계 확정 시 합의). AI 해설은 게이지/바차트처럼 자동으로는 안 만들고
// "AI 해설 보기"를 눌렀을 때만 요청한다 — 격자가 행정동 하나에 최대 100개
// 안팎이라 자동 호출이면 Gemini 무료 티어 일일 한도를 금방 써버린다.
function GridCellDetailPanel({ cellDetail, regionId, category, onBack, onClose, onAlternativeClick }) {
  return (
    <div className="region-detail-panel">
      <button className="modal-close" onClick={onClose} aria-label="닫기">
        ✕
      </button>

      {cellDetail.status === "loading" && (
        <div className="panel-loading modal-loading">
          <span className="spinner" aria-hidden="true" />셀 분석 중입니다…
        </div>
      )}

      {cellDetail.status === "error" && (
        <div className="panel-error">
          <strong>격자 상세 정보를 불러오지 못했습니다.</strong>
          <p>{cellDetail.error}</p>
        </div>
      )}

      {cellDetail.status === "success" && (
        <GridCellDetailContent
          detail={cellDetail.detail}
          regionId={regionId}
          category={category}
          onBack={onBack}
          onAlternativeClick={onAlternativeClick}
        />
      )}
    </div>
  )
}

function GridCellDetailContent({ detail, regionId, category, onBack, onAlternativeClick }) {
  const [report, setReport] = useState({ status: "idle" })

  // 다른 셀을 열면(대안 카드 클릭 등) 이전 셀의 AI 해설이 그대로 보이면 안 되니 초기화
  useEffect(() => {
    setReport({ status: "idle" })
  }, [detail.cell_id])

  async function handleShowReport() {
    setReport({ status: "loading" })
    try {
      const result = await fetchGridCellReport(regionId, category, detail.cell_id)
      setReport({ status: "success", reportText: result.report_text, isFallback: result.is_fallback })
    } catch (err) {
      setReport({ status: "error", error: err.message })
    }
  }

  return (
    <>
      <button className="grid-back-button" onClick={onBack}>
        ← 행정동 전체로
      </button>

      <h2 className="modal-title">{detail.label}</h2>
      <p className="grid-relative-note">이 점수는 부산 전체 기준이 아니라, 같은 행정동 안 격자들끼리의 상대 비교입니다.</p>

      <div className="gauge-row">
        <div className="gauge" style={{ "--gauge-color": scoreToColor(detail.total_score) }}>
          <span className="gauge-value">{detail.total_score}</span>
          <span className="gauge-max">/100</span>
        </div>
        <p className="gauge-caption">행정동 내 상대 점수</p>
      </div>

      <h3 className="modal-subheading">세부 지표</h3>
      <div className="breakdown-bars">
        {BREAKDOWN_LABELS.map(({ key, label }) => {
          const value = detail.breakdown[key]
          return (
            <div className="breakdown-row" key={key}>
              <span className="breakdown-label">{label}</span>
              <div className="breakdown-track">
                <div
                  className="breakdown-fill"
                  style={{ width: `${value ?? 0}%`, background: scoreToColor(value ?? 0) }}
                />
              </div>
              <span className="breakdown-value">{value ?? "데이터 없음"}</span>
            </div>
          )
        })}
        <div className="breakdown-row">
          <span className="breakdown-label">접근성</span>
          <div className="breakdown-track breakdown-track-empty" />
          <span className="breakdown-value breakdown-value-muted">데이터 없음</span>
        </div>
      </div>

      <p className="grid-competitor-info">
        동일업종 경쟁업체 <strong>{detail.competitor_count}개</strong>
        {detail.closure_available ? (
          <>
            {" "}
            · 최근 1년 폐업률 <strong>{detail.closure_rate}%</strong>
          </>
        ) : (
          ` · 폐업률 데이터 부족(표본 ${detail.closure_sample}건)으로 밀집도만 반영`
        )}
      </p>

      {detail.rent_count > 0 && (
        <div className="listings-section">
          <h3 className="modal-subheading">
            매물 정보 <span className="listings-count-badge">{detail.rent_count}건</span>
          </h3>
          {(detail.avg_deposit != null || detail.avg_rent_per_pyeong != null) && (
            <p className="listings-avg-note">
              평균 보증금 {detail.avg_deposit?.toLocaleString()}만원 · 평당 월세{" "}
              {detail.avg_rent_per_pyeong?.toLocaleString()}만원
            </p>
          )}
          <ListingsList listings={detail.listings} />
        </div>
      )}

      {detail.alternatives?.length > 0 && (
        <div className="low-score-section">
          <div className="low-score-tab-panel">
            <p className="alternatives-caption">
              <span className="alternatives-criteria-badge">같은 행정동 · 점수 높은 순</span> 이 격자보다 점수가 더
              높은 인근 격자입니다.
            </p>
            <ul className="alternatives-list">
              {detail.alternatives.map((alt) => (
                <li key={alt.region.region_id}>
                  <button
                    className="alternative-card"
                    onClick={() => onAlternativeClick(alt.region.region_id.slice(alt.region.region_id.indexOf("_") + 1))}
                  >
                    <span className="alternative-name">{alt.region.행정동명.match(/격자 [^)]+/)?.[0] ?? alt.region.행정동명}</span>
                    <span className="alternative-distance">{alt.distance_km}km</span>
                    <span className="alternative-score" style={{ color: scoreToColor(alt.score) }}>
                      {alt.score}점
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      <h3 className="modal-subheading">AI 해설</h3>
      {report.status === "idle" && (
        <button className="grid-ai-report-button" onClick={handleShowReport}>
          AI 해설 보기
        </button>
      )}
      {report.status === "loading" && (
        <div className="panel-loading">
          <span className="spinner" aria-hidden="true" />해설 생성 중입니다…
        </div>
      )}
      {report.status === "error" && (
        <div className="panel-error">
          <strong>AI 해설을 불러오지 못했습니다.</strong>
          <p>{report.error}</p>
        </div>
      )}
      {report.status === "success" && (
        <>
          {report.isFallback && (
            <p className="report-fallback-notice">AI 리포트 생성에 실패해 점수 기반 기본 요약을 표시합니다.</p>
          )}
          <p className="report-text">{report.reportText}</p>
        </>
      )}
    </>
  )
}

function ListingsList({ listings }) {
  const [expanded, setExpanded] = useState(false)
  if (!listings || listings.length === 0) {
    return <p className="placeholder-text">매물 정보가 없습니다.</p>
  }
  const visible = expanded ? listings : listings.slice(0, 8)
  return (
    <>
      <ul className="listings-list">
        {visible.map((item, idx) => (
          <li className="listing-card" key={idx}>
            <div className="listing-card-top">
              <span className="listing-name">{item.name}</span>
              <span className="listing-floor">{item.floor}층</span>
            </div>
            <div className="listing-card-bottom">
              <span className="listing-price">
                {item.deposit.toLocaleString()}/{item.rent.toLocaleString()}
              </span>
              <span className="listing-area">{item.area_m2 > 0 ? `${item.area_m2}m²` : "면적 미상"}</span>
              {item.rent_per_pyeong > 0 && <span className="listing-per-pyeong">평당 {item.rent_per_pyeong}만</span>}
            </div>
          </li>
        ))}
      </ul>
      {listings.length > 8 && (
        <button className="listings-toggle" onClick={() => setExpanded((v) => !v)}>
          {expanded ? "접기" : `매물 ${listings.length - 8}건 더보기`}
        </button>
      )}
    </>
  )
}

export default GridCellDetailPanel
