# -*- mode: python ; coding: utf-8 -*-
# jotunnslayer 发行版 spec
a = Analysis(
    ['G:/repos/jotunnslayer/main.py'],
    pathex=['G:/repos/jotunnslayer'],
    binaries=[],
    datas=[

    ],
    hiddenimports=[

    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch','cupy','dask','jax','jaxlib','ndonnx','sparse','sqlalchemy','matplotlib','IPython','Cython','setuptools','traitlets','jedi','pygments','yt_dlp','playwright','botocore','boto3','transformers','tokenizers','pyarrow','llvmlite','numba','scipy','sklearn','scikit-learn','imageio','imageio_ffmpeg','tensorflow','keras','moviepy','sympy','statsmodels','nltk','networkx','PyQt5','PyQt6','PySide2','PySide6','pymongo','bson'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='jotunnslayer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    contents_directory='.',
)