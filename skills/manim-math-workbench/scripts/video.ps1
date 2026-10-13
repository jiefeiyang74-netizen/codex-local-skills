param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet('contract', 'smoke', 'run', 'analyze')]
    [string]$Command,
    [string]$RuntimeDir = (Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)) 'ManimMathWorkbench'),
    [string]$RuntimeConfig,
    [string]$Request,
    [string]$Storyboard,
    [string]$JobDir,
    [ValidateSet('preview', 'final')]
    [string]$Quality = 'preview'
)

$ErrorActionPreference = 'Stop'
try {
    if (-not $RuntimeConfig) { $RuntimeConfig = Join-Path $RuntimeDir 'runtime.json' }
    $RuntimeConfig = [IO.Path]::GetFullPath($RuntimeConfig)
    if (-not (Test-Path -LiteralPath $RuntimeConfig -PathType Leaf)) {
        throw "Runtime config missing: $RuntimeConfig. Run scripts/setup.ps1 first."
    }
    $config = Get-Content -LiteralPath $RuntimeConfig -Raw -Encoding UTF8 | ConvertFrom-Json
    $pythonExe = [string]$config.python_exe
    if (-not [IO.Path]::IsPathRooted($pythonExe) -or -not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
        throw 'runtime.json must contain an existing absolute python_exe path.'
    }
    $runnerArgs = @('-I', (Join-Path $PSScriptRoot 'video.py'), $Command)
    if ($Command -ne 'contract') {
        if (-not $JobDir) { throw '-JobDir is required for smoke and run.' }
        $runnerArgs += @('--job-dir', $JobDir, '--runtime-config', $RuntimeConfig)
    }
    if ($Command -eq 'run') {
        if (-not $Request -or -not $Storyboard) { throw '-Request and -Storyboard are required for run.' }
        $runnerArgs += @('--request', $Request, '--storyboard', $Storyboard, '--quality', $Quality)
    }
    if ($Command -eq 'analyze') {
        if (-not $Request) { throw '-Request is required for analyze.' }
        $runnerArgs += @('--request', $Request)
    }
    # Make the configured FFmpeg available to Manim/pydub, even without a
    # system installation. Only this launcher process and its children change.
    $savedPath = $env:PATH
    try {
        if ($config.ffmpeg_exe) {
            $env:PATH = (Split-Path -Parent ([string]$config.ffmpeg_exe)) + [IO.Path]::PathSeparator + $savedPath
        }
        & $pythonExe @runnerArgs
    }
    finally { $env:PATH = $savedPath }
    exit $LASTEXITCODE
}
catch {
    [Console]::Error.WriteLine('video launcher failed: ' + $_.Exception.Message)
    exit 1
}
