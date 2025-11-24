const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
async function handle(r){if(!r.ok)throw new Error(await r.text());return r.json();}
export async function createJob(data){return handle(await fetch(API_BASE_URL+"/jobs/create",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)}));}
export async function getStatus(){return handle(await fetch(API_BASE_URL+"/status"));}
export async function listJobs(){return handle(await fetch(API_BASE_URL+"/jobs/list"));}
