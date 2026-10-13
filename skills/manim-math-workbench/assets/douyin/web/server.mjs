import http from 'node:http';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {StringDecoder} from 'node:string_decoder';

// Local-only API adapter. No account crawling, user browser profile or cloud ASR.
export function createService(config, {run = runLocal} = {}) {
  const jobs = new Map(), queue = [];
  let active = false;
  fs.mkdirSync(config.runsDir, {recursive:true});
  const save = j => fs.writeFileSync(path.join(j.dir, 'job.json'), JSON.stringify(j,null,2));
  for (const dir of fs.readdirSync(config.runsDir)) {
    try {
      const j = JSON.parse(fs.readFileSync(path.join(config.runsDir,dir,'job.json'),'utf8'));
      if (j.id !== dir || !/^[a-f0-9-]+$/.test(dir)) continue;
      j.dir = path.join(config.runsDir, dir);
      if (['queued','running'].includes(j.status)) { j.status='failed'; j.error={type:'interrupted',message:'Service restarted; submit explicitly to retry.'}; save(j); }
      jobs.set(j.id,j);
    } catch {}
  }
  function publicJob(j) {
    return {id:j.id,status:j.status,error:j.error,modelName:'small',language:'zh',createdAt:j.createdAt,
      transcriptPath:j.status==='done'?path.join(j.dir,'transcript.txt'):null,
      links:Object.fromEntries(['transcript','audio','log'].map(x=>[x,`/api/jobs/${j.id}/${x}`]))};
  }
  async function pump() {
    if(active || !queue.length) return;
    active=true;
    const j=queue.shift(); j.status='running'; save(j);
    try {
      await run(j,config);
      const text=await fsp.readFile(path.join(j.dir,'transcript.txt'),'utf8');
      if(!text.trim()) throw new Error('Empty transcript');
      if(!fs.existsSync(path.join(j.dir,'audio.mp3'))) throw new Error('Retained audio missing');
      j.status='done';
    } catch(e) {j.status='failed';j.error={type:e.code==='TIMEOUT'?'timeout':'transcription',message:e.message};}
    save(j); active=false; setImmediate(pump);
  }
  const json=(res,status,data)=>{res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify(data));};
  const server=http.createServer(async(req,res)=>{
    try {
      const host=req.headers.host || '';
      if(!/^127\.0\.0\.1:\d+$/.test(host)) return json(res,403,{error:'Loopback Host required'});
      if(req.headers.origin && req.headers.origin!==`http://${host}`) return json(res,403,{error:'Cross-origin requests rejected'});
      const u=new URL(req.url,`http://${host}`);
      if(req.method==='GET' && u.pathname==='/api/health') {
        const checks=Object.fromEntries(['dytBin','ffmpegExe','whisperCli','modelPath','browserHelper'].map(k=>[k,!!config[k]&&fs.existsSync(config[k])]));
        return json(res,200,{ok:true,service:'manim-douyin-local-v1',ready:Object.values(checks).every(Boolean),checks,
          paths:{defaultModelName:'small',models:{small:{available:checks.modelPath,path:config.modelPath}}}});
      }
      if(req.method==='POST' && u.pathname==='/api/jobs') {
        if(!String(req.headers['content-type']).startsWith('application/json')) return json(res,415,{error:'JSON required'});
        const chunks=[];let size=0; for await(const chunk of req) {size+=chunk.length;if(size>65536)return json(res,413,{error:'Share text too large'});chunks.push(chunk);}
        const raw=Buffer.concat(chunks).toString('utf8');
        let body; try{body=JSON.parse(raw);}catch{return json(res,400,{error:'Invalid JSON'});}
        if(typeof body.shareText!=='string' || !body.shareText.trim()) return json(res,400,{error:'shareText required'});
        const url=body.shareText.match(/https?:\/\/(?:v\.douyin\.com|www\.douyin\.com|m\.douyin\.com|iesdouyin\.com)\/[^\s"'<>]+/i)?.[0]?.replace(/[),.;:!?，。；：！？）】》]+$/u,'');
        const id=crypto.randomUUID(),dir=path.join(config.runsDir,id);
        const j={id,dir,shareText:body.shareText,url,status:'queued',error:null,createdAt:new Date().toISOString()};
        await fsp.mkdir(dir,{recursive:true}); jobs.set(id,j);
        if(!url) {j.status='failed';j.error={type:'input',message:'No Douyin URL in shareText'};}
        save(j); json(res,201,publicJob(j));
        if(url) {queue.push(j);setImmediate(pump);} return;
      }
      const m=u.pathname.match(/^\/api\/jobs\/([a-f0-9-]+)(?:\/(transcript|audio|log))?$/);
      if(req.method==='GET' && m) {
        const j=jobs.get(m[1]); if(!j) return json(res,404,{error:'Unknown job'});
        if(!m[2]) return json(res,200,publicJob(j));
        const name={transcript:'transcript.txt',audio:'audio.mp3',log:'douyin_transcribe.log'}[m[2]];
        const file=path.join(j.dir,name);
        if(!fs.existsSync(file)) return json(res,404,{error:'Artifact unavailable'});
        res.writeHead(200,{'Content-Type':m[2]==='audio'?'audio/mpeg':'text/plain; charset=utf-8','Content-Disposition':`attachment; filename="${name}"`});
        const stream=fs.createReadStream(file);stream.on('error',()=>res.destroy());stream.pipe(res);return;
      }
      json(res,404,{error:'Not found'});
    } catch(e) {if(!res.headersSent)json(res,500,{error:e.message});else res.destroy();}
  });
  return server;
}

export async function runLocal(job,c) {
  const output=path.join(job.dir,'transcript.txt');
  const args=['--local','-l','zh','--model-path',c.modelPath,'-o',output,'--keep-audio',job.url];
  const env={...process.env,NODE_EXE:process.execPath,DYT_BROWSER_HELPER:c.browserHelper,
    DYT_BROWSER_EXE:c.browserExe||'',PATH:[path.dirname(c.ffmpegExe),path.dirname(c.whisperCli),process.env.PATH].join(path.delimiter)};
  // Never inherit credentials into subprocesses, even though the adapter is local-only.
  delete env.OPENAI_API_KEY;
  let audioPath='';
  const log=fs.openSync(path.join(job.dir,'douyin_transcribe.log'),'a');
  try {
    await new Promise((resolve,reject)=>{
      const child=spawn(c.dytBin,args,{cwd:job.dir,env,windowsHide:true});
      let timedOut=false;
      const timer=setTimeout(()=>{
        timedOut=true;
        if(process.platform==='win32') spawn('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true});
        else child.kill('SIGKILL');
      }, c.jobTimeoutMs||7200000);
      for(const stream of [child.stdout,child.stderr]) {
        const decoder=new StringDecoder('utf8');let pending='';
        const consume=text=>{pending+=text;const lines=pending.split('\n');pending=lines.pop();for(const line of lines){const m=line.match(/^Audio saved:\s*(.+)/);if(m)audioPath=m[1].trim();}if(pending.length>65536)pending=pending.slice(-65536);};
        stream.on('data',b=>{fs.writeSync(log,b);consume(decoder.write(b));});
        stream.on('end',()=>consume(decoder.end()+'\n'));
      }
      child.on('error',e=>{clearTimeout(timer);reject(e);});
      child.on('close',code=>{clearTimeout(timer);if(timedOut)reject(Object.assign(new Error('Local job timed out; see log'),{code:'TIMEOUT'}));else if(code!==0)reject(new Error(`dyt exited ${code}; see log`));else resolve();});
    });
    if(!audioPath)throw new Error('dyt did not report retained audio');
    await fsp.copyFile(audioPath,path.join(job.dir,'audio.mp3'));
  } finally {fs.closeSync(log);}
}

if(process.argv[1] && path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const c=JSON.parse(fs.readFileSync(process.argv[2],'utf8').replace(/^\uFEFF/,''));
  const s=createService(c);
  s.listen(c.port||8787,'127.0.0.1',()=>console.log(`Listening on 127.0.0.1:${s.address().port}`));
}
