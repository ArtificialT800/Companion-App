const SESSION_ID = Math.random().toString(36).slice(2);
let searchResults = [];
let playlistTracks = [];
let downloadStatuses = {};
let batchFormat = 'm4a';
let allDownloads = [];
let selectedOption = null;
let cookiesPath = null;
let downloadErrors = {};
let currentCsvFile = null;
let currentPlaylistName = '';

let ytPlaylistTracks = [];
let ytPlaylistName = '';
let ytCoverUrl = '';
let ytBatchFormat = 'm4a';
let ytAllSelected = true;
let ytDownloadStatuses = {};
let ytDownloadErrors = {};
let activeBatchSource = null;

const evtSource = new EventSource(`/api/events/${SESSION_ID}`);
evtSource.onmessage = (e) => {
  const data = JSON.parse(e.data);
  if (data.type === 'ping') return;
  handleEvent(data);
};

function handleEvent(data) {
  switch (data.type) {
    case 'progress':
      updateSearchTrackProgress(data.video_id, data.progress);
      break;
    
    case 'done':
      updateSearchTrackDone(data.video_id, data.success);
      addToDownloads(data.video_id, data.success);
      break;
    
    case 'batch_searching':
      if (activeBatchSource === 'youtube') {
        updateYtBatchTrackFromEvent(data.title, data.artist, 'searching', 0);
      } else {
        updateBatchTrack(data.title, data.artist, 'searching', 0);
      }
      break;

    case 'batch_downloading':
      if (activeBatchSource === 'youtube') {
        updateYtBatchTrackFromEvent(data.title, data.artist, 'downloading', 0);
      } else {
        updateBatchTrack(data.title, data.artist, 'downloading', 0);
      }
      break;

    case 'batch_progress':
      if (activeBatchSource === 'youtube') {
        updateYtBatchTrackFromEvent(data.title, data.artist, 'downloading', data.progress);
      } else {
        updateBatchTrack(data.title, data.artist, 'downloading', data.progress);
      }
      break;

    case 'batch_error': {
      if (activeBatchSource === 'youtube') {
        const ytErrIdx = ytPlaylistTracks.findIndex(t => t.title === data.title && t.artist === data.artist);
        if (ytErrIdx !== -1) ytDownloadErrors[`yt-batch-${ytErrIdx}`] = data.error;
        updateYtBatchTrackFromEvent(data.title, data.artist, 'error', 0);
        updateYtBatchStats();
      } else {
        const spErrIdx = playlistTracks.findIndex(t => t.title === data.title && t.artist === data.artist);
        downloadErrors[`batch-${spErrIdx}`] = data.error;
        updateBatchTrack(data.title, data.artist, 'error', 0);
        updateBatchStats();
      }
      break;
    }

    case 'batch_done': {
      const skipped = data.skipped;
      const skipReason = data.skip_reason || '';
      const finalStatus = skipped ? 'skipped' : (data.success ? 'done' : 'error');
      if (activeBatchSource === 'youtube') {
        if (skipped) {
          const ytSkipIdx = ytPlaylistTracks.findIndex(t => t.title === data.title && t.artist === data.artist);
          if (ytSkipIdx !== -1) ytDownloadErrors[`yt-batch-${ytSkipIdx}`] = skipReason;
        }
        updateYtBatchTrackFromEvent(data.title, data.artist, finalStatus, 100);
        updateYtBatchStats();
      } else {
        if (skipped) {
          const spSkipIdx = playlistTracks.findIndex(t => t.title === data.title && t.artist === data.artist);
          if (spSkipIdx !== -1) downloadErrors[`batch-${spSkipIdx}`] = skipReason;
        }
        updateBatchTrack(data.title, data.artist, finalStatus, 100);
        updateBatchStats();
      }
      if (!skipped) addToDownloads(`${data.title} - ${data.artist}`, data.success);
      break;
    }

    case 'batch_complete': {
      activeBatchSource = null;
      const btn = document.getElementById('download-all-btn');
      const ytBtn = document.getElementById('yt-download-btn');
      if (btn) { btn.disabled = false; btn.textContent = 'Download All'; }
      if (ytBtn) { ytBtn.disabled = false; ytBtn.textContent = 'Download Missing'; }
      showToast('All downloads complete');
      break;
    }
  }
}

//Tab navigation ################################################################

function showTab(name, el) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById(`screen-${name}`).classList.add('active');
  el.classList.add('active');
}

//Playlist source switching ################################################################

function switchPlaylistSource(source) {
  document.getElementById('src-spotify').style.display = source === 'spotify' ? '' : 'none';
  document.getElementById('src-youtube').style.display = source === 'youtube' ? '' : 'none';
  document.getElementById('src-tab-spotify').classList.toggle('active', source === 'spotify');
  document.getElementById('src-tab-youtube').classList.toggle('active', source === 'youtube');
}

//Search ################################################################

let _searchAbortController = null;

async function doSearch() {
  const q = document.getElementById('search-input').value.trim();
  if (!q) return;
  const el = document.getElementById('search-results');
  el.innerHTML = '<div style="color:var(--text3);font-size:13px;padding:16px 0">Searching...</div>';
  if (_searchAbortController) _searchAbortController.abort();
  _searchAbortController = new AbortController();
  try {
    const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`, { signal: _searchAbortController.signal });
    const data = await res.json();
    searchResults = data.results || [];
    renderSearchResults();
  } catch (e) {
    if (e.name !== 'AbortError') {
      el.innerHTML = '<div style="color:var(--text3);font-size:13px;padding:16px 0">Search failed</div>';
    }
  }
}

function renderSearchResults() {
  const el = document.getElementById('search-results');
  if (!searchResults.length) {
    el.innerHTML = '<div style="color:var(--text3);font-size:13px;padding:16px 0">No results found</div>';
    return;
  }
  el.innerHTML = searchResults.map(t => searchTrackCard(t)).join('');
}

function searchTrackCard(t) {
  const key = t.video_id;
  const status = downloadStatuses[key] || 'idle';
  const duration = t.duration ? formatDuration(t.duration) : '';
  const thumb = t.thumbnail ? `<img src="${t.thumbnail}" onerror="this.style.display='none'" alt=""/>` : '🎵';
  const disabled = status !== 'idle' && status !== 'error' ? 'disabled' : '';
  const progressBar = `<div class="progress-bar" id="progbar-${key}" style="display:${status === 'downloading' ? 'block' : 'none'}"><div class="progress-fill" id="prog-${key}"></div></div>`;
  return `<div class="track-card track-card--${status}" id="card-${key}">
<div class="track-thumb">${thumb}</div>
<div class="track-info">
<div class="track-title">${esc(t.title)}</div>
<div class="track-artist">${esc(t.artist)}</div>
${duration ? `<div class="track-duration">${duration}</div>` : ''}
${progressBar}
</div>
<div class="track-actions">
<button class="fmt-btn" onclick="startDownload('${key}','m4a')" ${disabled}>M4A</button>
<button class="fmt-btn" onclick="startDownload('${key}','mp3')" ${disabled}>MP3</button>
<div class="status-icon status-${status}" id="status-${key}">${statusIcon(status)}</div>
</div>
</div>`;
}

async function startDownload(videoId, fmt) {
  const track = searchResults.find(t => t.video_id === videoId);
  if (!track) return;
  downloadStatuses[videoId] = 'downloading';
  const card = document.getElementById(`card-${videoId}`);
  if (card) card.className = 'track-card track-card--downloading';
  const progBar = document.getElementById(`progbar-${videoId}`);
  if (progBar) progBar.style.display = 'block';
  if (card) card.querySelectorAll('.fmt-btn').forEach(b => b.disabled = true);
  updateStatusIcon(videoId, 'downloading');
  await fetch('/api/download', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      session_id: SESSION_ID, video_id: videoId,
      title: track.title, artist: track.artist, format: fmt,
      album: track.album || '', art_url: track.art_url || '',
    }),
  });
}

function updateSearchTrackProgress(videoId, pct) {
  const prog = document.getElementById(`prog-${videoId}`);
  if (prog) prog.style.width = pct + '%';
  updateStatusIcon(videoId, 'downloading');
}

function updateSearchTrackDone(videoId, success) {
  downloadStatuses[videoId] = success ? 'done' : 'error';
  updateStatusIcon(videoId, success ? 'done' : 'error');
  const card = document.getElementById(`card-${videoId}`);
  if (card) card.className = `track-card track-card--${success ? 'done' : 'error'}`;
  const prog = document.getElementById(`prog-${videoId}`);
  if (prog) prog.style.width = '100%';
  if (success) showToast('Downloaded successfully');
}

// ─── Spotify CSV ──────────────────────────────────────────────────────────────

function handleCsvDrop(event) {
  event.preventDefault();
  document.getElementById('drop-zone').classList.remove('drop-zone--hover');
  const file = event.dataTransfer.files[0];
  if (file && file.name.endsWith('.csv')) {
    uploadCsv(file);
  } else {
    showToast('✕ Please drop a .csv file');
  }
}

function handleCsvFile(input) {
  const file = input.files[0];
  if (file) uploadCsv(file);
}

function renderTrackList(tracks, containerId, opts) {
  const el = document.getElementById(containerId);
  el.innerHTML = tracks.map((t, i) => {
    const key = `${opts.keyPrefix}${i}`;
    const status = opts.getStatus(t, key);
    const errMsg = opts.errors[key] || '';
    const checked = opts.isChecked(t) ? 'checked' : '';
    const thumb = opts.thumb ? opts.thumb(t) : '';
    const badge = opts.badge ? opts.badge(t, status) : '';
    const duration = opts.duration ? opts.duration(t) : '';
    return `<div class="track-card track-card--${status}" id="${opts.cardPrefix}${key}">
<input type="checkbox" class="${opts.checkClass}" id="${opts.checkPrefix}${i}" ${checked} style="accent-color:var(--primary);width:16px;height:16px;cursor:pointer;flex-shrink:0;" onchange="${opts.onchange}"/>
${thumb}
<div class="track-info">
<div class="track-title">${esc(t.title)}</div>
<div class="track-artist">${esc(t.artist)}</div>
${badge}
${duration}
${errMsg ? `<div style="font-size:11px;color:var(--red);margin-top:2px">${esc(errMsg)}</div>` : ''}
<div class="progress-bar" id="${opts.progPrefix}${key}" style="display:none"><div class="progress-fill" id="${opts.progFillPrefix}${key}"></div></div>
</div>
<div class="track-actions">
<div class="status-icon status-${status}" id="${opts.statusPrefix}${key}">${statusIcon(status)}</div>
</div>
</div>`;
  }).join('');
  opts.afterRender();
}

function renderPlaylist() {
  renderTrackList(playlistTracks, 'playlist-list', {
    keyPrefix: 'batch-',
    checkPrefix: 'check-',
    checkClass: 'track-check',
    cardPrefix: 'card-',
    progPrefix: 'progbar-',
    progFillPrefix: 'prog-',
    statusPrefix: 'status-',
    errors: downloadErrors,
    getStatus: (t, key) => downloadStatuses[key] || 'idle',
    isChecked: () => true,
    onchange: 'updateSelectAll()',
    afterRender: updateSelectAll,
  });
}

function renderYtPlaylist() {
  renderTrackList(ytPlaylistTracks, 'yt-playlist-list', {
    keyPrefix: 'yt-batch-',
    checkPrefix: 'yt-check-',
    checkClass: 'yt-track-check',
    cardPrefix: 'yt-card-',
    progPrefix: 'yt-progbar-',
    progFillPrefix: 'yt-prog-',
    statusPrefix: 'yt-status-',
    errors: ytDownloadErrors,
    getStatus: (t, key) => ytDownloadStatuses[key] || (t.local_status === 'found' ? 'done' : 'idle'),
    isChecked: (t) => t.local_status !== 'found',
    onchange: 'updateYtSelectAll()',
    thumb: (t) => `<div class="track-thumb">${t.art_url ? `<img src="${esc(t.art_url)}" onerror="this.style.display='none'" alt=""/>` : '🎵'}</div>`,
    badge: (t, status) => {
      if ((status === 'idle' || status === 'done') && t.local_status === 'found')
        return `<span style="font-size:11px;color:var(--green);margin-top:2px">● Already downloaded</span>`;
      if (status === 'idle' && t.local_status === 'not_found')
        return `<span style="font-size:11px;color:var(--orange);margin-top:2px">● Not downloaded</span>`;
      return '';
    },
    duration: (t) => t.duration ? `<div class="track-duration">${formatDuration(t.duration)}</div>` : '',
    afterRender: updateYtSelectAll,
  });
}

function updateBatchTrack(title, artist, status, progress) {
  const idx = playlistTracks.findIndex(t => t.title === title && t.artist === artist);
  if (idx === -1) return;
  const key = `batch-${idx}`;
  downloadStatuses[key] = status;
  updateStatusIcon(key, status);
  const card = document.getElementById(`card-${key}`);
  if (card) card.className = `track-card track-card--${status}`;
  const progBar = document.getElementById(`progbar-${key}`);
  const prog = document.getElementById(`prog-${key}`);
  if (progBar && prog) {
    progBar.style.display = status === 'downloading' ? 'block' : 'none';
    prog.style.width = progress + '%';
  }
}

function updateYtBatchTrackFromEvent(title, artist, status, progress) {
  const idx = ytPlaylistTracks.findIndex(t => t.title === title && t.artist === artist);
  if (idx === -1) return;
  const key = `yt-batch-${idx}`;
  ytDownloadStatuses[key] = status;
  const iconEl = document.getElementById(`yt-status-${key}`);
  if (iconEl) {
    iconEl.className = `status-icon status-${status}`;
    iconEl.innerHTML = statusIcon(status);
  }
  const card = document.getElementById(`yt-card-${key}`);
  if (card) card.className = `track-card track-card--${status}`;
  const progBar = document.getElementById(`yt-progbar-${key}`);
  const prog = document.getElementById(`yt-prog-${key}`);
  if (progBar && prog) {
    progBar.style.display = status === 'downloading' ? 'block' : 'none';
    prog.style.width = progress + '%';
  }
}

function updateBatchStats() {
  const done = Object.entries(downloadStatuses).filter(([k, v]) => k.startsWith('batch-') && v === 'done').length;
  document.getElementById('batch-stats').textContent = `${done}/${playlistTracks.length} downloaded`;
}

function updateSelectAll() {
  const total = playlistTracks.length;
  const checkboxes = document.querySelectorAll('.track-check');
  const checked = Array.from(checkboxes).filter(cb => cb.checked).length;

  const downloadBtn = document.getElementById('download-all-btn');
  if (downloadBtn) {
    downloadBtn.textContent = checked === total ? 'Download All' : `Download Selected (${checked})`;
  }

  const toggleBtn = document.getElementById('select-all-btn');
  if (toggleBtn) {
    toggleBtn.textContent = checked === total ? 'Deselect All' : 'Select All';
  }

  const stats = document.getElementById('batch-stats');
  if (stats) {
    stats.textContent = `${checked}/${total} selected`;
  }
}

function toggleSelectAll() {
  const checkboxes = document.querySelectorAll('.track-check');
  const allChecked = Array.from(checkboxes).every(cb => cb.checked);
  checkboxes.forEach(cb => { cb.checked = !allChecked; });
  updateSelectAll();
}

function getSelectedTracks() {
  return playlistTracks.filter((_, i) => {
    const cb = document.getElementById(`check-${i}`);
    return cb && cb.checked;
  });
}

async function downloadAll() {
  const selected = getSelectedTracks();
  if (!selected.length) { showToast('No songs selected'); return; }
  const btn = document.getElementById('download-all-btn');
  btn.disabled = true;
  btn.textContent = 'Downloading...';
  activeBatchSource = 'spotify';
  await fetch('/api/batch', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({session_id: SESSION_ID, tracks: selected, format: batchFormat}),
  });
}

function setFormat(fmt) {
  batchFormat = fmt;
  document.getElementById('chip-m4a').classList.toggle('active', fmt === 'm4a');
  document.getElementById('chip-mp3').classList.toggle('active', fmt === 'mp3');
}

async function uploadCsv(file) {
  const dz = document.getElementById('drop-zone');
  dz.innerHTML = `<div class="drop-icon"><div class="spinner"></div></div><p class="drop-title">Reading ${esc(file.name)}...</p><p class="drop-hint"></p>`;

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res  = await fetch('/api/spotify/csv', {method: 'POST', body: formData});
    const data = await res.json();
 
    if (data.error) {
      showToast(`✕ ${data.error}`);
      resetDropZone();
      return;
    }

    playlistTracks = data.tracks || [];
    currentCsvFile = file;
    currentPlaylistName = file.name.replace(/\.csv$/i, '').replace(/_/g, ' ');
    Object.keys(downloadStatuses).forEach(k => {
      if (k.startsWith('batch-')) delete downloadStatuses[k];
    });

    dz.innerHTML = `
      <p class="drop-title" style="color:var(--green)">${esc(file.name)}</p>
      <p class="drop-hint">${playlistTracks.length} tracks loaded - click to replace</p>
    `;
    dz.style.borderColor = 'var(--green)';
    dz.style.background  = '#00c85308';

    renderPlaylist();
    document.getElementById('playlist-tracks').style.display = 'block';
    showToast(`Loaded ${playlistTracks.length} tracks`);
 
  } catch (e) {
    showToast('✕ Failed to read CSV');
    resetDropZone();
  }
}

function resetDropZone() {
  const dz = document.getElementById('drop-zone');
  dz.style.borderColor = '';
  dz.style.background  = '';
  dz.innerHTML = `
    <div class="drop-icon"></div>
    <p class="drop-title">Drop your CSV here</p>
    <p class="drop-hint">or click to browse</p>
  `;
}

async function exportToPlumm() {
  if (!currentCsvFile) { showToast('✕ No playlist loaded'); return; }
  
  const btn = document.getElementById('export-plumm-btn');
  btn.disabled = true;
  btn.textContent = 'Exporting...';

  try {
    const formData  = new FormData();
    formData.append('file', currentCsvFile);
    const playlistUrl = document.getElementById('playlist-url-input')?.value.trim() || '';
    if (playlistUrl) formData.append('playlist_url', playlistUrl);

    const res = await fetch('/api/export_playlist', {method: 'POST', body: formData});
    if (!res.ok) {
      const err = await res.json();
      showToast(`✕ ${err.error || 'Export failed'}`);
      return;
    }
    
    await res.json();
    showToast(`"${currentPlaylistName}.plumm saved to PLUM folder`);
  } catch (e) {
    showToast('✕ Export failed');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Export to PLUMM';
  }
}

// ─── YouTube playlist ─────────────────────────────────────────────────────────

async function loadYtPlaylist() {
  const url = document.getElementById('yt-playlist-url').value.trim();
  if (!url) { showToast('✕ Paste a YouTube playlist URL first'); return; }
  
  const btn = document.getElementById('yt-load-btn');
  const statusEl = document.getElementById('yt-load-status');
  const tracksDiv = document.getElementById('yt-playlist-tracks');
  
  btn.disabled = true;
  btn.textContent = 'Loading...';
  statusEl.style.display = 'block';
  statusEl.textContent = 'Extracting playlist - this may take a moment for large playlists...';
  tracksDiv.style.display = 'none';
  
  try {
    const res  = await fetch('/api/youtube/playlist/extract', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url}),
    });
    const data = await res.json();

    if (data.error) {
      statusEl.textContent = `✕ ${data.error}`;
      statusEl.style.color = 'var(--red)';
      showToast(`✕ ${data.error}`);
      return;
    }

    ytPlaylistTracks = data.tracks || [];
    ytPlaylistName = data.name   || 'YouTube Playlist';
    ytCoverUrl = data.cover_url || '';
    ytAllSelected = true;
    ytDownloadStatuses = {};
    ytDownloadErrors = {};
    
    const found    = ytPlaylistTracks.filter(t => t.local_status === 'found').length;
    const notFound = ytPlaylistTracks.length - found;
    
    statusEl.style.color = 'var(--green)';
    statusEl.textContent = `"${ytPlaylistName}" - ${ytPlaylistTracks.length} tracks (${found} already downloaded, ${notFound} missing)`;
    
    renderYtPlaylist();
    tracksDiv.style.display = 'block';
    updateYtBatchStats();
    showToast(`Loaded ${ytPlaylistTracks.length} tracks`);
    
  } catch (e) {
    statusEl.textContent = '✕ Failed to load playlist';
    statusEl.style.color = 'var(--red)';
    showToast('✕ Failed to load playlist');
  } finally {
    btn.disabled    = false;
    btn.textContent = 'Load Playlist';
  }
}

function updateYtBatchStats() {
  const done     = ytPlaylistTracks.filter((t, i) => {
    const key = `yt-batch-${i}`;
    return ytDownloadStatuses[key] === 'done' || t.local_status === 'found';
  }).length;
  const el = document.getElementById('yt-batch-stats');
  if (el) el.textContent = `${done}/${ytPlaylistTracks.length} ready`;
}

function updateYtSelectAll() {
  const total   = ytPlaylistTracks.length;
  const checked = ytPlaylistTracks.filter((_, i) => {
    const cb = document.getElementById(`yt-check-${i}`);
    return cb && cb.checked;
  }).length;
  const btn = document.getElementById('yt-download-btn');
  if (btn) btn.textContent = `Download Missing (${checked} selected)`;
  updateYtBatchStats();
}

function toggleYtSelectAll() {
  ytAllSelected = !ytAllSelected;
  ytPlaylistTracks.forEach((_, i) => {
    const cb = document.getElementById(`yt-check-${i}`);
    if (cb) cb.checked = ytAllSelected;
  });
  document.getElementById('yt-select-all-btn').textContent = ytAllSelected ? 'Deselect All' : 'Select All';
  updateYtSelectAll();
}

function getSelectedYtTracks() {
  return ytPlaylistTracks.filter((t, i) => {
    const cb = document.getElementById(`yt-check-${i}`);
    return cb && cb.checked;
  });
}

async function downloadYtAll() {
  const selected = getSelectedYtTracks();
  if (!selected.length) { showToast('No tracks selected'); return; }

  const btn = document.getElementById('yt-download-btn');
  btn.disabled = true;
  btn.textContent = 'Downloading...';

  activeBatchSource = 'youtube';

  await fetch('/api/batch', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({session_id: SESSION_ID, tracks: selected, format: ytBatchFormat}),
  });
}
 
function setYtFormat(fmt) {
  ytBatchFormat = fmt;
  document.getElementById('yt-chip-m4a').classList.toggle('active', fmt === 'm4a');
  document.getElementById('yt-chip-mp3').classList.toggle('active', fmt === 'mp3');
}
  
async function exportYtToPlumm() {
  if (!ytPlaylistTracks.length) { showToast('✕ No playlist loaded'); return; }
  
  const btn = document.getElementById('yt-export-btn');
  btn.disabled = true;
  btn.textContent = 'Exporting...';
  
  try {
    const res = await fetch('/api/youtube/playlist/export', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        name: ytPlaylistName,
        cover_url: ytCoverUrl,
        tracks: ytPlaylistTracks,
      }),
    });
    
    if (!res.ok) {
      const err = await res.json();
      showToast(`✕ ${err.error || 'Export failed'}`);
      return;
    }

    await res.json();
    showToast(`"${ytPlaylistName}.plumm" saved to Music\\PLUM folder`);
  } catch (e) {
    showToast('✕ Export failed');
  } finally {
    btn.disabled    = false;
    btn.textContent = 'Export to PLUMM';
  }
}

// ─── Downloads tab ────────────────────────────────────────────────────────────

function addToDownloads(label, success) {
  allDownloads.unshift({label, success, time: new Date().toLocaleTimeString()});
  renderDownloads();
}

function renderDownloads() {
  const el = document.getElementById('downloads-list');
  if (!allDownloads.length) {
    el.innerHTML = `<div class="empty-state"><div class="empty-icon">📥</div><p>No downloads yet</p></div>`;
    return;
  }
  el.innerHTML = allDownloads.map(d => `<div class="track-card track-card--${d.success ? 'done' : 'error'}">
<div class="track-thumb">${d.success ? '✓' : '✕'}</div>
<div class="track-info">
<div class="track-title">${esc(d.label)}</div>
<div class="track-artist">${d.time}</div>
</div>
<div class="status-icon status-${d.success ? 'done' : 'error'}">${d.success ? '✓' : '✕'}</div>
</div>`).join('');
}

// ─── Setup ────────────────────────────────────────────────────────────────────

function selectOption(opt) {
  selectedOption = opt;
  document.getElementById('opt-a').classList.toggle('option-card--selected', opt === 'a');
  document.getElementById('opt-b').classList.toggle('option-card--selected', opt === 'b');
  document.getElementById('opt-a').querySelector('.option-badge').classList.toggle('option-badge--inactive', opt !== 'a');
  document.getElementById('opt-b').querySelector('.option-badge').classList.toggle('option-badge--inactive', opt !== 'b');
  document.getElementById('instructions-a').style.display = opt === 'a' ? 'block' : 'none';
  document.getElementById('instructions-b').style.display = opt === 'b' ? 'block' : 'none';
  if (opt === 'b') {
    document.getElementById('finish-btn').disabled = false;
  } else {
    document.getElementById('finish-btn').disabled = !cookiesPath;
  }
}

function onProfileInput() {
  const val = document.getElementById('firefox-profile-path').value.trim();
  document.getElementById('finish-btn').disabled = !val;
}

function loadCookiesFile(input) {
  const file = input.files[0];
  if (!file) return;
  const statusEl = document.getElementById('file-status');
  statusEl.textContent = 'Uploading...';
  statusEl.style.color = 'var(--text2)';
  const formData = new FormData();
  formData.append('file', file);
  fetch('/api/setup/cookies', {method: 'POST', body: formData})
    .then(r => r.json())
    .then(d => {
      if (d.ok) {
        cookiesPath = d.path;
        statusEl.textContent = `${file.name}`;
        statusEl.style.color = 'var(--green)';
        document.getElementById('finish-btn').disabled = false;
      } else {
        statusEl.textContent = '✕ Upload failed';
        statusEl.style.color = 'var(--red)';
      }
    });
}

function finishSetup() {
  const data = {
    method: selectedOption,
    cookies_path: selectedOption === 'a' ? cookiesPath : null,
    firefox_profile: selectedOption === 'b' ? document.getElementById('firefox-profile-path').value.trim() : null,
  };
  fetch('/api/setup/save', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data),
  }).then(r => {
    if (!r.ok) { showToast('Setup failed - please try again'); return; }
    document.getElementById('setup-overlay').style.display = 'none';
    showToast('Setup complete');
  }).catch(() => {
    showToast('Setup failed - connection error');
  });
}

function resetSetup() {
  fetch('/api/setup/reset', {method: 'POST'})
    .then(r => r.json())
    .then(d => {
      if (!d.ok) return;
      selectedOption = null;
      cookiesPath    = null;
      document.getElementById('instructions-a').style.display = 'none';
      document.getElementById('instructions-b').style.display = 'none';
      document.getElementById('finish-btn').disabled  = true;
      document.getElementById('file-status').textContent  = 'No file selected';
      document.getElementById('file-status').style.color  = 'var(--text3)';
      document.getElementById('opt-a').classList.add('option-card--selected');
      document.getElementById('opt-b').classList.remove('option-card--selected');
      document.getElementById('opt-a').querySelector('.option-badge').classList.remove('option-badge--inactive');
      document.getElementById('opt-b').querySelector('.option-badge').classList.add('option-badge--inactive');
      selectedOption = 'a';
      document.getElementById('firefox-profile-path').value = '';
      document.getElementById('setup-overlay').style.display = 'flex';
    });
}

fetch('/api/setup/status')
  .then(r => r.json())
  .then(d => { if (d.done) document.getElementById('setup-overlay').style.display = 'none'; });

// ─── Shared utilities ─────────────────────────────────────────────────────────

function statusIcon(status) {
  if (status === 'downloading' || status === 'searching') return '<div class="spinner"></div>';
  if (status === 'done')    return '✓';
  if (status === 'error')   return '✕';
  if (status === 'skipped') return '○';
  return '↓';
}

function updateStatusIcon(key, status) {
  const el = document.getElementById(`status-${key}`);
  if (!el) return;
  el.className = `status-icon status-${status}`;
  el.innerHTML = statusIcon(status);
}

function formatDuration(s) {
  const m = Math.floor(s / 60);
  const sec = String(s % 60).padStart(2, '0');
  return `${m}:${sec}`;
}

function esc(str) {
  if (!str) return '';
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

let _toastTimer = null;

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  if (_toastTimer) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { t.classList.remove('show'); _toastTimer = null; }, 3000);
}