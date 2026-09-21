"""
cvm_fundos.py
=============
Baixa e consolida COTAS DIÁRIAS de fundos de investimento a partir dos dados
abertos da CVM, entregando uma matriz Data × Fundos pronta para o otimizador.

Baseado em filtro_fundos_cvm_V36.py: a lógica de leitura foi preservada, porque
os CSVs da CVM mudam de formato conforme o ano (nome da coluna de CNPJ,
codificação e formato de data variam). Sobre ela foi acrescentada a camada de
download e um cache local, para o usuário não precisar baixar nada à mão.

Fontes (dados abertos da CVM):
  - Cadastro (nomes dos fundos):
        https://dados.cvm.gov.br/dados/FI/CAD/DADOS/cad_fi_hist.zip
        -> contém cad_fi_hist_denom_social.csv
  - Informe diário, a partir de 2021 (um zip por MÊS):
        https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_YYYYMM.zip
  - Informe diário, antes de 2021 (um zip por ANO, com 12 CSVs dentro):
        https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/HIST/inf_diario_fi_YYYY.zip

Dependências: requests, pandas.
"""

import io
import os
import re
import zipfile
import unicodedata
from datetime import datetime

import pandas as pd
import requests

# --------------------------------------------------------------------------- #
# Endereços e constantes
# --------------------------------------------------------------------------- #
URL_CADASTRO = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/cad_fi_hist.zip"
URL_INF_DIARIO = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/"
URL_INF_DIARIO_HIST = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/HIST/"

ARQ_CADASTRO_CSV = "cad_fi_hist_denom_social.csv"

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/122.0.0.0 Safari/537.36")
}

# Ordem de codificações que funciona com os arquivos da CVM (do original)
ENCODINGS = ['cp1252', 'latin1', 'iso-8859-1', 'utf-8-sig', 'utf-8']

# O nome da coluna do CNPJ muda conforme o ano do arquivo (do original)
COLUNAS_CNPJ = ['CNPJ_FUNDO_CLASSE', 'CNPJ_FUNDO', 'CNPJ', 'CD_CNPJ', 'CNPJ_FI']

# Só estas colunas interessam para montar a série de cotas
COLUNAS_UTEIS = ['CNPJ_FUNDO_CLASSE', 'DT_COMPTC', 'VL_QUOTA']

# Leitura em blocos: cada informe diário tem milhões de linhas (todos os fundos
# do Brasil), mas guardamos só as poucas milhares dos fundos pedidos.
CHUNK_LINHAS = 200_000


def _norm(txt):
    txt = unicodedata.normalize("NFKD", str(txt))
    return txt.encode("ascii", "ignore").decode("ascii").strip().lower()


def so_digitos(cnpj):
    """
    Reduz o CNPJ aos dígitos, para comparar sem depender da formatação.
    Os arquivos da CVM ora trazem '29.152.383/0001-03', ora '29152383000103'.
    """
    return re.sub(r'\D', '', str(cnpj))


# --------------------------------------------------------------------------- #
# Download com cache
# --------------------------------------------------------------------------- #
def _baixar(url, timeout=180):
    resp = requests.get(url, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def _extrair_zip(conteudo, destino, filtro=None):
    """
    Extrai para `destino` os membros .csv do zip. `filtro` é uma função que
    recebe o nome do membro e diz se ele interessa. Devolve os caminhos criados.
    """
    os.makedirs(destino, exist_ok=True)
    criados = []
    with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
        for nome in zf.namelist():
            if not nome.lower().endswith('.csv'):
                continue
            if filtro is not None and not filtro(nome):
                continue
            destino_arq = os.path.join(destino, os.path.basename(nome))
            with zf.open(nome) as origem, open(destino_arq, 'wb') as saida:
                saida.write(origem.read())
            criados.append(destino_arq)
    return criados


def baixar_cadastro(cache_dir, forcar=False):
    """
    Garante o cad_fi_hist_denom_social.csv no cache e devolve seu caminho.
    Só baixa se ainda não existir (ou se forcar=True).
    """
    destino = os.path.join(cache_dir, ARQ_CADASTRO_CSV)
    if os.path.exists(destino) and not forcar:
        return destino

    conteudo = _baixar(URL_CADASTRO)
    criados = _extrair_zip(
        conteudo, cache_dir,
        filtro=lambda n: os.path.basename(n).lower() == ARQ_CADASTRO_CSV.lower())
    if not criados:
        # Se o nome mudar, aceita qualquer CSV que mencione denominação social
        criados = _extrair_zip(
            conteudo, cache_dir,
            filtro=lambda n: 'denom' in os.path.basename(n).lower())
    if not criados:
        raise RuntimeError(
            f"O zip do cadastro não continha '{ARQ_CADASTRO_CSV}'.\n{URL_CADASTRO}")
    return criados[0]


def arquivos_baixados(cache_dir):
    """
    Lista os arquivos que ESTE modulo baixou para o cache.

    Serve para limpar o cache sem risco: a pasta e escolhida pelo usuario e
    pode conter arquivos dele (o CNPJ.csv, por exemplo), entao nunca apagamos
    a pasta inteira — apenas o que sabemos ter baixado.
    """
    if not cache_dir or not os.path.isdir(cache_dir):
        return []
    alvos = []
    for nome in os.listdir(cache_dir):
        baixo = nome.lower()
        if not baixo.endswith('.csv'):
            continue
        # Exatamente os dois padroes que baixamos/extraimos
        if baixo.startswith('inf_diario_fi_') or baixo.startswith('cad_fi_hist'):
            alvos.append(os.path.join(cache_dir, nome))
    return alvos


def limpar_cache(cache_dir):
    """
    Apaga do cache os arquivos baixados por este modulo e devolve quantos foram
    removidos. Arquivos do usuario (CNPJ.csv, planilhas etc.) NAO sao tocados,
    e a pasta so e removida se ficar vazia.
    """
    removidos = 0
    for caminho in arquivos_baixados(cache_dir):
        try:
            os.remove(caminho)
            removidos += 1
        except OSError:
            pass
    try:
        if os.path.isdir(cache_dir) and not os.listdir(cache_dir):
            os.rmdir(cache_dir)
    except OSError:
        pass
    return removidos


def _csv_do_mes(cache_dir, ano, mes):
    """Caminho do CSV mensal no cache, se já estiver lá."""
    caminho = os.path.join(cache_dir, f"inf_diario_fi_{ano}{mes:02d}.csv")
    return caminho if os.path.exists(caminho) else None


def baixar_informe_mes(cache_dir, ano, mes):
    """
    Garante no cache o informe diário de um mês e devolve o caminho do CSV.

    Tenta primeiro o zip MENSAL (formato usado de 2021 em diante) e, se não
    houver, o zip ANUAL da pasta HIST (anos anteriores), que traz os 12 meses
    de uma vez — nesse caso todos ficam em cache e os meses seguintes do mesmo
    ano não geram novo download.
    """
    ja = _csv_do_mes(cache_dir, ano, mes)
    if ja:
        return ja

    ym = f"{ano}{mes:02d}"

    # 1) Zip mensal (DADOS/)
    try:
        conteudo = _baixar(f"{URL_INF_DIARIO}inf_diario_fi_{ym}.zip")
        _extrair_zip(conteudo, cache_dir)
        ja = _csv_do_mes(cache_dir, ano, mes)
        if ja:
            return ja
    except requests.HTTPError:
        pass  # não existe como mensal: cai para o histórico anual

    # 2) Zip anual (DADOS/HIST/) — contém os 12 meses
    try:
        conteudo = _baixar(f"{URL_INF_DIARIO_HIST}inf_diario_fi_{ano}.zip")
        _extrair_zip(conteudo, cache_dir)
        ja = _csv_do_mes(cache_dir, ano, mes)
        if ja:
            return ja
    except requests.HTTPError:
        pass

    return None


# --------------------------------------------------------------------------- #
# Leitura dos arquivos (lógica preservada do filtro_fundos_cvm)
# --------------------------------------------------------------------------- #
def _ler_csv(caminho, **kwargs):
    """Lê um CSV da CVM tentando as codificações na ordem que funciona."""
    ultimo_erro = None
    for enc in ENCODINGS:
        try:
            return pd.read_csv(caminho, sep=';', encoding=enc,
                               low_memory=False, **kwargs)
        except UnicodeDecodeError as e:
            ultimo_erro = e
            continue
    raise RuntimeError(f"Não foi possível ler {os.path.basename(caminho)}: {ultimo_erro}")


def carregar_cadastro(caminho_csv):
    """
    Lê o cadastro e devolve um DataFrame [CNPJ_DIGITOS, DENOM_SOCIAL] apenas com
    os nomes VIGENTES (DT_FIM_DENOM_SOCIAL vazio), um por fundo — o mais recente
    quando há mais de um.
    """
    df = None
    for enc in ENCODINGS:
        try:
            df = pd.read_csv(caminho_csv, sep=';', encoding=enc, low_memory=False,
                             dtype=str, skipinitialspace=True, quoting=3)
            break
        except UnicodeDecodeError:
            continue
    if df is None:
        raise RuntimeError(f"Não foi possível ler {ARQ_CADASTRO_CSV}")

    df['CNPJ_FUNDO'] = df['CNPJ_FUNDO'].astype(str).str.strip()
    df['DT_FIM_DENOM_SOCIAL'] = (df['DT_FIM_DENOM_SOCIAL']
                                 .fillna('').astype(str).str.strip())

    # Vigentes = sem data de fim
    vigentes = df[df['DT_FIM_DENOM_SOCIAL'].isin(['', 'nan', 'NaN', 'None'])].copy()

    # Se houver mais de um vigente por fundo, fica com o de início mais recente
    if 'DT_INI_DENOM_SOCIAL' in vigentes.columns:
        vigentes['DT_INI_DENOM_SOCIAL'] = pd.to_datetime(
            vigentes['DT_INI_DENOM_SOCIAL'], errors='coerce')
        vigentes = (vigentes.sort_values('DT_INI_DENOM_SOCIAL')
                            .groupby('CNPJ_FUNDO').last().reset_index())
    else:
        vigentes = vigentes.drop_duplicates(subset=['CNPJ_FUNDO'], keep='last')

    vigentes['CNPJ_DIGITOS'] = vigentes['CNPJ_FUNDO'].map(so_digitos)
    return vigentes[['CNPJ_DIGITOS', 'CNPJ_FUNDO', 'DENOM_SOCIAL']]


def converter_datas(serie):
    """
    Converte a coluna DT_COMPTC respeitando o formato do arquivo.

    Os informes trazem a data em dois formatos conforme o ano:
        dd/mm/aaaa   (arquivos mais antigos)
        aaaa-mm-dd   (arquivos mais novos)

    O formato é DETECTADO e aplicado explicitamente, como no filtro original.
    Não usar dayfirst=True com format='mixed': essa combinação lê '2024-01-05'
    como 2024-05-01, trocando dia e mês sempre que o dia é menor ou igual a 12
    — e o estrago é silencioso, porque a data continua existindo.

    Linhas que não casarem com o formato detectado são tentadas no outro, para
    o caso raro de um arquivo misturar os dois.
    """
    s = serie.astype(str).str.strip()
    amostra = next((v for v in s if v and v.lower() != 'nan'), '')

    if '/' in amostra:
        principal, reserva = '%d/%m/%Y', '%Y-%m-%d'
    else:
        principal, reserva = '%Y-%m-%d', '%d/%m/%Y'

    datas = pd.to_datetime(s, format=principal, errors='coerce')
    faltando = datas.isna()
    if faltando.any():
        datas[faltando] = pd.to_datetime(s[faltando], format=reserva, errors='coerce')
    return datas


def processar_csv_diario(caminho, cnpjs_digitos):
    """
    Lê um informe diário mensal e devolve só as linhas dos fundos pedidos,
    com as colunas [CNPJ_DIGITOS, DT_COMPTC, VL_QUOTA].

    Trata as variações entre anos: nome da coluna do CNPJ, codificação e data
    em dd/mm/aaaa ou aaaa-mm-dd. A leitura é feita em blocos porque cada arquivo
    traz todos os fundos do país.
    """
    partes = []
    for enc in ENCODINGS:
        try:
            leitor = pd.read_csv(caminho, sep=';', encoding=enc, dtype=str,
                                 chunksize=CHUNK_LINHAS, low_memory=False)
            for bloco in leitor:
                col_cnpj = next((c for c in COLUNAS_CNPJ if c in bloco.columns), None)
                if col_cnpj is None:
                    return None  # formato inesperado
                if 'DT_COMPTC' not in bloco.columns or 'VL_QUOTA' not in bloco.columns:
                    return None

                bloco = bloco[[col_cnpj, 'DT_COMPTC', 'VL_QUOTA']].copy()
                bloco.columns = ['CNPJ', 'DT_COMPTC', 'VL_QUOTA']
                bloco['CNPJ_DIGITOS'] = bloco['CNPJ'].map(so_digitos)
                bloco = bloco[bloco['CNPJ_DIGITOS'].isin(cnpjs_digitos)]
                if not bloco.empty:
                    partes.append(bloco[['CNPJ_DIGITOS', 'DT_COMPTC', 'VL_QUOTA']])
            break  # a codificação funcionou
        except UnicodeDecodeError:
            partes = []
            continue

    if not partes:
        return None

    df = pd.concat(partes, ignore_index=True)
    # Datas: formato detectado explicitamente (ver converter_datas)
    df['DT_COMPTC'] = converter_datas(df['DT_COMPTC'])
    df['VL_QUOTA'] = pd.to_numeric(
        df['VL_QUOTA'].astype(str).str.replace(',', '.', regex=False),
        errors='coerce')
    return df.dropna(subset=['DT_COMPTC'])


def meses_do_periodo(d_ini, d_fim):
    """Lista de (ano, mes) cobrindo o período, inclusive as pontas."""
    meses = []
    ano, mes = d_ini.year, d_ini.month
    while (ano, mes) <= (d_fim.year, d_fim.month):
        meses.append((ano, mes))
        mes += 1
        if mes > 12:
            ano, mes = ano + 1, 1
    return meses


def ler_cnpjs_arquivo(caminho):
    """Lê CNPJs de um CSV (um por linha ou separados por , / ;)."""
    cabecalhos = {"cnpj", "cnpjs", "cnpj_fundo", "cnpj_fundo_classe",
                  "fundo", "fundos", "codigo", "codigos"}
    with open(caminho, "r", encoding="utf-8-sig") as fh:
        bruto = fh.read()
    itens, vistos = [], set()
    for pedaco in bruto.replace(";", "\n").replace(",", "\n").splitlines():
        item = pedaco.strip()
        if not item or _norm(item) in cabecalhos:
            continue
        if item not in vistos:
            vistos.add(item)
            itens.append(item)
    return itens


# --------------------------------------------------------------------------- #
# Fluxo completo
# --------------------------------------------------------------------------- #
def buscar_cotas_fundos(cnpjs, data_ini, data_fim, cache_dir, progress=None):
    """
    Baixa (se preciso), lê e consolida as cotas dos fundos pedidos.

    Devolve (wide, faltantes):
      wide      : DataFrame [Data, <NOME DO FUNDO>, ...] com VL_QUOTA
      faltantes : CNPJs pedidos que não renderam dados no período

    progress(i, total, item) é chamado a cada etapa, para a barra de progresso.
    """
    os.makedirs(cache_dir, exist_ok=True)
    alvo = {so_digitos(c) for c in cnpjs if so_digitos(c)}
    if not alvo:
        raise ValueError("Nenhum CNPJ válido informado.")

    meses = meses_do_periodo(data_ini, data_fim)
    total_etapas = len(meses) + 1  # +1 do cadastro

    # 1) Cadastro (nomes dos fundos)
    if progress:
        progress(0, total_etapas, "cadastro de fundos")
    caminho_cad = baixar_cadastro(cache_dir)
    cadastro = carregar_cadastro(caminho_cad)

    # 2) Informes diários, mês a mês
    partes = []
    for i, (ano, mes) in enumerate(meses, start=1):
        if progress:
            progress(i, total_etapas, f"{mes:02d}/{ano}")
        try:
            caminho = baixar_informe_mes(cache_dir, ano, mes)
        except Exception:
            caminho = None
        if not caminho:
            continue
        parcial = processar_csv_diario(caminho, alvo)
        if parcial is not None and not parcial.empty:
            partes.append(parcial)

    if progress:
        progress(total_etapas, total_etapas, None)

    if not partes:
        raise RuntimeError(
            "Nenhum dado encontrado para os CNPJs no período.\n"
            "Verifique os CNPJs e se o período tem informes publicados.")

    df = pd.concat(partes, ignore_index=True)

    # 3) Recorte fino pelo período pedido (os arquivos são mensais)
    df = df[(df['DT_COMPTC'] >= pd.Timestamp(data_ini)) &
            (df['DT_COMPTC'] <= pd.Timestamp(data_fim))]
    if df.empty:
        raise RuntimeError("Os arquivos vieram, mas nenhum registro caiu no período pedido.")

    # 4) Nome do fundo (sem nome, não há como rotular a coluna)
    df = df.merge(cadastro[['CNPJ_DIGITOS', 'DENOM_SOCIAL']],
                  on='CNPJ_DIGITOS', how='left')
    sem_nome = sorted(df.loc[df['DENOM_SOCIAL'].isna(), 'CNPJ_DIGITOS'].unique())
    df = df.dropna(subset=['DENOM_SOCIAL'])
    if df.empty:
        raise RuntimeError("Os fundos encontrados não têm denominação social no cadastro.")

    # 5) Matriz Data × Fundos
    wide = df.pivot_table(index='DT_COMPTC', columns='DENOM_SOCIAL',
                          values='VL_QUOTA', aggfunc='last').sort_index()
    wide = wide.reset_index().rename(columns={'DT_COMPTC': 'Data'})
    wide.columns.name = None

    encontrados = set(df['CNPJ_DIGITOS'].unique())
    faltantes = [c for c in cnpjs if so_digitos(c) not in encontrados]
    faltantes += [f"{c} (sem nome no cadastro)" for c in sem_nome]
    return wide, faltantes
