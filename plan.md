# Bridge Local Platform – V1 Plan

## 1. Branding & Config
- Global constants in backend config module:
  - APP_PUBLIC_NAME = "The Bridge — Local Services"
  - APP_INTERNAL_NAME = "bridge_local_platform"
- Config collection `app_config` in Mongo with feature flags:
  - auto_dispatch_enabled (bool, default false)
  - require_payment_before_confirm (bool, default true)
  - max_contractor_offers_per_job (int, default 3)
  - sandbox_mode (bool, default false)
- Simple config service to read with defaults + cache.

## 2. Backend Architecture

### 2.1 Tech Stack & Structure
- FastAPI app in `server.py` with APIRouter submodules:
  - `api.auth` – JWT auth, login, registration helpers (contractor/operator only)
  - `api.client_jobs` – client-facing job flows
  - `api.contractors` – contractor signup, offers, jobs
  - `api.operator` – operator/admin dashboards, quotes, overrides
  - `api.webhooks` – Stripe webhooks
  - `api.admin` – simulations & seeds
- Data access layer:
  - `db.py` – Mongo client + helpers
  - `models/*.py` – Pydantic models and DB helpers for each collection
- Domain & services layer:
  - `services/job_state.py` – job state machine and transition helper
  - `services/events.py` – job_events write + dispatcher
  - `services/notifications.py` – notification abstraction and in-app log
  - `services/quotes.py` – quote upsert + line items total
  - `services/payments.py` – Stripe integration, payment record handling
  - `services/contractors.py` – contractor business logic (matching, stats)

### 2.2 Collections / Schemas
- `users`
  - id (str, uuid)
  - role (client|contractor|operator|admin)
  - name, email (unique), phone
  - password_hash
  - created_at, last_login_at

- `cities`
  - id, slug, name, country, state, active
  - seed `abq` at startup if missing.

- `service_categories`
  - id, slug, display_name, description, base_pricing_rule_id (nullable)
  - seed examples: handyman, cleaning, assembly, plumbing.

- `contractor_profiles`
  - id
  - user_id (FK users)
  - city_id (FK cities)
  - base_zip
  - radius_miles (int)
  - services (list[service_category_id])
  - bio
  - avg_rating (float, default 0)
  - completed_jobs_count (int, default 0)
  - status (pending_review|active|suspended)
  - public_name
  - legal_name (nullable)
  - payout_preference (string, default "manual")
  - reliability_score (float, default 0)
  - total_earnings_cents (int, default 0)
  - loyalty_tier ("none"|"silver"|"gold", default "none")
  - preferred_hours (dict/json)
  - weekly_availability (dict/json, nullable)
  - referral_code (nullable)
  - internal_notes (nullable)

- `contractor_service_areas`
  - id, contractor_id, zip, radius_miles (nullable), active

- `jobs`
  - id
  - client_id
  - city_id
  - service_category_id
  - title
  - description
  - address_text (nullable)
  - zip
  - preferred_timing (asap|today|this_week|flexible)
  - status (enum – via state machine)
  - created_at, updated_at
  - assigned_contractor_id (nullable)
  - accepted_at, completed_at, cancelled_at (nullable)
  - origin_channel (web|sms|phone|manual)
  - is_test (bool)

- `job_line_items`
  - id, job_id
  - type (base|upsell|discount|fee)
  - label
  - quantity (int)
  - unit_price_cents (int)
  - total_price_cents (int)
  - metadata (dict, nullable)

- `quotes`
  - id, job_id
  - version (int)
  - status (draft|sent_to_client|approved|rejected|expired)
  - total_price_cents
  - created_at, approved_at (nullable)
  - rejected_reason (nullable)

- `payments`
  - id, job_id, quote_id
  - stripe_payment_intent_id
  - stripe_checkout_session_id
  - status (pending|succeeded|failed|refunded|partial)
  - amount_cents
  - currency
  - created_at, paid_at (nullable)
  - failure_reason (nullable)

- `payouts`
  - id, job_id, contractor_id
  - amount_cents
  - status (pending|initiated|paid|cancelled)
  - created_at, paid_at (nullable)
  - method (manual|zelle|stripe_connect|other string)
  - notes (nullable)

- `job_events`
  - id, job_id
  - event_type
  - actor_type (system|client|contractor|operator)
  - actor_id (nullable)
  - data (dict)
  - created_at

- `expansion_requests`
  - id, requested_by_user_id (nullable)
  - city_name_text
  - zip
  - service_category_id (nullable)
  - created_at

- `notifications`
  - id
  - recipient_type (client|contractor|operator)
  - recipient_id (user or contractor_profile depending on type)
  - template_id
  - channels (list[str])
  - payload (dict)
  - created_at
  - read_at (nullable)

### 2.3 Auth & JWT
- `POST /api/auth/login` – email/password → JWT (with role and user id)
- `POST /api/auth/register-contractor` used by contractor signup route
- Password hashing via passlib/bcrypt.
- JWT using python-jose or pyjwt; secret & expiry in backend .env.
- Dependency to enforce role-based access on routes (contractor, operator, admin).
- Clients:
  - Can create jobs unauthenticated (we can optionally create a client user behind the scenes).
  - Status lookup via lightweight client token stored in job (e.g., random string) or (phone + job id last 4). We’ll use a job-specific `client_view_token`.

### 2.4 Job State Machine
- Centralized in `services/job_state.py`:
  - States: new, offering_contractors, awaiting_quote, quote_sent, awaiting_payment, confirmed, in_progress, completed, cancelled_by_client, cancelled_internal, no_contractor_found.
  - `transition_job_status(job_id, new_status, actor_type, actor_id, metadata)`:
    - Validates allowed transitions map.
    - Updates job.status + timestamps (accepted_at, completed_at, cancelled_at as applicable).
    - Writes `job_events` record.
    - Calls specific event handlers (on_job_created, on_contractor_accepted, on_quote_sent, on_payment_succeeded, on_job_completed).

### 2.5 Event Handlers
- Implemented in `services/events.py` and/or specialized services:
  - `on_job_created(job, event)`:
    - Validate city & category exist.
    - Find active contractors:
      - same city
      - service_categories includes job.service_category_id
      - (radius/zip logic simplified: match by zip for v1)
    - If found: create `contractor_offers_prepared` event, transition → `offering_contractors`, and create notifications contractor_new_offer for top N contractors.
    - Else: transition → `no_contractor_found`, notifyOperator(operator_no_contractor_found).
  - `on_contractor_accepted(job, contractor_profile, event)`:
    - If job.offering_contractors & no assigned contractor: assign, set accepted_at, transition → awaiting_quote, notifyOperator.
    - Else: notifyContractor(contractor_job_already_taken).
  - `on_quote_sent(job, quote)`:
    - Ensure status quote_sent via state machine.
    - notifyClient(client_quote_ready).
  - `on_payment_succeeded(job, payment)`:
    - Transition quote_sent/awaiting_payment → confirmed.
    - notifyContractor(contractor_job_confirmed), notifyOperator.
  - `on_job_completed(job, contractor_profile, payout)`:
    - Create payout (pending) with 70% of total quote.
    - Increment contractor completed_jobs_count & total_earnings_cents when payout becomes paid.
    - notifyOperator, notifyClient(client_job_completed_review_request).

### 2.6 Payments / Stripe
- Env vars: STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PUBLIC_KEY (frontend usage if needed later).
- Backend service `services/payments.py`:
  - `create_checkout_session(job_id, quote_id, success_url, cancel_url)`:
    - Reads quote.total_price_cents.
    - Creates Stripe Checkout Session in test mode.
    - Saves `payments` record with pending status.
    - Returns session url/id.
  - Webhook `POST /api/webhooks/stripe`:
    - Validate signature using STRIPE_WEBHOOK_SECRET.
    - On `checkout.session.completed` or `payment_intent.succeeded`:
      - Lookup payment by session id or intent id.
      - Mark payment succeeded, set paid_at.
      - Call state machine to move job to confirmed & trigger events.

### 2.7 Notifications
- `services/notifications.py`:
  - `notify_client(job_id, template_id, channels=["in_app"], data_override=None)`
  - `notify_contractor(contractor_id, template_id, channels=["in_app"], data_override=None)`
  - `notify_operator(template_id, channels=["in_app"], data_override=None)`
- For v1, just insert into `notifications` collection, no external calls.
- Operator & contractor dashboards read recent notifications.

### 2.8 Admin Simulation
- `/api/admin/run-simulation` (admin only):
  - Creates a test job with `is_test=True` for the seeded city/category.
  - Runs through on_job_created, optionally auto-accepts, generates draft quote, optional fake payment event.
  - Returns summary of transitions.

## 3. API Routes (Detail)

### 3.1 Auth
- `POST /api/auth/login` – email, password → JWT, role, user basic info.

### 3.2 Client Routes
- `POST /api/jobs`
  - Body: city_slug, service_category_slug, title?, description, zip, preferred_timing, client_name, client_phone, client_email?, photos?, is_test? flag.
  - Behavior:
    - Find or create client user (role=client) by email/phone.
    - Create job with status new, origin_channel=web, is_test flag.
    - Generate client_view_token and store in job.
    - Log job_created event and call on_job_created.
    - Return { job_id, status, client_view_token }.

- `GET /api/jobs/{job_id}/status`
  - Auth: query param `token` (client_view_token) OR verify phone + minimal code later (v1: token only).
  - Returns job core fields, status, whether quote exists/approved, payment status summary.

- `POST /api/jobs/{job_id}/approve-quote`
  - Auth: client_view_token.
  - Behavior:
    - Ensure job in quote_sent and latest quote.status=sent_to_client.
    - Mark quote approved.
    - Depending on config.require_payment_before_confirm:
      - If true: transition job → awaiting_payment, create Stripe Checkout Session and return checkout_url.
      - If false: transition job → confirmed and possibly still create payment intent/session.

### 3.3 Contractor Routes
- `POST /api/contractors/signup`
  - Body: name, phone, email, password, city_slug, base_zip, radius_miles, service_category_ids, bio, optional suggest new area (city_name_text, zip, service_category_id).
  - Behavior:
    - Create user (role=contractor) and auth record.
    - Create contractor_profile with status pending_review (or active for v1 config).
    - Create contractor_service_area(s) as needed.
    - If suggest area provided: create expansion_request.

- `GET /api/contractors/me/jobs` (auth: contractor)
  - Filters: status (active, completed) via query param.

- `GET /api/contractors/me/offers` (auth: contractor)
  - Returns jobs:
    - status=offering_contractors
    - matching contractor city and service categories.

- `POST /api/contractors/offers/{job_id}/accept` (auth: contractor)
  - Behavior per spec (assign, transition via on_contractor_accepted; handle already taken).

- `POST /api/contractors/jobs/{job_id}/mark-complete` (auth: contractor)
  - Body: completion_note, completion_photos?
  - Behavior:
    - Transition job → completed (from confirmed or in_progress per v1 rule).
    - Create job_completed event; create pending payout record.
    - on_job_completed handler deals with payout creation and notifications.

### 3.4 Operator Routes (role operator|admin)
- `GET /api/operator/jobs`
  - Filters: city_slug, status, service_category_slug, date range.

- `PATCH /api/operator/jobs/{job_id}`
  - Body: status, assigned_contractor_id, internal notes.
  - Use job state machine for status updates.

- `POST /api/operator/jobs/{job_id}/quotes`
  - Body: line_items[] with type, label, quantity, unit_price_cents.
  - Upsert quote and line items (new version if existing approved/sent?).

- `POST /api/operator/jobs/{job_id}/send-quote`
  - Behavior:
    - Set latest quote.status=sent_to_client
    - Transition job → quote_sent
    - Create job_events
    - notifyClient(client_quote_ready).

- `GET /api/operator/contractors`
  - Filters: city, service_category, status.
  - Return includes total_earnings_cents and completed_jobs_count.

- `POST /api/operator/payouts/{payout_id}/mark-paid`
  - On mark paid:
    - Set payout.status=paid, paid_at.
    - Increment contractor_profile.total_earnings_cents and completed_jobs_count.

- `/api/admin/run-simulation` (role admin).

## 4. Frontend Architecture

### 4.1 Global
- Use React Router for multi-role UI.
- Use Tailwind + shadcn UI for clean, non-centered layout; rich but simple UI.
- Define a small API client module using axios with baseURL from `REACT_APP_BACKEND_URL`.

### 4.2 Pages / Routes

#### 4.2.1 Public / Client
- `/` – Marketing-ish entry + primary CTA “Request local help”:
  - Multi-step or single-page form (leaning toward single-page with grouped sections):
    - Step 1: City dropdown (preload cities from `/api/meta/cities`).
    - Step 2: Service category tiles/select.
    - Step 3: Job details: description, zip, preferred timing, optional photos URL.
    - Step 4: Contact info: name, phone, email; toggle "This is a test job".
  - On submit → POST /api/jobs.
  - Show confirmation with job id & a “Track status” link using client_view_token.

- `/jobs/:jobId/status?token=...` – Client status page:
  - Show:
    - Job title/category/city
    - Status with badge + simple timeline
    - If quote ready and not approved: show quote summary & “Approve & pay” button.
    - If awaiting_payment: show “Pay now” button (link to Stripe Checkout session or triggers new session).
    - After confirmed/completed: show final state.
  - All interactive elements must include `data-testid`.

#### 4.2.2 Contractor Portal
- `/contractor/signup` – simple signup form:
  - Fields: name, email, phone, password, confirm password, city, base zip, radius, service categories (multi-select), short bio, optional checkbox “Suggest a new area” + city name + zip.
- `/contractor/login` – email/password login.
- `/contractor` – dashboard layout with side navigation:
  - Tabs:
    - “Offers” – list from `/api/contractors/me/offers` with “Accept job” button.
    - “My Jobs” – active jobs with status and “Mark complete” button with completion note field.
    - “Notifications” – list of notifications for this contractor.

#### 4.2.3 Operator/Admin Portal
- `/operator/login` – email/password (shared auth with role check).
- `/operator` – dashboard with navigation:
  - “Jobs” – table:
    - Filters: city, status, category.
    - Columns: created_at, city, category, client info (light), status, contractor (if assigned), quote total, is_test flag.
    - Row click opens job detail drawer/page:
      - Job details
      - Timeline of job_events
      - Line items & quotes
      - Controls to change status (with state machine constraints) and assign contractor.
      - Form to create/update quote (line items) + button “Send quote to client”.
  - “Contractors” – table with search + columns: name, city, services, status, completed_jobs_count, total_earnings_cents.
  - “Notifications” – feed of operator notifications.
  - “Simulation” – button to call `/api/admin/run-simulation` and show result.

### 4.3 UI/UX Notes
- Use modern dark-on-light or light-with-muted-accent palette (no primary basic red/blue/green).
- Left-aligned main content; avoid full center alignment.
- Buttons: pill/rounded with hover states (background, border, shadow) and transition on background/box-shadow only.
- Every interactive or critical element must have `data-testid` attributes as per spec.

## 5. Implementation Phases

### Phase 1 – Backend Core
- Implement DB connection module + collections.
- Implement auth (JWT), users, cities/service_categories seeds.
- Implement jobs collection, state machine, events, notifications (in-app), contractors.
- Implement client routes: create job, status, approve quote (without Stripe yet).

### Phase 2 – Stripe & Payments
- Implement payments collection and Stripe service.
- Implement approve-quote payment path (create Checkout session, webhook handler, state transitions).

### Phase 3 – Frontend MVP
- Replace starter App with full routing structure.
- Implement client job request + status pages.
- Implement contractor signup/login + offers/my jobs.
- Implement operator login + basic jobs table, job details, quote management, contractor list, simulation trigger.

### Phase 4 – Polish & Manual QA
- Ensure data-testid on all important elements.
- Run eslint & ruff.
- Manual smoke test:
  - Client submits job.
  - Operator sees job, creates & sends quote.
  - Client sees quote, approves & goes to Stripe test checkout.
  - Webhook marks payment succeeded, job confirmed.
  - Contractor accepts job and marks complete.
  - Operator marks payout as paid and sees contractor totals updated.
