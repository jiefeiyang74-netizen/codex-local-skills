import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn} from 'node:child_process';
import crypto from 'node:crypto';
import {createService} from '../assets/douyin/web/server.mjs';
import {transcribe} from '../scripts/douyin_transcribe.mjs';
const c=JSON.parse((await fs.readFile(process.argv[2],'utf8')).replace(/^\uFEFF/,''));
const root=path.resolve(process.argv[3]),start=Date.now();
const config={...c,runsDir:path.join(root,'runs')};
// Real HTTP + real local CLI/FFmpeg/whisper small zh, substituted local media input ONLY.
const server=createService(config,{run:async j=>{
 await new Promise((resolve,reject)=>{
  const proc=spawn(c.dytBin,['--audio',path.join(root,'fixture.mp3'),'--model-path',c.modelPath,'-l','zh','-o',path.join(j.dir,'transcript.txt')],{cwd:j.dir,windowsHide:true,
   env:{...process.env,PATH:[path.dirname(c.ffmpegExe),path.dirname(c.whisperCli),process.env.PATH].join(path.delimiter)}});
  let log='';for(const s of [proc.stdout,proc.stderr])s.on('data',b=>log+=b.toString());
  proc.on('error',reject);proc.on('close',async code=>{await fs.writeFile(path.join(j.dir,'douyin_transcribe.log'),log);code===0?resolve():reject(new Error(`fixture CLI exited ${code}`));});
 });
 await fs.copyFile(path.join(root,'fixture.mp3'),path.join(j.dir,'audio.mp3'));
}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
try{
 const result=await transcribe({baseUrl:`http://127.0.0.1:${server.address().port}`,shareText:'自制中文fixture，无抖音网络访问 https://v.douyin.com/FIXTURE/',outputDir:path.join(root,'delivery'),pollMs:300,timeoutMs:180000});
 const text=await fs.readFile(result.transcriptPath,'utf8');
 if(!/一加一|等于二|等於二|三角形/.test(text))throw new Error('Recognized speech lacks expected fixture phrase');
 const hash=async f=>crypto.createHash('sha256').update(await fs.readFile(f)).digest('hex');
 const retained=(await hash(result.sourceAudioPath))===(await hash(path.join(root,'fixture.mp3')));
 if(!retained)throw new Error('Retained audio hash mismatch');
 const report={kind:'synthetic-Chinese-audio-real-small-zh',douyinNetworkTested:false,elapsedMs:Date.now()-start,transcript:text,retainedAudioSHA256:await hash(result.sourceAudioPath),audioPreserved:retained,modelSHA256:await hash(c.modelPath),result};
 await fs.writeFile(path.join(root,'verification.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
}finally{await new Promise(r=>server.close(r));}
