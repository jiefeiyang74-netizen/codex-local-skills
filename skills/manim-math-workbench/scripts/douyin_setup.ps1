[CmdletBinding()]
param(
 [string]$RuntimeDir = (Join-Path $env:LOCALAPPDATA 'ManimMathWorkbench/douyin'),
 [string]$ConfigPath,
 [string]$ManimRuntimeConfig = (Join-Path $env:LOCALAPPDATA 'ManimMathWorkbench/runtime.json'),
 [string]$ExistingServiceDir,
 [string]$NodeExe,
 [string]$GoExe,
 [int]$Port = 8787,
 [switch]$NodeOnly,
 [switch]$CheckOnly
)
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
$SkillRoot=Split-Path $PSScriptRoot -Parent
$RuntimeDir=[IO.Path]::GetFullPath($RuntimeDir)
if(!$ConfigPath){$ConfigPath=Join-Path $RuntimeDir 'config.json'}
$ConfigPath=[IO.Path]::GetFullPath($ConfigPath)
if($RuntimeDir.StartsWith($SkillRoot,[StringComparison]::OrdinalIgnoreCase) -or $ConfigPath.StartsWith($SkillRoot,[StringComparison]::OrdinalIgnoreCase)){throw 'Runtime and config must be outside the distributable Skill.'}
if($Port -lt 1024 -or $Port -gt 65535){throw 'Invalid port'}
function Write-Json($File,$Data){[IO.File]::WriteAllText($File,($Data|ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))}
if($CheckOnly){
 $c=Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8|ConvertFrom-Json
 foreach($k in @('nodeExe','serverPath','dytBin','ffmpegExe','whisperCli','modelPath','browserHelper')){if(!(Test-Path -LiteralPath $c.$k -PathType Leaf)){throw "Missing $k"}}
 & $c.nodeExe --version
 if($LASTEXITCODE){throw 'Node check failed'}
 Write-Output 'douyin runtime paths ready (not a live Douyin extraction test)';return
}
New-Item -ItemType Directory -Path $RuntimeDir -Force|Out-Null
New-Item -ItemType Directory -Path (Split-Path $ConfigPath -Parent) -Force|Out-Null
$lock=Get-Content "$SkillRoot/assets/douyin/runtime-lock.json" -Raw|ConvertFrom-Json
$mediaLock=Get-Content "$SkillRoot/assets/runtime-lock.json" -Raw|ConvertFrom-Json
function Install-Locked($Item,$Name){
 $dest=Join-Path $RuntimeDir $Name
 $stamp=Join-Path $dest '.archive-sha256'
 if((Test-Path $stamp) -and ((Get-Content $stamp -Raw).Trim() -eq $Item.sha256)){
  $found=Get-ChildItem $dest -Recurse -File -Filter $Item.executable|Select-Object -First 1
  if($found){return $found.FullName}
 }
 $zip=Join-Path $RuntimeDir "$Name.zip"
 if(!(Test-Path $zip) -or (Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Item.sha256){
  Invoke-WebRequest $Item.url -OutFile "$zip.partial" -UseBasicParsing
  if((Get-FileHash "$zip.partial" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Item.sha256){throw "$Name checksum mismatch"}
  Move-Item -LiteralPath "$zip.partial" -Destination $zip -Force
 }
 Expand-Archive -LiteralPath $zip -DestinationPath $dest -Force
 $found=Get-ChildItem $dest -Recurse -File -Filter $Item.executable|Select-Object -First 1
 if(!$found){throw "$Name executable missing"}
 [IO.File]::WriteAllText($stamp,$Item.sha256)
 return $found.FullName
}
if(!$NodeExe){$cmd=Get-Command node.exe -ErrorAction SilentlyContinue;if($cmd){$NodeExe=$cmd.Source}}
if($NodeExe){$v=& $NodeExe -p 'process.versions.node.split(".")[0]';if($LASTEXITCODE -or [int]$v -lt 20){$NodeExe=$null}}
if(!$NodeExe){$NodeExe=Install-Locked $lock.node 'node'}
if($NodeOnly){Write-Output $NodeExe;return}
if($ExistingServiceDir){
 $ExistingServiceDir=[IO.Path]::GetFullPath($ExistingServiceDir)
 if(!(Test-Path "$ExistingServiceDir/server.mjs")){throw 'Existing server.mjs missing'}
 $h=$null;try{$h=Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 3}catch{}
 if(!$h -or !$h.paths.dytBin){throw 'To adopt a legacy service, first start it normally so health can report its own dependency paths.'}
 foreach($key in @('dyt','ffmpeg','whisper','browserHelper','model')){if($h.checks.$key -ne $true){throw "Legacy dependency not ready: $key"}}
 if($h.paths.defaultModelName -ne 'small'){throw 'Legacy service is not configured for small; do not alter a live service automatically.'}
 $legacyRoot=Split-Path (Split-Path $ExistingServiceDir -Parent) -Parent
 $portableDir=Join-Path $RuntimeDir 'outputs/douyin-web'
 $c=[ordered]@{schemaVersion=1;port=$Port;nodeExe=$NodeExe;portableServiceDir=$portableDir;serverPath=(Join-Path $ExistingServiceDir 'server.mjs');serviceDir=$ExistingServiceDir;legacy=$true;appRoot=$legacyRoot;
 dytBin=$h.paths.dytBin;ffmpegExe=$h.paths.ffmpegExe;whisperCli=$h.paths.whisperCli;modelPath=$h.paths.models.small.path;browserHelper=$h.paths.browserHelper;browserExe='';runsDir=(Join-Path $ExistingServiceDir 'runs');jobTimeoutMs=7200000}
 if(Test-Path $ConfigPath){Copy-Item -LiteralPath $ConfigPath -Destination ($ConfigPath+'.backup-'+(Get-Date -Format yyyyMMddHHmmssfff))}
 Write-Json $ConfigPath $c
 Write-Output "Adopted healthy legacy service without downloads/build: $ConfigPath";return
}
$r=$null
if(Test-Path -LiteralPath $ManimRuntimeConfig){$r=Get-Content -LiteralPath $ManimRuntimeConfig -Raw -Encoding UTF8|ConvertFrom-Json}
$ffmpeg=$r.ffmpeg_exe;$whisper=$r.whisper_exe;$model=$r.whisper_model
if(!$ffmpeg -or !(Test-Path -LiteralPath $ffmpeg)){$i=$mediaLock.ffmpeg;$i.executable='ffmpeg.exe';$ffmpeg=Install-Locked $i 'ffmpeg'}
if(!$whisper -or !(Test-Path -LiteralPath $whisper)){$i=$mediaLock.whisper;$i.executable='whisper-cli.exe';$whisper=Install-Locked $i 'whisper'}
if(!$model -or !(Test-Path -LiteralPath $model)){
 $model=Join-Path $RuntimeDir 'ggml-small.bin'
 if(!(Test-Path $model)){
  Invoke-WebRequest $mediaLock.whisper_model.url -OutFile "$model.partial" -UseBasicParsing
  if((Get-FileHash "$model.partial" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $mediaLock.whisper_model.sha256){throw 'small model checksum mismatch'}
  Move-Item -LiteralPath "$model.partial" -Destination $model -Force
 }
}
if((Get-FileHash $model -Algorithm SHA256).Hash.ToLowerInvariant() -ne $mediaLock.whisper_model.sha256){throw 'Required small model hash mismatch; no base/cloud fallback'}
$serviceDir=Join-Path $RuntimeDir 'outputs/douyin-web'
New-Item -ItemType Directory -Path $serviceDir -Force|Out-Null
Copy-Item "$SkillRoot/assets/douyin/web/*" $serviceDir -Recurse -Force
$npm=Join-Path (Split-Path $NodeExe -Parent) 'node_modules/npm/bin/npm-cli.js'
if(!(Test-Path $npm)){throw 'Node installation needs npm-cli.js; supply full official Node distribution'}
$oldPath=$env:PATH
try {
 $env:PATH=(Split-Path $NodeExe -Parent)+';'+$oldPath
 Push-Location $serviceDir
 try {
  $npmHash=(Get-FileHash 'package-lock.json' -Algorithm SHA256).Hash
  $npmStamp=Join-Path $serviceDir '.npm-lock-sha256'
  if(!(Test-Path 'node_modules/playwright-core/package.json') -or !(Test-Path $npmStamp) -or (Get-Content $npmStamp -Raw).Trim() -ne $npmHash){
   & $NodeExe $npm ci --ignore-scripts --no-audit --no-fund;if($LASTEXITCODE){throw 'npm ci failed'}
   [IO.File]::WriteAllText($npmStamp,$npmHash)
  }
 }finally{Pop-Location}
}finally{$env:PATH=$oldPath}
$browser=@("${env:ProgramFiles}/Microsoft/Edge/Application/msedge.exe","${env:ProgramFiles(x86)}/Microsoft/Edge/Application/msedge.exe","${env:ProgramFiles}/Google/Chrome/Application/chrome.exe")|Where-Object {Test-Path -LiteralPath $_}|Select-Object -First 1
if(!$browser){
 $oldBrowsers=$env:PLAYWRIGHT_BROWSERS_PATH
 try{$env:PLAYWRIGHT_BROWSERS_PATH=Join-Path $RuntimeDir 'browsers'; & $NodeExe "$serviceDir/node_modules/playwright-core/cli.js" install chromium;if($LASTEXITCODE){throw 'Chromium install failed'}
 $browser=(Get-ChildItem $env:PLAYWRIGHT_BROWSERS_PATH -Recurse -Filter chrome.exe|Select-Object -First 1).FullName
 }finally{$env:PLAYWRIGHT_BROWSERS_PATH=$oldBrowsers}
 if(!$browser){throw 'Browser unavailable'}
}
$dyt=Join-Path $RuntimeDir 'dyt-local.exe'
$sourceHash=((Get-ChildItem "$SkillRoot/assets/douyin/source" -Recurse -File|Sort-Object FullName|ForEach-Object{(Get-FileHash $_.FullName -Algorithm SHA256).Hash}) -join ':')
$buildStamp=Join-Path $RuntimeDir '.dyt-source-sha256'
if(!$GoExe -and (Test-Path $ConfigPath)){$previous=Get-Content $ConfigPath -Raw|ConvertFrom-Json;if($previous.goExe -and (Test-Path $previous.goExe)){$GoExe=$previous.goExe}}
if(!(Test-Path $dyt) -or !(Test-Path $buildStamp) -or (Get-Content $buildStamp -Raw).Trim() -ne $sourceHash){
if(!$GoExe){$cmd=Get-Command go.exe -ErrorAction SilentlyContinue;if($cmd){$GoExe=$cmd.Source}}
if(!$GoExe){$GoExe=Install-Locked $lock.go 'go'}
$oldToolchain=$env:GOTOOLCHAIN
try {
 $env:GOTOOLCHAIN='local'
 Push-Location "$SkillRoot/assets/douyin/source"
 try {& $GoExe build -trimpath -o "$dyt.new.exe" .;if($LASTEXITCODE){throw 'Go build failed'}}finally{Pop-Location}
 Move-Item -LiteralPath "$dyt.new.exe" -Destination $dyt -Force
 [IO.File]::WriteAllText($buildStamp,$sourceHash)
}finally{$env:GOTOOLCHAIN=$oldToolchain}
}
$c=[ordered]@{schemaVersion=1;port=$Port;nodeExe=$NodeExe;goExe=$GoExe;portableServiceDir=$serviceDir;serverPath=(Join-Path $serviceDir 'server.mjs');serviceDir=$serviceDir;legacy=$false;dytBin=$dyt;ffmpegExe=$ffmpeg;whisperCli=$whisper;modelPath=$model;browserHelper=(Join-Path $serviceDir 'scripts/fetch_douyin_media.mjs');browserExe=$browser;runsDir=(Join-Path $RuntimeDir 'runs');jobTimeoutMs=7200000}
if($ExistingServiceDir){
 $ExistingServiceDir=[IO.Path]::GetFullPath($ExistingServiceDir)
 if(!(Test-Path "$ExistingServiceDir/server.mjs")){throw 'Existing server.mjs missing'}
 $c.legacy=$true;$c.serviceDir=$ExistingServiceDir;$c.serverPath=Join-Path $ExistingServiceDir 'server.mjs'
}
if(Test-Path $ConfigPath){Copy-Item -LiteralPath $ConfigPath -Destination ($ConfigPath+'.backup-'+(Get-Date -Format yyyyMMddHHmmssfff))}
Write-Json $ConfigPath $c
Write-Output "Configured: $ConfigPath"
