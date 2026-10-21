import os
import json
from typing import List, Dict, Any
from langchain_core.tools import tool

HARDWARE_CATALOG: List[Dict[str, Any]] = [
    {
        "categoria": "procesador",
        "modelo": "AMD Ryzen 5 7600",
        "precio": 240000,
        "consumo_watts": 65,
        "socket": "AM5",
        "tipo_memoria": "DDR5",
        "gama": "media-alta"
    },
    {
        "categoria": "procesador",
        "modelo": "Intel Core i5 13400F",
        "precio": 210000,
        "consumo_watts": 65,
        "socket": "LGA1700",
        "tipo_memoria": "DDR4/DDR5",
        "gama": "media"
    },
    {
        "categoria": "procesador",
        "modelo": "AMD Ryzen 9 7950X",
        "precio": 650000,
        "consumo_watts": 170,
        "socket": "AM5",
        "tipo_memoria": "DDR5",
        "gama": "alta-entusiasta"
    },
    {
        "categoria": "placa_video",
        "modelo": "NVIDIA GeForce RTX 4060 8GB",
        "precio": 360000,
        "consumo_watts": 115,
        "gama": "media",
        "rendimiento": "1080p Ultra / 1440p Medio"
    },
    {
        "categoria": "placa_video",
        "modelo": "AMD Radeon RX 7600 8GB",
        "precio": 320000,
        "consumo_watts": 165,
        "gama": "media",
        "rendimiento": "1080p Ultra"
    },
    {
        "categoria": "placa_video",
        "modelo": "NVIDIA GeForce RTX 4080 Super 16GB",
        "precio": 1250000,
        "consumo_watts": 320,
        "gama": "alta-entusiasta",
        "rendimiento": "4K Ultra Ray Tracing"
    },
    {
        "categoria": "memoria_ram",
        "modelo": "Corsair Vengeance 16GB (2x8GB) DDR5 5600MHz",
        "precio": 85000,
        "consumo_watts": 10,
        "tipo": "DDR5"
    },
    {
        "categoria": "memoria_ram",
        "modelo": "Corsair Vengeance 32GB (2x16GB) DDR5 6000MHz",
        "precio": 160000,
        "consumo_watts": 15,
        "tipo": "DDR5"
    },
    {
        "categoria": "almacenamiento",
        "modelo": "SSD Kingston NV2 1TB NVMe M.2",
        "precio": 70000,
        "consumo_watts": 5,
        "velocidad": "3500 MB/s"
    },
    {
        "categoria": "motherboard",
        "modelo": "ASUS Prime B650M-A II",
        "precio": 145000,
        "consumo_watts": 25,
        "socket": "AM5"
    },
    {
        "categoria": "fuente",
        "modelo": "Corsair CV650 650W 80 Plus Bronze",
        "precio": 80000,
        "potencia_watts": 650
    },
    {
        "categoria": "fuente",
        "modelo": "Corsair RM850e 850W 80 Plus Gold Modular",
        "precio": 190000,
        "potencia_watts": 850
    }
]


@tool
def search_hardware_components(query: str) -> str:
    """Busca componentes de PC con sus precios y consumo en Watts."""
    tavily_key = os.getenv("TAVILY_API_KEY")
    if tavily_key:
        try:
            from langchain_community.tools.tavily_search import TavilySearchResults
            tavily = TavilySearchResults(max_results=3)
            res = tavily.invoke({"query": f"precio y especificaciones hardware PC {query}"})
            return json.dumps(res, ensure_ascii=False)
        except Exception:
            pass

    terms = query.lower().split()
    resultados = []
    for item in HARDWARE_CATALOG:
        texto = f"{item['categoria']} {item['modelo']} {item.get('gama', '')}".lower()
        if any(term in texto for term in terms if len(term) > 2):
            resultados.append(item)

    if resultados:
        return json.dumps(resultados, indent=2, ensure_ascii=False)

    combo_base = [HARDWARE_CATALOG[0], HARDWARE_CATALOG[3], HARDWARE_CATALOG[6], HARDWARE_CATALOG[10]]
    return json.dumps(combo_base, indent=2, ensure_ascii=False)


search_tools = [search_hardware_components]
