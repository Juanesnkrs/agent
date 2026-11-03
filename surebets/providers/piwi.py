import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def procesar_mensaje_ws(mensaje_texto):
    """
    Convierte el payload del WebSocket a JSON y extrae eventos.
    """
    try:
        if isinstance(mensaje_texto, str):
            mensaje = json.loads(mensaje_texto)
        else:
            mensaje = mensaje_texto
    except json.JSONDecodeError:
        return []

    eventos = []
    if 'n' in mensaje and isinstance(mensaje['n'], list):
        for deporte in mensaje['n']:
            if isinstance(deporte, list) and len(deporte) > 2 and deporte[1] == 'Basketball':
                ligas = deporte[2]
                for liga in ligas:
                    if isinstance(liga, list) and len(liga) > 2 and liga[1] == 'NBA':
                        partidos = liga[2]
                        for partido in partidos:
                            if isinstance(partido, list) and len(partido) >= 9:
                                id_evento = partido[0]
                                equipo_local = partido[1]
                                equipo_visitante = partido[2]
                                timestamp_ms = partido[4]
                                cuotas_brutas = partido[8]
                                
                                cuota_local = 0.0
                                cuota_visitante = 0.0
                                
                                if isinstance(cuotas_brutas, dict) and '0' in cuotas_brutas:
                                    mercados = cuotas_brutas['0']
                                    try:
                                        cuota_local = float(mercados[1][0][0])
                                        cuota_visitante = float(mercados[1][0][1])
                                    except (IndexError, TypeError, ValueError) as e:
                                        logger.debug(f"Error extrayendo cuotas: {e}")

                                eventos.append({
                                    'proveedor': 'Piwi247',
                                    'id_evento': str(id_evento),
                                    'deporte': 'Basketball',
                                    'liga': 'NBA',
                                    'home': equipo_local,
                                    'away': equipo_visitante,
                                    'timestamp': timestamp_ms,
                                    'odds': {
                                        'home': cuota_local,
                                        'away': cuota_visitante
                                    }
                                })
    return eventos

def normalizar_datos_piwi(eventos_extraidos):
    """Filtra eventos sin equipos o con cuotas en 0."""
    eventos_validos = []
    for evento in eventos_extraidos:
        if evento.get('home') and evento.get('away'):
            if evento['odds']['home'] > 0 and evento['odds']['away'] > 0:
                eventos_validos.append(evento)
    return eventos_validos