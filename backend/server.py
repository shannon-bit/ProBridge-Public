import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, Body, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from starlette.middleware.cors import CORSMiddleware

import stripe

# -------------------------------------------------
# Env & DB setup
# -------------------------------------------------

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

APP_PUBLIC_NAME = "The Bridge — Local Services"
APP_INTERNAL_NAME = "bridge_local_platform"

# Auth / JWT
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "CHANGE_ME_DEV_SECRET")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Stripe
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "sk_test_placeholder")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "whsec_placeholder")

# -------------------------------------------------
# Helpers & Enums
# -------------------------------------------------

RoleType = Literal["client", "contractor", "operator", "admin"]
JobStatus = Literal[
    "new",
    "offering_contractors",
    "awaiting_quote",
    "quote_sent",
    "awaiting_payment",
    "confirmed",
    "in_progress",
    "completed",
    "cancelled_by_client",
    "cancelled_internal",
    "no_contractor_found",
]


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[str] = None
    role: Optional[RoleType] = None


class UserInDB(BaseModel):
    id: str
    email: EmailStr
    name: str
    phone: Optional[str] = None
    role: RoleType
    password_hash: str
    created_at: datetime
    last_login_at: Optional[datetime] = None

    model_config = ConfigDict(extra="ignore")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


async def get_user_by_email(email: str) -> Optional[UserInDB]:
    doc = await db.users.find_one({"email": email})
    if not doc:
        return None
    return UserInDB(**doc)


async def get_user(user_id: str) -> Optional[UserInDB]:
    doc = await db.users.find_one({"id": user_id})
    if not doc:
        return None
    return UserInDB(**doc)


async def authenticate_user(email: str, password: str) -> Optional[UserInDB]:
    user = await get_user_by_email(email)
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserInDB:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        role: str = payload.get("role")
        if user_id is None or role is None:
            raise credentials_exception
        _ = TokenData(user_id=user_id, role=role)
    except JWTError:
        raise credentials_exception
    user = await get_user(user_id)
    if user is None:
        raise credentials_exception
    return user


def require_role(*allowed_roles: RoleType):
    async def role_dep(current_user: UserInDB = Depends(get_current_user)) -> UserInDB:
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user

    return role_dep


# -------------------------------------------------
# Config model (feature flags)
# -------------------------------------------------


class AppConfig(BaseModel):
    auto_dispatch_enabled: bool = False
    require_payment_before_confirm: bool = True
    max_contractor_offers_per_job: int = 3
    sandbox_mode: bool = False

    model_config = ConfigDict(extra="ignore")


async def get_app_config() -> AppConfig:
    doc = await db.app_config.find_one({"id": "default"})
    if not doc:
        cfg = AppConfig()
        await db.app_config.insert_one({"id": "default", **cfg.model_dump()})
        return cfg
    return AppConfig(**doc)


# -------------------------------------------------
# Seed data helpers
# -------------------------------------------------


async def ensure_seed_data() -> None:
    # Cities
    if await db.cities.count_documents({}) == 0:
        await db.cities.insert_many(
            [
                {
                    "id": str(uuid.uuid4()),
                    "slug": "abq",
                    "name": "Albuquerque, NM",
                    "country": "USA",
                    "state": "NM",
                    "active": True,
                }
            ]
        )

    # Service categories
    if await db.service_categories.count_documents({}) == 0:
        cats = [
            {"slug": "handyman", "display_name": "Handyman", "description": "General repairs"},
            {"slug": "cleaning", "display_name": "Cleaning", "description": "Home & office cleaning"},
            {"slug": "assembly", "display_name": "Assembly", "description": "Furniture & equipment assembly"},
            {"slug": "plumbing", "display_name": "Plumbing", "description": "Basic plumbing"},
        ]
        for c in cats:
            c["id"] = str(uuid.uuid4())
            c["base_pricing_rule_id"] = None
        await db.service_categories.insert_many(cats)


# -------------------------------------------------
# Job models & state machine
# -------------------------------------------------


class Job(BaseModel):
    id: str
    client_id: str
    city_id: str
    service_category_id: str
    title: Optional[str] = None
    description: str
    address_text: Optional[str] = None
    zip: str
    preferred_timing: Literal["asap", "today", "this_week", "flexible"]
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    assigned_contractor_id: Optional[str] = None
    accepted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    origin_channel: str
    is_test: bool = False
    client_view_token: str

    model_config = ConfigDict(extra="ignore")


class JobCreateRequest(BaseModel):
    city_slug: str
    service_category_slug: str
    title: Optional[str] = None
    description: str
    zip: str
    preferred_timing: Literal["asap", "today", "this_week", "flexible"]
    client_name: str
    client_phone: str
    client_email: Optional[EmailStr] = None
    photos: Optional[List[str]] = None
    is_test: bool = False


class JobStatusResponse(BaseModel):
    id: str
    status: JobStatus
    title: Optional[str]
    description: str
    preferred_timing: str
    quote_total_cents: Optional[int] = None
    quote_status: Optional[str] = None
    payment_status: Optional[str] = None


ALLOWED_TRANSITIONS: Dict[JobStatus, List[JobStatus]] = {
    "new": ["offering_contractors", "cancelled_by_client", "cancelled_internal", "no_contractor_found"],
    "offering_contractors": [
        "awaiting_quote",
        "cancelled_by_client",
        "cancelled_internal",
        "no_contractor_found",
    ],
    "awaiting_quote": ["quote_sent", "cancelled_by_client", "cancelled_internal"],
    "quote_sent": [
        "awaiting_payment",
        "confirmed",
        "cancelled_by_client",
        "cancelled_internal",
    ],
    "awaiting_payment": ["confirmed", "cancelled_by_client", "cancelled_internal"],
    "confirmed": ["in_progress", "completed", "cancelled_by_client", "cancelled_internal"],
    "in_progress": ["completed", "cancelled_by_client", "cancelled_internal"],
    "completed": [],
    "cancelled_by_client": [],
    "cancelled_internal": [],
    "no_contractor_found": [],
}


async def create_job_event(
    job_id: str,
    event_type: str,
    actor_type: Literal["system", "client", "contractor", "operator"],
    actor_id: Optional[str],
    data: Optional[Dict[str, Any]] = None,
) -> None:
    ev = {
        "id": str(uuid.uuid4()),
        "job_id": job_id,
        "event_type": event_type,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "data": data or {},
        "created_at": datetime.now(timezone.utc),
    }
    await db.job_events.insert_one(ev)


async def notify(recipient_type: str, recipient_id: Optional[str], template_id: str, payload: Dict[str, Any]):
    doc = {
        "id": str(uuid.uuid4()),
        "recipient_type": recipient_type,
        "recipient_id": recipient_id,
        "template_id": template_id,
        "channels": ["in_app"],
        "payload": payload,
        "created_at": datetime.now(timezone.utc),
        "read_at": None,
    }
    await db.notifications.insert_one(doc)


async def notify_client(job_id: str, template_id: str, data: Optional[Dict[str, Any]] = None):
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        return
    await notify("client", job.get("client_id"), template_id, data or {"job_id": job_id})


async def notify_contractor(contractor_id: str, template_id: str, data: Optional[Dict[str, Any]] = None):
    await notify("contractor", contractor_id, template_id, data or {})


async def notify_operator(template_id: str, data: Optional[Dict[str, Any]] = None):
    await notify("operator", None, template_id, data or {})


async def transition_job_status(
    job_id: str,
    new_status: JobStatus,
    actor_type: Literal["system", "client", "contractor", "operator"],
    actor_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Job:
    job_doc = await db.jobs.find_one({"id": job_id})
    if not job_doc:
        raise HTTPException(status_code=404, detail="Job not found")
    job = Job(**job_doc)
    allowed = ALLOWED_TRANSITIONS.get(job.status, [])
    if new_status not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid transition from {job.status} to {new_status}")

    update: Dict[str, Any] = {"status": new_status, "updated_at": datetime.now(timezone.utc)}
    now = datetime.now(timezone.utc)
    if new_status == "awaiting_quote" and job.accepted_at is None:
        update["accepted_at"] = now
    if new_status == "completed":
        update["completed_at"] = now
    if new_status in ("cancelled_by_client", "cancelled_internal"):
        update["cancelled_at"] = now

    await db.jobs.update_one({"id": job_id}, {"$set": update})
    await create_job_event(job_id, f"status_{new_status}", actor_type, actor_id, metadata)

    # Refresh job
    job_doc = await db.jobs.find_one({"id": job_id})
    job = Job(**job_doc)

    # Trigger basic handlers
    if new_status == "offering_contractors":
        await on_job_created_handler(job)
    if new_status == "quote_sent":
        await on_quote_sent_handler(job)
    if new_status == "completed":
        await on_job_completed_handler(job)

    return job


# -------------------------------------------------
# Event Handlers (simplified for v1)
# -------------------------------------------------


async def on_job_created_handler(job: Job) -> None:
    # Simple contractor matching by city & service_category
    contractors = (
        await db.contractor_profiles.find(
            {
                "city_id": job.city_id,
                "services": job.service_category_id,
                "status": "active",
            },
            {"_id": 0},
        ).to_list(50)
    )
    if not contractors:
        await db.jobs.update_one({"id": job.id}, {"$set": {"status": "no_contractor_found"}})
        await create_job_event(job.id, "no_contractor_found", "system", None, {})
        await notify_operator("operator_no_contractor_found", {"job_id": job.id})
        return

    # Notify top N contractors
    top_n = 3
    for c in contractors[:top_n]:
        await notify_contractor(c["id"], "contractor_new_offer", {"job_id": job.id})
    await create_job_event(job.id, "contractor_offers_prepared", "system", None, {"count": len(contractors)})


async def on_quote_sent_handler(job: Job) -> None:
    await notify_client(job.id, "client_quote_ready", {"job_id": job.id})


async def on_payment_succeeded_handler(job: Job, payment: Dict[str, Any]) -> None:
    if job.assigned_contractor_id:
        await notify_contractor(job.assigned_contractor_id, "contractor_job_confirmed", {"job_id": job.id})
    await notify_operator("client_payment_received", {"job_id": job.id, "payment_id": payment["id"]})


async def on_job_completed_handler(job: Job) -> None:
    # Create payout record at 70% of quote total if not existing
    quote = await db.quotes.find_one({"job_id": job.id}, sort=[("version", -1)])
    if not quote:
        return
    amount = int(quote.get("total_price_cents", 0) * 0.7)
    payout = {
        "id": str(uuid.uuid4()),
        "job_id": job.id,
        "contractor_id": job.assigned_contractor_id,
        "amount_cents": amount,
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
        "paid_at": None,
        "method": "manual",
        "notes": None,
    }
    await db.payouts.insert_one(payout)
    await notify_operator("payout_pending", {"job_id": job.id, "payout_id": payout["id"]})
    await notify_client(job.id, "client_job_completed_review_request", {"job_id": job.id})


# -------------------------------------------------
# FastAPI app & routers
# -------------------------------------------------

app = FastAPI(title=APP_PUBLIC_NAME)
api_router = APIRouter(prefix="/api")


@app.on_event("startup")
async def startup_event():
    await ensure_seed_data()


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()


# ---------------------------
# Auth endpoints
# ---------------------------


@api_router.post("/auth/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.id, "role": user.role}, expires_delta=access_token_expires)
    await db.users.update_one(
        {"id": user.id},
        {"$set": {"last_login_at": datetime.now(timezone.utc)}},
    )
    return Token(access_token=access_token)


# ---------------------------
# Meta endpoints
# ---------------------------


class CityOut(BaseModel):
    id: str
    slug: str
    name: str

    model_config = ConfigDict(extra="ignore")


class ServiceCategoryOut(BaseModel):
    id: str
    slug: str
    display_name: str

    model_config = ConfigDict(extra="ignore")


@api_router.get("/meta/cities", response_model=List[CityOut])
async def get_cities():
    docs = await db.cities.find({"active": True}, {"_id": 0}).to_list(100)
    return [CityOut(**d) for d in docs]


@api_router.get("/meta/service-categories", response_model=List[ServiceCategoryOut])
async def get_service_categories():
    docs = await db.service_categories.find({}, {"_id": 0}).to_list(100)
    return [ServiceCategoryOut(**d) for d in docs]


# ---------------------------
# Client job routes
# ---------------------------


class JobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus
    client_view_token: str


@api_router.post("/jobs", response_model=JobCreateResponse)
async def create_job(body: JobCreateRequest):
    # Find city & category
    city = await db.cities.find_one({"slug": body.city_slug, "active": True})
    if not city:
        raise HTTPException(status_code=400, detail="Invalid city")
    category = await db.service_categories.find_one({"slug": body.service_category_slug})
    if not category:
        raise HTTPException(status_code=400, detail="Invalid service category")

    # Find or create client user (by email if provided, else phone)
    if body.client_email:
        user_query: Dict[str, Any] = {"email": body.client_email}
    else:
        user_query = {"phone": body.client_phone, "role": "client"}
    client_user = await db.users.find_one(user_query)
    now = datetime.now(timezone.utc)
    if not client_user:
        client_user = {
            "id": str(uuid.uuid4()),
            "name": body.client_name,
            "email": body.client_email or f"client-{uuid.uuid4()}@example.com",
            "phone": body.client_phone,
            "role": "client",
            "password_hash": get_password_hash(str(uuid.uuid4())),
            "created_at": now,
            "last_login_at": None,
        }
        await db.users.insert_one(client_user)

    job_id = str(uuid.uuid4())
    client_view_token = str(uuid.uuid4())
    job_doc = {
        "id": job_id,
        "client_id": client_user["id"],
        "city_id": city["id"],
        "service_category_id": category["id"],
        "title": body.title,
        "description": body.description,
        "address_text": None,
        "zip": body.zip,
        "preferred_timing": body.preferred_timing,
        "status": "new",
        "created_at": now,
        "updated_at": now,
        "assigned_contractor_id": None,
        "accepted_at": None,
        "completed_at": None,
        "cancelled_at": None,
        "origin_channel": "web",
        "is_test": body.is_test,
        "client_view_token": client_view_token,
    }
    await db.jobs.insert_one(job_doc)
    await create_job_event(job_id, "job_created", "client", client_user["id"], {})

    # For v1, directly run handler to prepare offers/notifications
    await on_job_created_handler(Job(**job_doc))

    return JobCreateResponse(job_id=job_id, status=job_doc["status"], client_view_token=client_view_token)


@api_router.post("/jobs/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(job_id: str, token: str = Body(..., embed=True)):
    job_doc = await db.jobs.find_one({"id": job_id})
    if not job_doc:
        raise HTTPException(status_code=404, detail="Job not found")
    if token != job_doc.get("client_view_token"):
        raise HTTPException(status_code=403, detail="Invalid token")

    # Find latest quote & payment summary
    quote = await db.quotes.find_one({"job_id": job_id}, sort=[("version", -1)])
    payment = await db.payments.find_one({"job_id": job_id}, sort=[("created_at", -1)])
    return JobStatusResponse(
        id=job_doc["id"],
        status=job_doc["status"],
        title=job_doc.get("title"),
        description=job_doc["description"],
        preferred_timing=job_doc["preferred_timing"],
        quote_total_cents=quote.get("total_price_cents") if quote else None,
        quote_status=quote.get("status") if quote else None,
        payment_status=payment.get("status") if payment else None,
    )


class ApproveQuoteResponse(BaseModel):
    job_id: str
    quote_id: str
    checkout_url: Optional[str] = None
    status: JobStatus


@api_router.post("/jobs/{job_id}/approve-quote", response_model=ApproveQuoteResponse)
async def approve_quote(job_id: str, token: str = Body(..., embed=True), request: Request = None):  # type: ignore[assignment]
    job_doc = await db.jobs.find_one({"id": job_id})
    if not job_doc:
        raise HTTPException(status_code=404, detail="Job not found")
    if token != job_doc.get("client_view_token"):
        raise HTTPException(status_code=403, detail="Invalid token")

    job = Job(**job_doc)
    if job.status != "quote_sent":
        raise HTTPException(status_code=400, detail="Job is not in quote_sent state")

    quote = await db.quotes.find_one({"job_id": job_id}, sort=[("version", -1)])
    if not quote or quote.get("status") != "sent_to_client":
        raise HTTPException(status_code=400, detail="No sent quote to approve")

    await db.quotes.update_one({"id": quote["id"]}, {"$set": {"status": "approved", "approved_at": datetime.now(timezone.utc)}})

    cfg = await get_app_config()

    domain = str(request.base_url).rstrip("/") if request else ""
    success_url = f"{domain}/jobs/{job_id}/status"
    cancel_url = f"{domain}/jobs/{job_id}/status"

    # Create Stripe Checkout session
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": job.title or "Service job"},
                    "unit_amount": quote["total_price_cents"],
                },
                "quantity": 1,
            }
        ],
        metadata={"job_id": job_id, "quote_id": quote["id"]},
        success_url=success_url,
        cancel_url=cancel_url,
    )

    payment_doc = {
        "id": str(uuid.uuid4()),
        "job_id": job_id,
        "quote_id": quote["id"],
        "stripe_payment_intent_id": session.get("payment_intent"),
        "stripe_checkout_session_id": session["id"],
        "status": "pending",
        "amount_cents": quote["total_price_cents"],
        "currency": "usd",
        "created_at": datetime.now(timezone.utc),
        "paid_at": None,
        "failure_reason": None,
    }
    await db.payments.insert_one(payment_doc)

    if cfg.require_payment_before_confirm:
        new_status: JobStatus = "awaiting_payment"
    else:
        new_status = "confirmed"
    await db.jobs.update_one({"id": job_id}, {"$set": {"status": new_status, "updated_at": datetime.now(timezone.utc)}})

    checkout_url = session.get("url")

    return ApproveQuoteResponse(job_id=job_id, quote_id=quote["id"], checkout_url=checkout_url, status=new_status)


# ---------------------------
# Contractor routes (simplified v1)
# ---------------------------


class ContractorSignupRequest(BaseModel):
    name: str
    email: EmailStr
    phone: str
    password: str
    city_slug: str
    base_zip: str
    radius_miles: int
    service_category_ids: List[str]
    bio: Optional[str] = None
    suggest_city_name_text: Optional[str] = None
    suggest_zip: Optional[str] = None
    suggest_service_category_id: Optional[str] = None


@api_router.post("/contractors/signup")
async def contractor_signup(body: ContractorSignupRequest):
    existing = await db.users.find_one({"email": body.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    city = await db.cities.find_one({"slug": body.city_slug})
    if not city:
        raise HTTPException(status_code=400, detail="Invalid city")

    now = datetime.now(timezone.utc)
    user_id = str(uuid.uuid4())
    user_doc = {
        "id": user_id,
        "name": body.name,
        "email": body.email,
        "phone": body.phone,
        "role": "contractor",
        "password_hash": get_password_hash(body.password),
        "created_at": now,
        "last_login_at": None,
    }
    await db.users.insert_one(user_doc)

    contractor_id = str(uuid.uuid4())
    profile = {
        "id": contractor_id,
        "user_id": user_id,
        "city_id": city["id"],
        "base_zip": body.base_zip,
        "radius_miles": body.radius_miles,
        "services": body.service_category_ids,
        "bio": body.bio or "",
        "avg_rating": 0.0,
        "completed_jobs_count": 0,
        "status": "pending_review",
        "public_name": body.name,
        "legal_name": None,
        "payout_preference": "manual",
        "reliability_score": 0.0,
        "total_earnings_cents": 0,
        "loyalty_tier": "none",
        "preferred_hours": {},
        "weekly_availability": None,
        "referral_code": None,
        "internal_notes": None,
    }
    await db.contractor_profiles.insert_one(profile)

    if body.suggest_city_name_text or body.suggest_zip:
        exp = {
            "id": str(uuid.uuid4()),
            "requested_by_user_id": user_id,
            "city_name_text": body.suggest_city_name_text or "",
            "zip": body.suggest_zip or "",
            "service_category_id": body.suggest_service_category_id,
            "created_at": now,
        }
        await db.expansion_requests.insert_one(exp)

    return {"contractor_id": contractor_id}


# ---------------------------
# Operator basic routes
# ---------------------------


@api_router.get("/operator/jobs")
async def operator_jobs(
    city_slug: Optional[str] = None,
    status: Optional[JobStatus] = None,
    service_category_slug: Optional[str] = None,
    current_user: UserInDB = Depends(require_role("operator", "admin")),
):
    _ = current_user
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    if city_slug:
        city = await db.cities.find_one({"slug": city_slug})
        if city:
            query["city_id"] = city["id"]
    if service_category_slug:
        cat = await db.service_categories.find_one({"slug": service_category_slug})
        if cat:
            query["service_category_id"] = cat["id"]

    docs = await db.jobs.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    return docs


# Quote creation & sending


class LineItem(BaseModel):
    type: Literal["base", "upsell", "discount", "fee"]
    label: str
    quantity: int = 1
    unit_price_cents: int
    metadata: Optional[Dict[str, Any]] = None


class CreateQuoteRequest(BaseModel):
    line_items: List[LineItem]


@api_router.post("/operator/jobs/{job_id}/quotes")
async def create_or_update_quote(
    job_id: str,
    body: CreateQuoteRequest,
    current_user: UserInDB = Depends(require_role("operator", "admin")),
):
    _ = current_user
    job_doc = await db.jobs.find_one({"id": job_id})
    if not job_doc:
        raise HTTPException(status_code=404, detail="Job not found")

    existing = await db.quotes.find_one({"job_id": job_id}, sort=[("version", -1)])
    version = (existing.get("version") if existing else 0) + 1

    total = 0
    items_docs = []
    for li in body.line_items:
        total_item = li.quantity * li.unit_price_cents
        total += total_item
        items_docs.append(
            {
                "id": str(uuid.uuid4()),
                "job_id": job_id,
                "type": li.type,
                "label": li.label,
                "quantity": li.quantity,
                "unit_price_cents": li.unit_price_cents,
                "total_price_cents": total_item,
                "metadata": li.metadata or {},
            }
        )

    for doc in items_docs:
        await db.job_line_items.insert_one(doc)

    quote_id = str(uuid.uuid4())
    quote_doc = {
        "id": quote_id,
        "job_id": job_id,
        "version": version,
        "status": "draft",
        "total_price_cents": total,
        "created_at": datetime.now(timezone.utc),
        "approved_at": None,
        "rejected_reason": None,
    }
    await db.quotes.insert_one(quote_doc)
    await create_job_event(job_id, "quote_created", "operator", current_user.id, {"quote_id": quote_id})
    return quote_doc


@api_router.post("/operator/jobs/{job_id}/send-quote")
async def send_quote(
    job_id: str,
    current_user: UserInDB = Depends(require_role("operator", "admin")),
):
    job_doc = await db.jobs.find_one({"id": job_id})
    if not job_doc:
        raise HTTPException(status_code=404, detail="Job not found")
    quote = await db.quotes.find_one({"job_id": job_id}, sort=[("version", -1)])
    if not quote:
        raise HTTPException(status_code=400, detail="No quote found")

    await db.quotes.update_one({"id": quote["id"]}, {"$set": {"status": "sent_to_client"}})
    await db.jobs.update_one({"id": job_id}, {"$set": {"status": "quote_sent", "updated_at": datetime.now(timezone.utc)}})
    await create_job_event(job_id, "quote_sent", "operator", current_user.id, {"quote_id": quote["id"]})
    await notify_client(job_id, "client_quote_ready", {"job_id": job_id, "quote_id": quote["id"]})
    return {"job_id": job_id, "quote_id": quote["id"]}


# ---------------------------
# Stripe webhook
# ---------------------------


@api_router.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        job_id = session["metadata"].get("job_id")
        quote_id = session["metadata"].get("quote_id")
        payment = await db.payments.find_one({"stripe_checkout_session_id": session["id"]})
        if payment:
            await db.payments.update_one(
                {"id": payment["id"]},
                {"$set": {"status": "succeeded", "paid_at": datetime.now(timezone.utc)}},
            )
        else:
            payment = {
                "id": str(uuid.uuid4()),
                "job_id": job_id,
                "quote_id": quote_id,
                "stripe_payment_intent_id": session.get("payment_intent"),
                "stripe_checkout_session_id": session["id"],
                "status": "succeeded",
                "amount_cents": int(session["amount_total"]),
                "currency": session["currency"],
                "created_at": datetime.now(timezone.utc),
                "paid_at": datetime.now(timezone.utc),
                "failure_reason": None,
            }
            await db.payments.insert_one(payment)

        if job_id:
            job_doc = await db.jobs.find_one({"id": job_id})
            if job_doc:
                await db.jobs.update_one(
                    {"id": job_id},
                    {"$set": {"status": "confirmed", "updated_at": datetime.now(timezone.utc)}},
                )
                await on_payment_succeeded_handler(Job(**job_doc), payment)

    return {"received": True}


# ---------------------------
# Admin simulation
# ---------------------------


@api_router.post("/admin/run-simulation")
async def run_simulation(current_user: UserInDB = Depends(require_role("admin"))):
    _ = current_user
    # Create a basic test job in ABQ handyman
    city = await db.cities.find_one({"slug": "abq"})
    cat = await db.service_categories.find_one({"slug": "handyman"})
    if not city or not cat:
        raise HTTPException(status_code=500, detail="Seed data missing")

    now = datetime.now(timezone.utc)
    client_user = {
        "id": str(uuid.uuid4()),
        "name": "Test Client",
        "email": f"test-{uuid.uuid4()}@example.com",
        "phone": "555-0000",
        "role": "client",
        "password_hash": get_password_hash("password"),
        "created_at": now,
        "last_login_at": None,
    }
    await db.users.insert_one(client_user)

    job_id = str(uuid.uuid4())
    client_view_token = str(uuid.uuid4())
    job_doc = {
        "id": job_id,
        "client_id": client_user["id"],
        "city_id": city["id"],
        "service_category_id": cat["id"],
        "title": "Simulation job",
        "description": "Simulated handyman task",
        "address_text": None,
        "zip": "87101",
        "preferred_timing": "flexible",
        "status": "new",
        "created_at": now,
        "updated_at": now,
        "assigned_contractor_id": None,
        "accepted_at": None,
        "completed_at": None,
        "cancelled_at": None,
        "origin_channel": "web",
        "is_test": True,
        "client_view_token": client_view_token,
    }
    await db.jobs.insert_one(job_doc)
    await create_job_event(job_id, "job_created", "system", None, {"simulation": True})

    return {"job_id": job_id, "client_view_token": client_view_token}


# -------------------------------------------------
# Root & CORS
# -------------------------------------------------


@api_router.get("/")
async def root():
    return {"message": "Bridge Local Platform API"}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
