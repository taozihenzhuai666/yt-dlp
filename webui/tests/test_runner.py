import pytest

from webui.runner import (
    build_args,
    build_command_preview,
    explain_error,
    extract_urls,
    parse_line,
)


def test_extract_from_douyin_share():
    t = '2.84 复制打开抖音，看看【秋芝2046的作品】一站式创作Agent！... https://v.douyin.com/gKWRpvtVAGg/ C@h.Bg :7pm 01/26 nQx:/'
    assert extract_urls(t) == ['https://v.douyin.com/gKWRpvtVAGg/']


def test_extract_multiple_and_chinese_tail():
    t = 'a https://b23.tv/abc看看\nhttps://youtu.be/x?y=1&z=2，'
    assert extract_urls(t) == ['https://b23.tv/abc', 'https://youtu.be/x?y=1&z=2']


def test_extract_none():
    assert extract_urls('没有链接') == []


def test_build_args_user_then_internal():
    a = build_args({'--format': 'bv*+ba', '--no-playlist': True,
                    '--sub-langs': ['en', 'zh-Hans'], '--quiet': True,
                    '--write-subs': False, '--output': ''},
                   downloads_dir='D:/dl', ffmpeg_path='C:/ff.exe')
    i = a.index('--format')
    assert a[i:i + 2] == ['--format', 'bv*+ba']
    j = a.index('--sub-langs')
    assert a[j:j + 4] == ['--sub-langs', 'en', '--sub-langs', 'zh-Hans']
    assert '--no-playlist' in a and a.index('--no-playlist') < a.index('--newline')
    assert '--write-subs' not in a and '--output' not in a
    for x in ['--newline', '--progress', '--no-quiet', '--progress-template',
              '-P', 'D:/dl', '--ffmpeg-location', 'C:/ff.exe']:
        assert x in a
    assert a.index('--no-quiet') > a.index('--quiet')


def test_user_paths_not_overridden():
    a = build_args({'--paths': ['E:/mine'], '--ffmpeg-location': 'E:/ff'},
                   downloads_dir='D:/dl', ffmpeg_path='C:/ff.exe')
    assert 'D:/dl' not in a and 'C:/ff.exe' not in a


def test_unknown_key_rejected():
    with pytest.raises(ValueError):
        build_args({'--exec-not-real': 'x'}, downloads_dir='d', ffmpeg_path=None)


def test_preview_quotes_and_hides_internal():
    s = build_command_preview({'--format': 'best[height<=720]'}, ['https://x.com/a b&c'])
    assert s.startswith('yt-dlp ') and '"https://x.com/a b&c"' in s
    assert '--format "best[height<=720]"' in s
    assert build_command_preview({'--format': 'best'}, ['https://a']) == 'yt-dlp --format best https://a'
    assert 'WEBUI_' not in s and '--progress-template' not in s


def test_parse_progress_and_chinese():
    p = parse_line(r'WEBUI_PROGRESS {"status": "downloading", "downloaded_bytes": 50, "total_bytes": 200, "speed": 1024.0, "eta": 3, "filename": "downloads\\秋芝.mp4.part"}')
    assert p['type'] == 'progress' and p['percent'] == 25.0 and p['eta'] == 3
    assert p['filename'].endswith('秋芝.mp4.part')
    assert parse_line('WEBUI_TITLE 一站式创作Agent')['title'] == '一站式创作Agent'
    assert parse_line(r'WEBUI_FILE D:\dl\秋芝.mp4')['path'].endswith('秋芝.mp4')
    assert parse_line('[download] hello') == {'type': 'log', 'text': '[download] hello'}


def test_progress_without_total():
    p = parse_line('WEBUI_PROGRESS {"status": "downloading", "downloaded_bytes": 50, "total_bytes_estimate": 100}')
    assert p['percent'] == 50.0
    assert parse_line('WEBUI_PROGRESS {"status": "downloading", "downloaded_bytes": 50}')['percent'] is None


def test_explain_error():
    assert 'Cookie' in explain_error('ERROR: [Douyin] 1: Fresh cookies (not necessarily logged in) are needed')
    assert 'Cookie' in explain_error('HTTP Error 403: Forbidden')
    assert '不支持' in explain_error('ERROR: Unsupported URL: https://a')
    assert '关闭' in explain_error('Could not copy Chrome cookie database')
    assert explain_error('everything fine') is None


def test_explain_error_prefers_error_lines_over_warnings():
    log = ('[BiliBili] Format(s) 1080P are missing; Use --cookies-from-browser or --cookies for the authentication.\n'
           "ERROR: Unable to download video: [WinError 32] 另一个程序正在使用此文件，进程无法访问。: 'a.mp4'\n")
    hint = explain_error(log)
    assert 'Cookie' not in hint and '占用' in hint


def test_explain_error_ignores_warning_only_when_error_unmatched():
    log = 'WARNING: Use --cookies for the authentication.\nERROR: something unknown\n'
    assert explain_error(log) is None
