"""Annual dispatcher with guarded support for categories lacking source headers."""
import copy
import importlib.util
from pathlib import Path

from seed import annual_series

# Give the frozen engine its own globals rather than changing the implementation
# or runtime profile used by already-published editions.
_spec = importlib.util.spec_from_file_location('seed._annual_legacy_runtime', Path(annual_series.__file__))
_engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_engine)
VERSION = 'annual-series-1.1'
_engine.VERSION = VERSION
_engine.INPUTS = (*_engine.INPUTS, 'seed/annual_legacy.py', 'reference/schema/ANNUAL_LEGACY.md')
_compare = _engine.compare_profile
_verify = _engine.verify
_render = _engine.render


def compare_profile(config, prior, doc):
    if len(prior['categories']) != len(doc['categories']):
        return _compare(config, prior, doc)
    missing = []
    for index, (old, new) in enumerate(zip(prior['categories'], doc['categories'])):
        if 'line' not in old or 'line' not in new:
            if ('line' in old) != ('line' in new) or old.get('name') is not None or new.get('name') is not None:
                raise ValueError('Unexplained category source-location change')
            if any(key in old or key in new for key in ('raw',)):
                raise ValueError('Unheaded category unexpectedly has a raw heading')
            missing.append(index)
    if not missing:
        return _compare(config, prior, doc)
    before, after = copy.deepcopy(prior), copy.deepcopy(doc)
    for index in missing:
        # Comparison-only sentinel. No invented line is stored in extraction.
        before['categories'][index]['line'] = None
        after['categories'][index]['line'] = None
    result = _compare(config, before, after)
    result['unheaded_categories_preserved'] = missing
    return result


def verify(conn, *, complete=True):
    if annual_series.selected_profile(conn) == VERSION:
        return _verify(conn, complete=complete)
    return annual_series.verify(conn, complete=complete)


def render(conn, digest):
    if annual_series.selected_profile(conn) == VERSION:
        return _render(conn, digest)
    return annual_series.render(conn, digest)


_engine.compare_profile = compare_profile
_engine.verify = verify
_engine.render = render
build = _engine.build
prepare = _engine.prepare
retire = _engine.retire
profile_context = _engine.profile_context
make_profile = _engine.make_profile
read_config = _engine.read_config


if __name__ == '__main__':
    _engine.main()
