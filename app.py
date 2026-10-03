import os
import io
import yt_dlp
from flask import Flask, request, Response, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ============================================================
# دالة مساعدة: استخراج رابط البث باستخدام yt-dlp
# ============================================================
def get_stream_url(video_url, audio_only=False):
    """يستخدم yt-dlp للحصول على رابط البث المباشر من يوتيوب"""
    
    if audio_only:
        # أفضل جودة صوت فقط
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'force_generic_extractor': False,
        }
    else:
        # أفضل فيديو مع صوت (بحد أقصى 720p للتوافق)
        ydl_opts = {
            'format': 'best[height<=720]/best',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'force_generic_extractor': False,
        }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
        
        if audio_only:
            # ابحث عن أفضل رابط صوت
            formats = info.get('formats', [])
            audio_formats = [f for f in formats if f.get('vcodec') == 'none' and f.get('acodec') != 'none']
            if audio_formats:
                # اختار أعلى bitrate
                audio_formats.sort(key=lambda x: x.get('abr', 0) or 0, reverse=True)
                return audio_formats[0]['url']
            # إذا لم يوجد، استخدم الرابط الافتراضي
            return info.get('url')
        else:
            # ابحث عن أفضل فيديو مع صوت مدمج
            formats = info.get('formats', [])
            combined = [f for f in formats 
                       if f.get('vcodec') != 'none' 
                       and f.get('acodec') != 'none' 
                       and f.get('height') is not None
                       and f.get('height') <= 720]
            if combined:
                combined.sort(key=lambda x: x.get('height', 0), reverse=True)
                return combined[0]['url']
            # إذا لم يوجد combined، استخدم best
            return info.get('url')


# ============================================================
# Endpoint: بث الفيديو
# ============================================================
@app.route('/stream')
def stream_video():
    video_url = request.args.get('url')
    if not video_url:
        return Response('Missing ?url= parameter', status=400)
    
    try:
        stream_url = get_stream_url(video_url, audio_only=False)
        if not stream_url:
            return Response('Could not extract stream URL', status=502)
        
        # جلب الفيديو من الرابط المباشر وإعادة بثه
        import requests
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.youtube.com/',
        }
        
        # دعم Range requests
        range_header = request.headers.get('Range')
        if range_header:
            headers['Range'] = range_header
        
        res = requests.get(stream_url, headers=headers, stream=True, timeout=30)
        
        # إعداد headers للاستجابة
        response_headers = {
            'Content-Type': res.headers.get('Content-Type', 'video/mp4'),
            'Access-Control-Allow-Origin': '*',
            'Accept-Ranges': 'bytes',
        }
        
        if 'Content-Length' in res.headers:
            response_headers['Content-Length'] = res.headers['Content-Length']
        if 'Content-Range' in res.headers:
            response_headers['Content-Range'] = res.headers['Content-Range']
        
        def generate():
            for chunk in res.iter_content(chunk_size=8192):
                yield chunk
        
        return Response(generate(), status=res.status_code, headers=response_headers)
    
    except Exception as e:
        return Response(f'Error: {str(e)}', status=500)


# ============================================================
# Endpoint: استخراج الصوت فقط (للتفريغ)
# ============================================================
@app.route('/audio')
def get_audio():
    video_url = request.args.get('url')
    if not video_url:
        return Response('Missing ?url= parameter', status=400)
    
    try:
        stream_url = get_stream_url(video_url, audio_only=True)
        if not stream_url:
            return Response('Could not extract audio URL', status=502)
        
        import requests
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.youtube.com/',
        }
        
        res = requests.get(stream_url, headers=headers, stream=True, timeout=30)
        
        response_headers = {
            'Content-Type': res.headers.get('Content-Type', 'audio/webm'),
            'Access-Control-Allow-Origin': '*',
            'Accept-Ranges': 'bytes',
        }
        
        if 'Content-Length' in res.headers:
            response_headers['Content-Length'] = res.headers['Content-Length']
        
        def generate():
            for chunk in res.iter_content(chunk_size=8192):
                yield chunk
        
        return Response(generate(), status=res.status_code, headers=response_headers)
    
    except Exception as e:
        return Response(f'Error: {str(e)}', status=500)


# ============================================================
# Health check
# ============================================================
@app.route('/')
def health():
    return {'status': 'ok', 'message': 'Auto Clipper Backend is running'}


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)