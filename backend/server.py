import os
import uuid
import json
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
# JWT_SECRET_KEY must be provided via environment in production
SECRET_KEY = os.environ["JWT_SECRET_KEY"]
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Stripe
# SMTP / Email (Zoho)
SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
EMAIL_FROM = os.environ.get("EMAIL_FROM", SMTP_USER or "")
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO", SMTP_USER or "")


# Stripe (optional, disabled when PAYMENT_MODE=offline or no key set)
PAYMENT_MODE = os.environ.get("PAYMENT_MODE", "offline")  # "stripe" or "offline"
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

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



import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr


async def send_smtp_email(
    to_email: str,
    subject: str,
    body: str,
    *,
    is_html: bool = False,
    sender_name: str = "ProBridge",
) -> bool:
    """Best-effort Zoho SMTP send. Never raises inside request handlers."""
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS or not EMAIL_FROM:
        # SMTP not configured; silently skip for v1
        return False
    if not to_email:
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = formataddr((sender_name, EMAIL_FROM))
        msg["To"] = to_email
        if EMAIL_REPLY_TO:
            msg["Reply-To"] = EMAIL_REPLY_TO

        subtype = "html" if is_html else "plain"
        part = MIMEText(body, subtype, "utf-8")
        msg.attach(part)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(EMAIL_FROM, [to_email], msg.as_string())
        return True
    except Exception:
        # For v1, don’t break flows on email issues
        return False


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

PRICING_CONFIG_DIR = ROOT_DIR / "config" / "pricing"
QUOTES_CONFIG_DIR = ROOT_DIR / "config" / "quotes"


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


async def get_pricing_suggestion(city_slug: str, service_category_slug: str, description: str) -> Optional[Dict[str, Any]]:
    """Simple estimator v1 based on config/quotes/*.json and config/pricing/*.json.

    For now we use only base_price and platform_fee_pct from pricing config.
    """
    pricing_path = PRICING_CONFIG_DIR / f"{city_slug}.json"
    pricing_cfg = load_json(pricing_path)
    if not pricing_cfg:
        return None

    rules = pricing_cfg.get("rules", [])
    rule = next((r for r in rules if r.get("slug") == service_category_slug), None)
    if not rule:
        return None

    base_price = int(rule.get("base_price", 0))
    if base_price <= 0:
        return None

    fee_pct = float(rule.get("platform_fee_pct", 25.0))
    total_cents = base_price * 100
    platform_cents = int(total_cents * fee_pct / 100.0)
    contractor_cents = total_cents - platform_cents

    return PricingSuggestion(
        suggested_total_cents=total_cents,
        platform_cut_cents=platform_cents,
        contractor_cut_cents=contractor_cents,
        source=f"pricing:{city_slug}:{service_category_slug}"
    ).model_dump()




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

    # Seed a default operator user if none exists (for initial launch/testing)
    if await db.users.count_documents({"role": "operator"}) == 0:
        now = datetime.now(timezone.utc)
        operator_user = {
            "id": str(uuid.uuid4()),
            "name": "ABQ Operator",
            "email": "operator@probridge.space",
            "phone": None,
            "role": "operator",
            "password_hash": get_password_hash("probridge-operator-123"),
            "created_at": now,
            "last_login_at": None,
        }
        await db.users.insert_one(operator_user)

    # Ensure primary operator account for Shannon exists even if other operators are present
    primary_email = "shannon@probridge.space"
    existing_primary = await db.users.find_one({"email": primary_email})
    if not existing_primary:
        now = datetime.now(timezone.utc)
        primary_operator = {
            "id": str(uuid.uuid4()),
            "name": "Shannon (Primary Operator)",
            "email": primary_email,
            "phone": None,
            "role": "operator",
            "status": "active",
            "password_hash": get_password_hash("ProBridge-Operator-001!"),
            "created_at": now,
            "last_login_at": None,
        }
        await db.users.insert_one(primary_operator)



        await db.service_categories.insert_many(cats)


class PricingSuggestion(BaseModel):
    suggested_total_cents: int
    platform_cut_cents: int
    contractor_cut_cents: int
    source: str



class ReferralCreateRequest(BaseModel):
    # Who is being referred
    referred_role: Literal["client", "contractor", "other"]
    referred_name: str
    referred_email: Optional[EmailStr] = None
    referred_phone: Optional[str] = None
    city_slug: Optional[str] = None

    # Who is making the referral
    referrer_role: Literal["client", "contractor", "other"]
    referrer_name: Optional[str] = None
    referrer_email: Optional[EmailStr] = None
    referrer_phone: Optional[str] = None

    # Extra context
    notes: Optional[str] = None
    referral_code: Optional[str] = None



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
    pricing_suggestion: Optional[Dict[str, Any]] = None

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


# Helper to fetch contractor profile for a user
async def get_contractor_profile_for_user(user_id: str) -> Optional[Dict[str, Any]]:
    return await db.contractor_profiles.find_one({"user_id": user_id})


async def send_client_job_received_email(job: Job, client_email: Optional[str]):
    if not client_email:
        return
    frontend_base = os.environ.get("FRONTEND_URL")
    if not frontend_base:
        # If FRONTEND_URL is not set, skip including link rather than using a hardcoded fallback
        subject = "We received your ProBridge request"
        body = (
            f"Hi {job.id[:8]},\n\n"
            f"Thanks for submitting your request with ProBridge. "
            "We received your job but cannot generate a status link right now.\n\n"
            "— ProBridge"
        )
        await send_smtp_email(client_email, subject, body)
        return
    frontend_base = frontend_base.rstrip("/")
    status_url = f"{frontend_base}/jobs/{job.id}/status?token={job.client_view_token}"
    subject = "We received your ProBridge request"
    body = (
        f"Hi {job.id[:8]},\n\n"
        f"Thanks for submitting your request with ProBridge. "
        f"You can check the status of this job and any quotes at this link:\n{status_url}\n\n"
        "— ProBridge"
    )
    await send_smtp_email(client_email, subject, body)


async def send_client_quote_ready_email(job: Job, client_email: Optional[str]):
    if not client_email:
        return
    frontend_base = os.environ.get("FRONTEND_URL")
    if not frontend_base:
        # If FRONTEND_URL is not set, skip including link rather than using a hardcoded fallback
        subject = "Your ProBridge quote is ready"
        body = (
            f"Hi {job.id[:8]},\n\n"
            "Your quote is ready, but we cannot generate a review link right now.\n\n"
            "— ProBridge"
        )
        await send_smtp_email(client_email, subject, body)
        return
    frontend_base = frontend_base.rstrip("/")
    status_url = f"{frontend_base}/jobs/{job.id}/status?token={job.client_view_token}"
    subject = "Your ProBridge quote is ready"
    body = (
        f"Hi {job.id[:8]},\n\n"
        "Your quote is ready. Review and approve it here:\n"
        f"{status_url}\n\n— ProBridge"
    )
    await send_smtp_email(client_email, subject, body)


async def send_contractor_job_offer_email(contractor_user: Dict[str, Any], job: Job):
    email = contractor_user.get("email")
    if not email:
        return
    subject = "New ProBridge job offer in your area"
    body = (
        f"Hi {contractor_user.get('name') or 'there'},\n\n"
        "You have a new job offer available in your ProBridge dashboard. "
        "Log in to review details and accept it if you’re interested.\n\n— ProBridge"
    )
    await send_smtp_email(email, subject, body)


# -------------------------------------------------
# Event Handlers (simplified for v1)
# -------------------------------------------------


async def on_job_created_handler(job: Job) -> None:
    # Email client that their job was received (best-effort)
    client = await db.users.find_one({"id": job.client_id})
    await send_client_job_received_email(job, client.get("email") if client else None)

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
        await db.jobs.update_one({"id": job.id}, {"$set": {"status": "no_contractor_found", "updated_at": datetime.now(timezone.utc)}})
        await create_job_event(job.id, "no_contractor_found", "system", None, {})
        await notify_operator("operator_no_contractor_found", {"job_id": job.id})
        return

    # Mark job as offering to contractors
    await db.jobs.update_one({"id": job.id}, {"$set": {"status": "offering_contractors", "updated_at": datetime.now(timezone.utc)}})

    # Notify top N contractors (in-app + email)
    top_n = 3
    for c in contractors[:top_n]:
        await notify_contractor(c["id"], "contractor_new_offer", {"job_id": job.id})
        # also email contractor user
        user = await db.users.find_one({"id": c.get("user_id")})
        await send_contractor_job_offer_email(user or {}, job)
    await create_job_event(job.id, "contractor_offers_prepared", "system", None, {"count": len(contractors)})


async def on_quote_sent_handler(job: Job) -> None:
    # In-app notification
    await notify_client(job.id, "client_quote_ready", {"job_id": job.id})

    # Email client that quote is ready (best-effort)
    client = await db.users.find_one({"id": job.client_id})
    await send_client_quote_ready_email(job, client.get("email") if client else None)


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
    # Compute simple pricing suggestion (estimator v1)
    pricing_suggestion = await get_pricing_suggestion(body.city_slug, body.service_category_slug, body.description)

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
        "pricing_suggestion": pricing_suggestion,
    }
    await db.jobs.insert_one(job_doc)
    await create_job_event(job_id, "job_created", "client", client_user["id"], {})

    # For v1, directly run handler to prepare offers/notifications
    await on_job_created_handler(Job(**job_doc))

    return JobCreateResponse(job_id=job_id, status=job_doc["status"], client_view_token=client_view_token)


@api_router.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(job_id: str, token: str):
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
    ok: bool = True
    payment_mode: str = "stripe"


class PaymentStatusIn(BaseModel):
    token: str


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
    success_url = f"{domain}/jobs/{job_id}/status?token={token}"
    cancel_url = success_url

    checkout_url: Optional[str] = None

    if PAYMENT_MODE == "stripe":
        # Create Stripe Checkout session
        payment_mode = "stripe"
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
            "method": "stripe",
        }
        await db.payments.insert_one(payment_doc)
        checkout_url = session.get("url")

        if cfg.require_payment_before_confirm:
            new_status: JobStatus = "awaiting_payment"
        else:
            new_status = "confirmed"
    else:
        # Offline / manual payment mode
        payment_mode = "offline"
        payment_id = str(uuid.uuid4())
        payment_doc = {
            "id": payment_id,
            "job_id": job_id,
            "quote_id": quote["id"],
            "status": "pending",
            "amount_cents": quote["total_price_cents"],
            "currency": "usd",
            "created_at": datetime.now(timezone.utc),
            "paid_at": None,
            "failure_reason": None,
            "method": "offline",
        }
        await db.payments.insert_one(payment_doc)
        # Record event + notify operator that offline payment is pending
        await create_job_event(job_id, "offline_payment_pending", "client", job.client_id, {"payment_id": payment_id})
        await notify_operator("offline_payment_pending", {"job_id": job_id, "payment_id": payment_id})
        new_status: JobStatus = "awaiting_payment"

    await db.jobs.update_one({"id": job_id}, {"$set": {"status": new_status, "updated_at": datetime.now(timezone.utc)}})

    return ApproveQuoteResponse(job_id=job_id, quote_id=quote["id"], checkout_url=checkout_url, status=new_status, payment_mode=payment_mode)


@api_router.post("/jobs/{job_id}/client-mark-payment-sent")
async def client_mark_payment_sent(job_id: str, body: PaymentStatusIn):
    """Client indicates they have sent an offline payment.

    This does NOT confirm payment – it only updates the payment status and notifies the operator.
    """
    token = body.token
    job_doc = await db.jobs.find_one({"id": job_id})
    if not job_doc:
        raise HTTPException(status_code=404, detail="Job not found")
    if token != job_doc.get("client_view_token"):
        raise HTTPException(status_code=403, detail="Invalid token")

    payment = await db.payments.find_one({"job_id": job_id}, sort=[("created_at", -1)])
    if not payment:
        raise HTTPException(status_code=400, detail="No payment record found")

    await db.payments.update_one(
        {"id": payment["id"]},
        {"$set": {"status": "client_marked_sent", "updated_at": datetime.now(timezone.utc)}},
    )

    await create_job_event(
        job_id,
        "client_marked_payment_sent",
        "client",
        job_doc.get("client_id"),
        {"payment_id": payment["id"]},
    )
    await notify_operator("client_marked_payment_sent", {"job_id": job_id, "payment_id": payment["id"]})

    return {"job_id": job_id, "payment_id": payment["id"]}


# ---------------------------
# Contractor routes
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
        "status": "active",
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


@api_router.get("/contractors/me/offers")
async def contractor_offers(current_user: UserInDB = Depends(require_role("contractor"))):
    profile = await get_contractor_profile_for_user(current_user.id)
    if not profile:
        raise HTTPException(status_code=404, detail="Contractor profile not found")

    # Offers are derived from notifications of type contractor_new_offer
    notifications = await db.notifications.find(
        {
            "recipient_type": "contractor",
            "recipient_id": profile["id"],
            "template_id": "contractor_new_offer",
        },
        {"_id": 0},
    ).to_list(100)
    job_ids = list({n["payload"].get("job_id") for n in notifications if n.get("payload")})
    if not job_ids:
        return []

    jobs = await db.jobs.find(
        {
            "id": {"$in": job_ids},
            "status": "offering_contractors",
            "assigned_contractor_id": None,
        },
        {"_id": 0},
    ).to_list(100)
    return jobs


@api_router.get("/contractors/me/jobs")
async def contractor_jobs(current_user: UserInDB = Depends(require_role("contractor"))):
    profile = await get_contractor_profile_for_user(current_user.id)
    if not profile:
        raise HTTPException(status_code=404, detail="Contractor profile not found")

    jobs = await db.jobs.find(
        {"assigned_contractor_id": profile["id"]},
        {"_id": 0},
    ).sort("created_at", -1).to_list(200)
    return jobs


class ContractorAcceptResponse(BaseModel):
    job_id: str
    status: JobStatus


@api_router.post("/contractors/offers/{job_id}/accept", response_model=ContractorAcceptResponse)
async def accept_offer(job_id: str, current_user: UserInDB = Depends(require_role("contractor"))):
    profile = await get_contractor_profile_for_user(current_user.id)
    if not profile:
        raise HTTPException(status_code=404, detail="Contractor profile not found")

    job_doc = await db.jobs.find_one({"id": job_id})
    if not job_doc:
        raise HTTPException(status_code=404, detail="Job not found")

    job = Job(**job_doc)
    if job.assigned_contractor_id and job.assigned_contractor_id != profile["id"]:
        # Already taken by someone else
        await notify_contractor(profile["id"], "contractor_job_already_taken", {"job_id": job_id})
        raise HTTPException(status_code=409, detail="Job already taken")

    if job.status != "offering_contractors":
        raise HTTPException(status_code=400, detail="Job is not currently being offered to contractors")

    # Basic eligibility check: same city and service
    if not (profile["city_id"] == job.city_id and job.service_category_id in profile.get("services", [])):
        raise HTTPException(status_code=403, detail="This job is not offered to you")

    # Assign contractor and move to awaiting_quote
    await db.jobs.update_one(
        {"id": job_id},
        {"$set": {"assigned_contractor_id": profile["id"], "accepted_at": datetime.now(timezone.utc)}},
    )
    await create_job_event(job_id, "contractor_accepted", "contractor", current_user.id, {"contractor_id": profile["id"]})
    updated = await transition_job_status(job_id, "awaiting_quote", "contractor", current_user.id)

    await notify_operator("contractor_accepted", {"job_id": job_id, "contractor_id": profile["id"]})

    return ContractorAcceptResponse(job_id=job_id, status=updated.status)


class MarkCompleteRequest(BaseModel):
    completion_note: Optional[str] = None
    photos: Optional[List[str]] = None


@api_router.post("/contractors/jobs/{job_id}/mark-complete")
async def contractor_mark_complete(
    job_id: str,
    body: MarkCompleteRequest,
    current_user: UserInDB = Depends(require_role("contractor")),
):
    profile = await get_contractor_profile_for_user(current_user.id)
    if not profile:
        raise HTTPException(status_code=404, detail="Contractor profile not found")

    job_doc = await db.jobs.find_one({"id": job_id})
    if not job_doc:
        raise HTTPException(status_code=404, detail="Job not found")

    job = Job(**job_doc)
    if job.assigned_contractor_id != profile["id"]:
        raise HTTPException(status_code=403, detail="You are not assigned to this job")

    if job.status not in ("confirmed", "in_progress"):
        raise HTTPException(status_code=400, detail="Job is not in a completable state")

    await create_job_event(
        job_id,
        "job_completed",
        "contractor",
        current_user.id,
        {"completion_note": body.completion_note, "photos": body.photos or []},
    )
    updated = await transition_job_status(job_id, "completed", "contractor", current_user.id)
    return {"job_id": job_id, "status": updated.status}


# ---------------------------
# Operator routes
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



class QuoteOut(BaseModel):
    id: str
    job_id: str
    version: int
    status: str
    total_price_cents: int
    created_at: str
    approved_at: Optional[str] = None
    rejected_reason: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class CreateQuoteRequest(BaseModel):
    line_items: List[LineItem]


@api_router.post("/operator/jobs/{job_id}/quotes", response_model=QuoteOut)
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

    await db.job_line_items.delete_many({"job_id": job_id})
    for doc in items_docs:
        await db.job_line_items.insert_one(doc)

    quote_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    quote_doc = {
        "id": quote_id,
        "job_id": job_id,
        "version": version,
        "status": "draft",
        "total_price_cents": total,
        "created_at": now.isoformat(),
        "approved_at": None,
        "rejected_reason": None,
    }
    await db.quotes.insert_one(quote_doc)
    await create_job_event(job_id, "quote_created", "operator", current_user.id, {"quote_id": quote_id})
    # Ensure no MongoDB internal _id leaks into the response
    quote_doc.pop("_id", None)
    return QuoteOut(**quote_doc)


@api_router.post("/operator/jobs/{job_id}/mark-paid")
async def operator_mark_job_paid(job_id: str, current_user: UserInDB = Depends(require_role("operator", "admin"))):
    _ = current_user
    job_doc = await db.jobs.find_one({"id": job_id})
    if not job_doc:
        raise HTTPException(status_code=404, detail="Job not found")

    payment = await db.payments.find_one({"job_id": job_id}, sort=[("created_at", -1)])
    if not payment:
        raise HTTPException(status_code=400, detail="No payment record found")

    if payment.get("status") == "succeeded":
        raise HTTPException(status_code=400, detail="Payment already marked as succeeded")

    now = datetime.now(timezone.utc)
    await db.payments.update_one(
        {"id": payment["id"]},
        {"$set": {"status": "succeeded", "paid_at": now}},
    )

    await db.jobs.update_one(
        {"id": job_id},
        {"$set": {"status": "confirmed", "updated_at": now}},
    )

    await on_payment_succeeded_handler(Job(**job_doc), payment)

    return {"job_id": job_id, "payment_id": payment["id"], "status": "succeeded"}


@api_router.post("/operator/jobs/{job_id}/mark-payment-received")
async def operator_mark_payment_received(job_id: str, current_user: UserInDB = Depends(require_role("operator", "admin"))):
    """Alias endpoint for marking offline payment as received.

    For now this simply forwards to the existing mark-paid logic.
    """
    return await operator_mark_job_paid(job_id, current_user)


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


class OperatorJobPatch(BaseModel):
    status: Optional[JobStatus] = None
    assigned_contractor_id: Optional[str] = None
    internal_notes: Optional[str] = None


@api_router.patch("/operator/jobs/{job_id}")
async def operator_update_job(
    job_id: str,
    body: OperatorJobPatch,
    current_user: UserInDB = Depends(require_role("operator", "admin")),
):
    _ = current_user
    job_doc = await db.jobs.find_one({"id": job_id})
    if not job_doc:
        raise HTTPException(status_code=404, detail="Job not found")

    updates: Dict[str, Any] = {}

    if body.assigned_contractor_id is not None:
        contractor = await db.contractor_profiles.find_one({"id": body.assigned_contractor_id})
        if not contractor:
            raise HTTPException(status_code=400, detail="Assigned contractor not found")
        updates["assigned_contractor_id"] = body.assigned_contractor_id

    if body.internal_notes is not None:
        updates["internal_notes"] = body.internal_notes

    if updates:
        updates["updated_at"] = datetime.now(timezone.utc)
        await db.jobs.update_one({"id": job_id}, {"$set": updates})

    if body.status is not None:
        await transition_job_status(job_id, body.status, "operator", current_user.id)

    updated = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return updated


@api_router.get("/operator/contractors")
async def operator_contractors(
    city_slug: Optional[str] = None,
    service_category_slug: Optional[str] = None,
    status: Optional[str] = None,
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
            query["services"] = cat["id"]

    profiles = await db.contractor_profiles.find(query, {"_id": 0}).to_list(200)

    # Attach simple city and services labels
    cities = {c["id"]: c for c in await db.cities.find({}, {"_id": 0}).to_list(100)}
    cats = {c["id"]: c for c in await db.service_categories.find({}, {"_id": 0}).to_list(100)}

    def map_profile(p: Dict[str, Any]) -> Dict[str, Any]:
        city = cities.get(p["city_id"])
        service_labels = [cats[s]["display_name"] for s in p.get("services", []) if s in cats]
        return {
            "id": p["id"],
            "public_name": p.get("public_name"),
            "city": city.get("name") if city else None,
            "service_labels": service_labels,
            "status": p.get("status"),
            "total_earnings_cents": p.get("total_earnings_cents", 0),
            "completed_jobs_count": p.get("completed_jobs_count", 0),
        }

    return [map_profile(p) for p in profiles]


@api_router.post("/operator/payouts/{payout_id}/mark-paid")
async def mark_payout_paid(payout_id: str, current_user: UserInDB = Depends(require_role("operator", "admin"))):
    _ = current_user
    payout = await db.payouts.find_one({"id": payout_id})
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")
    if payout.get("status") == "paid":
        raise HTTPException(status_code=400, detail="Payout already marked as paid")

    now = datetime.now(timezone.utc)
    await db.payouts.update_one(
        {"id": payout_id},
        {"$set": {"status": "paid", "paid_at": now}},
    )

    contractor_id = payout.get("contractor_id")
    amount = int(payout.get("amount_cents", 0))
    if contractor_id:
        await db.contractor_profiles.update_one(
            {"id": contractor_id},
            {"$inc": {"completed_jobs_count": 1, "total_earnings_cents": amount}},
        )

    return {"payout_id": payout_id, "status": "paid"}

# ---------------------------
# Referral intake
# ---------------------------


@api_router.post("/referrals")
async def create_referral(body: ReferralCreateRequest, request: Request):
    now = datetime.now(timezone.utc)

    # Try to map city_slug to city_id if provided
    city_id = None
    if body.city_slug:
        city = await db.cities.find_one({"slug": body.city_slug})
        if city:
            city_id = city["id"]

    referral_id = str(uuid.uuid4())
    doc = {
        "id": referral_id,
        "referred_role": body.referred_role,
        "referred_name": body.referred_name,
        "referred_email": body.referred_email,
        "referred_phone": body.referred_phone,
        "city_id": city_id,
        "city_slug": body.city_slug,
        "referrer_role": body.referrer_role,
        "referrer_name": body.referrer_name,
        "referrer_email": body.referrer_email,
        "referrer_phone": body.referrer_phone,
        "notes": body.notes,
        "referral_code": body.referral_code,
        "created_at": now,
        "source": "web",
        "request_path": str(request.url.path),
    }

    await db.referrals.insert_one(doc)

    # Create a simple operator notification
    await notify_operator(
        "new_referral_submitted",
        {
            "referral_id": referral_id,
            "referred_name": body.referred_name,
            "referred_role": body.referred_role,
            "referrer_name": body.referrer_name,
            "referrer_role": body.referrer_role,
        },
    )

    return {"id": referral_id}


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
