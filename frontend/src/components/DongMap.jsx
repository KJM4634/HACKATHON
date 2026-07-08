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

const HIGHLIGHT_STYLE = {
  color: "#2a78d6",
  weight: 3,
}

// index.css의 --status-critical/--status-good과 동일한 값. Leaflet이 값을 SVG
// 속성으로 바로 찍어 넣어 CSS 변수(var())가 항상 해석되리라 보장할 수 없으므로,
// colorScale.js와 같은 방식으로 실제 값을 그대로 박아 쓴다.
const ORIGIN_COLOR = "#d03b3b"
const ALTERNATIVE_COLOR = "#0ca30c"

function DongMap({ category, onRegionClick, highlightRegionIds, connections }) {
  const mapElRef = useRef(null)
  const mapRef = useRef(null)
  const geoLayerRef = useRef(null)
  const connectionsLayerRef = useRef(null)
  const scoresRef = useRef({})
  const highlightRef = useRef(new Set())
  const onRegionClickRef = useRef(onRegionClick)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // 이벤트 핸들러는 지도 생성 시 1회만 등록되므로, 최신 콜백을 ref로 따라가게 한다
  onRegionClickRef.current = onRegionClick

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
              onRegionClickRef.current?.(regionId, feature.properties.adm_nm)
            })
          },
        }).addTo(map)
        geoLayerRef.current = layer
        applyColors(layer, scoresRef.current) // 점수가 지도보다 먼저 도착해 있었을 수 있음
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
        applyColors(geoLayerRef.current, byRegion)
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

    alternatives.forEach((alt) => {
      const latlng = [alt.region.위도, alt.region.경도]
      points.push(latlng)

      L.polyline([[origin.위도, origin.경도], latlng], {
        color: ALTERNATIVE_COLOR,
        weight: 2,
        opacity: 0.8,
        className: "connection-line",
      }).addTo(layer)

      L.circleMarker(latlng, {
        radius: 8,
        color: "#fff",
        weight: 2,
        fillColor: ALTERNATIVE_COLOR,
        fillOpacity: 1,
        className: "connection-marker connection-marker-alt",
      })
        .bindTooltip(`${alt.region.행정동명}: ${alt.score}점 · ${alt.distance_km}km`, { direction: "top" })
        .on("click", () => onRegionClickRef.current?.(alt.region.region_id, alt.region.행정동명))
        .addTo(layer)
    })

    map.fitBounds(L.latLngBounds(points), { padding: [56, 56], maxZoom: 15 })
  }, [connections])

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

function applyColors(layer, byRegion) {
  if (!layer) return
  layer.eachLayer((lyr) => {
    const regionId = lyr.feature.properties.adm_cd2
    const info = byRegion[regionId]
    if (!info) {
      lyr.setStyle({ fillColor: NO_DATA_COLOR, dashArray: null })
      return
    }
    lyr.setStyle({
      fillColor: scoreToColor(info.total_score),
      dashArray: info.is_gu_level_estimate ? "4 4" : null,
    })
  })
}

export default DongMap
