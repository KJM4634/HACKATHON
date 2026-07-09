import { useState } from "react"
import "./QueryBar.css"

function QueryBar({ nlQuery, onSubmit, onCandidateClick }) {
  const [text, setText] = useState("")

  function submit() {
    if (!text.trim() || nlQuery.status === "loading") return
    onSubmit(text.trim())
  }

  return (
    <div className="query-bar">
      <input
        type="text"
        className="query-bar-input"
        placeholder="자연어로 물어보세요 (예: 서면에 커피숍 차릴 건데 어디가 좋아?)"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
      />
      <button className="query-bar-button" onClick={submit} disabled={nlQuery.status === "loading"}>
        {nlQuery.status === "loading" ? "분석 중…" : "질문하기"}
      </button>

      {nlQuery.status === "clarification" && (
        <div className="query-bar-notice query-bar-notice-clarify">
          {nlQuery.message}
          {nlQuery.candidates?.length >= 2 && (
            <div className="query-bar-candidates">
              {nlQuery.candidates.map((c) => (
                <button
                  key={c.region_id}
                  type="button"
                  className="query-bar-candidate-chip"
                  onClick={() => onCandidateClick(c.region_id, c.행정동명, nlQuery.category)}
                >
                  {c.행정동명}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      {nlQuery.status === "success" && (
        <div className="query-bar-notice query-bar-notice-success">{nlQuery.message}</div>
      )}
      {nlQuery.status === "error" && (
        <div className="query-bar-notice query-bar-notice-error">{nlQuery.message}</div>
      )}
    </div>
  )
}

export default QueryBar
