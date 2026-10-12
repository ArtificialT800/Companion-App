import os, sys, time, socket, threading, webbrowser, logging
from filelock import FileLock, Timeout

PORT = 7823
LOCK_PATH = os.path.join(os.path.expanduser("~"), ".plumm", "plum.lock")
CLOSE_GRACE = 6.0
STALE_AFTER = 150.0
NO_CLIENT_TIMEOUT = 180.0
TICK = 1.0
SUSPEND_GAP = 10.0
_log = logging.getLogger("plum.lifecycle")
_lock = None
_state_lock = threading.Lock()
_clients = {}
_closing = {}
_jobs = 0
_had_client = False
_started = time.time()

class _QuietHeartbeat(logging.Filter):
    def filter(self, record):
        return "/api/lifecycle/heartbeat" not in record.getMessage()

def acquire_instance():
    global _lock
    try:
        os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
        lock = FileLock(LOCK_PATH)
        lock.acquire(timeout=0)
    except Timeout:
        return False
    except Exception:
        _log.exception("instance lock unavailable, continuing without it")
        return True
    _lock = lock
    return True

def server_is_up():
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=0.5):
            return True
    except OSError:
        return False

def hand_off_to_running_instance():
    if server_is_up():
        _log.info("running instance is serving, opening a tab for it")
        webbrowser.open(f"http://localhost:{PORT}")
    else:
        _log.info("running instance is still starting, it will open the browser itself")

def job_begin():
    global _jobs
    with _state_lock:
        _jobs += 1

def job_end():
    global _jobs
    with _state_lock:
        _jobs = max(0, _jobs - 1)

def _touch(cid):
    global _had_client
    with _state_lock:
        if cid not in _clients:
            _log.info("tab connected: %s (%d open)", cid, len(_clients) + 1)
        _clients[cid] = time.time()
        _closing.pop(cid, None)
        _had_client = True

def _mark_closing(cid):
    with _state_lock:
        if cid in _clients:
            _closing[cid] = time.time()

def register(app):
    from flask import request
    logging.getLogger("werkzeug").addFilter(_QuietHeartbeat())

    @app.route("/api/lifecycle/heartbeat", methods=["POST"])
    def lifecycle_heartbeat():
        _touch(request.get_data(as_text=True).strip()[:64] or "anon")
        return "", 204

    @app.route("/api/lifecycle/closing", methods=["POST"])
    def lifecycle_closing():
        _mark_closing(request.get_data(as_text=True).strip()[:64] or "anon")
        return "", 204

def exit_now(reason):
    _log.info("exiting: %s", reason)
    logging.shutdown()
    os._exit(0)

def _watch(on_exit):
    last_tick = time.time()
    waiting_logged = False
    while True:
        time.sleep(TICK)
        now = time.time()
        gap = now - last_tick
        last_tick = now
        with _state_lock:
            if gap > SUSPEND_GAP:
                _log.info("loop gap of %.0f s (sleep or suspend), refreshing tab timers", gap)
                for cid in _clients:
                    _clients[cid] = now
                for cid in _closing:
                    _closing[cid] = now
            for cid in list(_clients):
                closed = cid in _closing and now - _closing[cid] > CLOSE_GRACE
                stale = now - _clients[cid] > STALE_AFTER
                if closed or stale:
                    _log.info("tab gone: %s (%s)", cid, "closed" if closed else "no heartbeat")
                    del _clients[cid]
                    _closing.pop(cid, None)
            empty = not _clients
            jobs = _jobs
            had_client = _had_client
        if not empty:
            waiting_logged = False
            continue
        if had_client:
            reason = "all tabs closed"
        elif now - _started > NO_CLIENT_TIMEOUT:
            reason = "no tab ever connected"
        else:
            continue
        if jobs > 0:
            if not waiting_logged:
                _log.info("no tabs open but %d job(s) still running, waiting for them", jobs)
                waiting_logged = True
            continue
        on_exit(reason)
        return

def start_watchdog(on_exit=exit_now):
    threading.Thread(target=_watch, args=(on_exit,), name="lifecycle", daemon=True).start()