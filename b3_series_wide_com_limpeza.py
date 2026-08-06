"""
b3_series_wide.py  (versão interativa)
======================================
Gera uma planilha (CSV + XLSX) de séries de preços da B3 no formato:

    Data       | ATIVO1 | ATIVO2 | ATIVO3 | ...
    02/01/2026 |  30.71 |  72.38 |  ...   |

Ao executar, o programa PERGUNTA:
  - Data de início
  - Data final (ENTER = hoje)
  - Tipo de preço (Abertura / Máximo / Mínimo / Fechamento)

Depois lê os ativos do arquivo "Simbolos.csv" (um código por linha),
baixa os arquivos COTAHIST anuais da B3 (sem captcha, via URL direta),
filtra pelo período e pelos ativos, e grava dois arquivos de saída.

Dependências:
    pip install requests pandas openpyxl
"""

import io
import os
import sys
import time
import zipfile
import unicodedata
from datetime import datetime

import pandas as pd
import requests

# Evita erro de emoji/acentos no console do Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# =========================================================================== #
#  Ajustes opcionais (normalmente não precisa mexer)                          #
# =========================================================================== #
ARQUIVO_SIMBOLOS = "Simbolos.csv"    # arquivo com os códigos dos ativos
SAIDA_CSV        = "series_precos.csv"
SAIDA_XLSX       = "series_precos.xlsx"
SOMENTE_VISTA    = True              # True = só mercado à vista (ações). Recomendado.
PAUSA_ENTRE_ANOS = 1.0               # segundos de pausa entre downloads de anos
# =========================================================================== #

BASE_URL = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

_COLSPECS = [
    ("tipreg", (0, 2)),    ("data",   (2, 10)),   ("codbdi", (10, 12)),
    ("codneg", (12, 24)),  ("tpmerc", (24, 27)),  ("nomres", (27, 39)),
    ("especi", (39, 49)),  ("prazot", (49, 52)),  ("modref", (52, 56)),
    ("preabe", (56, 69)),  ("premax", (69, 82)),  ("premin", (82, 95)),
    ("premed", (95, 108)), ("preult", (108, 121)),("preofc", (121, 134)),
    ("preofv", (134, 147)),("totneg", (147, 152)),("quatot", (152, 170)),
    ("voltot", (170, 188)),("preexe", (188, 201)),("indopc", (201, 202)),
    ("datven", (202, 210)),("fatcot", (210, 217)),("ptoexe", (217, 230)),
    ("codisi", (230, 242)),("dismes", (242, 245)),
]
_COLNAMES = [c[0] for c in _COLSPECS]
_POSITIONS = [c[1] for c in _COLSPECS]
_PRICE_COLS = ["preabe", "premax", "premin", "premed", "preult",
               "preofc", "preofv", "voltot", "preexe"]

_MAPA_PRECO = {
    "abertura":   ("preabe", "Abertura"),
    "maximo":     ("premax", "Máximo"),
    "minimo":     ("premin", "Mínimo"),
    "fechamento": ("preult", "Fechamento"),
}


# --------------------------------------------------------------------------- #
#  Entrada interativa                                                          #
# --------------------------------------------------------------------------- #
def _norm(txt: str) -> str:
    txt = unicodedata.normalize("NFKD", str(txt))
    txt = txt.encode("ascii", "ignore").decode("ascii")
    return txt.strip().lower()


def validar_data(data_string: str) -> datetime:
    """Aceita DD/MM/AAAA, DD-MM-AAAA, AAAA-MM-DD (e variações de 2 dígitos)."""
    formatos = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y"]
    for formato in formatos:
        try:
            return datetime.strptime(data_string, formato)
        except ValueError:
            continue
    raise ValueError(f"Formato de data inválido: {data_string}")


def solicitar_datas():
    """Pergunta e valida as datas de início e fim."""
    print("\n📅 PERÍODO")
    print("-" * 40)
    print("Formatos aceitos: DD/MM/AAAA, DD-MM-AAAA, AAAA-MM-DD")
    print("Exemplos: 02/01/2026, 15-06-2024, 2024-01-01")

    while True:
        try:
            ini_str = input("\n📅 Data de INÍCIO (ex: 02/01/2026): ").strip()
            if not ini_str:
                print("❌ A data de início é obrigatória!")
                continue
            data_inicio = validar_data(ini_str)

            fim_str = input("📅 Data FINAL (ex: 31/01/2026) ou ENTER para hoje: ").strip()
            if not fim_str:
                data_fim = datetime.now()
                print(f"   → Usando hoje: {data_fim.strftime('%d/%m/%Y')}")
            else:
                data_fim = validar_data(fim_str)

            if data_inicio > data_fim:
                print("❌ A data de início deve ser anterior (ou igual) à data final!")
                continue

            print("\n✅ Período selecionado:")
            print(f"   • Início: {data_inicio.strftime('%d/%m/%Y')}")
            print(f"   • Fim:    {data_fim.strftime('%d/%m/%Y')}")
            return data_inicio, data_fim

        except ValueError as e:
            print(f"❌ {e}. Tente novamente.")
        except KeyboardInterrupt:
            print("\n\n👋 Operação cancelada.")
            return None, None


def solicitar_tipo_preco() -> str:
    """Menu para escolher o tipo de preço. Retorna o rótulo (ex.: 'Fechamento')."""
    opcoes = {"1": "Abertura", "2": "Máximo", "3": "Mínimo", "4": "Fechamento"}
    print("\n💰 TIPO DE PREÇO")
    print("-" * 40)
    for k, v in opcoes.items():
        print(f"   {k}. {v}")
    while True:
        escolha = input("\nDigite o número (padrão: 4 - Fechamento): ").strip()
        if escolha == "":
            return "Fechamento"
        if escolha in opcoes:
            return opcoes[escolha]
        print("❌ Opção inválida. Tente novamente.")


def solicitar_k(padrao: int = 10) -> int:
    """Pergunta quantos buracos consecutivos eliminam o ativo (regra 2)."""
    print("\n🧹 LIMPEZA DE DADOS")
    print("-" * 40)
    while True:
        resp = input(
            f"Quantos registros consecutivos sem dados devem eliminar o ativo? "
            f"(padrão: {padrao}): "
        ).strip()
        if resp == "":
            return padrao
        try:
            valor = int(resp)
            if valor < 1:
                print("❌ Informe um número inteiro maior que zero.")
                continue
            return valor
        except ValueError:
            print("❌ Valor inválido. Digite um número inteiro (ex.: 10).")


# --------------------------------------------------------------------------- #
#  Núcleo: download, parsing e montagem                                       #
# --------------------------------------------------------------------------- #
def resolver_tipo_preco(tipo: str):
    chave = _norm(tipo)
    if chave not in _MAPA_PRECO:
        raise ValueError(f"Tipo de preço inválido: '{tipo}'.")
    return _MAPA_PRECO[chave]


def ler_simbolos(caminho: str):
    """Lê os códigos de ativos (um por linha ou separados por , / ;)."""
    cabecalhos = {"simbolo", "simbolos", "ticker", "tickers",
                  "codigo", "codigos", "ativo", "ativos", "papel", "papeis"}
    with open(caminho, "r", encoding="utf-8-sig") as fh:
        bruto = fh.read()

    tokens = []
    for pedaco in bruto.replace(";", "\n").replace(",", "\n").splitlines():
        item = pedaco.strip().upper()
        if item and _norm(item) not in cabecalhos:
            tokens.append(item)

    vistos, ordenados = set(), []
    for t in tokens:
        if t not in vistos:
            vistos.add(t)
            ordenados.append(t)
    return ordenados


def build_url(year: int) -> str:
    return f"{BASE_URL}COTAHIST_A{year}.ZIP"


def download_zip(url: str, timeout: int = 90) -> bytes:
    resp = requests.get(url, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def parse_cotahist(raw: bytes, alvo=None, somente_vista=True) -> pd.DataFrame:
    """
    Descompacta e parseia o COTAHIST. Se `alvo` (conjunto de códigos) for
    informado, filtra as linhas ANTES de montar o DataFrame — essencial para
    não estourar a memória: cada arquivo anual tem milhões de linhas, mas só
    guardamos as poucas milhares dos ativos que você pediu.
    """
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        nome_txt = zf.namelist()[0]
        with zf.open(nome_txt) as fh:
            if alvo:
                alvo_bytes = {c.strip().upper().encode("latin-1") for c in alvo}
                vista = b"010"
                selecionadas = []
                for linha in fh:                       # itera em bytes, baixa memória
                    if linha[0:2] != b"01":            # só registros de cotação
                        continue
                    if linha[12:24].strip() not in alvo_bytes:
                        continue
                    if somente_vista and linha[24:27] != vista:
                        continue
                    selecionadas.append(linha)
                if not selecionadas:
                    return pd.DataFrame(columns=_COLNAMES)
                buffer = io.BytesIO(b"".join(selecionadas))
                df = pd.read_fwf(buffer, colspecs=_POSITIONS, names=_COLNAMES,
                                 dtype=str, encoding="latin-1")
            else:
                df = pd.read_fwf(fh, colspecs=_POSITIONS, names=_COLNAMES,
                                 dtype=str, encoding="latin-1")
                df = df[df["tipreg"] == "01"]

    df = df.copy()
    for col in _PRICE_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce") / 100.0
    df["data"] = pd.to_datetime(df["data"], format="%Y%m%d", errors="coerce")
    df["codneg"] = df["codneg"].str.strip()
    return df


def baixar_periodo(data_ini, data_fim, alvo, somente_vista=True, progress=None) -> pd.DataFrame:
    # progress(indice, total, ano): callback opcional para uma barra de progresso
    # (a interface gráfica usa; no modo console fica None e nada muda).
    frames = []
    anos = list(range(data_ini.year, data_fim.year + 1))
    for i, ano in enumerate(anos):
        if progress is not None:
            progress(i, len(anos), ano)
        print(f"  Baixando COTAHIST de {ano}... (arquivo grande, aguarde)")
        try:
            raw = download_zip(build_url(ano))
            fano = parse_cotahist(raw, alvo=alvo, somente_vista=somente_vista)
            print(f"    → {len(fano)} registros dos seus ativos em {ano}")
            frames.append(fano)
            del raw, fano                     # libera a memória do ano antes do próximo
        except requests.HTTPError as exc:
            print(f"  [aviso] não foi possível baixar {ano}: {exc}")
        time.sleep(PAUSA_ENTRE_ANOS)
    if progress is not None:
        progress(len(anos), len(anos), None)
    frames = [f for f in frames if not f.empty]
    if not frames:
        raise RuntimeError("Nenhum dado dos seus ativos foi encontrado no período.")
    return pd.concat(frames, ignore_index=True)


def montar_planilha(df, simbolos, tipo_preco, data_ini, data_fim, somente_vista=True):
    price_col, _ = resolver_tipo_preco(tipo_preco)
    ini, fim = pd.Timestamp(data_ini), pd.Timestamp(data_fim)

    mask = (df["data"] >= ini) & (df["data"] <= fim) & (df["codneg"].isin(set(simbolos)))
    if somente_vista and "tpmerc" in df.columns:
        mask &= (df["tpmerc"] == "010")

    sub = df.loc[mask, ["data", "codneg", price_col]]
    if sub.empty:
        return pd.DataFrame(columns=["Data"] + list(simbolos)), list(simbolos)

    wide = sub.pivot_table(index="data", columns="codneg",
                           values=price_col, aggfunc="last").sort_index()
    existentes = [s for s in simbolos if s in wide.columns]
    faltantes = [s for s in simbolos if s not in wide.columns]
    wide = wide[existentes].reset_index().rename(columns={"data": "Data"})
    wide.columns.name = None
    return wide, faltantes


def _maior_sequencia_true(valores) -> int:
    """Maior quantidade de True consecutivos numa sequência booleana."""
    maior = atual = 0
    for v in valores:
        atual = atual + 1 if v else 0
        if atual > maior:
            maior = atual
    return maior


def limpar_dados(wide, k: int = 10):
    """
    Aplica as três regras de limpeza sobre a matriz Data × Ativos e devolve
    (wide_limpo, relatorio). A tabela de entrada deve estar ordenada por Data.

    Passo 0 - valor 0 é tratado como "sem dado" (vira vazio).
    Regra 1 - se a coluna não tem dado na 1ª data, a coluna é excluída.
    Regra 2 - se a coluna tem MAIS de k vazios consecutivos, é excluída.
    Regra 3 - vazios restantes são preenchidos com o valor do dia anterior.

    Ordem importa: 1 e 2 olham os vazios ANTES do preenchimento; 3 vem por último.
    """
    df = wide.copy()
    tickers = [c for c in df.columns if c != "Data"]
    relatorio = {"regra1": [], "regra2": [], "mantidos": tickers, "k": k}

    if not tickers or len(df) == 0:
        return df, relatorio

    # Passo 0: garante numérico e trata 0 como ausente
    precos = df[tickers].apply(pd.to_numeric, errors="coerce")
    precos = precos.mask(precos == 0)
    ausente = precos.isna()

    # Regra 1: sem dado na primeira linha (primeira data válida)
    primeira_linha = ausente.iloc[0]
    rem1 = [t for t in tickers if bool(primeira_linha[t])]

    # Regra 2: mais de k vazios consecutivos (avaliada só nas que passaram na 1)
    rem2 = []
    for t in tickers:
        if t in rem1:
            continue
        if _maior_sequencia_true(ausente[t].tolist()) > k:
            rem2.append(t)

    remover = set(rem1) | set(rem2)
    manter = [t for t in tickers if t not in remover]

    # Regra 3: preenche vazios com o valor do dia anterior (forward fill)
    limpo = pd.concat([df[["Data"]], precos[manter]], axis=1)
    if manter:
        limpo[manter] = limpo[manter].ffill()

    relatorio = {"regra1": rem1, "regra2": rem2, "mantidos": manter, "k": k}
    return limpo, relatorio


def salvar_saidas(wide, csv_path, xlsx_path):
    wide.to_csv(csv_path, index=False, date_format="%Y-%m-%d")
    print(f"💾 CSV gravado:  {csv_path}")
    try:
        wide.to_excel(xlsx_path, index=False)
        _formatar_xlsx(xlsx_path)
        print(f"💾 XLSX gravado: {xlsx_path}")
    except ImportError:
        print("⚠️  openpyxl não instalado — só o CSV foi gerado.")
        print("    Instale com:  pip install openpyxl")


def _formatar_xlsx(xlsx_path):
    from openpyxl import load_workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    wb = load_workbook(xlsx_path)
    ws = wb.active
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.freeze_panes = "B2"
    for row in ws.iter_rows(min_row=2, min_col=1, max_col=1):
        for cell in row:
            cell.number_format = "DD/MM/YYYY"
    for row in ws.iter_rows(min_row=2, min_col=2):
        for cell in row:
            cell.number_format = "#,##0.00"
    ws.column_dimensions["A"].width = 12
    for col in range(2, ws.max_column + 1):
        ws.column_dimensions[get_column_letter(col)].width = 12
    wb.save(xlsx_path)


# --------------------------------------------------------------------------- #
#  Principal                                                                   #
# --------------------------------------------------------------------------- #
def main():
    print("=" * 60)
    print("  📈 Gerador de séries de preços da B3")
    print("=" * 60)

    # Confere se o arquivo de símbolos existe antes de tudo
    if not os.path.exists(ARQUIVO_SIMBOLOS):
        print(f"❌ Arquivo '{ARQUIVO_SIMBOLOS}' não encontrado nesta pasta.")
        print("   Crie um arquivo com um código de ativo por linha (ex.: PETR4).")
        input("\nPressione ENTER para sair...")
        return

    # 1) Perguntas interativas
    tipo_preco = solicitar_tipo_preco()
    k = solicitar_k()
    data_inicio, data_fim = solicitar_datas()
    if not data_inicio or not data_fim:
        input("\nPressione ENTER para sair...")
        return

    # 2) Ler símbolos
    simbolos = ler_simbolos(ARQUIVO_SIMBOLOS)
    if not simbolos:
        print(f"❌ Nenhum ativo em '{ARQUIVO_SIMBOLOS}'.")
        input("\nPressione ENTER para sair...")
        return
    print(f"\n✅ {len(simbolos)} ativos: {', '.join(simbolos)}")

    # 3) Baixar e montar
    print("\n🔍 Buscando dados na B3...")
    print("-" * 60)
    try:
        df = baixar_periodo(data_inicio, data_fim, set(simbolos),
                            somente_vista=SOMENTE_VISTA)
    except Exception as e:
        print(f"❌ Erro no download: {e}")
        input("\nPressione ENTER para sair...")
        return
    print("-" * 60)

    wide, faltantes = montar_planilha(
        df, simbolos, tipo_preco, data_inicio, data_fim, somente_vista=SOMENTE_VISTA
    )

    if faltantes:
        print(f"⚠️  Sem dados no período para: {', '.join(faltantes)}")
    print(f"✅ {len(wide)} datas geradas | preço: {tipo_preco}")
    print("-" * 60)

    # 4) Limpeza dos dados (as três regras)
    print(f"🧹 Limpando dados (k={k})...")
    wide, rel = limpar_dados(wide, k=k)
    if rel["regra1"]:
        print(f"   • Excluídos por falta de dado na 1ª data (regra 1): "
              f"{', '.join(rel['regra1'])}")
    if rel["regra2"]:
        print(f"   • Excluídos por mais de {k} dias consecutivos sem dado "
              f"(regra 2): {', '.join(rel['regra2'])}")
    if not rel["regra1"] and not rel["regra2"]:
        print("   • Nenhum ativo precisou ser excluído.")
    print(f"   • Lacunas restantes preenchidas com o dia anterior (regra 3).")
    print(f"   • Ativos finais na planilha: {len(rel['mantidos'])}")

    if not rel["mantidos"]:
        print("❌ Após a limpeza não sobrou nenhum ativo. Nada a salvar.")
        input("\nPressione ENTER para sair...")
        return
    print("-" * 60)

    # 5) Salvar
    salvar_saidas(wide, SAIDA_CSV, SAIDA_XLSX)

    print("=" * 60)
    print("  🎉 Concluído!")
    print("=" * 60)
    input("\nPressione ENTER para sair...")


if __name__ == "__main__":
    main()
