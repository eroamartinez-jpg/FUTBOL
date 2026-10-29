"""Bot de apuestas de valor ("value betting") construido sobre el modelo.

Funciona como un bot de trading algorítmico, con las mismas cuatro piezas:

1. **Señal** (`strategy.py`): el modelo estima la probabilidad real de cada
   resultado; la cuota de la casa implica otra. Si la del modelo es mayor,
   la apuesta tiene valor esperado positivo (`edge`).
2. **Tamaño de posición** (`strategy.py`): criterio de Kelly fraccional,
   igual que el sizing de una posición según la ventaja estimada.
3. **Gestión de riesgo** (`strategy.py`): tope de stake por apuesta, tope de
   exposición por jornada, rango de cuotas permitido.
4. **Ejecución y P&L** (`ledger.py`): registro de cada apuesta en modo
   *paper trading* (sin dinero real), liquidación con el resultado real y
   métricas (ROI, yield, drawdown, CLV).

`backtest.py` reproduce todo el ciclo partido a partido sobre un histórico
con cuotas reales, reentrenando el modelo solo con el pasado.
"""
