from flask import Flask, send_from_directory, jsonify, request,send_file
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

@app.route('/api/wallpapers', methods=['GET'])
def get_wallpapers():
    """Return a list of all images in the wallpapers directory"""
    try:
        # List only files with allowed extensions in the wallpapers folder
        wallpapers = [f for f in os.listdir(WALLPAPER_FOLDER)
                      if f.lower().endswith(tuple(ALLOWED_EXTENSIONS))]
        
        # Generate URLs for each wallpaper
        wallpaper_urls = [f'/api/wallpapers/{wallpaper}' for wallpaper in wallpapers]
        
        return jsonify({
            'success': True,
            'wallpapers': wallpaper_urls
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/wallpapers/<path:filename>')
def serve_wallpaper(filename):
    """Serve an individual wallpaper file"""
    try:
        # Serve the specified file from the wallpapers folder
        return send_from_directory(WALLPAPER_FOLDER, filename)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404

@app.route('/api/images/download/<path:filename>')
def download_image_as_jpg(filename):
    """Serve a .webp image as a .jpg file"""
    webp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    if not os.path.exists(webp_path):
        return jsonify({
            'success': False,
            'error': 'File not found'
        }), 404

    try:
        # Convert .webp to .jpg
        img = Image.open(webp_path)
        img_rgb = img.convert('RGB')  # Convert to RGB for JPG compatibility
        
        # Save the image in-memory as .jpg
        img_io = io.BytesIO()
        img_rgb.save(img_io, 'JPEG', quality=85)
        img_io.seek(0)

        # Send the converted image as an attachment
        return send_file(img_io, mimetype='image/jpeg', as_attachment=True, download_name=f'{os.path.splitext(filename)[0]}.jpg')
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)