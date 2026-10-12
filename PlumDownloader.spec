# -*- mode: python ; coding: utf-8 -*-
import sys

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
    ],
    hiddenimports=[
        'flask',
        'yt_dlp',
        'mutagen',
        'mutagen.mp4',
        'mutagen.easyid3',
        'mutagen.id3',
        'musicbrainzngs',
        'requests',
        'static_ffmpeg',
        'queue',
        'threading',
        'webbrowser',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PlumDownloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='static/favicon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='PlumDownloader',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='PlumDownloader.app',
        icon='icons/PlumDownloader.icns',
        bundle_identifier='com.plum.downloader',
    )