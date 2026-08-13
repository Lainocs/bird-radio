from flask import Flask, render_template_string
import asyncio
import pyatv

app = Flask(__name__)

RADIOS = {
    "fip": "http://icecast.radiofrance.fr/fip-midfi.mp3",
    "france_info": "http://icecast.radiofrance.fr/franceinfo-midfi.mp3",
    "lounge": "https://stream.zeno.fm/f3wvbbqmdg8uv"
}

DEVIALET_IP = "192.168.1.168"

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

async def play_url_on_airplay(url):
    try:
        print(f"Recherche de l'appareil à l'IP {DEVIALET_IP}...")
        atvs = await pyatv.scan(loop=asyncio.get_running_loop(), hosts=[DEVIALET_IP])
        if not atvs:
            print("Aucun appareil trouvé à cette adresse.")
            return

        conf = atvs[0]
        print(f"Appareil trouvé : {conf.name}. Connexion...")
        atv = await pyatv.connect(conf, loop=asyncio.get_running_loop())

        print("Connecté ! Envoi de l'URL via le service audio AirPlay...")
        # Appel direct de play_url sur le service audio de l'appareil AirPlay
        await atv.audio.play_url(url)
        print("Flux envoyé.")
        await atv.close()
    except Exception as e:
        print(f"Erreur AirPlay : {e}")

async def stop_airplay():
    try:
        print("Recherche de l'appareil pour l'arrêt...")
        atvs = await pyatv.scan(loop=asyncio.get_running_loop(), hosts=[DEVIALET_IP])
        if not atvs:
            print("Aucun appareil trouvé à cette adresse.")
            return

        conf = atvs[0]
        atv = await pyatv.connect(conf, loop=asyncio.get_running_loop())
        await atv.remote_control.stop()
        print("Lecture arrêtée.")
        await atv.close()
    except Exception as e:
        print(f"Erreur lors de l'arrêt : {e}")

@app.route("/")
def index():
    return render_template_string(HTML_PAGE)

@app.route("/play/<radio_name>", methods=["POST"])
def play_radio(radio_name):
    if radio_name in RADIOS:
        url = RADIOS[radio_name]
        print(f"Demande de lecture reçue pour : {radio_name}")
        asyncio.run(play_url_on_airplay(url))
        return f"Lecture de {radio_name} sur la Devialet", 200
    return "Radio inconnue", 400

@app.route("/stop", methods=["POST"])
def stop_audio():
    print("Demande d'arrêt reçue")
    asyncio.run(stop_airplay())
    return "Audio arrêté", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)
