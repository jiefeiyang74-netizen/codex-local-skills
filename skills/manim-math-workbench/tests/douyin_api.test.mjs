import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {createService,runLocal} from '../assets/douyin/web/server.mjs';
import {transcribe} from '../scripts/douyin_transcribe.mjs';

const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function fixture(run){
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'douyin-api-fixture-'));
 const existing=process.execPath;
 const config={runsDir:path.join(root,'runs'),dytBin:existing,ffmpegExe:existing,whisperCli:existing,modelPath:existing,browserHelper:existing};
 const server=createService(config,{run});await new Promise(r=>server.listen(0,'127.0.0.1',r));
 return {root,config,server,baseUrl:`http://127.0.0.1:${server.address().port}`};
}
async function output(j){await fs.writeFile(path.join(j.dir,'transcript.txt'),'自制接口测试。\n');await fs.writeFile(path.join(j.dir,'audio.mp3'),'MOCK AUDIO, NOT ASR');}
const post=(baseUrl,text)=>fetch(baseUrl+'/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({shareText:text})});
test('real HTTP service with MOCK downstream: queued/running/done, full original shareText, downloads',async()=>{
 let release;const gate=new Promise(r=>release=r);let entered;const started=new Promise(r=>entered=r);
 const f=await fixture(async j=>{entered();await gate;await output(j);});
 try{
  const shareText='  中文分享全文\nhttps://v.douyin.com/FIXTURE/ 尾部文字  ';
  const j=await(await post(f.baseUrl,shareText)).json();assert.equal(j.status,'queued');await started;
  assert.equal((await(await fetch(f.baseUrl+'/api/jobs/'+j.id)).json()).status,'running');
  const saved=JSON.parse(await fs.readFile(path.join(f.config.runsDir,j.id,'job.json'),'utf8'));assert.equal(saved.shareText,shareText);
  release();const r=await transcribe({baseUrl:f.baseUrl,jobId:j.id,outputDir:f.root,pollMs:10,timeoutMs:3000});
  assert.equal(r.status,'done');assert.match(await fs.readFile(r.transcriptPath,'utf8'),/自制接口/);assert.equal(r.sourceAudioRole,'reference-not-final-narration');
  assert.match(await fs.readFile(r.sourceAudioPath,'utf8'),/MOCK AUDIO/);
 }finally{release();await new Promise(r=>f.server.close(r));}
});
test('real HTTP service + MOCK downstream: failed error, explicit worker timeout, input rejection, origin guard',async()=>{
 const f=await fixture(async j=>{throw Object.assign(new Error('fixture failure'),{code:j.shareText.includes('timeout')?'TIMEOUT':'FAIL'});});
 try{
  for(const kind of ['error','timeout']){
   await assert.rejects(transcribe({baseUrl:f.baseUrl,shareText:`${kind} https://v.douyin.com/FIXTURE/`,outputDir:f.root,pollMs:10,timeoutMs:3000}),e=>e.code==='JOB_FAILED'&&!!e.jobId);
  }
  const bad=await(await post(f.baseUrl,'https://127.0.0.1/private')).json();assert.equal(bad.status,'failed');
  assert.equal((await fetch(f.baseUrl+'/api/jobs',{method:'POST',headers:{Origin:'https://evil.example','Content-Type':'application/json'},body:'{}'})).status,403);
  assert.equal((await fetch(f.baseUrl+'/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:'{'})).status,400);
 }finally{await new Promise(r=>f.server.close(r));}
});
test('client timeout saves receipt; resume does not POST twice',async()=>{
 let release;const gate=new Promise(r=>release=r);
 const f=await fixture(async j=>{await gate;await output(j);});
 try{
  let id;
  await assert.rejects(transcribe({baseUrl:f.baseUrl,shareText:'https://v.douyin.com/FIXTURE/',outputDir:f.root,pollMs:10,timeoutMs:180}),e=>{id=e.jobId;return e.code==='TIMEOUT';});
  assert.ok(id);assert.equal(JSON.parse(await fs.readFile(path.join(f.root,id,'job-receipt.json'),'utf8')).jobId,id);
  release();await transcribe({baseUrl:f.baseUrl,jobId:id,outputDir:f.root,pollMs:10,timeoutMs:3000});
  assert.equal((await fs.readdir(f.config.runsDir)).length,1);
 }finally{release();await new Promise(r=>f.server.close(r));}
});
test('actual subprocess spawn failure is reported by real worker',async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'douyin-spawn-fixture-'));
 await assert.rejects(runLocal({dir:root,url:'https://v.douyin.com/FIXTURE/'},{dytBin:path.join(root,'missing.exe'),modelPath:'missing',ffmpegExe:process.execPath,whisperCli:process.execPath,browserHelper:'missing',jobTimeoutMs:1000}),/ENOENT/);
});
test('service restart marks unfinished jobs failed instead of rerunning',async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'douyin-restart-fixture-'));const id='1234-abcd';const dir=path.join(root,id);await fs.mkdir(dir);
 await fs.writeFile(path.join(dir,'job.json'),JSON.stringify({id,dir,status:'running'}));
 createService({runsDir:root});assert.equal(JSON.parse(await fs.readFile(path.join(dir,'job.json'),'utf8')).error.type,'interrupted');
});
test('shareText UTF-8 survives bytes split within a Chinese character',async()=>{
 const f=await fixture(async j=>output(j));
 try{
  const original='中文数学 https://v.douyin.com/FIXTURE/';const b=Buffer.from(JSON.stringify({shareText:original}));
  const split=b.indexOf(Buffer.from('中'))+1;
  const j=await new Promise((resolve,reject)=>{
   const req=http.request(f.baseUrl+'/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'}},r=>{let text='';r.on('data',c=>text+=c);r.on('end',()=>resolve(JSON.parse(text)));});
   req.on('error',reject);req.write(b.subarray(0,split));setTimeout(()=>req.end(b.subarray(split)),20);
  });
  await sleep(30);assert.equal(JSON.parse(await fs.readFile(path.join(f.config.runsDir,j.id,'job.json'),'utf8')).shareText,original);
 }finally{await new Promise(r=>f.server.close(r));}
});
test('real worker subprocess with MOCK CLI retains Chinese audio path before >128 KiB logs',{skip:!process.env.DOUYIN_MOCK_DYT},async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'douyin-long-log-'));
 await runLocal({dir:root,url:'https://v.douyin.com/FIXTURE/'},{dytBin:process.env.DOUYIN_MOCK_DYT,modelPath:'fixture',ffmpegExe:process.execPath,whisperCli:process.execPath,browserHelper:'fixture',jobTimeoutMs:5000});
 assert.equal(await fs.readFile(path.join(root,'audio.mp3'),'utf8'),'MOCK retained audio');
 assert.ok((await fs.stat(path.join(root,'douyin_transcribe.log'))).size>131072);
});
test('health dependency failure refuses POST',async()=>{
 let posts=0;const s=http.createServer((req,res)=>{if(req.method==='POST')posts++;res.setHeader('Content-Type','application/json');res.end(JSON.stringify({ok:true,paths:{defaultModelName:'small'},checks:{model:true,dyt:true,ffmpeg:false,whisper:true,browserHelper:true}}));});
 await new Promise(r=>s.listen(0,'127.0.0.1',r));
 try{await assert.rejects(transcribe({baseUrl:`http://127.0.0.1:${s.address().port}`,shareText:'test',outputDir:os.tmpdir()}),/ffmpeg/);assert.equal(posts,0);}finally{await new Promise(r=>s.close(r));}
});
test('real worker deadline kills MOCK subprocess and returns TIMEOUT',{skip:!process.env.DOUYIN_MOCK_DYT},async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'douyin-worker-timeout-'));
 const previous=process.env.DOUYIN_FIXTURE_HANG;process.env.DOUYIN_FIXTURE_HANG='1';
 try{await assert.rejects(runLocal({dir:root,url:'https://v.douyin.com/FIXTURE/'},{dytBin:process.env.DOUYIN_MOCK_DYT,modelPath:'fixture',ffmpegExe:process.execPath,whisperCli:process.execPath,browserHelper:'fixture',jobTimeoutMs:250}),e=>e.code==='TIMEOUT');}
 finally{if(previous===undefined)delete process.env.DOUYIN_FIXTURE_HANG;else process.env.DOUYIN_FIXTURE_HANG=previous;}
});
