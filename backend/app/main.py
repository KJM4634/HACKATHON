from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()  # backend/.env 에서 GEMINI_API_KEY, NAVER_CLIENT_ID/SECRET 등을 읽어옴

from app.api.analyze import router as analyze_router  # noqa: E402
from app.api.grid import router as grid_router  # noqa: E402
from app.api.grid_report import router as grid_review_router  # noqa: E402

app = FastAPI(title="여기차려 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze_router)
app.include_router(grid_router)
# grid_router와 같은 prefix("/api/grid")를 쓰지만 경로가 다르다(POST /api/grid/report
# vs 기존 POST /api/grid/cell/report) — 격자 AI 해설에 네이버 블로그 리뷰 요약을
# 이어붙인 별도 병렬 엔드포인트다(app/api/grid_report.py 참고, 기존 엔드포인트와
# 통합은 추후 검토).
app.include_router(grid_review_router)


@app.get("/health")
def health():
    return {"status": "ok"}
