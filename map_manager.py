"""
Módulo de Gerenciamento de Mapas e Geolocalização de Servidores do RemoteXPTI.
Permite visualização geográfica dos acessos e conexão RDP com 1 clique no mapa.
"""

import re
import sys
from pathlib import Path
from typing import Dict, Tuple, Optional, Any


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.resolve()


def get_map_cache_path() -> Path:
    cache_dir = get_app_dir() / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "map_tiles.db"


# Coordenadas de referência para Santa Catarina e principais cidades/unidades
SC_COORDINATES: Dict[str, Tuple[float, float]] = {
    # Unidades especiais / Penitenciárias / Complexos
    "cope": (-27.5954, -48.5480),             # Florianópolis
    "feminino chapeco": (-27.1004, -52.6152), # Chapecó Penitenciária
    "umax": (-26.3150, -48.8600),             # Joinville
    "industrial scs": (-27.2644, -50.4431),   # São Cristóvão do Sul
    "joinville (alt)": (-26.2800, -48.8400),

    # Municípios de Santa Catarina
    "agua doce": (-26.9986, -51.5544),
    "araquari": (-26.3711, -48.7208),
    "balneario camboriu": (-26.9926, -48.6354),
    "balneario picarras": (-26.7644, -48.6717),
    "barra velha": (-26.6322, -48.6839),
    "bombinhas": (-27.1394, -48.5144),
    "cacador": (-26.7753, -51.0125),
    "camboriu": (-27.0244, -48.6556),
    "campo alegre": (-26.1931, -49.2678),
    "campos novos": (-27.4019, -51.2258),
    "canelinha": (-27.2619, -48.7661),
    "canoinhas": (-26.1772, -50.3958),
    "catanduvas": (-27.0722, -51.6561),
    "chapeco": (-27.1004, -52.6152),
    "correia pinto": (-27.5847, -50.3611),
    "corupa": (-26.4258, -49.2433),
    "curitibanos": (-27.2831, -50.5844),
    "erval velho": (-27.2750, -51.4403),
    "fraiburgo": (-27.0258, -50.9208),
    "garuva": (-26.0308, -48.8558),
    "guaramirim": (-26.4736, -49.0028),
    "herval d'oeste": (-27.1858, -51.4981),
    "herval d oeste": (-27.1858, -51.4981),
    "herval doeste": (-27.1858, -51.4981),
    "iomere": (-27.0019, -51.2439),
    "irineopolis": (-26.2486, -50.7981),
    "itaiopolis": (-26.3353, -49.9078),
    "itajai": (-26.9078, -48.6619),
    "itapema": (-27.0906, -48.6111),
    "itapoa": (-26.1169, -48.6167),
    "joacaba": (-27.1758, -51.5033),
    "joinville": (-26.3045, -48.8487),
    "lages": (-27.8158, -50.3261),
    "luiz alves": (-26.7214, -48.9328),
    "luis alves": (-26.7214, -48.9328),
    "luzerna": (-27.1319, -51.4644),
    "mafra": (-26.1114, -49.8058),
    "massaranduba": (-26.6119, -48.9958),
    "navegantes": (-26.8967, -48.6539),
    "nova trento": (-27.2858, -48.9297),
    "otacilio costa": (-27.4828, -50.1219),
    "papanduva": (-26.3719, -50.1417),
    "penha": (-26.7708, -48.6458),
    "porto belo": (-27.1578, -48.5528),
    "porto uniao": (-26.2383, -51.0778),
    "rio negrinho": (-26.2544, -49.5186),
    "santo amaro": (-27.6869, -48.7789),
    "sao bento do sul": (-26.2503, -49.3789),
    "sao francisco do sul": (-26.2431, -48.6381),
    "sao joao batista": (-27.2764, -48.8492),
    "sao joaquim": (-28.2936, -49.9317),
    "schroeder": (-26.4122, -49.0733),
    "tijucas": (-27.2417, -48.6339),
    "treze tilias": (-26.9989, -51.4178),
    "videira": (-27.0083, -51.1517),

    # Demais polos catarinenses e nacionais
    "florianopolis": (-27.5954, -48.5480),
    "blumenau": (-26.9194, -49.0661),
    "criciuma": (-28.6778, -49.3703),
    "jaragua do sul": (-26.4850, -49.0833),
    "palhoca": (-27.6453, -48.6678),
    "sao jose": (-27.6136, -48.6367),
    "brusque": (-27.0983, -48.9169),
    "tubarao": (-28.4739, -49.0144),
    "concordia": (-27.2339, -52.0239),
    "rio do sul": (-27.2142, -49.6428),
    "ararangua": (-28.9356, -49.4939),
    "porto alegre": (-30.0346, -51.2177),
    "curitiba": (-25.4284, -49.2733),
    "sao paulo": (-23.5505, -46.6333),
    "brasilia": (-15.7975, -47.8919),
}

# Centro padrão do mapa: Santa Catarina
DEFAULT_MAP_CENTER = (-27.2, -50.2)
DEFAULT_MAP_ZOOM = 8

# Camadas de mapa
TILE_SERVERS = {
    "CartoDB Dark (Padrão)": "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
    "OpenStreetMap": "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
    "Google Maps": "https://mt0.google.com/vt/lyrs=m&hl=pt-BR&x={x}&y={y}&z={z}&s=Ga",
    "Google Satélite": "https://mt0.google.com/vt/lyrs=s&hl=pt-BR&x={x}&y={y}&z={z}&s=Ga",
}


def normalize_text(text: str) -> str:
    """Remove acentuação e padroniza para comparação."""
    import unicodedata
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    clean = "".join([c for c in nfkd if not unicodedata.combining(c)])
    clean = re.sub(r"[^a-zA-Z0-9\s]", " ", clean).lower()
    return re.sub(r"\s+", " ", clean).strip()


def resolve_server_coordinates(server: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    """
    Descobre a latitude e longitude do servidor:
    1. Se já existirem 'latitude' e 'longitude' numéricas válidas no servidor, usa-as.
    2. Caso contrário, tenta inferir pelo nome do servidor ou grupo baseado na lista de SC.
    """
    lat = server.get("latitude")
    lon = server.get("longitude")

    try:
        if lat is not None and lon is not None:
            f_lat = float(lat)
            f_lon = float(lon)
            if -90 <= f_lat <= 90 and -180 <= f_lon <= 180:
                return (f_lat, f_lon)
    except (ValueError, TypeError):
        pass

    # Tenta inferir pelo nome
    name_norm = normalize_text(server.get("name", ""))
    group_norm = normalize_text(server.get("group", ""))

    # Correspondência exata
    if name_norm in SC_COORDINATES:
        return SC_COORDINATES[name_norm]

    # Correspondência parcial no nome
    for city, coords in SC_COORDINATES.items():
        if city in name_norm or name_norm in city:
            return coords

    # Correspondência no grupo
    if group_norm in SC_COORDINATES:
        return SC_COORDINATES[group_norm]

    for city, coords in SC_COORDINATES.items():
        if city in group_norm:
            return coords

    return None
