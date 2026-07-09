import { scoreToColor } from "../colorScale"
import "./RegionDetailModal.css"
import "./AnalysisPanel.css"

function AnalysisPanel({ analysis, onCardClick }) {
  if (analysis.status === "idle") {
    return (
      <>
        <h2>추천 입지 TOP 3</h2>
        <p className="placeholder-text">분석 실행 전입니다.</p>

        <h2>AI 분석 리포트</h2>
        <p className="placeholder-text">
          업종을 고르고 [분석하기]를 누르면 상위 후보 지역과 AI 리포트가 여기 표시됩니다.
        </p>
      </>
    )
  }

  if (analysis.status === "loading") {
    return (
      <div className="panel-loading">
        <span className="spinner" aria-hidden="true" />
        분석 중입니다… (지역 점수 계산 + AI 리포트 생성)
      </div>
    )
  }

  if (analysis.status === "error") {
    return (
      <div className="panel-error">
        <strong>분석에 실패했습니다.</strong>
        <p>{analysis.error}</p>
      </div>
    )
  }

  const { top3, reportText, isFallback } = analysis

  // 예산이 신뢰도 범위 밖(30만~1,000만원 밖)이면 모든 후보가 같은 사유로 같은
  // 경고를 받으므로, 카드마다 반복하지 않고 위에 한 번만 보여준다(RegionDetailModal의
  // 대안 카드 처리와 같은 원칙).
  const unreliableBudgetFit = top3.find((c) => c.budget_fit?.is_unreliable)?.budget_fit

  return (
    <>
      <h2>추천 입지 TOP {top3.length}</h2>

      {unreliableBudgetFit && (
        <p className="budget-fit-note budget-fit-note-warning">
          예산 {Math.round(unreliableBudgetFit.monthly_budget_krw / 10_000)}만원 · {unreliableBudgetFit.label}
        </p>
      )}

      <ol className="top3-list">
        {top3.map((candidate, i) => (
          <li key={candidate.region.region_id}>
            <button className="top3-card" onClick={() => onCardClick(candidate.region.region_id)}>
              <span className="top3-rank">{i + 1}</span>
              <span className="top3-name">
                {candidate.region.행정동명}
                {candidate.alternatives?.length > 0 && (
                  <span className="top3-alt-badge" title="인근에 더 나은 대안이 있어요">
                    ⚠ 대안 {candidate.alternatives.length}곳
                  </span>
                )}
              </span>
              <span className="top3-score" style={{ color: scoreToColor(candidate.score.total_score) }}>
                {candidate.score.total_score}점
              </span>
            </button>
            {candidate.budget_fit && !candidate.budget_fit.is_unreliable && (
              <p className="budget-fit-note budget-fit-note-inline">{candidate.budget_fit.label}</p>
            )}
          </li>
        ))}
      </ol>

      <h2>AI 분석 리포트</h2>
      {isFallback && (
        <p className="report-fallback-notice">
          AI 리포트 생성에 실패해 점수 기반 기본 요약을 표시합니다.
        </p>
      )}
      <p className="report-text">{reportText}</p>
    </>
  )
}

export default AnalysisPanel
