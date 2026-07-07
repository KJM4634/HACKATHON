import './App.css'

function App() {
  return (
    <div className="app-shell">
      <header className="topbar">
        <span className="logo">여기차려</span>
        <div className="topbar-controls">
          <select disabled>
            <option>업종 선택</option>
          </select>
          <input type="text" placeholder="지역 검색 (예: 서면)" disabled />
        </div>
      </header>

      <main className="main-layout">
        <section className="map-area">
          <div className="map-placeholder">지도 영역 (Kakao Map / Leaflet 연동 예정)</div>
        </section>

        <aside className="side-panel">
          <h2>추천 입지 TOP 3</h2>
          <p className="placeholder-text">분석 실행 전입니다.</p>

          <h2>AI 분석 리포트</h2>
          <p className="placeholder-text">지역과 업종을 선택하고 분석하기를 누르면 리포트가 표시됩니다.</p>
        </aside>
      </main>
    </div>
  )
}

export default App
