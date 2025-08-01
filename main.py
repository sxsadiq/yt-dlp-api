from flask import Flask, request, jsonify
import yt_dlp

app = Flask(__name__)

@app.route("/extract", methods=["POST"])
def extract():
    try:
        url = request.json.get("url")
        if not url:
            return jsonify({"error": "Missing URL"}), 400

        ydl_opts = {
            "quiet": True,
            "skip_download": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return jsonify({
                "title": info.get("title"),
                "download_url": info.get("url")
            })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
