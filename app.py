from flask import Flask, render_template_string
import subprocess

app = Flask(__name__)

RADIOS = {
    "fip": "http://icecast.radiofrance.fr/fip-midfi.mp3",
    "france_info": "http://icecast.radiofrance.fr/franceinfo-midfi.mp3",
    "lounge": "https://stream.zeno.fm/f3wvbbqmdg8uv"
}

DEVIALET_IP = "192.168.1.168"

# Variable globale pour stocker le processus ffmpeg en cours
current_stream_process = None

HTML_PAGE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Radio Oiseau</title>
    <style>
        body { font-family: sans-serif; text-align: center; margin-top: 50px; background: #121212; color: #fff; }
        button { padding: 20px 30px; margin: 15px; font-size: 18px; cursor: pointer; border: none; border-radius: 12px; }
        .btn-play { background: #4CAF50; color: white; }
        .btn-stop { background: #f44336; color: white; }
    </style>
</head>
<body>
    <h1>🦜 Radio Oiseau - Contrôle</h1>
    <div>
        <button class="btn-play" onclick="fetch('/play/fip', {method: 'POST'})">Mettre FIP</button>
        <button class="btn-play" onclick="fetch('/play/france_info', {method: 'POST'})">Mettre France Info</button>
    </div>
    <div>
        <button class="btn-stop" onclick="fetch('/stop', {method: 'POST'})">Couper le son 🔇</button>
    </div>
</body>
</html>
"""

def stop_current_stream():
    global current_stream_process
    if current_stream_process:
        print("Arrêt du flux en cours...")
        current_stream_process.terminate()
        current_stream_process.wait()
        current_stream_process = None

@app.route("/")
def index():
    return render_template_string(HTML_PAGE)

@app.route("/play/<radio_name>", methods=["POST"])
def play_radio(radio_name):
    global current_stream_process
    if radio_name in RADIOS:
        url = RADIOS[radio_name]
        print(f"Demande de lecture reçue pour : {radio_name} ({url})")

        # Stopper tout flux précédent
        stop_current_stream()

        # Utilisation de ffmpeg pour streamer directement vers l'AirPlay de la Devialet
        # Commande ffmpeg pour décoder le flux web et l'envoyer au protocole raop (AirPlay audio)
        cmd = [
            "ffmpeg", "-re", "-i", url,
            "-f", "s16le", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
            f"raop://{DEVIALET_IP}"
        ]

        try:
            print(f"Lancement de ffmpeg vers {DEVIALET_IP}...")
            current_stream_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Lecture de {radio_name} sur la Devialet", 200
        except Exception as e:
            print(f"Erreur lors du lancement de ffmpeg : {e}")
            return "Erreur technique", 500

    return "Radio inconnue", 400

@app.route("/stop", methods=["POST"])
def stop_audio():
    print("Demande d'arrêt reçue")
    stop_current_stream()
    return "Audio arrêté", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)
