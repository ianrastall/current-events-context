"""Annual extraction successor for exact, guarded source-label interpretations."""
import copy
from contextlib import closing
import importlib.util
from pathlib import Path

from seed import annual_archive as annual, annual_unverified

# Preserve the 1.3 publication protocol and its frozen access implementation.
# Only the extraction profile advances; earlier editions delegate unchanged.
_spec = importlib.util.spec_from_file_location('seed._annual_labels_unverified', Path(annual_unverified.__file__))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)
VERSION = 'annual-series-1.4'
_engine = _base._engine
_engine.VERSION = VERSION
_base._base.VERSION = VERSION
_base._base._base.VERSION = VERSION
_engine.INPUTS = (*_engine.INPUTS, 'seed/annual_labels.py', 'reference/schema/ANNUAL_LABELS.md')
_base.selected = lambda conn: _engine.selected_profile(conn) == VERSION
_compare = _engine.compare_profile
_validate = _engine.validate_config


def validate_config(config):
    _validate(config)
    seen = set()
    for rule in config['roles']:
        if rule.get('interpretation') != 'explicit_source_label':
            continue
        key = (rule['date'], rule['category'], tuple(rule['source_path']))
        if key in seen or rule['role'] != 'topic' or type(rule.get('line')) is not int:
            raise ValueError('Invalid or duplicate explicit source label')
        seen.add(key)
        if not _engine.re.fullmatch('[0-9a-f]{64}', rule.get('prior_entry_sha256', '')):
            raise ValueError('Explicit source label requires exact prior entry hash')


def compare_profile(config, prior, doc):
    normalized = copy.deepcopy(doc)
    changes = []
    rules = [r for r in config['roles'] if r['date'] == doc['date']
             and r.get('interpretation') == 'explicit_source_label']
    for rule in rules:
        def locate(value):
            found = [e for c in value['categories'] if c['name'] == rule['category']
                     for e in c['entries'] if e['source_path'] == rule['source_path']
                     and e['line'] == rule['line']]
            if len(found) != 1:
                raise ValueError('Explicit source label locator drift')
            return found[0]
        old, new = locate(prior), locate(normalized)
        if (prior['source_page']['source_sha256'] != rule['source_sha256']
                or doc['source_page']['source_sha256'] != rule['source_sha256']
                or annual.structured_hash(old) != rule['prior_entry_sha256']
                or _engine.extract.fingerprint(new['raw']) != rule['raw_sha256']
                or old['role'] != 'event' or new['role'] != 'topic'):
            raise ValueError('Explicit source label guard drift')
        # Comparison only: all text, links, citations and hierarchy still pass
        # the original lossless comparator. The actual document retains topic.
        new['role'] = old['role']
        changes.append({'line': new['line'], 'before': 'event', 'after': 'topic',
                        'reason': rule['reason'], 'prior_entry_sha256': rule['prior_entry_sha256']})
    report = _compare(config, prior, normalized)
    report['source_role_changes'] = report.get('source_role_changes', []) + changes
    report['event_assertion_delta'] = report.get('event_assertion_delta', report['event_leaf_delta']) - len(changes)
    report['event_leaf_delta'] = report['event_assertion_delta']
    return report


_engine.validate_config = validate_config
_engine.compare_profile = compare_profile
build = _base.build
make_profile = _base.make_profile
read_config = _base.read_config
profile_context = _base.profile_context


def prepare(database, root=annual.ROOT):
    with closing(annual.connect(database, readonly=True)) as conn:
        selected = _base.selected(conn)
    return (_base.prepare if selected else annual_unverified.prepare)(database, root)


def retire(database, root=annual.ROOT):
    with closing(annual.connect(database, readonly=True)) as conn:
        selected = _base.selected(conn)
    return (_base.retire if selected else annual_unverified.retire)(database, root)


def verify(conn, *, complete=True):
    if _base.selected(conn):
        return _base.verify(conn, complete=complete)
    return annual_unverified.verify(conn, complete=complete)


def render(conn, digest):
    if _base.selected(conn):
        return _base.render(conn, digest)
    return annual_unverified.render(conn, digest)


# The CLI must use the outer dispatcher for old as well as new editions.
_engine.verify = verify
_engine.render = render
_engine.prepare = prepare
_engine.retire = retire
if __name__ == '__main__':
    _engine.main()
