import socket

import pytest

from webui.app import create_app, find_port
from webui.tasks import ProbeError


class FakeTask:
    def __init__(self):
        self.id = 't1'
        self.status = 'finished'
        self.events = [{'i': 0, 'type': 'title', 'title': '一'}]

    def to_dict(self):
        return {'id': self.id, 'status': self.status}

    def wait_events(self, after, timeout):
        return self.events[after:]


class FakeManager:
    def __init__(self):
        self.started = None
        self.cancelled = None

    def start(self, form, urls, **kwargs):
        from webui.runner import build_args
        build_args(form, downloads_dir='d', ffmpeg_path=None)
        self.started = (form, urls)
        return FakeTask()

    def get(self, task_id):
        return FakeTask() if task_id == 't1' else None

    def list(self):
        return [FakeTask()]

    def cancel(self, task_id):
        self.cancelled = task_id
        return task_id == 't1'


def fake_probe(url, cookies_browser, **kwargs):
    if 'bad' in url:
        raise ProbeError('ERROR: HTTP Error 403', '需要 Cookie')
    return {'title': url, 'cookies': cookies_browser}


@pytest.fixture
def client(tmp_path):
    (tmp_path / 'a.mp4').write_bytes(b'x')
    (tmp_path / 'b.mp4.part').write_bytes(b'x')
    manager = FakeManager()
    app = create_app(downloads_dir=str(tmp_path), manager=manager,
                     probe_fn=fake_probe, ffmpeg_path=None)
    c = app.test_client()
    c.manager = manager
    return c


def test_index(client):
    assert client.get('/').status_code == 200


def test_schema(client):
    assert len(client.get('/api/schema').json['groups']) >= 16


def test_start_extracts_url(client):
    r = client.post('/api/tasks', json={'form': {'--format': 'best'}, 'text': '看看 https://v.douyin.com/abc/ 复制'})
    assert r.status_code == 200 and client.manager.started[1] == ['https://v.douyin.com/abc/']


def test_no_url_400(client):
    r = client.post('/api/tasks', json={'form': {}, 'text': '没有'})
    assert r.status_code == 400 and '链接' in r.json['error']
    assert client.post('/api/probe', json={'text': '没有'}).status_code == 400


def test_unknown_option_400(client):
    r = client.post('/api/tasks', json={'form': {'--nope': '1'}, 'text': 'https://a'})
    assert r.status_code == 400 and '--nope' in r.json['error']


def test_preview(client):
    r = client.post('/api/preview-command', json={'form': {'--format': 'best'}, 'text': 'https://a'})
    assert r.json['command'] == 'yt-dlp --format best https://a'


def test_probe_ok_and_error(client):
    r = client.post('/api/probe', json={'text': 'x https://ok', 'cookies_browser': 'edge'})
    assert r.json == {'title': 'https://ok', 'cookies': 'edge'}
    r = client.post('/api/probe', json={'text': 'https://bad'})
    assert r.status_code == 400 and r.json['hint'] == '需要 Cookie'


def test_tasks_list_and_cancel(client):
    assert client.get('/api/tasks').json == [{'id': 't1', 'status': 'finished'}]
    assert client.post('/api/tasks/t1/cancel').json == {'ok': True}
    assert client.post('/api/tasks/zz/cancel').json == {'ok': False}


def test_events_sse(client):
    r = client.get('/api/tasks/t1/events?after=0')
    body = r.get_data(as_text=True)
    assert r.mimetype == 'text/event-stream'
    assert 'data: {"i": 0' in body and '一' in body
    assert client.get('/api/tasks/nope/events').status_code == 404


def test_files_list_and_serve(client):
    assert [f['name'] for f in client.get('/api/files').json] == ['a.mp4']
    assert client.get('/files/a.mp4').status_code == 200
    assert client.get('/files/../CLAUDE.md').status_code == 404
    assert client.get('/files/%2e%2e/CLAUDE.md').status_code == 404


def test_find_port_returns_free():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    s.listen()
    busy = s.getsockname()[1]
    try:
        assert find_port(busy) != busy
    finally:
        s.close()
