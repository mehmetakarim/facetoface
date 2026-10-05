# Builds the Windows 11 virtual camera: YuzAtolyesiKamera.dll (media source loaded by
# the Frame Server service) and yuz-vcam.exe (keeps the camera registered).
# Output: native/vcam/bin. Requires Visual Studio Build Tools with the C++ workload,
# a Windows SDK >= 10.0.22000 and nuget.exe (on PATH or passed with -Nuget).
param(
    [string]$Configuration = 'Release',
    [string]$Toolset = '',
    [string]$Nuget = 'nuget'
)
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vs = & $vswhere -products * -latest -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw 'Visual Studio C++ build tools were not found.' }

& $Nuget restore "$here\source\packages.config" -PackagesDirectory "$here\packages" -NonInteractive
if ($LASTEXITCODE) { throw 'NuGet restore failed.' }

$msbuild = Join-Path $vs 'MSBuild\Current\Bin\amd64\MSBuild.exe'
$properties = @("/p:Configuration=$Configuration", '/p:Platform=x64', "/p:OutDir=$here\bin\")
# The project targets VS 2026 (v145); older runners pass their own toolset.
if ($Toolset) { $properties += "/p:PlatformToolset=$Toolset" }
& $msbuild "$here\source\VCamSampleSource.vcxproj" @properties /m /v:minimal /nologo
if ($LASTEXITCODE) { throw 'Media source build failed.' }

$vcvars = Join-Path $vs 'VC\Auxiliary\Build\vcvars64.bat'
# vcvars64.bat calls vswhere.exe by name; native stderr must not abort the script.
$env:PATH = "$(Split-Path $vswhere);$env:PATH"
$ErrorActionPreference = 'Continue'
$obj = Join-Path $here 'helper\obj'
New-Item -ItemType Directory -Force $obj | Out-Null
cmd /c "`"$vcvars`" >nul 2>&1 && cl /nologo /utf-8 /O2 /EHsc /W4 /MT /Fo`"$obj\\`" `"$here\helper\yuz-vcam.cpp`" /Fe`"$here\bin\yuz-vcam.exe`""
if ($LASTEXITCODE) { throw 'Helper build failed.' }
Get-ChildItem "$here\bin" -Include 'YuzAtolyesiKamera.dll', 'yuz-vcam.exe' -Recurse | Select-Object Name, Length
