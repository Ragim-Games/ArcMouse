"""Build a Windows x64 EXE and a portable ZIP using an isolated build environment."""
from importlib.metadata import distribution
from pathlib import Path
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from arcmouse import __version__


def collect_licenses(destination):
    destination.mkdir(parents=True, exist_ok=True)
    prefix = Path(sys.base_prefix)
    shutil.copy2(prefix / 'LICENSE.txt', destination / 'Python-LICENSE.txt')
    tcl_root = prefix / 'tcl'
    for library in ('tcl', 'tk'):
        found = False
        for bundle in tcl_root.glob(f'lib{library}*.zip'):
            with zipfile.ZipFile(bundle) as archive:
                name = f'{library}_library/license.terms'
                if name in archive.namelist():
                    (destination / f'{library}-license.terms').write_bytes(archive.read(name))
                    found = True
                    break
        if not found:
            for folder in tcl_root.glob(f'{library}[0-9]*'):
                candidate = folder / 'license.terms'
                if candidate.is_file():
                    shutil.copy2(candidate, destination / f'{library}-license.terms')
                    found = True
                    break
        if not found:
            raise RuntimeError(f'Cannot locate the {library} license in {tcl_root}')
    for package in ('pyserial', 'pyinstaller'):
        dist = distribution(package)
        copied = False
        for item in dist.files or []:
            if item.name.lower().startswith(('license', 'copying')):
                source = Path(dist.locate_file(item))
                if source.is_file():
                    shutil.copy2(source, destination / f'{package}-{item.name}')
                    copied = True
        if not copied:
            # pySerial 3.5's wheel omits its license; retain the official sdist copy.
            fallback = ROOT / 'assets' / 'licenses' / f'{package}-LICENSE.txt'
            shutil.copy2(fallback, destination / fallback.name)


def main():
    if sys.platform != 'win32' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise SystemExit('Build on 64-bit Windows with 64-bit Python.')
    build = ROOT / 'build'
    release = ROOT / 'dist' / 'release'
    build.mkdir(exist_ok=True)
    release.mkdir(parents=True, exist_ok=True)
    licenses = build / 'licenses'
    collect_licenses(licenses)
    parts = tuple(map(int, __version__.split('.'))) + (0,)
    metadata = build / 'windows-version.txt'
    metadata.write_text(f'''VSVersionInfo(
ffi=FixedFileInfo(filevers={parts}, prodvers={parts}, mask=0x3f, flags=0,
                 OS=0x40004, fileType=0x1, subtype=0, date=(0, 0)),
kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'ArcMouse contributors'),
    StringStruct('FileDescription', 'ArcMouse auto-clicker'),
    StringStruct('FileVersion', '{__version__}'),
    StringStruct('InternalName', 'ArcMouse'),
    StringStruct('OriginalFilename', 'ArcMouse.exe'),
    StringStruct('ProductName', 'ArcMouse'),
    StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
''', encoding='utf-8')
    env = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(build / 'pyinstaller-cache'))
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                    '--onefile', '--windowed', '--noupx', '--name', 'ArcMouse',
                    '--icon', str(ROOT / 'assets' / 'arcmouse.ico'),
                    '--manifest', str(ROOT / 'assets' / 'windows.manifest'),
                    '--version-file', str(metadata), '--hidden-import', 'serial',
                    '--add-data', f'{licenses}:licenses',
                    '--add-data', f'{ROOT / "assets" / "arcmouse.ico"}:assets',
                    '--add-data', f'{ROOT / "LICENSE"}:.',
                    '--specpath', str(build), '--workpath', str(build / 'pyinstaller'),
                    '--distpath', str(ROOT / 'dist'), str(ROOT / 'main.py')],
                   cwd=ROOT, env=env, check=True)
    name = f'ArcMouse-{__version__}-windows-x64'
    executable = release / f'{name}.exe'
    shutil.copy2(ROOT / 'dist' / 'ArcMouse.exe', executable)
    archive_path = release / f'{name}.zip'
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.write(executable, 'ArcMouse.exe')
        for filename in ('README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md'):
            archive.write(ROOT / filename, filename)
        for license_file in sorted(licenses.iterdir()):
            archive.write(license_file, 'licenses/' + license_file.name)
    checksums = release / 'SHA256SUMS.txt'
    checksums.write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n'
                                 for p in (executable, archive_path)), encoding='ascii')
    print(f'Built {executable}\nBuilt {archive_path}')


if __name__ == '__main__':
    main()
