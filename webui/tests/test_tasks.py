import subprocess
import sys
import textwrap
import time

import pytest

from webui.tasks import ProbeError, TaskManager, probe


def fake(tmp_path, body, name='fake.py'):
    f = tmp_path / name
    f.write_text(textwrap.dedent(body), encoding='utf-8')
    return [sys.executable, str(f)]


def wait_done(task, seconds=10):
    end = time.time() + seconds
    while task.status == 'running' and time.time() < end:
        time.sleep(0.05)


def start(cmd, tmp_path):
    manager = TaskManager(cmd=cmd, cwd=str(tmp_path))
    return manager, manager.start({}, ['https://x'], downloads_dir=str(tmp_path), ffmpeg_path=None)


def test_progress_title_file_chinese(tmp_path):
    cmd = fake(tmp_path, '''
        print('WEBUI_TITLE 一站式创作Agent', flush=True)
        print('WEBUI_PROGRESS {"status":"downloading","downloaded_bytes":1,"total_bytes":2}', flush=True)
        print('WEBUI_FILE D:/dl/秋芝.mp4', flush=True)
    ''')
    _, t = start(cmd, tmp_path)
    wait_done(t)
    assert t.status == 'finished' and t.title == '一站式创作Agent'
    assert t.files == ['D:/dl/秋芝.mp4'] and t.progress['percent'] == 50.0
    assert [e['i'] for e in t.events] == list(range(len(t.events)))
    assert t.events[-1] == {'i': len(t.events) - 1, 'type': 'status', 'status': 'finished'}


def test_wait_events_returns_from_index(tmp_path):
    cmd = fake(tmp_path, '''
        print('a', flush=True)
        print('b', flush=True)
    ''')
    _, t = start(cmd, tmp_path)
    wait_done(t)
    assert [e.get('text') for e in t.wait_events(1, timeout=0.1)][:1] == ['b']
    assert t.wait_events(len(t.events), timeout=0.1) == []


def test_error_exit_sets_hint(tmp_path):
    cmd = fake(tmp_path, '''
        import sys
        print("ERROR: Unsupported URL: https://x", flush=True)
        sys.exit(1)
    ''')
    _, t = start(cmd, tmp_path)
    wait_done(t)
    assert t.status == 'error' and '不支持' in t.error_hint
    assert t.to_dict()['error_hint'] == t.error_hint


def test_cancel_kills_tree_and_cleans_part(tmp_path):
    marker = tmp_path / 'child.pid'
    part = tmp_path / 'v.mp4.part'
    cmd = fake(tmp_path, f'''
        import json, subprocess, sys, time
        c = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        open(r"{marker}", "w").write(str(c.pid))
        open(r"{part}", "w").write("x")
        print("WEBUI_PROGRESS " + json.dumps({{"status": "downloading", "downloaded_bytes": 1, "filename": r"{part}"}}), flush=True)
        time.sleep(60)
    ''')
    manager, t = start(cmd, tmp_path)
    end = time.time() + 10
    while not (marker.exists() and t.progress) and time.time() < end:
        time.sleep(0.05)
    assert manager.cancel(t.id)
    wait_done(t)
    assert t.status == 'cancelled' and not part.exists()
    child = int(marker.read_text())
    out = subprocess.run(['tasklist', '/FI', f'PID eq {child}'], capture_output=True, text=True).stdout
    assert str(child) not in out


def test_manager_get_list_cancel_unknown(tmp_path):
    manager, t = start(fake(tmp_path, 'print(1)'), tmp_path)
    assert manager.get(t.id) is t and manager.get('nope') is None
    assert manager.list() == [t]
    assert manager.cancel('nope') is False


def test_probe_parses_json(tmp_path):
    cmd = fake(tmp_path, '''
        import json
        print(json.dumps({"title": "合集", "uploader": "u", "duration": None, "thumbnail": None,
              "entries": [{"title": "一", "duration": 10}, {"title": "二", "duration": 20}]}, ensure_ascii=False))
    ''')
    r = probe('https://x', None, cmd=cmd)
    assert r['title'] == '合集' and [e['index'] for e in r['entries']] == [1, 2]
    assert r['entries'][0]['title'] == '一'


def test_probe_error_and_timeout(tmp_path):
    bad = fake(tmp_path, '''
        import sys
        print("ERROR: HTTP Error 403: Forbidden")
        sys.exit(1)
    ''', 'bad.py')
    with pytest.raises(ProbeError) as e:
        probe('https://x', 'edge', cmd=bad)
    assert 'Cookie' in e.value.hint and '403' in e.value.message
    slow = fake(tmp_path, 'import time; time.sleep(30)', 'slow.py')
    with pytest.raises(ProbeError) as e:
        probe('https://x', None, cmd=slow, timeout=1)
    assert '超时' in e.value.message


def test_cancel_removes_merge_and_fragment_leftovers(tmp_path):
    names = ['t.f1.mp4', 't.f2.m4a.part', 't.f2.m4a.part-Frag3', 't.f2.m4a.ytdl', 't.temp.mp4']
    keep = tmp_path / 'old.mp4'
    keep.write_text('x')
    marker = tmp_path / 'ready'
    cmd = fake(tmp_path, f'''
        import json, os, time
        d = r"{tmp_path}"
        for n in {names!r}:
            open(os.path.join(d, n), "w").write("x")
        def p(status, name):
            print("WEBUI_PROGRESS " + json.dumps({{"status": status, "downloaded_bytes": 1, "filename": os.path.join(d, name)}}), flush=True)
        p("finished", "old.mp4")
        p("downloading", "t.f1.mp4")
        p("downloading", "t.f2.m4a")
        open(r"{marker}", "w").write("1")
        time.sleep(60)
    ''')
    manager, t = start(cmd, tmp_path)
    end = time.time() + 10
    while not (marker.exists() and len(t.events) >= 3) and time.time() < end:
        time.sleep(0.05)
    assert manager.cancel(t.id)
    wait_done(t)
    assert t.status == 'cancelled'
    assert [n for n in names if (tmp_path / n).exists()] == []
    assert keep.exists()
