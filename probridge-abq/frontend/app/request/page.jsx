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
