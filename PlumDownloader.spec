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
    a.binaries,
    a.datas,
    [],
    name='PlumDownloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    icon='static/favicon.ico',
)

if sys.platform == 'darwin':
    coll = BUNDLE(
        exe,
        name='PlumDownloader.app',
        icon=None,
        bundle_identifier='com.plum.downloader',
    )