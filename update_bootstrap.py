"""Confirma ao helper que o frontend da versão instalada carregou."""
import json
import sys
from pathlib import Path
from update_engine import write_json_atomic
from version import CURRENT_VERSION


def confirm_update_startup(argv=None):
    argv = sys.argv if argv is None else argv
    if '--update-receipt' not in argv or '--update-token' not in argv:
        return False
    receipt = Path(argv[argv.index('--update-receipt') + 1]).resolve()
    token = argv[argv.index('--update-token') + 1]
    if receipt.name != 'receipt.json':
        raise ValueError('Recibo de atualização inválido.')
    job = json.loads((receipt.parent / 'job.json').read_text(encoding='utf-8'))
    if (job['token'] != token or job['version'] != CURRENT_VERSION
            or Path(job['target']).resolve() != Path(sys.executable).resolve()
            or Path(job['receipt']).resolve() != receipt):
        raise ValueError('Versão instalada não corresponde à atualização solicitada.')
    write_json_atomic(receipt, {'token': token, 'version': CURRENT_VERSION})
    return True
