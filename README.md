

Otimizador de Portfólio
Versão Desktop — Manual do Usuário
Documento de referência completo para operação do sistema de
otimização de portfólio com walk-forward e ranking automático de ativos.

Versão 1.0  •  2026
 
1. Introdução

O Otimizador de Portfólio é uma aplicação desktop desenvolvida em Python com interface gráfica Tkinter. Seu objetivo é auxiliar analistas e gestores a construir carteiras de ativos financeiros de forma quantitativa, combinando técnicas de otimização matemática, análise de risco e validação fora da amostra (out-of-sample).

1.1 Principais Funcionalidades
•	Carregamento de dados históricos de preços via planilha Excel.
•	Configuração de janelas temporais separadas para otimização e validação.
•	Múltiplos objetivos de otimização: Sharpe, risco mínimo, linearidade e outros.
•	Restrições globais e individuais de peso por ativo.
•	Suporte a posições vendidas (short selling / hedge).
•	Sistema de ranking automático de ativos com pesos personalizáveis.
•	Resultados in-sample e out-of-sample comparados lado a lado.
•	Tabelas de retornos mensais com cálculo de excesso sobre a referência.
•	Auto-Otimização com walk-forward sobre múltiplas combinações de parâmetros.
•	Exportação de resultados para CSV e Excel.

1.2 Requisitos do Sistema
Componente	Requisito
Sistema Operacional	Windows 10/11, Linux ou macOS
Python	3.8 ou superior (recomendado 3.10+)
Bibliotecas principais	pandas, numpy, scipy, matplotlib, tkcalendar
Módulo adicional	optimizer.py (incluso no projeto)
Resolução de tela	Mínimo 1400 × 900 pixels
Formato de dados	Planilha Excel (.xlsx ou .xls)

1.3 Como Iniciar o Programa
1.	Abra o terminal (Prompt de Comando ou PowerShell no Windows).
2.	Navegue até a pasta onde o arquivo desktop_app_FULL.py está localizado.
3.	Execute o comando: python desktop_app_FULL.py
4.	A janela principal do programa será exibida.

💡  O arquivo optimizer.py precisa estar na mesma pasta que desktop_app_FULL.py para o programa funcionar corretamente.

2. Estrutura da Interface

A interface é organizada em 8 abas (tabs) na parte superior da janela. O fluxo de trabalho recomendado segue a ordem das abas da esquerda para a direita.

Aba	Função
📁 Dados	Carregar planilha Excel, configurar janelas temporais e selecionar ativos
⚙️ Configuração	Definir objetivo de otimização, limites de peso e taxa de referência
🔧 Avançado	Configurar restrições individuais de peso por ativo
🔄 Short/Hedge	Definir posições vendidas com pesos negativos
🏆 Ranking	Calcular e aplicar ranking automático de ativos
📈 Resultados	Visualizar métricas in-sample, out-of-sample e composição do portfólio
📅 Retornos Mensais	Tabela de retornos mês a mês e excesso sobre a referência
🤖 Auto-Otimização	Walk-forward sobre múltiplas combinações de parâmetros automaticamente

 
3. Aba Dados — Carregamento e Configuração

Esta é a primeira aba a ser utilizada. Todo o fluxo começa aqui: carregue a planilha, configure as datas e selecione os ativos antes de avançar para as demais abas.

3.1 Formato da Planilha Excel
A planilha deve seguir o seguinte padrão:
•	Primeira coluna: datas no formato DD/MM/AAAA (a coluna pode ter qualquer nome; o sistema a renomeia automaticamente para 'Data').
•	Segunda coluna (opcional): taxa de referência ou benchmark (CDI, SELIC, IBOV etc.). O sistema detecta automaticamente se o nome da coluna contiver as palavras: taxa, livre, risco, ibov, ref, cdi ou selic.
•	Demais colunas: séries de preços dos ativos, uma por coluna, com o nome do ativo no cabeçalho.

💡  Os dados devem ser preços (cotas), não retornos. O sistema calcula os retornos internamente via transformação para base zero.

3.2 Carregar Arquivo
5.	Clique no botão 📂 Carregar Planilha Excel.
6.	Selecione o arquivo .xlsx ou .xls no diálogo que aparecer.
7.	O painel 'Informações do Arquivo' exibirá: nome do arquivo, número de linhas e colunas, período disponível (data início e data fim) e total de dias.
8.	Se uma taxa de referência for detectada automaticamente, ela aparecerá em verde no painel 'Taxa de Referência Detectada'. Caso contrário, um aviso em vermelho indicará que nenhuma taxa foi encontrada.

⚠️  Se a taxa de referência for detectada automaticamente, o campo de taxa manual na aba Configuração é desabilitado. Se não for detectada, o campo manual permanece disponível para entrada manual do valor acumulado no período.

3.3 Configurar Janelas Temporais
Após carregar o arquivo, configure as três datas críticas que definem os dois períodos de análise:

Data	Descrição
📊 Início da Otimização	Data inicial dos dados usados para calibrar o portfólio.
🎯 Fim da Otimização	Data final da janela de treinamento (in-sample).
📈 Fim da Análise	Data final do período de validação (out-of-sample). Só ativo se 'Usar validação' estiver marcado.

Ao carregar o arquivo, o sistema preenche automaticamente as datas sugeridas usando a proporção de 70% para otimização e 30% para validação. Você pode ajustar livremente clicando nos campos de data.

O painel abaixo das datas exibe em tempo real a quantidade de dias de cada janela e o percentual que representam do período total.

💡  O checkbox '✅ Usar validação (forward test)' permite desabilitar a janela de validação. Nesse caso, o programa usará apenas o período de otimização em todas as análises.

9.	Após ajustar as datas, clique em ⚡ Processar Período Selecionado.
10.	O sistema filtrará os dados brutos para os períodos configurados e aplicará a transformação para base zero.
11.	Uma mensagem de sucesso confirmará quantos dias e ativos estão disponíveis. Ativos com valor zero ou ausente no primeiro dia do período são automaticamente removidos.

3.4 Seleção de Ativos
O painel direito exibe a lista de todos os ativos disponíveis na planilha (excluindo a coluna de data e a taxa de referência, se detectada).
•	Seleção simples: clique em um ativo.
•	Seleção múltipla: Ctrl + clique para adicionar ativos à seleção.
•	Intervalo: Shift + clique para selecionar um intervalo contínuo.
•	✅ Todos: seleciona todos os ativos de uma vez.
•	❌ Limpar: remove toda a seleção.

⚠️  É necessário selecionar no mínimo 2 ativos para executar a otimização.

O contador no rodapé do painel mostra quantos ativos estão selecionados em relação ao total disponível (ex.: 'Selecionados: 8/25').

 
4. Aba Configuração — Parâmetros de Otimização

Nesta aba você define como o algoritmo deve buscar o portfólio ótimo: qual métrica maximizar (ou minimizar), os limites de participação de cada ativo e a taxa de referência utilizada nos cálculos de excesso de retorno.

4.1 Objetivo de Otimização
Selecione um dos objetivos disponíveis pelo botão de rádio:

Objetivo	Descrição
Maximizar Sharpe Ratio	Maximiza o retorno excedente à taxa de referência por unidade de risco. Objetivo mais comum para carteiras balanceadas.
Minimizar Risco	Minimiza a volatilidade do portfólio independentemente do retorno. Ideal para perfis conservadores.
Maximizar Inclinação	Maximiza a inclinação da regressão linear do retorno acumulado. Prioriza ativos com tendência de alta consistente.
Maximizar Inclinação/[(1-R²)×Vol]	Combina a inclinação com a qualidade da linearidade e a volatilidade. Penaliza ativos com retornos irregulares.
Maximizar Qualidade da Linearidade	Maximiza o R² da regressão do retorno acumulado. Prioriza ativos com comportamento linear e previsível.
Maximizar Linearidade do Excesso	Igual ao anterior, mas aplicado ao excesso de retorno sobre a referência. Disponível apenas quando uma taxa de referência é detectada.

4.2 Limites de Peso Globais
Defina os limites de participação de cada ativo no portfólio usando os controles deslizantes:
•	Peso mínimo por ativo (%): participação mínima que qualquer ativo selecionado deve ter. Valores típicos: 0% a 5%. Use 0% para permitir que o otimizador exclua ativos.
•	Peso máximo por ativo (%): participação máxima de qualquer ativo. Limita a concentração. Valores típicos: 15% a 30%.

💡  Os pesos são sempre positivos e somam 100% para posições long. Se houver posições short configuradas, os pesos dos ativos long ainda somam 100% antes do ajuste pelas posições vendidas.

4.3 Taxa de Referência
A taxa de referência é usada para calcular o Sharpe Ratio e o excesso de retorno.
•	Detecção automática: se a planilha contiver uma coluna de benchmark, o campo de taxa manual é desabilitado e a taxa é extraída automaticamente dos dados.
•	Taxa manual: quando não houver coluna de benchmark, informe o valor acumulado no período de otimização (ex.: para 12% ao ano em um período de 2 anos, informe 25.44, que corresponde a (1,12)² − 1 ≈ 25,44%).

4.4 Executar a Otimização
Clique em 🚀 OTIMIZAR PORTFÓLIO para iniciar o processo. Uma janela de progresso será exibida enquanto o algoritmo executa. Ao concluir, o programa navegará automaticamente para a aba Resultados.

 
5. Aba Avançado — Restrições Individuais

Esta aba permite definir limites de peso específicos para ativos individuais, sobrescrevendo os limites globais configurados na aba Configuração para aqueles ativos específicos.

5.1 Habilitar Restrições Individuais
12.	Marque o checkbox 'Habilitar limites específicos para ativos selecionados'.
13.	Clique em 📋 Configurar Restrições Individuais para abrir a janela de configuração.

5.2 Janela de Configuração
A janela exibe todos os ativos selecionados na aba Dados. Para cada ativo:
•	Marque o checkbox 'Usar limites específicos': ativa os campos de mínimo e máximo para aquele ativo.
•	Mín (%): peso mínimo individual (pode ser diferente do global).
•	Máx (%): peso máximo individual.

Ferramentas de ação rápida disponíveis na janela:
•	Buscar: filtra a lista de ativos por nome em tempo real.
•	Aplicar Globais: copia os limites globais para todos os ativos marcados.
•	Limpar Todos: desmarca todas as restrições individuais.
•	Lote — Mín / Máx + Aplicar aos Selecionados: define um valor de mínimo e máximo em lote para todos os ativos marcados.

14.	Após configurar, clique em ✅ Aplicar Configuração. Um resumo das restrições configuradas será exibido na aba Avançado.

💡  As restrições individuais têm prioridade sobre os limites globais. Se um ativo tem restrição individual definida, os valores globais são ignorados para ele.

 
6. Aba Short/Hedge — Posições Vendidas

Esta aba permite incluir posições vendidas (short selling) no portfólio, úteis para estratégias de hedge ou para explorar movimentos de queda em ativos específicos.

6.1 Habilitar Posições Short
15.	Marque o checkbox 'Habilitar posições short/hedge (venda a descoberto)'.
16.	Clique em 📋 Selecionar Ativos para Short para abrir a janela de seleção.

💡  Os ativos disponíveis para short são aqueles que NÃO estão selecionados como ativos principais na aba Dados. Portanto, é necessário ter selecionado os ativos long antes de configurar os shorts.

6.2 Janela de Seleção de Ativos Short
A janela lista todos os ativos disponíveis para posições vendidas. Para cada ativo:
•	Marque o checkbox: inclui o ativo como posição short.
•	Peso (%): informe o peso em percentual NEGATIVO (ex.: -10 para uma posição short de 10%). O sistema valida automaticamente que o valor seja negativo.

Ferramentas disponíveis:
•	Buscar: filtra ativos por nome.
•	Selecionar Todos / Limpar Todos: ações em lote.
•	Peso padrão + Aplicar aos Selecionados: define um peso padrão para todos os ativos marcados de uma vez.

⚠️  O peso dos ativos short deve obrigatoriamente ser NEGATIVO. O sistema rejeitará a configuração se qualquer peso for zero ou positivo.

6.3 Comportamento na Otimização
Quando há posições short configuradas:
•	Os ativos short são incluídos no otimizador com seus pesos fixos (conforme configurado).
•	O otimizador distribui os 100% restantes entre os ativos long selecionados.
•	Os pesos negativos aparecem na composição do portfólio identificados como 'SHORT'.
•	O cálculo de 'Peso Atual' na tabela de composição considera apenas o valor das posições long para normalização.

 
7. Aba Ranking — Classificação de Ativos

O sistema de ranking calcula um índice de qualidade para cada ativo com base em três dimensões: tendência (inclinação), estabilidade (desvio padrão) e correlação com a referência. Isso permite selecionar automaticamente os melhores ativos para a otimização.

7.1 Metodologia do Ranking
O cálculo ocorre em 4 passos internos:

17.	Diferença diária: para cada ativo, calcula-se a diferença entre o retorno diário do ativo e o retorno da referência (ativo − referência, dia a dia).
18.	Integral acumulada: soma acumulada (cumsum) das diferenças diárias. Representa a evolução do desempenho relativo ao longo do tempo.
19.	Parâmetros: regressão linear da integral acumulada (slope = inclinação, R² = qualidade) e desvio padrão das diferenças diárias. A correlação é calculada entre a integral acumulada do ativo e a da referência.
20.	Índice bruto e normalização: os três componentes são normalizados e combinados com pesos configuráveis. O resultado final é normalizado de 0 a 1.

Fórmula do índice:
Índice = [P_inc × Inclinação_norm + P_desv × (1 − Desvio_norm) + P_cor × Correlação] ÷ (P_inc + P_desv + P_cor)

7.2 Configurar e Calcular
21.	Marque o checkbox '🤖 Ativar ranking automático de ativos'. O painel de configuração aparecerá.
22.	Ajuste os pesos dos três componentes com os controles deslizantes (valores entre 0 e 1):
◦	📈 Peso Inclinação: importância da tendência de alta relativa à referência. Maior peso favorece ativos com retorno consistentemente superior ao benchmark.
◦	📊 Peso Estabilidade: importância da baixa volatilidade relativa. Maior peso favorece ativos que superam a referência de forma estável, sem grandes oscilações.
◦	🎯 Peso Correlação: importância da correlação com a referência. Valores negativos de correlação podem indicar ativos com potencial de hedge.
23.	Clique em 🔄 Calcular Ranking. O resultado aparece na tabela com até 20 ativos exibidos.

7.3 Tabela de Resultados
Coluna	Descrição
Posição	Classificação do ativo (1 = melhor).
Ativo	Nome do ativo conforme cabeçalho da planilha.
Índice	Score normalizado entre 0 e 1 (1 = melhor desempenho relativo).
Inclinação	Inclinação normalizada da regressão linear da integral acumulada.
R²	Coeficiente de determinação da regressão (qualidade da tendência linear).
Correlação	Correlação entre as integrais acumuladas do ativo e da referência.
Desvio	Desvio padrão normalizado das diferenças diárias ativo−referência.

7.4 Seleção Automática por Score
Abaixo da tabela, defina um intervalo de score para selecionar ativos automaticamente:
•	Score mínimo: limiar inferior do índice (ex.: 0.70 para selecionar apenas ativos acima de 70% do máximo).
•	Score máximo: limiar superior (geralmente 1.0 para incluir os melhores).
24.	Clique em ✅ Selecionar Ativos por Score. O programa selecionará automaticamente na listbox da aba Dados apenas os ativos dentro do intervalo definido e navegará para a aba Configuração.

💡  A seleção por score respeita as configurações de short selling e restrições individuais já definidas. Essas configurações são preservadas mesmo após a atualização da seleção de ativos.

 
8. Aba Resultados — Análise do Portfólio

Após a otimização, esta aba exibe um painel completo com três colunas de métricas lado a lado e a composição do portfólio com o gráfico de evolução.

8.1 Coluna IN-SAMPLE (Otimização)
Métricas calculadas sobre o período de treinamento (janela de otimização):
Métrica	Descrição
Retorno Total (%)	Retorno acumulado do portfólio no período de otimização em base zero.
Retorno Anualizado (%)	Retorno total anualizado pela fórmula: (1 + R)^(365/dias) − 1.
Sharpe Ratio	Excesso de retorno anualizado dividido pela volatilidade anualizada.
Volatilidade (%)	Desvio padrão anualizado dos retornos diários (×√252).
VaR 95% Diário	Value at Risk: perda máxima esperada em 95% dos dias (paramétrico).
CVaR 95% Diário	Conditional VaR: perda média esperada além do VaR (tail risk).
R²	Qualidade da linearidade do retorno acumulado (regressão linear).
Taxa Ref Período (%)	Retorno acumulado da taxa de referência no período.
Taxa Ref Anualizada (%)	Taxa de referência anualizada.
Excesso Período (%)	Retorno do portfólio menos o retorno da referência no período.
Dias	Número de dias corridos no período de otimização.

8.2 Coluna OUT-OF-SAMPLE (Validação)
As mesmas métricas calculadas para o período de validação, usando os MESMOS pesos otimizados na fase de treinamento. Este é o teste real de generalização do portfólio.

💡  Se nenhuma janela de validação foi configurada (ou o período de validação é muito curto), esta coluna exibirá uma mensagem informativa. Configure uma data 'Fim da Análise' na aba Dados para ativar este painel.

8.3 Coluna COMPARAÇÃO
Exibe as diferenças entre out-of-sample e in-sample para as principais métricas:
•	Retorno Anual (diferença): positivo indica que o portfólio performou melhor fora da amostra do que dentro.
•	Sharpe (diferença): chave para avaliar overfitting. Diferenças grandes e negativas sugerem que o modelo foi super ajustado ao período de treino.
•	Volatilidade (diferença): indica se o risco se manteve estável entre os períodos.
•	Resumo / Análise: o sistema emite automaticamente um diagnóstico qualitativo (ex.: 'Boa generalização!' ou 'Cuidado: overfitting?').

8.4 Composição do Portfólio
A tabela abaixo das três colunas exibe todos os ativos com peso significativo (> 0,1%):
Coluna	Descrição
Ativo	Nome do ativo.
Peso Inicial (%)	Peso otimizado na data de início do portfólio.
Peso Atual (%)	Peso estimado ao final do período, considerando a valorização relativa de cada ativo.
Tipo	LONG (posição comprada) ou SHORT (posição vendida).

As linhas de rodapé da tabela exibem o TOTAL LONG, TOTAL SHORT (quando aplicável) e a VARIAÇÃO do peso long entre o início e o fim do período.

8.5 Gráfico de Evolução
O gráfico à direita da composição exibe:
•	Linha azul: retorno acumulado do portfólio.
•	Linha laranja (tracejada): retorno acumulado da taxa de referência (quando disponível).
•	Linha verde (pontilhada): excesso de retorno acumulado (portfólio − referência).
•	Linha vertical vermelha: marca o fim do período de otimização e início do out-of-sample.

8.6 Exportação
•	💾 Exportar CSV: salva a tabela de composição do portfólio (Ativo, Peso Inicial, Peso Atual, Tipo) em formato CSV.
•	📊 Exportar Excel: salva a mesma tabela em formato .xlsx.

 
9. Aba Retornos Mensais

Esta aba exibe os retornos do portfólio organizados em tabela pivot (anos nas linhas, meses nas colunas), cobrindo o período completo configurado (otimização + validação).

9.1 Aba Retornos do Portfólio
Exibe os retornos mensais percentuais calculados pela metodologia de crescimento relativo em base zero:
•	Meses: Jan a Dez, exibidos como colunas.
•	Total Anual: retorno composto do ano, calculado pela multiplicação dos fatores mensais: (1+r₁)×(1+r₂)×...×(1+r₁₂) − 1.
•	Ícone 📈: indica ano com retorno médio positivo.
•	Ícone 📉: indica ano com retorno médio negativo.

9.2 Aba Excesso de Retorno
Disponível apenas quando uma taxa de referência foi detectada. Exibe a diferença entre o retorno mensal do portfólio e o retorno mensal da referência. Valores positivos indicam meses em que o portfólio superou o benchmark.

💡  Ambas as tabelas cobrem o período completo (otimização + validação), não apenas o período de treinamento. Isso permite avaliar o desempenho real do portfólio ao longo do tempo inteiro.

 
10. Aba Auto-Otimização — Walk-Forward

A Auto-Otimização executa automaticamente centenas ou milhares de testes walk-forward, variando sistematicamente os parâmetros de otimização para identificar as combinações mais robustas. É a funcionalidade mais avançada do sistema.

10.1 Conceito de Walk-Forward
O método walk-forward funciona da seguinte forma para cada combinação de parâmetros:
25.	Step 1 — Ranking: calcula o ranking de ativos para o período de treinamento atual e filtra os ativos pelo intervalo de score configurado.
26.	Step 2 — Otimização: otimiza o portfólio com os ativos selecionados pelo ranking, usando o objetivo e os limites de peso configurados.
27.	Step 3 — Validação: aplica os pesos otimizados no período de validação imediatamente seguinte (fora da amostra de treino).
28.	Step 4 — Avanço: desloca as janelas no tempo pelo período de rebalanceamento e repete os passos 1 a 3.
29.	Step 5 — Acumulação: o retorno de cada step é acumulado para calcular as métricas finais da configuração.

💡  O walk-forward usa os dados BRUTOS (não processados) da planilha original, aplicando a transformação base zero em cada step independentemente. Isso evita vazamento de informação entre períodos.

10.2 Parâmetros de Configuração
Janelas de Otimização
Definem o tamanho do período de treino em cada step:
Opção	Dias Corridos
3m	90 dias
6m	180 dias
1a	365 dias
2a	730 dias
3a	1095 dias

Janelas de Validação / Step
Definem ao mesmo tempo a duração do período out-of-sample e a frequência de rebalanceamento:
Opção	Dias Corridos
1 semana	7 dias
2 semanas	14 dias
1 mês	30 dias
2 meses	60 dias
3 meses	90 dias

Objetivos de Otimização
Selecione um ou mais objetivos. O sistema testará cada combinação para cada objetivo selecionado:
•	Maximizar Sharpe
•	Minimizar Risco
•	Maximizar Inc/[(1-R²)×Vol]
•	Qualidade da Linearidade

Posições Vendidas (Opcional)
Habilite e configure um ativo para posição short que será incluído em todos os steps automaticamente. Informe o nome exato do ativo (deve estar na planilha) e o peso em percentual negativo.

Configurações Globais
Parâmetro	Descrição
Score Min / Max (0–100)	Intervalo do ranking de ativos. Ativos com índice fora deste intervalo são excluídos da otimização em cada step. Valor 0–100 = todos os ativos.
Peso Min (%) / Max (%)	Limites globais de peso aplicados em cada step da otimização.

10.3 Estimar e Executar
30.	Clique em 🧮 Calcular para ver uma estimativa do número de configurações, testes totais e tempo esperado antes de executar.
31.	Clique em 🚀 INICIAR AUTO-OTIMIZAÇÃO. O processo roda em thread separada para não travar a interface.
32.	O status no topo direito da aba atualiza em tempo real: configuração atual sendo testada, resultado (✅ ou ❌) e número de steps.

⚠️  Para dados com muitos anos e janelas curtas (ex.: 1 semana), o número de steps pode ser muito alto. Use a estimativa antes de executar para evitar processos muito longos.

10.4 Tabela de Resultados
Ao concluir, a tabela exibe todas as configurações válidas ordenadas pelo Sharpe Ratio (maior para menor):
Coluna	Descrição
Rank	Posição na classificação (1 = melhor Sharpe).
Otim	Janela de otimização usada.
Rebal/Aval	Janela de validação/rebalanceamento.
Obj	Objetivo de otimização.
N_Ativos	Número médio de ativos por step.
Sharpe	Sharpe Ratio final acumulado (retorno anualizado − taxa ref) ÷ volatilidade média.
Ret%	Retorno anualizado acumulado de todos os steps.
TxRef%	Taxa de referência anualizada acumulada.
Vol%	Volatilidade média dos steps.
Pos%	Percentual médio de períodos (dias) com retorno positivo.

10.5 Exportação dos Resultados
•	💾 Exportar CSV: salva toda a tabela em formato CSV com codificação UTF-8.
•	📊 Exportar Excel: salva a tabela em .xlsx com ajuste automático da largura das colunas.

 
11. Fluxo de Trabalho Recomendado

Para obter os melhores resultados, siga esta sequência:

Etapa	Ação	Aba
1	Prepare a planilha Excel com datas, benchmark e ativos.	—
2	Carregue o arquivo e verifique se o benchmark foi detectado corretamente.	📁 Dados
3	Configure as janelas temporais (sugestão: 70% treino, 30% validação) e processe.	📁 Dados
4	Selecione os ativos de interesse ou use o ranking para seleção automática.	📁 Dados / 🏆 Ranking
5	Defina o objetivo de otimização e os limites globais de peso.	⚙️ Configuração
6	Se necessário, configure restrições individuais ou posições short.	🔧 Avançado / 🔄 Short
7	Execute a otimização e analise os resultados in-sample e out-of-sample.	📈 Resultados
8	Verifique os retornos mensais para consistência temporal.	📅 Mensais
9	Use a Auto-Otimização para explorar sistematicamente outros parâmetros.	🤖 Auto-Otimização
10	Exporte os resultados da composição e da auto-otimização para análise externa.	📈 / 🤖

 
12. Dicas e Boas Práticas

12.1 Preparação dos Dados
•	Certifique-se de que não há datas duplicadas na planilha.
•	Ativos com dados faltantes no início do período serão automaticamente removidos. Se um ativo começou a ser negociado depois dos demais, inclua-o a partir de sua primeira data disponível ou remova-o da planilha.
•	Utilize sempre preços de fechamento (ou cotas) ajustados por proventos para evitar distorções nos retornos calculados.
•	Nomeie as colunas dos ativos com identificadores claros (ex.: ticker da bolsa) para facilitar a interpretação dos resultados.

12.2 Seleção de Janelas Temporais
•	A proporção 70/30 (70% treino, 30% validação) é um ponto de partida razoável, mas pode ser ajustada conforme o tamanho da série histórica disponível.
•	Para períodos curtos (menos de 2 anos de dados), prefira janelas de otimização menores (3 a 6 meses) para garantir steps suficientes na auto-otimização.
•	Períodos de validação muito curtos (menos de 60 dias) podem não ser estatisticamente representativos.

12.3 Interpretação do Overfitting
•	Uma diferença grande e negativa no Sharpe entre out-of-sample e in-sample é o principal sinal de overfitting.
•	O objetivo 'Qualidade da Linearidade' (R²) tende a gerar modelos mais robustos e com menor overfitting do que Sharpe puro.
•	Prefira janelas de otimização mais longas (1 a 2 anos) para reduzir o risco de overfitting ao ruído de curto prazo.

12.4 Auto-Otimização
•	Comece com poucas combinações para validar o processo antes de executar centenas de configurações.
•	Um Sharpe alto na Auto-Otimização não garante desempenho futuro. Observe também a consistência (% de períodos positivos) e a estabilidade da volatilidade.
•	Configurações com janelas muito curtas (ex.: 1 semana de rebalanceamento) tendem a gerar custos de transação elevados em carteiras reais.

12.5 Ranking de Ativos
•	O peso de correlação pode ser ajustado para zero se você não quiser que a relação com o benchmark influencie o ranking.
•	Correlações negativas podem ser desejáveis para ativos de hedge: ajuste o peso de correlação para valores negativos não é suportado diretamente, mas ativos com correlação negativa obterão scores menores, o que pode ser usado para identificá-los e inclui-los como short.
•	Recalcule o ranking sempre que mudar o período de análise, pois os parâmetros são recalculados com base nos dados do período configurado.

 
13. Glossário

Termo	Definição
Base Zero	Transformação dos preços em retornos diários divididos pelo preço inicial: (P_n − P_{n-1}) ÷ P_1. Permite comparar ativos com escalas de preço diferentes.
Integral Acumulada	Soma acumulada (cumsum) dos retornos diários em base zero. Representa a evolução do retorno relativo ao longo do tempo.
In-Sample	Período usado para calibrar/treinar o modelo. Os pesos são otimizados neste intervalo.
Out-of-Sample	Período de validação, fora do intervalo de treinamento. Avalia se o modelo generaliza bem para dados não vistos.
Walk-Forward	Metodologia de backtest que simula a operação real do portfólio: treina em uma janela, valida na seguinte, avança no tempo e repete.
Sharpe Ratio	(Retorno anualizado − Taxa de referência anualizada) ÷ Volatilidade anualizada.
VaR 95%	Value at Risk: estimativa paramétrica da perda máxima esperada em 95% dos dias (μ − 1,65σ).
CVaR 95%	Conditional VaR: média das perdas nos 5% piores dias. Mede o risco de cauda (tail risk).
R²	Coeficiente de determinação da regressão linear do retorno acumulado. Mede a linearidade da evolução do portfólio (valores próximos de 1 indicam tendência mais linear).
Overfitting	Fenômeno em que o modelo se ajusta excessivamente ao período de treino e não generaliza para novos dados.
Benchmark / Taxa de Referência	Índice ou taxa usada como referência de desempenho (CDI, SELIC, IBOVESPA etc.).
Short Selling	Venda de um ativo que não se possui, apostando na queda de seu preço. Representado por pesos negativos no portfólio.
Score de Ranking	Índice normalizado entre 0 e 1 que representa a qualidade relativa de um ativo com base em tendência, estabilidade e correlação.

