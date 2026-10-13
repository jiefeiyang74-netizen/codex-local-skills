[CmdletBinding()]
param(
 [string]$ShareText,
 [string]$ShareTextFile,
 [string]$JobId,
 [string]$ConfigPath = (Join-Path $env:LOCALAPPDATA 'ManimMathWorkbench/douyin/config.json'),
 [string]$OutputDir = (Join-Path (Get-Location) 'douyin-inputs'),
 [ValidateRange(1,86400)][int]$TimeoutSeconds=7200,
 [switch]$HealthOnly
)
$ErrorActionPreference='Stop'
# Health is always the first service operation. Never restart an answering service.
$c=$null
if(Test-Path -LiteralPath $ConfigPath){$c=Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8|ConvertFrom-Json}
$port=8787;if($c){$port=$c.port}
$baseUrl="http://127.0.0.1:$port"
$health=$null
try{$health=Invoke-RestMethod "$baseUrl/api/health" -TimeoutSec 3}catch{}
if($HealthOnly){if(!$health){throw 'Service is not answering'};$health|ConvertTo-Json -Depth 8;return}
if(!$JobId -and !$ShareTextFile -and [string]::IsNullOrWhiteSpace($ShareText)){throw 'Supply ShareText / ShareTextFile, or JobId to resume.'}
if($ShareTextFile -and $ShareText){throw 'Choose ShareText or ShareTextFile'}
if(!$c){
 if($health -and $health.paths.browserHelper -and $health.paths.dytBin){
  $existing=Split-Path (Split-Path $health.paths.browserHelper -Parent) -Parent
  & "$PSScriptRoot/douyin_setup.ps1" -ConfigPath $ConfigPath -ExistingServiceDir $existing -Port $port
  $c=Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8|ConvertFrom-Json
 }elseif($health){
  $nodePath=& "$PSScriptRoot/douyin_setup.ps1" -NodeOnly
  $c=[pscustomobject]@{nodeExe=($nodePath|Select-Object -Last 1);legacy=$false}
 }else{
  & "$PSScriptRoot/douyin_setup.ps1" -ConfigPath $ConfigPath
  $c=Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8|ConvertFrom-Json
 }
}
# The existing legacy API accepts short links only. Use the portable adapter on
# a separate port for canonical URLs; preserve the original shareText unchanged.
$inputText=$ShareText
if($ShareTextFile){$inputText=[IO.File]::ReadAllText([IO.Path]::GetFullPath($ShareTextFile))}
if(!$JobId -and $c.legacy -and $inputText -notmatch 'https?://v\.douyin\.com/'){
 $directConfig=Join-Path (Split-Path $ConfigPath -Parent) 'direct-url-config.json'
 if(!(Test-Path $directConfig)){
  & "$PSScriptRoot/douyin_setup.ps1" -ConfigPath $directConfig -Port ([int]$c.port+1)
 }
 $ConfigPath=$directConfig;$c=Get-Content $ConfigPath -Raw -Encoding UTF8|ConvertFrom-Json
 $port=$c.port;$baseUrl="http://127.0.0.1:$port";$health=$null
 try{$health=Invoke-RestMethod "$baseUrl/api/health" -TimeoutSec 3}catch{}
}
if(!$health){
 # Do not replace an unknown listener (including a non-JSON health endpoint).
 $tcp=[Net.Sockets.TcpClient]::new()
 try{$tcp.Connect('127.0.0.1',[int]$port);$occupied=$true}catch{$occupied=$false}finally{$tcp.Dispose()}
 if($occupied){throw "Port $port is occupied by an unrecognized service; choose an isolated port in config."}
 $logDir=Split-Path $ConfigPath -Parent
 $launchArgs='"'+(Join-Path $PSScriptRoot 'douyin_launch.mjs')+'" "'+$ConfigPath+'"'
 $child=Start-Process -FilePath $c.nodeExe -ArgumentList $launchArgs -WorkingDirectory $c.serviceDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir 'server.stdout.log') -RedirectStandardError (Join-Path $logDir 'server.stderr.log')
 $child.Id|Set-Content (Join-Path $logDir 'launcher.pid')
 $until=(Get-Date).AddSeconds(30)
 do{Start-Sleep -Milliseconds 300;try{$health=Invoke-RestMethod "$baseUrl/api/health" -TimeoutSec 2}catch{}}while(!$health -and (Get-Date) -lt $until)
 if(!$health){throw "Service startup failed; inspect $logDir/server.stderr.log"}
}
$request=[ordered]@{baseUrl=$baseUrl;configPath=$ConfigPath;outputDir=[IO.Path]::GetFullPath($OutputDir);timeoutMs=$TimeoutSeconds*1000}
if($JobId){$request.jobId=$JobId}elseif($ShareTextFile){$request.shareTextFile=[IO.Path]::GetFullPath($ShareTextFile)}else{$request.shareText=$ShareText}
$temp=Join-Path ([IO.Path]::GetTempPath()) ('douyin-request-'+[Guid]::NewGuid().ToString()+'.json')
try{
 [IO.File]::WriteAllText($temp,($request|ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))
 & $c.nodeExe "$PSScriptRoot/douyin_transcribe.mjs" $temp
 if($LASTEXITCODE){throw 'Transcription did not complete; see structured error and job receipt. Do not automatically submit again.'}
}finally{Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue}
