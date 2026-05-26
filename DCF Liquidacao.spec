# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['interface.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('configuracoes.json', '.'),
        ('DCF - CONTRATOS.csv', '.'),
    ],
    hiddenimports=[
        'extrator',
        'consulta_cnpj',
        'comprasnet_base',
        'comprasnet_dados_basicos',
        'comprasnet_principal_orcamento',
        'comprasnet_deducao',
        'comprasnet_centro_custo',
        'comprasnet_dados_pagamento',
        'comprasnet_finalizar',
        'de_para_contratos',
        'abrir_chrome',
        'solar_fila',
    ],
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
    [],
    exclude_binaries=True,
    name='DCF Liquidacao',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
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
    upx=True,
    upx_exclude=[],
    name='DCF Liquidacao',
)
app = BUNDLE(
    coll,
    name='DCF Liquidacao.app',
    icon=None,
    bundle_identifier=None,
)
