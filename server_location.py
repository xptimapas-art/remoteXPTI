"""Offline city/UF lookup; user coordinates always take precedence."""
from functools import lru_cache
import json
import math
from pathlib import Path
import re
import unicodedata

STATES = frozenset('AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split())


def normalized_city(value):
    text = unicodedata.normalize('NFKD', value).casefold()
    text = ''.join(char for char in text if not unicodedata.combining(char))
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


@lru_cache(maxsize=1)
def municipality_catalog():
    path = Path(__file__).resolve().parent / 'resources' / 'br_municipalities.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    result = {}
    for name, state, lat, lon in data['cities']:
        key = (normalized_city(name), state)
        if key in result:
            raise ValueError('Base de municípios contém nomes ambíguos.')
        result[key] = (name, lat, lon)
    return result


def resolve_location(data):
    city = str(data.get('city') or '').strip()
    state = str(data.get('state') or '').strip().upper()
    if len(city) > 100 or (state and state not in STATES):
        raise ValueError('Cidade ou estado inválidos.')
    lat, lon = data.get('latitude'), data.get('longitude')
    if (lat is None) != (lon is None):
        raise ValueError('Informe latitude e longitude juntas, ou deixe ambas vazias.')
    if lat is not None:
        if isinstance(lat, bool) or isinstance(lon, bool):
            raise ValueError('Coordenadas inválidas.')
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            raise ValueError('Coordenadas inválidas.') from None
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError('Latitude ou longitude fora do intervalo válido.')
        return dict(city=city, state=state, latitude=lat, longitude=lon,
                    location_source='manual', location_approximate=False)
    if bool(city) != bool(state):
        raise ValueError('Informe cidade e estado juntos para localizar aproximadamente.')
    if not city:
        return dict(city='', state='', latitude=None, longitude=None,
                    location_source='none', location_approximate=False)
    try:
        found = municipality_catalog().get((normalized_city(city), state))
    except (OSError, KeyError, TypeError, ValueError):
        raise ValueError('A base local de municípios está indisponível. Informe as coordenadas ou tente novamente.') from None
    if found is None:
        raise ValueError('Cidade não encontrada nesse estado. Confira a grafia ou informe as coordenadas.')
    name, lat, lon = found
    return dict(city=name, state=state, latitude=lat, longitude=lon,
                location_source='city', location_approximate=True)


def location_update(existing, changes):
    if not {'city', 'state', 'latitude', 'longitude'} & changes.keys():
        return {}
    combined = {**existing, **changes}
    same_coordinates = all(changes.get(key, existing.get(key)) == existing.get(key)
                           for key in ('latitude', 'longitude'))
    if existing.get('location_source') == 'city' and (
            not {'latitude', 'longitude'} & changes.keys() or same_coordinates):
        combined.update(latitude=None, longitude=None)
    return resolve_location(combined)
