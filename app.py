from flask import Flask, render_template_string, jsonify
import asyncio
import threading
import time
import json
import pyatv
from pyatv import exceptions

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Catalogue des stations
# ---------------------------------------------------------------------------
# Les flux "Radio France" (icecast.radiofrance.fr) sont très stables.
# Les flux des groupes privés (RTL, M6/RTL2, NRJ Group, Lagardère...) changent
# de CDN de temps en temps. Si un bouton ne joue plus rien :
#   1. Va sur https://www.fluxradios.com/Radios-France et cherche la station
#   2. Ou ouvre le player web officiel de la radio, F12 > onglet Réseau,
#      filtre "mp3" ou "m3u8", et récupère l'URL du flux en cours
#   3. Remplace l'URL correspondante ci-dessous
#
# Categories utilisées pour organiser l'interface.
CATEGORIES = ["Radio France", "Généralistes", "Musique", "Jazz & Lounge"]

RADIOS = {
    # --- Radio France (flux tres stables) ---
    "france_inter": {
        "name": "France Inter", "emoji": "🎙️", "category": "Radio France",
        "url": "http://icecast.radiofrance.fr/franceinter-midfi.mp3",
    },
    "france_info": {
        "name": "France Info", "emoji": "📰", "category": "Radio France",
        "url": "http://icecast.radiofrance.fr/franceinfo-midfi.mp3",
    },
    "france_culture": {
        "name": "France Culture", "emoji": "📚", "category": "Radio France",
        "url": "http://icecast.radiofrance.fr/franceculture-midfi.mp3",
    },
    "france_musique": {
        "name": "France Musique", "emoji": "🎼", "category": "Radio France",
        "url": "http://icecast.radiofrance.fr/francemusique-midfi.mp3",
    },
    "fip": {
        "name": "FIP", "emoji": "🎷", "category": "Radio France",
        "url": "http://icecast.radiofrance.fr/fip-midfi.mp3",
    },
    "fip_rock": {
        "name": "FIP Rock", "emoji": "🎸", "category": "Radio France",
        "url": "http://icecast.radiofrance.fr/fiprock-midfi.mp3",
    },
    "fip_jazz": {
        "name": "FIP Jazz", "emoji": "🎺", "category": "Radio France",
        "url": "http://icecast.radiofrance.fr/fipjazz-midfi.mp3",
    },
    "fip_groove": {
        "name": "FIP Groove", "emoji": "🕺", "category": "Radio France",
        "url": "http://icecast.radiofrance.fr/fipgroove-midfi.mp3",
    },
    "mouv": {
        "name": "Mouv'", "emoji": "🎧", "category": "Radio France",
        "url": "http://icecast.radiofrance.fr/mouv-midfi.mp3",
    },

    # --- Généralistes / Info ---
    "rtl": {
        "name": "RTL", "emoji": "📻", "category": "Généralistes",
        "url": "http://streaming.radio.rtl.fr/rtl-1-44-96",
    },
    "rmc": {
        "name": "RMC", "emoji": "🗣️", "category": "Généralistes",
        "url": "http://chai5she.lb.vip.cdn.dvmr.fr/rmcinfo",
    },

    # --- Musique ---
    "rtl2": {
        "name": "RTL2", "emoji": "🎵", "category": "Musique",
        "url": "http://streaming.radio.rtl2.fr/rtl2-1-44-96",
    },
    "nrj": {
        "name": "NRJ", "emoji": "⚡", "category": "Musique",
        "url": "https://streaming.nrjaudio.fm/oumvmk8fnozc",
    },
    "skyrock": {
        "name": "Skyrock", "emoji": "🎤", "category": "Musique",
        "url": "http://icecast.skyrock.net/s/natio_mp3_128k",
    },
    "virgin_radio": {
        "name": "Virgin Radio", "emoji": "✨", "category": "Musique",
        "url": "http://mp3lg4.tdf-cdn.com/9243/lag_164753.mp3",
    },
    "nostalgie_rock": {
        "name": "Nostalgie Rock", "emoji": "🕰️", "category": "Musique",
        "url": "http://185.52.127.159/fr/30621/mp3_128.mp3",
    },

    # --- Jazz & Lounge ---
    "jazz_radio": {
        "name": "Jazz Radio", "emoji": "🎹", "category": "Jazz & Lounge",
        "url": "http://broadcast.infomaniak.ch/jazzradio-high.mp3",
    },
    "jazz_radio_lounge": {
        "name": "Jazz Radio Lounge", "emoji": "🛋️", "category": "Jazz & Lounge",
        "url": "http://broadcast.infomaniak.ch/jazzlounge-high.mp3",
    },
    "lounge_zeno": {
        "name": "Lounge (Zeno)", "emoji": "🌙", "category": "Jazz & Lounge",
        "url": "https://stream.zeno.fm/f3wvbbqmdg8uv",
    },
}

DEVIALET_IP = "192.168.1.168"

# Etat courant partage entre les requetes
state_lock = threading.Lock()
current_state = {
    "status": "stopped",   # "stopped" | "connecting" | "playing" | "error"
    "station": None,
    "message": "",
    "updated_at": time.time(),
}


def set_state(status, station=None, message=""):
    with state_lock:
        current_state["status"] = status
        current_state["station"] = station
        current_state["message"] = message
        current_state["updated_at"] = time.time()


HTML_PAGE = """
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Radio Oiseau</title>
<style>
  :root {
    --bg: #0f1115;
    --card: #181b22;
    --card-hover: #1f232c;
    --text: #f2f2f2;
    --muted: #8b8f98;
    --accent: #4CAF50;
    --danger: #f44336;
    --border: #262b35;
  }
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: radial-gradient(circle at top, #171a21 0%, #0b0d11 100%);
    color: var(--text);
    margin: 0;
    padding: 32px 18px 100px;
    min-height: 100vh;
  }
  .wrap { max-width: 480px; margin: 0 auto; }
  h1 { text-align: center; font-size: 26px; margin-bottom: 4px; }
  .subtitle { text-align: center; color: var(--muted); font-size: 14px; margin-bottom: 22px; }

  .now-playing {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 20px 22px;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 16px;
    transition: border-color 0.3s ease;
    position: sticky;
    top: 12px;
    z-index: 10;
    backdrop-filter: blur(6px);
  }
  .now-playing.playing { border-color: var(--accent); }
  .now-playing.error { border-color: var(--danger); }

  .np-icon {
    width: 52px; height: 52px; border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    font-size: 26px; background: #22262f; flex-shrink: 0;
  }
  .np-info { flex: 1; min-width: 0; }
  .np-status {
    font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em;
    color: var(--muted); margin-bottom: 2px;
    display: flex; align-items: center; gap: 6px;
  }
  .np-title { font-size: 17px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); display: inline-block; }
  .dot.playing { background: var(--accent); animation: pulse 1.4s infinite ease-in-out; }
  .dot.connecting { background: #e9c46a; animation: pulse 0.9s infinite ease-in-out; }
  .dot.error { background: var(--danger); }

  @keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.4; transform: scale(0.75); }
  }

  .search-box {
    width: 100%;
    padding: 13px 16px;
    border-radius: 12px;
    border: 1px solid var(--border);
    background: var(--card);
    color: var(--text);
    font-size: 15px;
    margin-bottom: 18px;
    outline: none;
  }
  .search-box::placeholder { color: var(--muted); }
  .search-box:focus { border-color: var(--accent); }

  .category { margin-bottom: 22px; }
  .category-title {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    margin: 0 0 10px 4px;
  }

  .stations { display: flex; flex-direction: column; gap: 10px; }
  .station-btn {
    display: flex; align-items: center; gap: 14px;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 14px 16px;
    cursor: pointer;
    color: var(--text);
    font-size: 15px;
    font-weight: 500;
    text-align: left;
    transition: all 0.15s ease;
  }
  .station-btn:hover { background: var(--card-hover); transform: translateY(-1px); }
  .station-btn:active { transform: translateY(0px) scale(0.99); }
  .station-btn.active {
    border-color: var(--accent);
    background: linear-gradient(90deg, rgba(76,175,80,0.12), transparent);
  }
  .station-emoji {
    width: 36px; height: 36px; border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 18px; background: #22262f; flex-shrink: 0;
  }
  .station-check { margin-left: auto; color: var(--accent); font-size: 18px; opacity: 0; }
  .station-btn.active .station-check { opacity: 1; }

  .stop-bar {
    position: fixed;
    bottom: 0; left: 0; right: 0;
    padding: 16px 18px calc(16px + env(safe-area-inset-bottom));
    background: linear-gradient(0deg, #0b0d11 60%, transparent);
  }
  .stop-btn {
    max-width: 480px;
    margin: 0 auto;
    width: 100%;
    padding: 15px;
    border: none;
    border-radius: 14px;
    background: var(--danger);
    color: white;
    font-size: 16px;
    font-weight: 600;
    cursor: pointer;
    display: block;
    transition: filter 0.15s ease;
  }
  .stop-btn:hover { filter: brightness(1.1); }
  .stop-btn:disabled, .station-btn:disabled { opacity: 0.5; cursor: not-allowed; }

  .no-results { text-align: center; color: var(--muted); padding: 20px; font-size: 14px; }
</style>
</head>
<body>
  <div class="wrap">
    <h1>🦜 Radio Oiseau</h1>
    <div class="subtitle">Contrôle de la Devialet</div>

    <div class="now-playing" id="nowPlaying">
      <div class="np-icon" id="npIcon">🔇</div>
      <div class="np-info">
        <div class="np-status"><span class="dot" id="npDot"></span><span id="npStatusText">Arrêté</span></div>
        <div class="np-title" id="npTitle">Aucune diffusion</div>
      </div>
    </div>

    <input class="search-box" id="searchBox" type="text" placeholder="Rechercher une station..." oninput="filterStations()">

    <div id="categoriesContainer"></div>
  </div>

  <div class="stop-bar">
    <button class="stop-btn" id="stopBtn" onclick="stopRadio()">Couper le son 🔇</button>
  </div>

<script>
const RADIOS = __RADIOS_JSON__;
const CATEGORIES = __CATEGORIES_JSON__;

const container = document.getElementById('categoriesContainer');

CATEGORIES.forEach(cat => {
  const entries = Object.entries(RADIOS).filter(([, r]) => r.category === cat);
  if (entries.length === 0) return;

  const catDiv = document.createElement('div');
  catDiv.className = 'category';
  catDiv.dataset.category = cat;

  const title = document.createElement('div');
  title.className = 'category-title';
  title.textContent = cat;
  catDiv.appendChild(title);

  const stationsDiv = document.createElement('div');
  stationsDiv.className = 'stations';

  entries.forEach(([key, r]) => {
    const btn = document.createElement('button');
    btn.className = 'station-btn';
    btn.id = 'btn-' + key;
    btn.dataset.name = r.name.toLowerCase();
    btn.onclick = () => playRadio(key);
    btn.innerHTML = `
      <div class="station-emoji">${r.emoji}</div>
      <span>${r.name}</span>
      <span class="station-check">✓</span>
    `;
    stationsDiv.appendChild(btn);
  });

  catDiv.appendChild(stationsDiv);
  container.appendChild(catDiv);
});

const noResultsEl = document.createElement('div');
noResultsEl.className = 'no-results';
noResultsEl.textContent = 'Aucune station trouvée';
noResultsEl.style.display = 'none';
container.appendChild(noResultsEl);

function filterStations() {
  const q = document.getElementById('searchBox').value.trim().toLowerCase();
  let anyVisible = false;
  document.querySelectorAll('.category').forEach(catDiv => {
    let catHasVisible = false;
    catDiv.querySelectorAll('.station-btn').forEach(btn => {
      const match = btn.dataset.name.includes(q);
      btn.style.display = match ? 'flex' : 'none';
      if (match) catHasVisible = true;
    });
    catDiv.style.display = catHasVisible ? 'block' : 'none';
    if (catHasVisible) anyVisible = true;
  });
  noResultsEl.style.display = anyVisible ? 'none' : 'block';
}

function setButtonsDisabled(disabled) {
  document.querySelectorAll('.station-btn, .stop-btn').forEach(b => b.disabled = disabled);
}

async function playRadio(key) {
  setButtonsDisabled(true);
  try {
    await fetch('/play/' + key, { method: 'POST' });
  } catch (e) {
    console.error(e);
  }
  await refreshStatus();
  setButtonsDisabled(false);
}

async function stopRadio() {
  setButtonsDisabled(true);
  try {
    await fetch('/stop', { method: 'POST' });
  } catch (e) {
    console.error(e);
  }
  await refreshStatus();
  setButtonsDisabled(false);
}

async function refreshStatus() {
  try {
    const res = await fetch('/status');
    const data = await res.json();
    updateUI(data);
  } catch (e) {
    console.error(e);
  }
}

function updateUI(data) {
  const npEl = document.getElementById('nowPlaying');
  const dotEl = document.getElementById('npDot');
  const iconEl = document.getElementById('npIcon');
  const statusTextEl = document.getElementById('npStatusText');
  const titleEl = document.getElementById('npTitle');

  npEl.classList.remove('playing', 'error');
  dotEl.classList.remove('playing', 'connecting', 'error');
  document.querySelectorAll('.station-btn').forEach(b => b.classList.remove('active'));

  const station = data.station ? RADIOS[data.station] : null;

  if (data.status === 'playing') {
    npEl.classList.add('playing');
    dotEl.classList.add('playing');
    statusTextEl.textContent = 'En cours de lecture';
    iconEl.textContent = station ? station.emoji : '🔊';
    titleEl.textContent = station ? station.name : 'Diffusion en cours';
    if (station) {
      const b = document.getElementById('btn-' + data.station);
      if (b) b.classList.add('active');
    }
  } else if (data.status === 'connecting') {
    dotEl.classList.add('connecting');
    statusTextEl.textContent = 'Connexion...';
    iconEl.textContent = station ? station.emoji : '📡';
    titleEl.textContent = station ? station.name : 'Connexion à la Devialet';
  } else if (data.status === 'error') {
    npEl.classList.add('error');
    dotEl.classList.add('error');
    statusTextEl.textContent = 'Erreur';
    iconEl.textContent = '⚠️';
    titleEl.textContent = data.message || 'Erreur de connexion';
  } else {
    statusTextEl.textContent = 'Arrêté';
    iconEl.textContent = '🔇';
    titleEl.textContent = 'Aucune diffusion';
  }
}

refreshStatus();
setInterval(refreshStatus, 2000);
</script>
</body>
</html>
"""


async def play_url_on_airplay(url):
    try:
        print(f"Recherche de l'appareil à l'IP {DEVIALET_IP}...")
        atvs = await pyatv.scan(loop=asyncio.get_running_loop(), hosts=[DEVIALET_IP])
        if not atvs:
            print("Aucun appareil trouvé à cette adresse.")
            set_state("error", message="Appareil introuvable")
            return
        conf = atvs[0]
        print(f"Appareil trouvé : {conf.name}. Connexion...")
        atv = await pyatv.connect(conf, loop=asyncio.get_running_loop())
        print("Connecté ! Envoi de l'URL via RAOP (stream_file)...")
        # Cet appareil expose RAOP mais pas la feature PlayUrl (nécessite un
        # pairing AirPlay complet). StreamFile fonctionne en revanche sans
        # pairing : pyatv utilise ffmpeg pour transcoder/streamer le flux.
        # stream_file accepte aussi bien un chemin local qu'une URL http(s).
        await atv.stream.stream_file(url)
        print("Flux envoyé.")
        atv.close()
    except Exception as e:
        print(f"Erreur AirPlay : {e}")
        set_state("error", message=str(e))
        raise


async def stop_airplay():
    try:
        print("Recherche de l'appareil pour l'arrêt...")
        atvs = await pyatv.scan(loop=asyncio.get_running_loop(), hosts=[DEVIALET_IP])
        if not atvs:
            print("Aucun appareil trouvé à cette adresse.")
            set_state("error", message="Appareil introuvable")
            return
        conf = atvs[0]
        atv = await pyatv.connect(conf, loop=asyncio.get_running_loop())
        try:
            await atv.remote_control.stop()
            print("Lecture arrêtée via remote_control.")
        except (exceptions.NotSupportedError, AttributeError) as e:
            print(f"remote_control.stop() non supporté ({e}), fermeture de la connexion.")
        atv.close()
        print("Connexion fermée.")
    except Exception as e:
        print(f"Erreur lors de l'arrêt : {e}")
        set_state("error", message=str(e))
        raise


@app.route("/")
def index():
    radios_for_js = {k: {"name": v["name"], "emoji": v["emoji"], "category": v["category"]} for k, v in RADIOS.items()}
    page = HTML_PAGE.replace("__RADIOS_JSON__", json.dumps(radios_for_js, ensure_ascii=False))
    page = page.replace("__CATEGORIES_JSON__", json.dumps(CATEGORIES, ensure_ascii=False))
    return render_template_string(page)


@app.route("/status")
def status():
    with state_lock:
        return jsonify(dict(current_state))


@app.route("/play/<radio_name>", methods=["POST"])
def play_radio(radio_name):
    if radio_name in RADIOS:
        url = RADIOS[radio_name]["url"]
        print(f"Demande de lecture reçue pour : {radio_name}")
        set_state("connecting", station=radio_name)
        try:
            asyncio.run(play_url_on_airplay(url))
        except Exception:
            return f"Erreur lors de la lecture de {radio_name}", 500
        set_state("playing", station=radio_name)
        return f"Lecture de {radio_name} sur la Devialet", 200
    return "Radio inconnue", 400


@app.route("/stop", methods=["POST"])
def stop_audio():
    print("Demande d'arrêt reçue")
    try:
        asyncio.run(stop_airplay())
    except Exception:
        return "Erreur lors de l'arrêt", 500
    set_state("stopped")
    return "Audio arrêté", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)
