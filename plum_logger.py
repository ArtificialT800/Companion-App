import sys, os, io, re, time, atexit, logging, platform, tempfile, shutil, threading, faulthandler, importlib
from logging.handlers import RotatingFileHandler

APP_VERSION = "1.1.0"
LOG_DIR = os.path.join(os.path.expanduser("~"), ".plumm", "logs")
LOG_FILE = os.path.join(LOG_DIR, "plum.log")
CRASH_FILE = os.path.join(LOG_DIR, "crash.log")
PROBE_MODULES = ["flask", "werkzeug", "jinja2", "requests", "urllib3", "certifi", "yt_dlp", "yt_dlp_ejs", "mutagen", "musicbrainzngs", "static_ffmpeg"]
_state = {"ready": False, "crash_handle": None, "streams": []}
_busy = threading.local()

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_USER_DIR = re.compile(r"(?<![\w.\-])((?:[a-z]:)?[\\/]{1,2}(?:users|home)[\\/]{1,2})([^\\/\s'\"<>|:*?]+)", re.IGNORECASE)
_default_patterns = []

def _make_patterns(home):
    forms = set()
    if home and home.strip("\\/"):
        for variant in (home, home.replace("\\", "/"), home.replace("/", "\\")):
            forms.add(variant)
            forms.add(variant.replace("\\", "\\\\"))
    return [re.compile(re.escape(form), re.IGNORECASE) for form in sorted(forms, key=len, reverse=True)]

def sanitize(text, home=None):
    if home is None:
        if not _default_patterns:
            _default_patterns.extend(_make_patterns(os.path.expanduser("~")))
        patterns = _default_patterns
    else:
        patterns = _make_patterns(home)
    for pattern in patterns:
        text = pattern.sub("~", text)
    return _USER_DIR.sub(r"\1<USER>", text)

def _scrub_file(path):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                raw = handle.read()
            clean = sanitize(raw)
            if clean != raw:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(clean)
    except OSError:
        pass

class _PlainFormatter(logging.Formatter):
    def format(self, record):
        return sanitize(_ANSI.sub("", super().format(record)))

class _StreamToLog:
    encoding = "utf-8"
    errors = "replace"

    def __init__(self, logger, level):
        self._logger = logger
        self._level = level
        self._buffer = ""
        self._lock = threading.Lock()

    @property
    def buffer(self):
        return self

    def write(self, text):
        if not text:
            return 0
        if isinstance(text, (bytes, bytearray)):
            text = bytes(text).decode("utf-8", "replace")
        if getattr(_busy, "on", False):
            return len(text)
        _busy.on = True
        try:
            with self._lock:
                self._buffer += text
                while "\n" in self._buffer:
                    line, self._buffer = self._buffer.split("\n", 1)
                    line = line.rstrip("\r")
                    if line.strip():
                        self._logger.log(self._level, line)
        finally:
            _busy.on = False
        return len(text)

    def flush(self):
        if getattr(_busy, "on", False):
            return
        _busy.on = True
        try:
            with self._lock:
                if self._buffer.strip():
                    self._logger.log(self._level, self._buffer.rstrip("\r\n"))
                self._buffer = ""
        finally:
            _busy.on = False

    def isatty(self):
        return False

    def writable(self):
        return True

    def fileno(self):
        raise io.UnsupportedOperation("fileno")

class YtdlpLogger:
    def __init__(self):
        self._log = logging.getLogger("plum.ytdlp")

    def debug(self, msg):
        if msg.startswith("[debug] "):
            self._log.debug(msg[8:])
        else:
            self._log.info(msg)

    def info(self, msg):
        self._log.info(msg)

    def warning(self, msg):
        self._log.warning(msg)

    def error(self, msg):
        self._log.error(msg)

def get(name):
    return logging.getLogger("plum." + name)

def setup():
    if _state["ready"]:
        return get("app")
    fmt = _PlainFormatter("%(asctime)s.%(msecs)03d %(levelname)s [%(threadName)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        file_handler = RotatingFileHandler(LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8")
    except OSError:
        file_handler = logging.NullHandler()
    file_handler.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    if not getattr(sys, "frozen", False) and sys.stderr is not None:
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(fmt)
        root.addHandler(console)
    logging.getLogger("plum").setLevel(logging.DEBUG)
    logging.captureWarnings(True)
    out_stream = _StreamToLog(logging.getLogger("plum.stdout"), logging.INFO)
    err_stream = _StreamToLog(logging.getLogger("plum.stderr"), logging.ERROR)
    sys.stdout = out_stream
    sys.stderr = err_stream
    _state["streams"] = [out_stream, err_stream]
    log = get("app")

    def _excepthook(exc_type, exc, tb):
        log.critical("Uncaught exception", exc_info=(exc_type, exc, tb))

    def _thread_excepthook(args):
        name = args.thread.name if args.thread else "unknown"
        log.critical("Uncaught exception in thread %s", name, exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook
    _scrub_file(CRASH_FILE)
    try:
        _state["crash_handle"] = open(CRASH_FILE, "a", encoding="utf-8")
        faulthandler.enable(file=_state["crash_handle"], all_threads=True)
    except Exception:
        log.exception("faulthandler could not be enabled")

    def _on_exit():
        for stream in _state["streams"]:
            stream.flush()
        log.info("process exiting")

    atexit.register(_on_exit)
    _state["ready"] = True
    return log

def log_environment():
    log = get("env")
    log.info("PLUM Downloader %s starting", APP_VERSION)
    log.info("python %s", sys.version.replace("\n", " "))
    log.info("platform %s, machine %s", platform.platform(), platform.machine())
    log.info("frozen=%s, executable=%s", getattr(sys, "frozen", False), sys.executable)
    log.info("bundle dir (_MEIPASS)=%s", getattr(sys, "_MEIPASS", None))
    log.info("cwd=%s, argv=%s", os.getcwd(), sys.argv)
    log.info("home=%s, temp=%s", os.path.expanduser("~"), tempfile.gettempdir())
    log.info("filesystem encoding=%s, stdout encoding=%s", sys.getfilesystemencoding(), getattr(sys.__stdout__, "encoding", None))
    log.info("deno=%s, ffmpeg on PATH=%s", shutil.which("deno"), shutil.which("ffmpeg"))
    try:
        out_dir = os.path.join(os.path.expanduser("~"), "Downloads", "Plum")
        probe_dir = out_dir if os.path.isdir(out_dir) else os.path.expanduser("~")
        usage = shutil.disk_usage(probe_dir)
        log.info("disk free at %s: %.1f GB", probe_dir, usage.free / 1e9)
    except Exception:
        log.exception("disk usage check failed")

def probe_imports():
    log = get("probe")
    for name in PROBE_MODULES:
        started = time.perf_counter()
        try:
            module = importlib.import_module(name)
            version = getattr(module, "__version__", None)
            if version is None and name == "yt_dlp":
                version = importlib.import_module("yt_dlp.version").__version__
            log.info("import ok: %s %s (%.0f ms)", name, version or "?", (time.perf_counter() - started) * 1000)
        except Exception:
            log.exception("import FAILED: %s", name)

def install_ytdlp_logging(yt_dlp_module):
    base = yt_dlp_module.YoutubeDL
    if getattr(base, "_plum_logged", False):
        return

    class LoggedYoutubeDL(base):
        _plum_logged = True

        def __init__(self, params=None, auto_init=True):
            params = dict(params or {})
            params.setdefault("logger", YtdlpLogger())
            super().__init__(params, auto_init)

    yt_dlp_module.YoutubeDL = LoggedYoutubeDL