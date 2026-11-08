# deskdancer.spec  v1.5.0 — сборка DeskDancer.exe (PyInstaller, onefile)
# Журнал:
# v1.5.0: без изменений сборки
# v1.4.0: QtQuick нужен (альфа-буфер прозрачной сцены)
# v1.3.0: без изменений сборки
# v1.2.0: без изменений сборки
# v1.1.0: без изменений сборки (девушки в комплекте копирует build_exe.bat)
# v1.0.0: первая версия — QtWebEngine нужен (3D-сцена), web/ внутрь exe;
#         characters/ и dances/ — рядом с exe (свои модели пользователя)
block_cipher = None

a = Analysis(
    ['DeskDancer.pyw'],
    pathex=['.'],
    binaries=[],
    datas=[('web', 'web')],
    hiddenimports=['deskdancer_qt', 'PySide6.QtQuick', 'soundcard', 'soundcard.mediafoundation',
                   'app.gh_update', 'app.gh_update_qt', 'app.gh_update_help',
                   'app.window_frame', 'app.theme'],
    excludes=['tkinter', 'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.QtCharts',
              'PySide6.QtMultimedia', 'PySide6.QtDataVisualization', 'PySide6.QtBluetooth'],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='DeskDancer',
    console=False,
    upx=False,
    icon=None,
)
