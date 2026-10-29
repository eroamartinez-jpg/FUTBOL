# Compilar con:  pyinstaller pocket_bot/pocket_bot.spec
import os

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all("BinaryOptionsToolsV2")
hiddenimports += collect_all("tzdata")[2]
datas += collect_all("tzdata")[0]

a = Analysis(
    ["launcher.py"],
    pathex=[os.path.join(SPECPATH, "..")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["matplotlib", "scipy", "sklearn", "tkinter", "IPython"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="pocket_bot",
    console=True,
    upx=False,
)
