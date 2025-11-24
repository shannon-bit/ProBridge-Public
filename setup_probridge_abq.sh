#!/usr/bin/env bash
set -euo pipefail

mkdir -p probridge-abq
cd probridge-abq

mkdir -p backend frontend/app/request frontend/app/status frontend/app/contractors frontend/lib config docs

cat << 'EOF' > backend/server.txt
SERVER SPEC (TEXT-ONLY SEED)

Endpoints:
1. GET /status
2. POST /jobs/create
3. GET /jobs/list
EOF

cat << 'EOF' > backend/routes.txt
ROUTES SPEC (TEXT MODE)

Routes:
- /status
- /jobs/create
- /jobs/list
EOF

cat << 'EOF' > backend/logic.txt
LOGIC SPEC (TEXT-ONLY)
EOF

cat << 'EOF' > backend/server.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from datetime import datetime

app = FastAPI(title="ProBridge ABQ Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class JobCreate(BaseModel):
    name: str
    location: str
    phone: str
    type: str
    description: str
    preferred_timing: str

class Job(JobCreate):
    job_id: int
    status: str = "created"
    created_at: datetime

jobs_db: List[Job] = []
next_job_id: int = 1

@app.get("/status")
def get_status():
    return {"status": "ok",
            "service": "ProBridge ABQ Backend",
            "time": datetime.utcnow().isoformat()+"Z",
            "jobs_count": len(jobs_db)}

@app.post("/jobs/create", response_model=Job)
def create_job(payload: JobCreate):
    global next_job_id
    job = Job(job_id=next_job_id,
              name=payload.name, location=payload.location,
              phone=payload.phone, type=payload.type,
              description=payload.description,
              preferred_timing=payload.preferred_timing,
              created_at=datetime.utcnow())
    jobs_db.append(job)
    next_job_id += 1
    return job

@app.get("/jobs/list", response_model=List[Job])
def list_jobs():
    return jobs_db
EOF

cat << 'EOF' > backend/requirements.txt
fastapi
uvicorn[standard]
pydantic
EOF

cat << 'EOF' > backend/run_local.txt
Run with:
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
EOF

cat << 'EOF' > frontend/package.json
{
  "name": "probridge-abq-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": { "dev": "next dev", "build": "next build", "start": "next start" },
  "dependencies": { "next": "14.2.0", "react": "18.2.0", "react-dom": "18.2.0" }
}
EOF

cat << 'EOF' > frontend/next.config.js
module.exports = { reactStrictMode: true };
EOF

# layout.jsx
cat << 'EOF' > frontend/app/layout.jsx
export const metadata = { title: "ProBridge ABQ" };

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body style={{margin:0,fontFamily:"system-ui"}}>
        <header style={{padding:"1rem",background:"#fff",borderBottom:"1px solid #ccc"}}>
          <div style={{fontWeight:700}}>ProBridge ABQ</div>
          <nav style={{display:"flex",gap:"1rem"}}>
            <a href="/">Home</a>
            <a href="/request">Request Help</a>
            <a href="/contractors">For Local Pros</a>
          </nav>
        </header>
        <main style={{padding:"1rem",maxWidth:"960px",margin:"0 auto"}}>{children}</main>
      </body>
    </html>
  );
}
EOF

# Home page
cat << 'EOF' > frontend/app/page.jsx
export default function HomePage() {
  return (
    <div>
      <h1>Need help with home tasks in ABQ?</h1>
      <a href="/request">I need help with a home task</a>
      <br/>
      <a href="/contractors">I'm a local pro</a>
    </div>
  );
}
EOF

# Request page
cat << 'EOF' > frontend/app/request/page.jsx
"use client";
import { useState } from "react";
import { createJob } from "../../lib/api";
export default function RequestPage() {
  const [form,setForm]=useState({name:"",location:"",phone:"",type:"repair",description:"",preferred_timing:"today"});
  const [submittedJob,setSubmittedJob]=useState(null);
  const [error,setError]=useState(null);
  function update(e){setForm({...form,[e.target.name]:e.target.value});}
  async function submit(e){e.preventDefault();setError(null);try{
    const job=await createJob(form);setSubmittedJob(job);}catch(err){setError("Error");}}
  if(submittedJob){return(<div><h1>Request Submitted</h1><p>Job ID: {submittedJob.job_id}</p><p>Status: {submittedJob.status}</p></div>);}  
  return (<form onSubmit={submit}><input name="name" onChange={update} required/><input name="location" onChange={update} required/><input name="phone" onChange={update} required/>
  <textarea name="description" onChange={update} required/>
  <button>Submit</button>{error&&<p>{error}</p>}</form>);
}
EOF

# Status page
cat << 'EOF' > frontend/app/status/page.jsx
"use client";
import { useEffect,useState } from "react";
import { getStatus } from "../../lib/api";
export default function Status(){
  const [status,setStatus]=useState(null);
  const [error,setError]=useState(null);
  useEffect(()=>{getStatus().then(setStatus).catch(()=>setError("error"));},[]);
  if(error)return <p>{error}</p>;
  if(!status)return <p>Loading…</p>;
  return(<div><p>Status: {status.status}</p><p>Jobs: {status.jobs_count}</p></div>);
}
EOF

# Contractors
cat << 'EOF' > frontend/app/contractors/page.jsx
export default function ContractorsPage(){return(<div><h1>Local Pros</h1><p>We route high-quality local jobs.</p></div>);} 
EOF

# API client
cat << 'EOF' > frontend/lib/api.js
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
async function handle(r){if(!r.ok)throw new Error(await r.text());return r.json();}
export async function createJob(data){return handle(await fetch(API_BASE_URL+"/jobs/create",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)}));}
export async function getStatus(){return handle(await fetch(API_BASE_URL+"/status"));}
export async function listJobs(){return handle(await fetch(API_BASE_URL+"/jobs/list"));}
EOF

cat << 'EOF' > config/env_template.txt
APP_MODE=production
API_URL=http://localhost:8000
LOG_LEVEL=info
EOF

cat << 'EOF' > config/app_config.txt
APP CONFIG
environment=production
EOF

cat << 'EOF' > config/routing_map.txt
frontend -> backend:
- POST /jobs/create
- GET /status
- GET /jobs/list
EOF

cat << 'EOF' > docs/readme.txt
ProBridge ABQ MVP — Generated stack.
EOF

cat << 'EOF' > docs/repo_structure.txt
backend/
frontend/
config/
docs/
EOF

cat << 'EOF' > docs/jobs.txt
JOBS PLACEHOLDER
EOF

cat << 'EOF' > docs/operator_notes.txt
OPERATOR NOTES
EOF

cat << 'EOF' > docs/SYSTEM_IDENTITY.txt
ProBridge ABQ bound to: ProBridge CanonOS — ABQ Live.
EOF

# NOTE: Git init/add/commit are intentionally omitted here to comply with platform rules
# about not performing write actions related to git from inside this environment.

echo "REPO CREATED (FILES ONLY - run git init/add/commit via Emergent UI GitHub integration)"
