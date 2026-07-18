import numpy as np
import pandas as pd
from scipy.optimize import minimize

class PortfolioOptimizer:
    def __init__(self, returns_data, selected_assets=None):
        """
        Inicializa o otimizador com dados de retorno
        returns_data: DataFrame com retornos dos ativos (base 0)
        selected_assets: Lista de ativos selecionados (None = todos)
        """
        self.original_data = returns_data.copy()  # Preservar dados originais com datas
        
        # Assumir que primeira coluna é data, resto são ativos
        if isinstance(returns_data.columns[0], str) and 'data' in returns_data.columns[0].lower():
            self.dates = pd.to_datetime(returns_data.iloc[:, 0])  # Guardar datas
            
            # Verificar se segunda coluna é Taxa Livre de Risco
            if len(returns_data.columns) > 2 and isinstance(returns_data.columns[1], str) and any(
                term in returns_data.columns[1].lower() for term in ['taxa', 'livre', 'risco', 'ibov', 'ref', 'cdi', 'selic']
            ):
                self.risk_free_returns = returns_data.iloc[:, 1].apply(pd.to_numeric, errors='coerce')  # Coluna B
                self.returns_data = returns_data.iloc[:, 2:]  # Ativos começam na coluna C
                # Calcular taxa livre de risco acumulada
                self.risk_free_cumulative = np.cumsum(self.risk_free_returns.dropna())
                if len(self.risk_free_cumulative) > 0:
                    self.risk_free_rate_total = self.risk_free_cumulative.iloc[-1]
                else:
                    self.risk_free_rate_total = 0.0
            else:
                self.risk_free_returns = None
                self.risk_free_cumulative = None
                self.risk_free_rate_total = 0.0
                self.returns_data = returns_data.iloc[:, 1:]  # Remove coluna de data
        else:
            self.returns_data = returns_data
            self.dates = None
            self.risk_free_returns = None
            self.risk_free_cumulative = None
            self.risk_free_rate_total = 0.0
        
        # Converter para numérico e remover NaNs
        self.returns_data = self.returns_data.apply(pd.to_numeric, errors='coerce').dropna()
        
        # Se temos datas, precisamos sincronizá-las com os dados após dropna
        if self.dates is not None:
            # Pegar os índices que sobraram após dropna
            valid_indices = self.returns_data.index
            self.dates = self.dates.iloc[valid_indices].reset_index(drop=True)
            self.returns_data = self.returns_data.reset_index(drop=True)
            
            # Sincronizar risk_free_returns também se existir
            if self.risk_free_returns is not None:
                self.risk_free_returns = self.risk_free_returns.iloc[valid_indices].reset_index(drop=True)
                # Recalcular acumulado com dados sincronizados
                self.risk_free_cumulative = np.cumsum(self.risk_free_returns)
                self.risk_free_rate_total = self.risk_free_cumulative.iloc[-1] if len(self.risk_free_cumulative) > 0 else 0.0
        
        # Se há ativos selecionados, filtrar apenas esses
        if selected_assets is not None:
            self.returns_data = self.returns_data[selected_assets]
        
        self.assets = self.returns_data.columns.tolist()
        self.n_assets = len(self.assets)
        self.n_periods = len(self.returns_data)
        
        print(f"Otimizador inicializado com {self.n_assets} ativos selecionados e {self.n_periods} períodos")
        if self.risk_free_rate_total > 0:
            print(f"Taxa livre de risco detectada: {self.risk_free_rate_total:.2%}")
    
    def calculate_portfolio_metrics(self, weights, risk_free_rate=0.0):
	    """
	    Calcula métricas do portfólio (EXATAMENTE como na planilha)
	    weights: pesos do portfólio
	    risk_free_rate: taxa livre de risco ACUMULADA do período (ex: 0.12 para 12%)
	    """
	    # Garante que weights é array numpy
	    weights = np.array(weights)
	    
	    # COLUNA GU: Retornos diários do portfólio (SOMARPRODUTO de cada linha pelos pesos)
	    portfolio_returns_daily = np.dot(self.returns_data.values, weights)
	    
	    # COLUNA GV: Retornos acumulados do portfólio (soma cumulativa da GU)
	    portfolio_cumulative = np.cumsum(portfolio_returns_daily)
	    
	    # ========== CORREÇÃO PARA BASE 0 ==========
	    # Calcular Variac_Result_PU: variação percentual diária do PU
	    # Primeiro, criar array com 0 no início para representar t=0
	    portfolio_cumulative_with_zero = np.concatenate([[0], portfolio_cumulative])
	    
	    # Calcular fatores: (1 + Retorno_Total[t]) / (1 + Retorno_Total[t-1])
	    variac_result_pu = (1 + portfolio_cumulative_with_zero[1:]) / (1 + portfolio_cumulative_with_zero[:-1])
	    
	    # Retornos percentuais diários = Variac_Result_PU - 1
	    portfolio_returns_pct = variac_result_pu - 1
	    
	    # HC5: Volatilidade anualizada (DESVPAD.P dos retornos percentuais × RAIZ(252))
	    portfolio_vol = np.std(portfolio_returns_pct, ddof=0) * np.sqrt(252)
	    # ========== FIM DA CORREÇÃO ==========
	    
	    # GV_final: Último valor da coluna GV (retorno acumulado total)
	    gv_final = portfolio_cumulative[-1]
	    
	    # HC8: Sharpe ratio CORRIGIDO com taxa livre de risco
	    # Fórmula: (Retorno Total - Taxa Livre de Risco) / Volatilidade
	    excess_return = gv_final - risk_free_rate
	    sharpe_ratio = excess_return / portfolio_vol if portfolio_vol > 0 else 0
	    
	    # NOVO: Sortino Ratio
	    # Downside Deviation = volatilidade apenas dos retornos negativos
	    # Usar 0 como threshold (definição clássica)
	    negative_returns = portfolio_returns_pct[portfolio_returns_pct < 0]
	    
	    if len(negative_returns) > 0:
		    # Desvio padrão dos retornos negativos, anualizado
		    downside_deviation = np.std(negative_returns, ddof=0) * np.sqrt(252)
	    else:
		    # Se não há retornos negativos
		    downside_deviation = 0
	    
	    # Sortino Ratio
	    # Usa o excesso de retorno sobre a taxa livre dividido pelo downside deviation
	    sortino_ratio = excess_return / downside_deviation if downside_deviation > 0 else 0
	    
	    # Retorno anualizado (para comparação)
	    annual_return = (1 + gv_final) ** (252 / self.n_periods) - 1
	    
	    # VaR (Value at Risk) - Método Paramétrico
	    # VaR diário - AGORA USANDO RETORNOS PERCENTUAIS
	    mean_daily_return = np.mean(portfolio_returns_pct)
	    std_daily_return = np.std(portfolio_returns_pct, ddof=0)
	    
	    # VaR 95% (1.65 desvios padrão) e 99% (2.33 desvios padrão)
	    var_95_daily = mean_daily_return - 1.65 * std_daily_return
	    var_99_daily = mean_daily_return - 2.33 * std_daily_return
	    
	    # VaR anualizado (multiplicar pelo sqrt(252) para volatilidade anual)
	    var_95_annual = mean_daily_return * 252 - 1.65 * std_daily_return * np.sqrt(252)
	    var_99_annual = mean_daily_return * 252 - 2.33 * std_daily_return * np.sqrt(252)
	    
	    # CVaR (Conditional Value at Risk) - Método Histórico
	    # CVaR = média dos retornos abaixo do VaR - AGORA USANDO RETORNOS PERCENTUAIS
	    sorted_returns = np.sort(portfolio_returns_pct)
	    
	    # Para 95% de confiança, pegamos os 5% piores retornos
	    n_worst_5pct = max(1, int(0.05 * len(portfolio_returns_pct)))
	    worst_returns_5pct = sorted_returns[:n_worst_5pct]
	    cvar_95_daily = np.mean(worst_returns_5pct)
	    
	    # Para 99% de confiança, pegamos o 1% pior
	    n_worst_1pct = max(1, int(0.01 * len(portfolio_returns_pct)))
	    worst_returns_1pct = sorted_returns[:n_worst_1pct]
	    cvar_99_daily = np.mean(worst_returns_1pct)
	    
	    # CVaR anualizado (aproximação)
	    cvar_95_annual = cvar_95_daily * 252
	    cvar_99_annual = cvar_99_daily * 252
	    
	    # HC10: Métrica de qualidade da tendência
	    try:
		    from scipy import stats
		    # Criar array de "dias" (índices numéricos representando datas)
		    days_numeric = np.arange(len(portfolio_cumulative))
		    
		    # Regressão linear: GV vs Tempo
		    slope, intercept, r_value, p_value, std_err = stats.linregress(days_numeric, portfolio_cumulative)
		    r_squared = r_value ** 2
		    
		    # HC10 = Inclinação / [Volatilidade × (1 - R²)]
		    if portfolio_vol > 0 and r_squared < 1:
			    hc10 = slope / (portfolio_vol * (1 - r_squared))
		    else:
			    hc10 = 0
			    
	    except Exception as e:
		    print(f"Erro no cálculo HC10: {e}")
		    hc10 = 0
		    r_squared = 0
		    slope = 0
	    
	    # NOVO: Métricas do EXCESSO DE RETORNO (v2.1)
	    excess_slope = 0
	    excess_r_squared = 0
	    excess_hc10 = 0
	    excess_cumulative = None
	    
	    if hasattr(self, 'risk_free_cumulative') and self.risk_free_cumulative is not None:
		    try:
			    # Calcular excesso acumulado diário
			    excess_cumulative = portfolio_cumulative - self.risk_free_cumulative.values
			    
			    # Regressão linear do EXCESSO
			    excess_slope, excess_intercept, excess_r_value, _, _ = stats.linregress(days_numeric, excess_cumulative)
			    excess_r_squared = excess_r_value ** 2
			    
			    # ========== CORREÇÃO PARA EXCESSO ==========
			    # Calcular Variac_Result_PU do EXCESSO
			    excess_cumulative_with_zero = np.concatenate([[0], excess_cumulative])
			    variac_excess_pu = (1 + excess_cumulative_with_zero[1:]) / (1 + excess_cumulative_with_zero[:-1])
			    excess_returns_pct = variac_excess_pu - 1
			    
			    # Volatilidade do excesso usando retornos percentuais
			    excess_vol = np.std(excess_returns_pct, ddof=0) * np.sqrt(252)
			    # ========== FIM DA CORREÇÃO DO EXCESSO ==========
			    
			    # HC10 do excesso
			    if excess_vol > 0 and excess_r_squared < 1:
				    excess_hc10 = excess_slope / (excess_vol * (1 - excess_r_squared))
			    else:
				    excess_hc10 = 0
				    
		    except Exception as e:
			    print(f"Erro no cálculo de métricas do excesso: {e}")
	    
	    return {
		    'gv_final': gv_final,
		    'annual_return': annual_return,
		    'volatility': portfolio_vol,
		    'sharpe_ratio': sharpe_ratio,
		    'sortino_ratio': sortino_ratio,  # NOVO
		    'downside_deviation': downside_deviation,  # NOVO
		    'excess_return': excess_return,
		    'risk_free_rate': risk_free_rate,
		    'hc10': hc10,
		    'portfolio_returns_daily': portfolio_returns_daily,
		    'portfolio_cumulative': portfolio_cumulative,
		    'r_squared': r_squared,
		    'slope': slope,
		    'var_95_daily': var_95_daily,
		    'var_99_daily': var_99_daily,
		    'var_95_annual': var_95_annual,
		    'var_99_annual': var_99_annual,
		    'cvar_95_daily': cvar_95_daily,
		    'cvar_99_daily': cvar_99_daily,
		    'cvar_95_annual': cvar_95_annual,
		    'cvar_99_annual': cvar_99_annual,
		    # Novas métricas do excesso
		    'excess_slope': excess_slope,
		    'excess_r_squared': excess_r_squared,
		    'excess_hc10': excess_hc10,
		    'excess_cumulative': excess_cumulative
	    }
    
    def optimize_portfolio(self, objective_type='sharpe', target_return=None, max_weight=1.0, min_weight=0.0, 
                          risk_free_rate=0.0, individual_constraints=None):
        """
        Otimiza o portfólio (substitui o Solver do Excel)
        risk_free_rate: taxa livre de risco acumulada do período
        individual_constraints: dicionário com limites específicos por ativo
        """
        
        def objective_function(weights):
            metrics = self.calculate_portfolio_metrics(weights, risk_free_rate)
            
            if objective_type == 'sharpe':
                # Maximizar Sharpe (minimizar -Sharpe)
                return -metrics['sharpe_ratio']
            elif objective_type == 'sortino':
                # NOVO: Maximizar Sortino (minimizar -Sortino)
                return -metrics['sortino_ratio']
            elif objective_type == 'volatility':
                # Minimizar volatilidade
                return metrics['volatility']
            elif objective_type == 'slope':
                # Maximizar Inclinação (minimizar -Inclinação)
                return -metrics['slope']
            elif objective_type == 'hc10':
                # Maximizar Inclinação/(1-R²)×Vol 
                # Mas para estabilidade, minimizamos o inverso: (1-R²)×Vol/Inclinação
                if metrics['volatility'] > 0 and metrics['r_squared'] < 1:
                    if metrics['slope'] > 0.000001:  # Inclinação positiva pequena
                        # Retornar o inverso para minimizar
                        return (1 - metrics['r_squared']) * metrics['volatility'] / metrics['slope']
                    elif metrics['slope'] < -0.000001:  # Inclinação negativa
                        # Penalizar fortemente inclinações negativas
                        return 1e10 - metrics['slope']  # Quanto mais negativo, pior
                    else:  # Inclinação muito próxima de zero
                        return 1e10
                else:
                    # Valor alto para penalizar casos inválidos
                    return 1e10
                    
            elif objective_type == 'quality_linear':
                # NOVA: Minimizar [Vol × (1-R²)]/R² 
                # Só funciona se temos taxa livre de risco detectada
                if not hasattr(self, 'risk_free_cumulative') or self.risk_free_cumulative is None:
                    return 1e10  # Penalizar se não tem taxa livre
                
                # Maximizar "qualidade da linearidade" 
                if metrics['volatility'] > 0 and metrics['r_squared'] > 0.001:  # R² > 0.1%
                    # Fórmula: [Vol × (1-R²)]/R²
                    quality_metric = (metrics['volatility'] * (1 - metrics['r_squared'])) / metrics['r_squared']
                    return quality_metric  # Minimizar (quanto menor, melhor a qualidade)
                else:
                    # Penalizar R² muito baixo ou volatilidade zero
                    return 1e10

            # EXPLICAÇÃO DA FÓRMULA:
            # - R² alto (próximo de 1) → denominador grande → métrica pequena ✅
            # - Vol baixa → numerador pequeno → métrica pequena ✅  
            # - R² baixo (próximo de 0) → denominador pequeno → métrica grande (ruim) ✅
            # - Vol alta → numerador grande → métrica grande (ruim) ✅        
                                
            elif objective_type == 'excess_hc10':
                # NOVO: Maximizar linearidade do EXCESSO de retorno
                if not hasattr(self, 'risk_free_cumulative') or self.risk_free_cumulative is None:
                    # Se não tem taxa livre, retornar erro alto
                    return 1e10
                
                # Calcular métricas incluindo excesso
                if metrics.get('excess_slope') is not None:
                    # Calcular volatilidade do excesso aqui para usar no objetivo
                    excess_returns_daily = metrics['portfolio_returns_daily'] - self.risk_free_returns.values
                    excess_vol = np.std(excess_returns_daily, ddof=0) * np.sqrt(252)
                    
                    if metrics['excess_slope'] > 0.000001 and excess_vol > 0 and metrics['excess_r_squared'] < 1:
                        # Retornar o inverso para minimizar
                        return (1 - metrics['excess_r_squared']) * excess_vol / metrics['excess_slope']
                    else:
                        # Penalizar casos ruins (inclinação negativa, zero ou vol zero)
                        if metrics['excess_slope'] <= 0:
                            # Quanto mais negativa a inclinação, pior
                            return 1e10 + abs(metrics['excess_slope']) * 1e6
                        else:
                            return 1e10
                else:
                    return 1e10
            elif objective_type == 'return':
                # Maximizar retorno (minimizar -retorno)
                return -metrics['annual_return']
        
        # Restrições
        constraints = [
            # Soma dos pesos = 1 (100%)
            {'type': 'eq', 'fun': lambda x: np.sum(x) - 1}
        ]
        
        # Limites para cada peso
        if individual_constraints is not None:
            # Usar limites individuais
            bounds = []
            for asset in self.assets:
                if asset in individual_constraints:
                    bounds.append((
                        individual_constraints[asset]['min'],
                        individual_constraints[asset]['max']
                    ))
                else:
                    # Usar limites globais como fallback
                    bounds.append((min_weight, max_weight))
            bounds = tuple(bounds)
        else:
            # Usar limites globais para todos
            bounds = tuple((min_weight, max_weight) for _ in range(self.n_assets))
        
        # Chute inicial (pesos iguais)
        initial_weights = np.array([1/self.n_assets] * self.n_assets)
        
        # Otimização (aqui é onde a mágica acontece!)
        try:
            result = minimize(
                objective_function,
                initial_weights,
                method='SLSQP',
                bounds=bounds,
                constraints=constraints,
                options={'maxiter': 1000, 'ftol': 1e-9}
            )
            
            if result.success:
                optimal_weights = result.x
                metrics = self.calculate_portfolio_metrics(optimal_weights, risk_free_rate)
                
                return {
                    'success': True,
                    'weights': optimal_weights,
                    'metrics': metrics,
                    'assets': self.assets
                }
            else:
                return {
                    'success': False,
                    'message': f"Otimização falhou: {result.message}"
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f"Erro na otimização: {str(e)}"
            }
    
    def optimize_portfolio_with_shorts(self, selected_assets, short_assets, short_weights, 
                                     objective_type='sharpe', max_weight=1.0, min_weight=0.0, 
                                     risk_free_rate=0.0, individual_constraints=None):
        """
        Otimiza portfólio com posições short fixas
        selected_assets: lista de ativos para otimizar (long)
        short_assets: lista de ativos short
        short_weights: dicionário com pesos dos ativos short
        individual_constraints: dicionário com limites específicos por ativo
        """
        # Índices dos ativos
        selected_indices = [self.assets.index(asset) for asset in selected_assets]
        short_indices = [self.assets.index(asset) for asset in short_assets]
        
        # Número de ativos para otimizar (apenas os long)
        n_optimize = len(selected_indices)
        
        def objective_function(weights_to_optimize):
            # Criar array de pesos completo
            full_weights = np.zeros(self.n_assets)
            
            # Pesos dos ativos otimizados
            for i, idx in enumerate(selected_indices):
                full_weights[idx] = weights_to_optimize[i]
            
            # Pesos fixos dos shorts
            for asset, weight in short_weights.items():
                idx = self.assets.index(asset)
                full_weights[idx] = weight
            
            # Calcular métricas com todos os pesos
            metrics = self.calculate_portfolio_metrics(full_weights, risk_free_rate)
            
            if objective_type == 'sharpe':
                return -metrics['sharpe_ratio']
            elif objective_type == 'sortino':
                return -metrics['sortino_ratio']
            elif objective_type == 'volatility':
                return metrics['volatility']
            elif objective_type == 'slope':
                return -metrics['slope']
            elif objective_type == 'hc10':
                if metrics['volatility'] > 0 and metrics['r_squared'] < 1:
                    if metrics['slope'] > 0.000001:
                        return (1 - metrics['r_squared']) * metrics['volatility'] / metrics['slope']
                    elif metrics['slope'] < -0.000001:
                        return 1e10 - metrics['slope']
                    else:
                        return 1e10
                else:
                    return 1e10
            elif objective_type == 'quality_linear':
                if not hasattr(self, 'risk_free_cumulative') or self.risk_free_cumulative is None:
                    return 1e10
                if metrics['volatility'] > 0 and metrics['r_squared'] > 0.001:
                    quality_metric = (metrics['volatility'] * (1 - metrics['r_squared'])) / metrics['r_squared']
                    return quality_metric
                else:
                    return 1e10
            elif objective_type == 'excess_hc10':
                if not hasattr(self, 'risk_free_cumulative') or self.risk_free_cumulative is None:
                    return 1e10
                if metrics.get('excess_slope') is not None:
                    excess_returns_daily = metrics['portfolio_returns_daily'] - self.risk_free_returns.values
                    excess_vol = np.std(excess_returns_daily, ddof=0) * np.sqrt(252)
                    if metrics['excess_slope'] > 0.000001 and excess_vol > 0 and metrics['excess_r_squared'] < 1:
                        return (1 - metrics['excess_r_squared']) * excess_vol / metrics['excess_slope']
                    else:
                        if metrics['excess_slope'] <= 0:
                            return 1e10 + abs(metrics['excess_slope']) * 1e6
                        else:
                            return 1e10
                else:
                    return 1e10
            elif objective_type == 'return':
                return -metrics['annual_return']
        
        # Restrições - soma dos pesos LONG = 1
        constraints = [
            {'type': 'eq', 'fun': lambda x: np.sum(x) - 1}
        ]
        
        # Limites para pesos long
        if individual_constraints is not None:
            # Usar limites individuais para ativos long
            bounds = []
            for asset in selected_assets:
                if asset in individual_constraints:
                    bounds.append((
                        individual_constraints[asset]['min'],
                        individual_constraints[asset]['max']
                    ))
                else:
                    # Usar limites globais como fallback
                    bounds.append((min_weight, max_weight))
            bounds = tuple(bounds)
        else:
            # Usar limites globais para todos
            bounds = tuple((min_weight, max_weight) for _ in range(n_optimize))
        
        # Chute inicial
        initial_weights = np.array([1/n_optimize] * n_optimize)
        
        # Otimização
        try:
            result = minimize(
                objective_function,
                initial_weights,
                method='SLSQP',
                bounds=bounds,
                constraints=constraints,
                options={'maxiter': 1000, 'ftol': 1e-9}
            )
            
            if result.success:
                # Reconstruir pesos completos
                full_weights = np.zeros(self.n_assets)
                
                # Pesos otimizados
                for i, idx in enumerate(selected_indices):
                    full_weights[idx] = result.x[i]
                
                # Pesos shorts
                for asset, weight in short_weights.items():
                    idx = self.assets.index(asset)
                    full_weights[idx] = weight
                
                metrics = self.calculate_portfolio_metrics(full_weights, risk_free_rate)
                
                return {
                    'success': True,
                    'weights': full_weights,
                    'metrics': metrics,
                    'assets': self.assets
                }
            else:
                return {
                    'success': False,
                    'message': f"Otimização falhou: {result.message}"
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f"Erro na otimização: {str(e)}"
            }
    
    def get_portfolio_summary(self, weights):
        """
        Cria resumo do portfólio otimizado com pesos iniciais e atuais
        Posições LONG e SHORT usam a mesma fórmula, mas patrimônio total considera apenas LONGs
        """
        # Calcular valores finais de cada ativo (LONG e SHORT usam mesma fórmula)
        asset_final_values = []
        
        for i, asset in enumerate(self.assets):
            if abs(weights[i]) > 0.001:  # Ativos significativos (positivos OU negativos)
                # Retorno acumulado do ativo individual
                asset_returns = self.returns_data[asset].values
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
        for i, asset in enumerate(self.assets):
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
            'Ativo': np.array(self.assets)[significant_weights],
            'Peso Inicial (%)': weights[significant_weights] * 100,
            'Peso Atual (%)': np.array(asset_current_weights)[significant_weights] * 100,
            'Tipo': ['SHORT' if w < 0 else 'LONG' for w in weights[significant_weights]]
        }).sort_values('Peso Inicial (%)', key=abs, ascending=False)
        
        return portfolio_df
