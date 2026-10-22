<#
.SYNOPSIS
    构建 SteamList Docker 镜像并部署到远程 Windows / Linux Docker 主机。

.DESCRIPTION
    本地流程：docker build -> docker save -> 打包项目 zip -> scp 到远端
              -> ssh 远端解压 -> docker load -> docker compose up -d --no-build

    镜像内的前端（web/）由 Dockerfile 多阶段构建，因此本地无需先执行 pnpm build。
    远端保留已有的 .env 与 ./data 目录，重复部署不会丢数据。

.PARAMETER RemoteUser
    远端 SSH 用户名（必填）。

.PARAMETER RemoteHost
    远端主机地址，默认 192.168.173.22。

.PARAMETER RemotePort
    远端 SSH 端口，默认 22。

.PARAMETER RemotePath
    远端项目目录，默认 D:\ProgramFiles\steamlist（Linux 主机请传 /opt/steamlist）。

.PARAMETER ProxyUrl
    容器访问 Steam 使用的代理地址。未指定 -NoProxy 时会写入远端 .env 的
    STEAMLIST_PROXY_URL。传入 127.0.0.1/localhost 会自动改写为 host.docker.internal，
    因为容器内的 127.0.0.1 指向容器自身。

.PARAMETER NoProxy
    不向远端写入代理配置（复用远端已有 .env）。

.PARAMETER IdentityFile
    SSH 私钥路径，默认 ~/.ssh/DockerPub_ed25519。

.PARAMETER ImageTag
    本地与远端使用的镜像标签，默认 steamlist:latest。

.PARAMETER DryRun
    只打印将执行的命令，不做任何构建、上传或远端变更。

.EXAMPLE
    .\deploy.ps1 -RemoteUser docker -RemoteHost 192.168.173.22 `
        -RemotePath D:\ProgramFiles\steamlist -ProxyUrl 127.0.0.1:10808

.EXAMPLE
    .\deploy.ps1 -RemoteUser docker -DryRun
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RemoteUser,

    [string]$RemoteHost = "192.168.173.22",

    [int]$RemotePort = 22,

    [string]$RemotePath = "D:\ProgramFiles\steamlist",

    [string]$ProxyUrl = "",

    [switch]$NoProxy,

    [string]$IdentityFile = "$HOME\.ssh\DockerPub_ed25519",

    [string]$ImageTag = "steamlist:latest",

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RemotePosixPath = $RemotePath -replace '\\', '/'
$RemoteDeployDir = "$RemotePosixPath/deploy"
$SshTarget = "$RemoteUser@$RemoteHost"
$RemoteUrl = "http://${RemoteHost}:8080"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Info {
    param([string]$Message)
    Write-Host "    $Message" -ForegroundColor DarkGray
}

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [string[]]$ArgumentList = @()
    )
    Write-Host ("    > {0} {1}" -f $Exe, ($ArgumentList -join " ")) -ForegroundColor DarkGray
    if ($DryRun) {
        return
    }
    & $Exe @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "$Exe 执行失败（exit code $LASTEXITCODE）"
    }
}

function New-RemoteShellCommand {
    param([string]$Target, [string]$RemoteScript)
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($RemoteScript))
    $sshArgs = @(
        "-p", "$RemotePort",
        "-i", $IdentityFile,
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        $Target,
        "powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand $encoded"
    )
    Invoke-Native -Exe "ssh" -ArgumentList $sshArgs
}

# ---------------------------------------------------------------------------
# 0. 前置检查
# ---------------------------------------------------------------------------
Write-Step "检查本地环境"
foreach ($tool in @("docker")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "未找到 $tool，请先安装 Docker Desktop 并加入 PATH"
    }
}
Invoke-Native -Exe "docker" -ArgumentList @("version", "--format", "{{.Server.Version}}")

if ($DryRun) {
    Write-Info "-DryRun：跳过 ssh 密钥检查与临时文件创建"
} else {
    if (-not (Test-Path -LiteralPath $IdentityFile)) {
        throw "SSH 私钥不存在：$IdentityFile（可用 -IdentityFile 指定）"
    }
    foreach ($tool in @("ssh", "scp")) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
            throw "未找到 $tool，请启用 Windows OpenSSH 客户端"
        }
    }
}

$effectiveProxy = $ProxyUrl
if ($effectiveProxy) {
    $effectiveProxy = $effectiveProxy.Trim()
    if ($effectiveProxy -match '^(?i)https?://') {
        # keep as is
    } elseif ($effectiveProxy -match '^(?i)(127\.0\.0\.1|localhost)(:\d+)?(.*)$') {
        $effectiveProxy = "http://host.docker.internal$($Matches[2])$($Matches[3])"
    } else {
        $effectiveProxy = "http://$effectiveProxy"
    }
    $effectiveProxy = $effectiveProxy -replace '(?i)http://(127\.0\.0\.1|localhost)', 'http://host.docker.internal'
}

$tempRoot = Join-Path $env:TEMP ("steamlist-deploy-" + [Guid]::NewGuid().ToString("N").Substring(0, 8))
$imageTarName = "steamlist-image.tar"
$zipName = "steamlist-project.zip"
$stageDir = Join-Path $tempRoot "stage"
$imageTarLocal = Join-Path $tempRoot $imageTarName
$zipLocal = Join-Path $tempRoot $zipName

try {
    # -----------------------------------------------------------------------
    # 1. 构建镜像（内含前端 pnpm build）
    # -----------------------------------------------------------------------
    Write-Step "构建 Docker 镜像 $ImageTag"
    Invoke-Native -Exe "docker" -ArgumentList @("build", "-t", $ImageTag, $ProjectRoot)

    # -----------------------------------------------------------------------
    # 2. 导出镜像
    # -----------------------------------------------------------------------
    Write-Step "导出镜像到本地 tar"
    if (-not $DryRun) {
        New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
    }
    Invoke-Native -Exe "docker" -ArgumentList @("save", "-o", $imageTarLocal, $ImageTag)

    # -----------------------------------------------------------------------
    # 3. 打包远端所需的项目文件（排除数据、依赖与构建产物）
    # -----------------------------------------------------------------------
    Write-Step "打包项目文件"
    if (-not $DryRun) {
        New-Item -ItemType Directory -Force -Path $stageDir | Out-Null
        $robocopyArgs = @(
            $ProjectRoot, $stageDir, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP",
            "/XD", ".git", ".venv", "data", "node_modules", "dist", "__pycache__",
            ".pytest_cache", "deploy-tmp",
            "/XF", "*.db", "*.db-wal", "*.db-shm", "*.tar", "*.zip"
        )
        & robocopy @robocopyArgs | Out-Null
        if ($LASTEXITCODE -ge 8) {
            throw "robocopy 打包失败（exit code $LASTEXITCODE）"
        }
        $global:LASTEXITCODE = 0
        # 远端只需要镜像 + compose 文件，数据目录由 volume 提供
        Get-ChildItem -LiteralPath $stageDir -Directory -Filter "web" -ErrorAction SilentlyContinue |
            ForEach-Object {
                Remove-Item -Recurse -Force (Join-Path $_.FullName "node_modules") -ErrorAction SilentlyContinue
            }
        Compress-Archive -Path (Join-Path $stageDir "*") -DestinationPath $zipLocal -Force
    }
    Write-Info "项目包：$zipLocal"
    Write-Info "镜像包：$imageTarLocal"

    # -----------------------------------------------------------------------
    # 4. 准备远端目录
    # -----------------------------------------------------------------------
    Write-Step "在远端创建部署目录 $RemoteDeployDir"
    $mkdirScript = @"
`$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path '$RemoteDeployDir' | Out-Null
Write-Output 'remote directory ready'
"@
    New-RemoteShellCommand -Target $SshTarget -RemoteScript $mkdirScript

    # -----------------------------------------------------------------------
    # 5. 上传 zip 与镜像 tar
    # -----------------------------------------------------------------------
    Write-Step "上传项目包与镜像包"
    $scpArgs = @(
        "-P", "$RemotePort",
        "-i", $IdentityFile,
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        $zipLocal, $imageTarLocal,
        "${SshTarget}:$RemoteDeployDir/"
    )
    Invoke-Native -Exe "scp" -ArgumentList $scpArgs

    # -----------------------------------------------------------------------
    # 6. 远端解压、加载镜像、启动
    # -----------------------------------------------------------------------
    Write-Step "远端解压、加载镜像并启动容器"
    $proxyLine = if ($effectiveProxy) { "STEAMLIST_PROXY_URL=$effectiveProxy" } else { "STEAMLIST_PROXY_URL=" }
    $remoteScript = @"
`$ErrorActionPreference = 'Stop'

New-Item -ItemType Directory -Force -Path '$RemotePath' | Out-Null
Set-Location -LiteralPath '$RemotePath'

Expand-Archive -LiteralPath '$RemoteDeployDir/$zipName' -DestinationPath '$RemotePath' -Force
Write-Output 'project extracted'

`$envFile = Join-Path '$RemotePath' '.env'
if (-not (Test-Path -LiteralPath `$envFile)) {
    `$lines = @(
        'STEAMLIST_PORT=8080',
        'TZ=Asia/Shanghai',
        'STEAMLIST_TIMEZONE=Asia/Shanghai',
        'STEAMLIST_DEFAULT_CC=cn',
        'STEAMLIST_DEFAULT_LANG=schinese',
        'STEAMLIST_ENABLE_SCHEDULER=true',
        '$proxyLine'
    )
    Set-Content -LiteralPath `$envFile -Value `$lines -Encoding ascii
    Write-Output 'wrote default .env'
} else {
    `$proxyValue = '$effectiveProxy'
    if (`$proxyValue) {
        `$pattern = '^STEAMLIST_PROXY_URL='
        `$found = `$false
        `$updated = foreach (`$line in (Get-Content -LiteralPath `$envFile)) {
            if (`$line -match `$pattern) {
                `$found = `$true
                "STEAMLIST_PROXY_URL=`$proxyValue"
            } else {
                `$line
            }
        }
        if (-not `$found) { `$updated = @(`$updated) + "STEAMLIST_PROXY_URL=`$proxyValue" }
        Set-Content -LiteralPath `$envFile -Value `$updated -Encoding ascii
        Write-Output 'updated STEAMLIST_PROXY_URL in existing .env'
    } else {
        Write-Output 'kept existing .env'
    }
}

docker load -i '$RemoteDeployDir/$imageTarName'
if (`$LASTEXITCODE -ne 0) { throw 'docker load failed' }

docker compose -p steamlist up -d --no-build
if (`$LASTEXITCODE -ne 0) { throw 'docker compose up failed' }

Start-Sleep -Seconds 3
docker compose -p steamlist ps
Write-Output ''
Write-Output 'SteamList deployed.'
"@
    New-RemoteShellCommand -Target $SshTarget -RemoteScript $remoteScript

    Write-Step "部署完成"
    Write-Host "    访问地址：$RemoteUrl" -ForegroundColor Green
    Write-Host "    远端目录：$RemotePath" -ForegroundColor Green
    Write-Host "    若无法访问，请检查远端防火墙 8080 端口与 docker compose logs。" -ForegroundColor DarkGray
}
finally {
    if (-not $DryRun -and (Test-Path -LiteralPath $tempRoot)) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
