# Build on the target OS. Never cross-compile Windows executables on Linux.
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_all, copy_metadata

root = Path(SPECPATH).parent
ortools_data, ortools_binaries, ortools_hidden = collect_all('ortools')
# Managed Linux Python builds can keep Tcl/Tk outside the dynamic linker search path.
tk_binaries = [(str(path), '.') for pattern in ('libtcl*.so', 'libtk*.so')
               for path in (Path(sys.base_prefix) / 'lib').glob(pattern)]
a = Analysis(
    [str(root / 'packaging' / 'desktop_entry.py')],
    pathex=[str(root / 'src')],
    binaries=ortools_binaries + tk_binaries,
    datas=ortools_data + copy_metadata('ortools') + copy_metadata('lottery-system'),
    hiddenimports=ortools_hidden + ['tkinter', 'tkinter.ttk', 'tkinter.filedialog', 'tkinter.messagebox', 'lottery.gui'],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='PTACarnivalLottery',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=(sys.platform != 'win32'), disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='PTACarnivalLottery')
