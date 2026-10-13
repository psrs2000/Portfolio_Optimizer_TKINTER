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
import bisect
import csv
import json
import math
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
from datetime import datetime, timedelta
from functools import partial
from urllib import robotparser
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

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
# Site NÃO oficial (opcional) para completar o histórico de proventos que as
# fontes oficiais não têm (hoje: FI-Infra e FIP). O endereço recebe o código
# no fim, ou no lugar de {ticker}. Vários endereços separados por ";" são
# tentados em ordem: o seguinte só é consultado se o anterior não passar na
# conferência ou não cobrir o período. Os termos do Carteira Falcão permitem
# o uso dos dados para fins pessoais; os do BRFiis não restringem o uso; o
# robots.txt dos dois libera as páginas. O BRFiis traz as amortizações (o
# Carteira Falcão não), e a tabela dele é paginada (?page=N).
SITE_PADRAO = "https://carteirafalcao.com.br/dividendos/ ; https://brfiis.com.br/fundos/"
SITES_PADRAO_ANTERIORES = ("https://carteirafalcao.com.br/dividendos/",)
PAUSA_SITE = 1.0               # segundos entre as páginas de uma tabela paginada
MAX_PAGINAS_SITE = 40
# Tipos de fundo da busca do Fundos.NET que publicam o aviso estruturado de
# "Rendimentos e Amortizações" (mesmo XML): FII, Fiagro e FIDC. FI-Infra e FIP
# não publicam lá.
TIPOS_FNET = ("1", "11", "2")
PARALELO = 4                   # consultas simultâneas (uma por empresa/fundo)
PARALELO_FNET = 6              # avisos do Fundos.NET baixados ao mesmo tempo (no total)
TEMPO_LIMITE = (10, 30)        # segundos: para conectar / para receber a resposta
LENTO = 5.0                    # resposta acima disto é registrada no console
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
    """
    Pedidos HTTP às fontes, com novas tentativas e pausa entre pedidos.

    Pode ser usada por várias linhas de execução ao mesmo tempo: cada uma
    tem a sua própria sessão. A página inicial do Fundos.NET é aberta uma
    vez só, e os cookies dela são repassados às demais sessões. Os avisos do
    Fundos.NET são baixados por um grupo FIXO de linhas de execução, que
    reaproveitam a conexão de um aviso para o outro.
    """

    def __init__(self):
        self._local = threading.local()
        self._trava = threading.Lock()
        self._fnet_cookies = None
        self._fnet_cabecalhos = {}
        self._robots = {}             # site -> regras do robots.txt
        self._pool = None

    def pool(self):
        """Linhas de execução para os downloads do Fundos.NET (criadas uma vez)."""
        with self._trava:
            if self._pool is None:
                self._pool = ThreadPoolExecutor(PARALELO_FNET, thread_name_prefix="fnet")
            return self._pool

    def fechar(self):
        if self._pool is not None:
            self._pool.shutdown(wait=False)
            self._pool = None

    @property
    def s(self):
        sessao = getattr(self._local, "sessao", None)
        if sessao is None:
            sessao = requests.Session()
            sessao.headers.update(CABECALHOS)
            self._local.sessao = sessao
        return sessao

    def _get(self, url, **kw):
        ultimo = "sem resposta"
        site = "Fundos.NET" if url.startswith(FNET_BASE) else "B3"
        limite_tempo = kw.pop("timeout", TEMPO_LIMITE)
        for tentativa in range(TENTATIVAS):
            t0 = time.time()
            try:
                r = self.s.get(url, timeout=limite_tempo, **kw)
                demora = time.time() - t0
                if demora > LENTO:
                    print(f"  [lento] {site} levou {demora:.0f} s para responder")
                if r.status_code == 200:
                    time.sleep(PAUSA)
                    return r
                ultimo = f"HTTP {r.status_code}"
            except requests.RequestException as e:
                ultimo = f"{type(e).__name__}: {e}"
            if tentativa < TENTATIVAS - 1:
                print(f"  [nova tentativa {tentativa + 2}/{TENTATIVAS}] {site}: {ultimo}")
                time.sleep(1.5 * (tentativa + 1))
        raise FonteIndisponivel(ultimo)

    # ---- Site não oficial ----
    def site_permite(self, url):
        """
        O robots.txt do site libera esta página? Sem robots.txt, nada é
        proibido (é a convenção). Uma vez lido, fica guardado durante a busca.
        """
        p = urlparse(url)
        raiz = f"{p.scheme}://{p.netloc}"
        with self._trava:
            regras = self._robots.get(raiz)
        if regras is None:
            regras = robotparser.RobotFileParser()
            try:
                r = self.s.get(raiz + "/robots.txt", timeout=TEMPO_LIMITE)
            except requests.RequestException as e:
                raise FonteIndisponivel(f"{type(e).__name__}: {e}")
            texto = r.text if r.status_code == 200 else ""
            if "<html" in texto[:500].lower():   # página de erro, não robots.txt
                texto = ""
            regras.parse(texto.splitlines())
            with self._trava:
                self._robots[raiz] = regras
        return regras.can_fetch(CABECALHOS["User-Agent"], url)

    def site_html(self, url):
        return self._get(url, headers={"Accept": "text/html,application/xhtml+xml,*/*"}).text

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
        try:
            dados = self._json(URL_COMPLEMENTO_EMPRESA + _b64(
                {"issuingCompany": empresa, "language": "pt-br"}))
        except FonteIndisponivel as e:
            # Para alguns fundos (ex.: RBRY11) o cadastro de EMPRESAS devolve
            # uma página em vez de JSON; o de FUNDOS ainda pode responder.
            erro_empresa, dados = e, None
        else:
            erro_empresa = None
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
            if erro_empresa is not None:
                raise erro_empresa
            return None
        item = dados[0] if isinstance(dados, list) and dados else dados
        if isinstance(item, dict) and (item.get("stockDividends") or item.get("cashDividends")):
            return {"tradingName": (item.get("fund") or "").strip(),
                    "stockDividends": item.get("stockDividends") or [],
                    "cashDividends": item.get("cashDividends") or []}
        if erro_empresa is not None:
            raise erro_empresa
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
        if getattr(self._local, "fnet_aberto", False):
            return
        with self._trava:
            if self._fnet_cookies is None:
                r = self._get(FNET_BASE + "abrirGerenciadorDocumentosCVM")
                m = (re.search(r'<meta[^>]+name="_csrf"[^>]+content="([^"]+)"', r.text)
                     or re.search(r'content="([^"]+)"[^>]+name="_csrf"', r.text))
                self._fnet_cabecalhos = {"CSRFToken": m.group(1)} if m else {}
                self._fnet_cookies = self.s.cookies.get_dict()
        self.s.cookies.update(self._fnet_cookies)
        self.s.headers.update(self._fnet_cabecalhos)
        self._local.fnet_aberto = True

    def fnet_documentos(self, cnpj, d_ini, d_fim, limite=2000, tipos=TIPOS_FNET):
        """
        Avisos de 'Rendimentos e Amortizações' entregues no período: do fundo
        com esse CNPJ, ou de TODOS os FIIs, Fiagro e FIDC se cnpj for None.

        A busca do Fundos.NET exige o tipo de fundo. Com CNPJ, consultam-se
        TODOS os tipos e os avisos são juntados: um mesmo fundo pode ter
        publicado como "Fundo Imobiliário" até 2025 e como "Fiagro" depois (a
        adaptação à CVM 175). Parar no primeiro tipo que respondia deixava
        meses de fora.
        """
        if cnpj is None:
            docs = []
            for tipo in tipos:
                docs += self._fnet_buscar(None, tipo, d_ini, d_fim, limite)
            return docs
        docs, vistos = [], set()
        for tipo in TIPOS_FNET:
            for d in self._fnet_buscar(cnpj, tipo, d_ini, d_fim, limite):
                if d.get("id") not in vistos:
                    vistos.add(d.get("id"))
                    docs.append(d)
        return docs

    def _fnet_buscar(self, cnpj, tipo, d_ini, d_fim, limite):
        self._abrir_fnet()
        docs, inicio, total, contador = [], 0, None, 0
        while True:
            contador += 1
            params = {"d": str(contador), "s": str(inicio), "l": "100",
                      "o[0][dataEntrega]": "desc", "tipoFundo": tipo,
                      "idCategoriaDocumento": "14", "idTipoDocumento": "41",
                      "idEspecieDocumento": "0",
                      "dataInicial": _fmt(d_ini), "dataFinal": _fmt(d_fim),
                      "_": str(int(time.time() * 1000))}
            if cnpj:
                params["cnpj"] = params["cnpjFundo"] = cnpj
            # A lista do Fundos.NET às vezes demora bem mais que os avisos.
            d = self._json(FNET_BASE + "pesquisarGerenciadorDocumentosDados",
                           params=params, headers={"X-Requested-With": "XMLHttpRequest"},
                           timeout=(10, 60))
            pagina = (d.get("data") if isinstance(d, dict) else None) or []
            if total is None and isinstance(d, dict):
                total = d.get("recordsTotal")
            if not pagina:
                break
            docs.extend(pagina)
            inicio += len(pagina)
            if total is not None and inicio >= int(total):
                break
            if inicio >= limite:
                break
        return docs

    def fnet_xml(self, id_doc):
        self._abrir_fnet()
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


def ler_xml_cnpj(conteudo):
    """CNPJ do fundo (só dígitos) informado nos dados gerais do aviso."""
    raiz = ET.fromstring(conteudo)
    for el in raiz.iter():
        if el.tag.split("}")[-1] == "CNPJFundo":
            return re.sub(r"\D", "", el.text or "")
    return ""


def _nome_normal(txt):
    return re.sub(r"\s+", " ", (txt or "").replace("/", "")).strip().upper()


PREFIXOS_FNET = {"FIAGRO": "11", "FIDC": "2", "FII": "1"}


def tipo_fnet_pelo_nome(nome_pregao):
    """Tipo de fundo do Fundos.NET pelo nome de pregão da B3 ('FIAGRO RIZA' -> '11')."""
    return PREFIXOS_FNET.get(_nome_normal(nome_pregao).split(" ")[0], "1")


def descobrir_cnpjs_fii(rede, procurados):
    """
    Descobre no Fundos.NET o CNPJ de FIIs que não estão na tabela.

    procurados: {código: (nome de pregão na B3, ISINs do papel)}.
    Devolve ({código: (cnpj, nome do fundo)} dos encontrados, completo), em
    que completo=False indica que alguma consulta falhou — quem não foi achado
    nesse caso NÃO deve ser dado como inexistente.

    Cada fundo é procurado só no tipo indicado pelo nome de pregão (FIAGRO,
    FIDC ou FII), o que deixa a consulta bem mais leve.

    Como: a lista de avisos de rendimento recentes de TODOS os FIIs traz o
    nome de pregão de cada fundo (o mesmo da B3). Para cada candidato com o
    mesmo nome, baixa-se o aviso e confere-se que ele cita o código (ou o
    ISIN) do papel — só então o CNPJ do aviso é aceito. Um nome parecido
    nunca basta.
    """
    achados, completo = {}, True
    hoje = pd.Timestamp.today().normalize()
    for dias in (45, 150):        # quem não pagou no último mês e meio, mais atrás
        faltam = {c: v for c, v in procurados.items() if c not in achados}
        if not faltam:
            break
        listas = {}
        for tipo in sorted({tipo_fnet_pelo_nome(n) for n, _ in faltam.values()}):
            try:
                listas[tipo] = rede.fnet_documentos(None, hoje - timedelta(days=dias), hoje,
                                                    limite=4000, tipos=(tipo,))
            except FonteIndisponivel as e:
                completo = False
                print(f"  [aviso] lista do Fundos.NET (tipo {tipo}) falhou: {e}")
        for codigo, (nome, isins) in faltam.items():
            lista = listas.get(tipo_fnet_pelo_nome(nome))
            if lista is None:
                continue
            alvo = _nome_normal(nome)
            emp = codigo[:4]
            candidatos = []
            for item in lista:
                if (item.get("situacaoDocumento") or "A") != "A":
                    continue
                nomes = {_nome_normal(item.get("nomePregao"))}
                nomes |= {_nome_normal(x) for x in (item.get("informacoesAdicionais") or "").split(";")}
                if (alvo and alvo in nomes) or any(emp in n.split() for n in nomes if n):
                    candidatos.append(item)
            for item in candidatos[:4]:
                try:
                    xml = rede.fnet_xml(item.get("id"))
                    itens = ler_xml_rendimentos(xml)
                    cnpj = ler_xml_cnpj(xml)
                except FonteIndisponivel:
                    completo = False
                    continue
                except ET.ParseError:
                    continue
                if len(cnpj) == 14 and any(x["codigo"] == codigo or (x["isin"] and x["isin"] in isins)
                                           for x in itens):
                    achados[codigo] = (cnpj, (item.get("descricaoFundo") or "").strip())
                    break
    return achados, completo


def gravar_cnpj_extra(caminho, codigo, cnpj):
    """Acrescenta o fundo ao fii_cnpj.csv do usuário (cria o arquivo se preciso)."""
    if not caminho:
        return False
    try:
        novo = not os.path.exists(caminho)
        if novo:
            os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
        with open(caminho, "a", encoding="utf-8", newline="") as fh:
            if novo:
                fh.write("codigo;cnpj\n")
            fh.write(f"{codigo};{cnpj}\n")
        return True
    except OSError:
        return False


def _texto_html(t):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t or "")).strip()


def ler_tabela_proventos(html):
    """
    A tabela de proventos de uma página: a que tem colunas de "Data com" (ou
    "Data base", o nome usado nos avisos de fundos) e "Valor" (o "Tipo" é
    opcional). Serve para qualquer site que apresente os proventos assim — o
    Carteira Falcão e o BRFiis, por exemplo. Do valor vale o primeiro número
    da célula (o BRFiis põe ao lado a variação, como "+614,3%").
    Devolve [{'data': Timestamp, 'valor': float, 'tipo': str}].
    """
    melhor = []
    for tabela in re.findall(r"<table.*?</table>", html, re.S | re.I):
        titulos = [_texto_html(x).lower()
                   for x in re.findall(r"<th[^>]*>(.*?)</th>", tabela, re.S | re.I)]
        i_data = next((i for i, t in enumerate(titulos)
                       if "data" in t.split() and {"com", "base"} & set(t.split())), None)
        i_valor = next((i for i, t in enumerate(titulos) if "valor" in t), None)
        i_tipo = next((i for i, t in enumerate(titulos) if "tipo" in t), None)
        if i_data is None or i_valor is None:
            continue
        linhas = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tabela, re.S | re.I):
            cel = [_texto_html(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)]
            if len(cel) <= max(i_data, i_valor):
                continue
            data = _data(cel[i_data])
            numero = re.search(r"\d[\d.]*(?:,\d+)?", cel[i_valor])
            valor = _num(numero.group(0)) if numero else None
            if data is None or not valor or valor <= 0:
                continue
            tipo = cel[i_tipo] if i_tipo is not None and i_tipo < len(cel) else "provento"
            linhas.append({"data": data, "valor": valor, "tipo": tipo or "provento"})
        if len(linhas) > len(melhor):
            melhor = linhas
    return melhor


def endereco_site(base, ticker):
    """'https://site/dividendos/' + 'KDIF11', ou {ticker} trocado pelo código."""
    if "{ticker}" in base or "{TICKER}" in base:
        return base.replace("{ticker}", ticker.lower()).replace("{TICKER}", ticker)
    return base.rstrip("/") + "/" + ticker


def lista_sites(texto):
    """'end1 ; end2' (ou uma lista) -> [end1, end2], na ordem."""
    if not texto:
        return []
    if isinstance(texto, (list, tuple)):
        return [t.strip() for t in texto if t and t.strip()]
    return [t.strip() for t in re.split(r"[;\n]", texto) if t.strip()]


def _paginacao(html, url):
    """
    (última página, nome do parâmetro) se a tabela for paginada por links
    para o próprio endereço com ?page=N (ou ?pagina=N); senão (1, None).
    """
    caminho = urlparse(url).path.rstrip("/")
    ultima, chave = 1, None
    for href in re.findall(r"""href=["']([^"']+)["']""", html, re.I):
        u = urlparse(urljoin(url, href.replace("&amp;", "&")))
        if u.path.rstrip("/") != caminho:
            continue
        for k, v in parse_qsl(u.query):
            if k.lower() in ("page", "pagina") and v.isdigit() and int(v) > ultima:
                ultima, chave = int(v), k
    return ultima, chave


def _com_parametro(url, chave, valor):
    p = urlparse(url)
    q = [(k, v) for k, v in parse_qsl(p.query) if k != chave] + [(chave, str(valor))]
    return urlunparse(p._replace(query=urlencode(q), fragment=""))


def _dados_site(rede, cache, base, ticker, inicio, ultima_data):
    """
    Proventos do papel no site não oficial (do cache, se ainda servir). Se a
    tabela for paginada, lê as páginas seguintes (com pausa entre elas) só até
    alcançar o início do período.
    """
    url = endereco_site(base, ticker)
    site = urlparse(url).netloc
    nome = f"site_{site}_{ticker}"
    salvo = cache.ler(nome)
    if (salvo and salvo.get("url") == url and _cache_serve(salvo.get("baixado_em"), ultima_data)
            and (salvo.get("completo", True)
                 or pd.Timestamp(salvo.get("desde") or "2100-01-01") <= inicio)):
        return {"site": site, "url": url, "proibido": False, "linhas": salvo.get("linhas") or []}
    if not rede.site_permite(url):
        return {"site": site, "url": url, "proibido": True, "linhas": []}
    html = rede.site_html(url)
    linhas = ler_tabela_proventos(html)
    ultima, chave = _paginacao(html, url)
    completo = True
    for n in range(2, ultima + 1):
        if not linhas:
            break
        if min(l["data"] for l in linhas) < inicio or n > MAX_PAGINAS_SITE:
            completo = False           # o resto é anterior ao período
            break
        pagina = _com_parametro(url, chave, n)
        if not rede.site_permite(pagina):
            completo = False
            break
        time.sleep(PAUSA_SITE)
        novas = ler_tabela_proventos(rede.site_html(pagina))
        if not novas:
            break
        linhas += novas
    linhas = [{"data": l["data"].strftime("%Y-%m-%d"), "valor": l["valor"], "tipo": l["tipo"]}
              for l in linhas]
    cache.gravar(nome, {"baixado_em": datetime.now().isoformat(timespec="seconds"),
                        "url": url, "linhas": linhas, "completo": completo,
                        "desde": pd.Timestamp(inicio).strftime("%Y-%m-%d")})
    return {"site": site, "url": url, "proibido": False, "linhas": linhas}


def _buscar_sites(rede, cache, sites, ticker, inicio, ultima_data, recentes, papel):
    """
    Consulta os sites na ordem dada; para no primeiro que passa na conferência
    com a B3 e cobre o período (ou a vida do papel, se for mais nova).
    Devolve [(endereço base, resultado ou exceção)] dos sites consultados.
    """
    primeiro = min(papel["data"]) if papel is not None and len(papel) else inicio
    alvo = max(inicio, primeiro) + timedelta(days=45)
    tentativas = []
    for base in sites:
        try:
            resultado = _dados_site(rede, cache, base, ticker, inicio, ultima_data)
        except (FonteIndisponivel, requests.RequestException) as e:
            tentativas.append((base, e))
            continue
        tentativas.append((base, resultado))
        if resultado["linhas"] and not resultado["proibido"]:
            aceito = conferir_site(resultado["linhas"], recentes, papel)[0]
            if aceito and min(pd.Timestamp(l["data"]) for l in resultado["linhas"]) <= alvo:
                break
    return tentativas


def _bloco_recente_b3(complemento, isins):
    """
    {data-com: valor somado} dos proventos dos dados complementares da B3 —
    só o bloco recente (~12 meses) do próprio papel. Uma linha antiga solta
    (o JURO11 tem uma de 2022) não conta como cobertura.
    """
    soma = {}
    for e in (complemento or {}).get("cashDividends") or []:
        if (e.get("isinCode") or "").strip().upper() not in isins:
            continue
        d, v = _data(e.get("lastDatePrior")), _num(e.get("rate"))
        if d is not None and v:
            soma[d] = soma.get(d, 0) + v
    if soma:
        limite = max(soma) - timedelta(days=400)
        soma = {d: v for d, v in soma.items() if d >= limite}
    return soma


def conferir_site(linhas, recentes, papel):
    """
    Confere o site contra os proventos EXATOS da B3 (últimos ~12 meses).

    Alguns sites chamam de "data com" a data ex (o pregão seguinte): os dois
    alinhamentos são testados e fica o que mais acerta. O site só é aceito se
    acertar data e valor em pelo menos 90% das datas da B3 (tolerância de 1
    centavo ou 1%, pelo arredondamento) e não inventar mais que uma data no
    mesmo período.

    Devolve (aceito, ex_corrigida, acertos, total, sobras, antigos), em que
    antigos = {data-com: (valor, tipos)} anteriores ao bloco da B3.
    """
    soma, tipos = {}, {}
    for l in linhas:
        d = pd.Timestamp(l["data"])
        soma[d] = soma.get(d, 0) + l["valor"]
        tipos.setdefault(d, set()).add(str(l.get("tipo") or "provento"))
    pregoes = sorted(papel["data"]) if papel is not None else []

    def anterior(d):
        pos = bisect.bisect_left(pregoes, d)
        return pregoes[pos - 1] if pos > 0 else None

    ini_b3, fim_b3 = min(recentes), max(recentes)
    melhor = None
    for desloc in (0, 1):
        mapa, tip = {}, {}
        for d, v in soma.items():
            dc = d if desloc == 0 else anterior(d)
            if dc is None:
                continue
            mapa[dc] = mapa.get(dc, 0) + v
            tip.setdefault(dc, set()).update(tipos[d])
        acertos = sum(1 for d, v in recentes.items()
                      if d in mapa and abs(mapa[d] - v) <= max(0.011, 0.01 * v))
        sobras = sum(1 for d in mapa if ini_b3 <= d <= fim_b3 and d not in recentes)
        chave = (acertos, -sobras)
        if melhor is None or chave > melhor[0]:
            melhor = (chave, desloc, mapa, tip, acertos, sobras)
    _, desloc, mapa, tip, acertos, sobras = melhor
    total = len(recentes)
    aceito = total >= 3 and acertos >= 0.9 * total and sobras <= 1
    antigos = {d: (v, tip[d]) for d, v in mapa.items() if d < ini_b3}
    return aceito, bool(desloc), acertos, total, sobras, antigos


def _proventos_do_site(resultado, recentes, papel, inicio, site_padrao):
    """
    Eventos com os proventos antigos vindos do site, se ele passar na
    conferência. Devolve (eventos, mensagem, aceito).
    """
    site = (resultado or {}).get("site") if isinstance(resultado, dict) else urlparse(site_padrao).netloc
    if isinstance(resultado, Exception):
        return [], f"o site {site} não respondeu ({resultado})", False
    if resultado.get("proibido"):
        return [], f"o robots.txt de {site} não permite ler {resultado['url']}", False
    if not resultado.get("linhas"):
        return [], f"{site} não tem tabela de proventos para este papel", False
    aceito, ex_corrigida, acertos, total, sobras, antigos = conferir_site(
        resultado["linhas"], recentes, papel)
    if not aceito:
        return [], (f"{site} confere com a B3 em só {acertos} de {total} datas"
                    + (f" e tem {sobras} data(s) a mais" if sobras else "")
                    + " — NÃO usado"), False
    linhas = []
    for d, (v, tipos) in sorted(antigos.items()):
        if d < inicio:
            continue
        fech, _ = _fechamento_em(papel, d)
        if fech:
            linhas.append((d, v / fech * 100, " + ".join(sorted(tipos))))
    eventos = _agrupar_proventos(linhas, f"site: {site}")
    msg = (f"proventos anteriores a {_fmt(min(recentes))} completados com {site} "
           f"(FONTE NÃO OFICIAL): {len(eventos)} data(s); conferido com a B3 em "
           f"{acertos} de {total} datas"
           + (" — a 'data com' do site é a data ex, corrigida para a data-com" if ex_corrigida else ""))
    return eventos, msg, True


def _proventos_dos_sites(tentativas, recentes, papel, inicio):
    """
    Entre os sites consultados, fica o aceito na conferência que traz mais
    datas (no empate, o primeiro da lista). Devolve (eventos, mensagem, aceito);
    a mensagem cita também os sites recusados.
    """
    melhor, recusas = None, []
    for base, resultado in tentativas:
        eventos, msg, aceito = _proventos_do_site(resultado, recentes, papel, inicio, base)
        if not aceito:
            recusas.append(msg)
        elif melhor is None or len(eventos) > len(melhor[0]):
            melhor = (eventos, msg)
    if melhor is None:
        return [], "; ".join(recusas), False
    return melhor[0], melhor[1] + (f" (outro site: {'; '.join(recusas)})" if recusas else ""), True


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
                  "AMORTIZACAO": "Amortização", "AMORTIZAÇÃO": "Amortização",
                  "AMORTIZACAO RF": "Amortização", "AMORTIZACAO RV": "Amortização"}


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


def _proventos_recentes(complemento, isins, papel, inicio, fim, vistos, avisos,
                        datas_cobertas=()):
    """
    Proventos dos dados complementares (últimos ~12 meses), sem repetir.
    Datas em datas_cobertas já vieram completas de outra fonte e são puladas.
    """
    linhas = []
    for e in (complemento or {}).get("cashDividends") or []:
        if (e.get("isinCode") or "").strip().upper() not in isins:
            continue
        data_com = _data(e.get("lastDatePrior"))
        valor = _num(e.get("rate"))
        if data_com is None or not valor or valor <= 0 or not (inicio <= data_com < fim):
            continue
        if data_com in datas_cobertas:
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

    # Data que o Fundos.NET já trouxe não é somada de novo com o valor da B3,
    # mesmo que os dois difiram em centavos (o aviso do fundo prevalece).
    cobertas = {d for d, _, _ in linhas}
    linhas += _proventos_recentes(complemento, isins, papel, inicio, fim, vistos, avisos,
                                  cobertas)
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


def _dados_fnet(rede, cache, cnpj, inicio, fim, ultima_data, andamento=None, chave=None):
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

    # Só os avisos ainda não guardados são baixados — vários ao mesmo tempo.
    pendentes = [str(i.get("id")) for i in lista
                 if str(i.get("id")) not in conhecidos
                 and (i.get("situacaoDocumento") or "A") == "A"]

    def baixar(id_doc):
        try:
            return ler_xml_rendimentos(rede.fnet_xml(id_doc))
        except ET.ParseError:
            return []

    lidos, erro = {}, None
    if andamento is not None:
        andamento[chave] = [0, len(pendentes)]
    if pendentes:
        t0 = time.time()
        proprio = None if hasattr(rede, "pool") else ThreadPoolExecutor(PARALELO)
        pool = rede.pool() if proprio is None else proprio
        try:
            futuros = {pool.submit(baixar, i): i for i in pendentes}
            for fut in as_completed(futuros):
                try:
                    lidos[futuros[fut]] = fut.result()
                except FonteIndisponivel as e:
                    erro = e
                if andamento is not None:
                    andamento[chave][0] += 1
        finally:
            if proprio is not None:
                proprio.shutdown(wait=True)
        demora = time.time() - t0
        rotulo = chave[1] if chave else cnpj
        print(f"  Fundos.NET {rotulo}: {len(pendentes)} avisos novos em {demora:.0f} s "
              f"({demora / len(pendentes):.1f} s cada, {PARALELO_FNET} ao mesmo tempo)")

    novos = 0
    usados = []
    for item in lista:
        id_doc = str(item.get("id"))
        situacao = item.get("situacaoDocumento") or "A"
        doc = conhecidos.get(id_doc)
        if doc is None:
            if id_doc not in lidos:
                continue
            doc = {"id": id_doc, "versao": item.get("versao") or 1, "eventos": lidos[id_doc]}
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
    if erro is not None:
        # O que foi baixado fica guardado; o período NÃO conta como coberto.
        cache.gravar(nome, {"baixado_em": salvo.get("baixado_em"), "janela": janela,
                            "docs": conhecidos})
        raise erro
    cache.gravar(nome, {"baixado_em": datetime.now().isoformat(timespec="seconds"),
                        "janela": nova, "docs": conhecidos})
    return usados, novos


# =========================================================================== #
#  Função principal                                                            #
# =========================================================================== #
def _motivo_12_meses(motivo, isins, complemento):
    """Complemento do aviso 'só há proventos da B3 a partir de...'."""
    if motivo == "busca_falhou":
        return (" (o Fundos.NET não respondeu ao procurar o CNPJ deste fundo; "
                "a próxima importação tenta de novo)")
    if motivo == "nao_achado":
        return " (o CNPJ não está na tabela e não foi achado no Fundos.NET — ver README)"
    if any("CTF" in i for i in isins):
        if _nome_normal((complemento or {}).get("tradingName")).split(" ")[0] in PREFIXOS_FNET:
            return " (o CNPJ não está na tabela; nova busca em até 30 dias — ver README)"
        return " (FI-Infra, FIP e ETFs não têm histórico de rendimentos no Fundos.NET — ver README)"
    return ""


def _isins_do_papel(bruto, ticker):
    """ISINs que o papel teve no COTAHIST baixado."""
    if bruto is None or "codisi" not in bruto.columns:
        return set()
    sub = bruto.loc[bruto["codneg"].astype(str).str.strip() == ticker, "codisi"]
    return {str(i).strip().upper() for i in sub.unique() if str(i).strip() not in ("", "nan")}


def _texto_espera(pendentes, futuros, andamento):
    """'aguardando HGLG11 12/37 avisos, PETR' — o que está em curso agora."""
    itens = []
    for fut in pendentes:
        chave = futuros[fut]
        feito = (andamento or {}).get(chave)
        if feito and feito[1]:
            itens.append(f"{chave[1]} {feito[0]}/{feito[1]} avisos")
        elif fut.running():
            itens.append(chave[1])
    if not itens:
        return "..."
    itens.sort()
    return "aguardando " + ", ".join(itens[:4]) + (" ..." if len(itens) > 4 else "")


def _executar(tarefas, progress, rotulo, andamento=None):
    """
    Roda os downloads em paralelo; falha de um não derruba os outros.

    Enquanto espera, devolve o controle à janela a cada ~0,3 s (pela função
    de progresso), dizendo o que ainda está pendente — antes ela ficava
    congelada no último papel CONCLUÍDO, o que parecia demora nele.
    """
    resultado = {}
    if not tarefas:
        return resultado
    total = len(tarefas)
    if progress is not None:
        progress(0, total, rotulo)
    pool = ThreadPoolExecutor(PARALELO)
    try:
        futuros = {pool.submit(f): chave for chave, f in tarefas.items()}
        pendentes, feitos = set(futuros), 0
        while pendentes:
            prontos, pendentes = wait(pendentes, timeout=0.3, return_when=FIRST_COMPLETED)
            for fut in prontos:
                chave = futuros[fut]
                feitos += 1
                try:
                    resultado[chave] = fut.result()
                except FonteIndisponivel as e:
                    resultado[chave] = e
                except Exception as e:       # resposta fora do formato esperado
                    resultado[chave] = FonteIndisponivel(f"{type(e).__name__}: {e}")
                print(f"  Eventos corporativos: {chave[1]} "
                      f"({'falhou' if isinstance(resultado[chave], Exception) else 'ok'})")
            if progress is not None and pendentes:
                progress(min(feitos, total - 1), total,
                         _texto_espera(pendentes, futuros, andamento))
    finally:
        pool.shutdown(wait=True)
    return resultado


def ajustar_eventos(wide, bruto, proventos=True, pasta_cache=None,
                    tabela_fii_extra=None, progress=None, rede=None,
                    site_nao_oficial=None):
    """
    Ajusta as séries de preço da B3 por eventos corporativos.

    wide      : DataFrame Data × papéis (o que a importação da B3 monta).
    bruto     : DataFrame do COTAHIST devolvido por baixar_periodo (precisa
                das colunas codneg, data, codisi, dismes, preabe, preult,
                quatot e fatcot).
    proventos : True ajusta também dividendos, JCP e rendimentos (retorno
                total); False só desdobramentos, grupamentos e bonificações.
    site_nao_oficial : endereço de um site (ex.: SITE_PADRAO) para completar
                o histórico de proventos que as fontes oficiais não têm, ou
                vários separados por ";" (tentados em ordem). Só é usado
                depois de conferido com a B3. None = não usar.

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
           "papeis": {}, "falhas": {}}

    andamento = {}                     # FII -> [avisos baixados, avisos a baixar]

    # 1ª fase — downloads, vários ao mesmo tempo: dados da B3 de cada empresa
    # e, para os FIIs, os avisos do Fundos.NET. O que já está no cache volta
    # na hora. A barra de progresso avança a cada um que termina.
    tarefas = {}
    for ticker in papeis:
        empresa, _ = empresa_e_classe(ticker)
        if not empresa:
            continue
        eh_fii = ticker in tabela_fii
        if ("b3", empresa) not in tarefas:
            tarefas[("b3", empresa)] = partial(_dados_b3, rede, cache, empresa, fim,
                                               proventos and not eh_fii)
        if proventos and eh_fii:
            tarefas[("fnet", ticker)] = partial(_dados_fnet, rede, cache, tabela_fii[ticker],
                                                inicio, fim, fim, andamento, ("fnet", ticker))
    t0 = time.time()
    baixado = _executar(tarefas, progress, "consultando a B3", andamento)
    notas = {}                         # informações (não são problemas)
    motivo_sem_historico = {}          # papel -> por que ficou só com 12 meses

    # 1ª fase (b) — FII que não está na tabela de CNPJs: o programa procura o
    # CNPJ no Fundos.NET, confere e guarda no fii_cnpj.csv do usuário. Quem
    # não for achado só é procurado de novo depois de 30 dias.
    if proventos:
        procurados = {}
        for ticker in papeis:
            empresa, _ = empresa_e_classe(ticker)
            res = baixado.get(("b3", empresa))
            if ticker in tabela_fii or not res or isinstance(res, Exception) or not res[0]:
                continue
            isins = _isins_do_papel(bruto, ticker)
            comp = res[0]
            nome = comp.get("tradingName") or ""
            # Só FII, Fiagro e FIDC publicam no Fundos.NET; FI-Infra, FIP e ETFs
            # não estão lá, e procurá-los só pesaria a consulta.
            if not (any("CTF" in i for i in isins)
                    and _nome_normal(nome).split(" ")[0] in PREFIXOS_FNET):
                continue
            tentativa = cache.ler(f"sem_cnpj_{ticker}") or {}
            try:
                recente = (datetime.now() - datetime.fromisoformat(tentativa.get("em", ""))).days < 30
            except ValueError:
                recente = False
            if not recente:
                procurados[ticker] = (nome, isins)
        if procurados:
            if progress is not None:
                progress(0, 1, "procurando o CNPJ de FII novo")
            achados, completo = descobrir_cnpjs_fii(rede, procurados)
            novas = {}
            for ticker in procurados:
                if ticker in achados:
                    cnpj, nome_fundo = achados[ticker]
                    tabela_fii[ticker] = cnpj
                    gravado = gravar_cnpj_extra(tabela_fii_extra, ticker, cnpj)
                    notas.setdefault(ticker, []).append(
                        f"Fundo fora da tabela: CNPJ {cnpj} ({nome_fundo or 'nome não informado'}) "
                        f"encontrado no Fundos.NET e conferido"
                        + (f" — guardado para as próximas vezes em: {os.path.abspath(tabela_fii_extra)}"
                           if gravado else
                           " — NÃO foi possível guardá-lo (pasta sem permissão de escrita?)"))
                    novas[("fnet", ticker)] = partial(_dados_fnet, rede, cache, cnpj, inicio, fim,
                                                      fim, andamento, ("fnet", ticker))
                elif completo:
                    cache.gravar(f"sem_cnpj_{ticker}", {"em": datetime.now().isoformat(timespec="seconds")})
                    motivo_sem_historico[ticker] = "nao_achado"
                else:
                    # Falha de conexão não prova que o fundo não existe: nada é
                    # gravado, e a próxima importação procura de novo.
                    motivo_sem_historico[ticker] = "busca_falhou"
            baixado.update(_executar(novas, progress, "Fundos.NET", andamento))
    # 1ª fase (c) — site não oficial, só para quem ficaria com os ~12 meses
    # da B3 (FI-Infra, FIP...). Ações (histórico da B3) e fundos com
    # Fundos.NET não são consultados.
    sites = lista_sites(site_nao_oficial)
    if proventos and sites:
        tarefas_site = {}
        for ticker in papeis:
            empresa, _ = empresa_e_classe(ticker)
            res = baixado.get(("b3", empresa))
            if not empresa or not res or isinstance(res, Exception):
                continue
            comp, hist, _ = res
            fnet = baixado.get(("fnet", ticker))
            if hist or (ticker in tabela_fii and fnet is not None
                        and not isinstance(fnet, Exception)):
                continue
            recentes = _bloco_recente_b3(comp, _isins_do_papel(bruto, ticker))
            if recentes and min(recentes) > inicio:
                tarefas_site[("site", ticker)] = partial(
                    _buscar_sites, rede, cache, sites, ticker, inicio, fim, recentes,
                    _cotahist_do_papel(bruto, ticker))
        baixado.update(_executar(tarefas_site, progress, "site não oficial", andamento))

    if hasattr(rede, "fechar"):
        rede.fechar()
    print(f"  Eventos corporativos: consultas concluídas em {time.time() - t0:.0f} s")

    # 2ª fase — cálculo, papel por papel (sem rede)
    for ticker in papeis:
        avisos = []
        info = {"eventos": [], "avisos": avisos, "notas": notas.setdefault(ticker, []),
                "ret_antes": None, "ret_depois": None}
        rel["papeis"][ticker] = info
        serie = pd.to_numeric(saida[ticker], errors="coerce")

        papel = _cotahist_do_papel(bruto, ticker)
        if papel is None:
            rel["falhas"][ticker] = "o papel não está no COTAHIST baixado"
            continue
        isins = _isins_do_papel(bruto, ticker)
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
            resultado = baixado.get(("b3", empresa))
            if isinstance(resultado, Exception):
                if ticker not in tabela_fii:
                    rel["falhas"][ticker] = (f"a B3 não respondeu ({resultado}) — série "
                                             f"mantida SEM ajuste")
                    continue
                # Fundo com CNPJ conhecido: os rendimentos vêm do Fundos.NET de
                # qualquer jeito; sem a B3, desdobramentos só pelo COTAHIST.
                avisos.append(f"a B3 não respondeu ({resultado}): rendimentos só do "
                              f"Fundos.NET e desdobramentos só pela detecção no COTAHIST")
                resultado = (None, None, "falhou")
            complemento, historico, situacao_b3 = resultado
            if complemento is None and situacao_b3 != "falhou":
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
                resultado = baixado.get(("fnet", ticker))
                if isinstance(resultado, Exception):
                    avisos.append(f"o Fundos.NET não respondeu ({resultado}): só os "
                                  f"rendimentos dos últimos ~12 meses (B3) foram ajustados")
                elif resultado is not None:
                    docs = resultado[0]
                eventos += proventos_fii(complemento, docs, ticker, isins, papel,
                                         inicio, fim, avisos)
            else:
                eventos += proventos_da_b3(historico, complemento, classe, isins,
                                           papel, inicio, fim, avisos)
                if not historico and (complemento or {}).get("cashDividends"):
                    recentes = _bloco_recente_b3(complemento, isins)
                    if recentes and min(recentes) > inicio:
                        resultado_site = baixado.get(("site", ticker))
                        usado, msg_site = False, ""
                        if isinstance(resultado_site, Exception):
                            resultado_site = [(sites[0], resultado_site)]
                        if resultado_site:
                            evs_site, msg_site, usado = _proventos_dos_sites(
                                resultado_site, recentes, papel, inicio)
                            eventos += evs_site
                        if usado:
                            info["notas"].append(msg_site)
                        else:
                            avisos.append(
                                f"só há proventos da B3 a partir de {_fmt(min(recentes))}; "
                                f"os anteriores NÃO foram ajustados"
                                + _motivo_12_meses(motivo_sem_historico.get(ticker), isins,
                                                   complemento)
                                + (f"; site não oficial: {msg_site}" if msg_site else ""))

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
        for a in info.get("notas", []):
            linhas.append(f"   ℹ️ {a}")
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
#  (com --descobrir, FIIs têm o CNPJ procurado no Fundos.NET, sem a tabela)    #
# =========================================================================== #
if __name__ == "__main__":
    import sys
    # --descobrir: ignora a tabela pronta e procura o CNPJ de cada FII no
    # Fundos.NET, como o programa faz com um FII que não está nela.
    descobrir = "--descobrir" in sys.argv[1:]
    papeis = [p.upper() for p in sys.argv[1:] if not p.startswith("--")] or ["MGLU3"]
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
        cnpj = "" if descobrir else TABELA_FII_PRONTA.get(t, ("",))[0]
        if not cnpj and _nome_normal(comp["tradingName"]).startswith(("FII", "FIAGRO", "FIDC")):
            print("  FII fora da tabela — procurando o CNPJ no Fundos.NET...")
            try:
                achado, _ = descobrir_cnpjs_fii(rede, {t: (comp["tradingName"], set())})
            except FonteIndisponivel as e:
                achado = {}
                print(f"  Fundos.NET não respondeu: {e}")
            if t in achado:
                cnpj = achado[t][0]
                tab = TABELA_FII_PRONTA.get(t, ("",))[0]
                print(f"  encontrado e conferido: CNPJ {cnpj} ({achado[t][1]})"
                      + (f" — igual ao da tabela" if cnpj == tab else
                         f" — DIFERENTE da tabela ({tab})" if tab else ""))
            else:
                print("  não encontrado: só os rendimentos dos últimos ~12 meses seriam ajustados")
                continue
        if cnpj:
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
