import json
from surebets.providers.piwi import procesar_mensaje_ws, normalizar_datos_piwi

# Simulamos el JSON exacto que capturaste
payload_simulado = json.dumps({
    "u": None,
    "l": [
        [4, "Basketball", [], 1793648172700, 1, None, [0, 0, 0], 0]
    ],
    "n": [
        [4, "Basketball", [
            [487, "NBA", [
                [1639313878, "Cleveland Cavaliers", "Oklahoma City Thunder", 11, 1793664600000, 0, 1, 74, 
                 {"0": [
                     [[4.5, -4.5, "4.5", "1.9", "1.9", 0, 1, 4.5, -4.5, 0]], 
                     [[1.4, 2.85, "", "1.4", "2.85", 0, 1, 0, 0, 0]]
                 ]}
                ]
            ]]
        ]]
    ]
})

print("\n--- INICIANDO PRUEBA FINAL DE CUOTAS PIWI247 ---")

eventos_extraidos = procesar_mensaje_ws(payload_simulado)
eventos_normalizados = normalizar_datos_piwi(eventos_extraidos)

print(f"\nEventos válidos extraídos: {len(eventos_normalizados)}")

if eventos_normalizados:
    evento = eventos_normalizados[0]
    print(f"\nPartido: {evento['home']} vs {evento['away']}")
    print(f"Cuota Local ({evento['home']}): {evento['odds']['home']}")
    print(f"Cuota Visitante ({evento['away']}): {evento['odds']['away']}")
else:
    print("No se extrajeron eventos. Revisa los índices.")

print("\n------------------------------------------\n")