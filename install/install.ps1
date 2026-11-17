# 表格法 · 一键安装
# 双击 install.bat 即可。也可以用参数精细控制：
#   .\install.ps1 -DryRun              只看会改什么，不写文件
#   .\install.ps1 -Python D:\Python\python.exe -Table D:\mytable.md
param(
    [switch]$DryRun,
    [string]$Python,
    [string]$Table
)

$ErrorActionPreference = 'Stop'

$Root        = Split-Path -Parent $PSScriptRoot
$ServerPath  = Join-Path $Root 'server\main.py'
$RulesPath   = Join-Path $Root 'AGENTS.md'
$Template    = Join-Path $Root 'templates\memory-table.md'
$HomeDir     = $env:USERPROFILE

function Step($m) { Write-Host ""; Write-Host ("== " + $m) -ForegroundColor Cyan }
function Ok($m)   { Write-Host "   [OK] $m" -ForegroundColor Green }
function Skip($m) { Write-Host "   [跳过] $m" -ForegroundColor DarkGray }
function Warn($m) { Write-Host "   [注意] $m" -ForegroundColor Yellow }
function Bad($m)  { Write-Host "   [失败] $m" -ForegroundColor Red }

function Write-Utf8([string]$path, [string]$text) {
    $dir = Split-Path -Parent $path
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    [System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding($false)))
}

function Read-Utf8([string]$path) {
    # PowerShell 5.1 的 Get-Content 默认按系统 ANSI（简体中文是 GBK）读。
    # 用它读 UTF-8 文件会变乱码，再写回去就是双重编码，文件永久损坏。
    return [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)
}

function Find-Python {
    if ($Python) { return $Python }
    # 便携版：包里自带运行时，优先用它。没有它，没装 Python 的电脑根本装不上。
    $bundled = Join-Path (Split-Path -Parent $PSScriptRoot) 'runtime\python.exe'
    if (Test-Path -LiteralPath $bundled) {
        try {
            $v = & $bundled -c "import sys;print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($v -and ([version]$v -ge [version]'3.10')) { return $bundled }
        } catch { }
    }
    $cands = @()
    $c = Get-Command python -ErrorAction SilentlyContinue
    if ($c) { $cands += $c.Source }
    $cands += @(
        'D:\Python\python.exe',
        (Join-Path $HomeDir 'AppData\Local\Programs\Python\Python313\python.exe'),
        (Join-Path $HomeDir 'AppData\Local\Programs\Python\Python312\python.exe'),
        (Join-Path $HomeDir 'AppData\Local\Programs\Python\Python311\python.exe'),
        'C:\Python313\python.exe',
        'C:\Python312\python.exe'
    )
    foreach ($p in $cands) {
        if ($p -and (Test-Path -LiteralPath $p)) {
            try {
                $v = & $p -c "import sys;print('%d.%d' % sys.version_info[:2])" 2>$null
                if ($v -and ([version]$v -ge [version]'3.10')) { return $p }
            } catch { }
        }
    }
    return $null
}

Write-Host "表格法 · 一张能手动改的状态表" -ForegroundColor White
if ($DryRun) { Write-Host "（演练模式：只看会改什么，不写任何文件）" -ForegroundColor Yellow }

# ---------- 1. Python ----------
Step "1/5 找 Python"
$py = Find-Python
if (-not $py) {
    Bad "没找到 Python 3.10+。装一个再回来：https://www.python.org/downloads/"
    exit 1
}
$pyVer = & $py -c "import sys;print('%d.%d.%d' % sys.version_info[:3])"
Ok "$py  (v$pyVer)"

$mcpOk = $false
try { & $py -c "import mcp" 2>$null; if ($LASTEXITCODE -eq 0) { $mcpOk = $true } } catch { }
if ($mcpOk) {
    Ok "依赖 mcp 已装"
} else {
    Warn "缺依赖 mcp，现在装（约 20MB）"
    if (-not $DryRun) {
        & $py -m pip install mcp -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet
        if ($LASTEXITCODE -eq 0) { Ok "mcp 装好了" } else { Bad "安装失败，手动跑：$py -m pip install mcp" ; exit 1 }
    }
}

if (-not (Test-Path -LiteralPath $ServerPath)) { Bad "找不到 $ServerPath"; exit 1 }

# ---------- 2. 表 ----------
Step "2/5 准备记忆表"
if ($Table) { $TablePath = $Table } else { $TablePath = Join-Path $Root 'memory-table.md' }
if (Test-Path -LiteralPath $TablePath) {
    Skip "已存在：$TablePath"
} else {
    if ($DryRun) {
        Warn "将新建：$TablePath"
    } else {
        Write-Utf8 $TablePath (Read-Utf8 $Template)
        Ok "已新建：$TablePath"
    }
}

# ---------- 3. 三个客户端 ----------
Step "3/5 配置客户端（已存在就跳过，不覆盖别人的条目）"

# 3.1 WorkBuddy
$wb = Join-Path $HomeDir '.workbuddy\mcp.json'
if (Test-Path -LiteralPath (Split-Path -Parent $wb)) {
    $existing = ''
    if (Test-Path -LiteralPath $wb) { $existing = Read-Utf8 $wb }
    if ($existing -match '"context-table"') {
        Skip "WorkBuddy 已有配置"
    } elseif ($DryRun) {
        Warn "将写入 $wb 的 mcpServers.context-table"
    } else {
        if (Test-Path -LiteralPath $wb) {
            $cfg = Read-Utf8 $wb | ConvertFrom-Json
        } else {
            $cfg = New-Object psobject
        }
        if (-not ($cfg.PSObject.Properties.Name -contains 'mcpServers')) {
            $cfg | Add-Member -NotePropertyName mcpServers -NotePropertyValue (New-Object psobject)
        }
        $entry = [ordered]@{
            command = $py
            args    = @($ServerPath)
            env     = [ordered]@{ CONTEXT_TABLE_PATH = $TablePath; PYTHONIOENCODING = 'utf-8' }
        }
        $cfg.mcpServers | Add-Member -NotePropertyName 'context-table' -NotePropertyValue $entry -Force
        Write-Utf8 $wb ($cfg | ConvertTo-Json -Depth 12)
        Ok "WorkBuddy 已写入（还差界面上点一次「信任」）"
    }
} else {
    Skip "没装 WorkBuddy"
}

# 3.2 Codex / ChatGPT 桌面（共用 ~/.codex/config.toml）
$cx = Join-Path $HomeDir '.codex\config.toml'
if (Test-Path -LiteralPath $cx) {
    $txt = Read-Utf8 $cx
    if ($txt -match '(?m)^\s*\[mcp_servers\.context-table\]') {
        Skip "Codex 已有配置"
    } else {
        $block = @"

# ---- context-table：跨平台状态表（MCP）----
[mcp_servers.context-table]
command = '$($py -replace '\\', '\\')'
args = ['$($ServerPath -replace '\\', '\\')']
env = { CONTEXT_TABLE_PATH = '$($TablePath -replace '\\', '\\')', PYTHONIOENCODING = 'utf-8' }
"@
        if ($DryRun) {
            Warn "将向 config.toml 追加 context-table"
        } else {
            Copy-Item -LiteralPath $cx -Destination "$cx.bak" -Force
            Write-Utf8 $cx ($txt.TrimEnd() + $block)
            Ok "Codex 已写入（备份 config.toml.bak）"
        }
    }
} else {
    Skip "没装 Codex"
}

# 3.3 DeepSeek Harness（MCP 客户端插件是内置的，不用装）
$dsh = Join-Path $HomeDir '.dsh\profiles\desktop\cordis.patch.yml'
# 版本不同，profile 目录可能不叫 desktop；在 profiles\* 下找第一个 cordis.patch.yml
if (-not (Test-Path -LiteralPath $dsh)) {
    $alt = Get-ChildItem -LiteralPath (Join-Path $HomeDir '.dsh\profiles') -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName 'cordis.patch.yml' } |
        Where-Object { Test-Path -LiteralPath $_ } |
        Select-Object -First 1
    if ($alt) { $dsh = $alt }
}
if (Test-Path -LiteralPath $dsh) {
    $txt = Read-Utf8 $dsh
    if ($txt -match 'mcp-context-table') {
        Skip "DSH 已有配置"
    } else {
        $block = @"

# ---- context-table：跨平台状态表（MCP）----
# 必须写成 insert: 形式。直接写 - id:/name: 会被当成"覆盖已有条目"，
# 因为 id 不存在而整条被丢弃，日志里只会留一句 patch: entry "..." not found。
- insert:
    - id: mcp-context-table
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: context_table
        transport: stdio
        command: '$($py -replace '\\', '/')'
        args: ['$($ServerPath -replace '\\', '/')']
        env:
          CONTEXT_TABLE_PATH: '$($TablePath -replace '\\', '/')'
          PYTHONIOENCODING: 'utf-8'
"@
        if ($DryRun) {
            Warn "将向 cordis.patch.yml 追加 context-table"
        } else {
            Copy-Item -LiteralPath $dsh -Destination "$dsh.bak" -Force
            Write-Utf8 $dsh ($txt.TrimEnd() + $block)
            Ok "DSH 已写入（MCP 客户端插件随应用自带，不用装）"
        }
    }
} else {
    if (Test-Path -LiteralPath (Join-Path $HomeDir '.dsh')) {
        Warn "找到 ~/.dsh，但没找到 cordis.patch.yml。DSH 版本可能不一样，手动加：见包里的 adapters\dsh\INSTRUCTIONS.md"
    } else {
        Skip "没装 DeepSeek Harness"
    }
}

# ---------- 4. 规则文件 ----------
Step "4/5 装规则文件（让它自己判断该记什么，不用你开口）"
$rules = Read-Utf8 $RulesPath
$ruleStart = '<!-- context-table:rule:start -->'
$ruleEnd   = '<!-- context-table:rule:end -->'
$block2 = $ruleStart + "`n" + $rules.Trim() + "`n" + $ruleEnd

$dshRules = Join-Path $HomeDir '.dsh\AGENTS.md'
if (Test-Path -LiteralPath (Split-Path -Parent $dshRules)) {
    $old = ''
    if (Test-Path -LiteralPath $dshRules) { $old = Read-Utf8 $dshRules }
    if ($old -match [regex]::Escape($ruleStart)) {
        Skip "DSH 规则已存在"
    } elseif ($old.Trim() -eq $rules.Trim()) {
        # 已经是这份规则，只是没标记，包上标记，下次就能识别
        if ($DryRun) { Warn "将给 $dshRules 的现有规则加标记" }
        else { Write-Utf8 $dshRules ($block2 + "`n"); Ok "DSH 全局规则：~/.dsh/AGENTS.md（已加标记）" }
    } else {
        # 里面有别的内容，绝不清空：先备份再追加
        if ($DryRun) { Warn "将向 $dshRules 追加规则区块" }
        else {
            if ($old.Trim()) { Copy-Item -LiteralPath $dshRules -Destination "$dshRules.bak" -Force }
            $new = if ($old.Trim()) { $old.TrimEnd() + "`n`n" + $block2 + "`n" } else { $block2 + "`n" }
            Write-Utf8 $dshRules $new
            Ok "DSH 全局规则：~/.dsh/AGENTS.md（原有内容保留，备份 .bak）"
        }
    }
} else {
    Skip "没装 DSH"
}

$dirs = @(Get-ChildItem -LiteralPath (Join-Path $HomeDir '.workbuddy') -Directory -Filter 'user-*' -ErrorAction SilentlyContinue)
foreach ($d in $dirs) {
    $mem = Join-Path $d.FullName 'MEMORY.md'
    $old = ''
    if (Test-Path -LiteralPath $mem) { $old = Read-Utf8 $mem }
    if ($old -match [regex]::Escape($ruleStart)) { Skip "WorkBuddy 规则已存在"; continue }
    if ($DryRun) { Warn "将向 $mem 追加规则区块"; continue }
    $new = if ($old.Trim()) { $old.TrimEnd() + "`n`n" + $block2 + "`n" } else { $block2 + "`n" }
    Write-Utf8 $mem $new
    Ok "WorkBuddy 用户级规则已写入"
}
if (-not $dirs) { Warn "没找到 WorkBuddy 用户目录。先打开一次 WorkBuddy（登录进入主界面），再重新运行本安装器，否则规则装不进去。" }

# ---------- 5. 汇报 ----------
Step "5/5 完成"
Write-Host ""
Write-Host "  表      $TablePath"
Write-Host "  服务    $ServerPath"
Write-Host ""
Write-Host "接下来各客户端做一件事：" -ForegroundColor White
Write-Host "  WorkBuddy   完全退出重开 -> 连接器 -> 自定义连接器 -> context-table 点「信任」"
Write-Host "  Codex       完全退出重开（不用点任何东西）"
Write-Host "  DSH         完全退出重开（不用点任何东西）"
Write-Host ""
Write-Host "豆包（未实机验证）：没有配置文件，脚本改不了，只能手点，约 3 分钟：" -ForegroundColor White
Write-Host "  侧边栏「技能·连接器·伙伴」-> 新建自定义连接器 -> 传输类型选 STDIO"
Write-Host "  命令   $py"
Write-Host "  参数   $ServerPath"
Write-Host "  环境变量 CONTEXT_TABLE_PATH=$TablePath"
Write-Host "  详细步骤见 adapters\doubao\INSTRUCTIONS.md"
Write-Host ""
Write-Host "验证：新开一个对话，说一句有结论的话，例如" -ForegroundColor White
Write-Host "  「这个项目以后只用本地文件，不走云同步。」"
Write-Host "  看回答末尾有没有：已记：定了 ×1（工具）"
Write-Host ""
if ($DryRun) { Write-Host "（演练结束，没写任何文件。去掉 -DryRun 再跑一次才真正生效）" -ForegroundColor Yellow }
