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

function DongMap({ category }) {
  const mapElRef = useRef(null)
  const mapRef = useRef(null)
  const geoLayerRef = useRef(null)
  const scoresRef = useRef({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

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
            lyr.on("mouseover", () => lyr.setStyle({ weight: 2.5 }))
            lyr.on("mouseout", () => lyr.setStyle({ weight: BASE_STYLE.weight }))
            lyr.on("click", () => {
              const regionId = feature.properties.adm_cd2
              const info = scoresRef.current[regionId]
              // eslint-disable-next-line no-console
              console.log("[지역 클릭]", feature.properties.adm_nm, info ?? "점수 없음(카테고리 미조회)")
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
