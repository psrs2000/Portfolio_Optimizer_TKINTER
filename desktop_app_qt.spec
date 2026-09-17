# -*- mode: python ; coding: utf-8 -*-
"""
Receita de construcao do executavel (PyInstaller).

Use o "Construir executavel.bat", que prepara o ambiente e chama este arquivo.

Decisoes tomadas aqui, e o porque:

- ARQUIVO UNICO (one-file). Gera um unico .exe, que e o programa inteiro:
  simples de enviar ao usuario final, que nao tem como errar qual arquivo
  abrir. O custo e a abertura: o executavel descompacta o conteudo numa pasta
  temporaria a CADA execucao, entao ele sempre leva alguns segundos para
  abrir. Se um dia a velocidade pesar mais que a facilidade de distribuir,
  basta reativar o bloco COLLECT no final deste arquivo (ver comentario la).

- CONSOLE LIGADO. O programa imprime o andamento da auto-otimizacao (steps,
  composicao da carteira, avisos do solver). Escondendo o console esses logs
  se perdem. Se preferir a janela limpa, troque console=True por False: o
  aplicativo continua funcionando, apenas sem os logs.

- UPX DESLIGADO. Comprime os arquivos, mas cada um precisa ser descomprimido
  ao carregar, atrasando ainda mais a abertura — que no modo arquivo unico ja
  e o ponto sensivel.
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

# Arquivo unico: binarios e dados entram DENTRO do proprio .exe.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Otimizador de Portfolio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# ---------------------------------------------------------------------------
# Para voltar ao modo PASTA (abertura bem mais rapida, porem varios arquivos
# para distribuir): em EXE acima, troque as tres linhas
#     a.scripts, a.binaries, a.datas, [],
# por
#     a.scripts, [],
# acrescente  exclude_binaries=True,  remova  runtime_tmpdir=None,  e
# descomente o bloco abaixo.
#
# coll = COLLECT(
#     exe,
#     a.binaries,
#     a.datas,
#     strip=False,
#     upx=False,
#     upx_exclude=[],
#     name='Otimizador de Portfolio',
# )
# ---------------------------------------------------------------------------
