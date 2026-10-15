# MACA 凭证配置（agent 侧一次配好，MCP 自动点亮）
# 用法：在启动 Agnes Harness / MCP 客户端之前跑一次
#   .\setup_maca.ps1 <你的活JWT>
# 之后所有 run_full_pipeline / maca_duel / maca_import 调用自动读 $env:MIDAS_MAPI_KEY，
# 无需每次传 midas_mapi_key 参数。JWT 20min 过期，重跑本脚本注入新值即可。
# 凭证只走环境变量，绝不写死进代码 / 不落到磁盘。

param(
    [Parameter(Position=0)]
    [string]$Jwt,
    [string]$ApiUrl = "https://moa-engineers.midasit.cn:443/gen"
)

if (-not $Jwt) {
    Write-Host "用法: .\setup_maca.ps1 <MIDAS_MAPI_JWT>"
    Write-Host "  例: .\setup_maca.ps1 eyJ1ciI6IlRpbWUyMCIs..."
    exit 1
}

$env:MIDAS_MAPI_KEY = $Jwt
$env:MIDAS_API_URL = $ApiUrl

Write-Host ""
Write-Host "===================================================" -ForegroundColor Green
Write-Host " MACA 凭证已注入当前 PowerShell 会话" -ForegroundColor Green
Write-Host "   MIDAS_MAPI_KEY : $(if($Jwt.Length -gt 20){$Jwt.Substring(0,20)+'...('+$Jwt.Length+'chars)'}else{$Jwt})"
Write-Host "   MIDAS_API_URL  : $ApiUrl"
Write-Host "   有效期         : ~20min（MIDAS Time20 窗口）"
Write-Host "===================================================" -ForegroundColor Green
Write-Host ""
Write-Host " 之后调 MCP 工具（agent 侧零配置自动点亮）：" -ForegroundColor Cyan
Write-Host "   run_full_pipeline {}        # 自动读 env，④点亮实时 FEA"
Write-Host "   check_credential {}         # 自检④是否点亮"
Write-Host ""
Write-Host " 注意：此变量只在本 PowerShell 会话有效。新开终端需重跑本脚本。" -ForegroundColor Yellow
Write-Host " 若要跨终端持久化（不推荐，JWT 短期），可用 setx，但过期后仍须手动刷新。"
