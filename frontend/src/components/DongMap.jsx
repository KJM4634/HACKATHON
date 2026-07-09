import { useEffect, useRef, useState } from "react"
import L from "leaflet"
import "leaflet/dist/leaflet.css"
import { fetchBulkScores } from "../api"
import { LEGEND_STOPS, NO_DATA_COLOR, scoreToColor } from "../colorScale"
import "./DongMap.css"

const BUSAN_CENTER = [35.1796, 129.0756]
const BOUNDARIES_URL = "/busan_dong_boundaries.geojson"

const BASE_STYLE = {
  color: "#52514e",
  weight: 1,
  fillOpacity: 0.45,
}

// index.css의 --accent와 동일한 값 — Leaflet이 값을 SVG 속성으로 바로 찍어 넣어
// CSS 변수(var())가 항상 해석되리라 보장할 수 없으므로 실제 값을 그대로 박아 쓴다.
const HIGHLIGHT_STYLE = {
  color: "#e35d2b",
  weight: 3,
}

// index.css의 --status-critical/--status-good과 동일한 값. Leaflet이 값을 SVG
// 속성으로 바로 찍어 넣어 CSS 변수(var())가 항상 해석되리라 보장할 수 없으므로,
// colorScale.js와 같은 방식으로 실제 값을 그대로 박아 쓴다.
const ORIGIN_COLOR = "#d03b3b"
const ALTERNATIVE_COLOR = "#0ca30c"

// 격자 셀 선택 테두리 — TOP3 강조(HIGHLIGHT_STYLE, 주황)와 헷갈리지 않도록 이
// 지도에서 아직 안 쓰인 색(파란색 계열)을 새로 쓴다. 나머지 팔레트는 전부
// 따뜻한 색(주황/빨강/초록)이라 파란색이 "지금 선택된 것"으로 눈에 확 띈다.
const SELECTED_CELL_STYLE = { color: "#2563eb", weight: 4 }
const UNSELECTED_CELL_STYLE = { color: "#fff", weight: 1 }

// "우리 집" 위치 마커 — 격자 선택과 같은 파란 계열이면 헷갈리니, 다른 배지에
// 안 쓰인 보라색으로 구분한다. 이모지 하나짜리 divIcon이라 별도 이미지 에셋이 필요 없다.
const HOME_MARKER_ICON = L.divIcon({
  html: '<span class="home-marker-emoji">🏠</span>',
  className: "home-marker-icon",
  iconSize: [28, 28],
  iconAnchor: [14, 26],
})

// GeoJSON의 adm_nm은 "부산광역시 OO구 OO동"이지만, TOP3 카드·상세 팝업 등
// 나머지 화면은 전부 백엔드 RegionInfo.행정동명("OO구 OO동", 시도명 없이) 형식을
// 쓴다. 표기를 통일하려고 지도 쪽에서 시도명만 잘라낸다.
function stripSido(name) {
  return name.replace(/^부산광역시\s*/, "")
}

function DongMap({
  category,
  onRegionClick,
  highlightRegionIds,
  connections,
  gridOverlay,
  onGridCellClick,
  selectedCellId,
  isSettingHome,
  onSetHomeLocation,
  homeLocation,
}) {
  const mapElRef = useRef(null)
  const mapRef = useRef(null)
  const geoLayerRef = useRef(null)
  const connectionsLayerRef = useRef(null)
  const gridLayerRef = useRef(null)
  const gridCellLayersRef = useRef(new Map()) // cell_id -> L.rectangle, 선택 테두리 갱신용
  const homeMarkerRef = useRef(null)
  const scoresRef = useRef({})
  const highlightRef = useRef(new Set())
  const onRegionClickRef = useRef(onRegionClick)
  const onGridCellClickRef = useRef(onGridCellClick)
  const isSettingHomeRef = useRef(isSettingHome)
  const onSetHomeLocationRef = useRef(onSetHomeLocation)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // 이벤트 핸들러는 지도 생성 시 1회만 등록되므로, 최신 콜백을 ref로 따라가게 한다
  onRegionClickRef.current = onRegionClick
  onGridCellClickRef.current = onGridCellClick
  isSettingHomeRef.current = isSettingHome
  onSetHomeLocationRef.current = onSetHomeLocation

  // 지도 + GeoJSON 레이어는 한 번만 만든다
  useEffect(() => {
    let cancelled = false // StrictMode의 effect 이중 실행 시 이미 해제된 지도에 접근하는 것 방지

    const map = L.map(mapElRef.current, {
      center: BUSAN_CENTER,
      zoom: 11,
      minZoom: 10,
      maxZoom: 16,
    })
    mapRef.current = map
    connectionsLayerRef.current = L.layerGroup().addTo(map)
    gridLayerRef.current = L.layerGroup().addTo(map)

    // 집 위치 지정 모드(isSettingHome)에서는 지도 아무 곳을 클릭해도(폴리곤 위 포함 —
    // Leaflet 벡터 레이어는 기본적으로 클릭이 지도까지 버블링됨) 행정동/격자 선택
    // 대신 집 위치를 지정한다. 폴리곤/격자 셀 각각의 클릭 핸들러에서 이 모드일 때
    // 자기 동작을 건너뛰게 해뒀다(아래 onEachFeature, 격자 렌더링 useEffect 참고).
    map.on("click", (e) => {
      if (isSettingHomeRef.current) onSetHomeLocationRef.current?.(e.latlng.lat, e.latlng.lng)
    })

    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; CARTO',
      maxZoom: 19,
    }).addTo(map)

    fetch(BOUNDARIES_URL)
      .then((res) => res.json())
      .then((geojson) => {
        if (cancelled) return
        const layer = L.geoJSON(geojson, {
          style: () => ({ ...BASE_STYLE, fillColor: NO_DATA_COLOR }),
          onEachFeature: (feature, lyr) => {
            const regionId = feature.properties.adm_cd2
            lyr.on("mouseover", () => lyr.setStyle({ weight: 2.5 }))
            lyr.on("mouseout", () =>
              lyr.setStyle(highlightRef.current.has(regionId) ? HIGHLIGHT_STYLE : { weight: BASE_STYLE.weight })
            )
            lyr.on("click", () => {
              if (isSettingHomeRef.current) return // 지도 click 이벤트로 버블링돼 집 위치 지정으로 처리됨
              onRegionClickRef.current?.(regionId, stripSido(feature.properties.adm_nm))
            })
            // sticky: true로 마우스를 따라다니게 함 — Leaflet이 호버 중인 레이어 하나에만
            // mousemove를 붙이는 방식이라 206개 폴리곤이 있어도 무겁지 않다. 점수는 아직
            // 없을 수 있어(비동기 로딩) 이름만 우선 넣고, applyTooltipsAndColors에서 채운다
            lyr.bindTooltip(stripSido(feature.properties.adm_nm), { sticky: true, direction: "top", offset: [0, -4] })
          },
        }).addTo(map)
        geoLayerRef.current = layer
        applyTooltipsAndColors(layer, scoresRef.current) // 점수가 지도보다 먼저 도착해 있었을 수 있음
      })
      .catch((err) => {
        if (!cancelled) setError(`행정동 경계 로딩 실패: ${err.message}`)
      })

    return () => {
      cancelled = true
      map.remove()
      mapRef.current = null
      geoLayerRef.current = null
      connectionsLayerRef.current = null
      gridLayerRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 업종이 바뀔 때마다 전체 지역 점수를 다시 받아 색을 입힌다
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    fetchBulkScores(category)
      .then((data) => {
        if (cancelled) return
        const byRegion = {}
        data.scores.forEach((s) => {
          byRegion[s.region_id] = s
        })
        scoresRef.current = byRegion
        applyTooltipsAndColors(geoLayerRef.current, byRegion)
        setLoading(false)
      })
      .catch((err) => {
        if (cancelled) return
        setError(`점수 조회 실패: ${err.message}`)
        setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [category])

  // Top3 추천 결과가 나오면 해당 행정동 테두리를 강조 표시한다
  useEffect(() => {
    highlightRef.current = new Set(highlightRegionIds ?? [])
    const layer = geoLayerRef.current
    if (!layer) return
    layer.eachLayer((lyr) => {
      const regionId = lyr.feature.properties.adm_cd2
      lyr.setStyle(highlightRef.current.has(regionId) ? HIGHLIGHT_STYLE : { weight: BASE_STYLE.weight })
    })
  }, [highlightRegionIds])

  // 선택 지역 점수가 낮아 대안이 있으면, 원래 지역(빨강)과 대안들(초록)을
  // 선으로 잇고 화면에 전부 들어오도록 확대/축소한다. 대안이 없으면(고득점)
  // 이전에 그려둔 게 있다면 지우기만 하고 기존처럼 지도는 단순 표시로 둔다.
  useEffect(() => {
    const map = mapRef.current
    const layer = connectionsLayerRef.current
    if (!map || !layer) return

    layer.clearLayers()
    if (!connections) return

    const { origin, alternatives } = connections
    const points = [[origin.위도, origin.경도]]

    L.circleMarker([origin.위도, origin.경도], {
      radius: 9,
      color: "#fff",
      weight: 2,
      fillColor: ORIGIN_COLOR,
      fillOpacity: 1,
      className: "connection-marker connection-marker-origin",
    })
      .bindTooltip(`${origin.행정동명} (선택 지역)`, { direction: "top" })
      .addTo(layer)

    // 대안마다 선이 "자라나는" 느낌을 주는 트릭: stroke-dasharray를 선 전체 길이로
    // 잡고 dashoffset을 그 길이만큼 밀어둔 상태(안 보임)에서 0으로 옮기면 선이
    // 시작점에서 끝점까지 그려지는 것처럼 보인다. 애니메이션이 끝나면 인라인
    // 스타일을 지우고 className을 "connection-line"으로 바꿔서, 원래 있던
    // 잔잔하게 흘러가는 점선 애니메이션(connection-flow)이 이어받게 한다 —
    // 두 애니메이션이 같은 stroke-dashoffset을 동시에 건드리면 서로 충돌하므로
    // 성장 중에는 흐르는 애니메이션이 없는 별도 클래스를 쓴다.
    const GROW_MS = 650 // 발표 시연에서도 눈에 띄게(원래 420ms) — "기다리는 느낌"이 들지 않는 선까지만 늘림
    const timers = []
    alternatives.forEach((alt, i) => {
      const latlng = [alt.region.위도, alt.region.경도]
      points.push(latlng)

      const line = L.polyline([[origin.위도, origin.경도], latlng], {
        color: ALTERNATIVE_COLOR,
        weight: 2,
        opacity: 0.8,
        className: "connection-line-growing",
      }).addTo(layer)

      const marker = L.circleMarker(latlng, {
        radius: 8,
        color: "#fff",
        weight: 2,
        fillColor: ALTERNATIVE_COLOR,
        fillOpacity: 0,
        opacity: 0,
        className: "connection-marker connection-marker-alt",
      })
        .bindTooltip(`${alt.region.행정동명}: ${alt.score}점 · ${alt.distance_km}km`, { direction: "top" })
        .on("click", () => onRegionClickRef.current?.(alt.region.region_id, alt.region.행정동명))
        .addTo(layer)

      const startDelay = i * 60 // 대안이 여러 개면 살짝 시차를 둬서 한꺼번에 딱 나타나지 않게
      timers.push(
        window.setTimeout(() => {
          const pathEl = line.getElement()
          if (pathEl) {
            const length = pathEl.getTotalLength()
            pathEl.style.strokeDasharray = `${length}`
            pathEl.style.strokeDashoffset = `${length}`
            pathEl.getBoundingClientRect() // 강제 리플로우: 위 "시작 상태"를 브라우저가 실제로 반영하게 함
            pathEl.style.transition = `stroke-dashoffset ${GROW_MS}ms ease-out`
            pathEl.style.strokeDashoffset = "0"
          }

          timers.push(
            window.setTimeout(() => {
              if (pathEl) {
                pathEl.style.transition = ""
                pathEl.style.strokeDasharray = ""
                pathEl.style.strokeDashoffset = ""
              }
              line.getElement()?.classList.replace("connection-line-growing", "connection-line")
              marker.setStyle({ fillOpacity: 1, opacity: 1 })
            }, GROW_MS)
          )
        }, startDelay)
      )
    })

    map.flyToBounds(L.latLngBounds(points), { padding: [56, 56], maxZoom: 15, duration: 0.5 })

    return () => timers.forEach((id) => window.clearTimeout(id))
  }, [connections])

  // 행정동 상세를 열면 그 동만 격자로 잘라 확대해서 보여준다("격자 확대 모드").
  // 나머지 205개 행정동은 흐리게(fillOpacity만 낮춤 — 개별 fillColor는 안 건드림)
  // 남겨서 지금 보는 동이 부산 어디쯔인지 맥락은 유지한다.
  useEffect(() => {
    const map = mapRef.current
    const layer = gridLayerRef.current
    const geoLayer = geoLayerRef.current
    if (!map || !layer) return

    layer.clearLayers()
    gridCellLayersRef.current.clear()

    if (!gridOverlay || gridOverlay.status !== "success") {
      geoLayer?.setStyle({ fillOpacity: BASE_STYLE.fillOpacity })
      return
    }

    geoLayer?.setStyle({ fillOpacity: 0.08 })

    // 셀이 몇 개든(우1동처럼 100개 넘어도) 전체 등장 시간이 SPREAD_MS를 넘지 않도록
    // 셀당 지연을 셀 수에 반비례하게 잡는다 — 그래야 "순차 등장"이 곧 "느려짐"이 되지 않는다.
    const SPREAD_MS = 500 // 발표 시연에서도 눈에 띄게(원래 280ms) — "기다리는 느낌"이 들지 않는 선까지만 늘림
    const cellCount = gridOverlay.cells.length
    const perCellDelay = cellCount > 1 ? SPREAD_MS / cellCount : 0

    const bounds = []
    const timers = []
    gridOverlay.cells.forEach((cell, i) => {
      const { north, south, east, west } = cell.bounds
      const rect = L.rectangle([[south, west], [north, east]], {
        color: "#fff",
        weight: 1,
        fillColor: scoreToColor(cell.total_score),
        fillOpacity: 0,
        opacity: 0,
        className: "grid-cell-rect",
      })
        .bindTooltip(`${cell.total_score}점`, { sticky: true })
        .on("click", () => {
          if (isSettingHomeRef.current) return // 지도 click 이벤트로 버블링돼 집 위치 지정으로 처리됨
          onGridCellClickRef.current?.(cell.cell_id)
        })
        .addTo(layer)
      gridCellLayersRef.current.set(cell.cell_id, rect)

      timers.push(
        window.setTimeout(() => {
          // 채우기만 연하게(행정동 히트맵과 같은 BASE_STYLE.fillOpacity) — 테두리(opacity)는
          // 그대로 완전 불투명 유지해서 지도 배경(도로·지명)이 함께 보이게 한다.
          rect.setStyle({ fillOpacity: BASE_STYLE.fillOpacity, opacity: 1 })
        }, i * perCellDelay)
      )

      bounds.push([south, west], [north, east])
    })

    if (bounds.length > 0) {
      map.flyToBounds(L.latLngBounds(bounds), { padding: [40, 40], maxZoom: 18, duration: 0.5 })
    }

    return () => timers.forEach((id) => window.clearTimeout(id))
  }, [gridOverlay])

  // 격자 셀 하나를 선택하면(GridCellDetailPanel이 열림) 그 셀에 파란 테두리를 입혀서
  // "지금 보고 있는 위치가 여기다"를 지도에서 바로 알 수 있게 한다 — 좌표 기반
  // 셀 ID(예: "I-8")를 텍스트로 보여주는 대신 시각적 표시로 대체한 것.
  useEffect(() => {
    gridCellLayersRef.current.forEach((rect, cellId) => {
      const selected = cellId === selectedCellId
      rect.setStyle(selected ? SELECTED_CELL_STYLE : UNSELECTED_CELL_STYLE)
      if (selected) rect.bringToFront()
    })
  }, [selectedCellId, gridOverlay])

  // "우리 집" 위치가 지정/변경/해제되면 마커를 그 상태에 맞춰 다시 그린다.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    homeMarkerRef.current?.remove()
    homeMarkerRef.current = null

    if (!homeLocation) return
    homeMarkerRef.current = L.marker([homeLocation.lat, homeLocation.lng], { icon: HOME_MARKER_ICON, zIndexOffset: 1000 })
      .bindTooltip("우리 집", { direction: "top", offset: [0, -22] })
      .addTo(map)
  }, [homeLocation])

  // 집 위치 지정 모드에서는 커서를 크로스헤어로 바꿔 "지금 클릭하면 여기로
  // 지정된다"는 걸 시각적으로 알려준다.
  useEffect(() => {
    const el = mapElRef.current
    if (!el) return
    el.style.cursor = isSettingHome ? "crosshair" : ""
  }, [isSettingHome])

  return (
    <div className="dong-map-wrap">
      <div ref={mapElRef} className="dong-map" />

      <div className="dong-map-legend">
        <div className="legend-title">생존 가능성 점수</div>
        <div
          className="legend-bar"
          style={{
            background: `linear-gradient(to right, ${LEGEND_STOPS.map((s) => `rgb(${s.rgb.join(",")}) ${s.score}%`).join(", ")})`,
          }}
        />
        <div className="legend-scale-labels">
          <span>0</span>
          <span>50</span>
          <span>100</span>
        </div>
        <div className="legend-hint">
          <span className="legend-swatch legend-swatch-dashed" />
          점선 테두리 = 배후인구가 구 단위 추정치(행정동 실측 아님)
        </div>
      </div>

      {loading && <div className="dong-map-overlay">점수 불러오는 중…</div>}
      {error && <div className="dong-map-overlay dong-map-overlay-error">{error}</div>}
    </div>
  )
}

function applyTooltipsAndColors(layer, byRegion) {
  if (!layer) return
  layer.eachLayer((lyr) => {
    const regionId = lyr.feature.properties.adm_cd2
    const name = stripSido(lyr.feature.properties.adm_nm)
    const info = byRegion[regionId]
    if (!info) {
      lyr.setStyle({ fillColor: NO_DATA_COLOR, dashArray: null })
      lyr.setTooltipContent(`${name} (점수 없음)`)
      return
    }
    lyr.setStyle({
      fillColor: scoreToColor(info.total_score),
      dashArray: info.is_gu_level_estimate ? "4 4" : null,
    })
    lyr.setTooltipContent(`${name} · ${info.total_score}점`)
  })
}

export default DongMap
