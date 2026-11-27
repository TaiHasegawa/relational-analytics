# relana セットアップ（Windows）
# 使い方: このファイルを右クリック →「PowerShell で実行」
# 実体は scripts\setup.py。ここは Python を探して渡すだけ。
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
foreach ($c in @("python", "python3", "py")) {
  try {
    & $c -c "import sys;sys.exit(0 if sys.version_info>=(3,11) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) {
      & $c "$Root\scripts\setup.py"
      Read-Host "Enter キーで終了します"
      exit $LASTEXITCODE
    }
  } catch { }
}
Write-Host ""
Write-Host "■ セットアップを中断しました" -ForegroundColor Red
Write-Host @"
Python 3.11 以上が見つかりませんでした。

  1. https://www.python.org/downloads/ を開く
  2. 大きな「Download Python」ボタンを押す
  3. インストーラの最初の画面で
     ★「Add python.exe to PATH」に必ずチェックを入れる★
  4. 「Install Now」を押す
  5. 終わったら、このファイルをもう一度実行する
"@
Read-Host "Enter キーで終了します"
exit 1
