import { scoreToColor } from "../colorScale"
import "./RegionDetailModal.css"

const BREAKDOWN_LABELS = [
  { key: "배후수요", label: "배후수요" },
  { key: "경쟁강도", label: "경쟁강도" },
  { key: "수익성", label: "수익성" },
]

function RegionDetailModal({ modal, category, onClose, onAlternativeClick }) {
  if (!modal.open) return null

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
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
    </div>
  )
}

function RegionDetailContent({ candidate, reportText, isFallback, category, onAlternativeClick }) {
  const { score, region, alternatives } = candidate
  const trackA = score.track_a

  return (
    <>
      <h2 className="modal-title">{region.행정동명}</h2>

      <div className="gauge-row">
        <div className="gauge" style={{ "--gauge-color": scoreToColor(score.total_score) }}>
          <span className="gauge-value">{score.total_score}</span>
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
        <div className="alternatives-section">
          <h3 className="modal-subheading">이 지역보다 나은 인근 대안</h3>
          <p className="alternatives-caption">
            총점 {score.total_score}점은 낮은 편이라, 같은 업종 기준 3km 이내에서 점수가 더 높은 지역을 찾아봤습니다.
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

      <h3 className="modal-subheading">AI 해설</h3>
      {isFallback && (
        <p className="report-fallback-notice">AI 리포트 생성에 실패해 점수 기반 기본 요약을 표시합니다.</p>
      )}
      <p className="report-text">{reportText}</p>

      {category === "음식점" && trackA?.available && (
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

export default RegionDetailModal
