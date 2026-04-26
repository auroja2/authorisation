from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta

from config import settings
from auth import authenticate_user, create_access_token, get_current_user, require_role, User
from models import GenerateRequest, PredictRequest, ReconciliationReport
from generator import generate_datasets
from reconciler import reconcile
import predictor

app = FastAPI(title="PayRecon API", version="1.0.0", description="Payment Reconciliation System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory state (replace with DB in prod)
_state: dict = {"platform": [], "bank": [], "report": None}


# ── Auth ──────────────────────────────────────────────────────────────────────


# 2FA Step 1: Username/password check, send OTP
from auth import generate_otp, verify_otp

@app.post("/auth/token", tags=["auth"], summary="Login & get JWT (2FA Step 1)")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    otp = generate_otp(user["username"])
    # For demo: return OTP in response (in production, send via email/SMS)
    return {"2fa_required": True, "username": user["username"], "otp_demo": otp}

# 2FA Step 2: OTP verification, issue token
from fastapi import Body
@app.post("/auth/verify-otp", tags=["auth"], summary="Verify OTP and get JWT (2FA Step 2)")
async def verify_otp_endpoint(
    username: str = Body(...),
    otp: str = Body(...)
):
    from auth import USERS_DB
    if not verify_otp(username, otp):
        raise HTTPException(status_code=401, detail="Invalid or expired OTP")
    user = USERS_DB.get(username)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    token = create_access_token(
        {"sub": user["username"], "role": user["role"]},
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": token, "token_type": "bearer", "role": user["role"]}


@app.get("/auth/me", tags=["auth"], summary="Get current user info")
async def me(current_user: User = Depends(get_current_user)):
    return current_user


# ── Data ──────────────────────────────────────────────────────────────────────

@app.post("/generate", tags=["data"], summary="Generate synthetic platform+bank datasets")
async def generate(
    req: GenerateRequest = GenerateRequest(),
    _: User = Depends(require_role("admin", "analyst"))
):
    platform, bank = generate_datasets(req.num_transactions, req.seed)
    _state["platform"] = platform
    _state["bank"] = bank
    _state["report"] = None
    return {
        "message": f"Generated {len(platform)} platform + {len(bank)} bank transactions",
        "platform_count": len(platform),
        "bank_count": len(bank),
        "platform": [t.model_dump() for t in platform[:5]],  # preview
        "bank": [t.model_dump() for t in bank[:5]],
    }


@app.get("/transactions", tags=["data"], summary="Get current datasets")
async def get_transactions(_: User = Depends(get_current_user)):
    return {
        "platform": [t.model_dump() for t in _state["platform"]],
        "bank": [t.model_dump() for t in _state["bank"]],
    }


# ── Reconciliation ────────────────────────────────────────────────────────────

@app.post("/reconcile", tags=["reconciliation"], summary="Run reconciliation engine")
async def run_reconcile(_: User = Depends(require_role("admin", "analyst"))):
    if not _state["platform"]:
        raise HTTPException(400, "No data. Call /generate first.")
    report = reconcile(_state["platform"], _state["bank"])
    _state["report"] = report
    # Auto-train predictor on results
    predictor.train(report.records)
    return report


@app.get("/report", tags=["reconciliation"], summary="Get latest reconciliation report")
async def get_report(_: User = Depends(get_current_user)) -> ReconciliationReport:
    if not _state["report"]:
        raise HTTPException(404, "No report. Call /reconcile first.")
    return _state["report"]


# ── Prediction ────────────────────────────────────────────────────────────────

@app.post("/predict", tags=["prediction"], summary="Predict status of new transactions")
async def predict_transactions(
    req: PredictRequest,
    _: User = Depends(require_role("admin", "analyst"))
):
    try:
        results = predictor.predict(req.transactions)
        return {"predictions": results}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/predict/model-info", tags=["prediction"], summary="Get ML model info")
async def model_info(_: User = Depends(get_current_user)):
    if predictor._model is None:
        return {"status": "not_trained", "message": "Run /reconcile to auto-train"}
    return {
        "status": "trained",
        "n_estimators": predictor._model.n_estimators,
        "classes": list(predictor._label_enc.classes_),
        "feature_importances": dict(zip(
            ["amount_inr", "amount_bank_inr", "diff", "same_currency", "is_refund", "has_bank", "month_diff"],
            [round(float(f), 4) for f in predictor._model.feature_importances_]
        ))
    }


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "version": "1.0.0"}
