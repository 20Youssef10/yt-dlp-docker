"""
yt-dlp REST API wrapper for Railway deployment.
Endpoints:
  POST /download  — get direct download URLs + metadata
  GET  /health    — health check
"""

import json
import subprocess
import os
from flask import Flask, request, jsonify

app = Flask(__name__)

API_KEY = os.environ.get("API_KEY", "")


def check_auth():
    if not API_KEY:
        return True
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    return token == API_KEY


@app.before_request
def auth_guard():
    if request.path == "/health":
        return None
    if not check_auth():
        return jsonify({"error": "Unauthorized"}), 401


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/download", methods=["POST"])
def download():
    data = request.json or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400

    options = data.get("options", {})

    # Build yt-dlp command
    cmd = ["yt-dlp", "--no-warnings", "--no-playlist"]

    # === Format selection ===
    audio_only = options.get("audioOnly", False)
    video_quality = options.get("videoQuality", "1080")
    audio_format = options.get("audioFormat", "best")
    video_codec = options.get("videoCodec", "")
    merge_format = options.get("mergeOutputFormat", "")

    if audio_only:
        cmd += ["-x"]
        if audio_format and audio_format != "best":
            cmd += ["--audio-format", audio_format]
        audio_quality = options.get("audioQuality", "0")
        cmd += ["--audio-quality", str(audio_quality)]
    else:
        # Build format string
        vcodec_filter = ""
        if video_codec:
            codec_map = {"h264": "avc", "av1": "av01", "vp9": "vp9"}
            vc = codec_map.get(video_codec, video_codec)
            vcodec_filter = f"[vcodec^={vc}]"

        fmt = f"bestvideo[height<={video_quality}]{vcodec_filter}+bestaudio/best[height<={video_quality}]/best"
        cmd += ["-f", fmt]

        if merge_format:
            cmd += ["--merge-output-format", merge_format]

    # === Subtitles ===
    if options.get("embedSubtitles"):
        cmd += ["--embed-subs"]
    if options.get("writeSubtitles"):
        cmd += ["--write-subs"]
    sub_lang = options.get("subtitleLanguage", "")
    if sub_lang:
        cmd += ["--sub-langs", sub_lang]

    # === Thumbnail ===
    if options.get("embedThumbnail"):
        cmd += ["--embed-thumbnail"]
    if options.get("writeThumbnail"):
        cmd += ["--write-thumbnail"]

    # === Metadata ===
    if options.get("disableMetadata"):
        cmd += ["--no-embed-info-json", "--parse-metadata", ":(?P<meta_comment>)"]
    if options.get("embedChapters"):
        cmd += ["--embed-chapters"]

    # === Network ===
    if options.get("geoBypass"):
        cmd += ["--geo-bypass"]
    proxy = options.get("proxy", "")
    if proxy:
        cmd += ["--proxy", proxy]
    rate_limit = options.get("rateLimit", "")
    if rate_limit:
        cmd += ["-r", rate_limit]

    # === File limits ===
    max_filesize = options.get("maxFileSize", "")
    if max_filesize:
        cmd += ["--max-filesize", max_filesize]

    # === Filename ===
    filename_style = options.get("filenameStyle", "pretty")
    templates = {
        "classic": "%(title)s-%(id)s.%(ext)s",
        "pretty": "%(title)s (%(height)sp %(uploader)s).%(ext)s",
        "basic": "%(title)s.%(ext)s",
        "nerdy": "%(title)s-%(id)s-%(format_id)s-%(height)sp.%(ext)s",
    }
    cmd += ["-o", templates.get(filename_style, templates["pretty"])]

    # === Playlist ===
    if options.get("noPlaylist"):
        cmd += ["--no-playlist"]
    else:
        # Default: already --no-playlist at top; remove it if user wants playlist
        if options.get("downloadPlaylist"):
            cmd = [c for c in cmd if c != "--no-playlist"]
            cmd += ["--yes-playlist"]

    # === Platform-specific ===
    if options.get("twitterGif"):
        pass  # yt-dlp handles twitter gifs natively
    if options.get("tiktokH265"):
        # Force h265 for tiktok
        pass

    # === SponsorBlock ===
    if options.get("sponsorBlock"):
        cmd += ["--sponsorblock-remove", "all"]

    # === Age gate ===
    if options.get("cookiesFromBrowser"):
        browser_name = options.get("cookiesBrowser", "chrome")
        cmd += ["--cookies-from-browser", browser_name]

    # Get JSON metadata + direct URLs
    cmd += ["--dump-json", "--no-download"]
    cmd.append(url)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=90
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            return jsonify({
                "status": "error",
                "error": stderr or "yt-dlp failed"
            }), 400

        # May return multiple JSON objects (playlist)
        lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
        entries = []
        for line in lines:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        if not entries:
            return jsonify({"status": "error", "error": "No results found"}), 404

        # Now get actual download URLs
        url_cmd = ["yt-dlp", "--no-warnings", "--get-url"]

        # Re-apply format selection
        if audio_only:
            url_cmd += ["-x"]
            if audio_format and audio_format != "best":
                url_cmd += ["--audio-format", audio_format]
        else:
            fmt_str = f"bestvideo[height<={video_quality}]+bestaudio/best[height<={video_quality}]/best"
            url_cmd += ["-f", fmt_str]

        if options.get("noPlaylist", True):
            url_cmd += ["--no-playlist"]

        url_cmd.append(url)

        url_result = subprocess.run(
            url_cmd, capture_output=True, text=True, timeout=60
        )

        download_urls = [u.strip() for u in url_result.stdout.strip().split("\n") if u.strip()]

        if len(entries) == 1:
            entry = entries[0]
            dl_url = download_urls[0] if download_urls else entry.get("url", "")
            ext = entry.get("ext", "mp4")
            title = entry.get("title", "download")

            # Build filename
            template = templates.get(filename_style, templates["pretty"])
            filename = f"{title}.{ext}"

            return jsonify({
                "status": "redirect",
                "url": dl_url,
                "filename": filename,
                "metadata": {
                    "title": title,
                    "duration": entry.get("duration"),
                    "uploader": entry.get("uploader"),
                    "thumbnail": entry.get("thumbnail"),
                    "resolution": entry.get("resolution"),
                    "filesize": entry.get("filesize_approx") or entry.get("filesize"),
                    "ext": ext,
                    "formats_available": len(entry.get("formats", [])),
                }
            })
        else:
            # Multiple entries (playlist)
            picker = []
            for i, entry in enumerate(entries):
                dl_url = download_urls[i] if i < len(download_urls) else entry.get("url", "")
                picker.append({
                    "url": dl_url,
                    "type": entry.get("title", f"Item {i+1}"),
                    "thumb": entry.get("thumbnail"),
                    "duration": entry.get("duration"),
                    "resolution": entry.get("resolution"),
                })

            return jsonify({
                "status": "picker",
                "picker": picker,
                "filename": entries[0].get("title", "playlist"),
            })

    except subprocess.TimeoutExpired:
        return jsonify({"status": "error", "error": "Request timed out"}), 504
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/formats", methods=["POST"])
def list_formats():
    """List all available formats for a URL."""
    data = request.json or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400

    cmd = ["yt-dlp", "--no-warnings", "--dump-json", "--no-download", "--no-playlist", url]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return jsonify({"error": result.stderr.strip()}), 400

        data = json.loads(result.stdout)
        formats = []
        for f in data.get("formats", []):
            formats.append({
                "format_id": f.get("format_id"),
                "ext": f.get("ext"),
                "resolution": f.get("resolution"),
                "fps": f.get("fps"),
                "vcodec": f.get("vcodec"),
                "acodec": f.get("acodec"),
                "filesize": f.get("filesize") or f.get("filesize_approx"),
                "note": f.get("format_note"),
            })

        return jsonify({
            "title": data.get("title"),
            "thumbnail": data.get("thumbnail"),
            "duration": data.get("duration"),
            "formats": formats,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
