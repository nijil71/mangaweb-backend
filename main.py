from flask import Flask, send_from_directory, jsonify, request, send_file, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import time
from PIL import Image
import io
from dotenv import load_dotenv
import secrets
from functools import wraps
import hashlib
import redis
from datetime import timedelta

load_dotenv()



app = Flask(__name__)
CORS(app)

# Add secret key configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
ADMIN_TOKEN = os.getenv('ADMIN_TOKEN')

def require_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization')
        
        if not token:
            return jsonify({
                'success': False,
                'error': 'No token provided'
            }), 401
        
        if token.startswith('Bearer '):
            token = token.split(' ')[1]
        
        # Verify token
        if token != ADMIN_TOKEN:
            return jsonify({
                'success': False,
                'error': 'Invalid token'
            }), 403
            
        return f(*args, **kwargs)
    return decorated_function

#upload folder and allowed extensions
UPLOAD_FOLDER = 'manga_images'
WALLPAPER_FOLDER = 'wallpapers'
CACHE_FOLDER = Path('image_cache')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# PostgreSQL database configuration 
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('POSTGRESQL_URI')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

db = SQLAlchemy(app)

class News(db.Model):
    __tablename__ = 'news'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    summary = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(200), nullable=True)
    image = db.Column(db.String(300), nullable=True)

    def __init__(self, date, title, summary, link, image):
        self.date = date
        self.title = title
        self.summary = summary
        self.link = link
        self.image = image

    def serialize(self):
        return {
            'id': self.id,
            'date': self.date,
            'title': self.title,
            'summary': self.summary,
            'link': self.link,
            'image': self.image
        }

# Create the database and tables
with app.app_context():
    db.create_all()

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(WALLPAPER_FOLDER, exist_ok=True)
CACHE_FOLDER.mkdir(exist_ok=True)
redis_client = redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379'))
IMAGE_SIZES = {
    'thumbnail': {
        'size': (300, 400),    # For grid view
        'quality': 60,         # Lower quality for thumbnails
        'target_size': 50_000  # Target ~50KB for thumbnails
    },
    'preview': {
        'size': (800, 1067),   # For modal view
        'quality': 85,         # Higher quality for previews
        'target_size': 200_000 # Target ~200KB for previews
    }
}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/news', methods=['POST'])
@require_token
def add_news():
    try:
        data = request.get_json()
        if not data or not all(key in data for key in ('date', 'title', 'summary')):
            return jsonify({
                'success': False,
                'error': 'Missing required fields'
            }), 400
        
        new_news = News(
            date=data['date'],
            title=data['title'],
            summary=data['summary'],
            link=data.get('link', None),  
            image=data.get('image', None)  
        )
        db.session.add(new_news)
        db.session.commit()

        return jsonify({
            'success': True,
            'news': new_news.serialize()
        }), 201
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
@app.route('/api/news', methods=['GET'])
def get_news():
    try:
        news_list = News.query.all()
        return jsonify({
            'success': True,
            'news': [news.serialize() for news in news_list]
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    
@app.route('/api/news/<int:news_id>', methods=['DELETE'])
def delete_news(news_id):
    try:
        news = db.session.get(News, news_id)
        if not news:
            return jsonify({
                'success': False,
                'error': 'News not found'
            }), 404
        db.session.delete(news)
        db.session.commit()
        return jsonify({
            'Sucess': True
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/images')
def get_images():
    """Return a list of all images in the manga_images directory"""
    try:
        images = [f for f in os.listdir(app.config['UPLOAD_FOLDER']) 
                 if f.lower().endswith(tuple(ALLOWED_EXTENSIONS))]
        image_urls = [f'/api/images/{image}' for image in images]
        
        return jsonify({
            'success': True,
            'images': image_urls
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/images/<path:filename>')
def serve_image(filename):
    """Serve an individual image file"""
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404

@app.route('/api/upload', methods=['POST'])
def upload_image():
    """Handle image upload"""
    try:
        if 'image' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No image file provided'
            }), 400

        file = request.files['image']
        
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'No selected file'
            }), 400

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Added timestamp to filename to avoid duplicates
            base, ext = os.path.splitext(filename)
            filename = f"{base}_{int(time.time())}{ext}"
            
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
            return jsonify({
                'success': True,
                'filename': filename,
                'url': f'/api/images/{filename}'
            })
        
        return jsonify({
            'success': False,
            'error': 'File type not allowed'
        }), 400

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@lru_cache(maxsize=100)
def get_optimized_image(image_path, preset):
    """Get or create optimized version of image with target file size"""
    cache_path = CACHE_FOLDER / f"{Path(image_path).stem}_{preset}.jpg"
    
    # Return cached file if it exists
    if cache_path.exists():
        return cache_path.read_bytes()
    
    size_config = IMAGE_SIZES[preset]
    quality = size_config['quality']
    target_size = size_config['target_size']
    
    with Image.open(image_path) as img:
        # Convert to RGB if necessary
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        
        # Resize image
        img.thumbnail(size_config['size'], Image.Resampling.LANCZOS)
        
        # Binary search for optimal quality to meet target file size
        min_quality = 20
        max_quality = quality
        best_buffer = None
        
        while min_quality <= max_quality:
            current_quality = (min_quality + max_quality) // 2
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=current_quality, optimize=True)
            
            if buffer.tell() <= target_size:
                best_buffer = buffer.getvalue()
                min_quality = current_quality + 1
            else:
                max_quality = current_quality - 1
        
        # Save to cache
        if best_buffer:
            cache_path.write_bytes(best_buffer)
            return best_buffer
        
        # Fallback if target size cannot be met
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=min_quality, optimize=True)
        cache_path.write_bytes(buffer.getvalue())
        return buffer.getvalue()

@app.route('/api/wallpapers')
def get_wallpapers():
    """Return a list of all wallpapers with optimized paths"""
    try:
        wallpapers = [f for f in os.listdir(WALLPAPER_FOLDER)
                     if f.lower().endswith(tuple(ALLOWED_EXTENSIONS))]
        
        wallpaper_data = []
        for wallpaper in wallpapers:
            wallpaper_data.append({
                'id': wallpaper,
                'thumbnail': f'/api/wallpapers/thumbnail/{wallpaper}',
                'preview': f'/api/wallpapers/preview/{wallpaper}',
                'download': f'/api/wallpapers/download/{wallpaper}'
            })
        
        return jsonify({
            'success': True,
            'wallpapers': wallpaper_data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/wallpapers/<string:size_preset>/<path:filename>')
def serve_wallpaper_size(size_preset, filename):
    """Serve wallpaper in specified size with caching"""
    try:
        if size_preset not in IMAGE_SIZES and size_preset != 'download':
            return jsonify({'error': 'Invalid size preset'}), 400

        image_path = os.path.join(WALLPAPER_FOLDER, filename)
        if not os.path.exists(image_path):
            return jsonify({'error': 'Image not found'}), 404

        # For downloads, serve original file
        if size_preset == 'download':
            return send_from_directory(
                WALLPAPER_FOLDER,
                filename,
                as_attachment=True
            )

        # Get optimized image
        image_data = get_optimized_image(image_path, size_preset)

        # Serve the image with caching headers
        response = make_response(image_data)
        response.headers['Content-Type'] = 'image/jpeg'
        response.headers['Cache-Control'] = 'public, max-age=31536000'  # Cache for 1 year
        response.headers['ETag'] = f'"{hash(image_data)}"'
        
        return response

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
if __name__ == '__main__':
    app.run(debug=True, port=5000)