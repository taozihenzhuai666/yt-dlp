import optparse

from yt_dlp.options import create_parser
from webui.options_schema import GROUP_TITLES_ZH, HIDDEN_KEYS, build_schema


def _all(schema):
    return [o for g in schema['groups'] for o in g['options']]


def test_counts_match_parser():
    p = create_parser()
    visible = [o for g in p.option_groups for o in g.option_list
               if o.help != optparse.SUPPRESS_HELP]
    hidden = [o for o in visible if o.get_opt_string() in HIDDEN_KEYS]
    assert len(_all(build_schema())) == len(visible) - len(hidden)
    assert len(build_schema()['groups']) == len(p.option_groups)


def test_hidden_not_present():
    keys = {o['key'] for o in _all(build_schema())}
    assert not keys & HIDDEN_KEYS


def test_kinds():
    by = {o['key']: o for o in _all(build_schema())}
    assert by['--no-playlist']['kind'] == 'flag'
    assert by['--format']['kind'] == 'text' and by['--format']['metavar'] == 'FORMAT'
    assert by['--sub-langs']['kind'] == 'multi'
    assert by['--add-headers']['kind'] == 'multi'
    assert by['--convert-subs']['kind'] in ('choice', 'text')
    assert by['--format']['flags'] == ['-f', '--format']


def test_every_group_has_chinese_title():
    for g in build_schema()['groups']:
        assert g['title_zh'] and g['title_zh'] != g['title']
        assert g['title'] in GROUP_TITLES_ZH
