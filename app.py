import subprocess, sys, os, threading, webbrowser, json, queue, shutil, time, csv, io, static_ffmpeg, requests
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, render_template, request, Response, jsonify
from downloader import Downloader, getOutputDir

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
    
def install(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", pkg])

if not getattr(sys, 'frozen', False):
    for pkg in ["flask", "yt-dlp", "static-ffmpeg", "yt-dlp-ejs", "mutagen", "requests", "musicbrainzngs"]:
        try:
            __import__(pkg.replace("-", "_"))
        except ImportError:
            print(f"Installing {pkg}...")
            install(pkg)

static_ffmpeg.add_paths()

app = Flask(__name__)
downloader = Downloader()
_queues: dict[str, queue.Queue] = {}
_executor = ThreadPoolExecutor(max_workers=4)

SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".plumm_downloader.json")
PLUM_DIR = os.path.expanduser("~/Music/Plum")

def get_queue(session_id):
    if session_id not in _queues:
        _queues[session_id] = queue.Queue()
    return _queues[session_id]

def send_event(session_id, event):
    get_queue(session_id).put(json.dumps(event))

def load_settings():
    try:
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def save_settings(data):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(data, f)

def parse_exportify_csv(text: str) -> list[dict]:
    tracks = []
    text = text.lstrip('\ufeff').lstrip('\xef\xbb\xbf')
    try:
        text = text.encode('latin-1').decode('utf-8')
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass

    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        title = (row.get('Track Name') or '').strip()
        artist = (row.get('Artist Name(s)') or '').strip()
        album = (row.get('Album Name') or '').strip()
        art_url = (row.get('Album Image URL') or '').strip()
 
        if ',' in artist:
            artist = artist.split(',')[0].strip()

        if title:
            tracks.append({'title': title, 'artist': artist, 'album': album, 'art_url': art_url})
    return tracks

def _unique_playlist_name(base_name: str, directory: str) -> str:
    if not os.path.exists(os.path.join(directory, f"{base_name}.plumm")):
        return base_name
    counter = 2
    while os.path.exists(os.path.join(directory, f"{base_name} ({counter}).plumm")):
        counter += 1
    return f"{base_name} ({counter})"
 
def fetch_spotify_cover(playlist_url: str) -> str | None:
    try:
        resp = requests.get('https://open.spotify.com/oembed', params={'url': playlist_url}, timeout=8, headers={'User-Agent': 'Mozilla/5.0'})
        if resp.status_code == 200:
            return resp.json().get('thumbnail_url')
    except Exception as e:
        print(f"oEmbed Error: {e}")
    return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/search')
def search():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'results': []})
    results = downloader.search(query)
    return jsonify({'results': results})

@app.route('/api/download', methods=['POST'])
def download():
    data = request.json
    session_id = data.get('session_id', 'default')
    video_id = data.get('video_id')
    title = data.get('title', 'Unknown')
    artist = data.get('artist', 'Unknown')
    fmt = data.get('format', 'm4a')
    album = data.get('album', '')
    art_url = data.get('art_url', '')
    genre = data.get('genre', '')

    if not video_id:
        return jsonify({'status': 'error', 'message': 'Missing video_id'}), 400
    
    def run():
        def on_progress(p):
            send_event(session_id, {'type': 'progress', 'video_id': video_id, 'progress': p})

        success = downloader.download(video_id=video_id, title=title, artist=artist, fmt=fmt, on_progress=on_progress, album=album, art_url=art_url, genre=genre)
        send_event(session_id, {'type': 'done', 'video_id': video_id, 'success': success})
    
    _executor.submit(run)
    return jsonify({'status': 'started'})

@app.route('/api/batch', methods=['POST'])
def batch():
    data = request.json
    session_id = data.get('session_id', 'default')
    tracks = data.get('tracks', [])
    fmt = data.get('format', 'm4a')
    
    def run():
        output_dir = getOutputDir()
        seen = set()

        for track in tracks:
            title = track.get('title', '').strip()
            artist = track.get('artist', '').strip()
            album = track.get('album', '')
            art_url = track.get('art_url', '')
            genre = track.get('genre', '')
            key = f"{title.lower()}_{artist.lower()}"
            if key in seen:
                send_event(session_id, {
                    'type': 'batch_done', 'title': title, 'artist': artist,
                    'success': True, 'skipped': True, 'skip_reason': 'Duplicate',
                })
                continue
            seen.add(key)

            safe_title = downloader._sanitize(title)
            safe_artist = downloader._sanitize(artist)
            filename_m4a = os.path.join(output_dir, f"{safe_artist} - {safe_title}.m4a")
            filename_mp3 = os.path.join(output_dir, f"{safe_artist} - {safe_title}.mp3")
            if os.path.exists(filename_m4a) or os.path.exists(filename_mp3):
                send_event(session_id, {
                    'type': 'batch_done', 'title': title, 'artist': artist,
                    'success': True, 'skipped': True, 'skip_reason': 'Already downloaded'
                })
                continue

            send_event(session_id, {'type': 'batch_searching', 'title': title, 'artist': artist})

            result = downloader.search(f"{title} {artist}")
            if not result:
                send_event(session_id, {
                    'type': 'batch_error', 'title': title, 'artist': artist,
                    'error': 'No match found on YouTube'
                })
                time.sleep(1)
                continue

            best = result[0]

            send_event(session_id, {
                'type': 'batch_downloading', 'title': title, 'artist': artist,
                'video_id': best['video_id']
            })

            def on_progress(p, t=title, a=artist):
                send_event(session_id, {'type': 'batch_progress', 'title': t, 'artist': a, 'progress': p})

            success = downloader.download(video_id=best['video_id'], title=title, artist=artist, fmt=fmt, on_progress=on_progress, album=album, art_url=art_url, genre=genre)
            send_event(session_id, {
                'type': 'batch_done', 'title': title, 'artist': artist,
                'success': success, 'skipped': False, 'skip_reason': None
            })
            time.sleep(2)

        send_event(session_id, {'type': 'batch_complete'})
        _queues.pop(session_id, None)
    
    _executor.submit(run)
    return jsonify({'status': 'started'})

@app.route('/api/events/<session_id>')
def events(session_id):
    q = get_queue(session_id)
    def stream():
        while True:
            try:
                msg = q.get(timeout=30)
                yield f"data: {msg}\n\n"
            except queue.Empty:
                yield 'data: {"type":"ping"}\n\n'

    return Response(stream(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
 
@app.route('/api/setup/status')
def setup_status():
    settings = load_settings()
    return jsonify({'done': bool(settings.get('method'))})

@app.route('/api/setup/cookies', methods=['POST'])
def setup_cookies():
    file = request.files.get('file')
    if not file:
        return jsonify({'ok': False, 'error': 'No file provided'}), 400
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > 10 * 1024 * 1024:
        return jsonify({'ok': False, 'error': 'File too large (max 10MB)'}), 400
    header = file.read(16).decode('utf-8', errors='ignore')
    file.seek(0)
    if 'Netscape HTTP' not in header:
        return jsonify({'ok': False, 'error': 'Not a valid Netscape cookies file'}), 400
    save_dir = os.path.join(os.path.expanduser("~"), ".plumm")
    os.makedirs(save_dir, exist_ok=True)
    path = os.path.join(save_dir, 'cookies.txt')
    file.save(path)
    return jsonify({'ok': True, 'path': path})

@app.route('/api/spotify/csv', methods=['POST'])
def spotify_csv():
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'No file uploaded'}), 400
    try:
        raw = file.read()
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = raw.decode('latin-1')
        tracks = parse_exportify_csv(text)
        if not tracks:
            return jsonify({'error': 'No tracks found in CSV'}), 400
        return jsonify({'tracks': tracks})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route("/api/export_playlist", methods=["POST"])
def export_playlist():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    if not f.filename.endswith(".csv"):
        return jsonify({"error": "Must be a .csv file"}), 400

    playlist_name = os.path.splitext(f.filename)[0].replace("_", " ").strip()
    playlist_name = ' '.join(w if w[0].isupper() else w.capitalize() for w in playlist_name.split()) if playlist_name else 'Spotify Playlist'
    playlist_url = request.form.get("playlist_url", "").strip()

    raw = f.read()
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('latin-1')

    tracks = parse_exportify_csv(text)
    if not tracks:
        return jsonify({"error": "No tracks found in CSV"}), 400

    cover_url = None
    if playlist_url:
        cover_url = fetch_spotify_cover(playlist_url)
    if not cover_url and tracks:
        cover_url = tracks[0].get('art_url') or None

    songs = [{'title': t['title'], 'artist': t['artist']} for t in tracks]

    playlist = {
        "name": playlist_name,
        "description": None,
        "cover_url": cover_url,
        "songs": songs,
    }

    os.makedirs(PLUM_DIR, exist_ok=True)
    safe_name = playlist_name.replace("/", "_").replace("\\", "_")
    final_name = _unique_playlist_name(safe_name, PLUM_DIR)
    if final_name != safe_name:
        playlist['name'] = final_name

    out_path = os.path.join(PLUM_DIR, f"{final_name}.plumm")
    with open(out_path, "w", encoding="utf-8") as out:
        json.dump(playlist, out, ensure_ascii=False, indent=2)

    return jsonify({"success": True, "message": "Playlist saved to PLUMM folder"})
    
# ─── YouTube playlist routes ──────────────────────────────────────────────────

@app.route('/api/youtube/playlist/extract', methods=['POST'])
def youtube_playlist_extract():
    data = request.json
    url = (data.get('url') or '').strip()
    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    try:
        result = downloader.extract_youtube_playlist(url)
        if result.get('error') and not result.get('tracks'):
            return jsonify({'error': result['error']}), 400
        return jsonify(result)
    except Exception as e:
        print(f"YouTube playlist extract error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/youtube/playlist/export', methods=['POST'])
def youtube_playlist_export():
    data = request.json
    name = (data.get('name') or 'YouTube Playlist').strip() or "Playlist"
    cover_url = data.get('cover_url', '')
    tracks = data.get('tracks', [])
    
    songs = [{'title': t.get('title', ''), 'artist': t.get('artist', '')} for t in tracks]
    
    playlist = {
        'name': name,
        'description': '',
        'cover_url': cover_url,
        'songs': songs,
    }
    
    os.makedirs(PLUM_DIR, exist_ok=True)
    safe_name = name.replace('/', '_').replace('\\', '_')
    final_name = _unique_playlist_name(safe_name, PLUM_DIR)

    out_path = os.path.join(PLUM_DIR, f"{final_name}.plumm")
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(playlist, f, ensure_ascii=False, indent=2)
    
    return jsonify({"success": True, "message": "Playlist saved to PLUMM folder"})
 
# ─── Setup routes ─────────────────────────────────────────────────────────────

@app.route('/api/setup/save', methods=['POST'])
def setup_save():
    data = request.json
    save_settings(data)
    return jsonify({'ok': True})

@app.route('/api/setup/reset', methods=['POST'])
def setup_reset():
    settings = load_settings()
    settings.pop('method', None)
    save_settings(settings)
    return jsonify({'ok': True})

def open_browser():
    time.sleep(1)
    webbrowser.open('http://localhost:7823')

if __name__ == '__main__':
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(port=7823, debug=False, threaded=True)
