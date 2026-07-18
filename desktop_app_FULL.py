import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import os
import sys
from datetime import datetime, timedelta
from tkcalendar import DateEntry  # Para seleção de datas
from optimizer import PortfolioOptimizer

# =============================================================================
# FUNÇÕES PARA RANKING DE ATIVOS
# =============================================================================

def calculate_asset_ranking(df_base_zero, risk_free_column=None, peso_inc=0.33, peso_desv=0.33, peso_cor=0.33):
    """
    Calcula ranking de ativos - VERSÃO TKINTER CORRIGIDA
    ATUALIZADO: Correlação agora é entre integrais (ativo vs referência)
    COM: Normalização final (0 a 1)
    """
    try:
        from scipy import stats
        import pandas as pd
        import numpy as np
        
        # Verificar se dados estão em base zero
        if df_base_zero is None or df_base_zero.empty:
            return None
            
        # Identificar colunas
        if 'Data' in df_base_zero.columns:
            df_work = df_base_zero.copy()
            
            # CORREÇÃO: Forçar formato brasileiro de data
            try:
                dates_col = pd.to_datetime(df_work['Data'], format='%d/%m/%Y')
            except:
                dates_col = pd.to_datetime(df_work['Data'])
            
            # Identificar coluna de referência (taxa livre de risco)
            if risk_free_column and risk_free_column in df_work.columns:
                ref_col = risk_free_column
                asset_columns = [col for col in df_work.columns if col not in ['Data', risk_free_column]]
            elif len(df_work.columns) > 2:
                # Assumir segunda coluna como referência se contém palavras-chave
                second_col = df_work.columns[1]
                if any(term in second_col.lower() for term in ['taxa', 'livre', 'risco', 'ibov', 'ref', 'cdi', 'selic']):
                    ref_col = second_col
                    asset_columns = [col for col in df_work.columns if col not in ['Data', second_col]]
                else:
                    ref_col = df_work.columns[1]
                    asset_columns = df_work.columns[2:].tolist()
            else:
                return None
        else:
            return None
        
        # ===============================
        # PASSO 1: CRIAR ABA "DIFERENÇA"
        # ===============================
        diferenca_data = {}
        diferenca_data['Data'] = dates_col
        
        for asset in asset_columns:
            # Cada ativo - referência (linha por linha)
            diferenca_data[f"{asset}_diff"] = df_work[asset] - df_work[ref_col]
        
        df_diferenca = pd.DataFrame(diferenca_data)
        
        # ===============================
        # PASSO 2: CRIAR ABA "INTEGRAL" 
        # ===============================
        integral_data = {}
        integral_data['Data'] = dates_col
        
        for asset in asset_columns:
            # Soma acumulada das diferenças
            integral_data[f"{asset}_integral"] = df_diferenca[f"{asset}_diff"].cumsum()
        
        df_integral = pd.DataFrame(integral_data)
        
        # ===============================
        # PASSO 3: CALCULAR PARÂMETROS (ÍNDICE BRUTO)
        # ===============================
        rankings = []
        all_slopes = []
        all_deviations = []
        
        # Primeira passada: coletar TODOS os valores
        for asset in asset_columns:
            try:
                # Dados para regressão (x = índice numérico das datas, y = integral)
                x_data = np.arange(len(df_integral))
                y_data = df_integral[f"{asset}_integral"].values
                
                # Calcular regressão linear
                slope, intercept, r_value, p_value, std_err = stats.linregress(x_data, y_data)
                
                # Desvio padrão das diferenças
                std_dev = df_diferenca[f"{asset}_diff"].std()
                
                # Coletar TODOS os valores (sem filtro)
                all_slopes.append(slope)
                all_deviations.append(std_dev)
                
            except Exception as e:
                continue
        
        # Encontrar máximos para normalização de componentes
        max_slope = max(all_slopes) if all_slopes else 1
        max_deviation = max(all_deviations) if all_deviations else 1
        
        # Segunda passada: calcular índices BRUTOS
        for asset in asset_columns:
            try:
                # Dados para regressão (ainda necessário para Inclinação e R²)
                x_data = np.arange(len(df_integral))
                y_data = df_integral[f"{asset}_integral"].values
                
                # Calcular regressão linear
                slope, intercept, r_value, p_value, std_err = stats.linregress(x_data, y_data)
                r_squared = r_value ** 2
                
                # ✅ NOVA CORRELAÇÃO: Entre integrais (evoluções acumuladas)
                # Integral do ativo PURO (não da diferença!)
                asset_integral = df_work[asset].cumsum().values
                # Integral da referência (soma acumulada)
                ref_integral = df_work[ref_col].cumsum().values
                # Correlação entre as duas curvas acumuladas
                correlation = np.corrcoef(asset_integral, ref_integral)[0, 1]
                
                # Desvio padrão das diferenças
                std_dev = df_diferenca[f"{asset}_diff"].std()
                
                # NORMALIZAÇÃO DE COMPONENTES
                slope_norm = slope / max_slope if max_slope > 0 else 0
                std_dev_norm = std_dev / max_deviation if max_deviation > 0 else 0
                
                # FÓRMULA COM PESOS PERSONALIZÁVEIS
                # Usar correlação com sinal (permite negativas para hedge)
                correlation_norm = correlation
                
                # Fórmula: [P_inc×Inclinação + P_desv×(1-Desvio) + P_cor×Correlação] / (P_inc+P_desv+P_cor)
                numerador = (peso_inc * slope_norm + 
                           peso_desv * (1 - std_dev_norm) + 
                           peso_cor * correlation_norm)
                denominador = peso_inc + peso_desv + peso_cor
                
                indice_bruto = numerador / denominador if denominador > 0 else 0
                
                rankings.append({
                    'Ativo': asset,
                    'Inclinação': slope,
                    'Inclinação_Norm': slope_norm,
                    'R²': r_squared,
                    'Correlação': correlation,
                    'Desvio_Padrão': std_dev,
                    'Desvio_Norm': std_dev_norm,
                    'Índice_Bruto': indice_bruto
                })
                
            except Exception as e:
                rankings.append({
                    'Ativo': asset,
                    'Inclinação': 0,
                    'Inclinação_Norm': 0,
                    'R²': 0,
                    'Correlação': 0,
                    'Desvio_Padrão': 0,
                    'Desvio_Norm': 0,
                    'Índice_Bruto': 0
                })
        
        # ===============================
        # PASSO 4: NORMALIZAÇÃO FINAL (0 a 1)
        # ===============================
        df_ranking = pd.DataFrame(rankings)
        
        if len(df_ranking) > 0:
            max_idx = df_ranking['Índice_Bruto'].max()
            min_idx = df_ranking['Índice_Bruto'].min()
            
            # Normalizar para range 0-1
            if max_idx > min_idx:
                df_ranking['Índice'] = (df_ranking['Índice_Bruto'] - min_idx) / (max_idx - min_idx)
            else:
                # Se todos os índices são iguais
                df_ranking['Índice'] = 0.5
            
            # Remover coluna temporária do índice bruto
            df_ranking = df_ranking.drop(columns=['Índice_Bruto'])
        else:
            df_ranking['Índice'] = 0
        
        # Ordenar por índice normalizado
        df_ranking = df_ranking.sort_values('Índice', ascending=False).reset_index(drop=True)
        df_ranking['Posição'] = range(1, len(df_ranking) + 1)
        
        # Reorganizar colunas
        cols = ['Posição', 'Ativo', 'Índice', 'Inclinação', 'Inclinação_Norm', 
                'R²', 'Correlação', 'Desvio_Padrão', 'Desvio_Norm']
        df_ranking = df_ranking[cols]
        
        return {
            'ranking': df_ranking,
            'referencia': ref_col,
            'total_ativos': len(asset_columns)
        }
        
    except Exception as e:
        print(f"❌ Erro no cálculo de ranking: {str(e)}")
        return None


# =============================================================================
# IMPORTAÇÃO DE RESTRIÇÕES (MÍN/MÁX OU PESOS) DE ARQUIVO EXCEL/CSV
# =============================================================================

def load_constraints_from_file(file_path):
    """
    Lê um arquivo Excel/CSV com restrições por ativo.

    Formatos aceitos (nomes de coluna flexíveis, sem diferenciar maiúsculas):
      • 'Ativo', 'Min', 'Max'  -> usa mínimo e máximo por ativo (faixas)
      • 'Ativo', 'Peso'        -> fixa min = max = peso
                                  (útil para ANALISAR um portfólio pronto:
                                   quando os pesos somam 100%, o otimizador
                                   é forçado exatamente àquela composição)

    Valores em PERCENTUAL (ex.: 30 = 30%). Se TODOS os valores forem <= 1,
    assume-se que já estão em fração (ex.: 0.30 = 30%).

    Retorna: (constraints, warnings)
      constraints = {ativo: {'min': fração, 'max': fração}}
      warnings    = lista de avisos (strings)
    """
    warnings = []
    ext = os.path.splitext(file_path)[1].lower()

    if ext in ('.xlsx', '.xls'):
        df = pd.read_excel(file_path)
    else:
        # CSV: detecta separador automaticamente (vírgula, ponto-e-vírgula, tab)
        df = pd.read_csv(file_path, sep=None, engine='python')

    if df is None or df.empty or len(df.columns) < 2:
        raise ValueError("Arquivo vazio ou sem colunas suficientes "
                         "(mínimo: coluna de ativo + 1 coluna de valor).")

    low = {c: str(c).strip().lower() for c in df.columns}

    def find(terms, exclude=()):
        for col, name in low.items():
            if any(t in name for t in terms) and not any(e in name for e in exclude):
                return col
        return None

    asset_col = find(['ativo', 'asset', 'ticker', 'papel', 'codigo', 'código', 'symbol', 'nome'])
    min_col = find(['min', 'mín'])
    max_col = find(['max', 'máx'])
    weight_col = find(['peso', 'weight', 'quant', 'aloca', 'aloc', 'percent', 'participa'])

    if asset_col is None:
        asset_col = df.columns[0]

    def to_float(v):
        if pd.isna(v):
            return None
        s = str(v).strip().replace('%', '').replace(' ', '')
        if s == '':
            return None
        if ',' in s and '.' in s:
            s = s.replace('.', '').replace(',', '.')   # 1.234,56 -> 1234.56
        elif ',' in s:
            s = s.replace(',', '.')                     # 30,5 -> 30.5
        try:
            return float(s)
        except ValueError:
            return None

    raw = {}
    if min_col is not None and max_col is not None:
        for _, row in df.iterrows():
            asset = str(row[asset_col]).strip()
            if not asset or asset.lower() == 'nan':
                continue
            mn = to_float(row[min_col])
            mx = to_float(row[max_col])
            if mn is None or mx is None:
                warnings.append(f"'{asset}': valor mín/máx inválido, ignorado.")
                continue
            raw[asset] = [mn, mx]
    else:
        # Coluna única de peso -> min = max = peso
        if weight_col is None:
            weight_col = df.columns[1]   # assume 2ª coluna como peso
        for _, row in df.iterrows():
            asset = str(row[asset_col]).strip()
            if not asset or asset.lower() == 'nan':
                continue
            w = to_float(row[weight_col])
            if w is None:
                warnings.append(f"'{asset}': peso inválido, ignorado.")
                continue
            raw[asset] = [w, w]

    if not raw:
        raise ValueError("Nenhum ativo válido encontrado no arquivo.")

    # Percentual (0-100) vs fração (0-1): decide pela maior magnitude presente
    all_vals = [abs(v) for pair in raw.values() for v in pair]
    max_val = max(all_vals) if all_vals else 0
    scale = 1.0 if max_val <= 1.0 else 0.01

    constraints = {}
    for asset, (mn, mx) in raw.items():
        mn *= scale
        mx *= scale
        if mn > mx:
            mn, mx = mx, mn
            warnings.append(f"'{asset}': mín > máx, valores invertidos.")
        constraints[asset] = {'min': max(0.0, mn), 'max': max(0.0, mx)}

    return constraints, warnings


class PortfolioOptimizerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("📊 Otimizador de Portfólio - Versão Desktop Completa")
        self.root.geometry("1400x900")
        
        # Variáveis de dados
        self.df = None
        self.optimizer = None
        self.result = None
        self.has_risk_free = False
        self.risk_free_column_name = None
        self.detected_risk_free_rate = 0.0
        
        # Variáveis para restrições individuais
        self.individual_constraints = {}
        self.constraint_widgets = {}
        
        # Variáveis para short selling
        self.short_weights = {}
        self.short_widgets = {}
        self.individual_constraints = {}
        
        # NOVO: Variáveis para tabelas mensais
        self.monthly_table = None
        self.excess_table = None

        # NOVO: Variáveis para janelas temporais
        self.dados_brutos = None           # Dados originais completos
        self.periodo_disponivel = None     # Info do período total disponível
        self.df_otimizacao = None         # Dados processados para otimização
        self.df_analise = None            # Dados processados para análise estendida
        self.periodo_otimizacao = None    # Datas da janela de otimização
        self.periodo_analise = None       # Datas da janela de análise
        
        # Configurar interface
        self.setup_ui()
        
    def setup_ui(self):
        """Criar interface do usuário"""
        # Notebook para organizar abas
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Aba 1: Carregar Dados
        self.tab_data = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_data, text="📁 Dados")
        self.setup_data_tab()
        
        # Aba 2: Configuração Básica
        self.tab_config = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_config, text="⚙️ Configuração")
        self.setup_config_tab()
        
        # Aba 3: Restrições Avançadas
        self.tab_advanced = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_advanced, text="🔧 Avançado")
        self.setup_advanced_tab()
        
        # Aba 4: Short Selling
        self.tab_short = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_short, text="🔄 Short/Hedge")
        self.setup_short_tab()
        
        # NOVA Aba 5: Ranking
        self.tab_ranking = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_ranking, text="🏆 Ranking")
        self.setup_ranking_tab()
        
        # Aba 6: Resultados (mudou de 5 para 6)
        self.tab_results = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_results, text="📈 Resultados")
        self.setup_results_tab()
        
        # Aba 7: Tabelas Mensais (mudou de 6 para 7)
        self.tab_monthly = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_monthly, text="📅 Retornos Mensais")
        self.setup_monthly_tab()

        # Aba 8: Auto-Otimização
        self.tab_auto = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_auto, text="🤖 Auto-Otimização")
        self.setup_auto_optimization_tab()
        
    def setup_data_tab(self):
        """Configurar aba de carregamento de dados - LAYOUT 50/50 + CORREÇÃO DADOS"""
        
        # Frame principal
        main_frame = ttk.Frame(self.tab_data)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # ========== LAYOUT HORIZONTAL 50/50 ==========
        horizontal_frame = ttk.Frame(main_frame)
        horizontal_frame.pack(fill='both', expand=True)
        
        # COLUNA ESQUERDA - Configurações (50%)
        left_frame = ttk.Frame(horizontal_frame)
        left_frame.pack(side='left', fill='both', expand=True, padx=(0,5))
        
        # COLUNA DIREITA - Seleção de Ativos (50%)  
        right_frame = ttk.Frame(horizontal_frame)
        right_frame.pack(side='right', fill='both', expand=True, padx=(5,0))
        
        # ========== COLUNA ESQUERDA - CONFIGURAÇÕES ==========
        
        # Frame para carregar dados
        load_frame = ttk.LabelFrame(left_frame, text="Carregar Dados", padding="10")
        load_frame.pack(fill='x', pady=(0,10))
        
        # Botão para carregar arquivo
        ttk.Button(
            load_frame, 
            text="📂 Carregar Planilha Excel", 
            command=self.load_excel_file,
            width=30
        ).pack(pady=10)
        
        # Frame para mostrar info do arquivo - REFERÊNCIA ESTÁVEL
        self.info_frame = ttk.LabelFrame(left_frame, text="Informações do Arquivo", padding="10")
        self.info_frame.pack(fill='x', pady=(0,10))
        
        # Label para mostrar status - REFERÊNCIA ESTÁVEL
        self.status_label = ttk.Label(self.info_frame, text="Nenhum arquivo carregado", wraplength=400)
        self.status_label.pack(pady=5, fill='x')
        
        # Frame para taxa de referência detectada - REFERÊNCIA ESTÁVEL
        self.risk_free_frame = ttk.LabelFrame(self.info_frame, text="Taxa de Referência Detectada", padding="5")
        self.risk_free_frame.pack(fill='x', pady=10)
        
        self.risk_free_info = ttk.Label(self.risk_free_frame, text="Nenhuma taxa detectada")
        self.risk_free_info.pack(pady=5)
        
        # Frame para janelas temporais - REFERÊNCIA ESTÁVEL
        self.temporal_frame = ttk.LabelFrame(left_frame, text="📅 Configurar Janelas Temporais", padding="10")
        self.temporal_frame.pack(fill='both', expand=True, pady=(0,10))
        
        # Label de instruções
        instruction_label = ttk.Label(self.temporal_frame, 
                                     text="🎯 Configure as 3 datas críticas para análise:", 
                                     font=('TkDefaultFont', 10, 'bold'))
        instruction_label.pack(anchor='w', pady=(0,10))
        
        # Frame para as 3 datas
        dates_frame = ttk.Frame(self.temporal_frame)
        dates_frame.pack(fill='x', pady=5)
        
        # Layout em coluna única para economizar espaço horizontal
        # Data 1: Início da Otimização
        date1_frame = ttk.Frame(dates_frame)
        date1_frame.pack(fill='x', pady=2)
        ttk.Label(date1_frame, text="📊 Início da Otimização:").pack(side='left')
        self.data_inicio_otim = DateEntry(date1_frame, width=12, background='darkblue',
                                         foreground='white', borderwidth=2,
                                         date_pattern='dd/MM/yyyy')
        self.data_inicio_otim.pack(side='right')
        
        # Data 2: Fim da Otimização  
        date2_frame = ttk.Frame(dates_frame)
        date2_frame.pack(fill='x', pady=2)
        ttk.Label(date2_frame, text="🎯 Fim da Otimização:").pack(side='left')
        self.data_fim_otim = DateEntry(date2_frame, width=12, background='darkblue',
                                      foreground='white', borderwidth=2,
                                      date_pattern='dd/MM/yyyy')
        self.data_fim_otim.pack(side='right')
        
        # Data 3: Fim da Análise
        date3_frame = ttk.Frame(dates_frame)
        date3_frame.pack(fill='x', pady=2)
        ttk.Label(date3_frame, text="📈 Fim da Análise:").pack(side='left')
        self.data_fim_analise = DateEntry(date3_frame, width=12, background='darkblue',
                                         foreground='white', borderwidth=2,
                                         date_pattern='dd/MM/yyyy')
        self.data_fim_analise.pack(side='right')
        
        # Configurar datas padrão
        hoje = datetime.now().date()
        self.data_inicio_otim.set_date(hoje - timedelta(days=365*2))
        self.data_fim_otim.set_date(hoje - timedelta(days=365))      
        self.data_fim_analise.set_date(hoje)
        
        # Checkbox para usar validação
        self.usar_validacao = tk.BooleanVar(value=True)
        validation_check = ttk.Checkbutton(self.temporal_frame, 
                                          text="✅ Usar validação (forward test)", 
                                          variable=self.usar_validacao,
                                          command=self.toggle_validacao)
        validation_check.pack(anchor='w', pady=5)
        
        # Conectar eventos de mudança de data
        self.data_inicio_otim.bind("<<DateEntrySelected>>", self.atualizar_metricas_janelas)
        self.data_fim_otim.bind("<<DateEntrySelected>>", self.atualizar_metricas_janelas)
        self.data_fim_analise.bind("<<DateEntrySelected>>", self.atualizar_metricas_janelas)
        
        # Frame para métricas das janelas - REFERÊNCIA ESTÁVEL
        self.metricas_frame = ttk.Frame(self.temporal_frame)
        self.metricas_frame.pack(fill='x', pady=10)
        
        # Labels para mostrar informações das janelas - REFERÊNCIA ESTÁVEL
        self.info_otimizacao = ttk.Label(self.metricas_frame, text="📊 Configure as datas acima", wraplength=300)
        self.info_otimizacao.pack(anchor='w')
        
        # Botão para processar período - REFERÊNCIA ESTÁVEL
        self.processar_btn = ttk.Button(self.temporal_frame, 
                                       text="⚡ Processar Período Selecionado", 
                                       command=self.processar_periodo,
                                       state='disabled')
        self.processar_btn.pack(pady=20)
        
        # Label de status do processamento - REFERÊNCIA ESTÁVEL
        self.status_processamento = ttk.Label(self.temporal_frame, text="", wraplength=300)
        self.status_processamento.pack(pady=10)
        
        # ========== COLUNA DIREITA - SELEÇÃO DE ATIVOS ==========
        
        # Frame para seleção de ativos - SEMPRE VISÍVEL NA DIREITA
        assets_frame = ttk.LabelFrame(right_frame, text="📋 Seleção de Ativos", padding="10")
        assets_frame.pack(fill='both', expand=True)
        
        ttk.Label(assets_frame, text="Selecione os ativos:", font=('TkDefaultFont', 9, 'bold')).pack(anchor='w', pady=(0,5))
        ttk.Label(assets_frame, text="(Ctrl+clique para múltiplos)", font=('TkDefaultFont', 8)).pack(anchor='w', pady=(0,10))
        
        # Frame para listbox com scrollbar
        listbox_frame = ttk.Frame(assets_frame)
        listbox_frame.pack(fill='both', expand=True, pady=5)
        
        self.assets_listbox = tk.Listbox(listbox_frame, selectmode='extended')
        scrollbar_assets = ttk.Scrollbar(listbox_frame, orient='vertical', command=self.assets_listbox.yview)
        self.assets_listbox.configure(yscrollcommand=scrollbar_assets.set)
        
        self.assets_listbox.pack(side='left', fill='both', expand=True)
        scrollbar_assets.pack(side='right', fill='y')
        
        # Botões de seleção rápida
        button_frame = ttk.Frame(assets_frame)
        button_frame.pack(fill='x', pady=(10,0))
        
        ttk.Button(button_frame, text="✅ Todos", command=self.select_all_assets, width=12).pack(side='left', padx=(0,5))
        ttk.Button(button_frame, text="❌ Limpar", command=self.clear_selection, width=12).pack(side='left')
        
        # Info de seleção - REFERÊNCIA ESTÁVEL
        self.selection_info = ttk.Label(assets_frame, text="", font=('TkDefaultFont', 8), foreground='blue')
        self.selection_info.pack(pady=(5,0))
        
        # Função para atualizar info de seleção - REFERÊNCIA ESTÁVEL
        def update_selection_info(event=None):
            try:
                selected_count = len(self.assets_listbox.curselection())
                total_count = self.assets_listbox.size()
                if total_count > 0:
                    self.selection_info.config(text=f"Selecionados: {selected_count}/{total_count}")
                else:
                    self.selection_info.config(text="Carregue dados primeiro")
            except tk.TclError:
                # Widget foi destruído, ignorar
                pass
        
        # Salvar referência da função para uso posterior
        self.update_selection_info = update_selection_info
        
        # Bind para atualizar info de seleção
        self.assets_listbox.bind('<<ListboxSelect>>', update_selection_info)
        
        # Atualizar info inicial
        update_selection_info()

    def toggle_validacao(self):
        """Toggle para habilitar/desabilitar validação"""
        if self.usar_validacao.get():
            self.data_fim_analise.config(state='normal')
        else:
            self.data_fim_analise.config(state='disabled')

    def processar_periodo(self):
        """Processar período selecionado - VERSÃO SIMPLIFICADA igual ao Streamlit"""
        if self.dados_brutos is None:
            messagebox.showerror("Erro", "Carregue dados primeiro!")
            return
        
        try:
            # Obter datas selecionadas
            data_inicio_otim = pd.to_datetime(self.data_inicio_otim.get(), format='%d/%m/%Y')
            data_fim_otim = pd.to_datetime(self.data_fim_otim.get(), format='%d/%m/%Y')

            # Verificar se vai usar validação
            if self.usar_validacao.get():
                data_fim_analise = pd.to_datetime(self.data_fim_analise.get(), format='%d/%m/%Y')
            else:
                data_fim_analise = None
            
            # Validações básicas
            if data_inicio_otim >= data_fim_otim:
                messagebox.showerror("Erro", "Data de início deve ser anterior à data fim!")
                return
            
            if data_fim_analise and data_fim_analise <= data_fim_otim:
                messagebox.showerror("Erro", "Data fim da análise deve ser posterior ao fim da otimização!")
                return
            
            # Mostrar progresso
            self.status_processamento.config(text="🔄 Processando dados...", foreground='blue')
            self.processar_btn.config(state='disabled')
            self.root.update()
            
            # ========== PROCESSAMENTO IGUAL AO STREAMLIT ==========
            
            # 1. Configurar dados
            if 'Data' in self.dados_brutos.columns:
                df_trabalho = self.dados_brutos.copy()
                df_trabalho['Data'] = pd.to_datetime(df_trabalho['Data'])
                df_trabalho = df_trabalho.set_index('Data')
            else:
                df_trabalho = self.dados_brutos.copy()
                if not isinstance(df_trabalho.index, pd.DatetimeIndex):
                    df_trabalho.index = pd.to_datetime(df_trabalho.index)
            
            # 2. Filtrar período para otimização
            df_otimizacao = df_trabalho[(df_trabalho.index >= data_inicio_otim) & 
                                       (df_trabalho.index <= data_fim_otim)].copy()
            
            # 3. Se tem data de análise, pegar período estendido
            df_analise_estendida = None
            if data_fim_analise and data_fim_analise > data_fim_otim:
                df_analise_estendida = df_trabalho[(df_trabalho.index >= data_inicio_otim) & 
                                                  (df_trabalho.index <= data_fim_analise)].copy()
            
            # 4. Converter para base 0 - período de otimização
            df_base0_otimizacao, cols_removidas_otim = self.transformar_base_zero(df_otimizacao)
            
            # 5. Converter para base 0 - período estendido (se aplicável)
            df_base0_analise = None
            if df_analise_estendida is not None:
                df_base0_analise, _ = self.transformar_base_zero(df_analise_estendida)
            
            # 6. Adicionar coluna de data de volta
            if df_base0_otimizacao is not None:
                df_base0_otimizacao = df_base0_otimizacao.reset_index()
                df_base0_otimizacao.rename(columns={'index': 'Data'}, inplace=True)
            
            if df_base0_analise is not None:
                df_base0_analise = df_base0_analise.reset_index()
                df_base0_analise.rename(columns={'index': 'Data'}, inplace=True)
            
            # ========== SALVAR DADOS E ATUALIZAR INTERFACE ==========
            
            if df_base0_otimizacao is not None:
                # Salvar dados processados
                self.df = df_base0_otimizacao
                self.df_otimizacao = df_base0_otimizacao
                self.df_analise = df_base0_analise
                
                # Salvar períodos
                self.periodo_otimizacao = {
                    'inicio': data_inicio_otim,
                    'fim': data_fim_otim
                }
                self.periodo_analise = {
                    'inicio': data_inicio_otim,
                    'fim': data_fim_analise if data_fim_analise else data_fim_otim
                }
                
                # Calcular taxa livre de risco se detectada
                if self.has_risk_free:
                    try:
                        temp_optimizer = PortfolioOptimizer(df_base0_otimizacao, [])
                        if hasattr(temp_optimizer, 'risk_free_rate_total'):
                            self.detected_risk_free_rate = temp_optimizer.risk_free_rate_total
                    except:
                        pass
                
                # ========== ATUALIZAR LISTBOX SEM PERDER SELEÇÕES ==========
                
                # Salvar seleções atuais
                selected_indices = self.assets_listbox.curselection()
                selected_assets = [self.assets_listbox.get(i) for i in selected_indices]
                
                # Reconstruir listbox
                self.assets_listbox.delete(0, tk.END)
                
                # Identificar ativos válidos (excluindo Data e taxa de referência)
                ativos_validos = []
                for col in df_base0_otimizacao.columns:
                    if col != 'Data' and col != self.risk_free_column_name:
                        ativos_validos.append(col)
                
                # Preencher listbox
                for asset in ativos_validos:
                    self.assets_listbox.insert(tk.END, asset)
                
                # RESTAURAR SELEÇÕES (apenas os ativos que ainda existem)
                for i in range(self.assets_listbox.size()):
                    asset = self.assets_listbox.get(i)
                    if asset in selected_assets:
                        self.assets_listbox.selection_set(i)
                
                # Atualizar widgets avançados
                self.update_advanced_widgets()
                
                # Mostrar informações de sucesso
                dias_otim = (data_fim_otim - data_inicio_otim).days
                if data_fim_analise:
                    dias_total = (data_fim_analise - data_inicio_otim).days
                    dias_valid = (data_fim_analise - data_fim_otim).days
                    info_text = f"""✅ Período processado com sucesso!
    📊 Otimização: {dias_otim} dias ({data_inicio_otim.strftime('%d/%m/%Y')} a {data_fim_otim.strftime('%d/%m/%Y')})
    🔍 Validação: {dias_valid} dias (até {data_fim_analise.strftime('%d/%m/%Y')})
    📈 Total: {dias_total} dias | {len(ativos_validos)} ativos disponíveis"""
                else:
                    info_text = f"""✅ Período processado com sucesso!
    📊 Otimização: {dias_otim} dias ({data_inicio_otim.strftime('%d/%m/%Y')} a {data_fim_otim.strftime('%d/%m/%Y')})
    📈 {len(ativos_validos)} ativos disponíveis"""
                
                if cols_removidas_otim:
                    info_text += f"\n⚠️ Removidos: {', '.join(cols_removidas_otim)}"
                
                self.status_processamento.config(text=info_text, foreground='green')
                self.processar_btn.config(state='normal')
                
                messagebox.showinfo("Sucesso", f"🎉 Dados processados!\n🎯 Agora você pode otimizar o portfólio.")
                
                # Mudar para aba de configuração
                self.notebook.select(self.tab_config)
                
            else:
                self.status_processamento.config(text="❌ Erro no processamento", foreground='red')
                self.processar_btn.config(state='normal')
                
        except Exception as e:
            self.status_processamento.config(text="❌ Erro no processamento", foreground='red')
            self.processar_btn.config(state='normal')
            messagebox.showerror("Erro", f"Erro ao processar período:\n{str(e)}")

    def atualizar_datas_automaticas(self):
        """Atualizar datas automaticamente quando carregar arquivo"""
        if self.periodo_disponivel:
            # Calcular datas padrão (70% otimização, 30% validação)
            total_dias = (self.periodo_disponivel['fim'] - self.periodo_disponivel['inicio']).days
            dias_otimizacao = int(total_dias * 0.7)
            
            data_inicio = self.periodo_disponivel['inicio']
            data_fim_otim = data_inicio + timedelta(days=dias_otimizacao)
            data_fim_analise = self.periodo_disponivel['fim']
            
            # Atualizar widgets
            self.data_inicio_otim.set_date(data_inicio.date())
            self.data_fim_otim.set_date(data_fim_otim.date())
            self.data_fim_analise.set_date(data_fim_analise.date())
            
            # Habilitar botão
            self.processar_btn.config(state='normal')
            
            # Atualizar informações
            dias_otim = (data_fim_otim - data_inicio).days
            dias_valid = (data_fim_analise - data_fim_otim).days
            
            info_text = f"""📊 Otimização: {dias_otim} dias ({(dias_otim/total_dias*100):.0f}% do total)
    🔍 Validação: {dias_valid} dias ({(dias_valid/total_dias*100):.0f}% do total)
    📈 Total: {total_dias} dias"""
            
            self.info_otimizacao.config(text=info_text)

    def atualizar_metricas_janelas(self, event=None):
        """Atualizar informações das janelas quando datas mudarem"""
        try:
            data_inicio = self.data_inicio_otim.get_date()
            data_fim_otim = self.data_fim_otim.get_date()
            data_fim_analise = self.data_fim_analise.get_date()
            
            # Calcular dias
            dias_otim = (data_fim_otim - data_inicio).days
            dias_valid = (data_fim_analise - data_fim_otim).days
            dias_total = dias_otim + dias_valid
            
            if dias_total > 0:
                info_text = f"""📊 Otimização: {dias_otim} dias ({(dias_otim/dias_total*100):.0f}% do total)
    🔍 Validação: {dias_valid} dias ({(dias_valid/dias_total*100):.0f}% do total)  
    📈 Total: {dias_total} dias"""
            else:
                info_text = "⚠️ Configure datas válidas"
            
            self.info_otimizacao.config(text=info_text)
            
            # Habilitar botão se dados carregados
            if self.dados_brutos is not None and dias_otim > 0:
                self.processar_btn.config(state='normal')
            else:
                self.processar_btn.config(state='disabled')
                
        except:
            self.info_otimizacao.config(text="⚠️ Configure datas válidas")
            self.processar_btn.config(state='disabled')

    def transformar_base_zero(self, df_precos):
        """
        Transforma dados de preços para base 0 - VERSÃO OTIMIZADA SEM FRAGMENTAÇÃO
        """
        if df_precos is None or df_precos.empty:
            return None, []
        
        df_limpo = df_precos.copy()
        
        # 1. Remove colunas com primeiro valor inválido
        colunas_removidas = []
        for coluna in df_limpo.columns:
            if len(df_limpo[coluna]) == 0:
                colunas_removidas.append(coluna)
                continue
                
            primeiro_valor = df_limpo[coluna].iloc[0]
            if pd.isna(primeiro_valor) or primeiro_valor == 0:
                colunas_removidas.append(coluna)
        
        if colunas_removidas:
            df_limpo = df_limpo.drop(columns=colunas_removidas)
        
        # Verifica se ainda há colunas válidas
        if df_limpo.empty:
            return None, colunas_removidas
        
        # 2. Preenche valores faltantes/zero
        for coluna in df_limpo.columns:
            df_limpo[coluna] = df_limpo[coluna].replace(0, np.nan)
            df_limpo[coluna] = df_limpo[coluna].ffill()
        
        df_limpo = df_limpo.fillna(0)
        
        # 3. Calcula base zero - VERSÃO OTIMIZADA
        # ✅ CORREÇÃO: Criar dicionário primeiro, depois DataFrame uma vez só
        base_zero_data = {}
        
        for coluna in df_limpo.columns:
            valores = df_limpo[coluna].values
            
            if len(valores) == 0:
                continue
                
            cota_1 = valores[0]  # Primeiro valor como referência
            
            if cota_1 == 0:  # Evita divisão por zero
                continue
            
            novos_valores = np.zeros(len(valores))
            novos_valores[0] = 0.0  # Primeiro valor sempre 0
            
            # Calcula os demais: (Preço_n - Preço_{n-1}) / Preço_1
            for i in range(1, len(valores)):
                cota_n = valores[i]
                cota_anterior = valores[i-1]
                novo_valor = (cota_n - cota_anterior) / cota_1
                novos_valores[i] = novo_valor
            
            # ✅ ARMAZENAR NO DICIONÁRIO (não no DataFrame ainda)
            base_zero_data[coluna] = novos_valores
        
        # ✅ CRIAR DATAFRAME UMA VEZ SÓ com todos os dados
        if base_zero_data:
            df_base_zero = pd.DataFrame(base_zero_data, index=df_limpo.index)
            return df_base_zero, colunas_removidas
        else:
            return None, colunas_removidas

    def setup_config_tab(self):
        """Configurar aba de configurações básicas"""
        # Frame principal com scroll
        canvas = tk.Canvas(self.tab_config)
        scrollbar = ttk.Scrollbar(self.tab_config, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 1. Objetivo de Otimização
        obj_frame = ttk.LabelFrame(scrollable_frame, text="🎯 Objetivo de Otimização", padding="10")
        obj_frame.pack(fill='x', padx=10, pady=5)
        
        self.objective_var = tk.StringVar(value="Maximizar Sharpe Ratio")
        
        # Lista COMPLETA de objetivos (como no Streamlit)
        self.base_objectives = [
            "Maximizar Sharpe Ratio",
            "Minimizar Risco",
            "Maximizar Inclinação",
            "Maximizar Inclinação/[(1-R²)×Vol]",
            "Maximizar Qualidade da Linearidade"
        ]
        
        # Objetivos que dependem de taxa livre serão adicionados dinamicamente
        self.risk_free_objectives = [
            "Maximizar Linearidade do Excesso"
        ]
        
        # Criar radiobuttons para objetivos base
        self.objective_buttons = {}
        for obj in self.base_objectives:
            btn = ttk.Radiobutton(obj_frame, text=obj, variable=self.objective_var, value=obj)
            btn.pack(anchor='w')
            self.objective_buttons[obj] = btn
        
        # Placeholder para objetivos de taxa livre
        self.risk_free_obj_frame = ttk.Frame(obj_frame)
        self.risk_free_obj_frame.pack(fill='x', pady=(10,0))
        
        # 2. Limites de Peso Globais
        limits_frame = ttk.LabelFrame(scrollable_frame, text="📊 Limites de Peso Globais", padding="10")
        limits_frame.pack(fill='x', padx=10, pady=5)
        
        # Min weight
        min_frame = ttk.Frame(limits_frame)
        min_frame.pack(fill='x', pady=2)
        ttk.Label(min_frame, text="Peso mínimo por ativo (%):").pack(side='left')
        self.min_weight_var = tk.DoubleVar(value=0.0)
        self.min_weight_label = ttk.Label(min_frame, text="0.0%")
        self.min_weight_label.pack(side='right')
        scale_min = ttk.Scale(limits_frame, from_=0, to=20, variable=self.min_weight_var, orient='horizontal',
                             command=lambda v: self.min_weight_label.config(text=f"{float(v):.1f}%"))
        scale_min.pack(fill='x', pady=2)
        
        # Max weight  
        max_frame = ttk.Frame(limits_frame)
        max_frame.pack(fill='x', pady=2)
        ttk.Label(max_frame, text="Peso máximo por ativo (%):").pack(side='left')
        self.max_weight_var = tk.DoubleVar(value=30.0)
        self.max_weight_label = ttk.Label(max_frame, text="30.0%")
        self.max_weight_label.pack(side='right')
        scale_max = ttk.Scale(limits_frame, from_=5, to=100, variable=self.max_weight_var, orient='horizontal',
                             command=lambda v: self.max_weight_label.config(text=f"{float(v):.1f}%"))
        scale_max.pack(fill='x', pady=2)
        
        # 3. Taxa Livre de Risco
        risk_frame = ttk.LabelFrame(scrollable_frame, text="🏛️ Taxa de Referência", padding="10")
        risk_frame.pack(fill='x', padx=10, pady=5)
        
        # Frame para taxa detectada vs manual
        self.risk_free_display_frame = ttk.Frame(risk_frame)
        self.risk_free_display_frame.pack(fill='x')
        
        # Taxa manual (será escondida se detectar automaticamente)
        manual_frame = ttk.Frame(risk_frame)
        manual_frame.pack(fill='x', pady=5)
        ttk.Label(manual_frame, text="Taxa de referência manual (% acumulada):").pack(anchor='w')
        self.risk_free_var = tk.DoubleVar(value=0.0)
        self.manual_risk_entry = ttk.Entry(manual_frame, textvariable=self.risk_free_var, width=10)
        self.manual_risk_entry.pack(anchor='w', pady=2)

        # 3b. Meta de Retorno (opcional)
        meta_frame = ttk.LabelFrame(scrollable_frame, text="🎯 Meta de Retorno (opcional)", padding="10")
        meta_frame.pack(fill='x', padx=10, pady=5)

        self.use_meta = tk.BooleanVar(value=False)
        ttk.Checkbutton(meta_frame, text="Exigir meta de retorno mínima",
                        variable=self.use_meta).pack(anchor='w')

        meta_row = ttk.Frame(meta_frame)
        meta_row.pack(fill='x', pady=2)
        ttk.Label(meta_row, text="Meta (% acima da referência):").pack(side='left')
        self.meta_var = tk.DoubleVar(value=5.0)
        ttk.Entry(meta_row, textvariable=self.meta_var, width=8).pack(side='left', padx=(5, 0))

        ttk.Label(meta_frame,
                  text="Combina com o objetivo escolhido acima: maximiza o objetivo garantindo retorno "
                       "de PELO MENOS referência × (1 + meta/100) no período (ex.: referência 12% e meta "
                       "5% → alvo 12,6%). Na prática é o menor risco que alcança a meta. "
                       "Se a meta for inatingível, retorna a carteira de MAIOR retorno possível e avisa.",
                  font=('TkDefaultFont', 8), foreground='gray',
                  wraplength=700, justify='left').pack(anchor='w', pady=(5, 0))

        # 4. Botão Otimizar
        ttk.Button(
            scrollable_frame, 
            text="🚀 OTIMIZAR PORTFÓLIO", 
            command=self.optimize_portfolio,
            style="Accent.TButton"
        ).pack(pady=20, ipadx=20, ipady=10)
        
        # Empacotar canvas e scrollbar
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
    def setup_advanced_tab(self):
        """Configurar aba de restrições individuais"""
        frame = ttk.LabelFrame(self.tab_advanced, text="🚫 Restrições Individuais por Ativo", padding="10")
        frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Checkbox para habilitar restrições
        self.use_individual_constraints = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame,
            text="Habilitar limites específicos para ativos selecionados",
            variable=self.use_individual_constraints,
            command=self.toggle_individual_constraints
        ).pack(anchor='w', pady=5)

        # Importar restrições de arquivo Excel/CSV
        import_frame = ttk.Frame(frame)
        import_frame.pack(anchor='w', fill='x', pady=(0,5))
        ttk.Button(
            import_frame,
            text="📂 Importar Restrições (Excel/CSV)",
            command=self.import_constraints_file
        ).pack(side='left')
        ttk.Label(
            frame,
            text="Colunas aceitas: 'Ativo, Min, Max' (faixas) ou 'Ativo, Peso' "
                 "(pesos fixos → analisa o portfólio). Valores em % (ex.: 30 = 30%).",
            font=('TkDefaultFont', 8), foreground='gray', wraplength=700, justify='left'
        ).pack(anchor='w', pady=(0,5))

        # Frame para scroll das restrições
        self.constraints_canvas = tk.Canvas(frame)
        constraints_scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.constraints_canvas.yview)
        self.constraints_frame = ttk.Frame(self.constraints_canvas)
        
        self.constraints_frame.bind(
            "<Configure>",
            lambda e: self.constraints_canvas.configure(scrollregion=self.constraints_canvas.bbox("all"))
        )
        
        self.constraints_canvas.create_window((0, 0), window=self.constraints_frame, anchor="nw")
        self.constraints_canvas.configure(yscrollcommand=constraints_scrollbar.set)
        
        self.constraints_canvas.pack(side="left", fill="both", expand=True, pady=10)
        constraints_scrollbar.pack(side="right", fill="y")
        
        # Label inicial
        self.constraints_info = ttk.Label(self.constraints_frame, text="Carregue dados e selecione ativos primeiro")
        self.constraints_info.pack(pady=20)

    def import_constraints_file(self):
        """Importar restrições mín/máx (ou pesos) de um arquivo Excel/CSV."""
        if self.assets_listbox.size() == 0:
            messagebox.showerror("Erro", "Carregue os dados primeiro (aba Dados)!")
            return

        file_path = filedialog.askopenfilename(
            title="Importar restrições (Excel/CSV)",
            filetypes=[("Planilhas", "*.xlsx *.xls *.csv"),
                       ("Excel", "*.xlsx *.xls"),
                       ("CSV", "*.csv"),
                       ("Todos", "*.*")]
        )
        if not file_path:
            return

        try:
            constraints, warnings = load_constraints_from_file(file_path)
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao ler o arquivo:\n{str(e)}")
            return

        self._apply_imported_constraints(constraints, warnings)

    def _apply_imported_constraints(self, constraints, warnings):
        """Casa os ativos do arquivo com os dados, seleciona e ativa as restrições."""
        available = list(self.assets_listbox.get(0, tk.END))
        avail_lower = {a.lower(): a for a in available}

        matched = {}
        not_found = []
        for asset, lim in constraints.items():
            if asset in available:
                matched[asset] = lim
            elif asset.lower() in avail_lower:
                matched[avail_lower[asset.lower()]] = lim
            else:
                not_found.append(asset)

        if not matched:
            exemplos = ', '.join(list(constraints.keys())[:10])
            messagebox.showwarning(
                "Atenção",
                "Nenhum ativo do arquivo corresponde aos ativos carregados.\n"
                f"Ativos no arquivo: {exemplos}")
            return

        # Selecionar exatamente os ativos importados e ativar restrições
        self.use_individual_constraints.set(True)
        self.individual_constraints = matched

        self.assets_listbox.selection_clear(0, tk.END)
        for i in range(self.assets_listbox.size()):
            if self.assets_listbox.get(i) in matched:
                self.assets_listbox.selection_set(i)

        self.update_advanced_widgets()
        try:
            self.update_selection_info()
        except Exception:
            pass

        # Diagnóstico: portfólio (min == max) e soma
        is_portfolio = all(abs(v['min'] - v['max']) < 1e-9 for v in matched.values())
        soma = sum((v['min'] + v['max']) / 2 for v in matched.values()) * 100

        msg = f"✅ {len(matched)} ativos importados e selecionados."
        if is_portfolio:
            msg += f"\n📊 Modo portfólio (pesos fixos). Soma = {soma:.1f}%."
            if abs(soma - 100) < 0.5:
                msg += "\n🎯 Soma ≈ 100%: o software atuará como analisador deste portfólio."
        if not_found:
            extra = ', '.join(not_found[:8]) + ('...' if len(not_found) > 8 else '')
            msg += f"\n⚠️ {len(not_found)} não encontrados nos dados: {extra}"
        if warnings:
            msg += "\n\n" + "\n".join(warnings[:6])
            if len(warnings) > 6:
                msg += "\n..."

        messagebox.showinfo("Importação concluída", msg)

    def setup_short_tab(self):
        """Configurar aba de short selling"""
        frame = ttk.LabelFrame(self.tab_short, text="🔄 Posições Short / Hedge", padding="10")
        frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Checkbox para habilitar shorts
        self.use_short = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame, 
            text="Habilitar posições short/hedge (venda a descoberto)", 
            variable=self.use_short,
            command=self.toggle_short_selling
        ).pack(anchor='w', pady=5)
        
        # Frame para scroll dos shorts
        self.short_canvas = tk.Canvas(frame)
        short_scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.short_canvas.yview)
        self.short_frame = ttk.Frame(self.short_canvas)
        
        self.short_frame.bind(
            "<Configure>",
            lambda e: self.short_canvas.configure(scrollregion=self.short_canvas.bbox("all"))
        )
        
        self.short_canvas.create_window((0, 0), window=self.short_frame, anchor="nw")
        self.short_canvas.configure(yscrollcommand=short_scrollbar.set)
        
        self.short_canvas.pack(side="left", fill="both", expand=True, pady=10)
        short_scrollbar.pack(side="right", fill="y")
        
        # Label inicial
        self.short_info = ttk.Label(self.short_frame, text="Carregue dados e selecione ativos principais primeiro")
        self.short_info.pack(pady=20)

    def setup_ranking_tab(self):
        """Configurar aba de ranking de ativos"""
        # Frame principal com scroll
        canvas = tk.Canvas(self.tab_ranking)
        scrollbar = ttk.Scrollbar(self.tab_ranking, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Título
        ttk.Label(scrollable_frame, text="🏆 Sistema de Ranking de Ativos", 
                 font=('TkDefaultFont', 14, 'bold')).pack(pady=10)
        
        # Checkbox para ativar ranking
        self.use_ranking = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            scrollable_frame, 
            text="🤖 Ativar ranking automático de ativos", 
            variable=self.use_ranking,
            command=self.toggle_ranking
        ).pack(anchor='w', pady=5, padx=20)
        
        # Frame para configurações de peso (inicialmente oculto)
        self.ranking_config_frame = ttk.LabelFrame(scrollable_frame, text="⚙️ Configurar Pesos dos Parâmetros", padding="10")
        
        # Sliders para pesos
        self.peso_inc_var = tk.DoubleVar(value=0.33)
        self.peso_desv_var = tk.DoubleVar(value=0.33)
        self.peso_cor_var = tk.DoubleVar(value=0.33)
        
        # Frame para os sliders
        sliders_frame = ttk.Frame(self.ranking_config_frame)
        sliders_frame.pack(fill='x', pady=10)
        
        # Peso Inclinação
        inc_frame = ttk.Frame(sliders_frame)
        inc_frame.pack(fill='x', pady=5)
        ttk.Label(inc_frame, text="📈 Peso Inclinação:").pack(side='left')
        self.inc_label = ttk.Label(inc_frame, text="0.33")
        self.inc_label.pack(side='right')
        scale_inc = ttk.Scale(inc_frame, from_=0, to=1, variable=self.peso_inc_var, orient='horizontal',
                             command=lambda v: self.inc_label.config(text=f"{float(v):.2f}"))
        scale_inc.pack(fill='x', pady=2)
        
        # Peso Desvio
        desv_frame = ttk.Frame(sliders_frame)
        desv_frame.pack(fill='x', pady=5)
        ttk.Label(desv_frame, text="📊 Peso Estabilidade:").pack(side='left')
        self.desv_label = ttk.Label(desv_frame, text="0.33")
        self.desv_label.pack(side='right')
        scale_desv = ttk.Scale(desv_frame, from_=0, to=1, variable=self.peso_desv_var, orient='horizontal',
                              command=lambda v: self.desv_label.config(text=f"{float(v):.2f}"))
        scale_desv.pack(fill='x', pady=2)
        
        # Peso Correlação
        cor_frame = ttk.Frame(sliders_frame)
        cor_frame.pack(fill='x', pady=5)
        ttk.Label(cor_frame, text="🎯 Peso Correlação:").pack(side='left')
        self.cor_label = ttk.Label(cor_frame, text="0.33")
        self.cor_label.pack(side='right')
        scale_cor = ttk.Scale(cor_frame, from_=0, to=1, variable=self.peso_cor_var, orient='horizontal',
                             command=lambda v: self.cor_label.config(text=f"{float(v):.2f}"))
        scale_cor.pack(fill='x', pady=2)
        
        # Botão para calcular ranking
        ttk.Button(
            self.ranking_config_frame, 
            text="🔄 Calcular Ranking", 
            command=self.calculate_ranking
        ).pack(pady=10)
        
        # Frame para resultados do ranking
        self.ranking_results_frame = ttk.LabelFrame(scrollable_frame, text="📊 Resultados do Ranking", padding="10")
        
        # Label inicial
        self.ranking_status = ttk.Label(self.ranking_results_frame, text="Ative o ranking e clique em 'Calcular Ranking'")
        self.ranking_status.pack(pady=20)
        
        # Empacotar canvas e scrollbar
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
    def toggle_ranking(self):
        """Toggle do sistema de ranking"""
        if self.use_ranking.get():
            self.ranking_config_frame.pack(fill='x', padx=20, pady=10)
            self.ranking_results_frame.pack(fill='both', expand=True, padx=20, pady=10)
        else:
            self.ranking_config_frame.pack_forget()
            self.ranking_results_frame.pack_forget()
    
    def calculate_ranking(self):
        """Calcular ranking dos ativos"""
        if self.df is None:
            tk.messagebox.showerror("Erro", "Carregue dados primeiro!")
            return
        
        try:
            # Pegar pesos
            peso_inc = self.peso_inc_var.get()
            peso_desv = self.peso_desv_var.get()
            peso_cor = self.peso_cor_var.get()
            
            # Calcular ranking
            ranking_result = calculate_asset_ranking(
                self.df, 
                self.risk_free_column_name,
                peso_inc, peso_desv, peso_cor
            )
            
            if ranking_result is not None:
                self.display_ranking_results(ranking_result)
            else:
                self.ranking_status.config(text="❌ Erro ao calcular ranking")
                
        except Exception as e:
            tk.messagebox.showerror("Erro", f"Erro no cálculo: {str(e)}")
    
    def display_ranking_results(self, ranking_result):
        """Exibir resultados do ranking"""
        # Limpar frame anterior
        for widget in self.ranking_results_frame.winfo_children():
            widget.destroy()
        
        df_ranking = ranking_result['ranking']
        
        # Info do ranking
        info_text = f"✅ Ranking calculado: {ranking_result['total_ativos']} ativos\n📊 Referência: {ranking_result['referencia']}"
        ttk.Label(self.ranking_results_frame, text=info_text).pack(pady=5)
        
        # Criar TreeView para mostrar ranking
        columns = ('Posição', 'Ativo', 'Índice', 'Inclinação', 'R²', 'Correlação', 'Desvio')
        self.ranking_tree = ttk.Treeview(self.ranking_results_frame, columns=columns, show='headings', height=15)
        
        for col in columns:
            self.ranking_tree.heading(col, text=col)
            self.ranking_tree.column(col, width=80, anchor='center')
        
        # Inserir dados (top 20)
        for _, row in df_ranking.head(20).iterrows():
            values = (
                int(row['Posição']),
                row['Ativo'],
                f"{row['Índice']:.4f}",
                f"{row['Inclinação_Norm']:.3f}",
                f"{row['R²']:.3f}",
                f"{row['Correlação']:.3f}",
                f"{row['Desvio_Norm']:.3f}"
            )
            self.ranking_tree.insert('', 'end', values=values)
        
        # Scrollbar para TreeView
        tree_scroll = ttk.Scrollbar(self.ranking_results_frame, orient='vertical', command=self.ranking_tree.yview)
        self.ranking_tree.configure(yscrollcommand=tree_scroll.set)
        
        self.ranking_tree.pack(side='left', fill='both', expand=True, pady=10)
        tree_scroll.pack(side='right', fill='y')

        # NOVA SEÇÃO: Seleção Automática por Score
        selection_frame = ttk.LabelFrame(self.ranking_results_frame, text="🎯 Seleção Automática de Ativos", padding="10")
        selection_frame.pack(fill='x', pady=10)
        
        # Frame para range de score
        range_frame = ttk.Frame(selection_frame)
        range_frame.pack(fill='x', pady=5)
        
        # Score mínimo
        min_frame = ttk.Frame(range_frame)
        min_frame.pack(side='left', fill='x', expand=True, padx=(0,5))
        ttk.Label(min_frame, text="📉 Score mínimo:").pack(anchor='w')
        self.score_min_var = tk.DoubleVar(value=0.7)
        ttk.Entry(min_frame, textvariable=self.score_min_var, width=8).pack(anchor='w')
        
        # Score máximo
        max_frame = ttk.Frame(range_frame)
        max_frame.pack(side='left', fill='x', expand=True, padx=(5,0))
        ttk.Label(max_frame, text="📈 Score máximo:").pack(anchor='w')
        self.score_max_var = tk.DoubleVar(value=1.0)
        ttk.Entry(max_frame, textvariable=self.score_max_var, width=8).pack(anchor='w')
        
        # Botão para selecionar
        button_frame = ttk.Frame(selection_frame)
        button_frame.pack(fill='x', pady=10)
        
        ttk.Button(
            button_frame, 
            text="✅ Selecionar Ativos por Score", 
            command=self.select_assets_by_score
        ).pack(side='left')
        
        # Label para mostrar resultado da seleção
        self.selection_result_label = ttk.Label(button_frame, text="")
        self.selection_result_label.pack(side='left', padx=(10,0))
        
        # Salvar resultado para uso posterior
        self.ranking_result = ranking_result

    def select_assets_by_score(self):
        """Selecionar ativos baseado no range de score"""
        if not hasattr(self, 'ranking_result') or self.ranking_result is None:
            tk.messagebox.showerror("Erro", "Calcule o ranking primeiro!")
            return
        
        try:
            score_min = self.score_min_var.get()
            score_max = self.score_max_var.get()
            
            # Validar range
            if score_min > score_max:
                tk.messagebox.showerror("Erro", "Score mínimo deve ser menor que o máximo!")
                return
            
            # Filtrar ativos por range de score
            df_ranking = self.ranking_result['ranking']
            filtered_ranking = df_ranking[
                (df_ranking['Índice'] >= score_min) & 
                (df_ranking['Índice'] <= score_max)
            ]
            
            if len(filtered_ranking) == 0:
                self.selection_result_label.config(
                    text=f"⚠️ Nenhum ativo no range {score_min:.2f} - {score_max:.2f}",
                    foreground='orange'
                )
                return
            
            # Atualizar seleção na listbox da aba de dados
            selected_assets = filtered_ranking['Ativo'].tolist()
            
            # PRESERVAR configurações short antes de limpar
            short_backup = self.short_weights.copy() if hasattr(self, 'short_weights') else {}
            individual_backup = self.individual_constraints.copy() if hasattr(self, 'individual_constraints') else {}
            
            # Limpar seleção atual
            self.assets_listbox.selection_clear(0, tk.END)
            
            # Selecionar novos ativos
            for i in range(self.assets_listbox.size()):
                asset = self.assets_listbox.get(i)
                if asset in selected_assets:
                    self.assets_listbox.selection_set(i)
            
            # Atualizar widgets avançados
            self.update_advanced_widgets()
            
            # RESTAURAR configurações short
            self.short_weights = short_backup
            # Só atualizar se a aba short estiver ativa
            if hasattr(self, 'update_short_summary') and hasattr(self, 'use_short') and self.use_short.get():
                try:
                    self.update_short_summary()
                except tk.TclError:
                    pass  # Ignorar se widgets não existem
            
            # RESTAURAR restrições individuais
            self.individual_constraints = individual_backup
            
            # Mostrar resultado
            avg_score = filtered_ranking['Índice'].mean()
            self.selection_result_label.config(
                text=f"✅ {len(selected_assets)} ativos selecionados (score médio: {avg_score:.3f})",
                foreground='green'
            )
            
            # Mudar para aba de configuração
            self.notebook.select(self.tab_config)
            
        except Exception as e:
            tk.messagebox.showerror("Erro", f"Erro na seleção: {str(e)}")
        
    def setup_results_tab(self):
        """Configurar aba de resultados - Layout limpo para controle total pelo display_results()"""
        
        # Frame único que será totalmente controlado pelo display_results()
        self.chart_frame = ttk.Frame(self.tab_results)
        self.chart_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Label inicial (será removido quando display_results() for chamado)
        initial_label = ttk.Label(
            self.chart_frame, 
            text="Execute uma otimização para ver os resultados",
            font=('TkDefaultFont', 12),
            foreground='gray'
        )
        initial_label.pack(expand=True)
        
        # Inicializar referências como None (serão criadas pelo display_results())
        self.export_csv_btn = None
        self.export_excel_btn = None
        self.portfolio_tree = None
        
    def setup_monthly_tab(self):
        """NOVA: Configurar aba de tabelas mensais"""
        # Frame principal com scroll
        main_frame = ttk.Frame(self.tab_monthly)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Notebook interno para tabelas
        self.monthly_notebook = ttk.Notebook(main_frame)
        self.monthly_notebook.pack(fill='both', expand=True)
        
        # Aba 1: Retornos do Portfólio
        self.tab_portfolio_monthly = ttk.Frame(self.monthly_notebook)
        self.monthly_notebook.add(self.tab_portfolio_monthly, text="📊 Retornos do Portfólio")
        
        # Frame com scroll para tabela do portfólio
        canvas1 = tk.Canvas(self.tab_portfolio_monthly)
        scrollbar1 = ttk.Scrollbar(self.tab_portfolio_monthly, orient="vertical", command=canvas1.yview)
        scrollable_frame1 = ttk.Frame(canvas1)
        
        scrollable_frame1.bind("<Configure>", lambda e: canvas1.configure(scrollregion=canvas1.bbox("all")))
        canvas1.create_window((0, 0), window=scrollable_frame1, anchor="nw")
        canvas1.configure(yscrollcommand=scrollbar1.set)
        
        self.portfolio_monthly_frame = scrollable_frame1
        
        canvas1.pack(side="left", fill="both", expand=True)
        scrollbar1.pack(side="right", fill="y")
        
        # Aba 2: Excesso de Retorno
        self.tab_excess_monthly = ttk.Frame(self.monthly_notebook)
        self.monthly_notebook.add(self.tab_excess_monthly, text="📈 Excesso de Retorno")
        
        # Frame com scroll para tabela do excesso
        canvas2 = tk.Canvas(self.tab_excess_monthly)
        scrollbar2 = ttk.Scrollbar(self.tab_excess_monthly, orient="vertical", command=canvas2.yview)
        scrollable_frame2 = ttk.Frame(canvas2)
        
        scrollable_frame2.bind("<Configure>", lambda e: canvas2.configure(scrollregion=canvas2.bbox("all")))
        canvas2.create_window((0, 0), window=scrollable_frame2, anchor="nw")
        canvas2.configure(yscrollcommand=scrollbar2.set)
        
        self.excess_monthly_frame = scrollable_frame2
        
        canvas2.pack(side="left", fill="both", expand=True)
        scrollbar2.pack(side="right", fill="y")
        
        # Labels iniciais
        ttk.Label(self.portfolio_monthly_frame, text="Execute uma otimização para ver as tabelas mensais").pack(pady=20)
        ttk.Label(self.excess_monthly_frame, text="Execute uma otimização para ver as tabelas mensais").pack(pady=20)
        

    def create_monthly_returns_table_desktop(self, returns_data, weights, dates=None, risk_free_returns=None):
        """
        Cria tabela de retornos mensais - IGUAL AO STREAMLIT
        MÉTODO CORRIGIDO: Usa metodologia BASE 0 + crescimento relativo
        """
        # Calcular retornos diários do portfólio (base 0)
        portfolio_returns_daily = np.dot(returns_data.values, weights)
        
        # Calcular retornos acumulados (base 0) - IGUAL AO OTIMIZADOR
        portfolio_cumulative = np.cumsum(portfolio_returns_daily)
        
        # Usar datas reais se disponíveis, senão simular
        if dates is not None:
            portfolio_df = pd.DataFrame({
                'cumulative': portfolio_cumulative
            }, index=dates)
        else:
            # Simular datas (assumindo dados diários consecutivos)
            start_date = pd.Timestamp('2020-01-01')
            dates = pd.date_range(start=start_date, periods=len(portfolio_cumulative), freq='D')
            portfolio_df = pd.DataFrame({
                'cumulative': portfolio_cumulative
            }, index=dates)
        
        # ========== NOVA METODOLOGIA: BASE 0 MENSAL ==========
        
        # 1. Agrupar por mês e pegar o ÚLTIMO valor de cada mês
        monthly_cumulative = portfolio_df['cumulative'].resample('ME').last()
        
        # 2. Calcular retornos mensais em PERCENTUAIS
        monthly_returns = []
        previous_cumulative = 0  # Começar do zero (base 0)

        for month_date, current_cumulative in monthly_cumulative.items():
            # ✅ NOVO: Retorno percentual do mês
            if previous_cumulative != 0:
                # Crescimento relativo: (novo - antigo) / (1 + antigo)
                monthly_return = (current_cumulative - previous_cumulative) / (1 + previous_cumulative)
            else:
                # Primeiro mês: retorno direto da base 0
                monthly_return = current_cumulative
            
            monthly_returns.append(monthly_return)
            previous_cumulative = current_cumulative
        
        # 3. Criar série com retornos mensais
        monthly_returns_series = pd.Series(monthly_returns, index=monthly_cumulative.index)
        
        # ========== PROCESSAR TAXA LIVRE DE RISCO ==========
        monthly_risk_free = None
        if risk_free_returns is not None:
            # Mesmo processo para taxa livre de risco
            risk_free_cumulative = np.cumsum(risk_free_returns.values)
            
            if dates is not None:
                risk_free_df = pd.DataFrame({
                    'cumulative': risk_free_cumulative
                }, index=dates)
            else:
                risk_free_df = pd.DataFrame({
                    'cumulative': risk_free_cumulative
                }, index=dates)
            
            # Agrupar por mês
            monthly_rf_cumulative = risk_free_df['cumulative'].resample('ME').last()
            
            # Calcular retornos mensais da taxa livre (base 0)
            monthly_rf_returns = []
            previous_rf_cumulative = 0
            
            for month_date, current_rf_cumulative in monthly_rf_cumulative.items():
                monthly_rf_return = current_rf_cumulative - previous_rf_cumulative
                monthly_rf_returns.append(monthly_rf_return)
                previous_rf_cumulative = current_rf_cumulative
            
            monthly_risk_free = pd.Series(monthly_rf_returns, index=monthly_rf_cumulative.index)
        
        # ========== CRIAR TABELA PIVOTADA ==========
        
        # Criar DataFrame para pivotar
        monthly_df = pd.DataFrame({
            'Year': monthly_returns_series.index.year,
            'Month': monthly_returns_series.index.month,
            'Return': monthly_returns_series.values
        })
        
        # Pivotar para ter anos nas linhas e meses nas colunas
        pivot_table = monthly_df.pivot(index='Year', columns='Month', values='Return')
        
        # Renomear colunas para nomes dos meses
        month_names = {
            1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr', 5: 'Mai', 6: 'Jun',
            7: 'Jul', 8: 'Ago', 9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez'
        }
        pivot_table.columns = [month_names.get(col, f'M{col}') for col in pivot_table.columns]
        
        # ========== CALCULAR TOTAL ANUAL CORRIGIDO ==========
        
        # ✅ NOVA METODOLOGIA: Multiplicação composta dos retornos percentuais
        yearly_returns = []
        for year in pivot_table.index:
            year_data = pivot_table.loc[year].dropna()
            if len(year_data) > 0:
                # Para percentuais: multiplicação composta (1+r1)*(1+r2)*...*(1+rn) - 1
                annual_return = 1.0
                for monthly_return in year_data:
                    annual_return *= (1 + monthly_return)
                annual_return -= 1  # Subtrair 1 para ter o ganho líquido
                yearly_returns.append(annual_return)
            else:
                yearly_returns.append(np.nan)
        
        pivot_table['Total Anual'] = yearly_returns
        
        # ========== TABELA DE COMPARAÇÃO (SE HÁ TAXA LIVRE) ==========
        
        comparison_table = None
        if monthly_risk_free is not None:
            # Criar tabela similar para taxa livre
            rf_monthly_df = pd.DataFrame({
                'Year': monthly_risk_free.index.year,
                'Month': monthly_risk_free.index.month,
                'Return': monthly_risk_free.values
            })
            
            rf_pivot = rf_monthly_df.pivot(index='Year', columns='Month', values='Return')
            rf_pivot.columns = [month_names.get(col, f'M{col}') for col in rf_pivot.columns]
            
            # Calcular total anual da taxa livre (soma simples - base 0)
            rf_yearly = []
            for year in rf_pivot.index:
                year_data = rf_pivot.loc[year].dropna()
                if len(year_data) > 0:
                    annual_return = year_data.sum()  # Soma simples para base 0
                    rf_yearly.append(annual_return)
                else:
                    rf_yearly.append(np.nan)
            
            rf_pivot['Total Anual'] = rf_yearly
            
            # Criar tabela de comparação (excesso de retorno)
            comparison_table = pivot_table - rf_pivot
        
        return pivot_table, comparison_table
        
    def display_monthly_tables(self):
        """Exibir tabelas de retornos mensais - PERÍODO COMPLETO"""
        if not self.result or not self.result['success']:
            return
        
        try:
            # ========== USAR PERÍODO COMPLETO ==========
            # Verificar se há dados de validação (igual ao Streamlit)
            if hasattr(self, 'df_analise') and self.df_analise is not None:
                # Determinar ativos usados na otimização
                selected_assets = self.get_selected_assets()
                
                # Verificar se usou shorts
                if hasattr(self, 'use_short') and self.use_short.get() and hasattr(self, 'short_weights'):
                    short_assets = list(self.short_weights.keys())
                    assets_used_in_optimization = selected_assets + short_assets
                else:
                    assets_used_in_optimization = selected_assets
                
                # Criar otimizador com dados COMPLETOS
                optimizer_to_use = PortfolioOptimizer(self.df_analise, assets_used_in_optimization)
                period_label = "Período Completo (Otimização + Validação)"
            else:
                # Usar dados apenas do período de otimização
                optimizer_to_use = self.optimizer
                period_label = "Período de Otimização"
            
            # Criar tabelas mensais com DADOS CORRETOS
            dates = getattr(optimizer_to_use, 'dates', None)
            risk_free_returns = getattr(optimizer_to_use, 'risk_free_returns', None)
            
            self.monthly_table, self.excess_table = self.create_monthly_returns_table_desktop(
                optimizer_to_use.returns_data, 
                self.result['weights'],
                dates,
                risk_free_returns
            )
            
            # Limpar frames anteriores
            for widget in self.portfolio_monthly_frame.winfo_children():
                widget.destroy()
            for widget in self.excess_monthly_frame.winfo_children():
                widget.destroy()
            
            # ========== INFORMAÇÕES DO PERÍODO ==========
            # Adicionar informações do período (igual ao Streamlit)
            if hasattr(self, 'df_analise') and self.df_analise is not None:
                # Com validação
                periodo_otim = self.periodo_otimizacao
                periodo_analise = self.periodo_analise
                
                info_frame = ttk.Frame(self.portfolio_monthly_frame)
                info_frame.pack(fill='x', pady=(0,10))
                
                ttk.Label(info_frame, 
                         text=f"📊 Período: {periodo_otim['inicio'].strftime('%d/%m/%Y')} a {periodo_analise['fim'].strftime('%d/%m/%Y')}",
                         font=('TkDefaultFont', 10, 'bold')).pack(side='left')
                
                ttk.Label(info_frame, 
                         text="🔍 Incluindo: Otimização + Validação (período completo)",
                         foreground='blue').pack(side='right')
            else:
                # Sem validação
                periodo_otim = self.periodo_otimizacao
                
                info_frame = ttk.Frame(self.portfolio_monthly_frame)
                info_frame.pack(fill='x', pady=(0,10))
                
                ttk.Label(info_frame, 
                         text=f"📊 Período: {periodo_otim['inicio'].strftime('%d/%m/%Y')} a {periodo_otim['fim'].strftime('%d/%m/%Y')}",
                         font=('TkDefaultFont', 10, 'bold')).pack(side='left')
                
                ttk.Label(info_frame, 
                         text="⚠️ Apenas: Período de otimização",
                         foreground='orange').pack(side='right')
            
            # Criar tabela do portfólio
            self.create_table_widget(self.portfolio_monthly_frame, self.monthly_table, "Retornos Mensais do Portfólio (%)")
            
            # Criar tabela do excesso se disponível
            if self.excess_table is not None:
                self.create_table_widget(self.excess_monthly_frame, self.excess_table, "Excesso de Retorno Mensal (%)")
            else:
                ttk.Label(self.excess_monthly_frame, text="Não disponível (sem taxa de referência detectada)").pack(pady=20)
                
        except Exception as e:
            ttk.Label(self.portfolio_monthly_frame, text=f"Erro ao gerar tabelas: {str(e)}").pack(pady=20)
            ttk.Label(self.excess_monthly_frame, text=f"Erro ao gerar tabelas: {str(e)}").pack(pady=20)
    
    def create_table_widget(self, parent, data_df, title):
        """Criar widget de tabela com cores para uma DataFrame"""
        # Título
        ttk.Label(parent, text=title, font=('TkDefaultFont', 12, 'bold')).pack(pady=(10,5))
        
        # Frame para tabela
        table_frame = ttk.Frame(parent)
        table_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Preparar dados formatados
        display_data = data_df.copy()
        for col in display_data.columns:
            display_data[col] = display_data[col].apply(
                lambda x: f"{x:.2%}" if pd.notna(x) else "-"
            )
        
        # Criar Treeview
        columns = ['Ano'] + list(display_data.columns)
        tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=12)
        
        # Configurar cabeçalhos
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=80, anchor='center')
        
        # Inserir dados
        for year, row in display_data.iterrows():
            values = [str(year)] + [str(val) for val in row]
            item = tree.insert('', 'end', values=values)
            
            # Colorir baseado nos valores (aproximação)
            try:
                # Verificar se maioria dos valores são positivos (verde) ou negativos (vermelho)
                numeric_values = []
                for val in row:
                    if val != "-" and pd.notna(val):
                        # Extrair valor numérico da string formatada
                        if isinstance(val, str) and '%' in val:
                            numeric_val = float(val.replace('%', '')) / 100
                        else:
                            numeric_val = float(val)
                        numeric_values.append(numeric_val)
                
                if numeric_values:
                    avg_return = sum(numeric_values) / len(numeric_values)
                    if avg_return > 0:
                        # Configurar tags para cores (se suportado pelo sistema)
                        tree.set(item, 'Ano', f"📈 {year}")
                    elif avg_return < 0:
                        tree.set(item, 'Ano', f"📉 {year}")
            except:
                pass  # Ignorar erros de formatação
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        h_scrollbar = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        # Layout da tabela
        tree.grid(row=0, column=0, sticky='nsew')
        v_scrollbar.grid(row=0, column=1, sticky='ns')
        h_scrollbar.grid(row=1, column=0, sticky='ew')
        
        # Configurar peso das colunas/linhas
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        
    def export_csv(self):
        """Exportar CSV - TODAS AS COLUNAS DA TABELA"""
        if not self.result or not self.result['success']:
            messagebox.showerror("Erro", "Execute uma otimização primeiro!")
            return
        
        try:
            # Diálogo para salvar
            filename = filedialog.asksaveasfilename(
                title="Salvar Composição do Portfólio",
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv")]
            )
            
            if filename:
                # 🔥 USAR OS MESMOS DADOS DA TABELA VISUAL
                portfolio_summary = self.get_portfolio_summary_desktop(
                    self.result['weights'], 
                    self.result['assets'],
                    self.optimizer.returns_data
                )
                
                # Exportar exatamente como está na tabela (4 colunas)
                portfolio_summary.to_csv(filename, index=False)
                
                messagebox.showinfo("Sucesso", f"CSV exportado com todas as colunas!\n{filename}")
                    
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao exportar CSV:\n{str(e)}")

    def export_excel(self):
        """Exportar Excel - TODAS AS COLUNAS DA TABELA"""
        if not self.result or not self.result['success']:
            messagebox.showerror("Erro", "Execute uma otimização primeiro!")
            return
        
        try:
            # Diálogo para salvar
            filename = filedialog.asksaveasfilename(
                title="Salvar Composição do Portfólio",
                defaultextension=".xlsx",
                filetypes=[("Excel files", "*.xlsx")]
            )
            
            if filename:
                # 🔥 USAR OS MESMOS DADOS DA TABELA VISUAL
                portfolio_summary = self.get_portfolio_summary_desktop(
                    self.result['weights'], 
                    self.result['assets'],
                    self.optimizer.returns_data
                )
                
                # Exportar exatamente como está na tabela (4 colunas)
                portfolio_summary.to_excel(filename, index=False)
                
                messagebox.showinfo("Sucesso", f"Excel exportado com todas as colunas!\n{filename}")
                    
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao exportar Excel:\n{str(e)}")
    
    def prepare_export_data(self):
        """Preparar dados da composição do portfólio para export"""
        # Obter todos os pesos (incluindo negativos)
        all_weights = self.result['weights']
        export_list = []
        
        for i, asset in enumerate(self.result['assets']):
            weight = all_weights[i]
            if abs(weight) > 0.001:  # Incluir pesos > 0.1%
                export_list.append({
                    'Ativo': asset,
                    'Peso_Decimal': weight,
                    'Peso_Percentual': weight * 100,
                    'Tipo': 'LONG' if weight > 0 else 'SHORT'
                })
        
        return pd.DataFrame(export_list)
    
    def prepare_metrics_export(self):
        """Preparar métricas do portfólio para export"""
        metrics = self.result['metrics']
        
        metrics_list = [
            {'Métrica': 'Retorno Total', 'Valor': metrics['gv_final'], 'Formato': f"{metrics['gv_final']:.4f}"},
            {'Métrica': 'Retorno Anualizado', 'Valor': metrics['annual_return'], 'Formato': f"{metrics['annual_return']:.4f}"},
            {'Métrica': 'Volatilidade', 'Valor': metrics['volatility'], 'Formato': f"{metrics['volatility']:.4f}"},
            {'Métrica': 'Sharpe Ratio', 'Valor': metrics['sharpe_ratio'], 'Formato': f"{metrics['sharpe_ratio']:.4f}"},
            {'Métrica': 'Downside Deviation', 'Valor': metrics['downside_deviation'], 'Formato': f"{metrics['downside_deviation']:.4f}"},
            {'Métrica': 'Excesso de Retorno', 'Valor': metrics['excess_return'], 'Formato': f"{metrics['excess_return']:.4f}"},
            {'Métrica': 'R²', 'Valor': metrics['r_squared'], 'Formato': f"{metrics['r_squared']:.4f}"},
            {'Métrica': 'VaR 95% Diário', 'Valor': metrics['var_95_daily'], 'Formato': f"{metrics['var_95_daily']:.4f}"},
            {'Métrica': 'CVaR 95% Diário', 'Valor': metrics['cvar_95_daily'], 'Formato': f"{metrics['cvar_95_daily']:.4f}"},
            {'Métrica': 'Taxa de Referência', 'Valor': metrics['risk_free_rate'], 'Formato': f"{metrics['risk_free_rate']:.4f}"},
        ]
        
        # Adicionar métricas do excesso se disponíveis
        if self.objective_var.get() == "Maximizar Linearidade do Excesso" and metrics.get('excess_r_squared') is not None:
            if hasattr(self.optimizer, 'risk_free_returns') and self.optimizer.risk_free_returns is not None:
                excess_returns_daily = metrics['portfolio_returns_daily'] - self.optimizer.risk_free_returns.values
                excess_vol = np.std(excess_returns_daily, ddof=0) * np.sqrt(252)
                
                metrics_list.extend([
                    {'Métrica': 'R² do Excesso', 'Valor': metrics['excess_r_squared'], 'Formato': f"{metrics['excess_r_squared']:.4f}"},
                    {'Métrica': 'Volatilidade do Excesso', 'Valor': excess_vol, 'Formato': f"{excess_vol:.4f}"},
                ])
        
        return pd.DataFrame(metrics_list)
        
    def load_excel_file(self):
        """Carregar arquivo Excel e salvar dados BRUTOS (sem processar)"""
        file_path = filedialog.askopenfilename(
            title="Selecionar planilha Excel",
            filetypes=[("Excel files", "*.xlsx *.xls")]
        )
        
        if file_path:
            try:
                # Carregar dados BRUTOS (sem processar)
                self.dados_brutos = pd.read_excel(file_path)
                
                # Normalizar: primeira coluna sempre "Data"
                if len(self.dados_brutos.columns) > 0:
                    self.dados_brutos.columns.values[0] = "Data"
               
                # Reset variáveis de processamento
                self.df = None
                self.df_otimizacao = None
                self.df_analise = None
                self.has_risk_free = False
                self.risk_free_column_name = None
                self.detected_risk_free_rate = 0.0
                
                # Identificar período disponível
                if 'Data' in self.dados_brutos.columns:
                    try:
                        datas = pd.to_datetime(self.dados_brutos['Data'])
                        self.periodo_disponivel = {
                            'inicio': datas.min(),
                            'fim': datas.max(),
                            'total_dias': len(datas)
                        }
                    except:
                        self.periodo_disponivel = None
                
                # Detectar taxa livre de risco (mesma lógica anterior)
                if len(self.dados_brutos.columns) > 2 and isinstance(self.dados_brutos.columns[1], str):
                    col_name = self.dados_brutos.columns[1].lower()
                    if any(term in col_name for term in ['taxa', 'livre', 'risco', 'ibov', 'ref', 'cdi', 'selic']):
                        self.has_risk_free = True
                        self.risk_free_column_name = self.dados_brutos.columns[1]
                        asset_columns = self.dados_brutos.columns[2:].tolist()
                    else:
                        asset_columns = self.dados_brutos.columns[1:].tolist()
                else:
                    asset_columns = self.dados_brutos.columns[1:].tolist()
                
                # Atualizar interface
                file_name = os.path.basename(file_path)
                if self.periodo_disponivel:
                    status_text = f"""✅ Arquivo: {file_name}
    📊 Dimensões: {self.dados_brutos.shape[0]} linhas x {self.dados_brutos.shape[1]} colunas
    📅 Período: {self.periodo_disponivel['inicio'].strftime('%d/%m/%Y')} a {self.periodo_disponivel['fim'].strftime('%d/%m/%Y')}
    🗓️ Total: {self.periodo_disponivel['total_dias']} dias"""
                else:
                    status_text = f"✅ Arquivo: {file_name}\n📊 Dimensões: {self.dados_brutos.shape[0]} linhas x {self.dados_brutos.shape[1]} colunas"
                
                self.status_label.config(text=status_text)
                
                # Atualizar info da taxa livre
                if self.has_risk_free:
                    risk_text = f"✅ Detectada: '{self.risk_free_column_name}'"
                    self.risk_free_info.config(text=risk_text, foreground='green')
                    self.manual_risk_entry.config(state='disabled')
                    self.update_objective_options()
                else:
                    self.risk_free_info.config(text="❌ Nenhuma taxa detectada", foreground='red')
                    self.manual_risk_entry.config(state='normal')
                
                # Preencher listbox de ativos
                self.assets_listbox.delete(0, tk.END)
                for asset in asset_columns:
                    self.assets_listbox.insert(tk.END, asset)
                
                # Resetar widgets avançados
                self.update_advanced_widgets()

                # Atualizar datas automaticamente
                self.atualizar_datas_automaticas()

                messagebox.showinfo("Sucesso", f"📥 Dados brutos carregados!\n🎯 Agora configure as janelas temporais.")
                
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao carregar arquivo:\n{str(e)}")
                
    def update_objective_options(self):
        """Atualizar opções de objetivo baseado na taxa livre"""
        # Limpar objetivos de taxa livre anteriores
        for widget in self.risk_free_obj_frame.winfo_children():
            widget.destroy()
        
        if self.has_risk_free:
            # Adicionar separador
            ttk.Separator(self.risk_free_obj_frame, orient='horizontal').pack(fill='x', pady=5)
            ttk.Label(self.risk_free_obj_frame, text="Objetivos com Taxa de Referência:", 
                     font=('TkDefaultFont', 9, 'bold')).pack(anchor='w')
            
            # Adicionar objetivos de taxa livre
            for obj in self.risk_free_objectives:
                btn = ttk.Radiobutton(self.risk_free_obj_frame, text=obj, variable=self.objective_var, value=obj)
                btn.pack(anchor='w')
                self.objective_buttons[obj] = btn
    
    def update_advanced_widgets(self):
        """Atualizar widgets de restrições e shorts"""
        self.update_constraints_widgets()
        self.update_short_widgets()
    
    def update_constraints_widgets(self):
        """Atualizar widgets de restrições individuais com seleção em janela"""
        # Preservar configurações existentes
        existing_constraints = getattr(self, 'individual_constraints', {}).copy()
        
        # Limpar widgets existentes
        for widget in self.constraints_frame.winfo_children():
            widget.destroy()
        self.constraint_widgets.clear()
        
        if not self.use_individual_constraints.get():
            self.constraints_info = ttk.Label(self.constraints_frame, text="Habilite as restrições individuais acima")
            self.constraints_info.pack(pady=20)
            return
            
        selected_assets = self.get_selected_assets()
        if len(selected_assets) < 2:
            self.constraints_info = ttk.Label(self.constraints_frame, text="Selecione pelo menos 2 ativos na aba Dados")
            self.constraints_info.pack(pady=20)
            return
        
        # Interface simplificada com botão para seleção
        ttk.Label(self.constraints_frame, text="Configure limites específicos por ativo:", 
                 font=('TkDefaultFont', 10, 'bold')).pack(anchor='w', pady=(0,10))
        
        # Botão para abrir janela de seleção
        ttk.Button(
            self.constraints_frame, 
            text="📋 Configurar Restrições Individuais", 
            command=lambda: self.open_constraints_window(selected_assets)
        ).pack(pady=10)
        
        # Frame para mostrar restrições configuradas
        self.constraints_summary_frame = ttk.LabelFrame(self.constraints_frame, text="Restrições Configuradas")
        self.constraints_summary_frame.pack(fill='both', expand=True, pady=10)
        
        # Restaurar configurações se existiam
        if existing_constraints and self.use_individual_constraints.get():
            self.individual_constraints = existing_constraints
            try:
                self.update_constraints_summary()
            except (AttributeError, tk.TclError):
                pass
        else:
            # Label inicial
            ttk.Label(self.constraints_summary_frame, text="Nenhuma restrição individual configurada").pack(pady=10)

    def open_constraints_window(self, selected_assets):
        """Abrir janela para configuração de restrições individuais"""
        # Criar janela popup
        popup = tk.Toplevel(self.root)
        popup.title("Configuração de Restrições Individuais")
        popup.geometry("700x600")
        popup.transient(self.root)
        popup.grab_set()
        
        # Frame principal
        main_frame = ttk.Frame(popup, padding="10")
        main_frame.pack(fill='both', expand=True)
        
        ttk.Label(main_frame, text="Configure limites específicos por ativo:", 
                 font=('TkDefaultFont', 12, 'bold')).pack(pady=(0,10))
        
        # Frame com informações dos limites globais
        info_frame = ttk.LabelFrame(main_frame, text="Limites Globais Atuais", padding="5")
        info_frame.pack(fill='x', pady=(0,10))
        
        global_min = self.min_weight_var.get()
        global_max = self.max_weight_var.get()
        ttk.Label(info_frame, 
                 text=f"📊 Globais: Mín={global_min:.1f}% | Máx={global_max:.1f}%").pack()
        
        # Frame com busca
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill='x', pady=(0,10))
        
        ttk.Label(search_frame, text="🔍 Buscar:").pack(side='left')
        search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=search_var)
        search_entry.pack(side='left', fill='x', expand=True, padx=(5,0))
        
        # Frame para lista com scroll
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill='both', expand=True, pady=(0,10))
        
        # Canvas com scrollbar
        canvas = tk.Canvas(list_frame)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Dicionário para guardar widgets
        constraint_widgets = {}
        
        def create_constraint_widgets():
            """Criar widgets para cada ativo"""
            # Limpar widgets existentes
            for widget in scrollable_frame.winfo_children():
                widget.destroy()
            constraint_widgets.clear()
            
            # Filtrar ativos baseado na busca
            search_term = search_var.get().lower()
            filtered_assets = [asset for asset in selected_assets 
                              if search_term in asset.lower()]
            
            for asset in filtered_assets:
                # Frame principal do ativo
                asset_frame = ttk.LabelFrame(scrollable_frame, text=asset, padding="5")
                asset_frame.pack(fill='x', pady=3, padx=5)
                
                # Checkbox para usar restrição específica
                use_var = tk.BooleanVar(value=asset in self.individual_constraints)
                check = ttk.Checkbutton(
                    asset_frame, 
                    text="Usar limites específicos", 
                    variable=use_var,
                    command=lambda a=asset, v=use_var: toggle_constraint(a, v)
                )
                check.pack(anchor='w', pady=(0,5))
                
                # Frame para min e max
                limits_frame = ttk.Frame(asset_frame)
                limits_frame.pack(fill='x')
                
                # Mín
                min_frame = ttk.Frame(limits_frame)
                min_frame.pack(side='left', fill='x', expand=True, padx=(0,10))
                ttk.Label(min_frame, text="Mín (%):").pack(anchor='w')
                
                # Valor inicial baseado em configuração existente ou global
                if asset in self.individual_constraints:
                    initial_min = self.individual_constraints[asset]['min'] * 100
                    initial_max = self.individual_constraints[asset]['max'] * 100
                else:
                    initial_min = global_min
                    initial_max = global_max
                
                min_var = tk.DoubleVar(value=initial_min)
                min_entry = ttk.Entry(min_frame, textvariable=min_var, width=8)
                min_entry.pack(anchor='w')
                
                # Máx
                max_frame = ttk.Frame(limits_frame)
                max_frame.pack(side='left', fill='x', expand=True)
                ttk.Label(max_frame, text="Máx (%):").pack(anchor='w')
                max_var = tk.DoubleVar(value=initial_max)
                max_entry = ttk.Entry(max_frame, textvariable=max_var, width=8)
                max_entry.pack(anchor='w')
                
                # Habilitar/desabilitar entries baseado no checkbox
                if not use_var.get():
                    min_entry.config(state='disabled')
                    max_entry.config(state='disabled')
                
                # Guardar referências
                constraint_widgets[asset] = {
                    'use_var': use_var,
                    'min_var': min_var,
                    'max_var': max_var,
                    'min_entry': min_entry,
                    'max_entry': max_entry,
                    'check': check
                }
        
        def toggle_constraint(asset, use_var):
            """Toggle restrição para ativo específico"""
            if asset in constraint_widgets:
                widgets = constraint_widgets[asset]
                if use_var.get():
                    widgets['min_entry'].config(state='normal')
                    widgets['max_entry'].config(state='normal')
                else:
                    widgets['min_entry'].config(state='disabled')
                    widgets['max_entry'].config(state='disabled')
        
        # Função de busca
        search_var.trace('w', lambda *args: create_constraint_widgets())
        
        # Criar widgets iniciais
        create_constraint_widgets()
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Botões de ação rápida
        quick_frame = ttk.LabelFrame(main_frame, text="Ações Rápidas", padding="5")
        quick_frame.pack(fill='x', pady=(10,0))
        
        quick_buttons_frame = ttk.Frame(quick_frame)
        quick_buttons_frame.pack(fill='x')
        
        ttk.Button(quick_buttons_frame, text="Aplicar Globais", 
                  command=lambda: apply_global_limits()).pack(side='left', padx=(0,5))
        ttk.Button(quick_buttons_frame, text="Limpar Todos", 
                  command=lambda: clear_all_constraints()).pack(side='left', padx=(0,5))
        
        # Campos para limites em lote
        ttk.Label(quick_buttons_frame, text="Lote - Mín:").pack(side='left', padx=(20,2))
        batch_min_var = tk.DoubleVar(value=global_min)
        ttk.Entry(quick_buttons_frame, textvariable=batch_min_var, width=6).pack(side='left', padx=(0,5))
        
        ttk.Label(quick_buttons_frame, text="Máx:").pack(side='left', padx=(5,2))
        batch_max_var = tk.DoubleVar(value=global_max)
        ttk.Entry(quick_buttons_frame, textvariable=batch_max_var, width=6).pack(side='left', padx=(0,5))
        
        ttk.Button(quick_buttons_frame, text="Aplicar aos Selecionados", 
                  command=lambda: apply_batch_limits()).pack(side='left', padx=(5,0))
        
        def apply_global_limits():
            """Aplicar limites globais aos selecionados"""
            for asset, widgets in constraint_widgets.items():
                if widgets['use_var'].get():
                    widgets['min_var'].set(global_min)
                    widgets['max_var'].set(global_max)
        
        def clear_all_constraints():
            """Limpar todas as restrições"""
            for asset, widgets in constraint_widgets.items():
                widgets['use_var'].set(False)
                toggle_constraint(asset, widgets['use_var'])
        
        def apply_batch_limits():
            """Aplicar limites em lote aos selecionados"""
            batch_min = batch_min_var.get()
            batch_max = batch_max_var.get()
            
            if batch_min > batch_max:
                tk.messagebox.showerror("Erro", "Mínimo deve ser menor que máximo!")
                return
            
            for asset, widgets in constraint_widgets.items():
                if widgets['use_var'].get():
                    widgets['min_var'].set(batch_min)
                    widgets['max_var'].set(batch_max)
        
        # Botões principais
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=(10,0))
        
        def apply_constraints():
            """Aplicar configuração de restrições"""
            new_constraints = {}
            
            for asset, widgets in constraint_widgets.items():
                if widgets['use_var'].get():
                    min_val = widgets['min_var'].get() / 100
                    max_val = widgets['max_var'].get() / 100
                    
                    if min_val > max_val:
                        tk.messagebox.showerror("Erro", f"Mínimo > máximo para {asset}!")
                        return
                    
                    new_constraints[asset] = {
                        'min': min_val,
                        'max': max_val
                    }
            
            # Atualizar configurações
            self.individual_constraints = new_constraints
            
            # Atualizar resumo
            self.update_constraints_summary()
            popup.destroy()
            
            if new_constraints:
                tk.messagebox.showinfo("Sucesso", f"Configuradas restrições para {len(new_constraints)} ativos!")
            else:
                tk.messagebox.showinfo("Info", "Todas as restrições foram removidas!")
        
        ttk.Button(button_frame, text="✅ Aplicar Configuração", 
                  command=apply_constraints).pack(side='right', padx=(5,0))
        ttk.Button(button_frame, text="❌ Cancelar", 
                  command=popup.destroy).pack(side='right')

    def update_constraints_summary(self):
        """Atualizar resumo de restrições individuais"""
        # Limpar frame
        for widget in self.constraints_summary_frame.winfo_children():
            widget.destroy()
        
        if not self.individual_constraints:
            ttk.Label(self.constraints_summary_frame, text="Nenhuma restrição individual configurada").pack(pady=10)
            return
        
        # Mostrar lista
        for asset, limits in self.individual_constraints.items():
            ttk.Label(self.constraints_summary_frame, 
                     text=f"📊 {asset}: {limits['min']*100:.1f}% - {limits['max']*100:.1f}%").pack(anchor='w', padx=10, pady=2)
        
        # Total
        ttk.Label(self.constraints_summary_frame, 
                 text=f"Total: {len(self.individual_constraints)} ativos com limites específicos", 
                 font=('TkDefaultFont', 9, 'bold')).pack(anchor='w', padx=10, pady=(5,0))
    
    def update_short_widgets(self):
        """Atualizar widgets de short selling com seleção em janela"""
        # Preservar configurações existentes
        existing_short_weights = getattr(self, 'short_weights', {}).copy()

        # Limpar widgets existentes
        for widget in self.short_frame.winfo_children():
            widget.destroy()
        self.short_widgets.clear()
        
        if not self.use_short.get():
            self.short_info = ttk.Label(self.short_frame, text="Habilite posições short acima")
            self.short_info.pack(pady=20)
            return
        
        if self.df is None:
            self.short_info = ttk.Label(self.short_frame, text="Carregue dados primeiro")
            self.short_info.pack(pady=20)
            return
            
        selected_assets = self.get_selected_assets()
        if len(selected_assets) < 1:
            self.short_info = ttk.Label(self.short_frame, text="Selecione ativos principais na aba Dados")
            self.short_info.pack(pady=20)
            return
        
        # Identificar ativos disponíveis para short (não selecionados)
        all_assets = list(self.assets_listbox.get(0, tk.END))
        available_for_short = [asset for asset in all_assets if asset not in selected_assets]
        
        if len(available_for_short) == 0:
            self.short_info = ttk.Label(self.short_frame, text="Selecione menos ativos principais para liberar opções de short")
            self.short_info.pack(pady=20)
            return
        
        # Interface simplificada com botão para seleção
        ttk.Label(self.short_frame, text="Configure posições short (venda a descoberto):", 
                 font=('TkDefaultFont', 10, 'bold')).pack(anchor='w', pady=(0,10))
        
        # Botão para abrir janela de seleção
        ttk.Button(
            self.short_frame, 
            text="📋 Selecionar Ativos para Short", 
            command=lambda: self.open_short_selection_window(available_for_short)
        ).pack(pady=10)
        
        # Frame para mostrar ativos short selecionados
        self.short_summary_frame = ttk.LabelFrame(self.short_frame, text="Ativos Short Configurados")
        self.short_summary_frame.pack(fill='both', expand=True, pady=10)
        
        # Label inicial
        ttk.Label(self.short_summary_frame, text="Nenhum ativo short configurado").pack(pady=10)

        # Restaurar configurações se existiam
        if existing_short_weights and self.use_short.get():
            self.short_weights = existing_short_weights
            try:
                self.update_short_summary()
            except (AttributeError, tk.TclError):
                pass  # Ignorar se widgets não existem ainda

    def open_short_selection_window(self, available_assets):
        """Abrir janela para seleção de ativos short com pesos individuais"""
        # Criar janela popup
        popup = tk.Toplevel(self.root)
        popup.title("Configuração de Ativos Short")
        popup.geometry("600x700")
        popup.transient(self.root)
        popup.grab_set()
        
        # Frame principal
        main_frame = ttk.Frame(popup, padding="10")
        main_frame.pack(fill='both', expand=True)
        
        ttk.Label(main_frame, text="Configure posições short individuais:", 
                 font=('TkDefaultFont', 12, 'bold')).pack(pady=(0,10))
        
        # Frame com busca
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill='x', pady=(0,10))
        
        ttk.Label(search_frame, text="🔍 Buscar:").pack(side='left')
        search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=search_var)
        search_entry.pack(side='left', fill='x', expand=True, padx=(5,0))
        
        # Frame para lista com scroll
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill='both', expand=True, pady=(0,10))
        
        # Canvas com scrollbar para widgets dinâmicos
        canvas = tk.Canvas(list_frame)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Dicionário para guardar widgets de cada ativo
        asset_widgets = {}
        
        def create_asset_widgets():
            """Criar widgets para cada ativo"""
            # Limpar widgets existentes
            for widget in scrollable_frame.winfo_children():
                widget.destroy()
            asset_widgets.clear()
            
            # Filtrar ativos baseado na busca
            search_term = search_var.get().lower()
            filtered_assets = [asset for asset in available_assets 
                              if search_term in asset.lower()]
            
            # Criar widget para cada ativo
            for asset in filtered_assets:
                # Frame principal do ativo
                asset_frame = ttk.Frame(scrollable_frame)
                asset_frame.pack(fill='x', pady=2, padx=5)
                
                # Checkbox para habilitar short neste ativo
                use_var = tk.BooleanVar(value=asset in self.short_weights)
                check = ttk.Checkbutton(
                    asset_frame, 
                    text=asset, 
                    variable=use_var,
                    command=lambda a=asset, v=use_var: toggle_asset_weight(a, v)
                )
                check.pack(side='left', anchor='w', padx=(0,10))
                
                # Frame para peso
                weight_frame = ttk.Frame(asset_frame)
                weight_frame.pack(side='right')
                
                ttk.Label(weight_frame, text="Peso (%):").pack(side='left', padx=(0,5))
                
                # Entry para peso (valor inicial baseado em configuração existente)
                initial_weight = self.short_weights.get(asset, -1.0) * 100
                weight_var = tk.DoubleVar(value=initial_weight)
                weight_entry = ttk.Entry(weight_frame, textvariable=weight_var, width=8)
                weight_entry.pack(side='left')
                
                # Habilitar/desabilitar entry baseado no checkbox
                if not use_var.get():
                    weight_entry.config(state='disabled')
                
                # Guardar referências
                asset_widgets[asset] = {
                    'use_var': use_var,
                    'weight_var': weight_var,
                    'weight_entry': weight_entry,
                    'check': check
                }
        
        def toggle_asset_weight(asset, use_var):
            """Toggle peso para ativo específico"""
            if asset in asset_widgets:
                widgets = asset_widgets[asset]
                if use_var.get():
                    widgets['weight_entry'].config(state='normal')
                else:
                    widgets['weight_entry'].config(state='disabled')
        
        # Função de busca
        def filter_assets():
            create_asset_widgets()
        
        search_var.trace('w', lambda *args: filter_assets())
        
        # Criar widgets iniciais
        create_asset_widgets()
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Botões de ação rápida
        quick_frame = ttk.LabelFrame(main_frame, text="Ações Rápidas", padding="5")
        quick_frame.pack(fill='x', pady=(10,0))
        
        quick_buttons_frame = ttk.Frame(quick_frame)
        quick_buttons_frame.pack(fill='x')
        
        ttk.Button(quick_buttons_frame, text="Selecionar Todos", 
                  command=lambda: select_all_assets(True)).pack(side='left', padx=(0,5))
        ttk.Button(quick_buttons_frame, text="Limpar Todos", 
                  command=lambda: select_all_assets(False)).pack(side='left', padx=(0,5))
        
        # Campo para peso em lote
        ttk.Label(quick_buttons_frame, text="Peso padrão:").pack(side='left', padx=(20,5))
        default_weight_var = tk.DoubleVar(value=-10.0)
        ttk.Entry(quick_buttons_frame, textvariable=default_weight_var, width=8).pack(side='left', padx=(0,5))
        ttk.Button(quick_buttons_frame, text="Aplicar aos Selecionados", 
                  command=lambda: apply_default_weight()).pack(side='left', padx=(5,0))
        
        def select_all_assets(select):
            """Selecionar/deselecionar todos os ativos"""
            for asset, widgets in asset_widgets.items():
                widgets['use_var'].set(select)
                toggle_asset_weight(asset, widgets['use_var'])
        
        def apply_default_weight():
            """Aplicar peso padrão aos ativos selecionados"""
            default_weight = default_weight_var.get()
            for asset, widgets in asset_widgets.items():
                if widgets['use_var'].get():
                    widgets['weight_var'].set(default_weight)
        
        # Botões principais
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=(10,0))
        
        def apply_configuration():
            """Aplicar configuração de shorts"""
            new_short_weights = {}
            
            for asset, widgets in asset_widgets.items():
                if widgets['use_var'].get():
                    weight = widgets['weight_var'].get() / 100
                    if weight >= 0:
                        tk.messagebox.showerror("Erro", f"Peso short deve ser negativo para {asset}!")
                        return
                    new_short_weights[asset] = weight
            
            # Atualizar configurações
            self.short_weights = new_short_weights
            
            # Atualizar resumo
            self.update_short_summary()
            popup.destroy()
            
            tk.messagebox.showinfo("Sucesso", f"Configurados {len(new_short_weights)} ativos short!")
        
        ttk.Button(button_frame, text="✅ Aplicar Configuração", 
                  command=apply_configuration).pack(side='right', padx=(5,0))
        ttk.Button(button_frame, text="❌ Cancelar", 
                  command=popup.destroy).pack(side='right')

    def update_short_summary(self):
        """Atualizar resumo de ativos short"""
        # Limpar frame
        for widget in self.short_summary_frame.winfo_children():
            widget.destroy()
        
        if not self.short_weights:
            ttk.Label(self.short_summary_frame, text="Nenhum ativo short configurado").pack(pady=10)
            return
        
        # Mostrar lista
        for asset, weight in self.short_weights.items():
            ttk.Label(self.short_summary_frame, 
                     text=f"📉 {asset}: {weight*100:.1f}%").pack(anchor='w', padx=10, pady=2)
        
        # Total
        total_short = sum(self.short_weights.values()) * 100
        ttk.Label(self.short_summary_frame, 
                 text=f"Total Short: {total_short:.1f}%", 
                 font=('TkDefaultFont', 9, 'bold')).pack(anchor='w', padx=10, pady=(5,0))
    
    def toggle_individual_constraints(self):
        """Toggle restrições individuais"""
        self.update_constraints_widgets()
    
    def toggle_short_selling(self):
        """Toggle short selling"""
        self.update_short_widgets()
    
    def toggle_short_asset(self, asset):
        """Toggle short para ativo específico"""
        if asset in self.short_widgets:
            widgets = self.short_widgets[asset]
            if widgets['use_var'].get():
                widgets['entry'].config(state='normal')
            else:
                widgets['entry'].config(state='disabled')
    
    def get_individual_constraints(self):
        """Obter dicionário de restrições individuais - VERSÃO ATUALIZADA"""
        if not self.use_individual_constraints.get():
            return None
        
        # Usar self.individual_constraints diretamente (já configurado)
        if not hasattr(self, 'individual_constraints') or not self.individual_constraints:
            return None
        
        # Validar restrições
        for asset, limits in self.individual_constraints.items():
            min_val = limits['min']
            max_val = limits['max']
            
            if min_val > max_val:
                tk.messagebox.showerror("Erro", f"Peso mínimo > máximo para {asset}")
                return None
        
        return self.individual_constraints.copy()
    
    def get_short_configuration(self):
        """Obter configuração de shorts - VERSÃO ATUALIZADA"""
        if not self.use_short.get():
            return [], {}
        
        # Usar self.short_weights diretamente (já configurado)
        if not hasattr(self, 'short_weights') or not self.short_weights:
            return [], {}
        
        short_assets = list(self.short_weights.keys())
        short_weights = self.short_weights.copy()
        
        # Validar pesos
        for asset, weight in short_weights.items():
            if weight >= 0:
                tk.messagebox.showerror("Erro", f"Peso short deve ser negativo para {asset}")
                return [], {}
        
        return short_assets, short_weights
    
    def select_all_assets(self):
        """Selecionar todos os ativos"""
        self.assets_listbox.select_set(0, tk.END)
        self.update_advanced_widgets()
    
    def clear_selection(self):
        """Limpar seleção de ativos"""
        self.assets_listbox.selection_clear(0, tk.END)
        self.update_advanced_widgets()
    
    def get_selected_assets(self):
        """Obter ativos selecionados"""
        selected_indices = self.assets_listbox.curselection()
        return [self.assets_listbox.get(i) for i in selected_indices]
    
    def optimize_portfolio(self):
        """Executar otimização do portfólio com TODAS as funcionalidades"""
        if self.df is None:
            messagebox.showerror("Erro", "Carregue um arquivo Excel primeiro!")
            return
        
        selected_assets = self.get_selected_assets()
        if len(selected_assets) < 2:
            messagebox.showerror("Erro", "Selecione pelo menos 2 ativos!")
            return
        
        # Obter configurações avançadas
        individual_constraints = self.get_individual_constraints()
        if individual_constraints is None and self.use_individual_constraints.get():
            return  # Erro já mostrado na função
        
        short_assets, short_weights = self.get_short_configuration()
        if short_assets is None:
            return  # Erro já mostrado na função
        
        try:
            # Mostrar janela de progresso
            progress_window = tk.Toplevel(self.root)
            progress_window.title("Otimizando...")
            progress_window.geometry("350x120")
            progress_window.transient(self.root)
            progress_window.grab_set()
            
            ttk.Label(progress_window, text="🔄 Otimizando portfólio...").pack(pady=15)
            progress_bar = ttk.Progressbar(progress_window, mode='indeterminate')
            progress_bar.pack(pady=10, padx=20, fill='x')
            progress_bar.start()
            
            status_label = ttk.Label(progress_window, text="Inicializando...")
            status_label.pack(pady=5)
            
            # Forçar atualização da interface
            self.root.update()
            
            # Preparar lista completa de ativos
            all_assets = selected_assets.copy()
            if len(short_assets) > 0:
                all_assets.extend(short_assets)
            
            status_label.config(text="Inicializando otimizador...")
            self.root.update()
            
            # Inicializar otimizador (SUA CLASSE ORIGINAL!)
            self.optimizer = PortfolioOptimizer(self.df, all_assets)
            
            status_label.config(text="Configurando parâmetros...")
            self.root.update()
            
            # Mapeamento completo de objetivos
            objective_map = {
                "Maximizar Sharpe Ratio": 'sharpe',
                "Minimizar Risco": 'volatility',
                "Maximizar Inclinação": 'slope',
                "Maximizar Inclinação/[(1-R²)×Vol]": 'hc10',
                "Maximizar Qualidade da Linearidade": 'quality_linear',
                "Maximizar Linearidade do Excesso": 'excess_hc10'
            }
            
            objective_type = objective_map[self.objective_var.get()]
            min_weight = self.min_weight_var.get() / 100
            max_weight = self.max_weight_var.get() / 100
            
            # Determinar taxa livre de risco
            if self.has_risk_free and hasattr(self.optimizer, 'risk_free_rate_total'):
                risk_free_rate = self.optimizer.risk_free_rate_total
            else:
                risk_free_rate = self.risk_free_var.get() / 100

            # Meta de retorno (opcional): excesso mínimo sobre a referência no período
            target_return = self.meta_var.get() / 100 if self.use_meta.get() else None

            status_label.config(text="Executando otimização...")
            self.root.update()

            # EXECUTAR OTIMIZAÇÃO com todas as funcionalidades
            if len(short_assets) > 0:
                # Otimização com shorts
                self.result = self.optimizer.optimize_portfolio_with_shorts(
                    selected_assets=selected_assets,
                    short_assets=short_assets,
                    short_weights=short_weights,
                    objective_type=objective_type,
                    target_return=target_return,
                    max_weight=max_weight,
                    min_weight=min_weight,
                    risk_free_rate=risk_free_rate,
                    individual_constraints=individual_constraints
                )
            else:
                # Otimização normal
                self.result = self.optimizer.optimize_portfolio(
                    objective_type=objective_type,
                    target_return=target_return,
                    max_weight=max_weight,
                    min_weight=min_weight,
                    risk_free_rate=risk_free_rate,
                    individual_constraints=individual_constraints
                )

            # Fechar janela de progresso
            progress_window.destroy()

            if self.result['success']:
                self.display_results()
                self.display_monthly_tables()  # NOVA: Exibir tabelas mensais
                self.export_csv_btn.config(state='normal')
                self.export_excel_btn.config(state='normal')
                messagebox.showinfo("Sucesso", "🎉 Otimização concluída com sucesso!" + self._meta_message())
                # Mudar para aba de resultados
                self.notebook.select(self.tab_results)
            else:
                messagebox.showerror("Erro", f"❌ {self.result['message']}")
                
        except Exception as e:
            if 'progress_window' in locals():
                progress_window.destroy()
            messagebox.showerror("Erro", f"Erro durante otimização:\n{str(e)}")

    def _meta_message(self):
        """Texto sobre o resultado da meta (vazio se meta não foi usada)."""
        if not self.result or not self.result.get('meta_used'):
            return ""
        meta = self.result['meta_target'] * 100
        ref = self.result['meta_ref'] * 100
        req = self.result['meta_required'] * 100
        ach = self.result['meta_achieved'] * 100
        if self.result.get('meta_atingida'):
            return (f"\n\n🎯 Meta atingida: retorno do período = {ach:.2f}% "
                    f"(alvo = referência {ref:.2f}% × (1+{meta:.1f}%) = {req:.2f}%).")
        return (f"\n\n⚠️ Meta NÃO atingida com os limites atuais.\n"
                f"Melhor possível: retorno = {ach:.2f}% (alvo = {req:.2f}%).")

    def display_results(self):
        """Exibir resultados com layout horizontal (In-Sample | Out-of-Sample | Comparação)"""
        if not self.result or not self.result['success']:
            return
        
        # Limpar widgets anteriores
        for widget in self.chart_frame.winfo_children():
            widget.destroy()
        
        # Criar frame principal horizontal
        main_horizontal = ttk.Frame(self.chart_frame)
        main_horizontal.pack(fill='both', expand=True)
        
        # =====================================================
        # COLUNA 1: IN-SAMPLE (OTIMIZAÇÃO) - COMPLETA
        # =====================================================
        in_sample_frame = ttk.LabelFrame(main_horizontal, text="📊 IN-SAMPLE (Otimização)", padding="10")
        in_sample_frame.pack(side='left', fill='both', expand=True, padx=(0,5))

        metrics = self.result['metrics']

        # Calcular período de otimização em dias
        if hasattr(self, 'periodo_otimizacao'):
            data_inicio_otim = self.periodo_otimizacao['inicio']
            data_fim_otim = self.periodo_otimizacao['fim']
            n_dias_otim = (data_fim_otim - data_inicio_otim).days
        else:
            # Fallback: usar número de registros
            n_dias_otim = len(self.optimizer.returns_data)

        risk_free_annual = (1 + metrics['risk_free_rate']) ** (365/n_dias_otim) - 1
        sharpe_corrected = (metrics['annual_return'] - risk_free_annual) / metrics['volatility']


        # Métricas In-Sample COMPLETAS
        in_sample_text = f"""🎯 RETORNOS:
        • Total: {metrics['gv_final']:.2%}
        • Anualizado: {metrics['annual_return']:.2%}

        ⚡ PERFORMANCE:
        • Sharpe: {sharpe_corrected:.3f}

        📊 RISCO:
        • Volatilidade: {metrics['volatility']:.2%}
        • VaR 95%: {metrics['var_95_daily']:.2%}
        • CVaR 95%: {metrics['cvar_95_daily']:.2%}

        📈 QUALIDADE:
        • R²: {metrics['r_squared']:.3f}

        🛡️ REFERÊNCIA:
        • Taxa Ref Período: {metrics['risk_free_rate']:.2%}
        • Taxa Ref Anualizada: {risk_free_annual*100:.2f}
        • Excesso Período: {metrics['excess_return']:.2%}

        📅 PERÍODO:
        • Dias: {n_dias_otim}"""

        in_sample_metrics = tk.Text(in_sample_frame, height=15, width=30, wrap='word')
        in_sample_metrics.pack(fill='both', expand=True, pady=(0,10))
        in_sample_metrics.insert('1.0', in_sample_text)
        in_sample_metrics.config(state='disabled')
        
        # =====================================================
        # COLUNA 2: OUT-OF-SAMPLE (VALIDAÇÃO)
        # =====================================================
        out_sample_frame = ttk.LabelFrame(main_horizontal, text="🔍 OUT-OF-SAMPLE (Validação)", padding="10")
        out_sample_frame.pack(side='left', fill='both', expand=True, padx=5)
        
        # Verificar se há dados de validação
        if hasattr(self, 'df_analise') and self.df_analise is not None:
            try:
                # IMPLEMENTAÇÃO IDÊNTICA AO STREAMLIT
                # Determinar ativos usados na otimização
                selected_assets = self.get_selected_assets()
                
                # Verificar se usou shorts
                if hasattr(self, 'use_short') and self.use_short.get() and hasattr(self, 'short_weights'):
                    short_assets = list(self.short_weights.keys())
                    assets_used_in_optimization = selected_assets + short_assets
                else:
                    assets_used_in_optimization = selected_assets
                
                # Criar otimizador com dados estendidos
                optimizer_valid = PortfolioOptimizer(self.df_analise, assets_used_in_optimization)
                
                # Verificar compatibilidade de dimensões
                n_assets_optimization = len(self.result['weights'])
                n_assets_validation = optimizer_valid.returns_data.shape[1] if len(optimizer_valid.returns_data.shape) > 1 else 1
                
                if n_assets_optimization == n_assets_validation:
                    # Calcular métricas com os pesos já otimizados
                    portfolio_returns_valid = np.dot(optimizer_valid.returns_data.values, self.result['weights'])
                    cumulative_valid = np.cumsum(portfolio_returns_valid)
                    
                    # Separar períodos
                    n_dias_otim = len(self.optimizer.returns_data)
                    
                    # Verificar se há período de validação
                    # Substituir esta seção no display_results(), dentro do bloco out-of-sample:

                    if len(portfolio_returns_valid) > n_dias_otim:
                        returns_valid_only = portfolio_returns_valid[n_dias_otim:]
                        
                        # ===== CORREÇÃO: USAR DIAS CORRIDOS REAIS =====
                        # Calcular dias corridos entre as datas configuradas
                        if hasattr(self, 'periodo_otimizacao') and hasattr(self, 'periodo_analise'):
                            data_fim_otim = self.periodo_otimizacao['fim']
                            data_fim_analise = self.periodo_analise['fim']
                            n_dias_valid = (data_fim_analise - data_fim_otim).days # DIAS CORRIDOS!
                        else:
                            # Fallback: estimar baseado nos dados (não ideal, mas funcional)
                            n_dias_valid = len(returns_valid_only)
                        
                        # 1. RETORNO DO PORTFÓLIO (BASE 0)
                        portfolio_total_ate_validacao = cumulative_valid[-1]
                        portfolio_total_ate_otimizacao = cumulative_valid[n_dias_otim-1]
                        retorno_total_valid = (1 + portfolio_total_ate_validacao) / (1 + portfolio_total_ate_otimizacao) - 1
                        
                        # Anualizar usando DIAS CORRIDOS (igual ao Streamlit)
                        if n_dias_valid > 0:
                            annual_return_valid = (1 + retorno_total_valid) ** (365/n_dias_valid) - 1
                        else:
                            annual_return_valid = 0
                        
                        # 2. VOLATILIDADE (METODOLOGIA VARIAC_RESULT_PU)
                        portfolio_cumulative_validacao = cumulative_valid[n_dias_otim-1:]
                        
                        if len(portfolio_cumulative_validacao) > 1:
                            portfolio_cumulative_with_zero = np.concatenate([[portfolio_cumulative_validacao[0]], portfolio_cumulative_validacao])
                            variac_result_pu = (1 + portfolio_cumulative_with_zero[1:]) / (1 + portfolio_cumulative_with_zero[:-1])
                            portfolio_returns_pct_valid = variac_result_pu - 1
                            vol_valid = np.std(portfolio_returns_pct_valid, ddof=0) * np.sqrt(252)
                        else:
                            vol_valid = 0
                        
                        # 3. TAXA LIVRE DE RISCO
                        if hasattr(optimizer_valid, 'risk_free_cumulative') and optimizer_valid.risk_free_cumulative is not None:
                            try:
                                risk_free_total_ate_validacao = optimizer_valid.risk_free_cumulative.iloc[-1]
                                risk_free_total_ate_otimizacao = optimizer_valid.risk_free_cumulative.iloc[n_dias_otim-1]
                                risk_free_total_valid = (1 + risk_free_total_ate_validacao) / (1 + risk_free_total_ate_otimizacao) - 1
                                
                                if n_dias_valid > 0:
                                    risk_free_annual_valid = (1 + risk_free_total_valid) ** (365/n_dias_valid) - 1
                                else:
                                    risk_free_annual_valid = 0
                            except:
                                risk_free_annual_valid = 0
                        else:
                            risk_free_annual_valid = 0
                        
                        # 4. SHARPE E SORTINO
                        if vol_valid > 0:
                            sharpe_valid = (annual_return_valid - risk_free_annual_valid) / vol_valid
                        else:
                            sharpe_valid = 0
                        
                        # VaR 95% (similar ao in-sample)
                        mean_daily_return = np.mean(portfolio_returns_pct_valid)
                        std_daily_return = np.std(portfolio_returns_pct_valid, ddof=0)
                        var_95_daily_valid = mean_daily_return - 1.65 * std_daily_return
                        
                        # Excesso de retorno
                        excess_return_valid = annual_return_valid - risk_free_annual_valid
                        
                        # Texto das métricas out-of-sample
                        out_sample_text = f"""🎯 RETORNOS:
    • Total: {retorno_total_valid:.2%}
    • Anualizado: {annual_return_valid:.2%}

    ⚡ PERFORMANCE:
    • Sharpe: {sharpe_valid:.3f}

    📊 RISCO:
    • Volatilidade: {vol_valid:.2%}
    • VaR 95%: {var_95_daily_valid:.2%}

    🛡️ REFERÊNCIA:
    • Taxa Ref Anualizada: {risk_free_annual_valid:.2%}
    • Excesso Anualizado: {excess_return_valid:.2%}

    📅 PERÍODO:
    • Dias: {n_dias_valid}"""
                        
                    else:
                        out_sample_text = "⚠️ Período de validação muito curto\nconfigurado."
                        # Zerar variáveis para comparação
                        annual_return_valid = sharpe_valid = vol_valid = 0
                        var_95_daily_valid = excess_return_valid = 0
                        
                else:
                    out_sample_text = f"❌ Incompatibilidade:\n{n_assets_optimization} pesos vs {n_assets_validation} ativos"
                    # Zerar variáveis para comparação
                    annual_return_valid = sharpe_valid = vol_valid = 0
                    var_95_daily_valid = excess_return_valid = 0
                    
            except Exception as e:
                out_sample_text = f"❌ Erro na validação:\n{str(e)}"
                # Zerar variáveis para comparação
                annual_return_valid = sharpe_valid = vol_valid = 0
                var_95_daily_valid = excess_return_valid = 0
        else:
            out_sample_text = "🔍 Configure um período de\nvalidação para ver resultados\nout-of-sample"
            # Zerar variáveis para comparação
            annual_return_valid = sharpe_valid = vol_valid = 0
            var_95_daily_valid = excess_return_valid = 0
        
        out_sample_metrics = tk.Text(out_sample_frame, height=15, width=30, wrap='word')
        out_sample_metrics.pack(fill='both', expand=True, pady=(0,10))
        out_sample_metrics.insert('1.0', out_sample_text)
        out_sample_metrics.config(state='disabled')
        
        # =====================================================
        # COLUNA 3: COMPARAÇÃO
        # =====================================================
        comparison_frame = ttk.LabelFrame(main_horizontal, text="⚖️ COMPARAÇÃO", padding="10")
        comparison_frame.pack(side='right', fill='both', expand=True, padx=(5,0))
        
        # Calcular diferenças (se out-of-sample está disponível)
        if 'annual_return_valid' in locals() and annual_return_valid != 0:
            diff_return = annual_return_valid - metrics['annual_return']
            diff_sharpe = sharpe_valid - metrics['sharpe_ratio']
            diff_vol = vol_valid - metrics['volatility']
            
            # Determinar qual é melhor
            better_return = "📈 Out" if diff_return > 0 else "📉 In"
            better_sharpe = "📈 Out" if diff_sharpe > 0 else "📉 In"
            better_vol = "📈 In" if diff_vol > 0 else "📉 Out"  # Menor vol é melhor
            
            comparison_text = f"""📊 DIFERENÇAS (Out - In):

    🎯 RETORNO:
    • Anual: {diff_return:+.2%}
    • Melhor: {better_return}

    ⚡ SHARPE:
    • Diferença: {diff_sharpe:+.3f}
    • Melhor: {better_sharpe}

    📊 VOLATILIDADE:
    • Diferença: {diff_vol:+.2%}
    • Menor risco: {better_vol}

    💡 RESUMO:
    {"✅ Out-of-sample superior" if diff_sharpe > 0 else "⚠️ Degradação out-of-sample"}

    🔍 ANÁLISE:
    {"Boa generalização!" if abs(diff_sharpe) < 0.1 else "Cuidado: overfitting?"}"""
        else:
            comparison_text = """⚖️ COMPARAÇÃO

    Configure um período de validação
    para ver a comparação entre
    in-sample e out-of-sample.

    Isso ajuda a detectar:
    • Overfitting
    • Generalização
    • Robustez da estratégia"""
        
        comparison_metrics = tk.Text(comparison_frame, height=15, width=30, wrap='word')
        comparison_metrics.pack(fill='both', expand=True, pady=(0,10))
        comparison_metrics.insert('1.0', comparison_text)
        comparison_metrics.config(state='disabled')
        
        # =====================================================
        # COMPOSIÇÃO DO PORTFÓLIO (ABAIXO)
        # =====================================================
        # Mover a composição para baixo do layout horizontal
        self.display_portfolio_composition()
 
    def display_portfolio_composition(self):
        """Exibir composição do portfólio (separada do layout horizontal)"""
        
        # Frame para composição (logo abaixo das métricas)
        composition_main = ttk.LabelFrame(self.chart_frame, text="📋 Composição do Portfólio", padding="10")
        composition_main.pack(fill='x', pady=(10,0))
        
        # Botões de exportação
        export_frame = ttk.Frame(composition_main)
        export_frame.pack(fill='x', pady=(0,10))
        
        self.export_csv_btn = ttk.Button(export_frame, text="💾 Exportar CSV", command=self.export_csv)
        self.export_csv_btn.pack(side='left', padx=(0,5))
        
        self.export_excel_btn = ttk.Button(export_frame, text="📊 Exportar Excel", command=self.export_excel)
        self.export_excel_btn.pack(side='left')
        
        self.export_csv_btn.config(state='normal')
        self.export_excel_btn.config(state='normal')
        
        # Frame horizontal para composição + gráfico
        comp_horizontal = ttk.Frame(composition_main)
        comp_horizontal.pack(fill='both', expand=True)
        
        # Composição (esquerda)
        comp_left = ttk.Frame(comp_horizontal)
        comp_left.pack(side='left', fill='both', expand=True, padx=(0,10))
        
        # Treeview para mostrar pesos - AGORA COM 4 COLUNAS
        columns = ('Ativo', 'Peso Inicial (%)', 'Peso Atual (%)', 'Tipo')
        self.portfolio_tree = ttk.Treeview(comp_left, columns=columns, show='headings', height=10)
        
        # Configurar colunas
        self.portfolio_tree.heading('Ativo', text='Ativo')
        self.portfolio_tree.heading('Peso Inicial (%)', text='Peso Inicial (%)')
        self.portfolio_tree.heading('Peso Atual (%)', text='Peso Atual (%)')
        self.portfolio_tree.heading('Tipo', text='Tipo')
        
        self.portfolio_tree.column('Ativo', width=100)
        self.portfolio_tree.column('Peso Inicial (%)', width=100)
        self.portfolio_tree.column('Peso Atual (%)', width=100)
        self.portfolio_tree.column('Tipo', width=60)
        
        # Scrollbar para treeview
        tree_scroll = ttk.Scrollbar(comp_left, orient='vertical', command=self.portfolio_tree.yview)
        self.portfolio_tree.configure(yscrollcommand=tree_scroll.set)
        
        self.portfolio_tree.pack(side='left', fill='both', expand=True)
        tree_scroll.pack(side='right', fill='y')
        
        # Preencher dados do portfólio
        self.populate_portfolio_tree()
        
        # Gráfico (direita) - mantém igual
        chart_right = ttk.LabelFrame(comp_horizontal, text="📈 Evolução do Portfólio", padding="5")
        chart_right.pack(side='right', fill='both', expand=True)
        
        # Criar gráfico de performance
        self.create_performance_chart_in_frame(chart_right)

    def get_portfolio_summary_desktop(self, weights, assets, returns_data):
        """
        Cria resumo do portfólio otimizado com pesos iniciais e atuais - VERSÃO DESKTOP
        Posições LONG e SHORT usam a mesma fórmula, mas patrimônio total considera apenas LONGs
        """
        # Calcular valores finais de cada ativo (LONG e SHORT usam mesma fórmula)
        asset_final_values = []
        
        for i, asset in enumerate(assets):
            if abs(weights[i]) > 0.001:  # Ativos significativos (positivos OU negativos)
                # Retorno acumulado do ativo individual
                asset_returns = returns_data[asset].values
                asset_cumulative_return = np.sum(asset_returns)  # Retorno total acumulado
                
                # MESMA FÓRMULA para LONG e SHORT
                asset_final_value = weights[i] * (1 + asset_cumulative_return)
                asset_final_values.append(asset_final_value)
            else:
                asset_final_values.append(0)
        
        # PATRIMÔNIO TOTAL = apenas soma das posições LONG (positivas)
        long_portfolio_value = sum([val for i, val in enumerate(asset_final_values) if weights[i] > 0])
        
        # Calcular novos pesos
        asset_current_weights = []
        for i, asset in enumerate(assets):
            if abs(weights[i]) > 0.001:
                if weights[i] > 0:  # Posição LONG
                    current_weight = asset_final_values[i] / long_portfolio_value if long_portfolio_value > 0 else 0
                else:  # Posição SHORT
                    current_weight = asset_final_values[i] / long_portfolio_value if long_portfolio_value > 0 else 0
                
                asset_current_weights.append(current_weight)
            else:
                asset_current_weights.append(0)
        
        # Filtrar ativos significativos para a tabela
        significant_weights = np.abs(weights) > 0.001
        
        portfolio_df = pd.DataFrame({
            'Ativo': np.array(assets)[significant_weights],
            'Peso Inicial (%)': weights[significant_weights] * 100,
            'Peso Atual (%)': np.array(asset_current_weights)[significant_weights] * 100,
            'Tipo': ['SHORT' if w < 0 else 'LONG' for w in weights[significant_weights]]
        }).sort_values('Peso Inicial (%)', key=abs, ascending=False)
        
        return portfolio_df

    # 2. SUBSTITUIR A FUNÇÃO populate_portfolio_tree() POR ESTA:

    def populate_portfolio_tree(self):
        """Preencher TreeView com dados do portfólio - VERSÃO COM PESO ATUAL"""
        # Limpar TreeView
        for item in self.portfolio_tree.get_children():
            self.portfolio_tree.delete(item)
        
        # Calcular resumo completo do portfólio
        portfolio_summary = self.get_portfolio_summary_desktop(
            self.result['weights'], 
            self.result['assets'],
            self.optimizer.returns_data
        )
        
        # Inserir dados com peso inicial E atual
        total_initial_positive = 0
        total_initial_negative = 0
        total_current_positive = 0
        total_current_negative = 0
        
        for _, row in portfolio_summary.iterrows():
            peso_inicial = row['Peso Inicial (%)']
            peso_atual = row['Peso Atual (%)']
            tipo = row['Tipo']
            
            # Inserir na TreeView
            self.portfolio_tree.insert('', 'end', values=(
                row['Ativo'], 
                f"{peso_inicial:.2f}%",
                f"{peso_atual:.2f}%",
                tipo
            ))
            
            # Somar totais
            if peso_inicial > 0:
                total_initial_positive += peso_inicial
                total_current_positive += peso_atual
            else:
                total_initial_negative += peso_inicial
                total_current_negative += peso_atual
        
        # Adicionar linha de separação e totais
        self.portfolio_tree.insert('', 'end', values=("─────────", "─────────", "─────────", "─────"))
        self.portfolio_tree.insert('', 'end', values=("TOTAL LONG", f"{total_initial_positive:.1f}%", f"{total_current_positive:.1f}%", ""))
        
        if abs(total_initial_negative) > 0.001:
            self.portfolio_tree.insert('', 'end', values=("TOTAL SHORT", f"{total_initial_negative:.1f}%", f"{total_current_negative:.1f}%", ""))
        
        # Adicionar linha com diferenças
        if abs(total_current_positive - total_initial_positive) > 0.1:
            diff_long = total_current_positive - total_initial_positive
            self.portfolio_tree.insert('', 'end', values=("", "", "", ""))
            self.portfolio_tree.insert('', 'end', values=(
                "VARIAÇÃO LONG", 
                "", 
                f"{diff_long:+.1f}%", 
                "🔄" if abs(diff_long) > 1 else "✅"
            ))

    def create_performance_chart_in_frame(self, parent_frame):
        """Criar gráfico de performance completo - EIXO X IGUAL AO STREAMLIT"""
        # Limpar frame do gráfico
        for widget in parent_frame.winfo_children():
            widget.destroy()
        
        # Verificar se há dados de validação
        if hasattr(self, 'df_analise') and self.df_analise is not None:
            try:
                # Determinar ativos usados na otimização
                selected_assets = self.get_selected_assets()
                
                # Verificar se usou shorts
                if hasattr(self, 'use_short') and self.use_short.get() and hasattr(self, 'short_weights'):
                    short_assets = list(self.short_weights.keys())
                    assets_used_in_optimization = selected_assets + short_assets
                else:
                    assets_used_in_optimization = selected_assets
                
                # Criar otimizador com dados completos
                optimizer_extended = PortfolioOptimizer(self.df_analise, assets_used_in_optimization)
                
                # Determinar taxa livre de risco
                if self.has_risk_free and hasattr(self.optimizer, 'risk_free_rate_total'):
                    final_risk_free_rate = self.optimizer.risk_free_rate_total
                else:
                    final_risk_free_rate = self.risk_free_var.get() / 100
                
                # Calcular métricas com período completo
                metrics_extended = optimizer_extended.calculate_portfolio_metrics(self.result['weights'], final_risk_free_rate)
                
                # Buscar datas completas
                dates_extended = getattr(optimizer_extended, 'dates', None)
                
                # Determinar ponto de divisão
                n_dias_otim = len(self.optimizer.returns_data)
                
                # Criar figura matplotlib
                fig, ax = plt.subplots(figsize=(8, 5))
                
                # Preparar dados
                if dates_extended is not None:
                    x_data = dates_extended
                else:
                    x_data = list(range(len(metrics_extended['portfolio_cumulative'])))
                
                portfolio_cumulative_extended = metrics_extended['portfolio_cumulative'] * 100
                
                # 1. LINHA DO PORTFÓLIO
                ax.plot(x_data, portfolio_cumulative_extended, 'b-', linewidth=2.5, label='Portfólio Otimizado')
                
                # 2. TAXA DE REFERÊNCIA (se existir)
                if hasattr(optimizer_extended, 'risk_free_cumulative') and optimizer_extended.risk_free_cumulative is not None:
                    risk_free_cumulative_extended = optimizer_extended.risk_free_cumulative * 100
                    ax.plot(x_data, risk_free_cumulative_extended, color='orange', linestyle='--', linewidth=2, 
                           label='Taxa de Referência')
                    
                    # 3. EXCESSO DE RETORNO
                    if metrics_extended.get('excess_cumulative') is not None:
                        excess_cumulative_extended = metrics_extended['excess_cumulative'] * 100
                        ax.plot(x_data, excess_cumulative_extended, 'g:', linewidth=2, label='Excesso de Retorno')
                
                # 4. LINHA VERTICAL (apenas se tiver validação)
                if len(x_data) > n_dias_otim:
                    if dates_extended is not None:
                        fim_otim_point = x_data[n_dias_otim-1]
                    else:
                        fim_otim_point = n_dias_otim-1
                    ax.axvline(x=fim_otim_point, color='red', linestyle='--', linewidth=2, alpha=0.8, 
                              label='Fim Otimização')
                
                # 5. CONFIGURAR LAYOUT
                ax.set_title('Evolução do Retorno Acumulado - Período Completo', fontsize=10)
                #ax.set_xlabel('Período')
                ax.set_ylabel('Retorno Acumulado (%)')
                ax.legend(loc='upper left', fontsize=8)
                ax.grid(True, alpha=0.3)
                
                # ============================================
                # 6. EIXO X IGUAL AO STREAMLIT - INÍCIO
                # ============================================
                if dates_extended is not None:
                    try:
                        import numpy as np
                        import matplotlib.dates as mdates
                        
                        # EXATAMENTE COMO NO STREAMLIT: 
                        # Dividir o período em 7 pontos (ou 12 se preferir) uniformemente
                        total_pontos = len(dates_extended)
                        n_ticks = 9  # Mude para 12 se preferir igual ao Streamlit
                        
                        # Calcular índices espaçados uniformemente
                        if total_pontos > n_ticks:
                            indices = np.linspace(0, total_pontos-1, n_ticks, dtype=int)
                        else:
                            indices = np.arange(total_pontos)
                        
                        # Selecionar as datas correspondentes
                        datas_selecionadas = [dates_extended.iloc[i] for i in indices]
                        
                        # Definir manualmente os ticks exatos
                        ax.set_xticks(datas_selecionadas)
                        
                        # FORMATO FIXO: SEMPRE dd/mm/yyyy (como no Streamlit)
                        # Independente do período - sempre mostra data completa
                        formato = mdates.DateFormatter('%d/%m/%Y')
                        ax.xaxis.set_major_formatter(formato)
                        
                        # Labels horizontais (sem rotação) para economizar espaço
                        plt.setp(ax.xaxis.get_majorticklabels(), rotation=0, ha='center', fontsize=8)
                        
                    except Exception as e:
                        # Fallback: usar método automático
                        ax.locator_params(axis='x', nbins=7)
                # ============================================
                # 6. EIXO X IGUAL AO STREAMLIT - FIM
                # ============================================
                
                usar_grafico_completo = True
                
            except Exception as e:
                usar_grafico_completo = False
        else:
            usar_grafico_completo = False
        
        # FALLBACK: Gráfico simples
        if not usar_grafico_completo:
            fig, ax = plt.subplots(figsize=(8, 5))
            
            # Dados básicos
            periods = range(1, len(self.result['metrics']['portfolio_cumulative']) + 1)
            portfolio_cumulative = self.result['metrics']['portfolio_cumulative'] * 100
            
            # Plot básico
            ax.plot(periods, portfolio_cumulative, 'b-', linewidth=2.5, label='Portfólio Otimizado')
            
            ax.set_title('Evolução do Retorno Acumulado - Período de Otimização', fontsize=10)
            ax.set_xlabel('Dias')
            ax.set_ylabel('Retorno Acumulado (%)')
            ax.legend()
            ax.grid(True, alpha=0.3)
        
        # Adicionar ao Tkinter
        canvas = FigureCanvasTkAgg(fig, parent_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True)
        
        plt.tight_layout()  

    def create_performance_chart(self):
        """Criar gráfico de performance completo"""
        # Limpar frame do gráfico
        for widget in self.chart_frame.winfo_children():
            widget.destroy()
        
        # Criar figura matplotlib
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # Dados do gráfico
        periods = range(1, len(self.result['metrics']['portfolio_cumulative']) + 1)
        portfolio_cumulative = self.result['metrics']['portfolio_cumulative'] * 100
        
        # Plot principal
        ax.plot(periods, portfolio_cumulative, 'b-', linewidth=2.5, label='Portfólio Otimizado')
        
        # Se tem taxa livre, adicionar TODAS as linhas
        if hasattr(self.optimizer, 'risk_free_cumulative') and self.optimizer.risk_free_cumulative is not None:
            risk_free_cumulative = self.optimizer.risk_free_cumulative * 100
            ax.plot(periods, risk_free_cumulative, color='orange', linestyle='--', linewidth=2, 
                   label='Taxa de Referência')
            
            # Excesso de retorno
            excess = portfolio_cumulative - risk_free_cumulative
            ax.plot(periods, excess, 'g:', linewidth=2, label='Excesso de Retorno')
        
        # Configurar gráfico
        ax.set_title('Evolução do Retorno Acumulado', fontsize=14, fontweight='bold')
        ax.set_xlabel('Dias de Negociação')
        ax.set_ylabel('Retorno Acumulado (%)')
        ax.legend(loc='upper left')
        ax.grid(True, alpha=0.3)
        
        # Anotação com retorno final
        final_return = self.result['metrics']['gv_final']
        ax.annotate(f'Retorno Final: {final_return:.2%}', 
                   xy=(len(periods), final_return * 100),
                   xytext=(-60, -30), textcoords='offset points',
                   bbox=dict(boxstyle='round,pad=0.5', fc='yellow', alpha=0.7),
                   arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0'))
        
        # Adicionar ao Tkinter
        canvas = FigureCanvasTkAgg(fig, self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True)
        
        # Toolbar para zoom/pan
        from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk
        toolbar = NavigationToolbar2Tk(canvas, self.chart_frame)
        toolbar.update()
        
        plt.tight_layout()

    def setup_auto_optimization_tab(self):
        """Configurar aba de auto-otimização inteligente - LÓGICA CORRIGIDA"""
        
        # Frame principal SEM scroll para ocupar tela inteira
        main_container = ttk.Frame(self.tab_auto)
        main_container.pack(fill='both', expand=True, padx=10, pady=10)
        
        # ========== CABEÇALHO COMPACTO ==========
        header_frame = ttk.LabelFrame(main_container, text="🤖 Auto-Otimização Inteligente", padding="5")
        header_frame.pack(fill='x', pady=(0,10))
        
        header_info = ttk.Frame(header_frame)
        header_info.pack(fill='x')
        
        ttk.Label(header_info, 
                 text="Walk-Forward Optimization com Ranking Dinâmico Anti-Overfitting", 
                 font=('TkDefaultFont', 10, 'bold')).pack(side='left')
        
        # Status compacto no cabeçalho
        self.status_auto_label = ttk.Label(header_info, text="Aguardando configuração...", 
                                          font=('TkDefaultFont', 9), foreground='blue')
        self.status_auto_label.pack(side='right')
        
        # ========== LAYOUT PRINCIPAL OCUPANDO TODA TELA ==========
        main_horizontal = ttk.Frame(main_container)
        main_horizontal.pack(fill='both', expand=True)
        
        # COLUNA ESQUERDA - Parâmetros (60% da tela)
        left_frame = ttk.Frame(main_horizontal)
        left_frame.pack(side='left', fill='both', expand=True, padx=(0,5))
        
        # COLUNA DIREITA - Controles e Resultados (40% da tela)
        right_frame = ttk.Frame(main_horizontal)  
        right_frame.pack(side='right', fill='both', expand=True, padx=(5,0))
        
        # ========== COLUNA ESQUERDA - TODOS OS PARÂMETROS ==========
        
        # Layout em grid 2x3 para aproveitar espaço
        params_container = ttk.Frame(left_frame)
        params_container.pack(fill='both', expand=True)
        params_container.grid_columnconfigure(0, weight=1)
        params_container.grid_columnconfigure(1, weight=1)
        params_container.grid_rowconfigure(0, weight=1)
        params_container.grid_rowconfigure(1, weight=1)
        params_container.grid_rowconfigure(2, weight=1)
        
        # 1. Janelas de Otimização (Posição 0,0) - SEM STEP
        otim_frame = ttk.LabelFrame(params_container, text="📅 Janelas de Otimização", padding="5")
        otim_frame.grid(row=0, column=0, sticky='nsew', padx=(0,5), pady=(0,5))
        
        self.otim_windows = {
            '3m': tk.BooleanVar(value=False),
            '6m': tk.BooleanVar(value=True), 
            '1a': tk.BooleanVar(value=True),
            '2a': tk.BooleanVar(value=False),
            '3a': tk.BooleanVar(value=False)
        }
        
        otim_grid = ttk.Frame(otim_frame)
        otim_grid.pack(fill='both', expand=True)
        
        for i, (period, var) in enumerate(self.otim_windows.items()):
            row, col = divmod(i, 3)
            ttk.Checkbutton(otim_grid, text=period, variable=var).grid(row=row, column=col, sticky='w', padx=5, pady=2)
        
        # 2. Janelas de Validação/Step (Posição 0,1) - CORRIGIDO
        valid_frame = ttk.LabelFrame(params_container, text="🔍 Janelas de Validação / Step", padding="5")
        valid_frame.grid(row=0, column=1, sticky='nsew', padx=(5,0), pady=(0,5))
        
        # Explicação da lógica
        ttk.Label(valid_frame, 
                 text="Frequência de rebalanceamento = Período de avaliação", 
                 font=('TkDefaultFont', 7), foreground='gray').pack(anchor='w')
        
        # NOVAS opções alinhadas com a realidade operacional
        self.rebalance_periods = {
            '1sem': tk.BooleanVar(value=False),   # 1 semana
            '2sem': tk.BooleanVar(value=False),   # 2 semanas  
            '1mes': tk.BooleanVar(value=True),    # 1 mês
            '2mes': tk.BooleanVar(value=True),    # 2 meses
            '3mes': tk.BooleanVar(value=False)    # 3 meses
        }
        
        valid_grid = ttk.Frame(valid_frame)
        valid_grid.pack(fill='both', expand=True, pady=5)
        
        period_labels = {
            '1sem': '1 semana',
            '2sem': '2 semanas',
            '1mes': '1 mês', 
            '2mes': '2 meses',
            '3mes': '3 meses'
        }
        
        for i, (period_key, var) in enumerate(self.rebalance_periods.items()):
            row, col = divmod(i, 2)
            ttk.Checkbutton(valid_grid, 
                           text=period_labels[period_key], 
                           variable=var).grid(row=row, column=col, sticky='w', padx=5, pady=1)
        
        # 3. Objetivos (Posição 1,0)
        obj_frame = ttk.LabelFrame(params_container, text="🎯 Objetivos de Otimização", padding="5")
        obj_frame.grid(row=1, column=0, sticky='nsew', padx=(0,5), pady=5)
        
        self.objectives = {
            'sharpe': tk.BooleanVar(value=True),
            'volatility': tk.BooleanVar(value=False),
            'hc10': tk.BooleanVar(value=False),
            'quality_linear': tk.BooleanVar(value=False)
        }
        
        # Objetivos em grid compacto
        obj_grid = ttk.Frame(obj_frame)
        obj_grid.pack(fill='both', expand=True)
        
        obj_labels = {
            'sharpe': 'Maximizar Sharpe',
            'volatility': 'Minimizar Risco',
            'hc10': 'Maximizar Inc/[(1-R²)×Vol]',
            'quality_linear': 'Qualidade da Linearidade'
        }
        
        for i, (key, var) in enumerate(self.objectives.items()):
            row, col = divmod(i, 1)  # Uma coluna só para ficar organizado
            ttk.Checkbutton(obj_grid, text=obj_labels[key], variable=var).grid(row=row, column=col, sticky='w', pady=1)
        
        # 4. POSIÇÕES VENDIDAS (Posição 1,1)
        short_frame = ttk.LabelFrame(params_container, text="🔻 Posições Vendidas", padding="5")
        short_frame.grid(row=1, column=1, sticky='nsew', padx=(5,0), pady=5)
        
        # Checkbox para habilitar shorts
        self.use_auto_shorts = tk.BooleanVar(value=False)
        ttk.Checkbutton(short_frame, text="Habilitar posições short", 
                       variable=self.use_auto_shorts,
                       command=self.toggle_auto_shorts).pack(anchor='w')
        
        # Frame para configuração de shorts
        self.auto_shorts_config = ttk.Frame(short_frame)
        self.auto_shorts_config.pack(fill='both', expand=True, pady=5)
        
        ttk.Label(self.auto_shorts_config, text="Ativo:").grid(row=0, column=0, sticky='w', padx=(0,5))
        self.short_asset_var = tk.StringVar(value="BOVA11")
        ttk.Entry(self.auto_shorts_config, textvariable=self.short_asset_var, width=8).grid(row=0, column=1, sticky='w')
        
        ttk.Label(self.auto_shorts_config, text="Peso (%):").grid(row=1, column=0, sticky='w', padx=(0,5), pady=(5,0))
        self.short_weight_var = tk.DoubleVar(value=-100.0)
        ttk.Entry(self.auto_shorts_config, textvariable=self.short_weight_var, width=8).grid(row=1, column=1, sticky='w', pady=(5,0))
        
        # Inicialmente desabilitado
        for widget in self.auto_shorts_config.winfo_children():
            widget.configure(state='disabled')
        
        # 5. Configurações Globais (Posição 2,0 e 2,1 - span)
        config_frame = ttk.LabelFrame(params_container, text="⚙️ Configurações Globais", padding="5")
        config_frame.grid(row=2, column=0, columnspan=2, sticky='nsew', pady=(5,0))
        
        # Layout interno em 2 colunas
        config_left = ttk.Frame(config_frame)
        config_left.pack(side='left', fill='both', expand=True, padx=(0,10))
        config_right = ttk.Frame(config_frame)  
        config_right.pack(side='right', fill='both', expand=True)
        
        # Ranking
        ttk.Label(config_left, text="🏆 Ranking de Ativos (por Score):", font=('TkDefaultFont', 9, 'bold')).pack(anchor='w')
        rank_frame = ttk.Frame(config_left)
        rank_frame.pack(fill='x', pady=2)
        
        ttk.Label(rank_frame, text="Score Min:").pack(side='left')
        self.rank_min_var = tk.DoubleVar(value=0)  # Valor mais realista
        ttk.Entry(rank_frame, textvariable=self.rank_min_var, width=6).pack(side='left', padx=2)
        ttk.Label(rank_frame, text="Max:").pack(side='left', padx=(5,0))
        self.rank_max_var = tk.DoubleVar(value=100)
        ttk.Entry(rank_frame, textvariable=self.rank_max_var, width=6).pack(side='left', padx=2)
        ttk.Label(rank_frame, text="(0-100)").pack(side='left')

        
        # Pesos
        ttk.Label(config_right, text="⚖️ Limites de Peso:", font=('TkDefaultFont', 9, 'bold')).pack(anchor='w')
        weight_frame = ttk.Frame(config_right)
        weight_frame.pack(fill='x', pady=2)
        
        ttk.Label(weight_frame, text="Min:").pack(side='left')
        self.weight_min_var = tk.DoubleVar(value=0)
        ttk.Entry(weight_frame, textvariable=self.weight_min_var, width=6).pack(side='left', padx=2)
        ttk.Label(weight_frame, text="% Max:").pack(side='left', padx=(5,0))
        self.weight_max_var = tk.DoubleVar(value=30)
        ttk.Entry(weight_frame, textvariable=self.weight_max_var, width=6).pack(side='left', padx=2)
        ttk.Label(weight_frame, text="%").pack(side='left')
        
        # ========== COLUNA DIREITA - CONTROLES E RESULTADOS ==========
        
        # Estimativa e controles (parte superior)
        controls_frame = ttk.Frame(right_frame)
        controls_frame.pack(fill='x', pady=(0,10))
        
        # Estimativa
        estimate_frame = ttk.LabelFrame(controls_frame, text="📊 Estimativa", padding="5")
        estimate_frame.pack(fill='x', pady=(0,5))
        
        self.estimate_label = ttk.Label(estimate_frame, text="Configure os parâmetros", font=('TkDefaultFont', 9))
        self.estimate_label.pack()
        
        ttk.Button(estimate_frame, text="🧮 Calcular", 
                  command=self.calculate_estimate).pack(pady=2)
        
        # Botão principal
        self.auto_optimize_btn = ttk.Button(controls_frame, 
                                           text="🚀 INICIAR AUTO-OTIMIZAÇÃO",
                                           command=self.start_auto_optimization,
                                           style="Accent.TButton")
        self.auto_optimize_btn.pack(fill='x', ipady=8, pady=5)
        
        # Resultados (parte inferior - ocupa espaço restante)
        results_frame = ttk.LabelFrame(right_frame, text="🏆 Top Configurações", padding="5")
        results_frame.pack(fill='both', expand=True)

        # Frame para botões de exportação
        export_frame = ttk.Frame(results_frame)
        export_frame.pack(fill='x', pady=(5, 0))

        ttk.Button(export_frame, text="💾 Exportar CSV", 
                  command=self.export_auto_results_csv).pack(side='left', padx=(0, 5))
        ttk.Button(export_frame, text="📊 Exportar Excel", 
                  command=self.export_auto_results_excel).pack(side='left')
        
        # TreeView para resultados - COLUNAS COMPLETAS
        columns = ('Rank', 'Otim', 'Rebal/Aval', 'Obj', 'N_Ativos', 'Sharpe', 'Ret%', 'TxRef%', 'Vol%', 'Pos%')
        self.auto_results_tree = ttk.Treeview(results_frame, columns=columns, show='headings')
        
        # Configurar colunas com tamanhos otimizados
        column_widths = {'Rank': 35, 'Otim': 45, 'Rebal/Aval': 70, 'Obj': 70, 'N_Ativos': 60, 
                        'Sharpe': 60, 'Ret%': 60, 'TxRef%': 60, 'Vol%': 50, 'Pos%': 50}
        
        for col in columns:
            self.auto_results_tree.heading(col, text=col)
            self.auto_results_tree.column(col, width=column_widths[col], anchor='center')
        
        auto_scroll = ttk.Scrollbar(results_frame, orient='vertical', command=self.auto_results_tree.yview)
        self.auto_results_tree.configure(yscrollcommand=auto_scroll.set)
        
        self.auto_results_tree.pack(side='left', fill='both', expand=True)
        auto_scroll.pack(side='right', fill='y')

    def toggle_auto_shorts(self):
        """Toggle para habilitar/desabilitar configuração de shorts"""
        if self.use_auto_shorts.get():
            state = 'normal'
        else:
            state = 'disabled'
        
        for widget in self.auto_shorts_config.winfo_children():
            widget.configure(state=state)

    # ========== MÉTODOS DE CONTROLE ==========

    def calculate_estimate(self):
        """Calcular estimativa de testes - VERSÃO LIMPA"""
        try:
            # Verificar se há dados carregados
            if not hasattr(self, 'df') or self.df is None:
                self.estimate_label.config(text="⚠️ Carregue dados primeiro")
                return
            
            # Calcular período total em dias corridos
            if 'Data' not in self.df.columns:
                self.estimate_label.config(text="⚠️ Coluna Data não encontrada")
                return
                
            # Extrair datas inicial e final
            data_inicial = pd.to_datetime(self.df['Data'].iloc[0])
            data_final = pd.to_datetime(self.df['Data'].iloc[-1])
            total_calendar_days = (data_final - data_inicial).days + 1
            
            # Contar parâmetros selecionados
            otim_count = sum(1 for var in self.otim_windows.values() if var.get())
            rebal_count = sum(1 for var in self.rebalance_periods.values() if var.get()) 
            obj_count = sum(1 for var in self.objectives.values() if var.get())
            
            if otim_count == 0 or rebal_count == 0 or obj_count == 0:
                self.estimate_label.config(text="❌ Selecione ao menos 1 opção\nde cada categoria")
                return
            
            # Usar os mesmos períodos em dias corridos
            period_to_days = {
                '3m': 90, '6m': 180, '1a': 365, '2a': 730, '3a': 1095,
                '1sem': 7, '2sem': 14, '1mes': 30, '2mes': 60, '3mes': 90
            }
            
            # Verificar compatibilidade dos dados com períodos selecionados
            selected_otim = [period for period, var in self.otim_windows.items() if var.get()]
            selected_rebal = [period for period, var in self.rebalance_periods.items() if var.get()]
            
            # Encontrar o maior período necessário
            max_otim_days = max(period_to_days[period] for period in selected_otim)
            max_rebal_days = max(period_to_days[period] for period in selected_rebal)
            min_required = max_otim_days + max_rebal_days * 2
            
            if total_calendar_days < min_required:
                self.estimate_label.config(
                    text=f"⚠️ Período insuficiente!\n"
                         f"Tem: {total_calendar_days} dias\n"
                         f"Precisa: {min_required} dias"
                )
                return
            
            # Estimar steps REAIS (sem limite de 20)
            total_steps_estimado = 0
            
            for otim_period in selected_otim:
                otim_days = period_to_days[otim_period]
                for rebal_period in selected_rebal:
                    rebal_days = period_to_days[rebal_period]
                    
                    # Calcular steps reais para esta combinação
                    steps_possiveis = (total_calendar_days - otim_days) // rebal_days
                    
                    # Aplicar o mesmo limite que usamos no run_walk_forward_test
                    if steps_possiveis > 1000000:
                        steps_usados = 1000000
                    else:
                        steps_usados = steps_possiveis
                    
                    total_steps_estimado += steps_usados
            
            total_configs = otim_count * rebal_count * obj_count
            total_tests = total_steps_estimado * obj_count
            
            # Fator de tempo ajustado para muitos steps
            if total_steps_estimado > 100:
                time_factor = 0.8  # Mais rápido para muitos steps
            else:
                time_factor = 0.95  # Fator original para poucos steps
            
            estimated_time = total_tests * time_factor
            
            if estimated_time < 60:
                time_str = f"{estimated_time:.0f} segundos"
            elif estimated_time < 3600:
                time_str = f"{estimated_time/60:.1f} minutos"  
            else:
                time_str = f"{estimated_time/3600:.1f} horas"
            
            # 🔥 VERSÃO LIMPA - SEM APROVEITAMENTO
            avg_steps = total_steps_estimado / (otim_count * rebal_count) if (otim_count * rebal_count) > 0 else 0
            
            self.estimate_label.config(
                text=f"📊 {total_configs} configurações\n"
                     f"⚡ ~{total_tests:,} testes\n" 
                     f"⏱️ ~{time_str}\n"
                     f"📅 {total_calendar_days} dias\n"
                     f"📈 ~{avg_steps:.0f} steps/config",
                font=('TkDefaultFont', 8)
            )
            
        except Exception as e:
            self.estimate_label.config(text=f"❌ Erro: {str(e)}")

    def start_auto_optimization(self):
        """Iniciar processo de auto-otimização"""
        if not self.validate_auto_config():
            return
        
        # Desabilitar botão durante execução
        self.auto_optimize_btn.config(state='disabled', text='🔄 Executando...')
        self.status_auto_label.config(text="Iniciando auto-otimização...", foreground='blue')
        
        # Executar em thread separada para não travar interface
        import threading
        thread = threading.Thread(target=self.run_auto_optimization_thread)
        thread.daemon = True
        thread.start()

    def run_auto_optimization_thread(self):
        """Thread principal de auto-otimização - SEM BARRA DE PROGRESSO"""
        try:
            # 1. Preparar configurações
            configs = self.prepare_test_configurations()
            
            if len(configs) == 0:
                self.update_auto_status("Nenhuma configuração válida encontrada", 'red')
                return
            
            self.update_auto_status(f"Iniciando {len(configs)} configurações...", 'blue')
            
            # 2. Executar testes - APENAS COM STATUS TEXT
            results = []
            total_configs = len(configs)
            
            for i, config in enumerate(configs):
                # Atualizar apenas status (sem barra)
                config_desc = f"{config['otim_period']}+{config['rebal_period']}+{config['objective']}"
                status_msg = f"[{i+1}/{total_configs}] {config_desc}"
                self.root.after(0, lambda msg=status_msg: self.update_auto_status(msg, 'blue'))
                
                # Executar walk-forward para esta configuração
                config_result = self.run_walk_forward_test(config)
                
                if config_result:
                    results.append(config_result)
                    # Mostrar sucesso com número de steps
                    success_msg = f"[{i+1}/{total_configs}] ✅ {config_desc} ({config_result['n_steps']} steps)"
                    self.root.after(0, lambda msg=success_msg: self.update_auto_status(msg, 'green'))
                else:
                    # Mostrar falha
                    fail_msg = f"[{i+1}/{total_configs}] ❌ {config_desc} FALHOU"
                    self.root.after(0, lambda msg=fail_msg: self.update_auto_status(msg, 'orange'))
                
                # Pequena pausa para interface atualizar
                import time
                time.sleep(0.1)
            
            # 3. Processar e exibir resultados
            if results:
                self.process_and_display_results(results)
                final_msg = f"🎉 Concluído! {len(results)}/{total_configs} configurações válidas"
                self.update_auto_status(final_msg, 'green')
            else:
                self.update_auto_status("❌ Nenhum resultado válido obtido", 'red')
                
        except Exception as e:
            self.update_auto_status(f"Erro: {str(e)}", 'red')
        
        finally:
            # Reabilitar botão (sem mexer na barra)
            self.root.after(0, lambda: self.auto_optimize_btn.config(
                state='normal', 
                text='🚀 INICIAR AUTO-OTIMIZAÇÃO'
            ))

    def update_auto_status(self, message, color='black'):
        """Atualizar status na thread principal"""
        self.root.after(0, self.status_auto_label.config, 
                       {'text': message, 'foreground': color})

    def prepare_test_configurations(self):
        """Preparar todas as combinações de configurações para teste"""
        configs = []
        
        # Obter seleções
        selected_otim = [period for period, var in self.otim_windows.items() if var.get()]
        selected_rebal = [period for period, var in self.rebalance_periods.items() if var.get()]  
        selected_obj = [obj for obj, var in self.objectives.items() if var.get()]
        
        # Mapeamento de objetivos para códigos internos
        obj_mapping = {
            'sharpe': 'sharpe',
            'volatility': 'volatility',
            'hc10': 'hc10',
            'quality_linear': 'quality_linear'
        }
        
        # Gerar todas as combinações
        for otim_period in selected_otim:
            for rebal_period in selected_rebal:
                for obj_key in selected_obj:
                    config = {
                        'otim_period': otim_period,
                        'rebal_period': rebal_period,
                        'objective': obj_mapping[obj_key],
                        'rank_min': self.rank_min_var.get(),
                        'rank_max': self.rank_max_var.get(),
                        'weight_min': self.weight_min_var.get() / 100,
                        'weight_max': self.weight_max_var.get() / 100,
                        'use_shorts': self.use_auto_shorts.get(),
                        'short_asset': self.short_asset_var.get() if self.use_auto_shorts.get() else None,
                        'short_weight': self.short_weight_var.get() / 100 if self.use_auto_shorts.get() else 0,
                        'desc': f"{otim_period}_{rebal_period}_{obj_key}"
                    }
                    configs.append(config)
        
        return configs

    def run_walk_forward_test(self, config):
        """Executar teste walk-forward - VERSÃO COM TAXA REF ACUMULADA"""
        try:
            # Converter períodos para dias corridos de calendário
            period_to_days = {
                '3m': 90, '6m': 180, '1a': 365, '2a': 730, '3a': 1095,
                '1sem': 7, '2sem': 14, '1mes': 30, '2mes': 60, '3mes': 90
            }
            
            otim_days = period_to_days[config['otim_period']]
            rebal_days = period_to_days[config['rebal_period']]
            
            # IMPORTANTE: Usar dados BRUTOS, não processados
            if hasattr(self, 'dados_brutos') and self.dados_brutos is not None:
                df_trabalho = self.dados_brutos.copy()
            else:
                print("AVISO: Usando dados já processados. Resultados podem não coincidir com modo manual.")
                df_trabalho = self.df.copy()
            
            # Verificar coluna de data
            if 'Data' not in df_trabalho.columns:
                print("Coluna 'Data' não encontrada")
                return None
                
            # Extrair datas inicial e final
            data_inicial = pd.to_datetime(df_trabalho['Data'].iloc[0])
            data_final = pd.to_datetime(df_trabalho['Data'].iloc[-1])
            total_calendar_days = (data_final - data_inicial).days + 1
            
            print(f"=== DEBUG WALK-FORWARD (BASE ZERO ÚNICA + ACUMULAÇÃO) ===")
            print(f"Config: {config['desc']}")
            print(f"Data inicial: {data_inicial.strftime('%d/%m/%Y')}")
            print(f"Data final: {data_final.strftime('%d/%m/%Y')}")
            print(f"Total dias corridos: {total_calendar_days}")
            print(f"Janela otimização: {otim_days} dias corridos")
            print(f"Período rebalanceamento: {rebal_days} dias corridos")
            
            # Verificar se temos dados suficientes
            min_required_days = otim_days + rebal_days * 2
            if total_calendar_days < min_required_days:
                print(f"Período insuficiente: {total_calendar_days} < {min_required_days} dias corridos")
                return None
            
            # Calcular steps baseado em dias corridos
            max_possible_steps = (total_calendar_days - otim_days) // rebal_days
            max_steps = max_possible_steps  # ✅ USA TODOS OS STEPS

            # Proteção apenas para casos extremos
            if max_steps > 1000000:
                print(f"⚠️ AVISO: {max_steps} steps é muito! Limitando a 1000000.")
                max_steps = 1000000
            
            print(f"Steps possíveis: {max_possible_steps}")
            print(f"Max steps que será usado: {max_steps}")
            
            if max_steps < 1:
                print(f"Steps insuficientes: {max_steps}")
                return None
            
            # ========== INICIALIZAR VARIÁVEIS DE ACUMULAÇÃO ==========
            ret_acumulado_config = 1.0  # Para retorno
            taxa_ref_acumulada_config = 1.0  # NOVO: Para taxa de referência
            primeira_data_validacao = None
            ultima_data_validacao = None
            step_metrics_individuais = []
            volatilidades = []  # NOVO: Para calcular média das volatilidades
            
            # Loop pelos steps
            for step_num in range(1, max_steps + 1):
                try:
                    # Calcular datas baseado em dias corridos
                    inicio_otim_days = (step_num - 1) * rebal_days
                    fim_otim_days = inicio_otim_days + otim_days
                    fim_valid_days = fim_otim_days + rebal_days
                    
                    # Converter para datas reais
                    data_inicio_otim = data_inicial + pd.Timedelta(days=inicio_otim_days)
                    data_fim_otim = data_inicial + pd.Timedelta(days=fim_otim_days - 1)
                    data_fim_valid = data_inicial + pd.Timedelta(days=fim_valid_days - 1)
                    
                    print(f"\nStep {step_num}:")
                    print(f"  Otimização: {data_inicio_otim.strftime('%d/%m/%Y')} a {data_fim_otim.strftime('%d/%m/%Y')}")
                    print(f"  Validação: {(data_fim_otim + pd.Timedelta(days=1)).strftime('%d/%m/%Y')} a {data_fim_valid.strftime('%d/%m/%Y')}")
                    
                    # Verificar se as datas estão dentro do período disponível
                    if data_fim_valid > data_final:
                        print(f"PAROU: data_fim_valid > data_final")
                        break
                    
                    # ========== PEGAR PERÍODO COMPLETO ==========
                    # Filtrar dados brutos do PERÍODO COMPLETO (otim + valid)
                    df_periodo_completo_bruto = df_trabalho[
                        (pd.to_datetime(df_trabalho['Data']) >= data_inicio_otim) & 
                        (pd.to_datetime(df_trabalho['Data']) <= data_fim_valid)
                    ].copy().reset_index(drop=True)
                    
                    print(f"  Período completo: {len(df_periodo_completo_bruto)} registros")
                    
                    # ========== APLICAR BASE ZERO ÚNICA ==========
                    print(f"  Aplicando transformação base zero ÚNICA...")
                    
                    # Transformar PERÍODO COMPLETO para base zero
                    df_completo_base0, cols_removidas = self.transformar_base_zero(
                        df_periodo_completo_bruto.set_index('Data')
                    )
                    
                    if df_completo_base0 is None:
                        print(f"  Falha na transformação base zero")
                        continue
                    
                    df_completo_base0 = df_completo_base0.reset_index()
                    df_completo_base0.rename(columns={'index': 'Data'}, inplace=True)
                    
                    # ========== SEPARAR PERÍODOS APÓS BASE ZERO ==========
                    # Agora separar os períodos já em base zero
                    df_otim_base0 = df_completo_base0[
                        (pd.to_datetime(df_completo_base0['Data']) >= data_inicio_otim) & 
                        (pd.to_datetime(df_completo_base0['Data']) <= data_fim_otim)
                    ].copy().reset_index(drop=True)
                    
                    df_valid_base0 = df_completo_base0[
                        (pd.to_datetime(df_completo_base0['Data']) > data_fim_otim) & 
                        (pd.to_datetime(df_completo_base0['Data']) <= data_fim_valid)
                    ].copy().reset_index(drop=True)
                    
                    print(f"  Após separação: otim={len(df_otim_base0)}, valid={len(df_valid_base0)}")
                    
                    # Verificar se há dados suficientes
                    if len(df_otim_base0) < 10 or len(df_valid_base0) < 2:
                        print(f"  Dados insuficientes após base zero")
                        continue
                    
                    # Executar step com dados em base zero e período completo
                    step_result = self.execute_single_step(
                        df_otim_base0, 
                        df_valid_base0, 
                        df_completo_base0,
                        config, 
                        step_num
                    )
                    
                    if step_result:
                        # ========== ACUMULAR RETORNO ==========
                        retorno_step = step_result['total_return']
                        ret_acumulado_config *= (1 + retorno_step)
                        
                        # ========== ACUMULAR TAXA REF ==========
                        if 'risk_free_period' in step_result:
                            taxa_ref_step = step_result['risk_free_period']
                            taxa_ref_acumulada_config *= (1 + taxa_ref_step)
                        
                        # ========== GUARDAR VOLATILIDADE ==========
                        if 'volatility' in step_result:
                            volatilidades.append(step_result['volatility'])
                        
                        # ========== GUARDAR DATAS ==========
                        # Primeira data de validação (só no primeiro step bem-sucedido)
                        if primeira_data_validacao is None:
                            primeira_data_validacao = pd.to_datetime(df_valid_base0['Data'].iloc[0])
                            print(f"  📅 Primeira data validação guardada: {primeira_data_validacao.strftime('%d/%m/%Y')}")
                        
                        # Sempre atualizar última data
                        ultima_data_validacao = pd.to_datetime(df_valid_base0['Data'].iloc[-1])
                        
                        # Guardar métricas individuais do step (para Sharpe, Sortino, etc)
                        step_metrics_individuais.append(step_result)
                        
                        print(f"  ✅ Step {step_num} concluído e acumulado")
                        print(f"     Retorno do step: {retorno_step:.2%}")
                        print(f"     Retorno acumulado até agora: {(ret_acumulado_config-1):.2%}")
                    else:
                        print(f"  ⚠️ Step {step_num} FALHOU")
                    
                except Exception as e:
                    print(f"  ERRO no step {step_num}: {str(e)}")
                    import traceback
                    traceback.print_exc()
            
            print(f"\n=== LOOP CONCLUÍDO ===")
            print(f"Steps com sucesso: {len(step_metrics_individuais)}")
            
            # ========== CALCULAR MÉTRICAS FINAIS ==========
            if step_metrics_individuais and len(step_metrics_individuais) >= 1:
                # Retorno total acumulado
                retorno_total_config = ret_acumulado_config - 1
                taxa_ref_total_config = taxa_ref_acumulada_config - 1
                
                # Calcular dias corridos totais
                if primeira_data_validacao and ultima_data_validacao:
                    dias_totais = (ultima_data_validacao - primeira_data_validacao).days + 1
                    
                    # Anualizar retorno
                    if dias_totais > 0:
                        retorno_anualizado = (1 + retorno_total_config) ** (365/dias_totais) - 1
                        taxa_ref_anualizada = (1 + taxa_ref_total_config) ** (365/dias_totais) - 1
                    else:
                        retorno_anualizado = 0
                        taxa_ref_anualizada = 0
                else:
                    retorno_anualizado = retorno_total_config
                    taxa_ref_anualizada = taxa_ref_total_config
                
                # Volatilidade média
                vol_media = sum(volatilidades) / len(volatilidades) if volatilidades else 0
                
                # CALCULAR SHARPE FINAL
                if vol_media > 0:
                    sharpe_final = (retorno_anualizado - taxa_ref_anualizada) / vol_media
                else:
                    sharpe_final = 0
                
                print(f"📊 CÁLCULO SHARPE FINAL:")
                print(f"   Retorno anualizado: {retorno_anualizado:.2%}")
                print(f"   Taxa ref anualizada: {taxa_ref_anualizada:.2%}")
                print(f"   Volatilidade média: {vol_media:.2%}")
                print(f"   Sharpe = ({retorno_anualizado:.4f} - {taxa_ref_anualizada:.4f}) / {vol_media:.4f}")
                print(f"   Sharpe = {sharpe_final:.3f}")
                
                # Calcular médias das outras métricas
                return self.calculate_average_metrics_v2(
                    step_metrics_individuais, 
                    config,
                    retorno_anualizado,
                    taxa_ref_anualizada,
                    vol_media,
                    sharpe_final,
                    retorno_total_config,
                    dias_totais
                )

            else:
                print(f"Steps insuficientes para análise: {len(step_metrics_individuais)}")
                return None
                
        except Exception as e:
            print(f"Erro no walk-forward test: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def execute_single_step(self, df_otim, df_valid, df_completo, config, step_num):
        """Step walk-forward - USANDO PERÍODO COMPLETO COM BASE ZERO ÚNICA"""
        try:
            print(f"\n🎯 STEP {step_num} - VALIDAÇÃO DE MÉTRICAS")
            
            # 1. RANKING E SELEÇÃO
            ranking_result = calculate_asset_ranking(
                df_otim, 
                self.risk_free_column_name,
                peso_inc=0.33, peso_desv=0.33, peso_cor=0.33
            )
            
            if not ranking_result:
                return None
            
            df_ranking = ranking_result['ranking']
            score_min = config['rank_min'] / 100  
            score_max = config['rank_max'] / 100  

            filtered_ranking = df_ranking[
                (df_ranking['Índice'] >= score_min) & 
                (df_ranking['Índice'] <= score_max)
            ]

            if len(filtered_ranking) < 2:
                return None

            selected_assets = filtered_ranking['Ativo'].tolist()
            print(f"✅ {len(selected_assets)} ativos selecionados")
            
            # BACKUP ESTADO
            original_df = self.df
            original_optimizer = self.optimizer
            original_result = getattr(self, 'result', None)
            
            try:
                # ========================================
                # OTIMIZAÇÃO (período treino)
                # ========================================
                self.df = df_otim.copy()
                
                # Preparar lista de ativos para otimização
                if config['use_shorts'] and config['short_asset']:
                    if config['short_asset'] not in df_otim.columns:
                        print(f"❌ Ativo short '{config['short_asset']}' não encontrado")
                        return None
                    all_assets = selected_assets + [config['short_asset']]
                else:
                    all_assets = selected_assets
                
                self.optimizer = PortfolioOptimizer(self.df, all_assets if config['use_shorts'] else selected_assets)

                # Taxa livre de risco para otimização
                if hasattr(self.optimizer, 'risk_free_rate_total'):
                    risk_free_rate = self.optimizer.risk_free_rate_total
                    print(f"🎯 Taxa para otimização: {risk_free_rate:.4f} ({risk_free_rate:.2%})")
                else:
                    risk_free_rate = 0.0

                objective_map = {
                    'sharpe': 'sharpe',
                    'volatility': 'volatility',
                    'hc10': 'hc10',
                    'quality_linear': 'quality_linear'
                }

                # Executar otimização
                if config['use_shorts'] and config['short_asset']:
                    print(f"🔄 OTIMIZAÇÃO COM SHORTS")
                    self.result = self.optimizer.optimize_portfolio_with_shorts(
                        selected_assets=selected_assets,
                        short_assets=[config['short_asset']],
                        short_weights={config['short_asset']: config['short_weight']},
                        objective_type=objective_map[config['objective']],
                        max_weight=config['weight_max'],
                        min_weight=config['weight_min'],
                        risk_free_rate=risk_free_rate,
                        individual_constraints=None
                    )
                else:
                    print(f"📊 OTIMIZAÇÃO NORMAL (SEM SHORTS)")
                    self.result = self.optimizer.optimize_portfolio(
                        objective_type=objective_map[config['objective']],
                        max_weight=config['weight_max'],
                        min_weight=config['weight_min'],
                        risk_free_rate=risk_free_rate,
                        individual_constraints=None
                    )

                if not self.result['success']:
                    print(f"❌ Otimização falhou: {self.result.get('message', 'Erro desconhecido')}")
                    return None
                    
                optimized_weights = self.result['weights']
                optimized_assets = self.result['assets']

                # Debug composição
                print(f"\n🔍 COMPOSIÇÃO DO PORTFÓLIO:")
                for i, asset in enumerate(optimized_assets):
                    weight = optimized_weights[i]
                    if abs(weight) > 0.001:
                        tipo = "SHORT" if weight < 0 else "LONG"
                        print(f"   {asset}: {weight:.3f} ({weight*100:.1f}%) - {tipo}")

                print(f"✅ Otimização concluída")
                
                # ========================================
                # OUT-OF-SAMPLE - USANDO PERÍODO COMPLETO
                # ========================================
                
                print("\n🔍 Calculando OUT-OF-SAMPLE (BASE ZERO ÚNICA)")
                
                # Verificar disponibilidade dos ativos no período completo
                available_assets = [asset for asset in optimized_assets if asset in df_completo.columns]
                if len(available_assets) != len(optimized_assets):
                    print("⚠️ Nem todos os ativos disponíveis no período completo")
                    return None
                
                # IMPORTANTE: Usar o PERÍODO COMPLETO já em base zero
                optimizer_completo = PortfolioOptimizer(df_completo, available_assets)
                
                # Calcular retornos do portfólio para período completo
                portfolio_returns_completo = np.dot(optimizer_completo.returns_data.values, optimized_weights)
                cumulative_completo = np.cumsum(portfolio_returns_completo)
                
                # Identificar índices dos períodos
                n_dias_otim = len(df_otim)
                n_dias_total = len(df_completo)
                n_dias_valid = n_dias_total - n_dias_otim
                
                print(f"📊 Divisão do período completo:")
                print(f"   Total: {n_dias_total} registros")
                print(f"   Otimização: {n_dias_otim} registros")
                print(f"   Validação: {n_dias_valid} registros")
                
                if n_dias_valid <= 0:
                    print("⚠️ Período de validação muito curto")
                    return None
                
                # ========== DIAS CORRIDOS REAIS ==========
                # Usar datas do df_valid para calcular dias corridos
                primeira_data_valid = pd.to_datetime(df_valid['Data'].iloc[0])
                ultima_data_valid = pd.to_datetime(df_valid['Data'].iloc[-1])
                n_dias_corridos_valid = (ultima_data_valid - primeira_data_valid).days + 1
                
                print(f"\n📅 Período validação: {primeira_data_valid.strftime('%d/%m/%Y')} a {ultima_data_valid.strftime('%d/%m/%Y')}")
                print(f"   Dias corridos: {n_dias_corridos_valid}")
                
                # ========== 1. RETORNO DO PORTFÓLIO ==========
                # Valores acumulados usando o período completo
                portfolio_acum_fim_otim = cumulative_completo[n_dias_otim - 1]
                portfolio_acum_fim_valid = cumulative_completo[-1]
                
                print(f"\n📊 RETORNO DO PORTFÓLIO (BASE ZERO ÚNICA):")
                print(f"   Acumulado fim otimização: {portfolio_acum_fim_otim:.6f}")
                print(f"   Acumulado fim validação: {portfolio_acum_fim_valid:.6f}")
                
                # Retorno do período de validação (fórmula correta)
                retorno_periodo_valid = (1 + portfolio_acum_fim_valid) / (1 + portfolio_acum_fim_otim) - 1
                print(f"   Retorno período validação: {retorno_periodo_valid:.4f} ({retorno_periodo_valid:.2%})")
                
                # Anualizar retorno
                if n_dias_corridos_valid > 0:
                    retorno_anual_valid = (1 + retorno_periodo_valid) ** (365/n_dias_corridos_valid) - 1
                else:
                    retorno_anual_valid = 0
                print(f"   Retorno anualizado: {retorno_anual_valid:.4f} ({retorno_anual_valid:.2%})")
                
                # ========== 2. TAXA LIVRE DE RISCO ==========
                if hasattr(optimizer_completo, 'risk_free_cumulative') and optimizer_completo.risk_free_cumulative is not None:
                    try:
                        # Valores acumulados da taxa livre usando período completo
                        taxa_acum_fim_otim = optimizer_completo.risk_free_cumulative.iloc[n_dias_otim - 1]
                        taxa_acum_fim_valid = optimizer_completo.risk_free_cumulative.iloc[-1]
                        
                        print(f"\n📊 TAXA LIVRE DE RISCO (BASE ZERO ÚNICA):")
                        print(f"   Acumulada fim otimização: {taxa_acum_fim_otim:.6f}")
                        print(f"   Acumulada fim validação: {taxa_acum_fim_valid:.6f}")
                        
                        # Taxa do período de validação (fórmula correta)
                        taxa_periodo_valid = (1 + taxa_acum_fim_valid) / (1 + taxa_acum_fim_otim) - 1
                        print(f"   Taxa período validação: {taxa_periodo_valid:.4f} ({taxa_periodo_valid:.2%})")
                        
                        # Anualizar taxa
                        if n_dias_corridos_valid > 0:
                            taxa_anual_valid = (1 + taxa_periodo_valid) ** (365/n_dias_corridos_valid) - 1
                        else:
                            taxa_anual_valid = 0
                        print(f"   Taxa anualizada: {taxa_anual_valid:.4f} ({taxa_anual_valid:.2%})")
                        
                    except Exception as e:
                        print(f"   Erro no cálculo da taxa: {e}")
                        taxa_periodo_valid = 0
                        taxa_anual_valid = 0
                else:
                    taxa_periodo_valid = 0
                    taxa_anual_valid = 0
                    print("   Taxa livre não disponível")
                
                # ========== 3. VOLATILIDADE ==========
                # Usar apenas o período de validação para volatilidade
                portfolio_cumulative_validacao = cumulative_completo[n_dias_otim:]
                
                if len(portfolio_cumulative_validacao) > 1:
                    # Adicionar o valor do fim da otimização como ponto inicial
                    portfolio_cumulative_validacao_completo = np.concatenate(
                        [[portfolio_acum_fim_otim], portfolio_cumulative_validacao]
                    )
                    
                    # Calcular variações percentuais diárias
                    variac_result_pu = (1 + portfolio_cumulative_validacao_completo[1:]) / (1 + portfolio_cumulative_validacao_completo[:-1])
                    portfolio_returns_pct_valid = variac_result_pu - 1
                    
                    # Volatilidade anualizada
                    vol_valid = np.std(portfolio_returns_pct_valid, ddof=0) * np.sqrt(252)
                else:
                    vol_valid = 0
                    portfolio_returns_pct_valid = np.array([])
                
                print(f"\n📊 VOLATILIDADE:")
                print(f"   Volatilidade anualizada: {vol_valid:.4f} ({vol_valid:.2%})")
                
                # ========== 4. SHARPE E SORTINO ==========
                # Excesso de retorno
                excesso_anual_valid = retorno_anual_valid - taxa_anual_valid
                print(f"\n📊 PERFORMANCE:")
                print(f"   Excesso anualizado: {excesso_anual_valid:.4f} ({excesso_anual_valid:.2%})")
                
                # Sharpe
                if vol_valid > 0:
                    sharpe_valid = excesso_anual_valid / vol_valid
                else:
                    sharpe_valid = 0
                print(f"   Sharpe Ratio: {sharpe_valid:.3f}")
                
                # ========== 5. VaR ==========
                if len(portfolio_returns_pct_valid) > 0:
                    mean_daily_return = np.mean(portfolio_returns_pct_valid)
                    std_daily_return = np.std(portfolio_returns_pct_valid, ddof=0)
                    var_95_daily_valid = mean_daily_return - 1.65 * std_daily_return
                else:
                    var_95_daily_valid = 0
                print(f"   VaR 95% diário: {var_95_daily_valid:.4f} ({var_95_daily_valid:.2%})")
                
                # ========== 6. PERCENTUAL POSITIVOS ==========
                if len(portfolio_returns_pct_valid) > 0:
                    positive_returns = portfolio_returns_pct_valid[portfolio_returns_pct_valid > 0]
                    total_returns = len(portfolio_returns_pct_valid)
                    positive_return_pct = len(positive_returns) / total_returns if total_returns > 0 else 0
                else:
                    positive_return_pct = 0
                
                print(f"\n✅ RESUMO OUT-OF-SAMPLE:")
                print(f"   Retorno Total: {retorno_periodo_valid:.2%}")
                print(f"   Retorno Anual: {retorno_anual_valid:.2%}")
                print(f"   Taxa Anual: {taxa_anual_valid:.2%}")
                print(f"   Excesso Anual: {excesso_anual_valid:.2%}")
                print(f"   Volatilidade: {vol_valid:.2%}")
                print(f"   Sharpe: {sharpe_valid:.3f}")
                print(f"   VaR 95%: {var_95_daily_valid:.2%}")
                print(f"   Dias: {n_dias_corridos_valid}")
                
                # RETORNAR métricas
                return {
                    'n_assets': len(available_assets),
                    'sharpe': sharpe_valid,  # Manter por enquanto, mas não vamos usar
                    'annual_return': retorno_anual_valid,
                    'volatility': vol_valid,
                    'positive_return_pct': positive_return_pct,
                    'total_return': retorno_periodo_valid,
                    'risk_free_annual': taxa_anual_valid,
                    'risk_free_period': taxa_periodo_valid,  # ADICIONAR ESTA LINHA
                    'excess_annual': excesso_anual_valid,
                    'var_95': var_95_daily_valid,
                    'n_days': n_dias_corridos_valid
                }
                
            finally:
                # RESTAURAR ESTADO
                self.df = original_df
                self.optimizer = original_optimizer
                if original_result is not None:
                    self.result = original_result
                else:
                    if hasattr(self, 'result'):
                        delattr(self, 'result')
                
        except Exception as e:
            print(f"❌ Erro: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def calculate_average_metrics_v2(self, step_metrics, config, retorno_anualizado, 
                                     taxa_ref_anualizada, vol_media, sharpe_final,
                                     retorno_total, dias_totais):
        """Calcular métricas médias - VERSÃO COM SHARPE RECALCULADO"""
        
        avg_metrics = {}
        
        # Média simples apenas para N_Ativos e Positivos%
        for metric in ['n_assets', 'positive_return_pct']:
            values = [step[metric] for step in step_metrics 
                     if metric in step and step[metric] is not None]
            avg_metrics[metric] = sum(values) / len(values) if values else 0
        
        # Usar valores já calculados
        avg_metrics['annual_return'] = retorno_anualizado
        avg_metrics['risk_free_annual'] = taxa_ref_anualizada
        avg_metrics['volatility'] = vol_media
        avg_metrics['sharpe'] = sharpe_final
        
        print(f"\n📊 MÉTRICAS FINAIS DA CONFIGURAÇÃO:")
        print(f"   Retorno Anual: {retorno_anualizado:.2%}")
        print(f"   Taxa Ref Anual: {taxa_ref_anualizada:.2%}")
        print(f"   Volatilidade Média: {vol_media:.2%}")
        print(f"   Sharpe Final: {sharpe_final:.3f}")
        print(f"   % Positivos Médio: {avg_metrics['positive_return_pct']:.1%}")
        print(f"   Steps com sucesso: {len(step_metrics)}")
        
        result = {
            'config': config,
            'metrics': avg_metrics,
            'n_steps': len(step_metrics),
            'total_return': retorno_total,
            'total_days': dias_totais
        }
        
        return result

    def process_and_display_results(self, results):
        """Processar e exibir resultados - VERSÃO COM TAXA REF"""
        # Limpar tabela anterior
        for item in self.auto_results_tree.get_children():
            self.auto_results_tree.delete(item)
        
        # Ordenar por Sharpe
        results.sort(key=lambda x: x['metrics']['sharpe'], reverse=True)
        
        # Mapear objetivos
        obj_names = {
            'sharpe': 'Sharpe',
            'volatility': 'MinRisco',
            'hc10': 'Inc/[(1-R²)×Vol]',
            'quality_linear': 'Qualidade'
        }
        
        # Inserir resultados
        for i, result in enumerate(results):
            config = result['config']
            metrics = result['metrics']
            
            values = (
                i + 1,  # Rank
                config['otim_period'],
                config['rebal_period'],
                obj_names.get(config['objective'], config['objective']),
                int(metrics['n_assets']),
                f"{metrics['sharpe']:.3f}",
                f"{metrics['annual_return']:.1%}",
                f"{metrics.get('risk_free_annual', 0):.1%}",  # Taxa Ref
                f"{metrics['volatility']:.1%}",
                f"{metrics['positive_return_pct']:.1%}"
            )
            
            self.auto_results_tree.insert('', 'end', values=values)

    def export_auto_results_csv(self):
        """Exportar resultados da auto-otimização para CSV - VERSÃO ATUALIZADA"""
        # Verificar se há dados
        if not self.auto_results_tree.get_children():
            messagebox.showerror("Erro", "Não há resultados para exportar!")
            return
        
        try:
            # Diálogo para salvar
            filename = filedialog.asksaveasfilename(
                title="Salvar Resultados Auto-Otimização",
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
            )
            
            if filename:
                # Coletar dados da tabela
                data = []
                # COLUNAS ATUALIZADAS (sem Sortino, com TxRef)
                columns = ['Rank', 'Otimização', 'Rebalanceamento', 'Objetivo', 
                          'N_Ativos', 'Sharpe', 'Retorno(%)', 'Taxa_Ref(%)', 
                          'Volatilidade(%)', 'Positivos(%)']
                
                # Pegar todos os itens do TreeView
                for item in self.auto_results_tree.get_children():
                    values = self.auto_results_tree.item(item)['values']
                    data.append(values)
                
                # Criar DataFrame
                df = pd.DataFrame(data, columns=columns)
                
                # Salvar CSV
                df.to_csv(filename, index=False, encoding='utf-8-sig')
                
                messagebox.showinfo("Sucesso", f"Resultados exportados para:\n{filename}")
                
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao exportar CSV:\n{str(e)}")

    def export_auto_results_excel(self):
        """Exportar resultados da auto-otimização para Excel - VERSÃO ATUALIZADA"""
        # Verificar se há dados
        if not self.auto_results_tree.get_children():
            messagebox.showerror("Erro", "Não há resultados para exportar!")
            return
        
        try:
            # Diálogo para salvar
            filename = filedialog.asksaveasfilename(
                title="Salvar Resultados Auto-Otimização",
                defaultextension=".xlsx",
                filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")]
            )
            
            if filename:
                # Coletar dados da tabela
                data = []
                # COLUNAS ATUALIZADAS (sem Sortino, com TxRef)
                columns = ['Rank', 'Otimização', 'Rebalanceamento', 'Objetivo', 
                          'N_Ativos', 'Sharpe', 'Retorno(%)', 'Taxa_Ref(%)', 
                          'Volatilidade(%)', 'Positivos(%)']
                
                # Pegar todos os itens do TreeView
                for item in self.auto_results_tree.get_children():
                    values = self.auto_results_tree.item(item)['values']
                    data.append(values)
                
                # Criar DataFrame
                df = pd.DataFrame(data, columns=columns)
                
                # Criar Excel com formatação
                with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                    df.to_excel(writer, sheet_name='Resultados Auto-Otimização', index=False)
                    
                    # Ajustar largura das colunas
                    worksheet = writer.sheets['Resultados Auto-Otimização']
                    for column in worksheet.columns:
                        max_length = 0
                        column_letter = column[0].column_letter
                        for cell in column:
                            try:
                                if len(str(cell.value)) > max_length:
                                    max_length = len(str(cell.value))
                            except:
                                pass
                        adjusted_width = min(max_length + 2, 30)
                        worksheet.column_dimensions[column_letter].width = adjusted_width
                
                messagebox.showinfo("Sucesso", f"Resultados exportados para:\n{filename}")
                
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao exportar Excel:\n{str(e)}")

    def validate_auto_config(self):
        """Validar configuração antes de iniciar - ATUALIZADO"""
        if not hasattr(self, 'df') or self.df is None:
            messagebox.showerror("Erro", "Carregue e processe dados primeiro!")
            return False
            
        # Verificar se há pelo menos uma opção selecionada
        if not any(var.get() for var in self.otim_windows.values()):
            messagebox.showerror("Erro", "Selecione pelo menos uma janela de otimização!")
            return False
            
        if not any(var.get() for var in self.rebalance_periods.values()):
            messagebox.showerror("Erro", "Selecione pelo menos um período de rebalanceamento!")
            return False
            
        if not any(var.get() for var in self.objectives.values()):
            messagebox.showerror("Erro", "Selecione pelo menos um objetivo!")
            return False
        
        return True



def main():
    """Função principal"""
    root = tk.Tk()
    
    # Configurar estilo
    style = ttk.Style()
    style.theme_use('clam')  # Tema mais moderno
    
    # Configurações de estilo personalizadas
    style.configure("Accent.TButton", background="#0078d4", foreground="white")
    
    # Criar aplicação
    app = PortfolioOptimizerGUI(root)
    
    # Executar
    root.mainloop()

if __name__ == "__main__":
    main()
