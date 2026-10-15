"""Run the existing AJIN dashboard alongside its scheduled collector.

Deploy with dashboard.py and logs_ONU metadata in the same directory.
The collector's CSV files and camera mapping remain in C:\\temp.
"""
import os
from pathlib import Path
import threading
import logging
import json
import math
import re
from http.server import ThreadingHTTPServer

import dashboard

UNSET = object()


class InactivePoints:
    """Geographic inventory without an identified ONU; never network telemetry."""

    def __init__(self, path):
        self.available = True
        self.points = []
        try:
            source = Path(path)
            values = json.loads(source.read_text(encoding='utf-8')) if source.exists() else []
            if not isinstance(values, list):
                raise ValueError('Cadastro de pontos desativados inválido')
            numbers = set()
            for point in values:
                if not isinstance(point, dict) or type(point.get('number')) is not int or not 1 <= point['number'] <= 9999 or point['number'] in numbers:
                    raise ValueError('Identificação de ponto inválida ou duplicada')
                if point.get('map_enabled') is not False or not isinstance(point.get('address'), str) or not point['address'].strip() or len(point['address']) > 300:
                    raise ValueError('Ponto sem endereço ou que não está desativado')
                validate_coordinates(point.get('latitude'), point.get('longitude'))
                if point.get('latitude') is None:
                    raise ValueError('Ponto sem localização')
                numbers.add(point['number'])
            self.points = sorted(values, key=lambda item: item['number'])
        except Exception:
            self.available = False
            logging.exception('Cadastro de pontos desativados não pôde ser carregado; arquivo preservado')

    def overlay(self, data):
        registered = set()
        for row in data.get('rows', []):
            match = re.fullmatch(r'Ponto\s+0*(\d+)', str(row.get('name', '')).strip(), re.I)
            if match:
                registered.add(int(match[1]))
        return {**data, 'inactive_points':[dict(point) for point in self.points if point['number'] not in registered],
            'features':{**data.get('features', {}), 'inactive_points':self.available}}


def validate_coordinates(latitude, longitude):
    if latitude is None and longitude is None:
        return
    if type(latitude) not in (int, float) or type(longitude) not in (int, float) or not math.isfinite(latitude) or not math.isfinite(longitude) or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError('Latitude e longitude inválidas')


class PointNotes:
    """Shared annotations, separate from legacy labels so older clients cannot erase them."""

    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.available = True
        self.values = {}
        try:
            if self.path.exists():
                values = json.loads(self.path.read_text(encoding='utf-8'))
                if not isinstance(values, dict) or any(not isinstance(item, dict) or not isinstance(item.get('text'), str)
                    or ('map_enabled' in item and not isinstance(item['map_enabled'], bool)) for item in values.values()):
                    raise ValueError('Arquivo de observações inválido')
                for item in values.values():
                    if 'latitude' in item or 'longitude' in item:
                        if not {'latitude', 'longitude'} <= item.keys():
                            raise ValueError('Coordenadas incompletas no cadastro')
                        validate_coordinates(item['latitude'], item['longitude'])
                self.values = values
        except Exception:
            self.available = False
            logging.exception('As observações AJIN não puderam ser carregadas; arquivo preservado')

    @staticmethod
    def key(port, onu_id):
        return json.dumps([str(port), str(onu_id)], separators=(',', ':'))

    @staticmethod
    def serial(value):
        return str(value or '').replace(':', '').replace('-', '').upper()

    def save(self, port, onu_id, serial, text, map_enabled=None, latitude=UNSET, longitude=UNSET):
        if text is not None and (not isinstance(text, str) or len(text) > 4000):
            raise ValueError('Observações devem ter até 4000 caracteres')
        if map_enabled is not None and not isinstance(map_enabled, bool):
            raise ValueError('A visibilidade no mapa deve ser verdadeira ou falsa')
        if latitude is not UNSET or longitude is not UNSET:
            validate_coordinates(latitude, longitude)
        with self.lock:
            if not self.available:
                raise ValueError('Arquivo de observações indisponível; nenhuma observação foi sobrescrita')
            values = dict(self.values)
            key = self.key(port, onu_id)
            previous = values.get(key, {})
            if previous.get('serial', '') != self.serial(serial):
                previous = {}
            text = previous.get('text', '') if text is None else text
            visible = previous.get('map_enabled', True) if map_enabled is None else map_enabled
            record = {'serial':self.serial(serial), 'text':text, 'map_enabled':visible}
            if latitude is not UNSET:
                record.update(latitude=latitude, longitude=longitude)
            elif 'latitude' in previous:
                record.update(latitude=previous['latitude'], longitude=previous['longitude'])
            if text or not visible or 'latitude' in record:
                values[key] = record
            else:
                values.pop(key, None)
            temporary = self.path.with_suffix('.json.tmp')
            temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(self.path)
            self.values = values

    def overlay(self, data):
        with self.lock:
            rows = []
            for row in data.get('rows', []):
                note = self.values.get(self.key(row.get('port'), row.get('id')), {})
                same_device = note.get('serial', '') == self.serial(row.get('serial'))
                rows.append({**row, 'notes':note.get('text', '') if same_device else '',
                    'map_enabled':note.get('map_enabled', True) if same_device else True})
                if same_device and 'latitude' in note:
                    rows[-1].update(latitude=note['latitude'], longitude=note['longitude'], coordinates_shared=True)
            return {**data, 'rows':rows, 'features':{**data.get('features', {}), 'point_notes':self.available, 'map_visibility':self.available, 'shared_coordinates':self.available}}


def notes_handler(original, app, notes, lock):
    class NotesHandler(original):
        def do_POST(self):
            if self.path != '/api/point_label':
                return super().do_POST()
            try:
                length = int(self.headers.get('Content-Length') or 0)
                if not 0 < length <= 32768:
                    raise ValueError('Tamanho da requisição inválido')
                body = json.loads(self.rfile.read(length).decode('utf-8'))
                if not isinstance(body, dict):
                    raise ValueError('Identificação inválida')
                port, onu_id = str(body.get('port') or '').strip(), str(body.get('id') or '').strip()
                name, desc, text = body.get('name'), body.get('desc'), body.get('notes')
                map_enabled = body.get('map_enabled')
                latitude, longitude = body.get('latitude', UNSET), body.get('longitude', UNSET)
                if not port or len(port) > 80 or not onu_id or len(onu_id) > 32:
                    raise ValueError('Porta e ID obrigatórios')
                if not isinstance(name, str) or len(name) > 120 or not isinstance(desc, str) or len(desc) > 300 or (text is not None and (not isinstance(text, str) or len(text) > 4000)):
                    raise ValueError('Campos de identificação ou observações inválidos')
                if map_enabled is not None and not isinstance(map_enabled, bool):
                    raise ValueError('Visibilidade no mapa inválida')
                if latitude is not UNSET or longitude is not UNSET:
                    validate_coordinates(latitude, longitude)
                with lock:
                    if not notes.available:
                        raise ValueError('Observações indisponíveis no coletor')
                    serial = app.load_registered().get(f'{port}|{onu_id}', '')
                    if 'expected_serial' in body and (not serial or notes.serial(serial) != notes.serial(body['expected_serial'])):
                        raise ValueError('A ONU mudou desde a preparação da importação. Cadastro preservado.')
                    if not serial:
                        serial = next((row.get('serial', '') for row in app.load_data().get('rows', [])
                            if row.get('port') == port and str(row.get('id')) == onu_id), '')
                    if not serial:
                        raise ValueError('Não foi possível confirmar o serial da ONU. Atualize os dados e tente novamente.')
                    app.save_label(port, onu_id, name=name, desc=desc)
                    notes.save(port, onu_id, serial, text, map_enabled, latitude, longitude)
                result = {'ok':True, 'notes_saved':True, 'map_saved':True, 'coordinates_saved':True}
            except Exception as exc:
                logging.exception('Falha ao salvar identificação e observações AJIN')
                result = {'ok':False, 'error':str(exc)}
            self._send(json.dumps(result).encode('utf-8'), 'application/json; charset=utf-8')
    return NotesHandler


def configure():
    root = Path(__file__).resolve().parent
    metadata = root / "logs_ONU"
    metadata.mkdir(exist_ok=True)
    dashboard.LOGS_DIR = os.environ.get("AJIN_COLLECTOR_DIR", r"C:\temp")
    # These paths were initialized during import and stay in the hub directory.
    dashboard.CAMERAS_FILE = str(Path(dashboard.LOGS_DIR) / "onu_cameras.json")
    dashboard.puxa_logs = None  # No remote copy: the collector runs on this server.
    lock = threading.RLock()
    notes = PointNotes(metadata / 'point_notes.json')
    inactive = InactivePoints(metadata / 'inactive_points.json')
    dashboard.enrich_point_notes = lambda data: inactive.overlay(notes.overlay(data))
    dashboard.Handler = notes_handler(dashboard.Handler, dashboard, notes, lock)
    original_load = dashboard.load_data

    def load_data(*args, **kwargs):
        with lock:
            return original_load(*args, **kwargs)

    dashboard.load_data = load_data

    def log_access(handler):
        try:
            with (metadata / "dash_access.log").open("a", encoding="utf-8") as stream:
                stream.write(f"{handler.client_address[0]} {handler.command} {handler.path}\n")
        except OSError:
            pass

    dashboard.Handler._log_access = log_access
    return dashboard


def main():
    app = configure()
    # Prime once before listening. Every client gets a ready snapshot instead of
    # repeating the expensive scan of CSV history inside its HTTP request.
    original_load = app.load_data
    cached = {"15": original_load()}
    cache_lock = threading.Lock()

    def load_cached(window="15"):
        window = str(window)
        with cache_lock:
            data = cached.get(window)
        if data is None:
            data = original_load(window=window)
            with cache_lock:
                cached[window] = data
        response = {**data, 'server':dict(app.server_ping_state)}
        return getattr(app, 'enrich_point_notes', lambda value:value)(response)

    def refresh():
        while True:
            with cache_lock:
                windows = list(cached)
            for window in windows:
                try:
                    data = original_load(window=window)
                    with cache_lock:
                        cached[window] = data
                except Exception:
                    logging.exception("Falha ao atualizar o snapshot AJIN")
            threading.Event().wait(10)

    logging.basicConfig(filename=str(Path(__file__).resolve().parent / "hub.log"),
                        level=logging.WARNING, encoding="utf-8")
    app.load_data = load_cached
    threading.Thread(target=refresh, daemon=True).start()
    threading.Thread(target=app.server_ping_loop, daemon=True).start()
    threading.Thread(target=app.bench_ping_loop, daemon=True).start()
    # The Scheduled Task owns this process and restarts it after failure.
    # No browser or additional SNMP collector is launched here.
    with ThreadingHTTPServer(("0.0.0.0", app.PORT), app.Handler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
