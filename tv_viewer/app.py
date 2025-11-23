from flask import Flask, render_template, send_from_directory, send_file, request, Response
import os
import socket
import mimetypes
import subprocess

BASE_DIR = "D:\\TV"
VIDEO_EXTS = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.ts', '.webm', '.m2ts']

# Skeleton stripped down version: template_folder='templates'
app = Flask(__name__, template_folder='templates/ux')

@app.route('/')
def index():
    return browse('')

@app.route('/browse/<path:subpath>')
def browse(subpath):
    full_path = os.path.join(BASE_DIR, subpath)
    if not os.path.exists(full_path):
        return "Path not found", 404

    if os.path.isfile(full_path):
        # If it's a file, serve it
        is_mobile = 'mobile' in request.headers.get('User-Agent', '').lower()
        mime_type = mimetypes.guess_type(full_path)[0] or 'video/mp4'
        # For mobile, keep proper MIME so app can stream
        return send_file(full_path, mimetype=mime_type)

    items = os.listdir(full_path)
    dirs = sorted([item for item in items if os.path.isdir(os.path.join(full_path, item))])
    files = sorted([item for item in items if os.path.isfile(os.path.join(full_path, item))])
    videos = []
    for f in sorted([f for f in files if any(f.lower().endswith(ext) for ext in VIDEO_EXTS)]):
        video_href = "/browse/" + ((subpath + "/" + f) if subpath else f)
        videos.append({'name': f, 'href': video_href})
    other_files = sorted([f for f in files if not any(f.lower().endswith(ext) for ext in VIDEO_EXTS)])

    parent_path = '/'.join(subpath.split('/')[:-1]) if '/' in subpath else ''
    is_mobile = 'mobile' in request.headers.get('User-Agent', '').lower()
    # For intent URL on mobile
    host = request.host
    # Check for thumbnails if using UX template
    if 'ux' in app.template_folder.lower():
        dirs_processed = []
        for d in dirs:
            folder_path = os.path.join(BASE_DIR, subpath, d) if subpath else os.path.join(BASE_DIR, d)
            if os.path.exists(folder_path):
                files = os.listdir(folder_path)
            has_thumb = any(f.lower() == 'index.jpg' for f in files)
        else:
            has_thumb = False
        dirs_processed.append({'name': d, 'has_thumb': has_thumb})
    else:
        dirs_processed = dirs
    return render_template('index.html', dirs=dirs_processed, videos=videos, other_files=other_files, subpath=subpath, parent_path=parent_path, is_mobile=is_mobile, host=host)

@app.route('/play/<path:filepath>')
def play(filepath):
    full_path = os.path.join(BASE_DIR, filepath)
    if not os.path.exists(full_path) or not os.path.isfile(full_path):
        return "Video not found", 404

    filename = os.path.basename(full_path)
    back_path = '/'.join(filepath.split('/')[:-1]) if '/' in filepath else ''
    return render_template('player.html', filename=filename, filepath=filepath, back_path=back_path)

@app.route('/video/<path:filepath>')
def video(filepath):
    full_path = os.path.join(BASE_DIR, filepath)
    if not os.path.exists(full_path) or not os.path.isfile(full_path):
        return "File not found", 404

    mime_type = mimetypes.guess_type(full_path)[0] or 'video/mp4'
    return send_file(full_path, mimetype=mime_type)

@app.route('/stream/<path:filepath>')
def stream(filepath):
    full_path = os.path.join(BASE_DIR, filepath)
    if not os.path.exists(full_path) or not os.path.isfile(full_path):
        return "File not found", 404

    def generate():
        command = [
            'C:\\ffmpeg-2025-11-17-git-e94439e49b-full_build\\bin\\ffmpeg.exe', '-i', full_path, '-c:v', 'libx264', '-c:a', 'aac',
            '-preset', 'ultrafast', '-b:v', '500k', '-b:a', '96k', '-f', 'mp4', '-movflags', 'frag_keyframe', '-'
        ]
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            while True:
                data = proc.stdout.read(1024*1024)  # 1MB chunks
                if not data:
                    break
                yield data
        finally:
            proc.terminate()

    return Response(generate(), content_type='video/mp4', headers={'Accept-Ranges': 'bytes'})

@app.route('/thumb/<path:thumbpath>')
def thumb(thumbpath):
    if thumbpath.endswith('/index.jpg'):
        folder_path = os.path.join(BASE_DIR, thumbpath[:-len('/index.jpg')])
        img_path = os.path.join(BASE_DIR, thumbpath)
        if os.path.exists(img_path):
            mime_type = mimetypes.guess_type(img_path)[0] or 'image/jpeg'
            print("Thumbnail requested for:", thumbpath, "img_path:", img_path, "mime:", mime_type, "sending file")
            try:
                return send_file(img_path, mimetype=mime_type)
            except Exception as e:
                print("Error sending file:", img_path, "error:", e)
                return '', 500
        else:
            print("Thumbnail requested for:", thumbpath, "img_path:", img_path, "not found")
            return '', 404
    print("Thumbnail requested for:", thumbpath, "invalid path")
    return '', 404

if __name__ == '__main__':
    # Get local IP
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    except Exception as e:
        local_ip = "unable to detect (check network)"
    finally:
        s.close()

    print("TV Series Viewer Server")
    print(f"Access on this laptop: http://localhost:8000")
    print(f"Access from mobile/other devices: http://{local_ip}:8000")
    app.run(host='0.0.0.0', port=8000, debug=True)
