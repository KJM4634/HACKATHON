import { scoreToColor } from "../colorScale"
import "./RegionDetailModal.css"

const BREAKDOWN_LABELS = [
  { key: "배후수요", label: "배후수요" },
  { key: "경쟁강도", label: "경쟁강도" },
  { key: "수익성", label: "수익성" },
]

// 행정동 상세(RegionDetailModal)와 같은 자리(사이드 패널)에 끼워지는, 격자 셀
// 전용 패널. AI 해설과 Track A는 일부러 안 넣는다 — Track A는 행정동 단위로
// 학습된 모델이라 격자에는 안 맞고(설계 확정 시 합의), AI 해설은 셀 클릭마다
// Gemini를 부르면 무료 티어 쿼터를 너무 빨리 쓰게 되어 숫자 기반 정보만 보여준다.
function GridCellDetailPanel({ cellDetail, onBack, onClose, onAlternativeClick }) {
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
        <GridCellDetailContent detail={cellDetail.detail} onBack={onBack} onAlternativeClick={onAlternativeClick} />
      )}
    </div>
  )
}

function GridCellDetailContent({ detail, onBack, onAlternativeClick }) {
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
    </>
  )
}

export default GridCellDetailPanel
