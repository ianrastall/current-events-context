"""Pinned comparison of consecutive citation-only source continuation lines."""
import copy
import datetime as dt
from contextlib import closing
import importlib.util
from pathlib import Path
import re

from seed import annual_archive as annual, annual_labels

_spec = importlib.util.spec_from_file_location('seed._annual_continuations_labels', Path(annual_labels.__file__))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)
VERSION = 'annual-series-1.5'
_base.VERSION = VERSION
_engine = _base._engine
_engine.VERSION = VERSION
_base._base._base.VERSION = VERSION
_base._base._base._base.VERSION = VERSION
_engine.INPUTS = (*_engine.INPUTS, 'seed/annual_continuations.py', 'reference/schema/ANNUAL_CONTINUATIONS.md')
_compare = _engine.compare_profile
_validate = _engine.validate_config


def validate_config(config):
    _validate(config)
    seen = set()
    for rule in config.get('citation_continuations', []):
        day = dt.date.fromisoformat(rule['date'])
        if (str(day) != rule['date'] or type(rule['line']) is not int or rule['line'] < 1
                or not isinstance(rule['source_path'], list) or not rule['source_path']
                or any(type(n) is not int or n < 1 for n in rule['source_path'])):
            raise ValueError('Invalid citation continuation source locator')
        key = (rule['date'], rule['category'], tuple(rule['source_path']), rule['line'])
        if key in seen or day.year != config['year'] or not rule['reason'].strip():
            raise ValueError('Duplicate, out-of-year or undocumented citation continuation')
        seen.add(key)
        for field in ('source_sha256', 'prior_entry_sha256', 'extraction_entry_sha256'):
            if not re.fullmatch('[0-9a-f]{64}', rule.get(field, '')):
                raise ValueError('Citation continuation requires exact source/entry hashes')


def compare_profile(config, prior, doc):
    normalized = copy.deepcopy(prior)
    groups = []
    for rule in (r for r in config.get('citation_continuations', []) if r['date'] == doc['date']):
        def locate(value):
            entries = [e for c in value['categories'] if c['name'] == rule['category']
                       for e in c['entries'] if e['source_path'] == rule['source_path'] and e['line'] == rule['line']]
            if len(entries) != 1:
                raise ValueError('Citation continuation locator drift')
            return entries[0]
        old, new = locate(prior), locate(doc)
        if (prior['source_page']['source_sha256'] != rule['source_sha256']
                or doc['source_page']['source_sha256'] != rule['source_sha256']
                or annual.structured_hash(old) != rule['prior_entry_sha256']
                or annual.structured_hash(new) != rule['extraction_entry_sha256']
                or not new['raw'].startswith(old['raw'] + '\n')):
            raise ValueError('Citation continuation source/entry guard drift')
        appended = new['raw'][len(old['raw']) + 1:].split('\n')
        if len(appended) < 2:
            raise ValueError('Consecutive citation rule is stale or unnecessary')
        first = old['line'] + old['raw'].count('\n') + 1
        records = []
        for line, raw in enumerate(appended, first):
            before = [w for w in prior['warnings'] if w['code'] == 'UNSUPPORTED_CONTENT' and w['line'] == line and w['raw'] == raw]
            after = [w for w in doc['warnings'] if w['code'] == 'CITATION_CONTINUATION' and w['line'] == line and w['raw'] == raw
                     and w.get('resolution') == 'deterministic_source_rule']
            if len(before) != 1 or len(after) != 1:
                raise ValueError('Citation continuation warning coverage drift')
            records.append({'line': line, 'raw_sha256': annual.digest(raw.encode('utf-8'))})
        # Comparison-only aggregate: the frozen lossless comparator accepts a
        # single preserved warning fragment. Stored warnings remain separate.
        aggregate = copy.deepcopy(before[0])
        aggregate['raw'] = '\n'.join(appended)
        normalized['warnings'].append(aggregate)
        groups.append({**rule, 'continuation_lines': records})
    report = _compare(config, normalized, doc)
    report['consecutive_citation_reconciliations'] = groups
    return report


_engine.validate_config = validate_config
_engine.compare_profile = compare_profile
build = _base.build
make_profile = _base.make_profile
read_config = _base.read_config
profile_context = _base.profile_context


def verify(conn, *, complete=True):
    if _engine.selected_profile(conn) == VERSION:
        return _base.verify(conn, complete=complete)
    return annual_labels.verify(conn, complete=complete)


def render(conn, digest):
    if _engine.selected_profile(conn) == VERSION:
        return _base.render(conn, digest)
    return annual_labels.render(conn, digest)


def prepare(database, root=annual.ROOT):
    with closing(annual.connect(database, readonly=True)) as conn:
        selected = _engine.selected_profile(conn) == VERSION
    return (_base.prepare if selected else annual_labels.prepare)(database, root)


def retire(database, root=annual.ROOT):
    with closing(annual.connect(database, readonly=True)) as conn:
        selected = _engine.selected_profile(conn) == VERSION
    return (_base.retire if selected else annual_labels.retire)(database, root)


_engine.verify = verify
_engine.render = render
_engine.prepare = prepare
_engine.retire = retire
if __name__ == '__main__':
    _engine.main()
