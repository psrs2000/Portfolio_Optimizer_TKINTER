"""
eventos_corporativos.py — ajuste OPCIONAL das cotações da B3 por eventos
corporativos: desdobramentos, grupamentos, bonificações e proventos
(dividendos, JCP, rendimentos de FII, amortizações).

O arquivo COTAHIST da B3 traz os preços como foram negociados. Num
desdobramento de 1 para 4 o preço cai a um quarto de um dia para o outro; num
dividendo o preço cai o valor pago. Para o otimizador, os dois parecem perdas
— e não são. Este módulo recalcula os preços ANTERIORES a cada evento, para
que a série conte a história de quem ficou com o papel o tempo todo.

Este módulo não altera nada sozinho: só age quando a importação da B3 é feita
com a opção de ajuste marcada. Desmarcada, a importação é exatamente a de
sempre.

DE ONDE VÊM OS EVENTOS
----------------------
1. B3, "dados complementares" da empresa: desdobramentos, grupamentos e
   bonificações desde os anos 90, e os proventos dos últimos ~12 meses.
2. B3, histórico de proventos em dinheiro da empresa: todos os dividendos e
   JCP desde 1996, já com o percentual sobre o preço da data-com.
3. O próprio COTAHIST: a B3 às vezes deixa um desdobramento fora da lista (os
   da Magazine Luiza em 2017 e 2019, por exemplo). O arquivo os denuncia: no
   dia "ex" o número de distribuição muda, o preço cai x vezes e a quantidade
   negociada sobe x vezes. Só se aplica o que tiver as três marcas juntas.
4. FIIs: a B3 só guarda os rendimentos dos últimos ~12 meses. Os anteriores
   vêm do Fundos.NET (o sistema da B3 em que os próprios fundos publicam os
   avisos de rendimento), pelo CNPJ do fundo — ver tabela_fii_cnpj.py.

COMO O AJUSTE É FEITO
---------------------
Para cada evento com data-com D, todos os preços com data <= D são
multiplicados por um fator; os preços depois de D não mudam. Assim, o último
preço da série continua sendo o preço real de hoje.

- desdobramento/bonificação/grupamento: fator = 1 / (ações depois / antes)
- provento em dinheiro: fator = 1 − provento / preço de fechamento na data-com

O cache (pequenos arquivos .json) evita baixar de novo o que já foi baixado.
"""

import base64
import csv
import json
import math
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import pandas as pd
import requests

try:
    from tabela_fii_cnpj import TABELA as TABELA_FII_PRONTA
except Exception:                      # tabela ausente: FIIs ficam só com a B3
    TABELA_FII_PRONTA = {}


# =========================================================================== #
#  Endereços e parâmetros                                                      #
# =========================================================================== #
B3_BASE = "https://sistemaswebb3-listados.b3.com.br"
URL_COMPLEMENTO_EMPRESA = B3_BASE + "/listedCompaniesProxy/CompanyCall/GetListedSupplementCompany/"
URL_COMPLEMENTO_FUNDO = B3_BASE + "/fundsProxy/fundsCall/GetListedSupplementFunds/"
URL_PROVENTOS = B3_BASE + "/listedCompaniesProxy/CompanyCall/GetListedCashDividends/"
FNET_BASE = "https://fnet.bmfbovespa.com.br/fnet/publico/"

CABECALHOS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
}

PAUSA = 0.25                   # segundos entre pedidos (cortesia com o servidor)
TENTATIVAS = 3
TAMANHOS_PAGINA = (120, 60, 20)  # a B3 recusa em silêncio páginas grandes demais

# Classe da ação pelo número do código de negociação
CLASSES = {"3": "ON", "4": "PN", "5": "PNA", "6": "PNB", "7": "PNC",
           "8": "PND", "11": "UNT"}

# Detector de desdobramentos no COTAHIST: razões inteiras de 2 a 1000. Bonificações
# pequenas (ex.: 5%) não se distinguem de um pregão comum pelo preço; para essas
# a lista da B3 é a única fonte.
RAZOES_DETECTAVEIS = (2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 16, 20, 25, 30, 40, 50,
                      60, 80, 100, 200, 250, 500, 1000)
SALTO_MINIMO = 0.6             # abertura/fechamento anterior abaixo disto (ou
SALTO_MAXIMO = 1.0 / 0.6       # acima disto) num dia de evento: suspeita de desdobramento
TOLERANCIA_RAZAO = 0.12        # |ln(salto × razão)| aceitável
TOLERANCIA_QUANTIDADE = math.log(3.0)

# Depois do ajuste: variação diária acima disto vira aviso no relatório
VARIACAO_SUSPEITA = 0.45

# Conferência dos proventos da B3: o fechamento informado por ela na data-com
# deve bater com o do COTAHIST. Se não bater, a linha é de outro papel.
TOLERANCIA_PRECO = 0.02


class FonteIndisponivel(Exception):
    """A fonte não respondeu (rede, bloqueio, servidor fora do ar)."""


# =========================================================================== #
#  Pequenas utilidades                                                         #
# =========================================================================== #
def _num(texto):
    """Número da B3/Fundos.NET para float. '7.900,00' -> 7900.0; '1.17' -> 1.17."""
    if texto is None:
        return None
    s = str(texto).strip()
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _data(texto):
    """'dd/mm/aaaa' ou 'aaaa-mm-dd' para Timestamp. Datas absurdas viram None."""
    if not texto:
        return None
    s = str(texto).strip()[:10]
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(s, fmt)
        except ValueError:
            continue
        if 1900 <= d.year <= 2100:
            return pd.Timestamp(d)
        return None
    return None


def _b64(parametros):
    """A B3 recebe os parâmetros como JSON compacto em base64 no endereço."""
    texto = json.dumps(parametros, separators=(",", ":"))
    return base64.b64encode(texto.encode("utf-8")).decode("ascii")


def _fmt(d):
    return pd.Timestamp(d).strftime("%d/%m/%Y")


def _fmt_num(x, casas=4):
    """Número em português, sem zeros inúteis: 0.25 -> '0,25'; 4.0 -> '4'."""
    txt = f"{x:.{casas}f}".rstrip("0").rstrip(".")
    return txt.replace(".", ",")


def empresa_e_classe(ticker):
    """'PETR4' -> ('PETR', 'PN'); 'TAEE11' -> ('TAEE', 'UNT'); 'HGLG11' -> ('HGLG', 'UNT')."""
    m = re.fullmatch(r"([A-Z0-9]{4})(\d{1,2})[A-Z]?", ticker.strip().upper())
    if not m:
        return None, None
    return m.group(1), CLASSES.get(m.group(2))


# =========================================================================== #
#  Tabela código de FII -> CNPJ                                                #
# =========================================================================== #
def carregar_tabela_fii(caminho_extra=None):
    """
    Tabela pronta (tabela_fii_cnpj.py) + acréscimos do usuário num CSV
    opcional com as colunas  codigo;cnpj  (um fundo por linha). O CSV extra
    tem prioridade: serve para incluir um fundo novo sem esperar uma versão
    nova do programa.
    """
    tabela = {cod: dados[0] for cod, dados in TABELA_FII_PRONTA.items()}
    if caminho_extra and os.path.exists(caminho_extra):
        try:
            with open(caminho_extra, encoding="utf-8-sig") as fh:
                amostra = fh.read(2048)
                fh.seek(0)
                sep = ";" if amostra.count(";") >= amostra.count(",") else ","
                for linha in csv.reader(fh, delimiter=sep):
                    if len(linha) < 2:
                        continue
                    cod = linha[0].strip().upper()
                    cnpj = re.sub(r"\D", "", linha[1])
                    if re.fullmatch(r"[A-Z0-9]{4}\d{2}", cod) and len(cnpj) == 14:
                        tabela[cod] = cnpj
        except Exception as e:
            print(f"  [aviso] não foi possível ler {caminho_extra}: {e}")
    return tabela


# =========================================================================== #
#  Acesso às fontes (B3 e Fundos.NET)                                          #
# =========================================================================== #
class Rede:
    """Pedidos HTTP às fontes, com novas tentativas e pausa entre pedidos."""

    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update(CABECALHOS)
        self._fnet_aberto = False

    def _get(self, url, **kw):
        ultimo = "sem resposta"
        for tentativa in range(TENTATIVAS):
            try:
                r = self.s.get(url, timeout=40, **kw)
                if r.status_code == 200:
                    time.sleep(PAUSA)
                    return r
                ultimo = f"HTTP {r.status_code}"
            except requests.RequestException as e:
                ultimo = f"{type(e).__name__}: {e}"
            time.sleep(1.5 * (tentativa + 1))
        raise FonteIndisponivel(ultimo)

    def _json(self, url, **kw):
        r = self._get(url, **kw)
        try:
            return r.json()
        except ValueError:
            raise FonteIndisponivel("a resposta não veio em JSON")

    # ---- B3 ----
    def complemento(self, empresa):
        """
        Dados complementares da B3: {'tradingName', 'stockDividends',
        'cashDividends'}, ou None se a B3 não conhece o código.
        Tenta o cadastro de empresas e, se vier vazio, o de fundos.
        """
        dados = self._json(URL_COMPLEMENTO_EMPRESA + _b64(
            {"issuingCompany": empresa, "language": "pt-br"}))
        item = dados[0] if isinstance(dados, list) and dados else dados
        if isinstance(item, dict) and (item.get("stockDividends") or item.get("cashDividends")
                                       or item.get("tradingName")):
            return {"tradingName": (item.get("tradingName") or "").strip(),
                    "stockDividends": item.get("stockDividends") or [],
                    "cashDividends": item.get("cashDividends") or []}
        try:
            dados = self._json(URL_COMPLEMENTO_FUNDO + _b64(
                {"cnpj": "0", "identifierFund": empresa, "typeFund": 7}))
        except FonteIndisponivel:
            return None
        item = dados[0] if isinstance(dados, list) and dados else dados
        if isinstance(item, dict) and (item.get("stockDividends") or item.get("cashDividends")):
            return {"tradingName": (item.get("fund") or "").strip(),
                    "stockDividends": item.get("stockDividends") or [],
                    "cashDividends": item.get("cashDividends") or []}
        return None

    def proventos(self, nome_pregao):
        """Histórico completo de proventos em dinheiro de uma empresa."""
        # Como a própria página da B3 faz: sem barra e sem espaços sobrando
        # (com a barra, 'KLABIN S/A' devolve zero resultados).
        nome = re.sub(r"\s+", " ", nome_pregao.replace("/", "")).strip()
        if not nome:
            return []
        linhas = []
        for tamanho in TAMANHOS_PAGINA:
            linhas, total, pagina = [], None, 1
            while pagina <= 100:
                d = self._json(URL_PROVENTOS + _b64(
                    {"language": "pt-br", "pageNumber": pagina,
                     "pageSize": tamanho, "tradingName": nome}))
                pag = d.get("page") if isinstance(d, dict) else None
                total = (pag or {}).get("totalRecords", total)
                resultado = (d.get("results") if isinstance(d, dict) else None) or []
                if not resultado:
                    break
                linhas.extend(resultado)
                if total is not None and len(linhas) >= int(total):
                    break
                pagina += 1
            if not total or len(linhas) >= int(total):
                return linhas
            # Veio menos do que o total anunciado: página grande demais.
        return linhas

    # ---- Fundos.NET ----
    def _abrir_fnet(self):
        if self._fnet_aberto:
            return
        r = self._get(FNET_BASE + "abrirGerenciadorDocumentosCVM")
        m = (re.search(r'<meta[^>]+name="_csrf"[^>]+content="([^"]+)"', r.text)
             or re.search(r'content="([^"]+)"[^>]+name="_csrf"', r.text))
        if m:
            self.s.headers["CSRFToken"] = m.group(1)
        self._fnet_aberto = True

    def fnet_documentos(self, cnpj, d_ini, d_fim):
        """Avisos de 'Rendimentos e Amortizações' do fundo entregues no período."""
        self._abrir_fnet()
        docs, inicio, total, contador = [], 0, None, 0
        while True:
            contador += 1
            params = {"d": str(contador), "s": str(inicio), "l": "100",
                      "o[0][dataEntrega]": "desc", "tipoFundo": "1",
                      "idCategoriaDocumento": "14", "idTipoDocumento": "41",
                      "idEspecieDocumento": "0", "cnpj": cnpj, "cnpjFundo": cnpj,
                      "dataInicial": _fmt(d_ini), "dataFinal": _fmt(d_fim),
                      "_": str(int(time.time() * 1000))}
            d = self._json(FNET_BASE + "pesquisarGerenciadorDocumentosDados",
                           params=params, headers={"X-Requested-With": "XMLHttpRequest"})
            pagina = (d.get("data") if isinstance(d, dict) else None) or []
            if total is None and isinstance(d, dict):
                total = d.get("recordsTotal")
            if not pagina:
                break
            docs.extend(pagina)
            inicio += len(pagina)
            if total is not None and inicio >= int(total):
                break
            if inicio > 2000:
                break
        return docs

    def fnet_xml(self, id_doc):
        r = self._get(FNET_BASE + f"downloadDocumento?id={id_doc}",
                      headers={"Accept": "application/xhtml+xml"})
        conteudo = r.content
        if not conteudo.lstrip().startswith(b"<"):
            try:
                conteudo = base64.b64decode(conteudo)
            except Exception:
                pass
        return conteudo


def ler_xml_rendimentos(conteudo):
    """
    Lê um aviso estruturado de Rendimentos e Amortizações do Fundos.NET.
    Devolve [{'codigo', 'isin', 'data_com', 'valor', 'tipo'}].

    Há dois formatos:
    - antigo (até 2022): o código da cota vem nos dados gerais
      (CodNegociacaoCota) e cada <Rendimento>/<Amortizacao> traz
      ValorProventoCota;
    - novo: cada <Provento> traz CodISIN e CodNegociacao, e dentro dele o
      <Rendimento>/<Amortizacao> com ValorProvento. Um mesmo aviso pode ter a
      cota e recibos de subscrição (HGLG11, HGLG13...): o filtro pelo código
      fica a cargo de quem chama.
    """
    raiz = ET.fromstring(conteudo)
    nome = lambda el: el.tag.split("}")[-1]
    filhos = lambda el: {nome(c): (c.text or "").strip() for c in el}

    padrao = ("", "")
    for el in raiz.iter():
        if nome(el) == "DadosGerais":
            g = filhos(el)
            padrao = (g.get("CodNegociacaoCota", ""), g.get("CodISINCota", ""))
            break

    saida = []

    def visitar(el, cod, isin):
        n = nome(el)
        if n == "Provento":
            g = filhos(el)
            cod = g.get("CodNegociacao") or cod
            isin = g.get("CodISIN") or isin
        if n in ("Rendimento", "Amortizacao"):
            g = filhos(el)
            valor = None
            for chave in ("ValorProvento", "ValorProventoCota"):
                valor = _num(g.get(chave))
                if valor:
                    break
            if not valor:
                for chave, texto in g.items():
                    if chave.startswith("Valor") and _num(texto):
                        valor = _num(texto)
                        break
            data_com = _data(g.get("DataBase"))
            if valor and valor > 0 and data_com is not None:
                saida.append({"codigo": cod.strip().upper(), "isin": isin.strip().upper(),
                              "data_com": data_com.strftime("%Y-%m-%d"),
                              "valor": valor, "tipo": n.upper()})
            return
        for c in el:
            visitar(c, cod, isin)

    visitar(raiz, *padrao)
    return saida


# =========================================================================== #
#  Cache                                                                       #
# =========================================================================== #
class Cache:
    """Arquivos .json pequenos, um por empresa (B3) e um por fundo (Fundos.NET)."""

    def __init__(self, pasta):
        self.pasta = pasta
        if pasta:
            try:
                os.makedirs(pasta, exist_ok=True)
            except OSError:
                self.pasta = None

    def _caminho(self, nome):
        return os.path.join(self.pasta, re.sub(r"[^A-Za-z0-9_.-]", "_", nome) + ".json")

    def ler(self, nome):
        if not self.pasta:
            return None
        try:
            with open(self._caminho(nome), encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None

    def gravar(self, nome, dados):
        if not self.pasta:
            return
        try:
            tmp = self._caminho(nome) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(dados, fh, ensure_ascii=False)
            os.replace(tmp, self._caminho(nome))
        except OSError:
            pass


def _cache_serve(baixado_em, ultima_data):
    """
    O cache vale se foi baixado HOJE, ou num dia POSTERIOR ao último pregão da
    série: nesse caso todo evento com data-com dentro da série já tinha sido
    anunciado quando o cache foi feito.
    """
    try:
        dia = datetime.fromisoformat(baixado_em).date()
    except (TypeError, ValueError):
        return False
    return dia >= datetime.now().date() or dia > pd.Timestamp(ultima_data).date()


# =========================================================================== #
#  Leitura do COTAHIST de cada papel                                           #
# =========================================================================== #
def _cotahist_do_papel(bruto, ticker):
    """
    Linhas do COTAHIST do papel, uma por pregão, com os preços POR AÇÃO.

    Até 2005 algumas ações eram cotadas por lote de mil (campo FATCOT = 1000).
    Dividir pelo FATCOT põe tudo em preço por ação — e tem de ser feito junto
    com os grupamentos daquela época: o Banco do Brasil agrupou 1000 para 1 em
    2004 ao mesmo tempo em que passou a ser cotado por ação, e o preço exibido
    quase não mudou. Aplicando só um dos dois, a série erraria por mil vezes.
    """
    if bruto is None or "codneg" not in bruto.columns:
        return None
    sub = bruto.loc[bruto["codneg"].astype(str).str.strip() == ticker].copy()
    if sub.empty:
        return None
    sub["data"] = pd.to_datetime(sub["data"])
    for col in ("preabe", "preult"):
        sub[col] = pd.to_numeric(sub[col], errors="coerce")
    for col in ("quatot", "fatcot"):
        if col in sub.columns:
            sub[col] = pd.to_numeric(sub[col], errors="coerce")
        else:
            sub[col] = 1.0 if col == "fatcot" else float("nan")
    sub["fatcot"] = sub["fatcot"].fillna(1).clip(lower=1)
    sub["dismes"] = sub["dismes"].astype(str).str.strip() if "dismes" in sub.columns else ""
    sub["codisi"] = sub["codisi"].astype(str).str.strip() if "codisi" in sub.columns else ""
    sub = sub.sort_values("data").groupby("data", as_index=False).last()
    sub["abre"] = sub["preabe"] / sub["fatcot"]
    sub["fecha"] = sub["preult"] / sub["fatcot"]
    return sub.reset_index(drop=True)


def _fechamento_em(papel, dia):
    """Fechamento (por ação) no último pregão <= dia; e se o pregão é o próprio dia."""
    if papel is None:
        return None, False
    antes = papel.loc[papel["data"] <= dia]
    if antes.empty:
        return None, False
    linha = antes.iloc[-1]
    return float(linha["fecha"]), linha["data"] == dia


# =========================================================================== #
#  Montagem da lista de eventos de um papel                                    #
# =========================================================================== #
def _evento(data_com, fator, tipo, descricao, fonte):
    return {"data_com": pd.Timestamp(data_com), "fator": float(fator),
            "tipo": tipo, "descricao": descricao, "fonte": fonte}


def eventos_em_acoes(complemento, isins, avisos, inicio=None, fim=None):
    """
    Desdobramentos, grupamentos e bonificações da lista da B3.

    Só valem os eventos registrados no ISIN do próprio papel. Numa unit isso
    importa: em 2014 o Santander agrupou as ações ON e PN, mas a unit SANB11
    foi recomposta e o preço dela não mudou — a B3 lança o grupamento só nas
    ações, e aplicá-lo à unit criaria um salto que não existiu.
    """
    eventos, vistos = [], set()
    no_periodo = lambda d: (inicio is None or d >= inicio) and (fim is None or d < fim)
    for e in (complemento or {}).get("stockDividends") or []:
        if (e.get("isinCode") or "").strip().upper() not in isins:
            continue
        data_com = _data(e.get("lastDatePrior"))
        f = _num(e.get("factor"))
        rotulo = (e.get("label") or "").strip().upper()
        # A mesma linha repetida é erro de cadastro: aplicada duas vezes, um
        # desdobramento de 2 viraria de 4.
        chave = (data_com, rotulo, f)
        if chave in vistos:
            continue
        vistos.add(chave)
        if data_com is None or not f or f <= 0:
            avisos.append(f"evento '{rotulo}' com dados incompletos na B3 foi ignorado "
                          f"(fator {e.get('factor')!r}, data {e.get('lastDatePrior')!r})")
            continue
        if rotulo in ("DESDOBRAMENTO", "BONIFICACAO"):
            mult = 1 + f / 100.0         # fator da B3 = % de ações novas
            if rotulo == "DESDOBRAMENTO":
                desc = f"Desdobramento: cada ação virou {_fmt_num(mult)}"
            else:
                desc = f"Bonificação de {_fmt_num(f)}% em ações"
        elif rotulo == "GRUPAMENTO":
            mult = f                     # fator da B3 = multiplicador direto
            desc = f"Grupamento: {_fmt_num(1 / f)} ações viraram 1"
        else:
            if no_periodo(data_com):
                if rotulo.startswith("CIS"):
                    texto = (f"data-com {_fmt(data_com)}: cisão (ações de outra empresa "
                             f"entregues aos acionistas) NÃO é ajustada — a queda do dia "
                             f"seguinte permanece na série")
                else:
                    texto = (f"data-com {_fmt(data_com)}: evento '{rotulo}' não é ajustado "
                             f"(só desdobramento, grupamento e bonificação)")
                if texto not in avisos:
                    avisos.append(texto)
            continue
        eventos.append(_evento(data_com, 1.0 / mult, rotulo.lower(), desc, "B3"))
    return eventos


def eventos_detectados(papel, eventos_conhecidos, inicio, fim, avisos):
    """
    Desdobramentos/grupamentos que faltam na lista da B3, achados no COTAHIST.

    Exige as três marcas juntas no mesmo pregão:
      1. o número de distribuição (DISMES) muda — a B3 o muda exatamente no
         dia "ex" de cada evento;
      2. a abertura salta x vezes em relação ao fechamento anterior, com x
         perto de uma razão inteira (2, 3, 4, 5, 8, 10...);
      3. a quantidade de ações negociadas passa a ser cerca de x vezes a de
         antes (num tombo de mercado o preço cai, mas a quantidade não
         multiplica).
    Saltos fortes num dia de evento sem as três marcas viram aviso.
    """
    if papel is None or len(papel) < 3:
        return []
    datas_conhecidas = [ev["data_com"] for ev in eventos_conhecidos]
    achados = []
    for i in range(1, len(papel)):
        ant, dia = papel.iloc[i - 1], papel.iloc[i]
        if not (inicio < dia["data"] <= fim):
            continue
        if not dia["dismes"] or dia["dismes"] == ant["dismes"]:
            continue
        if any(ant["data"] - timedelta(days=4) <= d < dia["data"] for d in datas_conhecidas):
            continue
        if not (ant["fecha"] > 0 and dia["abre"] > 0):
            continue
        salto = dia["abre"] / ant["fecha"]
        if SALTO_MINIMO <= salto <= SALTO_MAXIMO:
            continue
        candidatas = [r for r in RAZOES_DETECTAVEIS] + [1.0 / r for r in RAZOES_DETECTAVEIS]
        razao = min(candidatas, key=lambda r: abs(math.log(salto * r)))
        texto_salto = f"a cotação saltou ×{_fmt_num(salto, 3)} em {_fmt(dia['data'])}"
        if abs(math.log(salto * razao)) > TOLERANCIA_RAZAO:
            avisos.append(f"{texto_salto} num dia de evento, mas o salto não corresponde "
                          f"a um desdobramento/grupamento — NÃO ajustado; confira")
            continue
        q_antes = papel["quatot"].iloc[max(0, i - 10):i].median()
        q_depois = papel["quatot"].iloc[i:i + 10].median()
        if not (q_antes and q_depois and q_antes > 0 and q_depois > 0):
            continue
        # A quantidade tem de ficar mais perto de ×razão do que de ×1 (sem isso,
        # um desdobramento de 2 aceitaria quantidade inalterada).
        limite = min(TOLERANCIA_QUANTIDADE, abs(math.log(razao)) / 2)
        if abs(math.log((q_depois / q_antes) / razao)) > limite:
            avisos.append(f"{texto_salto} num dia de evento, mas a quantidade negociada "
                          f"não acompanhou (×{_fmt_num(q_depois / q_antes, 2)}) — NÃO "
                          f"ajustado; confira")
            continue
        if razao >= 1:
            tipo, desc = "desdobramento", f"Desdobramento: cada ação virou {_fmt_num(razao)}"
        else:
            tipo, desc = "grupamento", f"Grupamento: {_fmt_num(1 / razao)} ações viraram 1"
        achados.append(_evento(ant["data"], 1.0 / razao, tipo,
                               desc + " (ausente na lista da B3)", "COTAHIST"))
    return achados


NOMES_PROVENTO = {"JRS CAP PROPRIO": "JCP", "DIVIDENDO": "Dividendo",
                  "RENDIMENTO": "Rendimento", "REST CAP DIN": "Restituição de capital",
                  "AMORTIZACAO": "Amortização", "AMORTIZAÇÃO": "Amortização"}


def _agrupar_proventos(linhas, fonte):
    """Junta os proventos da mesma data-com: fator = 1 − soma dos percentuais."""
    por_data = {}
    for data_com, pct, rotulo in linhas:
        rotulo = rotulo.strip().upper()
        por_data.setdefault(data_com, []).append((pct, NOMES_PROVENTO.get(rotulo, rotulo.capitalize())))
    eventos = []
    for data_com, itens in sorted(por_data.items()):
        soma = sum(p for p, _ in itens)
        if soma >= 100:
            continue
        rotulos = sorted({r for _, r in itens})
        desc = f"{' + '.join(rotulos)}: {_fmt_num(soma, 3)}% do preço"
        if len(itens) > 1:
            desc += f" ({len(itens)} pagamentos)"
        eventos.append(_evento(data_com, 1 - soma / 100.0, "provento", desc, fonte))
    return eventos


def proventos_da_b3(historico, complemento, classe, isins, papel, inicio, fim, avisos):
    """
    Proventos em dinheiro de ações: o histórico da B3 (desde 1996, com o
    percentual já calculado) mais os dos dados complementares que ainda não
    estiverem nele.
    """
    linhas = []        # (data_com, pct, rotulo)
    vistos = {}        # (data, valor) -> quantas vezes; para não contar duas vezes
    rejeitadas = 0

    hist = historico or []
    if classe and any(l.get("typeStock") == classe for l in hist):
        hist = [l for l in hist if l.get("typeStock") == classe]
        conferir_classe = False
    else:
        # Classe não reconhecida (units, BDRs...): fica só o que bate com a
        # cotação do papel na data-com.
        conferir_classe = True

    for l in hist:
        data_com = _data(l.get("lastDatePriorEx"))
        if data_com is None or not (inicio <= data_com < fim):
            continue
        valor = _num(l.get("valueCash"))
        pct = _num(l.get("corporateActionPrice"))
        fech_b3 = _num(l.get("closingPricePriorExDate"))
        dia_preco = _data(l.get("dateClosingPricePriorExDate")) or data_com
        fech, exato = _fechamento_em(papel, dia_preco)
        # Conferência pelo preço: só no próprio pregão e com cotação unitária
        confere = None
        if fech and fech_b3 and exato:
            fatcot_dia = papel.loc[papel["data"] == dia_preco, "fatcot"].iloc[0]
            if fatcot_dia == 1:
                confere = abs(fech / fech_b3 - 1) <= TOLERANCIA_PRECO
        if confere is False or (confere is None and conferir_classe):
            rejeitadas += 1
            continue
        if not pct or pct <= 0:
            q = _num(l.get("quotedPerShares")) or 1
            r = _num(l.get("ratio")) or 1
            if valor and fech:
                pct = valor * q / r / fech * 100
        if not pct or pct <= 0:
            continue
        chave = (data_com, round(valor or 0, 6))
        vistos[chave] = vistos.get(chave, 0) + 1
        linhas.append((data_com, pct, (l.get("corporateAction") or "provento").strip().lower()))

    if rejeitadas and not conferir_classe:
        avisos.append(f"{rejeitadas} provento(s) da B3 ignorado(s): o preço informado "
                      f"pela B3 na data-com não confere com o COTAHIST")
    elif rejeitadas and conferir_classe and not linhas:
        avisos.append(f"o histórico da B3 não separa os proventos da classe "
                      f"{classe or 'deste papel'} e nenhum deles confere com a cotação "
                      f"— proventos do período NÃO ajustados")

    linhas += _proventos_recentes(complemento, isins, papel, inicio, fim, vistos, avisos)
    return _agrupar_proventos(linhas, "B3")


def _proventos_recentes(complemento, isins, papel, inicio, fim, vistos, avisos):
    """Proventos dos dados complementares (últimos ~12 meses), sem repetir."""
    linhas = []
    for e in (complemento or {}).get("cashDividends") or []:
        if (e.get("isinCode") or "").strip().upper() not in isins:
            continue
        data_com = _data(e.get("lastDatePrior"))
        valor = _num(e.get("rate"))
        if data_com is None or not valor or valor <= 0 or not (inicio <= data_com < fim):
            continue
        chave = (data_com, round(valor, 6))
        if vistos.get(chave, 0) > 0:
            vistos[chave] -= 1
            continue
        fech, _ = _fechamento_em(papel, data_com)
        if not fech:
            avisos.append(f"provento de {_fmt(data_com)} sem cotação para calcular o "
                          f"percentual — não ajustado")
            continue
        linhas.append((data_com, valor / fech * 100,
                       (e.get("label") or "provento").strip().lower()))
    return linhas


def proventos_fii(complemento, docs_fnet, ticker, isins, papel, inicio, fim, avisos):
    """
    Rendimentos e amortizações de FII: Fundos.NET (histórico) + dados
    complementares da B3 (últimos ~12 meses), sem contar duas vezes.

    No Fundos.NET o mesmo rendimento pode ter sido reenviado (retificação):
    para cada data-com vale o aviso de versão mais nova.
    """
    por_data = {}
    for doc in docs_fnet or []:
        itens = [x for x in doc["eventos"]
                 if x["codigo"] == ticker or (x["isin"] and x["isin"] in isins)]
        for x in itens:
            chave_doc = (int(doc.get("versao") or 1), int(doc["id"]))
            atual = por_data.get(x["data_com"])
            if atual is None or chave_doc > atual[0]:
                por_data[x["data_com"]] = (chave_doc, [y for y in itens
                                                       if y["data_com"] == x["data_com"]])

    linhas, vistos = [], {}
    for data_txt, (_, itens) in por_data.items():
        data_com = pd.Timestamp(data_txt)
        if not (inicio <= data_com < fim):
            continue
        fech, _ = _fechamento_em(papel, data_com)
        if not fech:
            continue
        for x in itens:
            chave = (data_com, round(x["valor"], 6))
            vistos[chave] = vistos.get(chave, 0) + 1
            rotulo = "amortização" if x["tipo"] == "AMORTIZACAO" else "rendimento"
            linhas.append((data_com, x["valor"] / fech * 100, rotulo))

    linhas += _proventos_recentes(complemento, isins, papel, inicio, fim, vistos, avisos)
    return _agrupar_proventos(linhas, "Fundos.NET/B3" if docs_fnet else "B3")


# =========================================================================== #
#  Busca (com cache) dos dados de cada papel                                   #
# =========================================================================== #
def _dados_b3(rede, cache, empresa, ultima_data, com_historico):
    """Complemento e histórico de proventos da empresa, do cache ou da B3."""
    nome = f"b3_{empresa}"
    salvo = cache.ler(nome)
    if salvo and _cache_serve(salvo.get("baixado_em"), ultima_data) and \
            (not com_historico or salvo.get("historico") is not None):
        return salvo.get("complemento"), salvo.get("historico"), True

    complemento = rede.complemento(empresa)
    historico = None
    if com_historico:
        historico = []
        if complemento and complemento.get("tradingName"):
            historico = rede.proventos(complemento["tradingName"])
    cache.gravar(nome, {"baixado_em": datetime.now().isoformat(timespec="seconds"),
                        "complemento": complemento, "historico": historico})
    return complemento, historico, False


def _dados_fnet(rede, cache, cnpj, inicio, fim, ultima_data):
    """
    Avisos de rendimento do FII no período. Cada aviso é baixado UMA vez e
    fica no cache; nas próximas buscas só se baixam os avisos novos.
    """
    nome = f"fnet_{cnpj}"
    salvo = cache.ler(nome) or {}
    conhecidos = salvo.get("docs") or {}
    janela = salvo.get("janela") or []

    ini_txt, fim_txt = inicio.strftime("%Y-%m-%d"), fim.strftime("%Y-%m-%d")

    # A lista de avisos do período é pedida de novo, salvo se o cache já
    # cobre o período e foi feito depois do último pregão da série.
    cobre = (len(janela) == 2 and janela[0] <= ini_txt and janela[1] >= fim_txt
             and _cache_serve(salvo.get("baixado_em"), ultima_data))
    if cobre:
        return [d for d in conhecidos.values() if d.get("situacao", "A") == "A"], 0

    # Rendimentos são anunciados até ~40 dias antes da data-com e às vezes
    # entregues alguns dias depois dela.
    lista = rede.fnet_documentos(cnpj, inicio - timedelta(days=40), fim + timedelta(days=10))
    novos = 0
    usados = []
    for item in lista:
        id_doc = str(item.get("id"))
        situacao = item.get("situacaoDocumento") or "A"
        doc = conhecidos.get(id_doc)
        if doc is None:
            if situacao != "A":
                continue
            try:
                eventos = ler_xml_rendimentos(rede.fnet_xml(id_doc))
            except ET.ParseError:
                eventos = []
            doc = {"id": id_doc, "versao": item.get("versao") or 1, "eventos": eventos}
            novos += 1
        doc["situacao"] = situacao
        ref = _data(item.get("dataReferencia"))
        doc["referencia"] = ref.strftime("%Y-%m-%d") if ref is not None else None
        conhecidos[id_doc] = doc
        if situacao == "A":
            usados.append(doc)

    # O período coberto só cresce se o anterior encostar no novo; senão
    # haveria um buraco no meio dado como "já consultado".
    nova = [ini_txt, fim_txt]
    if len(janela) == 2 and janela[0] <= fim_txt and janela[1] >= ini_txt:
        nova = [min(janela[0], ini_txt), max(janela[1], fim_txt)]
    cache.gravar(nome, {"baixado_em": datetime.now().isoformat(timespec="seconds"),
                        "janela": nova, "docs": conhecidos})
    return usados, novos


# =========================================================================== #
#  Função principal                                                            #
# =========================================================================== #
def ajustar_eventos(wide, bruto, proventos=True, pasta_cache=None,
                    tabela_fii_extra=None, progress=None, rede=None):
    """
    Ajusta as séries de preço da B3 por eventos corporativos.

    wide      : DataFrame Data × papéis (o que a importação da B3 monta).
    bruto     : DataFrame do COTAHIST devolvido por baixar_periodo (precisa
                das colunas codneg, data, codisi, dismes, preabe, preult,
                quatot e fatcot).
    proventos : True ajusta também dividendos, JCP e rendimentos (retorno
                total); False só desdobramentos, grupamentos e bonificações.

    Devolve (wide_ajustado, relatorio). Um papel cuja fonte não responde
    segue SEM ajuste e aparece em relatorio['falhas'] — nunca é ajustado pela
    metade em silêncio.
    """
    rede = rede or Rede()
    cache = Cache(pasta_cache)
    tabela_fii = carregar_tabela_fii(tabela_fii_extra)

    saida = wide.copy()
    datas = pd.to_datetime(saida["Data"])
    inicio, fim = datas.min(), datas.max()
    papeis = [c for c in saida.columns if c != "Data"]
    rel = {"inicio": inicio, "fim": fim, "proventos": proventos,
           "papeis": {}, "falhas": {}, "baixados": 0, "do_cache": 0}

    cache_b3 = {}                       # empresa -> (complemento, historico)
    for n, ticker in enumerate(papeis):
        if progress is not None:
            progress(n, len(papeis), ticker)
        print(f"  Eventos corporativos: {ticker}...")
        avisos = []
        info = {"eventos": [], "avisos": avisos, "ret_antes": None, "ret_depois": None}
        rel["papeis"][ticker] = info
        serie = pd.to_numeric(saida[ticker], errors="coerce")

        papel = _cotahist_do_papel(bruto, ticker)
        if papel is None:
            rel["falhas"][ticker] = "o papel não está no COTAHIST baixado"
            continue
        isins = {i.upper() for i in papel["codisi"].unique() if i and i != "nan"}
        empresa, classe = empresa_e_classe(ticker)

        # 1) Preço por ação (FATCOT)
        fatcot = papel.set_index("data")["fatcot"]
        if (fatcot != 1).any():
            f = fatcot.reindex(datas, method="ffill").fillna(1).to_numpy()
            serie = serie / f
            avisos.append("cotações antigas por lote de mil ações convertidas para preço por ação")

        # 2) Eventos da B3
        eventos = []
        complemento = historico = None
        if empresa:
            try:
                eh_fii = ticker in tabela_fii
                if empresa not in cache_b3:
                    complemento, historico, do_cache = _dados_b3(
                        rede, cache, empresa, fim, com_historico=proventos and not eh_fii)
                    cache_b3[empresa] = (complemento, historico)
                    rel["do_cache" if do_cache else "baixados"] += 1
                complemento, historico = cache_b3[empresa]
            except FonteIndisponivel as e:
                rel["falhas"][ticker] = f"a B3 não respondeu ({e}) — série mantida SEM ajuste"
                continue
            if complemento is None:
                avisos.append("a B3 não tem dados complementares deste código "
                              "(ETF, BDR ou papel fora de listagem?)")
            eventos += eventos_em_acoes(complemento, isins, avisos, inicio, fim)
        else:
            avisos.append("código fora do padrão da B3: só a detecção pelo COTAHIST foi feita")

        # 3) Desdobramentos ausentes na lista da B3, achados no COTAHIST
        eventos += eventos_detectados(papel, eventos, inicio, fim, avisos)

        # 4) Proventos
        if proventos and empresa:
            if ticker in tabela_fii:
                docs = []
                try:
                    docs, novos = _dados_fnet(rede, cache, tabela_fii[ticker], inicio, fim, fim)
                    rel["baixados"] += novos
                except FonteIndisponivel as e:
                    avisos.append(f"o Fundos.NET não respondeu ({e}): só os rendimentos "
                                  f"dos últimos ~12 meses (B3) foram ajustados")
                eventos += proventos_fii(complemento, docs, ticker, isins, papel,
                                         inicio, fim, avisos)
            else:
                eventos += proventos_da_b3(historico, complemento, classe, isins,
                                           papel, inicio, fim, avisos)
                if not historico and (complemento or {}).get("cashDividends"):
                    recentes = [_data(e.get("lastDatePrior"))
                                for e in complemento["cashDividends"]]
                    recentes = [d for d in recentes if d is not None]
                    if recentes and min(recentes) > inicio:
                        avisos.append(
                            f"só há proventos da B3 a partir de {_fmt(min(recentes))}; "
                            f"os anteriores NÃO foram ajustados"
                            + (" (FII fora da tabela de CNPJs — ver README)"
                               if any("CTF" in i for i in isins) else ""))

        # 5) Aplicação: preços até a data-com (inclusive) × fator
        aplicados = [ev for ev in eventos if inicio <= ev["data_com"] < fim]
        aplicados.sort(key=lambda ev: ev["data_com"])
        fator = pd.Series(1.0, index=saida.index)
        for ev in aplicados:
            fator[(datas <= ev["data_com"]).to_numpy()] *= ev["fator"]
        ajustada = serie * fator.to_numpy()
        saida[ticker] = ajustada

        # 6) Conferência: variações diárias ainda muito grandes
        var = ajustada.pct_change()
        for idx in var.index[var.abs() > VARIACAO_SUSPEITA]:
            avisos.append(f"variação de {var[idx] * 100:+.0f}% em {_fmt(datas[idx])} "
                          f"mesmo depois do ajuste — confira se há evento faltando")

        info["eventos"] = aplicados
        valida = serie.dropna()
        if len(valida) >= 2:
            orig = pd.to_numeric(wide[ticker], errors="coerce").dropna()
            info["ret_antes"] = orig.iloc[-1] / orig.iloc[0] - 1
            aj = ajustada.dropna()
            info["ret_depois"] = aj.iloc[-1] / aj.iloc[0] - 1

    if progress is not None:
        progress(len(papeis), len(papeis), None)
    return saida, rel


# =========================================================================== #
#  Relatório legível                                                           #
# =========================================================================== #
def texto_relatorio(rel):
    """O que foi ajustado, papel por papel, para o usuário conferir."""
    linhas = ["AJUSTE POR EVENTOS CORPORATIVOS",
              f"Período: {_fmt(rel['inicio'])} a {_fmt(rel['fim'])}",
              "Ajustados: desdobramentos, grupamentos e bonificações"
              + (" + proventos (dividendos, JCP, rendimentos)" if rel["proventos"]
                 else " (proventos NÃO ajustados)"),
              "Regra: os preços até a data-com (inclusive) são multiplicados pelo "
              "fator; o último preço da série é o real.", ""]
    for ticker, info in rel["papeis"].items():
        linhas.append("=" * 72)
        if ticker in rel["falhas"]:
            linhas.append(f"{ticker}: ⚠️ NÃO AJUSTADO — {rel['falhas'][ticker]}")
            continue
        acoes = [ev for ev in info["eventos"] if ev["tipo"] != "provento"]
        prov = [ev for ev in info["eventos"] if ev["tipo"] == "provento"]
        cab = f"{ticker}: {len(acoes)} evento(s) em ações, {len(prov)} data(s) de provento"
        if info["ret_antes"] is not None:
            cab += (f" | retorno no período: {info['ret_antes'] * 100:+.1f}% sem ajuste "
                    f"→ {info['ret_depois'] * 100:+.1f}% ajustado")
        linhas.append(cab)
        for ev in info["eventos"]:
            linhas.append(f"   data-com {_fmt(ev['data_com'])}  {ev['descricao']:<58} "
                          f"fator {_fmt_num(ev['fator'], 6):>10}  [{ev['fonte']}]")
        for a in info["avisos"]:
            linhas.append(f"   ⚠️ {a}")
    if rel["falhas"]:
        linhas += ["", "=" * 72,
                   f"⚠️ {len(rel['falhas'])} papel(is) ficou(aram) SEM ajuste: "
                   + ", ".join(rel["falhas"])]
    return "\n".join(linhas)


def resumo_curto(rel):
    """Uma ou duas linhas para a mensagem de sucesso da importação."""
    n_acoes = sum(1 for i in rel["papeis"].values() for ev in i["eventos"] if ev["tipo"] != "provento")
    n_prov = sum(1 for i in rel["papeis"].values() for ev in i["eventos"] if ev["tipo"] == "provento")
    n_avisos = sum(len(i["avisos"]) for i in rel["papeis"].values())
    txt = f"🧮 Ajuste por eventos: {n_acoes} em ações"
    if rel["proventos"]:
        txt += f", {n_prov} datas de provento"
    if n_avisos:
        txt += f" | {n_avisos} aviso(s)"
    if rel["falhas"]:
        txt += f"\n⚠️ SEM ajuste (fonte não respondeu): {', '.join(rel['falhas'])}"
    return txt


# =========================================================================== #
#  Uso direto, para conferir a conexão: python eventos_corporativos.py MGLU3   #
# =========================================================================== #
if __name__ == "__main__":
    import sys
    papeis = [p.upper() for p in sys.argv[1:]] or ["MGLU3"]
    rede = Rede()
    for t in papeis:
        empresa, classe = empresa_e_classe(t)
        print("=" * 72)
        print(f"{t}  (empresa {empresa}, classe {classe})")
        try:
            comp = rede.complemento(empresa)
        except FonteIndisponivel as e:
            print(f"  B3 não respondeu: {e}")
            continue
        if not comp:
            print("  a B3 não tem dados complementares deste código")
            continue
        print(f"  nome de pregão: {comp['tradingName']!r}")
        for e in comp["stockDividends"]:
            print(f"  {e.get('label'):<14} fator {e.get('factor'):<20} "
                  f"data-com {e.get('lastDatePrior')}  ISIN {e.get('isinCode')}")
        print(f"  proventos recentes (dados complementares): {len(comp['cashDividends'])}")
        if t in TABELA_FII_PRONTA:
            cnpj = TABELA_FII_PRONTA[t][0]
            print(f"  FII: CNPJ {cnpj} — consultando o Fundos.NET (últimos 12 meses)...")
            hoje = pd.Timestamp.today().normalize()
            try:
                docs = rede.fnet_documentos(cnpj, hoje - timedelta(days=365), hoje)
            except FonteIndisponivel as e:
                print(f"  Fundos.NET não respondeu: {e}")
                continue
            ativos = [d for d in docs if (d.get("situacaoDocumento") or "A") == "A"]
            print(f"  avisos de rendimento encontrados: {len(docs)} ({len(ativos)} ativos)")
            for d in ativos[:3]:
                try:
                    evs = ler_xml_rendimentos(rede.fnet_xml(d.get("id")))
                except Exception as e:
                    print(f"    aviso {d.get('id')}: não foi possível ler ({type(e).__name__})")
                    continue
                for x in evs:
                    if x["codigo"] == t:
                        print(f"    data-com {x['data_com']}  R$ {x['valor']:.4f} por cota "
                              f"({x['tipo'].lower()})")
        else:
            hist = rede.proventos(comp["tradingName"])
            datas = [_data(l.get("lastDatePriorEx")) for l in hist]
            datas = [d for d in datas if d is not None]
            if datas:
                print(f"  histórico de proventos: {len(hist)} linhas, de "
                      f"{_fmt(min(datas))} a {_fmt(max(datas))}")
                classes = {}
                for l in hist:
                    c = l.get("typeStock") or "?"
                    classes[c] = classes.get(c, 0) + 1
                print("  classes no histórico: "
                      + ", ".join(f"{c}={n}" for c, n in sorted(classes.items())))
                if classe and classe not in classes:
                    print(f"  ⚠️ a classe {classe} não aparece: só entram os proventos "
                          f"cujo preço confere com a cotação do papel")
                recentes = [l for l in hist if l.get("typeStock") == classe][:3]
                for l in recentes:
                    print(f"    data-com {l.get('lastDatePriorEx')}  {l.get('corporateAction'):<16}"
                          f" R$ {l.get('valueCash')}  fechamento R$ "
                          f"{l.get('closingPricePriorExDate')}  ({l.get('corporateActionPrice')}%)")
            else:
                print("  histórico de proventos: vazio")
