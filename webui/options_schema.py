"""Describe every yt-dlp command-line option as data the web page can render."""
import optparse

from yt_dlp.options import create_parser

HIDDEN_KEYS = frozenset({'--help', '--version', '--update', '--no-update', '--update-to'})

GROUP_TITLES_ZH = {
    'Aliases': '别名',
    'General Options': '通用',
    'Network Options': '网络',
    'Geo-restriction': '地区限制',
    'Video Selection': '视频筛选',
    'Download Options': '下载',
    'Filesystem Options': '文件与命名',
    'Thumbnail Options': '缩略图',
    'Internet Shortcut Options': '网页快捷方式',
    'Verbosity and Simulation Options': '输出与模拟',
    'Workarounds': '兼容处理',
    'Video Format Options': '画质与格式',
    'Subtitle Options': '字幕',
    'Authentication Options': '登录认证',
    'Post-Processing Options': '后期处理',
    'SponsorBlock Options': 'SponsorBlock 片段',
    'Extractor Options': '提取器',
}

_FLAG_ACTIONS = ('store_true', 'store_false', 'store_const')
_MULTI_ACTIONS = ('append', 'callback')


def _kind(opt):
    if opt.action in _FLAG_ACTIONS or not opt.takes_value():
        return 'flag'
    if opt.type == 'choice' or opt.choices:
        return 'choice'
    if opt.action in _MULTI_ACTIONS:
        return 'multi'
    return 'text'


def _option(opt):
    help_text = opt.help or ''
    if '%default' in help_text:
        help_text = help_text.replace('%default', str(opt.default))
    return {
        'key': (opt._long_opts or opt._short_opts)[0],
        'flags': [*opt._short_opts, *opt._long_opts],
        'kind': _kind(opt),
        'choices': list(opt.choices) if opt.choices else None,
        'metavar': opt.metavar,
        'help': help_text,
        'dest': opt.dest,
    }


def build_schema():
    groups = []
    for group in create_parser().option_groups:
        options = [
            _option(opt) for opt in group.option_list
            if opt.help != optparse.SUPPRESS_HELP and opt.get_opt_string() not in HIDDEN_KEYS]
        groups.append({
            'id': group.title.lower().replace(' ', '-'),
            'title': group.title,
            'title_zh': GROUP_TITLES_ZH.get(group.title, group.title),
            'options': options,
        })
    return {'groups': groups}
