"""
b3_excel_rendafixa.py
=====================
Busca séries de preços via Excel (função STOCKHISTORY / HISTÓRICODEAÇÕES),
para os ativos que o COTAHIST da B3 não cobre bem — tipicamente ETFs de
renda fixa (FIXA11, IMAB11, B5P211, DEBB11, ...).

A fonte por trás da STOCKHISTORY é a LSEG (Refinitiv), diferente da B3.
Serve como fonte COMPLEMENTAR: use a B3 como primária e o Excel só para
os códigos que faltarem. Não misture as duas fontes na mesma coluna.

Requisitos (rodar no Windows):
    - Microsoft 365 (assinatura) com Excel instalado e logado.
    - pip install xlwings pandas

Observações técnicas importantes (tratadas neste módulo):
    - A fórmula é escrita pelo NOME EM INGLÊS ("STOCKHISTORY") com vírgulas,
      mesmo no Excel em português. O Excel exibe como HISTÓRICODEAÇÕES.
    - As datas vão como DATE(ano,mês,dia) para não depender do formato local.
    - A STOCKHISTORY calcula de forma ASSÍNCRONA; usamos
      CalculateUntilAsyncQueriesDone() + espera ativa até os dados chegarem.
    - O código do ticker é prefixado pela bolsa (padrão "BVMF"; alternativa
      "XBSP"), pois a função exige o identificador do mercado.
"""

import os
import sys
import time
from datetime import datetime

import pandas as pd

# Evita erro de emoji/acentos no console do Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Propriedade da STOCKHISTORY para cada tipo de preço:
#   0=Data, 1=Fechamento, 2=Abertura, 3=Máximo, 4=Mínimo, 5=Volume
_PROP_PRECO = {
    "abertura":   2,
    "maximo":     3,
    "minimo":     4,
    "fechamento": 1,
}

# Formas de identificar o ativo, tentadas nesta ordem.
# "" = ticker puro (ex.: "FIXA11") — foi o que funcionou no teste manual.
# Os prefixos de bolsa entram só como reserva, caso o puro não resolva.
_PREFIXOS_B3 = ["", "BVMF", "XBSP"]


def _norm(txt: str) -> str:
    import unicodedata
    txt = unicodedata.normalize("NFKD", str(txt))
    return txt.encode("ascii", "ignore").decode("ascii").strip().lower()


def _codigo_preco(tipo_preco: str) -> int:
    chave = _norm(tipo_preco)
    if chave not in _PROP_PRECO:
        raise ValueError(f"Tipo de preço inválido: '{tipo_preco}'.")
    return _PROP_PRECO[chave]


def _formula(simbolo_completo: str, d1: datetime, d2: datetime, code: int) -> str:
    """
    Monta a fórmula STOCKHISTORY em inglês (locale-proof):
      intervalo 0 = diário | cabeçalho 0 = sem cabeçalho
      propriedades: 0 (Data) e `code` (o preço escolhido)
    """
    return (
        f'=STOCKHISTORY("{simbolo_completo}",'
        f'DATE({d1.year},{d1.month},{d1.day}),'
        f'DATE({d2.year},{d2.month},{d2.day}),'
        f'0,0,0,{code})'
    )


def _valor_pronto(v) -> bool:
    """True se a célula A1 já trouxe uma data (cálculo concluído com sucesso)."""
    return isinstance(v, datetime)


# Faixa dos códigos de erro do Excel (CVErr) que o COM devolve como números
# gigantes e negativos. Ex.: #N/D = -2146826246, #VALOR! = -2146826273,
# #REF! = -2146826265, #NOME? = -2146826259, #NÚM! = -2146826252, etc.
# Todos caem nesta faixa — tratamos qualquer um deles como "sem dado".
_EXCEL_ERR_MIN, _EXCEL_ERR_MAX = -2146827000, -2146826000


def _preco_valido(v):
    """
    Converte o valor de preço vindo do Excel. Devolve NaN quando a célula é
    um erro (#N/D, #VALOR!, ...), que o COM entrega como um código numérico
    gigante negativo — senão esse código entraria na série como se fosse preço.
    """
    try:
        x = float(v)
    except (TypeError, ValueError):
        return float("nan")
    if _EXCEL_ERR_MIN <= x <= _EXCEL_ERR_MAX:      # é um código de erro do Excel
        return float("nan")
    return x


# Código de "ainda carregando" (não é falha — é pra continuar esperando).
_EXCEL_ERR_GETTING_DATA = -2146826234   # #GETTING_DATA / #OCUPADO

# Só desistimos de um ativo se um ERRO PERSISTIR por este tempo (segundos).
# Erros que somem antes disso são transitórios (a STOCKHISTORY exibe vários
# enquanto ainda está carregando) e NÃO devem provocar desistência.
_GRACE_ERRO = 5.0


def _estado_celula(v) -> str:
    """
    Classifica a célula-âncora A1 em um de três estados:
      'ok'         -> já virou uma data: a STOCKHISTORY retornou a série.
      'carregando' -> vazia ou ainda buscando dados (#GETTING_DATA): esperar.
      'erro'       -> erro do Excel (#VALOR!, #N/D, #NOME?, ...). Atenção: pode
                      ser TRANSITÓRIO durante o carregamento — por isso só conta
                      como falha se persistir (ver _aguardar_resultado).

    O erro pode chegar de duas formas conforme a via de leitura:
      - como CÓDIGO NUMÉRICO negativo (via COM cru .api.Value), ou
      - como TEXTO "#VALOR!"/"#N/D" (via xlwings .value).
    Reconhecemos as duas.
    """
    if isinstance(v, datetime):
        return "ok"

    # Erro (ou status) vindo como TEXTO: "#VALOR!", "#N/D", "#GETTING_DATA"...
    if isinstance(v, str):
        s = v.strip().upper()
        if not s:
            return "carregando"
        if "GETTING" in s or "OCUPADO" in s or "BUSY" in s:
            return "carregando"             # ainda carregando
        if s.startswith("#"):
            return "erro"                   # #VALOR!, #N/D, #NOME?, #REF! ...
        return "carregando"

    # Erro vindo como CÓDIGO NUMÉRICO (CVErr do COM)
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "carregando"                 # None/vazio
    if x == _EXCEL_ERR_GETTING_DATA:
        return "carregando"                 # ainda chegando da LSEG
    if _EXCEL_ERR_MIN <= x <= _EXCEL_ERR_MAX:
        return "erro"                       # erro do Excel (pode ser transitório)
    return "carregando"


def _aguardar_resultado(ler_valor, timeout, grace_erro=_GRACE_ERRO, passo=0.5):
    """
    Espera o resultado da STOCKHISTORY. Retorna:
      'ok'      -> A1 virou data (sucesso). Detecção IDÊNTICA à versão que
                   funcionava: basta a célula virar uma data.
      'erro'    -> um erro PERSISTIU por `grace_erro` segundos seguidos (ativo
                   realmente sem dados) -> desiste rápido, sem esperar o timeout.
      'timeout' -> estourou o tempo sem virar data.

    `ler_valor` é uma função sem argumentos que devolve o valor atual de A1.
    Erros transitórios (que aparecem e somem antes de `grace_erro`) são
    ignorados — eles surgem enquanto a função ainda está carregando.
    """
    inicio = time.time()
    erro_desde = None
    while time.time() - inicio < timeout:
        st = _estado_celula(ler_valor())
        if st == "ok":
            return "ok"
        if st == "erro":
            if erro_desde is None:
                erro_desde = time.time()            # começou um erro; cronometra
            elif time.time() - erro_desde >= grace_erro:
                return "erro"                        # erro persistente = falhou
        else:
            erro_desde = None                        # voltou a carregar: zera
        time.sleep(passo)
    return "timeout"


def _to_naive_datetime(v):
    """
    Converte a data vinda do Excel/COM (um pywintypes.datetime COM FUSO) em
    um datetime 'ingênuo' (sem timezone). O fuso do COM é malformado e faz o
    pandas quebrar ao montar a coluna de datas. Para série diária, só o dia
    importa, então descartamos hora/fuso com segurança.
    """
    if isinstance(v, datetime):
        return datetime(v.year, v.month, v.day)
    return v  # float serial, string etc. -> deixa o pandas tentar


def _linhas(vals):
    """Normaliza o retorno do COM em lista-de-linhas (cada linha uma lista)."""
    if vals is None:
        return []
    if not isinstance(vals, (list, tuple)):      # célula única (escalar)
        return [[vals]]
    if len(vals) == 0:
        return []
    if not isinstance(vals[0], (list, tuple)):   # uma única linha
        return [list(vals)]
    return [list(r) for r in vals]               # matriz (várias linhas)


def _ler_spill(sht, timeout):
    """
    Lê a matriz derramada (spill) da STOCKHISTORY de forma robusta.
    Usa a referência do spill (SpillingToRange, o 'A1#' do Excel) e espera
    até a matriz vir completa com as 2 colunas (Data, Preço), pois ela se
    preenche de forma assíncrona.
    """
    inicio = time.time()
    while time.time() - inicio < timeout:
        try:
            vals = sht["A1"].api.SpillingToRange.Value   # matriz inteira do spill
        except Exception:
            vals = sht["A1"].expand().value              # alternativa
        linhas = _linhas(vals)
        if linhas and len(linhas[0]) >= 2:               # já tem Data + Preço
            return linhas
        time.sleep(0.4)
    return []


def _set_formula_dinamica(cell, formula: str) -> None:
    """
    Grava a fórmula como ARRAY DINÂMICO usando a propriedade moderna Formula2.
    Isso evita o '@' (operador de interseção implícita) que o Excel insere
    quando se usa a propriedade antiga .Formula — e que impede o spill.
    """
    try:
        cell.api.Formula2 = formula        # moderno: deixa a STOCKHISTORY derramar
    except Exception:
        cell.formula = formula             # reserva para Excel muito antigo


def _buscar_um(sht, app, simbolo: str, d1, d2, code: int,
               prefixos, timeout: float):
    """
    Tenta buscar um ticker, testando os prefixos de bolsa em ordem.
    Retorna DataFrame [Data, <simbolo>] ou None se falhar em todos.
    """
    for prefixo in prefixos:
        simbolo_completo = simbolo if not prefixo else f"{prefixo}:{simbolo}"
        sht.clear()
        _set_formula_dinamica(sht["A1"], _formula(simbolo_completo, d1, d2, code))

        # força o Excel a terminar as consultas assíncronas da STOCKHISTORY
        try:
            app.api.CalculateUntilAsyncQueriesDone()
        except Exception:
            app.calculate()

        # Lê A1 pelo COM CRU (.api.Value): aqui o erro chega como código
        # numérico (ex.: #VALOR! = -2146826273), que o _estado_celula detecta.
        # Pela via .value do xlwings o erro vinha como texto/None e era
        # confundido com "carregando" — por isso o sistema esperava ~90s à toa.
        estado = _aguardar_resultado(lambda: sht["A1"].api.Value, timeout)
        if estado == "erro":
            return None      # erro persistente (>5s) -> esquece o ativo já, sem
                             # tentar os outros prefixos, e parte para o próximo
        if estado == "timeout":
            continue         # só ficou carregando -> tenta o próximo prefixo
        # estado == "ok": a série chegou; segue para ler a matriz

        # espera a matriz derramada vir completa (Data + Preço)
        linhas = _ler_spill(sht, timeout)
        if not linhas or len(linhas[0]) < 2:
            continue

        # Limpa o fuso das DATAS enquanto ainda são objetos Python crus (a lista
        # `linhas`), ANTES de montar o DataFrame. Se deixarmos o pandas construir
        # a coluna a partir dos datetimes com fuso quebrado do COM, ele quebra até
        # mesmo ao só percorrer a coluna. Aqui iteramos uma lista comum, sem risco.
        datas = [_to_naive_datetime(r[0]) for r in linhas]
        precos = [_preco_valido(r[1]) for r in linhas]

        df = pd.DataFrame({"Data": datas, simbolo: precos})
        df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
        df[simbolo] = pd.to_numeric(df[simbolo], errors="coerce")
        df = df.dropna(subset=["Data"]).reset_index(drop=True)
        if not df.empty:
            return df
    return None


def fetch_excel_wide(tickers, data_ini, data_fim, tipo_preco,
                     prefixos=None, timeout=30.0, visivel=False):
    """
    Retorna (wide_df, falhas):
      wide_df: DataFrame [Data, TICKER1, TICKER2, ...] no formato da B3.
      falhas : lista de tickers que o Excel não conseguiu trazer.

    Requer Excel 365 instalado. Abre o Excel via xlwings, escreve uma
    STOCKHISTORY por ticker, lê o resultado e junta tudo pela Data.
    """
    try:
        import xlwings as xw
    except ImportError as e:
        raise ImportError(
            "xlwings não instalado. Rode:  pip install xlwings\n"
            "(e é preciso ter o Excel 365 instalado e logado)."
        ) from e

    code = _codigo_preco(tipo_preco)
    d1, d2 = pd.Timestamp(data_ini).to_pydatetime(), pd.Timestamp(data_fim).to_pydatetime()
    prefixos = prefixos or _PREFIXOS_B3

    resultado = None
    falhas = []

    app = xw.App(visible=visivel, add_book=False)
    try:
        wb = app.books.add()
        sht = wb.sheets[0]
        for tk in tickers:
            print(f"  Excel → buscando {tk}...")
            parcial = _buscar_um(sht, app, tk, d1, d2, code, prefixos, timeout)
            if parcial is None:
                print(f"    [falhou] {tk} não retornou dados no Excel")
                falhas.append(tk)
                continue
            resultado = parcial if resultado is None else \
                resultado.merge(parcial, on="Data", how="outer")
    finally:
        wb.close()
        app.quit()

    if resultado is None:
        return pd.DataFrame(columns=["Data"] + list(tickers)), falhas

    resultado = resultado.sort_values("Data").reset_index(drop=True)
    # reordena as colunas na ordem pedida (só as que vieram)
    cols = ["Data"] + [t for t in tickers if t in resultado.columns]
    return resultado[cols], falhas


# =========================================================================== #
#  Programa standalone: interativo + limpeza + gravação (gêmeo do da B3)       #
# =========================================================================== #
ARQUIVO_SIMBOLOS = "SimbolosRF.csv"        # códigos dos ETFs de renda fixa
SAIDA_CSV        = "series_precos_rf.csv"
SAIDA_XLSX       = "series_precos_rf.xlsx"


def validar_data(data_string: str) -> datetime:
    """Aceita DD/MM/AAAA, DD-MM-AAAA, AAAA-MM-DD (e variações de 2 dígitos)."""
    for formato in ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y"]:
        try:
            return datetime.strptime(data_string, formato)
        except ValueError:
            continue
    raise ValueError(f"Formato de data inválido: {data_string}")


def solicitar_datas():
    print("\n📅 PERÍODO")
    print("-" * 40)
    print("Formatos aceitos: DD/MM/AAAA, DD-MM-AAAA, AAAA-MM-DD")
    while True:
        try:
            ini_str = input("\n📅 Data de INÍCIO (ex: 02/01/2023): ").strip()
            if not ini_str:
                print("❌ A data de início é obrigatória!")
                continue
            data_inicio = validar_data(ini_str)
            fim_str = input("📅 Data FINAL (ex: 31/12/2024) ou ENTER para hoje: ").strip()
            if not fim_str:
                data_fim = datetime.now()
                print(f"   → Usando hoje: {data_fim.strftime('%d/%m/%Y')}")
            else:
                data_fim = validar_data(fim_str)
            if data_inicio > data_fim:
                print("❌ A data de início deve ser anterior (ou igual) à final!")
                continue
            print(f"\n✅ Período: {data_inicio.strftime('%d/%m/%Y')} a "
                  f"{data_fim.strftime('%d/%m/%Y')}")
            return data_inicio, data_fim
        except ValueError as e:
            print(f"❌ {e}. Tente novamente.")
        except KeyboardInterrupt:
            print("\n\n👋 Operação cancelada.")
            return None, None


def solicitar_tipo_preco() -> str:
    opcoes = {"1": "Abertura", "2": "Máximo", "3": "Mínimo", "4": "Fechamento"}
    print("\n💰 TIPO DE PREÇO")
    print("-" * 40)
    for k_, v in opcoes.items():
        print(f"   {k_}. {v}")
    while True:
        escolha = input("\nDigite o número (padrão: 4 - Fechamento): ").strip()
        if escolha == "":
            return "Fechamento"
        if escolha in opcoes:
            return opcoes[escolha]
        print("❌ Opção inválida. Tente novamente.")


def solicitar_k(padrao: int = 10) -> int:
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


def ler_simbolos(caminho: str):
    """Lê os códigos de ativos (um por linha ou separados por , / ;)."""
    cabecalhos = {"simbolo", "simbolos", "ticker", "tickers", "codigo",
                  "codigos", "ativo", "ativos", "papel", "papeis"}
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


def _maior_sequencia_true(valores) -> int:
    maior = atual = 0
    for v in valores:
        atual = atual + 1 if v else 0
        if atual > maior:
            maior = atual
    return maior


def limpar_dados(wide, k: int = 10):
    """
    Mesmas três regras do módulo da B3:
      0 - valor 0 conta como "sem dado".
      1 - sem dado na 1ª data -> exclui a coluna.
      2 - mais de k vazios consecutivos -> exclui a coluna.
      3 - vazios restantes preenchidos com o valor do dia anterior.
    """
    df = wide.copy()
    tickers = [c for c in df.columns if c != "Data"]
    if not tickers or len(df) == 0:
        return df, {"regra1": [], "regra2": [], "mantidos": tickers, "k": k}

    precos = df[tickers].apply(pd.to_numeric, errors="coerce").mask(
        lambda x: x == 0)
    ausente = precos.isna()

    primeira = ausente.iloc[0]
    rem1 = [t for t in tickers if bool(primeira[t])]
    rem2 = [t for t in tickers if t not in rem1
            and _maior_sequencia_true(ausente[t].tolist()) > k]

    remover = set(rem1) | set(rem2)
    manter = [t for t in tickers if t not in remover]

    limpo = pd.concat([df[["Data"]], precos[manter]], axis=1)
    if manter:
        limpo[manter] = limpo[manter].ffill()
    return limpo, {"regra1": rem1, "regra2": rem2, "mantidos": manter, "k": k}


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


def main():
    print("=" * 60)
    print("  📊 Séries de preços via Excel (renda fixa)")
    print("=" * 60)

    if not os.path.exists(ARQUIVO_SIMBOLOS):
        print(f"❌ Arquivo '{ARQUIVO_SIMBOLOS}' não encontrado nesta pasta.")
        print("   Crie um arquivo com um código por linha (ex.: FIXA11).")
        input("\nPressione ENTER para sair...")
        return

    # 1) Perguntas interativas (mesma ordem do programa da B3)
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

    # 3) Buscar no Excel
    print("\n🔍 Buscando dados no Excel (STOCKHISTORY)...")
    print("-" * 60)
    # IMPORTANTE: a STOCKHISTORY só popula com o Excel VISÍVEL/ativo — com ele
    # escondido, o serviço de dados não responde e todos os ativos falham.
    try:
        wide, falhas = fetch_excel_wide(
            simbolos, data_inicio, data_fim, tipo_preco, visivel=False
        )
    except Exception as e:
        print(f"❌ Erro ao consultar o Excel: {e}")
        input("\nPressione ENTER para sair...")
        return
    print("-" * 60)
    if falhas:
        print(f"⚠️  O Excel não retornou dados para: {', '.join(falhas)}")
    print(f"✅ {len(wide)} datas obtidas | preço: {tipo_preco}")
    print("-" * 60)

    # 4) Limpeza (as três regras)
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
    print("   • Lacunas restantes preenchidas com o dia anterior (regra 3).")
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
