from flask import Flask, send_from_directory, jsonify, request,send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import time
from PIL import Image
import io



app = Flask(__name__)
CORS(app)

#upload folder and allowed extensions
UPLOAD_FOLDER = 'manga_images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
            # Add timestamp to filename to avoid duplicates
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