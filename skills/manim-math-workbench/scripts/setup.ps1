[CmdletBinding()]
param(
    [string]$RuntimeDir = (Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)) "ManimMathWorkbench"),
    [string]$ConfigPath,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$PackageRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$LockPath = Join-Path $PackageRoot "assets\runtime-lock.json"
$RuntimeDir = [IO.Path]::GetFullPath($RuntimeDir)
$ConfigPathProvided = ($ConfigPath -and $ConfigPath.Trim().Length -gt 0)
if (-not $ConfigPathProvided) { $ConfigPath = Join-Path $RuntimeDir "runtime.json" }
$ConfigPath = [IO.Path]::GetFullPath($ConfigPath)

function Fail([string]$Message) { throw $Message }

function Read-Lock {
    if (-not (Test-Path -LiteralPath $LockPath -PathType Leaf)) { Fail "Missing runtime lock: $LockPath" }
    try { $lock = Get-Content -LiteralPath $LockPath -Raw -Encoding UTF8 | ConvertFrom-Json }
    catch { Fail "Runtime lock is not valid JSON: $LockPath" }
    if ([int]$lock.schema_version -ne 1) { Fail "Unsupported runtime lock schema: $($lock.schema_version)" }
    foreach ($section in @("uv", "python", "whisper", "whisper_model", "ffmpeg")) {
        if ($null -eq $lock.$section) { Fail "Runtime lock is missing section: $section" }
    }
    if ([string]$lock.target.os -ne "windows" -or [string]$lock.target.architecture -ne "x86_64") { Fail "Runtime lock target is not Windows x86_64." }
    if ($lock.target.tex_required -ne $false) { Fail "This setup supports the Text-only engine and does not install TeX." }
    if ([string]$lock.target.font_name -ne "Microsoft YaHei") { Fail "The locked engine font must be Microsoft YaHei." }
    return $lock
}

function Get-FullPath([string]$Value) { return [IO.Path]::GetFullPath($Value) }

function Test-PathUnder([string]$Child, [string]$Parent) {
    $childFull = (Get-FullPath $Child).TrimEnd('\')
    $parentFull = (Get-FullPath $Parent).TrimEnd('\') + '\'
    return $childFull.StartsWith($parentFull, [StringComparison]::OrdinalIgnoreCase)
}

function Ensure-Directory([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
    return (Get-FullPath $Path)
}

function Remove-Staging([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        if (-not (Test-PathUnder $Path (Join-Path $RuntimeDir ".staging"))) {
            Fail "Refusing to delete a path outside the staging root: $Path"
        }
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Write-Utf8NoBom([string]$Path, [string]$Text) {
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($Path, $Text, $encoding)
}

function Invoke-Checked([string]$Executable, [string[]]$Arguments, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) { Fail "$Label does not exist: $Executable" }
    # Native tools often report progress on stderr. Capture it without letting
    # Windows PowerShell 5.1's Stop preference abort on the first progress line.
    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = @(& $Executable @Arguments 2>&1)
        $code = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $previousErrorAction }
    if ($code -ne 0) {
        $tail = (($output | ForEach-Object { [string]$_ }) -join "`n")
        if ($tail.Length -gt 1200) { $tail = $tail.Substring($tail.Length - 1200) }
        Fail "$Label failed (exit $code): $Executable`n$tail"
    }
    return (($output | ForEach-Object { [string]$_ }) -join "`n")
}

function Download-Verified([object]$Spec, [string]$Destination, [Nullable[Int64]]$ExpectedSize) {
    $destination = Get-FullPath $Destination
    $parent = Split-Path -Parent $destination
    Ensure-Directory $parent | Out-Null
    try { $uri = [Uri]([string]$Spec.url) } catch { Fail "Invalid download URL: $([string]$Spec.url)" }
    if ($uri.Scheme -ne "https") { Fail "Only HTTPS download URLs are allowed: $uri" }
    $expectedHash = ([string]$Spec.sha256).ToLowerInvariant()
    if ($expectedHash -notmatch '^[0-9a-f]{64}$') { Fail "Invalid locked SHA-256 for download: $destination" }
    if (Test-Path -LiteralPath $destination -PathType Leaf) {
        $sizeOkay = $true
        if ($ExpectedSize.HasValue) { $sizeOkay = ([IO.FileInfo]::new($destination).Length -eq $ExpectedSize.Value) }
        if ($sizeOkay -and (Get-Sha256 $destination) -eq $expectedHash) { return $destination }
        Remove-Item -LiteralPath $destination -Force
    }
    $temp = Join-Path $parent ("." + [IO.Path]::GetFileName($destination) + "." + [Guid]::NewGuid().ToString("N") + ".part")
    try {
        Write-Host ("Downloading pinned dependency: " + [IO.Path]::GetFileName($destination))
        Add-Type -AssemblyName System.Net.Http
        $client = New-Object System.Net.Http.HttpClient
        $response = $null
        $input = $null
        $output = $null
        try {
            $client.Timeout = [TimeSpan]::FromMinutes(30)
            $client.DefaultRequestHeaders.UserAgent.ParseAdd("manim-math-workbench-setup/1")
            $response = $client.GetAsync($uri, [Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
            $null = $response.EnsureSuccessStatusCode()
            $input = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
            $output = [IO.File]::Open($temp, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::None)
            $null = $input.CopyToAsync($output).GetAwaiter().GetResult()
        }
        finally {
            if ($output) { $output.Dispose() }
            if ($input) { $input.Dispose() }
            if ($response) { $response.Dispose() }
            if ($client) { $client.Dispose() }
        }
        if (-not (Test-Path -LiteralPath $temp -PathType Leaf)) { Fail "Download did not produce a file: $([string]$Spec.url)" }
        if ($ExpectedSize.HasValue -and ([IO.FileInfo]::new($temp).Length -ne $ExpectedSize.Value)) {
            Fail "Downloaded size mismatch: $([IO.FileInfo]::new($temp).Length), expected $($ExpectedSize.Value)"
        }
        $actual = Get-Sha256 $temp
        if ($actual -ne $expectedHash) { Fail "Downloaded SHA-256 mismatch: $actual, expected $expectedHash" }
        Move-Item -LiteralPath $temp -Destination $destination
    }
    catch {
        if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue }
        Fail ("Dependency download or verification failed (ready runtime was not written): " + $_.Exception.Message)
    }
    return $destination
}

function Expand-SafeZip([string]$ZipPath, [string]$Destination) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $destination = Ensure-Directory $Destination
    $root = $destination.TrimEnd('\') + '\'
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $archive = [IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        foreach ($entry in $archive.Entries) {
            $entryName = ([string]$entry.FullName).Replace('/', '\')
            if ([string]::IsNullOrWhiteSpace($entryName)) { continue }
            if ($entryName.StartsWith('\') -or $entryName -match '^[A-Za-z]:') { Fail "ZIP contains an absolute path: $($entry.FullName)" }
            $parts = $entryName.Split('\')
            if (@($parts | Where-Object { $_ -eq '..' }).Count -gt 0) { Fail "ZIP contains path traversal: $($entry.FullName)" }
            $target = [IO.Path]::GetFullPath((Join-Path $destination $entryName))
            if (-not $target.StartsWith($root, [StringComparison]::OrdinalIgnoreCase) -and $target -ne $destination) {
                Fail "ZIP target escapes staging directory: $($entry.FullName)"
            }
            if ($entry.FullName.EndsWith('/')) {
                Ensure-Directory $target | Out-Null
                continue
            }
            if (-not $seen.Add($target)) { Fail "ZIP contains a duplicate file: $($entry.FullName)" }
            Ensure-Directory (Split-Path -Parent $target) | Out-Null
            $input = $entry.Open()
            $output = [IO.File]::Open($target, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
            try { $input.CopyTo($output) }
            finally { $output.Dispose(); $input.Dispose() }
        }
    }
    finally { $archive.Dispose() }
}

function Move-IntoPlace([string]$Staged, [string]$Final) {
    if (-not (Test-PathUnder $Staged (Join-Path $RuntimeDir ".staging"))) { Fail "Refusing to publish a path outside staging: $Staged" }
    $final = Get-FullPath $Final
    Ensure-Directory (Split-Path -Parent $final) | Out-Null
    $backup = $null
    if (Test-Path -LiteralPath $final) {
        $backup = "$final.invalid.$([DateTime]::UtcNow.ToString('yyyyMMddHHmmss')).$([Guid]::NewGuid().ToString('N'))"
        Move-Item -LiteralPath $final -Destination $backup
    }
    try {
        Move-Item -LiteralPath $Staged -Destination $final
    }
    catch {
        if ($backup -and (Test-Path -LiteralPath $backup) -and -not (Test-Path -LiteralPath $final)) {
            Move-Item -LiteralPath $backup -Destination $final -ErrorAction SilentlyContinue
        }
        throw
    }
    return $final
}

function Get-ExistingJson([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try { return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json) }
    catch { return $null }
}

function Test-Font([object]$Lock) {
    $fontCandidates = @(
        (Join-Path $env:WINDIR "Fonts\msyh.ttc"),
        (Join-Path $env:WINDIR "Fonts\msyh.ttf"),
        (Join-Path $env:WINDIR "Fonts\msyhl.ttc")
    )
    foreach ($candidate in $fontCandidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return (Get-FullPath $candidate) }
    }
    Fail "Windows font Microsoft YaHei (msyh.ttc) is missing; setup will not modify system fonts."
}

function Test-PythonRuntime([string]$PythonExe) {
    # Avoid quote characters in the native -c argument: Windows PowerShell 5.1
    # otherwise strips JSON quotes while constructing the process command line.
    $code = 'import sys,struct,manim,av,PIL; print(str(sys.version_info[0])+chr(46)+str(sys.version_info[1])+chr(46)+str(sys.version_info[2])+chr(124)+str(struct.calcsize(chr(80))*8)+chr(124)+manim.__version__+chr(124)+av.__version__+chr(124)+PIL.__version__)'
    $raw = Invoke-Checked $PythonExe @('-I', '-c', $code) "Python/Manim runtime"
    $line = @($raw -split "`r?`n" | Where-Object { $_.Trim().Contains('|') }) | Select-Object -Last 1
    $parts = ([string]$line).Trim().Split('|')
    if ($parts.Count -lt 5) { Fail "Python runtime probe returned no version record: $raw" }
    $info = [pscustomobject]@{ python = $parts[0]; pointer_bits = [int]$parts[1]; manim = $parts[2]; av = $parts[3]; pillow = $parts[4] }
    if ([string]$info.python -ne [string]$Lock.python.version) { Fail "Python version mismatch: $($info.python), expected $($Lock.python.version)" }
    if ([int]$info.pointer_bits -ne 64) { Fail "Python is not 64-bit: $($info.pointer_bits) bit" }
    if ([string]$info.manim -ne "0.19.0") { Fail "Manim version mismatch: $($info.manim), expected 0.19.0" }
    if ([string]$info.av -ne "13.1.0") { Fail "PyAV version mismatch: $($info.av), expected 13.1.0" }
    if ([string]$info.pillow -ne "12.3.0") { Fail "Pillow version mismatch: $($info.pillow), expected 12.3.0" }
    return $info
}

function Test-Tools([string]$PythonExe, [string]$FfmpegExe, [string]$WhisperExe, [string]$ModelPath) {
    $pythonInfo = Test-PythonRuntime $PythonExe
    $ffmpegOutput = Invoke-Checked $FfmpegExe @('-hide_banner', '-version') "FFmpeg"
    if ($ffmpegOutput -notmatch 'ffmpeg version') { Fail "Unrecognized FFmpeg version output: $FfmpegExe" }
    $whisperOutput = Invoke-Checked $WhisperExe @('--help') "Whisper.cpp"
    if ($whisperOutput -notmatch '(?i)whisper') { Fail "Unrecognized Whisper.cpp help output: $WhisperExe" }
    if (-not (Test-Path -LiteralPath $ModelPath -PathType Leaf)) { Fail "Whisper model does not exist: $ModelPath" }
    $modelSpec = $Lock.whisper_model
    if ([IO.FileInfo]::new($ModelPath).Length -ne [Int64]$modelSpec.size_bytes) { Fail "Whisper model size mismatch: $ModelPath" }
    if ((Get-Sha256 $ModelPath) -ne ([string]$modelSpec.sha256).ToLowerInvariant()) { Fail "Whisper model SHA-256 mismatch: $ModelPath" }
    return $pythonInfo
}

function Test-ReadyConfig([object]$Config, [string]$ExpectedLockHash) {
    if ($null -eq $Config -or $Config.ready -ne $true) { return $false }
    if ([string]$Config.lock_sha256 -ne $ExpectedLockHash) { return $false }
    $expectedEngine = Get-FullPath (Join-Path $PackageRoot "assets\engine")
    # The runtime is reusable across package copies; the runner always uses
    # this package's engine, never the historical engine_root in runtime.json.
    if (-not (Test-Path -LiteralPath (Join-Path $expectedEngine "v3\runtime_template.py") -PathType Leaf)) { return $false }
    foreach ($key in @('python_exe', 'ffmpeg_exe', 'whisper_exe', 'whisper_model')) {
        $value = [string]$Config.$key
        $absolute = ($value -match '^[A-Za-z]:[\\/]' -or $value -match '^\\\\')
        if (-not $absolute -or -not (Test-Path -LiteralPath $value -PathType Leaf)) { return $false }
    }
    return $true
}

function Get-LockDigest { return (Get-Sha256 $LockPath) }

try {
    $Lock = Read-Lock
    $LockDigest = Get-LockDigest
    $processArch = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
    if (-not [Environment]::Is64BitOperatingSystem -or [Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or $processArch -notmatch '^(AMD64|x86_64)$') {
        Fail "Only Windows x64 is supported; this operating system is not supported."
    }
    $fontPath = Test-Font $Lock
    $existing = Get-ExistingJson $ConfigPath
    if (Test-ReadyConfig $existing $LockDigest) {
        try {
            $existingInfo = Test-Tools ([string]$existing.python_exe) ([string]$existing.ffmpeg_exe) ([string]$existing.whisper_exe) ([string]$existing.whisper_model)
            if (-not $ConfigPathProvided -and -not $CheckOnly) {
                $compatConfig = Join-Path $RuntimeDir "runtime-config.json"
                $compatTemp = Join-Path $RuntimeDir (".runtime-config.json." + [Guid]::NewGuid().ToString("N") + ".tmp")
                Write-Utf8NoBom $compatTemp (Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8)
                Move-Item -LiteralPath $compatTemp -Destination $compatConfig -Force
            }
            Write-Output "Existing runtime is valid: $ConfigPath"
            Write-Output ("python={0}; manim={1}; font={2}" -f $existingInfo.python, $existingInfo.manim, $fontPath)
            return
        }
        catch {
            if ($CheckOnly) { throw }
            Write-Warning ("Existing runtime.json failed verification; rebuilding in isolated staging: " + $_.Exception.Message)
        }
    }
    elseif ($CheckOnly) {
        Fail "No valid ready runtime.json was found, or its lock version is stale: $ConfigPath"
    }

    $stagingBase = Join-Path $RuntimeDir ".staging"
    $stage = Join-Path $stagingBase ([Guid]::NewGuid().ToString("N"))
    $volumeRoot = [IO.Path]::GetPathRoot($RuntimeDir)
    $driveName = $volumeRoot.TrimEnd('\').TrimEnd(':')
    $drive = Get-PSDrive -Name $driveName -ErrorAction SilentlyContinue
    if ($null -eq $drive) { Fail "Cannot check free space for target volume: $volumeRoot" }
    $freeBytes = [Int64]$drive.Free
    $requiredFree = [Int64](5GB)
    if ($freeBytes -lt $requiredFree) {
        Fail ("Insufficient free space on target volume: {0:N1} GB available, at least {1:N1} GB required; use -RuntimeDir on a larger volume." -f ($freeBytes / 1GB), ($requiredFree / 1GB))
    }

    Ensure-Directory $RuntimeDir | Out-Null
    Ensure-Directory $stagingBase | Out-Null
    Ensure-Directory $stage | Out-Null
    $oldUvCache = $env:UV_CACHE_DIR
    $oldTemp = $env:TEMP
    $oldTmp = $env:TMP
    $env:UV_CACHE_DIR = Ensure-Directory (Join-Path $RuntimeDir "cache\uv")
    $runtimeTemp = Ensure-Directory (Join-Path $RuntimeDir "cache\tmp")
    $env:TEMP = $runtimeTemp
    $env:TMP = $runtimeTemp
    try {
        $downloadRoot = Ensure-Directory (Join-Path $RuntimeDir "cache\downloads")

        $uvFinal = Join-Path $RuntimeDir ("tools\uv\" + [string]$Lock.uv.version)
        $uvExe = Join-Path $uvFinal "uv.exe"
        $uvReusable = $false
        if (Test-Path -LiteralPath $uvExe -PathType Leaf) {
            try { $uvReusable = (Invoke-Checked $uvExe @('--version') "uv") -match ([string]$Lock.uv.version) } catch { $uvReusable = $false }
        }
        if (-not $uvReusable) {
            $uvZip = Download-Verified $Lock.uv (Join-Path $downloadRoot ([string]$Lock.uv.asset)) $null
            $uvStage = Join-Path $stage "uv"
            Expand-SafeZip $uvZip $uvStage
            $uvStageExe = Join-Path $uvStage "uv.exe"
            if (-not (Test-Path -LiteralPath $uvStageExe -PathType Leaf)) { Fail "uv ZIP does not contain uv.exe" }
            Move-IntoPlace $uvStage $uvFinal | Out-Null
            $uvExe = Join-Path $uvFinal "uv.exe"
        }
        $uvVersion = Invoke-Checked $uvExe @('--version') "uv"
        if ($uvVersion -notmatch ([string]$Lock.uv.version)) { Fail "uv version mismatch: $uvVersion" }

        $pythonFinal = Join-Path $RuntimeDir ("python\" + [string]$Lock.python.version)
        $pythonExe = Get-ChildItem -LiteralPath $pythonFinal -Recurse -File -Filter "python.exe" -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
        if (-not $pythonExe) {
            $pythonStage = Join-Path $stage "python"
            Ensure-Directory $pythonStage | Out-Null
            Invoke-Checked $uvExe @('python', 'install', ([string]$Lock.python.version), '--install-dir', $pythonStage, '--no-bin', '--no-registry', '--managed-python', '--no-progress', '--cache-dir', $env:UV_CACHE_DIR) "Python download"
            $pythonExe = Get-ChildItem -LiteralPath $pythonStage -Recurse -File -Filter "python.exe" | Select-Object -First 1 -ExpandProperty FullName
            if (-not $pythonExe) { Fail "uv Python install did not produce python.exe" }
            $pythonPublished = Move-IntoPlace $pythonStage $pythonFinal
            $pythonExe = Get-ChildItem -LiteralPath $pythonPublished -Recurse -File -Filter "python.exe" | Select-Object -First 1 -ExpandProperty FullName
        }

        $venvFinal = Join-Path $RuntimeDir ("venv\py" + [string]$Lock.python.version + "-manim-0.19.0")
        $venvPython = Join-Path $venvFinal "Scripts\python.exe"
        $venvValid = $false
        if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
            try { $null = Test-PythonRuntime $venvPython; $venvValid = $true } catch { $venvValid = $false }
        }
        if (-not $venvValid) {
            $venvStage = Join-Path $stage "venv"
            Invoke-Checked $uvExe @('venv', $venvStage, '--python', $pythonExe, '--no-progress') "Python virtual environment"
            $requirements = Join-Path $stage "requirements.txt"
            Write-Utf8NoBom $requirements ((@($Lock.python_packages) -join "`r`n") + "`r`n")
            Invoke-Checked $uvExe @('pip', 'install', '--python', (Join-Path $venvStage "Scripts\python.exe"), '--requirement', $requirements, '--index-url', 'https://pypi.org/simple', '--no-progress', '--cache-dir', $env:UV_CACHE_DIR) "Pinned Manim dependencies"
            $venvPython = Join-Path $venvStage "Scripts\python.exe"
            $null = Test-PythonRuntime $venvPython
            Move-IntoPlace $venvStage $venvFinal | Out-Null
            $venvPython = Join-Path $venvFinal "Scripts\python.exe"
        }

        $whisperFinal = Join-Path $RuntimeDir ("whisper\" + [string]$Lock.whisper.release)
        $whisperExe = Join-Path $whisperFinal ([string]$Lock.whisper.executable).Replace('/', '\')
        if (-not (Test-Path -LiteralPath $whisperExe -PathType Leaf)) {
            $whisperZip = Download-Verified $Lock.whisper (Join-Path $downloadRoot ([string]$Lock.whisper.asset)) $null
            $whisperStage = Join-Path $stage "whisper"
            Expand-SafeZip $whisperZip $whisperStage
            $whisperStageExe = Join-Path $whisperStage ([string]$Lock.whisper.executable).Replace('/', '\')
            if (-not (Test-Path -LiteralPath $whisperStageExe -PathType Leaf)) { Fail "Whisper ZIP does not contain whisper-cli.exe" }
            Move-IntoPlace $whisperStage $whisperFinal | Out-Null
            $whisperExe = Join-Path $whisperFinal ([string]$Lock.whisper.executable).Replace('/', '\')
        }

        $ffmpegFinal = Join-Path $RuntimeDir ("ffmpeg\" + [string]$Lock.ffmpeg.release)
        $ffmpegExe = Join-Path $ffmpegFinal ([string]$Lock.ffmpeg.executable).Replace('/', '\')
        if (-not (Test-Path -LiteralPath $ffmpegExe -PathType Leaf)) {
            $ffmpegZip = Download-Verified $Lock.ffmpeg (Join-Path $downloadRoot ([string]$Lock.ffmpeg.asset)) $null
            $ffmpegStage = Join-Path $stage "ffmpeg"
            Expand-SafeZip $ffmpegZip $ffmpegStage
            $ffmpegStageExe = Get-ChildItem -LiteralPath $ffmpegStage -Recurse -File -Filter "ffmpeg.exe" | Select-Object -First 1 -ExpandProperty FullName
            if (-not $ffmpegStageExe) { Fail "FFmpeg ZIP does not contain bin/ffmpeg.exe" }
            Move-IntoPlace $ffmpegStage $ffmpegFinal | Out-Null
            $ffmpegExe = Get-ChildItem -LiteralPath $ffmpegFinal -Recurse -File -Filter "ffmpeg.exe" | Select-Object -First 1 -ExpandProperty FullName
        }

        $modelFinal = Join-Path $RuntimeDir "models\ggml-small.bin"
        $modelValid = $false
        if (Test-Path -LiteralPath $modelFinal -PathType Leaf) {
            $modelValid = ([IO.FileInfo]::new($modelFinal).Length -eq [Int64]$Lock.whisper_model.size_bytes -and (Get-Sha256 $modelFinal) -eq ([string]$Lock.whisper_model.sha256).ToLowerInvariant())
        }
        if (-not $modelValid) {
            $modelStage = Join-Path $stage "ggml-small.bin"
            $modelCache = Join-Path $downloadRoot ([string]$Lock.whisper_model.name)
            $verifiedModel = Download-Verified $Lock.whisper_model $modelCache ([Int64]$Lock.whisper_model.size_bytes)
            Copy-Item -LiteralPath $verifiedModel -Destination $modelStage -Force
            Move-IntoPlace $modelStage $modelFinal | Out-Null
        }

        $pythonInfo = Test-Tools $venvPython $ffmpegExe $whisperExe $modelFinal
        $engineRoot = Get-FullPath (Join-Path $PackageRoot "assets\engine")
        if (-not (Test-Path -LiteralPath $engineRoot -PathType Container) -or -not (Test-Path -LiteralPath (Join-Path $engineRoot "v3\runtime_template.py") -PathType Leaf)) {
            Fail "Package engine assets are incomplete: $engineRoot"
        }
        $payload = [ordered]@{
            ready = $true
            schema_version = 1
            lock_sha256 = $LockDigest
            runtime_root = $RuntimeDir
            python_exe = (Get-FullPath $venvPython)
            ffmpeg_exe = (Get-FullPath $ffmpegExe)
            whisper_exe = (Get-FullPath $whisperExe)
            whisper_model = (Get-FullPath $modelFinal)
            engine_root = $engineRoot
            manim_project = $engineRoot
            font_name = [string]$Lock.target.font_name
            font_path = $fontPath
            tex_required = $false
            versions = [ordered]@{
                uv = [string]$Lock.uv.version
                python = [string]$Lock.python.version
                manim = "0.19.0"
                whisper = [string]$Lock.whisper.release
                whisper_model_revision = [string]$Lock.whisper_model.revision
                ffmpeg = [string]$Lock.ffmpeg.release
            }
        }
        $configParent = Ensure-Directory (Split-Path -Parent $ConfigPath)
        $tempConfig = Join-Path $configParent ("." + [IO.Path]::GetFileName($ConfigPath) + "." + [Guid]::NewGuid().ToString("N") + ".tmp")
        $configJson = $payload | ConvertTo-Json -Depth 8
        Write-Utf8NoBom $tempConfig $configJson
        Move-Item -LiteralPath $tempConfig -Destination $ConfigPath -Force
        if (-not $ConfigPathProvided) {
            # Keep the documented runner spelling available while runtime.json
            # remains the canonical output requested by the installer contract.
            $compatConfig = Join-Path $RuntimeDir "runtime-config.json"
            $compatTemp = Join-Path $RuntimeDir (".runtime-config.json." + [Guid]::NewGuid().ToString("N") + ".tmp")
            Write-Utf8NoBom $compatTemp $configJson
            Move-Item -LiteralPath $compatTemp -Destination $compatConfig -Force
        }
        Write-Output "runtime ready: $ConfigPath"
        Write-Output ("python={0}`nffmpeg={1}`nwhisper={2}`nmodel={3}" -f $payload.python_exe, $payload.ffmpeg_exe, $payload.whisper_exe, $payload.whisper_model)
    }
    finally {
        if ($oldUvCache) { $env:UV_CACHE_DIR = $oldUvCache } else { Remove-Item Env:UV_CACHE_DIR -ErrorAction SilentlyContinue }
        if ($oldTemp) { $env:TEMP = $oldTemp } else { Remove-Item Env:TEMP -ErrorAction SilentlyContinue }
        if ($oldTmp) { $env:TMP = $oldTmp } else { Remove-Item Env:TMP -ErrorAction SilentlyContinue }
        Remove-Staging $stage
    }
}
catch {
    [Console]::Error.WriteLine("setup failed: " + $_.Exception.Message)
    exit 1
}
