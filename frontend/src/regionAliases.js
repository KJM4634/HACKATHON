// 공식 행정동명이 아닌 생활권/번화가 이름 -> 실제 행정동명에 들어있는 부분 문자열들.
// "서면"은 부산진구 부전1동·부전2동·전포1동·전포2동을 아우르는 생활권 이름이라
// 어떤 공식 행정동명에도 문자열 그대로 나타나지 않는다 — 검색창은 단순 부분일치라
// 그대로 두면 0건이 나온다. 자연어 질의(query_parser.py)는 Gemini가 이런 이름을
// 이해해서 처리하지만, 검색창은 즉시·결정론적으로 반응해야 하는 단순 필터라
// Gemini를 다시 부르는 대신 자주 쓰이는 이름 몇 개만 정적 테이블로 커버한다.
// 목록에 없는 생활권 이름은 여전히 자연어 질의창을 쓰면 된다.
export const REGION_ALIASES = {
  서면: ["부전1동", "부전2동", "전포1동", "전포2동"],
  광안리: ["광안1동", "광안2동", "광안3동", "광안4동"],
}

// 검색어가 행정동명에 그대로 포함되면 그걸로 매치, 아니면 별칭 테이블의 부분
// 문자열 중 하나라도 포함되면 매치로 본다.
export function matchesRegionQuery(행정동명, query) {
  if (행정동명.includes(query)) return true
  const fragments = REGION_ALIASES[query]
  return fragments?.some((fragment) => 행정동명.includes(fragment)) ?? false
}
