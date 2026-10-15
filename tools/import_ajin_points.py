"""Prepare or apply the supplied AJIN point mapping. Defaults to a read-only plan."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request


def coordinates(latitude, longitude):
    return all(type(value) in (float, int) and math.isfinite(value) for value in (latitude, longitude)) and -90 <= latitude <= 90 and -180 <= longitude <= 180


def point_number(name):
    match = re.fullmatch(r'Ponto\s+0*(\d+)', str(name).strip(), re.IGNORECASE)
    return int(match[1]) if match else None


def parse_mapping(text):
    points = {}
    for line in text.splitlines():
        if not line.startswith('| **Ponto '):
            continue
        cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
        if len(cells) != 6:
            raise ValueError('Linha da tabela com colunas inesperadas')
        match = re.fullmatch(r'\*\*Ponto (\d+)(?: \(Desativado\))?\*\*', cells[0])
        pair = re.fullmatch(r'`(-?\d+\.\d+),\s*(-?\d+\.\d+)`', cells[3])
        if not match or not pair:
            raise ValueError('Ponto ou coordenadas inválidas na tabela')
        number = int(match[1])
        if number in points:
            raise ValueError(f'Ponto {number} duplicado no arquivo')
        lat, lon = map(float, pair.groups())
        if not coordinates(lat, lon):
            raise ValueError(f'Coordenadas fora dos limites no ponto {number}')
        url = re.search(r'\]\((https://www\.google\.com/maps\?[^)]+)\)', cells[5])
        if url:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url[1]).query).get('q', [''])[0]
            precise_lat, precise_lon = map(float, query.split(','))
            if not coordinates(precise_lat, precise_lon) or abs(lat - precise_lat) > 1e-6 or abs(lon - precise_lon) > 1e-6:
                raise ValueError(f'Tabela e link divergem no ponto {number}')
            lat, lon = precise_lat, precise_lon
        if 'Desativado' not in cells[4] and 'Ativo' not in cells[4]:
            raise ValueError(f'Status desconhecido no ponto {number}')
        points[number] = {'number':number, 'address':cells[1], 'region':cells[2], 'latitude':lat, 'longitude':lon,
                          'active':'Desativado' not in cells[4]}
    if not points:
        raise ValueError('Nenhum ponto encontrado na tabela')
    return points


def prepare(points, rows, excluded):
    counts = Counter(point_number(row.get('name')) for row in rows)
    changes, pending = [], []
    known = set()
    for row in rows:
        number = point_number(row.get('name'))
        known.add(number)
        if number in excluded or number not in points or counts[number] != 1 or not row.get('serial'):
            reason = 'Pendente por decisão do usuário' if number in excluded else 'Nome/serial ausente, sem correspondência ou duplicado'
            pending.append({'name':row.get('name'), 'port':row['port'], 'id':str(row['id']), 'reason':reason})
            continue
        point = points[number]
        payload = {'port':row['port'], 'id':str(row['id']), 'name':row['name'], 'desc':point['address'],
                   'latitude':point['latitude'], 'longitude':point['longitude'], 'expected_serial':row['serial'],
                   'map_enabled':False if not point['active'] else row.get('map_enabled', True)}
        previous = str(row.get('desc') or '').strip()
        if previous and (previous.lower() == 'angeloni' or 'onu' in previous.lower()):
            note = f'Referência anterior do cadastro: {previous}'
            notes = str(row.get('notes') or '').strip()
            if note not in notes:
                payload['notes'] = f'{notes}\n{note}'.strip()
                if len(payload['notes']) > 4000:
                    raise ValueError(f'Observações excederiam o limite em {row["name"]}')
        changes.append({'point':number, 'before':row, 'payload':payload})
    changes.sort(key=lambda change:change['point'])
    return {'source_points':len(points), 'inventory':len(rows), 'changes':changes, 'pending':pending,
            'not_registered':[points[number] for number in sorted(points.keys() - known)]}


def inactive_catalog(plan):
    """Export missing geographic points without fabricating ONU identities."""
    return [{key:point[key] for key in ('number', 'address', 'region', 'latitude', 'longitude')} | {'map_enabled':False}
            for point in plan['not_registered']]


def request(hub, path, payload=None):
    req = urllib.request.Request(hub.rstrip('/') + path,
        data=None if payload is None else json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8'),
        headers={'Content-Type':'application/json', 'User-Agent':'RemoteXPTI-PointImport'},
        method='GET' if payload is None else 'POST')
    with urllib.request.urlopen(req, timeout=15) as response:
        result = json.load(response)
        if response.status != 200:
            raise ValueError('Resposta inesperada do coletor')
    if payload is not None and (result.get('ok') is not True or result.get('coordinates_saved') is not True):
        raise ValueError(result.get('error') or 'O coletor não confirmou a importação')
    return result


def report(plan, applied, error=None):
    lines = ['# Importação dos endereços e coordenadas AJIN', '', f'- Pontos no arquivo: {plan["source_points"]}.',
             f'- ONUs no inventário: {plan["inventory"]}.', f'- Pontos importados: {len(applied)}.',
             f'- Cadastros pendentes: {len(plan["pending"])}.', f'- Pontos sem ONU cadastrada: {len(plan["not_registered"])}.', '']
    if error:
        lines += [f'Importação interrompida: {error}', '']
    lines += ['## Importados', '', '| Ponto | Porta / ID da ONU | Endereço | Latitude | Longitude |', '|---|---|---|---|---|']
    for item in applied:
        value = item['payload']
        lines.append(f'| {value["name"]} | {value["port"]} / {value["id"]} | {value["desc"]} | {value["latitude"]} | {value["longitude"]} |')
    lines += ['', '## Pendentes', '']
    lines += [f'- {item["name"]} ({item["port"]}, ONU {item["id"]}): {item["reason"]}.' for item in plan['pending']]
    lines += ['', '## Sem ONU cadastrada', '', ', '.join(f'Ponto {item["number"]:02}' for item in plan['not_registered']) + '.', '',
              'Os pontos sem ONU não foram cadastrados artificialmente. Os endereços e coordenadas importados ficam no coletor e são compartilhados. Observações e escolhas de visibilidade existentes foram preservadas. Nenhuma ONU foi excluída ou desativada.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--hub', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--exclude-point', type=int, action='append', default=[])
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    source = args.source.read_bytes()
    data = request(args.hub, '/data')
    plan = prepare(parse_mapping(source.decode('utf-8-sig')), data['rows'], set(args.exclude_point))
    plan.update(source_sha256=hashlib.sha256(source).hexdigest(), created_at=datetime.now().isoformat())
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'before.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    (args.output/'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    (args.output/'inactive_points.json').write_text(json.dumps(inactive_catalog(plan), ensure_ascii=False, indent=2), encoding='utf-8')
    applied, error = [], None
    if args.apply:
        if not data.get('features', {}).get('shared_coordinates'):
            raise ValueError('O coletor ainda não oferece coordenadas compartilhadas')
        try:
            for item in plan['changes']:
                request(args.hub, '/api/point_label', item['payload'])
                applied.append(item)
                (args.output/'applied.json').write_text(json.dumps(applied, ensure_ascii=False, indent=2), encoding='utf-8')
            deadline = time.monotonic() + 30
            while True:
                after = request(args.hub, '/data')
                by_key = {(row['port'], str(row['id'])):row for row in after['rows']}
                confirmed = all((row := by_key.get((item['payload']['port'], item['payload']['id'])))
                    and row.get('coordinates_shared') and all(row.get(field) == item['payload'][field]
                        for field in ('name', 'desc', 'latitude', 'longitude', 'map_enabled')) for item in applied)
                if confirmed:
                    break
                if time.monotonic() >= deadline:
                    raise ValueError('O snapshot do coletor não confirmou todos os campos importados no prazo previsto')
                time.sleep(.5)
            (args.output/'after.json').write_text(json.dumps(after, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception as exc:
            error = str(exc)
        if args.report:
            args.report.write_text(report(plan, applied, error), encoding='utf-8')
    print(json.dumps({'source':plan['source_points'], 'inventory':plan['inventory'], 'planned':len(plan['changes']),
                      'applied':len(applied), 'pending':plan['pending'], 'not_registered':[point['number'] for point in plan['not_registered']],
                      'error':error, 'backup':str(args.output)}, ensure_ascii=False))
    if error:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
