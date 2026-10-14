"""Run yt-dlp downloads in the background and collect their events."""
import glob
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid

from webui.runner import build_args, explain_error, parse_line

YTDLP_CMD = [sys.executable, '-m', 'yt_dlp']
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_ENV = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')


def _kill_tree(pid):
    if os.name == 'nt':
        subprocess.run(['taskkill', '/T', '/F', '/PID', str(pid)],
                       capture_output=True, check=False)
    else:
        import signal
        os.killpg(os.getpgid(pid), signal.SIGKILL)


def _popen(cmd, cwd, **kwargs):
    extra = {} if os.name == 'nt' else {'start_new_session': True}
    return subprocess.Popen(
        cmd, cwd=cwd, env=_ENV, stdin=subprocess.DEVNULL, shell=False, **extra, **kwargs)


class Task:
    def __init__(self, urls):
        self.id = uuid.uuid4().hex[:12]
        self.urls = urls
        self.status = 'running'
        self.title = None
        self.progress = None
        self.files = []
        self.events = []
        self.error_hint = None
        self._cancelled = False
        self._partials = set()
        self._cond = threading.Condition(threading.RLock())

    def _add(self, event):
        with self._cond:
            event = {'i': len(self.events), **event}
            self.events.append(event)
            self._cond.notify_all()

    def _handle(self, line):
        event = parse_line(line)
        if event['type'] == 'progress':
            self.progress = event
            if event.get('filename') and event.get('status') == 'downloading':
                self._partials.add(event['filename'])
        elif event['type'] == 'title':
            self.title = event['title']
        elif event['type'] == 'file':
            self.files.append(event['path'])
        self._add(event)

    def wait_events(self, after, timeout):
        with self._cond:
            if len(self.events) <= after and self.status == 'running':
                self._cond.wait(timeout)
            return self.events[after:]

    def to_dict(self):
        return {
            'id': self.id,
            'urls': self.urls,
            'status': self.status,
            'title': self.title,
            'progress': self.progress,
            'files': self.files,
            'error_hint': self.error_hint,
        }


class TaskManager:
    def __init__(self, cmd=YTDLP_CMD, cwd=REPO_ROOT):
        self.cmd = cmd
        self.cwd = cwd
        self._tasks = {}
        self._procs = {}

    def start(self, form, urls, *, downloads_dir, ffmpeg_path):
        args = build_args(form, downloads_dir=downloads_dir, ffmpeg_path=ffmpeg_path)
        task = Task(urls)
        proc = _popen([*self.cmd, *args, *urls], self.cwd,
                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self._tasks[task.id] = task
        self._procs[task.id] = proc
        threading.Thread(target=self._read, args=(task, proc), daemon=True).start()
        return task

    def _read(self, task, proc):
        log = []
        for raw in proc.stdout:
            line = raw.decode('utf-8', 'replace').rstrip('\r\n')
            if line:
                log.append(line)
                task._handle(line)
        code = proc.wait()
        if task._cancelled:
            _remove_partials(task._partials)
            status = 'cancelled'
        elif code == 0:
            status = 'finished'
        else:
            status = 'error'
            task.error_hint = explain_error('\n'.join(log))
        with task._cond:
            task._add({'type': 'status', 'status': status})
            task.status = status

    def get(self, task_id):
        return self._tasks.get(task_id)

    def list(self):
        return list(self._tasks.values())

    def cancel(self, task_id):
        task, proc = self._tasks.get(task_id), self._procs.get(task_id)
        if not task or task.status != 'running':
            return False
        task._cancelled = True
        _kill_tree(proc.pid)
        return True


_FORMAT_SUFFIX_RE = re.compile(r'\.f[0-9A-Za-z_-]+(\.[^.\\/]+)$')


def _leftovers(name):
    # Everything yt-dlp/ffmpeg may leave for a file that was still downloading:
    # the file itself, .part/.ytdl/-FragN pieces, and the merger's <title>.temp.<ext>
    paths = set(glob.glob(glob.escape(name) + '*'))
    merged = _FORMAT_SUFFIX_RE.sub(r'.temp\1', name)
    if merged != name:
        paths.add(merged)
    return paths


def _remove_partials(filenames):
    pending = set().union(*map(_leftovers, filenames)) if filenames else set()
    for _ in range(10):  # a killed ffmpeg may hold its handles for a moment
        for path in list(pending):
            try:
                os.remove(path)
            except FileNotFoundError:
                pending.discard(path)
            except OSError:
                continue
            else:
                pending.discard(path)
        if not pending:
            return
        time.sleep(0.3)


class ProbeError(Exception):
    def __init__(self, message, hint=None):
        super().__init__(message)
        self.message = message
        self.hint = hint


def probe(url, cookies_browser, *, cmd=YTDLP_CMD, timeout=60):
    args = ['-J', '--flat-playlist', '--no-warnings']
    if cookies_browser:
        args += ['--cookies-from-browser', cookies_browser]
    proc = _popen([*cmd, *args, url], REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc.pid)
        proc.communicate()
        raise ProbeError(f'解析超时（{timeout:g} 秒），可以重试')
    text = (out + err).decode('utf-8', 'replace')
    if proc.returncode != 0:
        errors = [line for line in text.splitlines() if 'ERROR' in line]
        message = errors[-1] if errors else (text.strip().splitlines() or ['解析失败'])[-1]
        raise ProbeError(message, explain_error(text))
    info = json.loads(out.decode('utf-8'))
    entries = info.get('entries')
    return {
        'title': info.get('title'),
        'uploader': info.get('uploader'),
        'duration': info.get('duration'),
        'thumbnail': info.get('thumbnail') or _first_thumbnail(info),
        'entries': None if entries is None else [
            {'index': i, 'title': e.get('title'), 'duration': e.get('duration')}
            for i, e in enumerate(entries, 1)],
    }


def _first_thumbnail(info):
    thumbs = info.get('thumbnails') or []
    return thumbs[-1].get('url') if thumbs else None
