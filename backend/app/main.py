from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()  # backend/.env 에서 GEMINI_API_KEY 등을 읽어옴

from app.api.analyze import router as analyze_router  # noqa: E402

app = FastAPI(title="여기차려 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze_router)


@app.get("/health")
def health():
    return {"status": "ok"}
