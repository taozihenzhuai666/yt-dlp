"""Turn the web form into yt-dlp arguments, and yt-dlp output back into events."""
import json
import re

from webui.options_schema import build_schema

PROGRESS_TAG = 'WEBUI_PROGRESS '
TITLE_TAG = 'WEBUI_TITLE '
FILE_TAG = 'WEBUI_FILE '

_URL_RE = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+")
_URL_TRAILING = '.,;:!?)\'"'
_NEEDS_QUOTES = re.compile(r'[\s&|<>^()%!*?;,"]')

_ERROR_HINTS = [
    (('cookie database', 'could not copy'), '读取浏览器 Cookie 失败：请完全关闭该浏览器后重试'),
    (('cookies', 'http error 403'), '这个网站需要 Cookie：在常用区「Cookie 来源」里选一个浏览器，并先关闭它'),
    (('unsupported url',), 'yt-dlp 不支持这个链接'),
    (('http error 404',), '视频不存在或已删除'),
    (('requested format is not available',), '没有你选的画质，换一个画质试试'),
    (('password',), '需要账号密码：在高级设置「Authentication Options」里填写'),
]


def extract_urls(text):
    urls = []
    for match in _URL_RE.findall(text or ''):
        url = match.rstrip(_URL_TRAILING)
        if url not in urls:
            urls.append(url)
    return urls


def _option_keys():
    return [o['key'] for g in build_schema()['groups'] for o in g['options']]


def _user_args(form):
    keys = _option_keys()
    unknown = set(form) - set(keys)
    if unknown:
        raise ValueError(f'未知参数 {", ".join(sorted(unknown))}')
    args = []
    for key in keys:
        value = form.get(key)
        if value is True:
            args.append(key)
        elif isinstance(value, str) and value:
            args += [key, value]
        elif isinstance(value, list):
            for item in value:
                if item:
                    args += [key, item]
    return args


def build_args(form, *, downloads_dir, ffmpeg_path):
    args = _user_args(form)
    args += [
        '--newline', '--progress', '--no-quiet',
        '--progress-template', f'download:{PROGRESS_TAG}%(progress)j',
        '--print', f'before_dl:{TITLE_TAG}%(title)s',
        '--print', f'after_move:{FILE_TAG}%(filepath)s',
    ]
    if not form.get('--paths'):
        args += ['-P', downloads_dir]
    if not form.get('--ffmpeg-location') and ffmpeg_path:
        args += ['--ffmpeg-location', ffmpeg_path]
    return args


def _quote(arg):
    if not arg or _NEEDS_QUOTES.search(arg):
        return '"' + arg.replace('"', '\\"') + '"'
    return arg


def build_command_preview(form, urls):
    return ' '.join(['yt-dlp', *map(_quote, _user_args(form)), *map(_quote, urls)])


def _percent(progress):
    total = progress.get('total_bytes') or progress.get('total_bytes_estimate')
    downloaded = progress.get('downloaded_bytes')
    if not total or downloaded is None:
        return None
    return round(downloaded / total * 100, 1)


def parse_line(line):
    if line.startswith(PROGRESS_TAG):
        progress = json.loads(line[len(PROGRESS_TAG):])
        return {
            'type': 'progress',
            'status': progress.get('status'),
            'percent': _percent(progress),
            'downloaded': progress.get('downloaded_bytes'),
            'total': progress.get('total_bytes') or progress.get('total_bytes_estimate'),
            'speed': progress.get('speed'),
            'eta': progress.get('eta'),
            'filename': progress.get('filename'),
        }
    if line.startswith(TITLE_TAG):
        return {'type': 'title', 'title': line[len(TITLE_TAG):]}
    if line.startswith(FILE_TAG):
        return {'type': 'file', 'path': line[len(FILE_TAG):]}
    return {'type': 'log', 'text': line}


def explain_error(log_text):
    lowered = (log_text or '').lower()
    for keywords, hint in _ERROR_HINTS:
        if any(k in lowered for k in keywords):
            return hint
    return None
