"""Build without activation. Signed distribution needs a Team ID and profile."""
import argparse
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--identity', help='Developer ID Application certificate name')
parser.add_argument('--team-id')
parser.add_argument('--extension-profile', type=Path)
parser.add_argument('--host-profile', type=Path)
args = parser.parse_args()
signed = bool(args.identity)
if signed and (not args.team_id or not re.fullmatch(r'[A-Z0-9]{10}', args.team_id) or not args.extension_profile or not args.host_profile):
    parser.error('Signed builds require --team-id, --extension-profile and --host-profile.')
if not signed and any([args.team_id, args.extension_profile, args.host_profile]):
    parser.error('Signing arguments require --identity.')
for profile in (args.extension_profile, args.host_profile):
    if profile and not profile.is_file(): parser.error(f'Profile not found: {profile}')
team = args.team_id or 'UNSIGNED'
env = {**os.environ, 'DEVELOPER_DIR': os.environ.get('DEVELOPER_DIR', '/Library/Developer/CommandLineTools')}
app = ROOT / 'build' / 'YuzAtolyesiCamera.app'
contents = app / 'Contents'
ext = contents / 'Library' / 'SystemExtensions' / 'com.yuzatolyesi.camera.extension.systemextension'
for folder in (contents / 'MacOS', ext / 'Contents' / 'MacOS'):
    folder.mkdir(parents=True, exist_ok=True)
# A reused build must never inherit a prior developer's provisioning profile.
for folder in (contents, ext / 'Contents'):
    stale = folder / 'embedded.provisionprofile'
    if stale.exists(): stale.unlink()

def plist(path, data):
    path.write_bytes(plistlib.dumps(data))

base = dict(CFBundleVersion='1', CFBundleShortVersionString='0.1.0', LSMinimumSystemVersion='13.0')
plist(contents / 'Info.plist', dict(base, CFBundleIdentifier='com.yuzatolyesi.camera',
    CFBundleExecutable='YuzCameraManager', CFBundleName='Yüz Atölyesi Kamera', CFBundlePackageType='APPL',
    NSCameraUsageDescription='İşlenmiş görüntüyü sanal kameraya aktarmak için kamera erişimi gerekir.',
    YuzSigned=signed, YuzTeamID=team))
plist(ext / 'Contents' / 'Info.plist', dict(base, CFBundleIdentifier='com.yuzatolyesi.camera.extension',
    CFBundleExecutable='YuzCameraExtension', CFBundleName='Yüz Atölyesi Kamera', CFBundlePackageType='SYSX',
    CMIOExtension={'CMIOExtensionMachServiceName': f'{team}.com.yuzatolyesi.camera.extension'}, YuzTeamID=team, NSSystemExtensionUsageDescription='İşlenmiş görüntüyü diğer uygulamalara Yüz Atölyesi Kamera olarak aktarır.'))
# Camera extensions are sandboxed; frames use CMIO sink streams, no shared files/network.
plist(ROOT / 'build' / 'extension.entitlements', {'com.apple.security.app-sandbox': True,
    'com.apple.security.application-groups': [f'{team}.com.yuzatolyesi.camera']})
plist(ROOT / 'build' / 'host.entitlements', {'com.apple.developer.system-extension.install': True,
                                         'com.apple.security.device.camera': True,
                                         'com.apple.security.application-groups': [f'{team}.com.yuzatolyesi.camera']})

common = ['-fobjc-arc', '-fmodules', '-fmodules-cache-path=/tmp/yuz-clang-modules', '-mmacosx-version-min=13.0',
          '-arch', 'arm64', '-arch', 'x86_64', '-framework', 'Foundation', '-framework', 'CoreMediaIO',
          '-framework', 'CoreMedia', '-framework', 'CoreVideo']
subprocess.run(['xcrun', 'clang', *common, '-framework', 'Security', str(ROOT / 'CameraExtension.m'),
                '-o', str(ext / 'Contents' / 'MacOS' / 'YuzCameraExtension')], env=env, check=True)
subprocess.run(['xcrun', 'clang++', '-x', 'objective-c++', '-std=c++17', *common, str(ROOT / 'CameraBridge.m'),
                '-o', str(contents / 'MacOS' / 'yuz-camera-bridge')], env=env, check=True)
manager_binaries = []
for arch in ('arm64', 'x86_64'):
    output = ROOT / 'build' / f'manager-{arch}'
    subprocess.run(['xcrun', 'swiftc', '-swift-version', '5', '-module-cache-path', '/tmp/yuz-swift-modules',
                    '-target', f'{arch}-apple-macos13.0', str(ROOT / 'CameraManager.swift'), '-o', str(output)], env=env, check=True)
    manager_binaries.append(str(output))
subprocess.run(['xcrun', 'lipo', '-create', *manager_binaries, '-output', str(contents / 'MacOS' / 'YuzCameraManager')], env=env, check=True)
if args.extension_profile: shutil.copy2(args.extension_profile, ext / 'Contents' / 'embedded.provisionprofile')
if args.host_profile: shutil.copy2(args.host_profile, contents / 'embedded.provisionprofile')
identity = args.identity or '-'
flags = ['--options', 'runtime', '--timestamp'] if signed else []
for target, identifier, entitlements in [
    (contents / 'MacOS' / 'yuz-camera-bridge', 'com.yuzatolyesi.camera-bridge', None),
    (ext, 'com.yuzatolyesi.camera.extension', ROOT / 'build' / 'extension.entitlements'),
    (app, 'com.yuzatolyesi.camera', ROOT / 'build' / 'host.entitlements'),
]:
    command = ['codesign', '--force', '--sign', identity, '--identifier', identifier, *flags]
    if entitlements and signed: command += ['--entitlements', str(entitlements)]
    subprocess.run([*command, str(target)], check=True)
subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
print(app)
print('Signed package: notarization and activation testing remain.' if signed else
      'Ad-hoc development build only. Installation is disabled until signed.')
