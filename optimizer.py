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
    
    def _core_metrics(self, weights, risk_free_rate=0.0):
	    """
	    Versão ENXUTA das métricas, usada APENAS dentro do loop de otimização
	    para os objetivos simples (Sharpe / Sortino / Volatilidade / Retorno).

	    Calcula só retorno, volatilidade e downside — evitando VaR, CVaR, duas
	    regressões lineares e as métricas de excesso a cada uma das centenas de
	    avaliações por iteração do SLSQP (com 133 ativos isso pesa muito).

	    As métricas COMPLETAS (VaR, HC10, etc.) continuam sendo recalculadas uma
	    única vez ao final, sobre os pesos ótimos, via calculate_portfolio_metrics
	    — então a tabela de resultados não é afetada. Os valores aqui são
	    idênticos aos de calculate_portfolio_metrics para estas mesmas métricas.
	    """
	    weights = np.array(weights)
	    portfolio_returns_daily = np.dot(self.returns_data.values, weights)
	    portfolio_cumulative = np.cumsum(portfolio_returns_daily)
	    cum_with_zero = np.concatenate([[0], portfolio_cumulative])
	    returns_pct = (1 + cum_with_zero[1:]) / (1 + cum_with_zero[:-1]) - 1

	    vol = np.std(returns_pct, ddof=0) * np.sqrt(252)
	    gv_final = portfolio_cumulative[-1]
	    excess_return = gv_final - risk_free_rate

	    downside_returns = np.minimum(returns_pct, 0.0)
	    downside_dev = np.sqrt(np.mean(downside_returns ** 2)) * np.sqrt(252)

	    # Total Under Water: soma de todos os retornos diários negativos (<= 0).
	    # abs_under_water é o total de perdas do período (>= 0). É uma SOMA (L1),
	    # bem mais estável que o downside deviation (RMS) — não encolhe perto de
	    # zero com dados reais, então a razão Sharpe/Under Water fica bem
	    # condicionada para o otimizador (ao contrário do Sortino).
	    total_under_water = np.sum(downside_returns)
	    abs_under_water = abs(total_under_water)

	    annual_return = (1 + gv_final) ** (252 / self.n_periods) - 1

	    sharpe_ratio = excess_return / vol if vol > 0 else 0
	    return {
		    'volatility': vol,
		    'gv_final': gv_final,
		    'excess_return': excess_return,
		    'annual_return': annual_return,
		    'sharpe_ratio': sharpe_ratio,
		    'sortino_ratio': excess_return / downside_dev if downside_dev > 0 else 0,
		    'total_under_water': total_under_water,
		    'abs_under_water': abs_under_water,
		    'sharpe_uw': sharpe_ratio / abs_under_water if abs_under_water > 1e-9 else sharpe_ratio / 1e-9,
	    }

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
	    # Downside Deviation = semi-desvio-padrão clássico de Sortino & Price:
	    #   sqrt( média( min(retorno, 0)² ) ), sobre TODOS os períodos, anualizado.
	    # Esta forma é SUAVE (diferenciável): min(r,0)² não tem "quinas" no
	    # threshold zero, ao contrário do desvio-padrão sobre o subconjunto de
	    # negativos (cuja contagem mudava descontinuamente a cada passo do
	    # solver, deixando o SLSQP lento/travado na otimização por Sortino).
	    downside_returns = np.minimum(portfolio_returns_pct, 0.0)
	    downside_deviation = np.sqrt(np.mean(downside_returns ** 2)) * np.sqrt(252)

	    # Sortino Ratio
	    # Usa o excesso de retorno sobre a taxa livre dividido pelo downside deviation
	    sortino_ratio = excess_return / downside_deviation if downside_deviation > 0 else 0

	    # NOVO: Total Under Water e o índice proprietário Sharpe/Under Water.
	    # Total Under Water = soma de todos os retornos diários negativos (<= 0);
	    # abs_under_water = total de perdas do período (>= 0). Sendo uma SOMA (L1),
	    # é bem mais estável que o downside deviation (RMS): não encolhe perto de
	    # zero, então a razão Sharpe/Under Water fica bem condicionada no otimizador.
	    total_under_water = np.sum(downside_returns)
	    abs_under_water = abs(total_under_water)
	    sharpe_uw = sharpe_ratio / abs_under_water if abs_under_water > 1e-9 else sharpe_ratio / 1e-9
	    
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
		    'total_under_water': total_under_water,  # NOVO: soma dos retornos negativos
		    'abs_under_water': abs_under_water,  # NOVO: total de perdas (>= 0)
		    'sharpe_uw': sharpe_uw,  # NOVO: índice Sharpe / Under Water
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
    
    def _solve_multistart(self, objective_function, bounds, constraints, initial_weights, n_starts=15):
        """
        Resolve o NLP com SLSQP a partir de pesos iguais e, SE detectar
        travamento (parou no ponto inicial ou preso na região de penalidade),
        tenta vários chutes iniciais aleatórios e fica com o melhor.

        Objetivos como hc10/excess_hc10 usam sentinelas de penalidade (1e10);
        quando os pesos iguais caem nessa região, o SLSQP "converge" de imediato
        (tolerância relativa sobre um valor enorme) e devolve o próprio ponto
        inicial. O multi-start escapa desse platô sem custo no caso comum
        (só dispara quando há travamento).
        """
        def _run(x0):
            return minimize(
                objective_function, x0, method='SLSQP',
                bounds=bounds, constraints=constraints,
                options={'maxiter': 1000, 'ftol': 1e-9}
            )

        result = _run(initial_weights)

        def _stuck(res):
            if not res.success:
                return True
            try:
                if np.allclose(res.x, initial_weights, atol=1e-6):
                    return True   # não saiu do ponto inicial
                if objective_function(res.x) >= 1e9:
                    return True   # preso na região de penalidade
            except Exception:
                return True
            return False

        if _stuck(result):
            # Guardar o melhor válido até agora (se houver)
            if result.success and objective_function(result.x) < 1e9:
                best, best_val = result, objective_function(result.x)
            else:
                best, best_val = None, np.inf

            lows = np.array([b[0] for b in bounds])
            highs = np.array([b[1] for b in bounds])
            rng = np.random.default_rng(0)  # determinístico: resultado reprodutível

            # Parada antecipada: assim que escapamos da penalidade e o resultado
            # estagna, não vale a pena continuar testando todos os reinícios.
            min_starts = 3     # tenta ao menos alguns para poder comparar
            patience = 2       # para após N reinícios seguidos sem melhora
            no_improve = 0
            for i in range(n_starts):
                x0 = lows + rng.random(len(bounds)) * (highs - lows)
                try:
                    res = _run(x0)
                except Exception:
                    no_improve += 1
                    res = None
                if res is not None and res.success:
                    val = objective_function(res.x)
                    if val < best_val:
                        best, best_val = res, val
                        no_improve = 0
                    else:
                        no_improve += 1
                else:
                    no_improve += 1

                escaped = best is not None and best_val < 1e9
                if escaped and (i + 1) >= min_starts and no_improve >= patience:
                    break

            if best is not None:
                result = best

        return result

    def optimize_portfolio(self, objective_type='sharpe', target_return=None, max_weight=1.0, min_weight=0.0,
                          risk_free_rate=0.0, individual_constraints=None):
        """
        Otimiza o portfólio (substitui o Solver do Excel)
        risk_free_rate: taxa livre de risco acumulada do período
        individual_constraints: dicionário com limites específicos por ativo
        """
        
        def objective_function(weights):
            # Caminho ENXUTO para objetivos simples: calcula só o necessário,
            # sem VaR/CVaR/regressões. Acelera muito com muitos ativos.
            if objective_type in ('sharpe', 'sortino', 'sharpe_uw', 'volatility', 'return'):
                core = self._core_metrics(weights, risk_free_rate)
                if objective_type == 'sharpe':
                    return -core['sharpe_ratio']
                elif objective_type == 'sortino':
                    return -core['sortino_ratio']
                elif objective_type == 'sharpe_uw':
                    # NOVO: Maximizar Sharpe / Under Water
                    return -core['sharpe_uw']
                elif objective_type == 'volatility':
                    return core['volatility']
                else:  # 'return'
                    return -core['annual_return']

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
        
        # Restrições base: soma dos pesos = 1 (100%)
        constraints = [
            {'type': 'eq', 'fun': lambda x: np.sum(x) - 1}
        ]

        # META DE RETORNO (opcional): exige retorno do período >= referência × (1 + meta)
        # Ex.: referência 12% e meta 5% -> alvo = 0.12 × 1.05 = 0.126 (12,6%)
        meta_used = target_return is not None
        meta_required = risk_free_rate * (1 + target_return) if meta_used else None
        if meta_used:
            constraints.append({
                'type': 'ineq',
                'fun': lambda w: self._core_metrics(w, risk_free_rate)['gv_final'] - meta_required
            })
        
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
            result = self._solve_multistart(objective_function, bounds, constraints, initial_weights)

            # Verificar a meta; se inatingível, cair para "melhor retorno possível"
            meta_atingida = True
            if meta_used:
                if result.success:
                    m = self.calculate_portfolio_metrics(result.x, risk_free_rate)
                    meta_atingida = m['gv_final'] >= meta_required - 1e-6
                else:
                    meta_atingida = False
                if not meta_atingida:
                    base_constraints = [{'type': 'eq', 'fun': lambda x: np.sum(x) - 1}]

                    def _return_obj(w):
                        return -self._core_metrics(w, risk_free_rate)['annual_return']

                    result = self._solve_multistart(_return_obj, bounds, base_constraints, initial_weights)

            if result.success:
                optimal_weights = result.x
                metrics = self.calculate_portfolio_metrics(optimal_weights, risk_free_rate)

                out = {
                    'success': True,
                    'weights': optimal_weights,
                    'metrics': metrics,
                    'assets': self.assets
                }
                if meta_used:
                    out['meta_used'] = True
                    out['meta_target'] = target_return
                    out['meta_required'] = meta_required
                    out['meta_achieved'] = metrics['gv_final']
                    out['meta_ref'] = risk_free_rate
                    out['meta_atingida'] = metrics['gv_final'] >= meta_required - 1e-6
                return out
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
                                     objective_type='sharpe', target_return=None, max_weight=1.0, min_weight=0.0,
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

        def _full_weights(weights_to_optimize):
            """Monta o vetor completo de pesos (long otimizados + shorts fixos)."""
            fw = np.zeros(self.n_assets)
            for i, idx in enumerate(selected_indices):
                fw[idx] = weights_to_optimize[i]
            for asset, weight in short_weights.items():
                fw[self.assets.index(asset)] = weight
            return fw

        def objective_function(weights_to_optimize):
            full_weights = _full_weights(weights_to_optimize)

            # Caminho ENXUTO para objetivos simples (ver optimize_portfolio)
            if objective_type in ('sharpe', 'sortino', 'sharpe_uw', 'volatility', 'return'):
                core = self._core_metrics(full_weights, risk_free_rate)
                if objective_type == 'sharpe':
                    return -core['sharpe_ratio']
                elif objective_type == 'sortino':
                    return -core['sortino_ratio']
                elif objective_type == 'sharpe_uw':
                    return -core['sharpe_uw']
                elif objective_type == 'volatility':
                    return core['volatility']
                else:  # 'return'
                    return -core['annual_return']

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

        # META DE RETORNO (opcional): retorno do período >= referência × (1 + meta)
        meta_used = target_return is not None
        meta_required = risk_free_rate * (1 + target_return) if meta_used else None
        if meta_used:
            constraints.append({
                'type': 'ineq',
                'fun': lambda w: self._core_metrics(_full_weights(w), risk_free_rate)['gv_final'] - meta_required
            })

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
            result = self._solve_multistart(objective_function, bounds, constraints, initial_weights)

            # Verificar a meta; se inatingível, cair para "melhor retorno possível"
            meta_atingida = True
            if meta_used:
                if result.success:
                    m = self.calculate_portfolio_metrics(_full_weights(result.x), risk_free_rate)
                    meta_atingida = m['gv_final'] >= meta_required - 1e-6
                else:
                    meta_atingida = False
                if not meta_atingida:
                    base_constraints = [{'type': 'eq', 'fun': lambda x: np.sum(x) - 1}]

                    def _return_obj(w):
                        return -self._core_metrics(_full_weights(w), risk_free_rate)['annual_return']

                    result = self._solve_multistart(_return_obj, bounds, base_constraints, initial_weights)

            if result.success:
                full_weights = _full_weights(result.x)
                metrics = self.calculate_portfolio_metrics(full_weights, risk_free_rate)

                out = {
                    'success': True,
                    'weights': full_weights,
                    'metrics': metrics,
                    'assets': self.assets
                }
                if meta_used:
                    out['meta_used'] = True
                    out['meta_target'] = target_return
                    out['meta_required'] = meta_required
                    out['meta_achieved'] = metrics['gv_final']
                    out['meta_ref'] = risk_free_rate
                    out['meta_atingida'] = metrics['gv_final'] >= meta_required - 1e-6
                return out
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
