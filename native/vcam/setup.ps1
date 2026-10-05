# Installs or removes the "Yüz Atölyesi Kamera" media source. Runs elevated (the app
# starts it through UAC). The Frame Server services load the DLL as Local Service /
# Local System, which cannot read user folders such as Downloads, so the DLL is
# copied to ProgramData and registered machine-wide (HKLM) from there.
#
# Exit codes: 0 done, 3 DLL missing next to this script, 4 regsvr32 failed, 5 other error.
param(
    [Parameter(Mandatory)][ValidateSet('install', 'uninstall')][string]$Action
)
$ErrorActionPreference = 'Stop'
$clsid = '{92966083-168A-4874-9B2F-4E4F50BD7742}'  # native/vcam/source/dllmain.cpp
$key = "HKLM:\SOFTWARE\Classes\CLSID\$clsid\InprocServer32"
$target = Join-Path $env:ProgramData 'YuzAtolyesi\vcam'

function Invoke-Regsvr32([string[]]$arguments) {
    # regsvr32 is a GUI program; Start-Process -Wait is needed to get its exit code.
    (Start-Process regsvr32.exe -ArgumentList $arguments -Wait -PassThru -WindowStyle Hidden).ExitCode
}

try {
    if ($Action -eq 'install') {
        # Packaged kit: next to this script. Development checkout: native/vcam/bin.
        $source = @("$PSScriptRoot\YuzAtolyesiKamera.dll", "$PSScriptRoot\bin\YuzAtolyesiKamera.dll") |
            Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
        if (-not $source) { exit 3 }
        New-Item -ItemType Directory -Force -Path $target | Out-Null
        $dll = Join-Path $target 'YuzAtolyesiKamera.dll'
        try {
            Copy-Item -LiteralPath $source -Destination $dll -Force
        } catch {
            # A running Frame Server may still hold the previous copy; register a new file instead.
            $dll = Join-Path $target ('YuzAtolyesiKamera-{0}.dll' -f (Get-Date -Format 'yyyyMMddHHmmss'))
            Copy-Item -LiteralPath $source -Destination $dll
        }
        if (Invoke-Regsvr32 @('/s', "`"$dll`"")) { exit 4 }
        Get-ChildItem -LiteralPath $target -Filter 'YuzAtolyesiKamera*.dll' |
            Where-Object { $_.FullName -ne $dll } |
            Remove-Item -Force -ErrorAction SilentlyContinue
        exit 0
    }

    $registered = (Get-ItemProperty -LiteralPath $key -ErrorAction SilentlyContinue).'(default)'
    if ($registered -and (Test-Path -LiteralPath $registered)) {
        if (Invoke-Regsvr32 @('/u', '/s', "`"$registered`"")) { exit 4 }
    }
    # Covers a DLL that was deleted while still registered.
    Remove-Item -LiteralPath "HKLM:\SOFTWARE\Classes\CLSID\$clsid" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
    exit 0
} catch {
    exit 5
}
