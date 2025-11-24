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
