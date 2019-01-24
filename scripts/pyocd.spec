# -*- mode: python -*-

import os
import glob
import platform
from PyInstaller.utils.hooks import (get_package_paths, collect_dynamic_libs)

is_windows = (platform.system() == "Windows")

block_cipher = None

# Code from the pyinstaller GitHub wiki.
def Entrypoint(dist, group, name, **kwargs):
    import pkg_resources

    # get toplevel packages of distribution from metadata
    def get_toplevel(dist):
        distribution = pkg_resources.get_distribution(dist)
        if distribution.has_metadata('top_level.txt'):
            return list(distribution.get_metadata('top_level.txt').split())
        else:
            return []

    kwargs.setdefault('hiddenimports', [])
    packages = []
    for distribution in kwargs['hiddenimports']:
        packages += get_toplevel(distribution)

    kwargs.setdefault('pathex', [])
    # get the entry point
    ep = pkg_resources.get_entry_info(dist, group, name)
    # insert path of the egg at the very front of the search path
    kwargs['pathex'] = [ep.dist.location] + kwargs['pathex']
    # script name must not be a valid module name to avoid name clashes on import
    script_path = os.path.join(workpath, name + '-script.py')
    print("creating script for entry point", dist, group, name)
    with open(script_path, 'w') as fh:
        print("import", ep.module_name, file=fh)
        print("%s.%s()" % (ep.module_name, '.'.join(ep.attrs)), file=fh)
        for package in packages:
            print("import", package, file=fh)

    return Analysis(
        [script_path] + kwargs.get('scripts', []),
        **kwargs
    )

# Get binary extension libraries...

# Capstone for disassembly.
capstone_libs = collect_dynamic_libs("capstone")

# CPM's native lib doesn't match the patterns that collect_dynamic_libs() expects.
cpm_path = get_package_paths('cmsis_pack_manager')[1]
if is_windows:
    # Example: _native__lib.cp37-win_amd64.pyd
    matches = glob.glob(os.path.join(cpm_path, "*.pyd"))
    if matches:
        cpm_lib_name = matches[0]
    else:
        raise Exception("failed to find cmsis-pack-manager native library")
else:
    cpm_lib_name = "_native__lib.so"
cpm_libs = [(os.path.join(cpm_path, cpm_lib_name), "cmsis_pack_manager")]

binaries = capstone_libs + cpm_libs

a = Entrypoint('pyocd', 'console_scripts', 'pyocd',
                binaries=binaries,
                excludes=[
                    'FixTk',
                    'tcl',
                    'tk',
                    '_tkinter',
                    'tkinter',
                    'Tkinter',
                    ])

pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          [],
          name='pyocd',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=(not is_windows), # upx caused failures on windows
          runtime_tmpdir=None,
          console=True )
