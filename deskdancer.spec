# deskdancer.spec  v2.0.0 — сборка DeskDancer.exe (PyInstaller, onefile)
# Журнал:
# v2.0.0: без браузера — QtWebEngine и web/ не нужны (exe намного меньше); Panda3D
#         целиком (модули графики pandagl / pandadx9 / p3tinydisplay грузятся по имени)
# v1.4.0: QtQuick нужен (альфа-буфер прозрачной сцены)
# v1.0.0: первая версия; characters/ и dances/ — рядом с exe (свои модели пользователя)
from PyInstaller.utils.hooks import collect_all

block_cipher = None
p3d_datas, p3d_bins, p3d_hidden = collect_all('panda3d')

a = Analysis(
    ['DeskDancer.pyw'],
    pathex=['.'],
    binaries=p3d_bins,
    datas=p3d_datas,
    hiddenimports=p3d_hidden + ['deskdancer_qt', 'soundcard', 'soundcard.mediafoundation',
                                'app.engine3d', 'app.gltf_anim', 'app.gltf_mesh', 'app.neon',
                                'app.gh_update', 'app.gh_update_qt', 'app.gh_update_help',
                                'app.window_frame', 'app.theme'],
    excludes=['tkinter', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
              'PySide6.QtQuick', 'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.QtCharts',
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
