import { useEffect, useState } from "react"

// 0에서 target까지 ease-out-cubic으로 올라가는 카운트업. 게이지가 열릴 때마다
// (target이 바뀔 때마다) 처음부터 다시 센다.
export function useCountUp(target, duration = 600) {
  const [value, setValue] = useState(0)

  useEffect(() => {
    let start = null
    let raf

    function step(timestamp) {
      if (start === null) start = timestamp
      const progress = Math.min((timestamp - start) / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      setValue(Math.round(eased * target))
      if (progress < 1) raf = requestAnimationFrame(step)
    }

    setValue(0)
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [target, duration])

  return value
}
