"""Local web UI for yt-dlp: `python -m webui.app` from the repository root."""
import json
import os
import socket
import threading
import webbrowser

from flask import Flask, Response, abort, jsonify, request, send_from_directory

from webui.options_schema import build_schema
from webui.runner import build_command_preview, extract_urls
from webui.tasks import REPO_ROOT, ProbeError, TaskManager, probe

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
DEFAULT_PORT = 8765
_LOCAL_HOSTS = ('127.0.0.1', 'localhost')
_LEFTOVER_MARKERS = ('.part', '.ytdl', '.temp.', '-Frag')


def _default_ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _error(message, hint=None, status=400):
    return jsonify({'error': message, 'hint': hint}), status


def create_app(*, downloads_dir, manager=None, probe_fn=probe, ffmpeg_path=_default_ffmpeg()):
    app = Flask(__name__, static_folder=None)
    app.json.ensure_ascii = False
    manager = manager or TaskManager()
    downloads_dir = os.path.abspath(downloads_dir)
    schema = build_schema()

    @app.before_request
    def only_this_page():
        # The server can run any yt-dlp option (even --exec), so refuse requests that
        # other web pages could forge: wrong Host (DNS rebinding) or cross-origin POSTs
        if request.host.rsplit(':', 1)[0].strip('[]') not in _LOCAL_HOSTS:
            return _error('只接受本机访问', status=403)
        if request.method == 'POST':
            origin = request.headers.get('Origin')
            if not request.is_json or (origin and origin != f'http://{request.host}'):
                return _error('只接受本页面发出的请求', status=403)

    @app.get('/')
    def index():
        return send_from_directory(STATIC_DIR, 'index.html')

    @app.get('/api/schema')
    def get_schema():
        return jsonify(schema)

    @app.post('/api/preview-command')
    def preview_command():
        body = request.get_json()
        try:
            command = build_command_preview(body.get('form') or {}, extract_urls(body.get('text', '')))
        except ValueError as e:
            return _error(str(e))
        return jsonify({'command': command})

    @app.post('/api/probe')
    def probe_url():
        body = request.get_json()
        urls = extract_urls(body.get('text', ''))
        if not urls:
            return _error('没有找到链接')
        try:
            return jsonify(probe_fn(urls[0], body.get('cookies_browser')))
        except ProbeError as e:
            return _error(e.message, e.hint)

    @app.post('/api/tasks')
    def start_task():
        body = request.get_json()
        urls = extract_urls(body.get('text', ''))
        if not urls:
            return _error('没有找到链接')
        try:
            task = manager.start(body.get('form') or {}, urls,
                                 downloads_dir=downloads_dir, ffmpeg_path=ffmpeg_path)
        except ValueError as e:
            return _error(str(e))
        return jsonify(task.to_dict())

    @app.get('/api/tasks')
    def list_tasks():
        return jsonify([t.to_dict() for t in reversed(manager.list())])

    @app.get('/api/tasks/<task_id>/events')
    def task_events(task_id):
        task = manager.get(task_id)
        if not task:
            abort(404)
        after = request.args.get('after', 0, type=int)

        def stream():
            nonlocal after
            while True:
                events = task.wait_events(after, timeout=15)
                for event in events:
                    yield f'data: {json.dumps(event, ensure_ascii=False)}\n\n'
                after += len(events)
                if task.status != 'running' and after >= len(task.events):
                    return
                if not events:
                    yield ': ping\n\n'

        return Response(stream(), mimetype='text/event-stream',
                        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    @app.post('/api/tasks/<task_id>/cancel')
    def cancel_task(task_id):
        return jsonify({'ok': manager.cancel(task_id)})

    @app.get('/api/files')
    def list_files():
        files = []
        if os.path.isdir(downloads_dir):
            for entry in os.scandir(downloads_dir):
                if entry.is_file() and not any(m in entry.name for m in _LEFTOVER_MARKERS):
                    stat = entry.stat()
                    files.append({'name': entry.name, 'size': stat.st_size, 'mtime': stat.st_mtime})
        files.sort(key=lambda f: f['mtime'], reverse=True)
        return jsonify(files)

    @app.get('/files/<path:name>')
    def serve_file(name):
        return send_from_directory(downloads_dir, name)

    @app.post('/api/open-folder')
    def open_folder():
        os.makedirs(downloads_dir, exist_ok=True)
        os.startfile(downloads_dir)
        return jsonify({'ok': True})

    return app


def find_port(preferred=DEFAULT_PORT):
    for port in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind(('127.0.0.1', port))
            except OSError:
                continue
            return s.getsockname()[1]
    raise OSError('没有可用端口')


def main():
    downloads_dir = os.path.join(REPO_ROOT, 'downloads')
    os.makedirs(downloads_dir, exist_ok=True)
    port = find_port()
    url = f'http://127.0.0.1:{port}/'
    print(f'yt-dlp 网页已启动：{url}  （关闭这个窗口即停止）', flush=True)
    if not os.environ.get('WEBUI_NO_BROWSER'):
        threading.Timer(1, webbrowser.open, args=(url,)).start()
    create_app(downloads_dir=downloads_dir).run(host='127.0.0.1', port=port, threaded=True)


if __name__ == '__main__':
    main()
