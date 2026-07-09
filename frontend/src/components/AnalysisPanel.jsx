import { useState } from "react"
import { scoreToColor } from "../colorScale"
import { SuccessStrategyPanel } from "./RegionDetailModal"
import "./RegionDetailModal.css"
import "./AnalysisPanel.css"

function AnalysisPanel({ analysis, onCardClick }) {
  // early return(idle/loading/error) 앞에 둬야 한다(Hooks 규칙) — 카드마다 별도
  // state를 두지 않고 "한 번에 하나만 펼침" 방식으로, RegionDetailModal의
  // lowScoreTab과 같은 단순함을 유지한다.
  const [expandedStrategyId, setExpandedStrategyId] = useState(null)

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
        {top3.map((candidate, i) => {
          const hasAlternatives = candidate.alternatives?.length > 0
          const isStrategyExpanded = expandedStrategyId === candidate.region.region_id
          return (
            <li key={candidate.region.region_id}>
              <button className="top3-card" onClick={() => onCardClick(candidate.region.region_id)}>
                <span className="top3-rank">{i + 1}</span>
                <span className="top3-name">
                  {candidate.region.행정동명}
                  {hasAlternatives && (
                    <span className="top3-alt-badge" title="인근에 더 나은 대안이 있어요">
                      ⚠ 대안 {candidate.alternatives.length}곳
                    </span>
                  )}
                </span>
                <span className="top3-score" style={{ color: scoreToColor(candidate.score.total_score) }}>
                  {candidate.score.total_score}점
                </span>
              </button>
              {candidate.trend?.data_available && (
                <p className="trend-note trend-note-inline">
                  {candidate.trend.dong_yoy_pct > candidate.trend.city_median_yoy_pct ? "▲" : "▽"} {candidate.trend.label}
                </p>
              )}
              {candidate.budget_fit && !candidate.budget_fit.is_unreliable && (
                <p className="budget-fit-note budget-fit-note-inline">{candidate.budget_fit.label}</p>
              )}
              {hasAlternatives && (
                <button
                  type="button"
                  className="top3-strategy-toggle"
                  onClick={() => setExpandedStrategyId(isStrategyExpanded ? null : candidate.region.region_id)}
                >
                  이곳에서 성공하려면 {isStrategyExpanded ? "▲" : "▼"}
                </button>
              )}
              {hasAlternatives && isStrategyExpanded && (
                <div className="low-score-section top3-strategy-panel">
                  <SuccessStrategyPanel candidate={candidate} category={candidate.category} />
                </div>
              )}
            </li>
          )
        })}
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
