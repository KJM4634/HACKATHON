import { useState } from "react"
import DongMap from "./components/DongMap"
import "./App.css"

const CATEGORIES = ["카페", "음식점", "편의점", "미용실"]

function App() {
  const [category, setCategory] = useState(CATEGORIES[0])

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
          <input type="text" placeholder="지역 검색 (예: 서면)" disabled />
        </div>
      </header>

      <main className="main-layout">
        <section className="map-area">
          <DongMap category={category} />
        </section>

        <aside className="side-panel">
          <h2>추천 입지 TOP 3</h2>
          <p className="placeholder-text">분석 실행 전입니다.</p>

          <h2>AI 분석 리포트</h2>
          <p className="placeholder-text">
            지도에서 행정동을 클릭하면 콘솔에 점수가 출력됩니다. 리포트 UI는 다음 단계에서
            연결됩니다.
          </p>
        </aside>
      </main>
    </div>
  )
}

export default App
