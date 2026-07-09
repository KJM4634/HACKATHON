import { useEffect, useState } from "react"

// active가 delayMs보다 길게 true로 유지되면 true를 반환한다 — Gemini 호출이 가끔
// 몇 초~십수 초까지 걸릴 때, 정적인 "분석 중입니다" 문구만 떠 있으면 멈춘 것처럼
// 보이는 문제를 완화하려고 로딩 화면에 "시간이 더 걸릴 수 있다"는 안내를 늦게
// 덧붙이는 용도. active가 false->true로 바뀔 때마다(새 로딩 사이클마다) 타이머를
// 새로 건다 — 컴포넌트가 언마운트되지 않고 계속 재사용되는 화면(AnalysisPanel 등)
// 에서도 두 번째 요청부터 곧바로 "느림" 문구가 남아있지 않도록 함.
export function useDelayedFlag(active, delayMs) {
  const [flag, setFlag] = useState(false)

  useEffect(() => {
    if (!active) {
      setFlag(false)
      return undefined
    }
    setFlag(false)
    const id = window.setTimeout(() => setFlag(true), delayMs)
    return () => window.clearTimeout(id)
  }, [active, delayMs])

  return flag
}
