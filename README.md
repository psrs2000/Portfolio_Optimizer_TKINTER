**Otimizador de Portfólio**

Versão Desktop - Manual do Usuário

Documento de referência completo para operação do sistema de

otimização de portfólio com walk-forward e ranking automático de ativos.

Versão 3.0 • 2026

# 1\. Introdução

O Otimizador de Portfólio é uma aplicação desktop desenvolvida em Python com interface **PyQt5** (`desktop_app_qt.py`), apoiada no motor de cálculo `optimizer.py`. Seu objetivo é auxiliar analistas e gestores a construir carteiras de ativos financeiros de forma quantitativa, combinando técnicas de otimização matemática, análise de risco e validação fora da amostra (out-of-sample).

⚠️ **Sobre a versão Tkinter:** o projeto nasceu em Tkinter (`desktop_app_FULL.py`) e esse arquivo continua no repositório por referência histórica, mas **não é mais mantido**. Ele não possui os recursos introduzidos a partir da versão 2.1 (objetivos Under Water e Sharpe do Excesso, meta absoluta, tabela ordenável, coluna Meta%, degradação graciosa, exportação numérica, entre outros). **Use sempre a versão PyQt5.**

## 1.1 Principais Funcionalidades

- Carregamento de dados históricos de preços via planilha Excel **ou busca online em várias fontes** (Yahoo Finance, B3/COTAHIST, Excel/STOCKHISTORY e CVM/fundos de investimento).
- Configuração de janelas temporais separadas para otimização e validação.
- **Oito objetivos de otimização**, incluindo Sharpe, Sortino, Under Water, linearidade e dois objetivos aplicados ao excesso sobre a referência.
- Restrições globais e individuais de peso por ativo, com importação via arquivo Excel/CSV.
- **Meta de retorno opcional em dois modos:** relativa à referência ou absoluta (% ao ano).
- Suporte a posições vendidas (short selling / hedge), inclusive na Auto-Otimização.
- Sistema de ranking automático de ativos com pesos personalizáveis.
- Resultados in-sample e out-of-sample comparados lado a lado.
- Tabelas de retornos mensais com cálculo de excesso sobre a referência.
- Auto-Otimização com walk-forward sobre múltiplas combinações de parâmetros.
- **Tabela de resultados ordenável** por qualquer coluna, com ordenação numérica correta.
- Solver com multi-start automático e **degradação graciosa** (entrega a melhor carteira viável em vez de abortar).
- **Exportação para CSV e Excel com valores numéricos de verdade**, prontos para cálculo.

## 1.2 Requisitos do Sistema

| **Componente**         | **Requisito**                                |
| ---------------------- | -------------------------------------------- |
| Sistema Operacional    | Windows 10/11, Linux ou macOS                |
| Python                 | 3.8 ou superior (recomendado 3.10+)          |
| Bibliotecas            | PyQt5, pandas, numpy, scipy, matplotlib, openpyxl |
| Opcional               | yfinance (Yahoo Finance), requests (B3 e CVM — normalmente já presente), xlwings + Excel 365/Windows (importação via Excel) |
| Módulo adicional       | optimizer.py (incluso no projeto)            |
| Resolução de tela      | Mínimo 1400 × 900 pixels (recomendado 2100+ de largura para ver a tabela da Auto-Otimização inteira) |
| Formato de dados       | Planilha Excel (.xlsx ou .xls) e CSV         |

## 1.3 Como Iniciar o Programa

- Abra o terminal (Prompt de Comando ou PowerShell no Windows).
- Navegue até a pasta onde os arquivos do projeto estão localizados.
- Execute: `python desktop_app_qt.py`
- A janela principal do programa será exibida.

💡 O arquivo `optimizer.py` precisa estar na mesma pasta que `desktop_app_qt.py` para o programa funcionar corretamente.

⚠️ Os módulos das fontes de dados (`cvm_fundos.py`, `b3_series_wide_com_limpeza.py`, `b3_excel_rendafixa.py`) também precisam estar **na mesma pasta**. Sem eles o aplicativo abre normalmente, mas o botão da fonte correspondente avisa o que está faltando.

## 1.4 Gerar o Executável (Windows)

Para distribuir o programa a quem não tem Python instalado, dê **duplo clique em `Construir executavel.bat`**. Ele cuida de tudo: localiza o Python, cria um ambiente isolado (`.venv`), instala as dependências e chama o PyInstaller.

O resultado sai em **`dist\Otimizador de Portfolio\`**.

⚠️ **O programa é a PASTA inteira, não apenas o `.exe`.** Para levar a outro computador, copie ou compacte a pasta completa. Dentro dela, o arquivo que abre o programa é `Otimizador de Portfolio.exe`.

Duas escolhas feitas na receita de construção (`desktop_app_qt.spec`), e o porquê:

| **Escolha** | **Motivo** |
| ----------- | ---------- |
| **Pasta** (e não arquivo único) | O executável único descompacta ~200 MB numa pasta temporária a **cada** execução, deixando toda abertura lenta. Em pasta esse custo não existe. |
| **Console ligado** | O programa imprime o andamento da auto-otimização (steps, composição da carteira, avisos do solver). Escondendo o console esses logs se perdem. Para preferir a janela limpa, troque `console=True` por `False` no `.spec`. |

💡 **A primeira abertura demora mais** — o Windows está lendo e verificando os arquivos pela primeira vez (o antivírus escaneia cada DLL nova). As aberturas seguintes são rápidas. Se incomodar, ajuda: manter a pasta fora do OneDrive e adicioná-la às exclusões do Windows Defender.

💡 As fontes opcionais (`yfinance` e `xlwings`) são instaladas **em separado** pelo `.bat`, sem interromper a construção se alguma falhar — o aplicativo funciona sem elas.

# 2\. Estrutura da Interface

A interface é organizada em 8 abas (tabs) na parte superior da janela. O fluxo de trabalho recomendado segue a ordem das abas da esquerda para a direita.

| **Aba**             | **Função**                                                                |
| ------------------- | ------------------------------------------------------------------------- |
| 📁 Dados            | Carregar planilha Excel, configurar janelas temporais e selecionar ativos |
| ⚙️ Configuração     | Definir objetivo de otimização, limites de peso, taxa de referência e meta de retorno |
| 🔧 Avançado         | Configurar restrições individuais de peso por ativo                       |
| 🔄 Short/Hedge      | Definir posições vendidas com pesos negativos                             |
| 🏆 Ranking          | Calcular e aplicar ranking automático de ativos                           |
| 📈 Resultados       | Visualizar métricas in-sample, out-of-sample e composição do portfólio    |
| 📅 Retornos Mensais | Tabela de retornos mês a mês e excesso sobre a referência                 |
| 🤖 Auto-Otimização  | Walk-forward sobre múltiplas combinações de parâmetros automaticamente    |

# 3\. Aba Dados - Carregamento e Configuração

Esta é a primeira aba a ser utilizada. Todo o fluxo começa aqui: carregue a planilha, configure as datas e selecione os ativos antes de avançar para as demais abas.

## 3.1 Formato da Planilha Excel

A planilha deve seguir o seguinte padrão:

- **Primeira coluna:** datas no formato DD/MM/AAAA (a coluna pode ter qualquer nome; o sistema a renomeia automaticamente para 'Data').
- **Segunda coluna (opcional):** taxa de referência ou benchmark (CDI, SELIC, IBOV etc.). O sistema detecta automaticamente se o nome da coluna contiver as palavras: taxa, livre, risco, ibov, ref, cdi ou selic.
- **Demais colunas:** séries de preços dos ativos, uma por coluna, com o nome do ativo no cabeçalho.

💡 Os dados devem ser preços (cotas), não retornos. O sistema calcula os retornos internamente via transformação para base zero.

## 3.2 Carregar Arquivo

- Clique no botão **📂 Carregar Planilha Excel**.
- Selecione o arquivo .xlsx ou .xls no diálogo que aparecer.
- O painel 'Informações do Arquivo' exibirá: nome do arquivo, número de linhas e colunas, período disponível (data início e data fim) e total de dias.
- Se uma taxa de referência for detectada automaticamente, ela aparecerá em verde no painel 'Taxa de Referência Detectada'. Caso contrário, um aviso em vermelho indicará que nenhuma taxa foi encontrada.

⚠️ Se a taxa de referência for detectada automaticamente, o campo de taxa manual na aba Configuração é desabilitado. Se não for detectada, o campo manual permanece disponível para entrada manual do valor acumulado no período.

## 3.2.1 Fontes Online (Yahoo, B3, Excel e CVM)

Além de carregar uma planilha, o programa busca cotações **direto da internet** por quatro fontes. Qualquer uma delas alimenta o programa exatamente como uma planilha carregada — mesmo fluxo daí em diante (detecção da taxa de referência, lista de ativos e janelas temporais). Todas entregam séries de preços (ou cotas, no caso dos fundos), e a transformação para base zero é feita internamente ao processar o período.

| **Fonte**            | **Botão**                          | **Melhor para**                                  | **Requisito**                         |
| -------------------- | ---------------------------------- | ------------------------------------------------ | ------------------------------------- |
| Yahoo Finance        | 🌐 Importar do Yahoo Finance       | Ações internacionais, cripto, uso rápido          | `yfinance`                            |
| B3 (COTAHIST)        | 🇧🇷 Importar da B3 (COTAHIST)      | Ações e ETFs brasileiros (fonte oficial)          | `requests`                            |
| Excel (STOCKHISTORY) | 📊 Importar via Excel (renda fixa) | ETFs de renda fixa que o COTAHIST não cobre       | Windows + Excel 365 + `xlwings`       |
| CVM (fundos)         | 🏦 Importar Fundos (CVM)           | Cotas diárias de fundos de investimento           | `requests`                            |

💡 As fontes da B3, do Excel e da CVM usam dados oficiais/institucionais, mais confiáveis que o Yahoo para o mercado brasileiro.

### Regras de limpeza (iguais nas quatro fontes)

Toda importação online passa pelas **mesmas três regras**, aplicadas **nesta ordem** sobre a matriz Data × Ativos:

| **Ordem** | **Regra**                                                                 |
| --------- | ------------------------------------------------------------------------- |
| 0         | Valor **zero** conta como "sem dado".                                     |
| 1         | Coluna **sem dado na primeira data** → o ativo é **excluído**.            |
| 2         | Coluna com mais de **k** registros consecutivos sem dado → **excluída**.  |
| 3         | Lacunas restantes → preenchidas com o **valor do dia anterior**.          |

O valor de **k** é o campo **🧹 Elimina após N dias sem dado** (padrão 10), presente nas três janelas de importação junto com o tipo de preço e o período.

⚠️ **A ordem importa:** as regras 1 e 2 avaliam os buracos **antes** do preenchimento; a regra 3 vem por último. Se o preenchimento viesse antes, não sobrariam buracos para as regras 1 e 2 analisarem.

💡 **Por que isso importa:** sem a regra 3, lacunas chegariam como vazio ao otimizador, que descarta a **linha inteira** quando qualquer ativo falta — ou seja, um único ativo com falha eliminaria aquela data para **todos** os demais. As exclusões efetuadas pelas regras 1 e 2 são informadas na mensagem ao final da importação.

### Importar do Yahoo Finance

Baixe cotações pelo botão **🌐 Importar do Yahoo Finance**. Na janela que abre:

- **📝 Símbolos dos Ativos:** um código por linha (ex.: `PETR4`, `VALE3`, `ITUB4`). Mínimo de 2.
- **💰 Preço** e **🧹 Elimina após N dias sem dado:** iguais aos das outras fontes (ver regras de limpeza acima).
- **🏷️ Tipo de ativo:** define o sufixo acrescentado automaticamente ao código.

| **Tipo**                 | **Comportamento**                                                         |
| ------------------------ | ------------------------------------------------------------------------- |
| Ações Brasileiras (.SA)  | Acrescenta `.SA` (ex.: `PETR4` → `PETR4.SA`).                             |
| Ações Americanas / ETFs / Criptomoedas | Usa o código como digitado (ex.: `MSFT`, `BTC-USD`).        |
| Códigos Livres do Yahoo  | Nenhum sufixo é acrescentado — digite exatamente como aparece no Yahoo.   |

- **🏛️ Ativo de Referência:** informe um benchmark (padrão `BOVA11`) e marque **Incluir**. Ele é baixado junto e vira a coluna de referência, renomeada para `Taxa_Ref_<CÓDIGO>` e posicionada como segunda coluna — é isso que faz a **detecção automática** reconhecê-la e habilitar os objetivos de excesso. Sugestões: `BOVA11` (Ibovespa), `LFTS11` (CDI), `SMAL11` (Small Caps), `IVV` (S&P 500).
- **📅 Período:** datas de início e fim da busca (padrão: últimos 3 anos).

Clique em **🚀 Buscar e Importar**. Uma barra de progresso mostra o andamento ativo a ativo.

💡 Códigos que já contenham ponto (ex.: `PETR4.SA`) são usados como digitados, mesmo no modo com sufixo — não vira `PETR4.SA.SA`.

⚠️ Séries com menos de 6 pregões no período são descartadas já na busca, e os símbolos sem dados são listados ao final; o que sobrar ainda passa pelas três regras de limpeza. Se o **ativo de referência** não sobreviver (não retornou ou foi excluído na limpeza), a importação continua sem ele e o programa avisa — nesse caso os objetivos que dependem da referência ficam indisponíveis.

⚠️ **Requer a biblioteca `yfinance`** (`pip install yfinance`). Sem ela o aplicativo funciona normalmente, apenas esse botão exibe um aviso explicando como instalar.

💡 Os dados vêm como **preços de fechamento**, exatamente o formato que o programa espera — a transformação para base zero continua sendo feita internamente ao processar o período.

### Importar da B3 (COTAHIST) — fontes nacionais

O botão **🇧🇷 Importar da B3 (COTAHIST)** baixa os arquivos anuais oficiais da B3 (mercado à vista) e monta a série de preços dos ativos pedidos. Por ser a fonte oficial da bolsa brasileira, é mais confiável que o Yahoo para ações e ETFs negociados na B3.

A janela é parecida com a do Yahoo, com alguns campos próprios:

- **📝 Símbolos:** os códigos exatamente como negociados na B3 (ex.: `PETR4`, `VALE3`, `BOVA11`).
- **💰 Preço:** Abertura, Máximo, Mínimo ou **Fechamento** (padrão).
- **🧹 Elimina após N dias sem dado:** regra de limpeza (padrão 10). Se um ativo ficar mais de N pregões seguidos sem cotação, é descartado; lacunas menores são preenchidas com o preço do dia anterior. Ativos sem cotação na primeira data também são descartados.
- **🏛️ Ativo de Referência** e **📅 Período:** iguais aos do Yahoo.

⚠️ O primeiro download de cada ano é **grande** (dezenas de MB) e pode levar de segundos a minutos — a janela pode parecer parada enquanto baixa cada ano. A barra de progresso avança a cada ano concluído.

⚠️ Requer a biblioteca **`requests`** (normalmente já instalada). Cobre bem ações e a maioria dos ETFs; para **ETFs de renda fixa** que a B3 não cobre bem, use a fonte via Excel abaixo.

### Importar via Excel (renda fixa) — fonte complementar

O botão **📊 Importar via Excel (renda fixa)** usa a função `STOCKHISTORY` do Excel (dados LSEG/Refinitiv) para buscar os ETFs de renda fixa que o COTAHIST não cobre bem (ex.: `FIXA11`, `IMAB11`, `B5P211`, `IRFM11`). Os campos são os mesmos da importação da B3.

⚠️ **Requisitos específicos:** Windows com **Excel 365** instalado e logado, e a biblioteca **`xlwings`** (`pip install xlwings`). É a única fonte que não roda em Linux/macOS. Sem esses requisitos, o botão abre normalmente mas a busca informa o que está faltando.

💡 **Fonte complementar, não substituta:** use a B3 como fonte principal e o Excel só para os códigos de renda fixa que faltarem. Não misture as duas fontes na mesma carteira — os preços têm origens diferentes (B3 vs LSEG).

### Importar Fundos da CVM

O botão **🏦 Importar Fundos (CVM)** traz as **cotas diárias de fundos de investimento** a partir dos dados abertos da CVM. Permite otimizar carteiras de fundos exatamente como se faz com ações — a cota é o "preço" do fundo.

Na janela:

- **📝 CNPJs dos Fundos:** um CNPJ por linha, **com ou sem pontuação** (`29.152.383/0001-03` ou `29152383000103`). Mínimo de 2.
- **📁 Pasta de cache:** onde os arquivos baixados ficam guardados. Se existir um **`CNPJ.csv`** nessa pasta, os CNPJs são carregados dele automaticamente.
- **🧹 Elimina após N dias sem dado** e **📅 Período:** iguais às outras fontes.
- **🏛️ Ativo de Referência:** diferente das demais — como o nome do fundo só é conhecido depois da busca, ao final aparece a **lista dos fundos obtidos** para você escolher qual será a referência. Um fundo *referenciado DI* costuma ser a melhor escolha.

O que é baixado automaticamente:

| **Arquivo**                    | **Origem**                                                        |
| ------------------------------ | ----------------------------------------------------------------- |
| Cadastro (nomes dos fundos)    | `.../FI/CAD/DADOS/cad_fi_hist.zip`                                |
| Informe diário, 2021 em diante | `.../FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_AAAAMM.zip` (mensal)   |
| Informe diário, antes de 2021  | `.../FI/DOC/INF_DIARIO/DADOS/HIST/inf_diario_fi_AAAA.zip` (anual) |

⚠️ **Os arquivos são grandes** — cada informe diário traz todos os fundos do país. A primeira busca de um período baixa e **guarda em cache**; as buscas seguintes reaproveitam o que já está lá. Um zip anual do histórico traz os 12 meses de uma vez, então basta um download por ano antigo.

💡 **As colunas recebem o nome do fundo** (denominação social vigente no cadastro), que costuma ser longo. É esse nome que aparece na lista de ativos, na composição da carteira e nos gráficos.

💡 O formato dos CSVs da CVM **muda conforme o ano** (nome da coluna de CNPJ, codificação, data em DD/MM/AAAA ou AAAA-MM-DD, decimal com vírgula ou ponto). Tudo isso é tratado automaticamente, e a comparação de CNPJ ignora a pontuação.

## 3.2.2 Baixar a Base Carregada

O botão **💾 Baixar Base de Dados Carregada** salva em disco a base **bruta** atualmente em memória — não importa a origem (planilha, Yahoo, B3 ou Excel). Útil para conferir os dados, ajustá-los à mão ou guardar uma cópia da série que você montou online.

- Fica **desabilitado** enquanto nenhuma base estiver carregada; habilita automaticamente após carregar/importar.
- Escolha **.xlsx** (Excel, com datas em DD/MM/AAAA, preços numéricos, cabeçalho em negrito e primeira linha congelada) ou **.csv** (separador `;` e decimal `,`, padrão que o Excel pt-BR abre direto).
- Grava exatamente `Data | (Taxa_Ref, se houver) | ativos...`, **sem** a transformação para base zero — ou seja, os preços originais, do jeito que o otimizador os recebe.

💡 Os preços são gravados com **precisão total** (sem arredondamento), para que o arquivo seja fiel ao dado usado nos cálculos. No Excel, a exibição fica limpa (2 casas) mas o valor exato é preservado na célula.

💡 Um bom uso: importe online (Yahoo/B3/Excel), baixe a base, ajuste o que precisar numa planilha e recarregue pelo botão **📂 Carregar Planilha Excel**.

## 3.3 Configurar Janelas Temporais

Após carregar o arquivo, configure as três datas críticas que definem os dois períodos de análise:

| **Data**                | **Descrição**                                                                                     |
| ----------------------- | ------------------------------------------------------------------------------------------------- |
| 📊 Início da Otimização | Data inicial dos dados usados para calibrar o portfólio.                                          |
| 🎯 Fim da Otimização    | Data final da janela de treinamento (in-sample).                                                  |
| 📈 Fim da Análise       | Data final do período de validação (out-of-sample). Só ativo se 'Usar validação' estiver marcado. |

Ao carregar o arquivo, o sistema preenche automaticamente as datas sugeridas usando a proporção de 70% para otimização e 30% para validação. Você pode ajustar livremente clicando nos campos de data.

O painel abaixo das datas exibe em tempo real a quantidade de dias de cada janela e o percentual que representam do período total.

💡 O checkbox '✅ Usar validação (forward test)' permite desabilitar a janela de validação. Nesse caso, o programa usará apenas o período de otimização em todas as análises.

- Após ajustar as datas, clique em **⚡ Processar Período Selecionado**.
- O sistema filtrará os dados brutos para os períodos configurados e aplicará a transformação para base zero.
- Uma mensagem de sucesso confirmará quantos dias e ativos estão disponíveis. Ativos com valor zero ou ausente no primeiro dia do período são automaticamente removidos.

## 3.4 Seleção de Ativos

O painel direito exibe a lista de todos os ativos disponíveis na planilha (excluindo a coluna de data e a taxa de referência, se detectada).

- **Seleção simples:** clique em um ativo.
- **Seleção múltipla:** Ctrl + clique para adicionar ativos à seleção.
- **Intervalo:** Shift + clique para selecionar um intervalo contínuo.
- **✅ Todos:** seleciona todos os ativos de uma vez.
- **❌ Limpar:** remove toda a seleção.

⚠️ É necessário selecionar no mínimo 2 ativos para executar a otimização.

O contador no rodapé do painel mostra quantos ativos estão selecionados em relação ao total disponível (ex.: 'Selecionados: 8/25').

# 4\. Aba Configuração - Parâmetros de Otimização

Nesta aba você define como o algoritmo deve buscar o portfólio ótimo: qual métrica maximizar (ou minimizar), os limites de participação de cada ativo e a taxa de referência utilizada nos cálculos de excesso de retorno.

## 4.1 Objetivo de Otimização

Selecione um dos objetivos disponíveis pelo botão de rádio:

| **Objetivo**                        | **Descrição**                                                                                                                          |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Maximizar Sharpe Ratio              | Maximiza o retorno excedente à taxa de referência por unidade de risco. Objetivo mais comum para carteiras balanceadas.                |
| Maximizar Sortino Ratio             | Semelhante ao Sharpe, mas penaliza apenas a volatilidade de queda (downside). Não pune oscilações de alta — útil quando a preocupação é o risco de perda.  |
| Minimizar Risco                     | Minimiza a volatilidade do portfólio independentemente do retorno. Ideal para perfis conservadores.                                    |
| Minimizar Under Water               | Minimiza o **total de perdas acumuladas** do período — a soma de todos os retornos diários negativos. É uma medida de risco **assimétrica**: pune apenas queda, nunca oscilação de alta (ao contrário da volatilidade). Combina especialmente bem com a Meta de Retorno. |
| Maximizar Inclinação/\[(1-R²)×Vol\] | Combina a inclinação com a qualidade da linearidade e a volatilidade. Penaliza ativos com retornos irregulares.                        |
| Maximizar Qualidade da Linearidade  | Maximiza o R² da regressão do retorno acumulado. Prioriza ativos com comportamento linear e previsível.                                |

### Objetivos com Taxa de Referência

Os dois objetivos abaixo aparecem em uma seção separada e só ficam disponíveis quando há taxa de referência. Ambos trabalham sobre a curva do **excesso** (carteira − referência):

| **Objetivo**                     | **Descrição**                                                                                                                        |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Maximizar Linearidade do Excesso | Maximiza `inclinação_excesso ÷ [(1 − R²_excesso) × vol_excesso]`. Premia uma curva de excesso **reta** (R² alto), ou seja, uma vantagem sobre a referência que cresce de forma regular. |
| Maximizar Sharpe do Excesso      | É a Linearidade do Excesso **sem o fator (1 − R²)**: maximiza `inclinação_excesso ÷ vol_excesso`. Premia o **risco-retorno** do excesso sem exigir linearidade. |

💡 O objetivo "Maximizar Inclinação" (isolado) foi **removido** na versão 3.0 por não apresentar vantagem prática sobre os demais critérios. O cálculo de inclinação usado na aba Ranking é independente e continua funcionando normalmente.

## 4.2 Limites de Peso Globais

Defina os limites de participação de cada ativo no portfólio usando os controles deslizantes:

- **Peso mínimo por ativo (%):** participação mínima que qualquer ativo selecionado deve ter. Valores típicos: 0% a 5%. Use 0% para permitir que o otimizador exclua ativos.
- **Peso máximo por ativo (%):** participação máxima de qualquer ativo. Limita a concentração. Valores típicos: 15% a 30%.

💡 Os pesos são sempre positivos e somam 100% para posições long. Se houver posições short configuradas, os pesos dos ativos long ainda somam 100% antes do ajuste pelas posições vendidas.

## 4.3 Taxa de Referência

A taxa de referência é usada para calcular o Sharpe Ratio e o excesso de retorno.

- **Detecção automática:** se a planilha contiver uma coluna de benchmark, o campo de taxa manual é desabilitado e a taxa é extraída automaticamente dos dados.
- **Taxa manual:** quando não houver coluna de benchmark, informe o valor acumulado no período de otimização (ex.: para 12% ao ano em um período de 2 anos, informe 25.44, que corresponde a (1,12)² − 1 ≈ 25,44%).

## 4.4 Meta de Retorno (Opcional)

A meta de retorno permite exigir um retorno mínimo do portfólio, combinando essa exigência com o objetivo escolhido acima. Na prática, o otimizador busca **atingir a meta com o menor risco possível** — o ponto ideal entre "maximizar retorno" e "minimizar risco".

Marque **'Exigir meta de retorno mínima'** e escolha um dos dois modos:

| **Modo**     | **Como o alvo é calculado**                                    | **Quando usar**                                                        |
| ------------ | -------------------------------------------------------------- | ---------------------------------------------------------------------- |
| **Relativa** | `Referência × (1 + Meta ÷ 100)` no período. Ex.: referência 12% e meta 5% → alvo **12,6%**. | Quando o que importa é bater a referência por uma margem ("quero 30% acima do CDI"). Acompanha automaticamente a referência de cada step. |
| **Absoluta** | `(1 + Meta ÷ 100)^(pregões ÷ 252) − 1`. Ex.: 15% ao ano em 126 pregões → alvo **7,24%** no período. | Quando você pensa em retorno-alvo próprio ("quero 15% ao ano") ou **quando não há taxa de referência**. |

- O otimizador maximiza o objetivo escolhido garantindo **pelo menos** esse retorno acumulado no período.
- Se a meta for **inatingível** com os ativos e limites atuais, o sistema não falha: retorna a carteira de **maior retorno possível** e avisa que a meta não foi atingida.

⚠️ **A meta relativa exige referência maior que zero.** Sem referência, o alvo vira `0 × (1 + Meta) = 0` e a restrição não exige nada. É justamente esse buraco que a **meta absoluta** preenche — ela funciona independentemente da referência.

⚠️ **A meta absoluta é absoluta, não "acima da referência".** Com meta absoluta de 30% e referência de 19% ao ano, o alvo é **30% ao ano** (e não 49%). Se você quer "x% acima da referência", use o modo **relativa**.

💡 **Meta absoluta e os objetivos do Excesso são independentes.** Nos objetivos "Linearidade do Excesso" e "Sharpe do Excesso", o *objetivo* trabalha sobre o excesso (carteira − referência), enquanto a *meta* é uma restrição sobre o retorno **total**. A combinação significa: "entre as carteiras que rendem pelo menos X ao ano, escolha a de melhor excesso sobre a referência". Como esses objetivos costumam superar bastante o alvo, é comum a meta absoluta ficar folgada.

💡 A conversão anual→período é exata e usa a mesma convenção do otimizador (252 pregões): exigir o alvo equivale a exigir `retorno anualizado ≥ meta`. A mensagem de conclusão informa o alvo, o retorno obtido no período e, no modo absoluto, também o retorno anualizado.

## 4.5 Executar a Otimização

**Clique em 🚀 OTIMIZAR PORTFÓLIO** para iniciar o processo. Uma janela de progresso será exibida enquanto o algoritmo executa. Ao concluir, o programa navegará automaticamente para a aba Resultados.

💡 Se o solver não convergir plenamente mas encontrar uma carteira viável, o programa exibe **"Otimização concluída com ressalvas"** (aviso, não erro) e preenche os resultados normalmente. Ver a seção 12.7 — Degradação Graciosa.

# 5\. Aba Avançado - Restrições Individuais

Esta aba permite definir limites de peso específicos para ativos individuais, sobrescrevendo os limites globais configurados na aba Configuração para aqueles ativos específicos.

## 5.1 Habilitar Restrições Individuais

- Marque o checkbox 'Habilitar limites específicos para ativos selecionados'.
- Clique em **📋 Configurar Restrições Individuais** para abrir a janela de configuração.

## 5.1.1 Importar Restrições de Arquivo (Excel/CSV)

Em vez de digitar os limites manualmente, você pode importá-los de uma planilha com o botão **📂 Importar Restrições (Excel/CSV)**. É especialmente útil quando alguém já lhe entrega os pesos de uma carteira pronta.

Formatos aceitos (nomes de coluna flexíveis, sem diferenciar maiúsculas/minúsculas):

- **`Ativo, Min, Max`** — define faixas de mínimo e máximo por ativo.
- **`Ativo, Peso`** — fixa mínimo = máximo = peso. **Quando os pesos somam 100%, o otimizador é forçado exatamente àquela composição — o software passa a atuar como um analisador do portfólio informado.**

Detalhes da leitura:

- Os valores são interpretados em **percentual** (ex.: `30` = 30%); se todos forem ≤ 1, são tratados como fração (ex.: `0.30` = 30%).
- Aceita CSV com separador `,`, `;` ou tabulação, e vírgula decimal (ex.: `30,5`).
- Ao importar, o sistema **seleciona automaticamente** na aba Dados exatamente os ativos do arquivo que existem nos dados carregados, **ativa** as restrições individuais e preenche o resumo. Ativos do arquivo que não existirem nos dados são reportados e ignorados.

💡 Carregue os dados (aba Dados) antes de importar, pois o sistema casa os ativos do arquivo com os ativos disponíveis na planilha carregada.

## 5.2 Janela de Configuração

A janela exibe todos os ativos selecionados na aba Dados. Para cada ativo:

- **Marque o checkbox 'Usar limites específicos':** ativa os campos de mínimo e máximo para aquele ativo.
- **Mín (%):** peso mínimo individual (pode ser diferente do global).
- **Máx (%):** peso máximo individual.

Ferramentas de ação rápida disponíveis na janela:

- **Buscar:** filtra a lista de ativos por nome em tempo real.
- **Aplicar Globais:** copia os limites globais para todos os ativos marcados.
- **Limpar Todos:** desmarca todas as restrições individuais.
- **Lote - Mín / Máx + Aplicar aos Selecionados:** define um valor de mínimo e máximo em lote para todos os ativos marcados.

- Após configurar, clique em **✅ Aplicar Configuração**. Um resumo das restrições configuradas será exibido na aba Avançado.

💡 As restrições individuais têm prioridade sobre os limites globais. Se um ativo tem restrição individual definida, os valores globais são ignorados para ele.

# 6\. Aba Short/Hedge - Posições Vendidas

Esta aba permite incluir posições vendidas (short selling) no portfólio, úteis para estratégias de hedge ou para explorar movimentos de queda em ativos específicos.

## 6.1 Habilitar Posições Short

- Marque o checkbox 'Habilitar posições short/hedge (venda a descoberto)'.
- Clique em **📋 Selecionar Ativos para Short** para abrir a janela de seleção.

💡 Os ativos disponíveis para short são aqueles que NÃO estão selecionados como ativos principais na aba Dados. Portanto, é necessário ter selecionado os ativos long antes de configurar os shorts.

## 6.2 Janela de Seleção de Ativos Short

A janela lista todos os ativos disponíveis para posições vendidas. Para cada ativo:

- **Marque o checkbox:** inclui o ativo como posição short.
- **Peso (%):** informe o peso em percentual NEGATIVO (ex.: -10 para uma posição short de 10%). O sistema valida automaticamente que o valor seja negativo.

Ferramentas disponíveis:

- **Buscar:** filtra ativos por nome.
- **Selecionar Todos / Limpar Todos:** ações em lote.
- **Peso padrão + Aplicar aos Selecionados:** define um peso padrão para todos os ativos marcados de uma vez.

⚠️ O peso dos ativos short deve obrigatoriamente ser NEGATIVO. O sistema rejeitará a configuração se qualquer peso for zero ou positivo.

## 6.3 Comportamento na Otimização

Quando há posições short configuradas:

- Os ativos short são incluídos no otimizador com seus pesos fixos (conforme configurado).
- O otimizador distribui os 100% restantes entre os ativos long selecionados.
- Os pesos negativos aparecem na composição do portfólio identificados como 'SHORT'.
- O cálculo de 'Peso Atual' na tabela de composição considera apenas o valor das posições long para normalização.

# 7\. Aba Ranking - Classificação de Ativos

O sistema de ranking calcula um índice de qualidade para cada ativo com base em três dimensões: tendência (inclinação), estabilidade (desvio padrão) e correlação com a referência. Isso permite selecionar automaticamente os melhores ativos para a otimização.

## 7.1 Metodologia do Ranking

O cálculo ocorre em 4 passos internos:

- **Diferença diária:** para cada ativo, calcula-se a diferença entre o retorno diário do ativo e o retorno da referência (ativo − referência, dia a dia).
- **Integral acumulada:** soma acumulada (cumsum) das diferenças diárias. Representa a evolução do desempenho relativo ao longo do tempo.
- **Parâmetros:** regressão linear da integral acumulada (slope = inclinação, R² = qualidade) e desvio padrão das diferenças diárias. A correlação é calculada entre a integral acumulada do ativo e a da referência.
- **Índice bruto e normalização:** os três componentes são normalizados e combinados com pesos configuráveis. O resultado final é normalizado de 0 a 1.

Fórmula do índice:

**Índice = \[P_inc × Inclinação_norm + P_desv × (1 − Desvio_norm) + P_cor × Correlação\] ÷ (P_inc + P_desv + P_cor)**

## 7.2 Configurar e Calcular

- Marque o checkbox '🤖 Ativar ranking automático de ativos'. O painel de configuração aparecerá.
- Ajuste os pesos dos três componentes com os controles deslizantes (valores entre 0 e 1):
  - **📈 Peso Inclinação:** importância da tendência de alta relativa à referência. Maior peso favorece ativos com retorno consistentemente superior ao benchmark.
  - **📊 Peso Estabilidade:** importância da baixa volatilidade relativa. Maior peso favorece ativos que superam a referência de forma estável, sem grandes oscilações.
  - **🎯 Peso Correlação:** importância da correlação com a referência. Valores negativos de correlação podem indicar ativos com potencial de hedge.
- Clique em **🔄 Calcular Ranking**. O resultado aparece na tabela com até 20 ativos exibidos.

## 7.3 Tabela de Resultados

| **Coluna** | **Descrição**                                                             |
| ---------- | ------------------------------------------------------------------------- |
| Posição    | Classificação do ativo (1 = melhor).                                      |
| Ativo      | Nome do ativo conforme cabeçalho da planilha.                             |
| Índice     | Score normalizado entre 0 e 1 (1 = melhor desempenho relativo).           |
| Inclinação | Inclinação normalizada da regressão linear da integral acumulada.         |
| R²         | Coeficiente de determinação da regressão (qualidade da tendência linear). |
| Correlação | Correlação entre as integrais acumuladas do ativo e da referência.        |
| Desvio     | Desvio padrão normalizado das diferenças diárias ativo−referência.        |

## 7.4 Seleção Automática por Score

Abaixo da tabela, defina um intervalo de score para selecionar ativos automaticamente:

- **Score mínimo:** limiar inferior do índice (ex.: 0.70 para selecionar apenas ativos acima de 70% do máximo).
- **Score máximo:** limiar superior (geralmente 1.0 para incluir os melhores).

- Clique em **✅ Selecionar Ativos por Score**. O programa selecionará automaticamente na listbox da aba Dados apenas os ativos dentro do intervalo definido e navegará para a aba Configuração.

💡 A seleção por score respeita as configurações de short selling e restrições individuais já definidas. Essas configurações são preservadas mesmo após a atualização da seleção de ativos.

# 8\. Aba Resultados - Análise do Portfólio

Após a otimização, esta aba exibe um painel completo com três colunas de métricas lado a lado e a composição do portfólio com o gráfico de evolução.

## 8.1 Coluna IN-SAMPLE (Otimização)

Métricas calculadas sobre o período de treinamento (janela de otimização):

| **Métrica**             | **Descrição**                                                         |
| ----------------------- | --------------------------------------------------------------------- |
| Retorno Total (%)       | Retorno acumulado do portfólio no período de otimização em base zero. |
| Retorno Anualizado (%)  | Retorno total anualizado pela fórmula: (1 + R)^(365/dias) − 1.        |
| Sharpe Ratio            | Excesso de retorno anualizado dividido pela volatilidade anualizada.  |
| Volatilidade (%)        | Desvio padrão anualizado dos retornos diários (×√252).                |
| VaR 95% Diário          | Value at Risk: perda máxima esperada em 95% dos dias (paramétrico).   |
| CVaR 95% Diário         | Conditional VaR: perda média esperada além do VaR (tail risk).        |
| R²                      | Qualidade da linearidade do retorno acumulado (regressão linear).     |
| Taxa Ref Período (%)    | Retorno acumulado da taxa de referência no período.                   |
| Taxa Ref Anualizada (%) | Taxa de referência anualizada.                                        |
| Excesso Período (%)     | Retorno do portfólio menos o retorno da referência no período.        |
| Excesso Anualizado (%)  | Retorno anualizado do portfólio menos a taxa de referência anualizada. |
| Excesso/Ref (%)         | Excesso anualizado dividido pela taxa de referência anualizada: quanto o portfólio superou a referência em termos relativos (ex.: 50% = rendeu 50% a mais que a referência). |
| Dias                    | Número de dias corridos no período de otimização.                     |

## 8.2 Coluna OUT-OF-SAMPLE (Validação)

As mesmas métricas calculadas para o período de validação, usando os MESMOS pesos otimizados na fase de treinamento. Este é o teste real de generalização do portfólio.

💡 Se nenhuma janela de validação foi configurada (ou o período de validação é muito curto), esta coluna exibirá uma mensagem informativa. Configure uma data 'Fim da Análise' na aba Dados para ativar este painel.

## 8.3 Coluna COMPARAÇÃO

Exibe as diferenças entre out-of-sample e in-sample para as principais métricas:

- **Retorno Anual (diferença):** positivo indica que o portfólio performou melhor fora da amostra do que dentro.
- **Sharpe (diferença):** chave para avaliar overfitting. Diferenças grandes e negativas sugerem que o modelo foi super ajustado ao período de treino.
- **Volatilidade (diferença):** indica se o risco se manteve estável entre os períodos.
- **Resumo / Análise:** o sistema emite automaticamente um diagnóstico qualitativo (ex.: 'Boa generalização!' ou 'Cuidado: overfitting?').

## 8.4 Composição do Portfólio

A tabela abaixo das três colunas exibe todos os ativos com peso significativo (> 0,1%):

| **Coluna**       | **Descrição**                                                                         |
| ---------------- | ------------------------------------------------------------------------------------- |
| Ativo            | Nome do ativo.                                                                        |
| Peso Inicial (%) | Peso otimizado na data de início do portfólio.                                        |
| Peso Atual (%)   | Peso estimado ao final do período, considerando a valorização relativa de cada ativo. |
| Tipo             | LONG (posição comprada) ou SHORT (posição vendida).                                   |

As linhas de rodapé da tabela exibem o TOTAL LONG, TOTAL SHORT (quando aplicável) e a VARIAÇÃO do peso long entre o início e o fim do período.

## 8.5 Gráfico de Evolução

O gráfico à direita da composição exibe:

- **Linha azul:** retorno acumulado do portfólio.
- **Linha laranja (tracejada):** retorno acumulado da taxa de referência (quando disponível).
- **Linha verde (pontilhada):** excesso de retorno acumulado (portfólio − referência).
- **Linha vertical vermelha:** marca o fim do período de otimização e início do out-of-sample.

## 8.6 Exportação

- **💾 Exportar CSV:** salva a tabela de composição do portfólio (Ativo, Peso Inicial, Peso Atual, Tipo) em formato CSV.
- **📊 Exportar Excel:** salva a mesma tabela em formato .xlsx.

# 9\. Aba Retornos Mensais

Esta aba exibe os retornos do portfólio organizados em tabela pivot (anos nas linhas, meses nas colunas), cobrindo o período completo configurado (otimização + validação).

## 9.1 Aba Retornos do Portfólio

Exibe os retornos mensais percentuais calculados pela metodologia de crescimento relativo em base zero:

- **Meses:** Jan a Dez, exibidos como colunas.
- **Total Anual:** retorno composto do ano, calculado pela multiplicação dos fatores mensais: (1+r₁)×(1+r₂)×...×(1+r₁₂) − 1.
- **Ícone 📈:** indica ano com retorno médio positivo.
- **Ícone 📉:** indica ano com retorno médio negativo.

## 9.2 Aba Excesso de Retorno

Disponível apenas quando uma taxa de referência foi detectada. Exibe a diferença entre o retorno mensal do portfólio e o retorno mensal da referência. Valores positivos indicam meses em que o portfólio superou o benchmark.

💡 Ambas as tabelas cobrem o período completo (otimização + validação), não apenas o período de treinamento. Isso permite avaliar o desempenho real do portfólio ao longo do tempo inteiro.

# 10\. Aba Auto-Otimização - Walk-Forward

A Auto-Otimização executa automaticamente centenas ou milhares de testes walk-forward, variando sistematicamente os parâmetros de otimização para identificar as combinações mais robustas. É a funcionalidade mais avançada do sistema.

## 10.1 Conceito de Walk-Forward

O método walk-forward funciona da seguinte forma para cada combinação de parâmetros:

- **Step 1 - Ranking:** calcula o ranking de ativos para o período de treinamento atual e filtra os ativos pelo intervalo de score configurado.
- **Step 2 - Otimização:** otimiza o portfólio com os ativos selecionados pelo ranking, usando o objetivo e os limites de peso configurados.
- **Step 3 - Validação:** aplica os pesos otimizados no período de validação imediatamente seguinte (fora da amostra de treino).
- **Step 4 - Avanço:** desloca as janelas no tempo pelo período de rebalanceamento e repete os passos 1 a 3.
- **Step 5 - Acumulação:** o retorno de cada step é acumulado para calcular as métricas finais da configuração.

💡 O walk-forward usa os dados BRUTOS (não processados) da planilha original, aplicando a transformação base zero em cada step independentemente. Isso evita vazamento de informação entre períodos.

## 10.2 Parâmetros de Configuração

### Janelas de Otimização

Definem o tamanho do período de treino em cada step:

| **Opção** | **Dias Corridos** |
| --------- | ----------------- |
| 3m        | 90 dias           |
| 6m        | 180 dias          |
| 1a        | 365 dias          |
| 2a        | 730 dias          |
| 3a        | 1095 dias         |

### Janelas de Validação / Step

Definem ao mesmo tempo a duração do período out-of-sample e a frequência de rebalanceamento:

| **Opção** | **Dias Corridos** |
| --------- | ----------------- |
| 1 semana  | 7 dias            |
| 2 semanas | 14 dias           |
| 1 mês     | 30 dias           |
| 2 meses   | 60 dias           |
| 3 meses   | 90 dias           |

### Objetivos de Otimização

Selecione um ou mais objetivos. O sistema testará cada combinação para cada objetivo selecionado:

- Maximizar Sharpe
- Maximizar Sortino
- Minimizar Risco
- Minimizar Under Water
- Maximizar Inc/\[(1-R²)×Vol\]
- Qualidade da Linearidade
- Linearidade do Excesso
- Sharpe do Excesso

### Posições Vendidas (Opcional)

Marque **'Habilitar posições short'** e clique em **📋 Selecionar Ativos para Short** para abrir a janela de seleção. Nela você pode escolher **um ou mais ativos** para posição vendida, cada um com seu peso em percentual negativo (com busca, seleção em lote e peso padrão, igual à aba Short/Hedge). Os ativos e pesos escolhidos são fixos e aplicados a **todos os steps** do walk-forward. Um resumo dos shorts configurados aparece na própria aba.

💡 Os candidatos a short são todos os ativos carregados (aba Dados). Em cada step, se um ativo short também tiver sido escolhido como long pelo ranking, ele é tratado apenas como short. Ativos short ausentes no período de um step são ignorados naquele step.

### Configurações Globais

| **Parâmetro**           | **Descrição**                                                                                                                                   |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Score Min / Max (0-100) | Intervalo do ranking de ativos. Ativos com índice fora deste intervalo são excluídos da otimização em cada step. Valor 0-100 = todos os ativos. |
| Peso Min (%) / Max (%)  | Limites globais de peso aplicados em cada step da otimização.                                                                                   |
| Meta de Retorno         | Opcional. Marque 'Exigir meta' e escolha o modo: **% acima da ref.** (relativa) ou **% ao ano** (absoluta). A meta é aplicada **em cada step** do walk-forward — na relativa, contra a referência daquele período; na absoluta, convertida para os pregões daquela janela. O cumprimento por step é reportado na coluna **Meta%** da tabela de resultados. |

## 10.3 Estimar e Executar

- Clique em **🧮 Calcular** para ver uma estimativa do número de configurações, testes totais, dias do período e steps por configuração antes de executar.
- Clique em **🚀 INICIAR AUTO-OTIMIZAÇÃO**. O processo roda em thread separada para não travar a interface.
- O status no topo direito da aba atualiza em tempo real: configuração atual sendo testada, resultado (✅ ou ❌) e número de steps.

⚠️ Para dados com muitos anos e janelas curtas (ex.: 1 semana), o número de steps pode ser muito alto. Use a estimativa antes de executar para evitar processos muito longos.

## 10.4 Tabela de Resultados

Ao concluir, a tabela exibe todas as configurações válidas ordenadas pelo Sharpe Ratio (maior para menor):

| **Coluna** | **Descrição**                                                                      |
| ---------- | ---------------------------------------------------------------------------------- |
| #          | Posição na classificação (1 = melhor Sharpe).                                      |
| Otimização | Janela de otimização usada.                                                        |
| Rebalanc.  | Janela de validação/rebalanceamento.                                               |
| Objetivo   | Objetivo de otimização.                                                            |
| N_Ativos   | Número médio de ativos por step.                                                   |
| Sharpe     | Sharpe Ratio final acumulado (retorno anualizado − taxa ref) ÷ volatilidade média. |
| Ret%       | Retorno anualizado acumulado de todos os steps (**fora da amostra**).              |
| Meta%      | Percentual de steps que cumpriram a Meta **dentro da janela de otimização**. Exibe "—" quando a meta não foi usada. Ver interpretação abaixo. |
| Ref%       | Taxa de referência anualizada acumulada.                                           |
| Vol%       | Volatilidade média dos steps.                                                      |
| VaR%       | VaR 95% diário médio dos steps (perda esperada nos piores 5% dos dias). Risco de cauda. |
| >Ref%      | Percentual de períodos (steps de rebalanceamento) em que o retorno superou a taxa de referência do período. |
| >0%        | Percentual de períodos (steps de rebalanceamento) com retorno positivo em termos absolutos. |

💡 **Cabeçalhos abreviados com tooltip:** passe o mouse sobre qualquer título de coluna para ver a explicação completa do que ela mede.

💡 **Tabela ordenável:** clique em qualquer cabeçalho para reordenar por aquela coluna; clique de novo para inverter. A ordenação é **numérica** (e não alfabética), então `10` vem depois de `3` e `2.101` depois de `18.5%`, como esperado.

### Como interpretar a coluna Meta%

A coluna Meta% mede o cumprimento da meta **onde o otimizador podia agir** (dentro da amostra), enquanto Ret% mede o resultado **fora da amostra**. Cruzar as duas separa duas causas bem diferentes de um retorno abaixo do alvo:

| **Meta%** | **Leitura**                                                                                                    |
| --------- | -------------------------------------------------------------------------------------------------------------- |
| 100% com Ret% abaixo do alvo | A meta foi batida in-sample, mas **não se sustentou fora da amostra**. Típico dos minimizadores de risco (Minimizar Risco, Under Water): a meta é restrição ativa, a carteira encosta exatamente no alvo e fica **sem folga** — qualquer degradação out-of-sample derruba o número. |
| Abaixo de 100%               | Em alguns steps o alvo era **inatingível** com os limites vigentes, valendo o fallback de "maior retorno possível". |
| "—"                          | A meta não estava em uso nessa execução.                                                                       |

💡 Objetivos que buscam retorno por natureza (Sharpe, Sortino) tendem a **passar longe** do alvo in-sample, guardando folga que sobrevive fora da amostra. Se a meta relativa está sendo cumprida in-sample mas não se sustenta, considere pedir uma margem maior.

## 10.5 Exportação dos Resultados

Ambas as exportações gravam **valores numéricos de verdade** (não texto), respeitando a ordenação atual da tabela — o que você vê é o que é exportado.

- **💾 Exportar CSV:** separador `;` e decimal `,` (padrão brasileiro, que o Excel pt-BR abre com duplo clique sem passar pelo assistente de importação). Os percentuais saem já multiplicados por 100, coerentes com o cabeçalho `(%)`.
- **📊 Exportar Excel:** percentuais gravados como **percentual nativo** do Excel (formatos `0,0%`, `0,00%`), Sharpe com formato `0,000`, Rank e N_Ativos como inteiros. Inclui cabeçalho em negrito, painel congelado na primeira linha, autofiltro e ajuste automático da largura das colunas.

💡 Como os valores são números reais, o separador decimal exibido é o do **seu sistema** (vírgula no Brasil) e as células podem ser somadas, ordenadas e usadas em fórmulas normalmente. Quando a meta não é usada, a célula de Meta_OK fica **vazia** (em vez de "—"), para não atrapalhar cálculos.

# 11\. Fluxo de Trabalho Recomendado

Para obter os melhores resultados, siga esta sequência:

| **Etapa** | **Ação**                                                                         | **Aba**                |
| --------- | -------------------------------------------------------------------------------- | ---------------------- |
| 1         | Prepare a planilha Excel com datas, benchmark e ativos.                          | -                      |
| 2         | Carregue o arquivo e verifique se o benchmark foi detectado corretamente.        | 📁 Dados               |
| 3         | Configure as janelas temporais (sugestão: 70% treino, 30% validação) e processe. | 📁 Dados               |
| 4         | Selecione os ativos de interesse ou use o ranking para seleção automática.       | 📁 Dados / 🏆 Ranking  |
| 5         | Defina o objetivo de otimização e os limites globais de peso.                    | ⚙️ Configuração        |
| 6         | Se necessário, configure restrições individuais ou posições short.               | 🔧 Avançado / 🔄 Short |
| 7         | Execute a otimização e analise os resultados in-sample e out-of-sample.          | 📈 Resultados          |
| 8         | Verifique os retornos mensais para consistência temporal.                        | 📅 Mensais             |
| 9         | Use a Auto-Otimização para explorar sistematicamente outros parâmetros.          | 🤖 Auto-Otimização     |
| 10        | Exporte os resultados da composição e da auto-otimização para análise externa.   | 📈 / 🤖                |

# 12\. Dicas e Boas Práticas

## 12.1 Preparação dos Dados

- Certifique-se de que não há datas duplicadas na planilha.
- Ativos com dados faltantes no início do período serão automaticamente removidos. Se um ativo começou a ser negociado depois dos demais, inclua-o a partir de sua primeira data disponível ou remova-o da planilha.
- Utilize sempre preços de fechamento (ou cotas) ajustados por proventos para evitar distorções nos retornos calculados.
- Nomeie as colunas dos ativos com identificadores claros (ex.: ticker da bolsa) para facilitar a interpretação dos resultados.

## 12.2 Seleção de Janelas Temporais

- A proporção 70/30 (70% treino, 30% validação) é um ponto de partida razoável, mas pode ser ajustada conforme o tamanho da série histórica disponível.
- Para períodos curtos (menos de 2 anos de dados), prefira janelas de otimização menores (3 a 6 meses) para garantir steps suficientes na auto-otimização.
- Períodos de validação muito curtos (menos de 60 dias) podem não ser estatisticamente representativos.

## 12.3 Interpretação do Overfitting

- Uma diferença grande e negativa no Sharpe entre out-of-sample e in-sample é o principal sinal de overfitting.
- O objetivo 'Qualidade da Linearidade' (R²) tende a gerar modelos mais robustos e com menor overfitting do que Sharpe puro.
- Prefira janelas de otimização mais longas (1 a 2 anos) para reduzir o risco de overfitting ao ruído de curto prazo.

## 12.4 Auto-Otimização

- Comece com poucas combinações para validar o processo antes de executar centenas de configurações.
- Um Sharpe alto na Auto-Otimização não garante desempenho futuro. Observe também a consistência (% de períodos positivos) e a estabilidade da volatilidade.
- Configurações com janelas muito curtas (ex.: 1 semana de rebalanceamento) tendem a gerar custos de transação elevados em carteiras reais.

## 12.5 Ranking de Ativos

- O peso de correlação pode ser ajustado para zero se você não quiser que a relação com o benchmark influencie o ranking.
- Correlações negativas podem ser desejáveis para ativos de hedge: ajuste o peso de correlação para valores negativos não é suportado diretamente, mas ativos com correlação negativa obterão scores menores, o que pode ser usado para identificá-los e inclui-los como short.
- Recalcule o ranking sempre que mudar o período de análise, pois os parâmetros são recalculados com base nos dados do período configurado.

## 12.6 Robustez da Otimização (Multi-Start)

Alguns objetivos não-lineares (como Inclinação/\[(1-R²)×Vol\] e Linearidade do Excesso) podem, em certas configurações, fazer o otimizador "travar" no ponto de partida e devolver uma carteira de **pesos iguais** (todos os ativos com o mesmo percentual). Para evitar isso, o solver detecta automaticamente esse travamento e reinicia a busca a partir de vários pontos aleatórios, ficando com o melhor resultado.

- **Sinal de travamento (versões antigas):** se você vir todos os ativos com peso exatamente igual (ex.: todos com 1,67%), é sinal de que a otimização não convergiu. Com o multi-start isso é corrigido automaticamente.
- **Custo:** o multi-start só é acionado quando há travamento, então otimizações que convergem normalmente não ficam mais lentas. Nos casos travados, a otimização pode demorar mais alguns segundos (especialmente com muitos ativos), pois testa vários reinícios.
- **Reprodutibilidade:** os reinícios usam uma semente fixa, então a mesma configuração sempre produz o mesmo resultado.

## 12.7 Degradação Graciosa (em vez de "Otimização falhou")

Em janelas difíceis — tipicamente quando há **mais ativos do que dias** no período de otimização — o solver pode não convergir formalmente e retornar a mensagem `Positive directional derivative for linesearch`. Antes, isso abortava a otimização sem mostrar resultado algum.

Agora, quando os pesos em mãos formam uma **carteira viável** (respeitam os limites e somam 100% após normalização), o sistema entrega essa carteira com um aviso, em vez de falhar:

- Na otimização manual, aparece a mensagem **"Otimização concluída com ressalvas"** (aviso, não erro), e a aba Resultados é preenchida normalmente com todas as métricas.
- Na Auto-Otimização, a ressalva é registrada no log do step e o processo **segue** para os próximos steps.
- Se os pesos realmente não forem aproveitáveis, o erro original continua sendo exibido.
- Há também um aviso específico quando o objetivo termina em região inválida (ex.: inclinação negativa), caso em que a carteira devolvida pode estar próxima do ponto de partida.

⚠️ **Causa de raiz:** ter mais ativos do que dias torna o problema matematicamente mal-posto — existem infinitas carteiras que parecem ótimas dentro da amostra, e a maioria é ajuste ao ruído. A degradação graciosa evita a interrupção, mas o remédio de verdade é **reduzir o universo de ativos** (use o Ranking por Score) para que ele fique confortavelmente abaixo do número de dias da janela.

## 12.8 Desempenho

O motor de cálculo passou por otimizações que reduziram bastante o tempo das rodadas, **sem alterar nenhum resultado**:

- **Caminho de cálculo enxuto:** para os objetivos simples (Sharpe, Sortino, Under Water, Minimizar Risco), cada avaliação dentro do laço do solver calcula apenas o necessário, sem VaR, CVaR nem regressões. As métricas completas continuam sendo calculadas uma única vez, ao final, sobre os pesos ótimos — a aba Resultados e as tabelas não mudam.
- **Sortino suavizado:** o *downside deviation* usa o semi-desvio clássico de Sortino & Price, `√(média(mín(retorno,0)²))`, que é diferenciável. A forma anterior (desvio-padrão apenas do subconjunto de dias negativos) tinha "quinas" que deixavam o solver lento e sujeito a falhas de convergência.
- **Regressão por fórmula fechada:** a inclinação e o R² usados por HC10, Linearidade do Excesso e Sharpe do Excesso são calculados diretamente, em vez de via `scipy.stats.linregress`. O resultado é idêntico (diferença ~1e-15, ruído de ponto flutuante) e o cálculo de métricas completas ficou **cerca de 5× mais rápido**.

💡 Se você usava versões anteriores, note que os **valores de Sortino mudaram de magnitude** por causa da nova fórmula (o denominador passou a ser calculado sobre todos os períodos). O ranking relativo entre carteiras se mantém.

# 13\. Glossário

| **Termo**                      | **Definição**                                                                                                                                                            |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Base Zero                      | Transformação dos preços em retornos diários divididos pelo preço inicial: (P*n − P*{n-1}) ÷ P_1. Permite comparar ativos com escalas de preço diferentes.               |
| Integral Acumulada             | Soma acumulada (cumsum) dos retornos diários em base zero. Representa a evolução do retorno relativo ao longo do tempo.                                                  |
| In-Sample                      | Período usado para calibrar/treinar o modelo. Os pesos são otimizados neste intervalo.                                                                                   |
| Out-of-Sample                  | Período de validação, fora do intervalo de treinamento. Avalia se o modelo generaliza bem para dados não vistos.                                                         |
| Walk-Forward                   | Metodologia de backtest que simula a operação real do portfólio: treina em uma janela, valida na seguinte, avança no tempo e repete.                                     |
| Sharpe Ratio                   | (Retorno anualizado − Taxa de referência anualizada) ÷ Volatilidade anualizada.                                                                                          |
| Sortino Ratio                  | Semelhante ao Sharpe, mas divide o excesso de retorno apenas pela volatilidade de queda (downside deviation), ignorando as oscilações de alta.                            |
| Downside Deviation             | Semi-desvio-padrão das perdas: √(média(mín(retorno, 0)²)), anualizado. Denominador do Sortino.                                                                            |
| Under Water (Total)            | Soma de todos os retornos diários negativos do período; em valor absoluto, o total de perdas acumuladas. Medida de risco **assimétrica** — pune apenas queda, nunca alta. |
| Sharpe do Excesso              | Inclinação da regressão do excesso acumulado dividida pela volatilidade do excesso. É a Linearidade do Excesso sem o fator (1 − R²).                                      |
| Meta de Retorno                | Retorno mínimo exigido do portfólio, combinado ao objetivo escolhido. Em dois modos: **relativa** (Referência × (1 + Meta ÷ 100)) ou **absoluta** ((1 + Meta)^(pregões ÷ 252) − 1, independente da referência). |
| Multi-Start                    | Estratégia do solver que reinicia a otimização a partir de vários pontos iniciais quando detecta travamento, escapando de ótimos locais e devolvendo o melhor resultado.  |
| Degradação Graciosa            | Comportamento do sistema quando o solver não converge formalmente: em vez de abortar, entrega a melhor carteira **viável** encontrada (dentro dos limites e somando 100%) acompanhada de um aviso. |
| In-Sample vs Out-of-Sample (Meta) | A meta é exigida **dentro** da janela de otimização; o Ret% da tabela mede o resultado **fora** dela. A coluna Meta% mostra o cumprimento in-sample, permitindo distinguir "alvo inatingível" de "alvo atingido que não se sustentou". |
| VaR 95%                        | Value at Risk: estimativa paramétrica da perda máxima esperada em 95% dos dias (μ − 1,65σ).                                                                              |
| CVaR 95%                       | Conditional VaR: média das perdas nos 5% piores dias. Mede o risco de cauda (tail risk).                                                                                 |
| R²                             | Coeficiente de determinação da regressão linear do retorno acumulado. Mede a linearidade da evolução do portfólio (valores próximos de 1 indicam tendência mais linear). |
| Overfitting                    | Fenômeno em que o modelo se ajusta excessivamente ao período de treino e não generaliza para novos dados.                                                                |
| Benchmark / Taxa de Referência | Índice ou taxa usada como referência de desempenho (CDI, SELIC, IBOVESPA etc.).                                                                                          |
| Short Selling                  | Venda de um ativo que não se possui, apostando na queda de seu preço. Representado por pesos negativos no portfólio.                                                     |
| Score de Ranking               | Índice normalizado entre 0 e 1 que representa a qualidade relativa de um ativo com base em tendência, estabilidade e correlação.                                         |
