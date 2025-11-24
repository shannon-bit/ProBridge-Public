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
