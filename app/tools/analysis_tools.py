import json
from typing import List
from langchain_core.tools import tool


@tool
def calculate_build_budget(component_prices: List[float], budget_limit: float) -> str:
    """Calcula el costo total del armado y lo compara con el presupuesto disponible."""
    total_cost = sum(component_prices)
    diferencia = budget_limit - total_cost
    porcentaje_usado = (total_cost / budget_limit) * 100.0 if budget_limit > 0 else 0.0

    res = {
        "costo_total": round(total_cost, 2),
        "presupuesto_limite": round(budget_limit, 2),
        "diferencia": round(diferencia, 2),
        "porcentaje_utilizado": round(porcentaje_usado, 2),
        "estado": "Dentro del presupuesto" if diferencia >= 0 else "Supera el presupuesto",
        "margen_restante": round(diferencia, 2) if diferencia >= 0 else 0.0,
        "es_critico": total_cost >= 1000000.0
    }
    return json.dumps(res, indent=2, ensure_ascii=False)


@tool
def calculate_power_requirement(total_component_watts: float) -> str:
    """Calcula el consumo total en Watts y determina la potencia recomendada para la fuente."""
    consumo_base = total_component_watts + 40.0
    potencia_recomendada = consumo_base * 1.30

    escalones = [500, 550, 600, 650, 750, 850, 1000]
    fuente_sugerida = escalones[-1]
    for e in escalones:
        if e >= potencia_recomendada:
            fuente_sugerida = e
            break

    res = {
        "consumo_estimado_watts": round(consumo_base, 1),
        "margen_seguridad_watts": round(potencia_recomendada, 1),
        "fuente_minima_recomendada": f"{fuente_sugerida}W 80 Plus",
        "observacion": f"Una fuente de {fuente_sugerida}W cubre el pico de consumo dejando buen margen térmico.",
        "alta_potencia": fuente_sugerida >= 850
    }
    return json.dumps(res, indent=2, ensure_ascii=False)


analysis_tools = [
    calculate_build_budget,
    calculate_power_requirement
]
