import fs from 'node:fs';
import {spawn} from 'node:child_process';
const filename=process.argv[2];
const c=JSON.parse(fs.readFileSync(filename,'utf8').replace(/^\uFEFF/,''));
const env={...process.env,HOST:'127.0.0.1',PORT:String(c.port),DEFAULT_MODEL:'small',SMALL_MODEL_PATH:c.modelPath,
  DYT_BIN:c.dytBin,FFMPEG_EXE:c.ffmpegExe,WHISPER_CLI:c.whisperCli,DYT_BROWSER_HELPER:c.browserHelper,DYT_BROWSER_EXE:c.browserExe,
  RUNS_DIR:c.runsDir,ACCOUNT_RUNS_DIR:c.runsDir+'-unused-account'};
if(c.appRoot)env.APP_ROOT=c.appRoot;
// Legacy adapter needs --prompt support; use only explicitly configured legacy dyt.
const child=spawn(c.nodeExe,[c.serverPath,...(c.legacy?[]:[filename])],{cwd:c.serviceDir,env,windowsHide:true,stdio:'inherit'});
child.on('error',e=>{console.error(e.message);process.exitCode=1;});
child.on('exit',code=>{process.exitCode=code??1;});
