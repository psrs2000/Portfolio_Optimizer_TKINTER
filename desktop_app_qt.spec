# -*- mode: python ; coding: utf-8 -*-
"""
Receita de construcao do executavel (PyInstaller).

Use o "Construir executavel.bat", que prepara o ambiente e chama este arquivo.

Decisoes tomadas aqui, e o porque:

- ONE DIRECTORY (nao one-file). O one-file descompacta ~200 MB numa pasta
  temporaria a CADA execucao, o que deixa toda abertura lenta. Em pasta, esse
  custo nao existe; a primeira abertura ainda demora (o Windows le e escaneia
  os arquivos pela primeira vez), mas as seguintes sao rapidas.

- CONSOLE LIGADO. O programa imprime o andamento da auto-otimizacao (steps,
  composicao da carteira, avisos do solver). Escondendo o console esses logs
  se perdem. Se preferir a janela limpa, troque console=True por False: o
  aplicativo continua funcionando, apenas sem os logs.

- UPX DESLIGADO. Comprime os arquivos, mas cada um precisa ser descomprimido
  ao carregar, atrasando justamente a abertura.
"""

# Modulos locais do projeto. Sao importados normalmente pelo aplicativo, mas
# entram aqui de forma explicita para nao dependerem da analise estatica.
modulos_locais = [
    'optimizer',
    'b3_series_wide_com_limpeza',
    'b3_excel_rendafixa',
    'cvm_fundos',
]

# Dependencias que o PyInstaller nao enxerga sozinho (carregadas em tempo de
# execucao pelas bibliotecas).
ocultos = [
    'requests',
    'openpyxl',
    'scipy.optimize',
    'scipy.special.cython_special',
    'matplotlib.backends.backend_qtagg',
]

# Pacotes OPCIONAIS: so entram se estiverem instalados. Assim a construcao nao
# quebra em quem nao usa a importacao pelo Yahoo ou via Excel.
for _pacote in ('yfinance', 'curl_cffi', 'peewee', 'multitasking',
                'websockets', 'bs4', 'xlwings'):
    try:
        __import__(_pacote)
    except Exception:
        pass
    else:
        ocultos.append(_pacote)

# Nada disso e usado pelo aplicativo. Fora do pacote, o executavel fica menor
# e a primeira abertura mais rapida (menos arquivos para o antivirus varrer).
# O matplotlib usa o backend Qt (fixado no codigo), entao o tkinter nao entra.
descartados = [
    'tkinter',
    'tkcalendar',
    'IPython',
    'jupyter',
    'notebook',
    'pytest',
    'sphinx',
]


a = Analysis(
    ['desktop_app_qt.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=modulos_locais + ocultos,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=descartados,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Otimizador de Portfolio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Otimizador de Portfolio',
)
