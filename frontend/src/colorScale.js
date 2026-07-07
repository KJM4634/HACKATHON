// 0~100 점수 -> 색상. dataviz 스킬의 고정 status 팔레트(good/warning/serious/critical)를
// 4개 앵커로 그대로 이어붙여 연속 보간한다.
//
// 순수 빨강-초록 2색 다이버징은 쓰지 않았다: 적록색맹(deuteranopia/protanopia, 남성 약 8%)에게
// 두 끝이 거의 같은 색으로 보여 위험도가 구분되지 않기 때문. 대신 critical(빨강) ->
// serious(주황) -> warning(노랑) -> good(초록)으로 중간 색을 넣어, 색맹이어도 명도/채도
// 변화로 위치를 구분할 수 있게 했다. 결과적으로 "낮으면 빨강, 높으면 초록"이라는 원래
// 요청은 그대로 지키면서 접근성만 보강한 것.
const STOPS = [
  { score: 0, rgb: [208, 59, 59] }, // critical #d03b3b
  { score: 33, rgb: [236, 131, 90] }, // serious  #ec835a
  { score: 67, rgb: [250, 178, 25] }, // warning  #fab219
  { score: 100, rgb: [12, 163, 12] }, // good     #0ca30c
]

export const NO_DATA_COLOR = "#c3c2b7" // muted — 점수 없음

function lerp(a, b, t) {
  return a + (b - a) * t
}

export function scoreToColor(score) {
  const clamped = Math.max(0, Math.min(100, score))
  for (let i = 0; i < STOPS.length - 1; i++) {
    const lo = STOPS[i]
    const hi = STOPS[i + 1]
    if (clamped >= lo.score && clamped <= hi.score) {
      const t = (clamped - lo.score) / (hi.score - lo.score)
      const rgb = lo.rgb.map((c, idx) => Math.round(lerp(c, hi.rgb[idx], t)))
      return `rgb(${rgb.join(",")})`
    }
  }
  return `rgb(${STOPS[STOPS.length - 1].rgb.join(",")})`
}

export const LEGEND_STOPS = STOPS
