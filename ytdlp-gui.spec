# -*- mode: python ; coding: utf-8 -*-
"""Сборка yt-dlp GUI в один самодостаточный .exe.

Собирается из каталога проекта:

    pyinstaller ytdlp-gui.spec --noconfirm

Внутрь бандла кладутся переводы интерфейса и сам ``yt-dlp.exe``, поэтому
готовый файл ``dist/ytdlp-gui.exe`` можно перенести в любой каталог и
запустить откуда угодно — внешние файлы рядом с ним не нужны. Если рядом
с .exe (или в подкаталоге ``bin``) всё же положить свой ``yt-dlp.exe``,
использоваться будет он: локальная копия имеет приоритет над встроенной.

FFmpeg не вшивается — он нужен не всегда, весит больше самого приложения
и обычно уже установлен в системе. Приложение ищет его рядом с собой, в
``PATH`` и в стандартных каталогах; путь можно указать в настройках.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

PROJECT_DIR = Path(SPECPATH)

datas = [('ytdlp_gui/resources', 'ytdlp_gui/resources')]
binaries = []
hiddenimports = ['PIL._tkinter_finder']

# yt-dlp кладём как data, а не как binary: это самостоятельное
# приложение, а не библиотека, от которой зависит наш код, — и
# анализатор зависимостей PyInstaller не должен пытаться разбирать его
# импорты и тянуть за собой чужие DLL.
#
# yt-dlp распространяется в двух видах, и от этого зависит, что вшивать:
#   * однофайловый релиз с сайта проекта (~17 МБ) — самодостаточен;
#   * сборка в режиме onedir (~7 МБ) — рядом обязан лежать каталог
#     `_internal` с её интерпретатором. Без него exe запускается, но
#     сразу падает с «Failed to load Python DLL» и молча ничего не
#     выводит.
# Кладём всё в подкаталог `bin` — там приложение и так ищет бинарники.
YTDLP_BINARY = PROJECT_DIR / 'yt-dlp.exe'
YTDLP_INTERNAL = PROJECT_DIR / '_internal'
#: Ниже этого размера yt-dlp.exe — почти наверняка onedir-сборка.
ONEFILE_MIN_BYTES = 15 * 1024 * 1024

if not YTDLP_BINARY.is_file():
    raise SystemExit(
        f'{YTDLP_BINARY} не найден: положите yt-dlp.exe рядом со спекой '
        '(https://github.com/yt-dlp/yt-dlp/releases) или уберите этот блок, '
        'если бинарник вшивать не нужно.'
    )
datas += [(str(YTDLP_BINARY), 'bin')]

if YTDLP_BINARY.stat().st_size < ONEFILE_MIN_BYTES:
    if not YTDLP_INTERNAL.is_dir():
        raise SystemExit(
            f'{YTDLP_BINARY.name} похож на onedir-сборку, но каталога '
            f'{YTDLP_INTERNAL.name} рядом нет: вшитый yt-dlp не запустится.'
        )
    datas += [(str(YTDLP_INTERNAL), 'bin/_internal')]

tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['ytdlp_gui/main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ytdlp-gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
