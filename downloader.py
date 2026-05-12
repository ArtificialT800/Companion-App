import os, re, json, shutil, yt_dlp, time, requests, musicbrainzngs, difflib, threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from mutagen.mp4 import MP4, MP4Cover
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB

musicbrainzngs.set_useragent('PlumDownloader', '1.0', 'plum-downloader-app')
musicbrainzngs.set_rate_limit(limit_or_interval=1.0, new_requests=1)

_itunes_session = requests.Session()
_itunes_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (compatible; PlumDownloader/1.0)'
})

_deezer_session = requests.Session()
_deezer_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
})

_last_itunes_call: float = 0.0
_ITUNES_MIN_INTERVAL = 3.2
_itunes_lock = threading.Lock()

def getOutputDir():
    home = os.path.expanduser("~")
    path = os.path.join(home, "Music", "Plum")
    os.makedirs(path, exist_ok=True)
    return path

def _clean_for_search(title: str) -> str:
    """Cleans a YouTube title for search or metadata use."""
    patterns = [
        r'\(official\s*(music\s*)?video\)', r'\(official\s*audio\)',
        r'\(official\s*lyric\s*video\)', r'\(lyrics?\s*video\)',
        r'\(lyrics?\s*\+\s*chords?\)', r'\(lyrics?\)', r'\(audio\)',
        r'\(hd\)', r'\(hq\)', r'\(visuali[sz]er\)', r'\(live.*?\)',
        r'\(.*?version\)', r'\[official\s*(music\s*)?video\]',
        r'\[official\s*audio\]', r'\[lyrics?\]', r'\[audio\]',
        r'\[hd\]', r'\[hq\]', r'\|.*$', r'//.*$',
        r'ft\.?\s+\S+', r'feat\.?\s+\S+',
    ]
    result = title
    for p in patterns:
        result = re.sub(p, '', result, flags=re.IGNORECASE)
    return result.strip(' -–-')

def _artist_match(searched: str, returned: str) -> bool:
    stop = {'the', 'a', 'an', 'and', '&', 'feat', 'ft', 'vs', 'x'}
    s_words = {w.lower() for w in re.split(r'\W+', searched) if len(w) > 2 and w.lower() not in stop}
    r_words = {w.lower() for w in re.split(r'\W+', returned) if len(w) > 2 and w.lower() not in stop}
    if not s_words:
        return True
    return bool(s_words & r_words)

# ─── Deezer ──────────────────────────────────────────────────────────────────

def _normalize_for_match(s: str) -> str:
    s = s.lower()
    s = re.sub(r'\s*[\(\[][^\)\]]*[\)\]]', '', s)
    s = re.sub(r'\s*-\s*(official|video|audio|lyrics|hd|4k|mv|m/v|music video).*$', '', s)
    s = re.sub(r'[^\w\s]', '', s)
    return re.sub(r'\s+', ' ', s).strip()

def _title_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _normalize_for_match(a), _normalize_for_match(b)).ratio()

def _search_deezer(query: str) -> list[dict]:
    try:
        resp = _deezer_session.get('https://api.deezer.com/search', params={'q': query, 'limit': 8}, timeout=5)
        if resp.status_code != 200:
            return []
        data = resp.json().get('data', [])
        results = []
        for track in data:
            md5 = track.get('md5_image', '')
            art = (f'https://cdns-images.dzcdn.net/images/cover/{md5}/1000x1000-000000-80-0-0.jpg' if md5 else '')
            results.append({
                'title': track.get('title', ''),
                'artist': track.get('artist', {}).get('name', ''),
                'album': track.get('album', {}).get('title', ''),
                'art_url': art,
                'duration': track.get('duration', 0),
            })
        return results
    except Exception as e:
        print(f'Deezer search error: {e}')
        return []

def _enrich_with_deezer(query: str, youtube_results: list[dict]) -> list[dict]:
    deezer_tracks = _search_deezer(query)
    if not deezer_tracks:
        return youtube_results
    enriched = []
    for yt in youtube_results:
        yt_title = yt.get('title', '')
        yt_duration = yt.get('duration') or 0
        best_match = None
        best_score = 0.0
        for dz in deezer_tracks:
            title_score = _title_similarity(yt_title, dz['title'])
            duration_ok = (
                yt_duration == 0 or
                dz['duration'] == 0 or
                abs(yt_duration - dz['duration']) <= 15
            )
            score = title_score if duration_ok else title_score * 0.6
            if score > best_score:
                best_score = score
                best_match = dz
        if best_match and best_score >= 0.55:
            enriched.append({
                **yt,
                'title':     best_match['title'],
                'artist':    best_match['artist'],
                'album':     best_match['album'],
                'art_url':   best_match['art_url'],
                'thumbnail': best_match['art_url'] or yt.get('thumbnail', ''),
            })
        else:
            enriched.append(yt)
    return enriched

# ─── iTunes ───────────────────────────────────────────────────────────────────

@lru_cache(maxsize=256)
def _fetch_metadata_itunes(artist: str, title: str) -> dict:
    global _last_itunes_call
    
    clean_title = _clean_for_search(title)
    empty = {'genre': '', 'album': '', 'art_url': '', 'artist': '', 'title': ''}
    
    def _query(term: str) -> dict:
        global _last_itunes_call
        with _itunes_lock:
            elapsed = time.time() - _last_itunes_call
            if elapsed < _ITUNES_MIN_INTERVAL:
                time.sleep(_ITUNES_MIN_INTERVAL - elapsed)
            _last_itunes_call = time.time()
        try:
            url = (
                'https://itunes.apple.com/search'
                f'?term={requests.utils.quote(term)}'
                '&entity=musicTrack&limit=5&media=music'
            )
            resp = _itunes_session.get(url, timeout=8)
            if resp.status_code != 200:
                return {}
            return resp.json()
        except Exception as e:
            print(f'iTunes fetch error: {e}')
            return {}
    
    def _extract(data: dict, require_artist_match: bool) -> dict | None:
        for result in data.get('results', []):
            returned_artist = result.get('artistName', '')
            if require_artist_match and not _artist_match(artist, returned_artist):
                continue
            genre      = result.get('primaryGenreName', '')
            album      = result.get('collectionName', '')
            art_url    = result.get('artworkUrl100', '').replace('100x100bb', '1200x1200bb')
            track_name = result.get('trackName', '')
            if genre or album or art_url:
                print(f"iTunes match ({'strict' if require_artist_match else 'title-only'}): "
                      f"{genre} / {album} (via '{returned_artist}')")
                return {
                    'genre':   genre,
                    'album':   album,
                    'art_url': art_url,
                    'artist':  returned_artist,
                    'title':   track_name,
                }
        return None
    
    # Pass 1 - artist + title, strict artist match
    query1 = f"{clean_title} {artist}".strip()
    result = _extract(_query(query1), require_artist_match=True)
    if result:
        return result
    
    # Pass 2 - title only, no artist match required
    print(f"iTunes strict miss for '{title}' - retrying title-only...")
    result = _extract(_query(clean_title), require_artist_match=False)
    if result:
        return result
    
    return empty

# ─── MusicBrainz ─────────────────────────────────────────────────────────────

def _fetch_genre_musicbrainz(artist: str, title: str) -> str | None:
    try:
        clean_title = _clean_for_search(title)

        def _search(recording_query, artist_query=None) -> str | None:
            kwargs = {'recording': recording_query, 'limit': 5}
            if artist_query:
                kwargs['artist'] = artist_query
            result = musicbrainzngs.search_recordings(**kwargs)
            for rec in result.get('recording-list', []):
                tags = rec.get('tag-list', [])
                if tags:
                    best = sorted(tags, key=lambda t: int(t.get('count', 0)), reverse=True)
                    genre = best[0].get('name', '').strip().title()
                    if genre:
                        return genre
            return None

        genre = _search(clean_title, artist)
        if genre:
            print(f"MusicBrainz genre: {genre}")
            return genre

        print(f"MusicBrainz strict miss for '{title}' - retrying title-only...")
        genre = _search(clean_title)
        if genre:
            print(f"MusicBrainz genre (title-only): {genre}")
            return genre

        return None
    except Exception as e:
        print(f'MusicBrainz genre fetch error: {e}')
        return None

def fetch_track_metadata(artist: str, title: str) -> dict:
    """iTunes -> MusicBrainz (genre fallback) -> empty. Returns {genre, album, art_url, artist, title}"""
    meta = _fetch_metadata_itunes(artist, title)
    if meta['genre']:
        return meta
    print(f"iTunes miss for '{title}' - trying MusicBrainz for genre...")
    genre = _fetch_genre_musicbrainz(artist, title)
    return {
        'genre': genre or '',
        'album': meta['album'],
        'art_url': meta['art_url'],
        'artist': meta['artist'],
        'title': meta['title'],
    }

# ─── Downloader class ─────────────────────────────────────────────────────────

class Downloader:
    def __init__(self):
        self._cookie_opts_cache: dict | None = None
        self._js_opts_cache: dict | None = None

    def _get_cookie_opts(self) -> dict:
        if self._cookie_opts_cache is not None:
            return self._cookie_opts_cache
        result = {}
        try:
            settings_path = os.path.join(os.path.expanduser("~"), ".plumm_downloader.json")
            with open(settings_path) as f:
                settings = json.load(f)
            method = settings.get('method')
            if method == 'a':
                cookies_path = settings.get('cookies_path')
                if cookies_path and os.path.exists(cookies_path):
                    result = {'cookiefile': cookies_path}
                else:
                    print("Cookies file missing or path wrong")
            elif method == 'b':
                profile = settings.get('firefox_profile', '').strip()
                if profile:
                    result = {'cookiesfrombrowser': ('firefox', profile, None, None)}
                else:
                    print("No firefox profile path saved")
        except Exception as e:
            print(f"Settings error: {e}")
        self._cookie_opts_cache = result
        return result

    def _get_js_opts(self) -> dict:
        if self._js_opts_cache is not None:
            return self._js_opts_cache
        deno = shutil.which("deno")
        if not deno:
            possible = [
                os.path.expandvars(r"%USERPROFILE%\.deno\bin\deno.exe"),
                os.path.expanduser("~/.deno/bin/deno"),
            ]
            for p in possible:
                if os.path.exists(p):
                    deno = p
                    break
        if deno:
            self._js_opts_cache = {
                "js_runtimes": {"deno": {"path": deno}},
                "remote_components": {"ejs": {"source": "github"}},
            }
        else:
            print("ERROR: Deno not found")
            self._js_opts_cache = {}
        return self._js_opts_cache

    def _clean_title(self, title: str) -> str:
        return _clean_for_search(title)
    
    def _parse_youtube_title_artist(self, raw_title: str, channel: str) -> tuple[str, str]:
        cleaned = self._clean_title(raw_title)

        if ' - ' in cleaned:
            parts = cleaned.split(' - ', 1)
            return parts[1].strip(), parts[0].strip()
 
        # No dash - use full cleaned title, channel as artist placeholder
        return cleaned, channel
    
    def extract_youtube_playlist(self, url: str) -> dict:
        ydl_opts = {
            'extract_flat': True,
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'ignoreerrors': True,
        }
        ydl_opts.update(self._get_cookie_opts())
        ydl_opts.update({
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            },
        })

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            print(f'Playlist extraction error: {e}')
            return {'name': '', 'cover_url': '', 'tracks': [], 'error': str(e)}
 
        if not info:
            return {'name': '', 'cover_url': '', 'tracks': [], 'error': 'Could not extract playlist info'}

        playlist_name = info.get('title', 'YouTube Playlist')
        playlist_cover = info.get('thumbnail', '')
        entries = info.get('entries', [])

        output_dir = getOutputDir()

        valid_entries = [e for e in entries if e]

        def _enrich_entry(entry: dict) -> dict:
            raw_title = entry.get('title', 'Unknown')
            channel = entry.get('channel', entry.get('uploader', ''))
            duration = entry.get('duration', 0) or 0
            thumbnail = entry.get('thumbnail', '')
            video_id = entry.get('id', '')
            title, artist = self._parse_youtube_title_artist(raw_title, channel)
            final_title = title
            final_artist = artist
            final_album = ''
            final_art = thumbnail
            deezer_results = _search_deezer(f"{title} {artist}")
            if deezer_results:
                best = max(deezer_results, key=lambda d: _title_similarity(title, d['title']))
                score = _title_similarity(title, best['title'])
                if duration > 0 and best['duration'] > 0 and abs(duration - best['duration']) > 15:
                    score *= 0.7
                if score >= 0.50:
                    final_title = best['title']
                    final_artist = best['artist']
                    final_album = best['album']
                    final_art = best['art_url'] or thumbnail
            safe_title = self._sanitize(final_title)
            safe_artist = self._sanitize(final_artist)
            fname_base = f"{safe_artist} - {safe_title}" if safe_artist else safe_title
            local_status = 'found' if (
                os.path.exists(os.path.join(output_dir, f"{fname_base}.m4a")) or
                os.path.exists(os.path.join(output_dir, f"{fname_base}.mp3"))
            ) else 'not_found'
            return {
                'video_id': video_id,
                'title': final_title,
                'artist': final_artist,
                'album': final_album,
                'art_url': final_art,
                'duration': duration,
                'local_status': local_status,
            }

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = []
            for entry in valid_entries:
                futures.append(pool.submit(_enrich_entry, entry))
            tracks = []
            for i, future in enumerate(futures):
                tracks.append(future.result())
                if (i + 1) % 3 == 0:
                    time.sleep(0.3)

        return {
            'name': playlist_name,
            'cover_url': playlist_cover,
            'tracks': tracks,
        }
    
    def _write_metadata(self, filepath: str, title: str, artist: str, album: str = '', art_url: str = '', genre: str = '') -> None:
        try:
            art_data = None
            if art_url:
                try:
                    with urllib.request.urlopen(art_url, timeout=10) as r:
                        art_data = r.read()
                    print(f"Album art fetched: {len(art_data)} bytes")
                except Exception as e:
                    print(f"Art fetch error: {e}")

            if filepath.endswith('.m4a'):
                audio = MP4(filepath)
                audio['\xa9nam'] = [title]
                audio['\xa9ART'] = [artist]
                if album:
                    audio['\xa9alb'] = [album]
                if genre:
                    audio['\xa9gen'] = [genre]
                if art_data:
                    audio['covr'] = [MP4Cover(art_data, imageformat=MP4Cover.FORMAT_JPEG)]
                audio.save()

            elif filepath.endswith('.mp3'):
                try:
                    easy = EasyID3(filepath)
                except Exception:
                    easy = EasyID3()
                    easy.save(filepath)
                    easy = EasyID3(filepath)
                easy['title'] = [title]
                easy['artist'] = [artist]
                if album:
                    easy['album'] = [album]
                if genre:
                    easy['genre'] = [genre]
                easy.save()

                if art_data:
                    tags = ID3(filepath)
                    tags.delall('APIC')
                    tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=art_data))
                    tags.save()

            print(f"Metadata written: {artist} - {title} ({album}) [{genre or 'no genre'}]")
        except Exception as e:
            print(f"Metadata write error: {e}")
    
    def search(self, query: str) -> list[dict]:
        is_url = query.startswith("http://") or query.startswith("https://")
        search_query = query if is_url else f"ytsearch8:{query}"

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "skip_download": True,
        }
        ydl_opts.update(self._get_cookie_opts())
        ydl_opts.update({
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            },
            "extractor_args": {
                "youtube": {
                    "player_client": ["web", "android"],
                }
            },
        })
        ydl_opts.update(self._get_js_opts())

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(search_query, download=False)
                entries = info.get("entries", [info]) if "entries" in info else [info]
                results = []
                for e in entries:
                    if not e:
                        continue
                    results.append({
                        "video_id": e.get("id", ""),
                        "title":    e.get("title", "Unknown"),
                        "artist":   e.get("uploader", e.get("channel", "Unknown")),
                        "duration": e.get("duration", 0),
                        "thumbnail": e.get("thumbnail", ""),
                    })
                results = _enrich_with_deezer(query, results)
                return results[:8]
        except Exception as e:
            print(f"Search error: {e}")
            return []
    
    def download(self, video_id: str, title: str, artist: str, fmt: str, on_progress=None, album: str = '', art_url: str = '', genre: str = '') -> bool:
        output_dir = getOutputDir()
        url = f"https://youtube.com/watch?v={video_id}"

        clean_title  = self._clean_title(title)
        clean_artist = artist.strip()
        safe_title   = self._sanitize(clean_title)
        safe_artist  = self._sanitize(clean_artist)
        filename     = f"{safe_artist} - {safe_title}" if safe_artist else safe_title

        def progress_hook(d):
            if d["status"] == "downloading" and on_progress:
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                downloaded = d.get("downloaded_bytes", 0)
                if total > 0:
                    on_progress(round(downloaded / total * 100, 1))
            elif d["status"] == "finished" and on_progress:
                on_progress(100)

        postprocessors = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": fmt,
                "preferredquality": "320" if fmt == "mp3" else "0",
            },
            {
                "key": "FFmpegMetadata",
                "add_metadata": True,
                "add_chapters": False,
            },
        ]

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(output_dir, f"{filename}.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "postprocessors": postprocessors,
            "progress_hooks": [progress_hook],
        }

        ydl_opts.update(self._get_cookie_opts())
        ydl_opts.update({
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            },
            "extractor_args": {
                "youtube": {
                    "player_client": ["web", "android"],
                }
            },
        })
        ydl_opts.update(self._get_js_opts())

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
 
            final_m4a  = os.path.join(output_dir, f"{filename}.m4a")
            final_mp3  = os.path.join(output_dir, f"{filename}.mp3")
            final_path = final_m4a if os.path.exists(final_m4a) else (final_mp3 if os.path.exists(final_mp3) else None)

            if final_path:
                meta             = fetch_track_metadata(clean_artist, clean_title)
                resolved_genre   = genre   or meta['genre']
                resolved_album   = album   or meta['album']
                resolved_art_url = art_url or meta['art_url']
                resolved_artist  = clean_artist
                resolved_title   = clean_title

                if meta['artist']:
                    is_likely_channel = (' ' not in clean_artist or any(s in clean_artist.lower() for s in ['vevo', 'official', 'music', 'records', 'ost', 'topic']))
                    if is_likely_channel:
                        resolved_artist = meta['artist']
                        print(f"Artist corrected: '{clean_artist}' -> '{resolved_artist}'")

                if meta['title'] and resolved_artist != clean_artist:
                    resolved_title = meta['title']

                if resolved_artist != clean_artist or resolved_title != clean_title:
                    ext = '.m4a' if final_path.endswith('.m4a') else '.mp3'
                    new_filename = (f"{self._sanitize(resolved_artist)} - {self._sanitize(resolved_title)}" if resolved_artist else self._sanitize(resolved_title))
                    new_path = os.path.join(output_dir, f"{new_filename}{ext}")
                    try:
                        os.rename(final_path, new_path)
                        final_path = new_path
                        print(f"File renamed -> {new_filename}{ext}")
                    except Exception as e:
                        print(f"Rename failed (non-fatal): {e}")
 
                self._write_metadata(final_path, resolved_title, resolved_artist, resolved_album, resolved_art_url, resolved_genre)

            return final_path is not None
        except Exception as e:
            print(f"Download error: {e}")
            return False
    
    def _sanitize(self, name: str) -> str:
        return name.replace('/', '-').replace('\\', '-').replace(':', '-') \
                   .replace('*', '').replace('?', '').replace('"', '') \
                   .replace('<', '').replace('>', '').replace('|', '').strip()