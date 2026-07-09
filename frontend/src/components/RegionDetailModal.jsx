import { useState } from "react"
import { scoreToColor } from "../colorScale"
import { useCountUp } from "../useCountUp"
import "./RegionDetailModal.css"

const BREAKDOWN_LABELS = [
  { key: "배후수요", label: "배후수요" },
  { key: "경쟁강도", label: "경쟁강도" },
  { key: "수익성", label: "수익성" },
]

const WEAK_THRESHOLD = 50 // 세부점수가 이보다 낮으면 "이 지표가 약하다"로 설명

// 데스크톱/태블릿에서는 AnalysisPanel과 같은 자리(우측 사이드 패널)에 그대로
// 끼워 넣는 일반 패널이고, 모바일 너비에서만 CSS 미디어쿼리로 전체화면
// 오버레이가 된다(RegionDetailModal.css의 .region-detail-panel 참고) — 지도를
// 가리지 않으면서 대안 위치를 지도와 동시에 볼 수 있어야 한다는 요구사항 때문.
function RegionDetailModal({ modal, category, onClose, onAlternativeClick }) {
  if (!modal.open) return null

  return (
    <div className="region-detail-panel">
      <button className="modal-close" onClick={onClose} aria-label="닫기">
        ✕
      </button>

      {modal.status === "loading" && (
        <div className="panel-loading modal-loading">
          <span className="spinner" aria-hidden="true" />
          {modal.regionName ?? "지역"} 분석 중입니다…
        </div>
      )}

      {modal.status === "error" && (
        <div className="panel-error">
          <strong>상세 정보를 불러오지 못했습니다.</strong>
          <p>{modal.error}</p>
        </div>
      )}

      {modal.status === "success" && (
        <RegionDetailContent
          candidate={modal.candidate}
          reportText={modal.reportText}
          isFallback={modal.isFallback}
          category={category}
          onAlternativeClick={onAlternativeClick}
        />
      )}
    </div>
  )
}

function RegionDetailContent({ candidate, reportText, isFallback, category, onAlternativeClick }) {
  const { score, region, alternatives } = candidate
  const trackA = score.track_a
  const [lowScoreTab, setLowScoreTab] = useState("alternatives")
  const animatedScore = useCountUp(score.total_score)

  return (
    <>
      <h2 className="modal-title">{region.행정동명}</h2>

      <div className="gauge-row">
        <div className="gauge" style={{ "--gauge-color": scoreToColor(score.total_score) }}>
          <span className="gauge-value">{animatedScore}</span>
          <span className="gauge-max">/100</span>
        </div>
        <p className="gauge-caption">종합 생존 가능성 점수</p>
      </div>

      <h3 className="modal-subheading">세부 지표</h3>
      <div className="breakdown-bars">
        {BREAKDOWN_LABELS.map(({ key, label }) => {
          const value = score.breakdown[key]
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

      {alternatives?.length > 0 && (
        <div className="low-score-section">
          <div className="low-score-tabs" role="tablist">
            <button
              role="tab"
              aria-selected={lowScoreTab === "alternatives"}
              className={`low-score-tab ${lowScoreTab === "alternatives" ? "low-score-tab-active" : ""}`}
              onClick={() => setLowScoreTab("alternatives")}
            >
              대안 추천
            </button>
            <button
              role="tab"
              aria-selected={lowScoreTab === "strategy"}
              className={`low-score-tab ${lowScoreTab === "strategy" ? "low-score-tab-active" : ""}`}
              onClick={() => setLowScoreTab("strategy")}
            >
              이곳에서 성공하려면
            </button>
          </div>

          {lowScoreTab === "alternatives" && (
            <div className="low-score-tab-panel">
              <p className="alternatives-caption">
                <span className="alternatives-criteria-badge">3km 이내 · 점수 높은 순</span> 총점{" "}
                {score.total_score}점은 낮은 편이라, 같은 업종 기준 3km 이내에서 점수가 더 높은 지역을
                찾아봤습니다.
              </p>
              <ul className="alternatives-list">
                {alternatives.map((alt) => (
                  <li key={alt.region.region_id}>
                    <button className="alternative-card" onClick={() => onAlternativeClick(alt.region.region_id)}>
                      <span className="alternative-name">{alt.region.행정동명}</span>
                      <span className="alternative-distance">{alt.distance_km}km</span>
                      <span className="alternative-score" style={{ color: scoreToColor(alt.score) }}>
                        {alt.score}점
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {lowScoreTab === "strategy" && <SuccessStrategyPanel candidate={candidate} category={category} />}
        </div>
      )}

      <h3 className="modal-subheading">AI 해설</h3>
      {isFallback && (
        <p className="report-fallback-notice">AI 리포트 생성에 실패해 점수 기반 기본 요약을 표시합니다.</p>
      )}
      <p className="report-text">{reportText}</p>

      {category === "한식" && trackA?.available && (
        <details className="track-a-section">
          <summary>실험적 예측 모델 (참고용)</summary>
          <div className="track-a-body">
            <p className="track-a-disclaimer">
              행정동 단위 집계 데이터만으로 학습해 아직 신뢰도가 낮은 실험적 지표입니다. 메인
              점수(위 종합 점수)와는 독립적으로 참고만 하세요.
            </p>
            <p className="track-a-metric">
              3년 내 폐업 확률 예측: <strong>{Math.round(trackA.closure_risk_3yr * 100)}%</strong>
            </p>
            <p className="track-a-model">모델: {trackA.model_name}</p>
          </div>
        </details>
      )}
    </>
  )
}

// 점수가 낮아도 "그래도 여기서 하고 싶다"는 사용자를 위한 탭. 세부지표/경쟁현황은
// 이미 받은 데이터로 바로 계산하고(추가 요청 없음), 차별화 전략만 백엔드가 미리
// 생성해둔 candidate.differentiation_strategy를 그대로 보여준다.
function SuccessStrategyPanel({ candidate, category }) {
  const { score, market_data: marketData, differentiation_strategy: strategy } = candidate
  const reasons = buildWeaknessReasons(score.breakdown, marketData, category)

  return (
    <div className="low-score-tab-panel">
      <div className="strategy-block">
        <h4 className="strategy-block-title">왜 이 지역이 어려운지</h4>
        <ul className="strategy-reasons">
          {reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      </div>

      <div className="strategy-block">
        <h4 className="strategy-block-title">이미 있는 경쟁 가게 현황</h4>
        <p className="strategy-competitor-info">
          동일업종({category}) 경쟁업체 <strong>{marketData.competitors.total_count}개</strong>
          {marketData.closure_stats.data_available ? (
            <>
              {" "}
              · 최근 1년 폐업률 <strong>{marketData.closure_stats.폐업률}%</strong>
            </>
          ) : (
            " · 이 업종은 폐업 이력 데이터가 없어 폐업률은 확인할 수 없습니다"
          )}
        </p>
      </div>

      <div className="strategy-block">
        <h4 className="strategy-block-title">
          차별화 전략 제안 <span className="strategy-disclaimer-badge">참고용 제안</span>
        </h4>
        {strategy ? (
          <p className="strategy-text">{strategy}</p>
        ) : (
          <p className="strategy-unavailable">전략 제안을 생성하지 못했어요. 잠시 후 다시 열어보세요.</p>
        )}
      </div>
    </div>
  )
}

function buildWeaknessReasons(breakdown, marketData, category) {
  const reasons = []
  if (breakdown.경쟁강도 !== null && breakdown.경쟁강도 < WEAK_THRESHOLD) {
    reasons.push(
      `${category} ${marketData.competitors.total_count}개로 경쟁 밀집도가 높은 편입니다 (경쟁강도 ${breakdown.경쟁강도}점)`
    )
  }
  if (breakdown.수익성 !== null && breakdown.수익성 < WEAK_THRESHOLD) {
    reasons.push(`인근 매출 규모가 상대적으로 작은 편입니다 (수익성 ${breakdown.수익성}점)`)
  }
  if (breakdown.배후수요 !== null && breakdown.배후수요 < WEAK_THRESHOLD) {
    reasons.push(`유동인구·배후인구가 상대적으로 적은 편입니다 (배후수요 ${breakdown.배후수요}점)`)
  }
  if (reasons.length === 0) {
    reasons.push("세부 지표가 골고루 평이한 수준이라, 특별히 두드러지게 약한 지표는 없습니다.")
  }
  return reasons
}

export default RegionDetailModal
