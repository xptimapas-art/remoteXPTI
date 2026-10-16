"""Group names remain compatible with legacy server records."""
import unicodedata

DEFAULT_GROUPS = ('BEMTEVI', 'SEJURI', 'XPTI')


def group_key(value):
    return unicodedata.normalize('NFKC', value.strip()).casefold()


def group_name(value):
    if not isinstance(value, str):
        raise ValueError('Informe um nome de grupo.')
    name = value.strip()
    if not name or len(name) > 60 or any(ord(char) < 32 for char in name):
        raise ValueError('O grupo deve ter de 1 a 60 caracteres, sem quebras de linha.')
    return name
