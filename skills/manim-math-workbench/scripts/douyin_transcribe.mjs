import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

export async function transcribe({baseUrl,configPath,shareText,jobId,outputDir,timeoutMs=7200000,pollMs=1500}) {
 const base=new URL(baseUrl);
 if(base.protocol!=='http:'||base.hostname!=='127.0.0.1'||base.username||base.password)throw new Error('Only http://127.0.0.1 is supported');
 if(!Number.isFinite(timeoutMs)||timeoutMs<=0||!Number.isFinite(pollMs)||pollMs<=0)throw new Error('Positive timeout and poll interval required');
 const deadline=Date.now()+timeoutMs;
 async function request(relative,options={}) {
  const url=new URL(relative,base);
  if(url.origin!==base.origin)throw new Error('Cross-origin artifact rejected');
  const remaining=deadline-Date.now();if(remaining<=0)throw Object.assign(new Error('Polling timeout; job continues, resume with job ID'),{code:'TIMEOUT',jobId});
  let r;
  try{r=await fetch(url,{...options,redirect:'error',signal:AbortSignal.timeout(Math.min(remaining,30000))});}
  catch(e){if(e.name==='TimeoutError'||e.name==='AbortError')throw Object.assign(new Error('HTTP wait timed out; inspect receipt before retrying'),{code:'TIMEOUT',jobId});throw e;}
  if(!r.ok)throw new Error(`HTTP ${r.status} ${relative}`);
  return r;
 }
 const health=await (await request('/api/health')).json();
 if(!health.ok || health.paths?.defaultModelName!=='small' || health.ready===false || health.checks?.model===false)throw new Error('Service must be healthy and configured for local small; refusing fallback');
 const required=health.service==='manim-douyin-local-v1'?['dytBin','ffmpegExe','whisperCli','modelPath','browserHelper']:['dyt','ffmpeg','whisper','model','browserHelper'];
 for(const key of required)if(health.checks?.[key]!==true)throw new Error(`Service dependency not ready: ${key}`);
 let job;
 if(jobId){if(!/^[a-zA-Z0-9-]+$/.test(jobId))throw new Error('Invalid job ID');job=await(await request(`/api/jobs/${jobId}`)).json();}
 else {
  if(typeof shareText!=='string'||!shareText.trim())throw new Error('Full share text or URL required');
  job=await(await request('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({shareText})})).json();
 }
 jobId=job.id;
 if(!/^[a-zA-Z0-9-]+$/.test(jobId||''))throw new Error('Service returned invalid job ID');
 const dir=path.resolve(outputDir,jobId);await fs.mkdir(dir,{recursive:true});
 await fs.writeFile(path.join(dir,'job-receipt.json'),JSON.stringify({jobId,baseUrl,configPath,sourceAudioRole:'reference-not-final-narration'},null,2));
 while(true) {
  await fs.writeFile(path.join(dir,'job-status.json'),JSON.stringify(job,null,2));
  if(job.status==='done')break;
  if(['failed','error','timeout'].includes(job.status))throw Object.assign(new Error(JSON.stringify(job.error||job)),{jobId,code:'JOB_FAILED'});
  if(!['queued','running'].includes(job.status))throw new Error(`Unexpected job status: ${job.status}`);
  if(Date.now()>=deadline)throw Object.assign(new Error('Polling timeout; job continues. Resume using job ID.'),{jobId,code:'TIMEOUT'});
  await new Promise(r=>setTimeout(r,Math.min(pollMs,Math.max(1,deadline-Date.now()))));
  job=await(await request(`/api/jobs/${jobId}`)).json();
 }
 const links={};
 for(const [kind,name] of [['transcript','transcript.txt'],['audio','source-audio.mp3']]) {
  const link=job.links?.[kind]||`/api/jobs/${jobId}/${kind}`;
  const response=await request(link);
  const bytes=Buffer.from(await response.arrayBuffer());if(!bytes.length)throw new Error(`Empty ${kind}`);
  const dest=path.join(dir,name);await fs.writeFile(dest+'.partial',bytes);await fs.rename(dest+'.partial',dest);
  links[kind]=new URL(link,base).href;
 }
 const result={jobId,status:'done',configPath,transcriptPath:path.join(dir,'transcript.txt'),sourceAudioPath:path.join(dir,'source-audio.mp3'),links,
  nextStage:'math-check-and-authorized-rewrite-then-recording-segments',sourceAudioRole:'reference-not-final-narration'};
 await fs.writeFile(path.join(dir,'result.json'),JSON.stringify(result,null,2));return result;
}
if(process.argv[1] && path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
 try {const input=JSON.parse(await fs.readFile(process.argv[2],'utf8'));if(input.shareTextFile)input.shareText=await fs.readFile(input.shareTextFile,'utf8');console.log(JSON.stringify(await transcribe(input),null,2));}
 catch(e){console.error(JSON.stringify({error:e.message,code:e.code,jobId:e.jobId}));process.exitCode=1;}
}
