param([Parameter(Mandatory=$true)][string]$ConfigPath,[Parameter(Mandatory=$true)][string]$EvidenceDir)
$ErrorActionPreference='Stop'
New-Item -ItemType Directory -Path $EvidenceDir -Force|Out-Null
$EvidenceDir=[IO.Path]::GetFullPath($EvidenceDir)
$c=Get-Content $ConfigPath -Raw -Encoding UTF8|ConvertFrom-Json
Add-Type -AssemblyName System.Speech
$speaker=[System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
 $voice=$speaker.GetInstalledVoices()|Where-Object {$_.VoiceInfo.Culture.Name -eq 'zh-CN'}|Select-Object -First 1
 if(!$voice){throw 'Install a Chinese Windows speech voice for the synthetic fixture; do not substitute private recordings.'}
 $speaker.SelectVoice($voice.VoiceInfo.Name)
 $speaker.SetOutputToWaveFile((Join-Path $EvidenceDir 'fixture.wav'))
 $speaker.Speak('这是本地语音识别测试。一加一等于二。三角形的内角和是一百八十度。')
}finally{$speaker.Dispose()}
& $c.ffmpegExe -y -hide_banner -loglevel error -i (Join-Path $EvidenceDir 'fixture.wav') (Join-Path $EvidenceDir 'fixture.mp3')
if($LASTEXITCODE){throw 'Fixture MP3 conversion failed'}
& $c.nodeExe (Join-Path $PSScriptRoot 'douyin_real_fixture.mjs') $ConfigPath $EvidenceDir
if($LASTEXITCODE){throw 'Real small zh fixture failed'}
