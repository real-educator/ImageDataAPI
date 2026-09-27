#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Professional Metadata Extractor v3.0
Telegram: @KSHATRIYA_OP
"""

import os
import json
import subprocess
import tempfile
import base64
from datetime import datetime
from flask import Flask, request, render_template_string, jsonify, send_file
from werkzeug.utils import secure_filename
import io

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max

# ---------- METADATA CATEGORIES ----------
CATEGORIES = {
    '📷 Camera & Lens': {
        'icon': '📷',
        'keys': ['Make', 'Model', 'CameraModelName', 'LensModel', 'LensInfo', 'LensID', 
                'LensMake', 'LensSerialNumber', 'LensSpecification']
    },
    '⚙️ Camera Settings': {
        'icon': '⚙️',
        'keys': ['ISO', 'ExposureTime', 'FNumber', 'FocalLength', 'FocalLengthIn35mmFormat',
                'Aperture', 'ShutterSpeed', 'ExposureProgram', 'ExposureMode', 'MeteringMode',
                'WhiteBalance', 'Flash', 'FlashMode', 'DigitalZoomRatio', 'ExposureCompensation',
                'ExposureTime', 'ApertureValue', 'BrightnessValue', 'MaxApertureValue']
    },
    '🖼️ Image Properties': {
        'icon': '🖼️',
        'keys': ['ImageWidth', 'ImageHeight', 'BitsPerSample', 'ColorSpace', 'ImageSize',
                'Megapixels', 'Resolution', 'ResolutionUnit', 'XResolution', 'YResolution',
                'Orientation', 'Compression', 'Quality', 'JFIFVersion', 'PixelDimensions']
    },
    '📅 Date & Time': {
        'icon': '📅',
        'keys': ['DateTimeOriginal', 'CreateDate', 'ModifyDate', 'DateTimeDigitized',
                'DateCreated', 'TimeCreated', 'SubSecTimeOriginal', 'OffsetTime',
                'ModifyDate', 'MetadataDate', 'DateAcquired']
    },
    '🌍 GPS Location': {
        'icon': '🌍',
        'keys': ['GPSLatitude', 'GPSLongitude', 'GPSAltitude', 'GPSPosition',
                'GPSLatitudeRef', 'GPSLongitudeRef', 'GPSAltitudeRef', 'GPSDateStamp',
                'GPSTimeStamp', 'GPSImgDirection', 'GPSDestBearing', 'GPSHPositioningError']
    },
    '📝 File Information': {
        'icon': '📝',
        'keys': ['FileName', 'FileSize', 'FileType', 'MIMEType', 'FilePermissions',
                'FileModifyDate', 'FileAccessDate', 'FileInodeChangeDate', 'FileExtension',
                'FileSize', 'Directory']
    },
    '🎨 Author & Copyright': {
        'icon': '🎨',
        'keys': ['Artist', 'Author', 'Creator', 'Copyright', 'CopyrightNotice',
                'Rights', 'Credit', 'Source', 'OwnerName', 'UsageTerms', 'CreatorWorkURL']
    },
    '🏷️ Description & Tags': {
        'icon': '🏷️',
        'keys': ['Description', 'ImageDescription', 'Caption', 'Title', 'ObjectName',
                'Keywords', 'Subject', 'Category', 'Headline', 'City', 'State', 'Country',
                'Location', 'CountryCode', 'ProvinceState', 'Sub-location']
    },
    '📱 Software & Device': {
        'icon': '📱',
        'keys': ['Software', 'HostComputer', 'CreatorTool', 'Producer', 'ApplicationName',
                'DeviceModel', 'DeviceManufacturer', 'Platform', 'OperatingSystem']
    },
    '🔧 Advanced EXIF': {
        'icon': '🔧',
        'keys': ['ExifVersion', 'FlashpixVersion', 'ComponentsConfiguration', 'ExposureIndex',
                'SensingMethod', 'SceneType', 'SceneCaptureType', 'GainControl',
                'Contrast', 'Saturation', 'Sharpness', 'SubjectDistance', 'SubjectArea',
                'LightSource', 'FocalPlaneXResolution', 'FocalPlaneYResolution']
    },
    '📊 Technical Data': {
        'icon': '📊',
        'keys': ['BitsPerSample', 'YCbCrSubSampling', 'InteroperabilityIndex',
                'InteroperabilityVersion', 'ThumbnailImage', 'CompressedBitsPerPixel',
                'PixelXDimension', 'PixelYDimension', 'ImageLength', 'ImageWidth']
    }
}

# ---------- PARSE METADATA ----------
def parse_metadata_to_readable(raw_metadata):
    """Convert raw metadata into organized, user-friendly format"""
    
    result = {
        'summary': {},
        'categories': {},
        'all_raw': raw_metadata,
        'gps': None
    }
    
    # Extract summary
    summary_keys = ['FileName', 'Make', 'Model', 'DateTimeOriginal', 'ImageSize', 'FileSize']
    for key in summary_keys:
        if key in raw_metadata and raw_metadata[key]:
            result['summary'][key] = raw_metadata[key]
    
    # Extract GPS
    if 'GPSPosition' in raw_metadata:
        result['gps'] = raw_metadata['GPSPosition']
    elif 'GPSLatitude' in raw_metadata and 'GPSLongitude' in raw_metadata:
        result['gps'] = f"{raw_metadata['GPSLatitude']}, {raw_metadata['GPSLongitude']}"
    
    # Categorize
    for cat_name, cat_info in CATEGORIES.items():
        cat_data = {}
        for key in cat_info['keys']:
            if key in raw_metadata and raw_metadata[key] not in [None, '', '0']:
                value = raw_metadata[key]
                if isinstance(value, str):
                    value = value.strip()
                if value:
                    cat_data[key] = value
        if cat_data:
            result['categories'][cat_name] = {
                'icon': cat_info['icon'],
                'data': cat_data
            }
    
    # Unknown metadata
    known_keys = set()
    for cat in CATEGORIES.values():
        known_keys.update(cat['keys'])
    
    unknown_data = {}
    for key, value in raw_metadata.items():
        if key not in known_keys and key not in ['SourceFile', 'ExifToolVersion']:
            if value not in [None, '', '0']:
                unknown_data[key] = value
    
    if unknown_data:
        result['categories']['🔍 Other Information'] = {
            'icon': '🔍',
            'data': unknown_data
        }
    
    return result

# ---------- EXIFTOOL EXTRACTOR ----------
def extract_metadata(file_path):
    try:
        cmd = ['exiftool', '-j', '-a', '-G', '-n', file_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            return {'error': f'ExifTool error: {result.stderr}'}
        
        data = json.loads(result.stdout)
        if data and isinstance(data, list) and len(data) > 0:
            metadata = data[0]
            metadata.pop('SourceFile', None)
            metadata.pop('ExifToolVersion', None)
            return {'metadata': metadata}
        else:
            return {'error': 'No metadata found'}
            
    except FileNotFoundError:
        return {'error': 'ExifTool not installed. Install: apt-get install exiftool'}
    except subprocess.TimeoutExpired:
        return {'error': 'File processing timed out'}
    except Exception as e:
        return {'error': f'Error: {str(e)}'}

# ---------- HTML TEMPLATE ----------
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📸 Smart Metadata Viewer - @Black_Hats_Hackers</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0a0a1a;
            --bg-secondary: #12122a;
            --bg-card: #1a1a3e;
            --text-primary: #e8e8f0;
            --text-secondary: #a0a0c0;
            --accent: #6c63ff;
            --accent-glow: rgba(108, 99, 255, 0.3);
            --border-color: #2a2a5a;
        }
        
        body {
            font-family: 'Inter', sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            padding: 20px;
        }
        
        .main-container {
            max-width: 1300px;
            margin: auto;
        }
        
        /* Header */
        .header {
            text-align: center;
            padding: 30px 0 20px;
        }
        .header h1 {
            font-size: 2.8rem;
            font-weight: 800;
            background: linear-gradient(135deg, #6c63ff, #a78bfa);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .header .subtitle {
            color: var(--text-secondary);
            font-size: 1.1rem;
        }
        .header .badge-telegram {
            display: inline-block;
            background: #0088cc;
            color: white;
            padding: 6px 20px;
            border-radius: 50px;
            font-size: 0.9rem;
            margin-top: 10px;
        }
        .header .badge-telegram i {
            margin-right: 8px;
        }
        
        /* Upload Area */
        .upload-area {
            border: 2px dashed var(--border-color);
            border-radius: 24px;
            padding: 50px 20px;
            background: var(--bg-secondary);
            transition: all 0.3s ease;
            cursor: pointer;
            text-align: center;
            position: relative;
        }
        .upload-area:hover {
            border-color: var(--accent);
            background: var(--bg-card);
        }
        .upload-area.dragover {
            border-color: var(--accent);
            background: rgba(108, 99, 255, 0.1);
            transform: scale(1.01);
        }
        .upload-icon {
            font-size: 70px;
            color: var(--accent);
            margin-bottom: 15px;
        }
        .upload-area h4 {
            color: var(--text-primary);
            font-weight: 600;
        }
        .upload-area p {
            color: var(--text-secondary);
        }
        #fileInput {
            display: none;
        }
        .btn-primary-custom {
            background: linear-gradient(135deg, #6c63ff, #4a42d4);
            border: none;
            padding: 14px 40px;
            border-radius: 50px;
            font-weight: 600;
            color: white;
            transition: all 0.3s;
            margin-top: 15px;
        }
        .btn-primary-custom:hover {
            transform: translateY(-3px);
            box-shadow: 0 10px 30px var(--accent-glow);
            color: white;
        }
        
        /* File Preview */
        .file-preview {
            display: none;
            margin: 20px 0;
            padding: 20px;
            background: var(--bg-card);
            border-radius: 16px;
            text-align: center;
        }
        .file-preview img {
            max-height: 300px;
            max-width: 100%;
            border-radius: 12px;
            border: 1px solid var(--border-color);
        }
        .file-preview .file-name-display {
            color: var(--text-secondary);
            margin-top: 10px;
        }
        
        /* Spinner */
        .spinner-container {
            display: none;
            text-align: center;
            padding: 30px;
        }
        .spinner-border {
            width: 50px;
            height: 50px;
            border-color: var(--accent);
            border-right-color: transparent;
        }
        
        /* Results */
        #resultArea {
            display: none;
            margin-top: 30px;
        }
        
        /* Summary */
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px;
            background: var(--bg-card);
            padding: 20px;
            border-radius: 16px;
            margin-bottom: 25px;
            border: 1px solid var(--border-color);
        }
        .summary-item {
            text-align: center;
            padding: 10px;
            background: var(--bg-secondary);
            border-radius: 12px;
        }
        .summary-item .label {
            color: var(--text-secondary);
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .summary-item .value {
            color: var(--text-primary);
            font-weight: 600;
            font-size: 1rem;
            word-break: break-all;
        }
        
        /* Category Cards */
        .category-card {
            background: var(--bg-card);
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 16px;
            border-left: 4px solid var(--accent);
            border: 1px solid var(--border-color);
            transition: all 0.2s;
        }
        .category-card:hover {
            border-color: var(--accent);
        }
        .category-title {
            font-weight: 700;
            font-size: 1.15rem;
            color: var(--text-primary);
            margin-bottom: 14px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .metadata-row {
            display: flex;
            justify-content: space-between;
            padding: 6px 12px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            font-size: 0.9rem;
            align-items: center;
            gap: 15px;
        }
        .metadata-row:last-child {
            border-bottom: none;
        }
        .metadata-key {
            color: var(--accent);
            font-weight: 500;
            min-width: 150px;
            flex-shrink: 0;
        }
        .metadata-value {
            color: var(--text-primary);
            word-break: break-word;
            text-align: right;
            flex: 1;
        }
        .copy-btn {
            background: transparent;
            border: none;
            color: var(--text-secondary);
            cursor: pointer;
            padding: 2px 8px;
            font-size: 0.8rem;
            transition: color 0.2s;
        }
        .copy-btn:hover {
            color: var(--accent);
        }
        
        /* GPS Map Link */
        .gps-link {
            display: inline-block;
            background: #1a73e8;
            color: white;
            padding: 4px 14px;
            border-radius: 50px;
            font-size: 0.8rem;
            text-decoration: none;
            margin-left: 10px;
        }
        .gps-link:hover {
            color: white;
            background: #1557b0;
        }
        
        /* Raw JSON */
        .raw-json {
            background: #0a0a1a;
            color: #a0e0a0;
            padding: 20px;
            border-radius: 12px;
            font-size: 12px;
            line-height: 1.6;
            white-space: pre-wrap;
            word-break: break-word;
            max-height: 400px;
            overflow-y: auto;
            display: none;
            margin-top: 15px;
            border: 1px solid var(--border-color);
            font-family: 'Courier New', monospace;
        }
        
        /* Action Buttons */
        .action-buttons {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin: 20px 0;
            justify-content: center;
        }
        .action-btn {
            padding: 10px 25px;
            border-radius: 50px;
            border: 1px solid var(--border-color);
            background: var(--bg-card);
            color: var(--text-primary);
            transition: all 0.3s;
            font-size: 0.9rem;
            cursor: pointer;
        }
        .action-btn:hover {
            border-color: var(--accent);
            background: var(--bg-secondary);
            color: var(--accent);
        }
        .action-btn i {
            margin-right: 8px;
        }
        
        /* Toggle Switch for Dark/Light */
        .theme-toggle {
            position: fixed;
            top: 20px;
            right: 20px;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            width: 44px;
            height: 44px;
            border-radius: 50%;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.2rem;
            transition: all 0.3s;
            z-index: 100;
        }
        .theme-toggle:hover {
            border-color: var(--accent);
            transform: scale(1.05);
        }
        
        /* Light Theme */
        body.light-theme {
            --bg-primary: #f0f2f5;
            --bg-secondary: #ffffff;
            --bg-card: #ffffff;
            --text-primary: #1a1a2e;
            --text-secondary: #555577;
            --border-color: #d0d0e0;
        }
        body.light-theme .upload-area {
            background: #f8f9ff;
        }
        body.light-theme .summary-item {
            background: #f0f2f5;
        }
        body.light-theme .raw-json {
            background: #1a1a2e;
            color: #a0e0a0;
        }
        
        /* Responsive */
        @media (max-width: 768px) {
            .header h1 { font-size: 2rem; }
            .summary-grid { grid-template-columns: 1fr 1fr; }
            .metadata-row { flex-direction: column; align-items: flex-start; gap: 2px; }
            .metadata-value { text-align: left; }
            .metadata-key { min-width: auto; }
            .action-buttons { flex-direction: column; align-items: center; }
        }
        @media (max-width: 480px) {
            .summary-grid { grid-template-columns: 1fr; }
        }
        
        /* Scrollbar */
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: var(--bg-secondary); }
        ::-webkit-scrollbar-thumb { background: var(--accent); border-radius: 10px; }
        
        /* Toast notification */
        .toast-notification {
            position: fixed;
            bottom: 30px;
            left: 50%;
            transform: translateX(-50%);
            background: var(--bg-card);
            color: var(--text-primary);
            padding: 12px 30px;
            border-radius: 50px;
            border: 1px solid var(--accent);
            font-weight: 500;
            display: none;
            z-index: 200;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
        }
    </style>
</head>
<body>
    <!-- Theme Toggle -->
    <button class="theme-toggle" onclick="toggleTheme()" title="Dark/Light Mode">
        <i class="fas fa-moon"></i>
    </button>
    
    <div class="main-container">
        <!-- Header -->
        <div class="header">
            <h1><i class="fas fa-camera-retro"></i> Smart Metadata Viewer</h1>
            <p class="subtitle">Image ke andar chhupi har jaankari — ek click mein</p>
            <a href="https://t.me/Black_Hats_Hackers" target="_blank" class="badge-telegram">
                <i class="fab fa-telegram-plane"></i> @Black_Hats_Hackers
            </a>
        </div>
        
        <!-- Upload Area -->
        <div id="uploadArea" class="upload-area" onclick="document.getElementById('fileInput').click()">
            <div class="upload-icon"><i class="fas fa-cloud-upload-alt"></i></div>
            <h4>Click karein ya Drag & Drop karein</h4>
            <p>JPG, PNG, HEIC, RAW, GIF, BMP, TIFF — sab support</p>
            <input type="file" id="fileInput" accept="image/*" multiple>
            <button class="btn-primary-custom" onclick="event.stopPropagation(); document.getElementById('fileInput').click();">
                <i class="fas fa-upload"></i> Image Choose Karein
            </button>
        </div>
        
        <!-- File Preview -->
        <div id="filePreview" class="file-preview">
            <img id="previewImage" src="" alt="Preview">
            <div class="file-name-display" id="previewFileName"></div>
        </div>
        
        <!-- Spinner -->
        <div class="spinner-container" id="spinnerContainer">
            <div class="spinner-border" role="status"></div>
            <p style="color: var(--text-secondary); margin-top: 10px;">Metadata nikaala ja raha hai...</p>
        </div>
        
        <!-- Results -->
        <div id="resultArea">
            <!-- Summary -->
            <div id="summaryContainer"></div>
            
            <!-- Categories -->
            <div id="categoriesContainer"></div>
            
            <!-- Action Buttons -->
            <div class="action-buttons">
                <button class="action-btn" onclick="downloadJSON()"><i class="fas fa-download"></i> Download JSON</button>
                <button class="action-btn" onclick="copyAllData()"><i class="fas fa-copy"></i> Copy All</button>
                <button class="action-btn" onclick="toggleRaw()"><i class="fas fa-code"></i> Raw Data</button>
                <button class="action-btn" onclick="window.print()"><i class="fas fa-print"></i> Print</button>
            </div>
            
            <!-- Raw JSON -->
            <div id="rawJson" class="raw-json"></div>
        </div>
        
        <!-- Footer -->
        <div class="text-center mt-4" style="color: var(--text-secondary); font-size: 0.8rem; border-top: 1px solid var(--border-color); padding-top: 20px;">
            <i class="fas fa-shield-alt"></i> Image locally process hoti hai — koi server par upload nahi hoti
            <br>
            <span style="opacity: 0.5;">Made with ❤️ for @Black_Hats_Hackers</span>
        </div>
    </div>
    
    <!-- Toast -->
    <div class="toast-notification" id="toast">✅ Copied!</div>
    
    <script>
        let metadataData = null;
        let currentFile = null;
        
        // ---------- File Upload ----------
        document.getElementById('fileInput').addEventListener('change', handleFiles);
        
        const uploadArea = document.getElementById('uploadArea');
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        });
        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('dragover');
        });
        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0) {
                document.getElementById('fileInput').files = e.dataTransfer.files;
                handleFiles();
            }
        });
        
        function handleFiles() {
            const files = document.getElementById('fileInput').files;
            if (files.length === 0) return;
            
            // Show first file preview
            const file = files[0];
            if (!file.type.startsWith('image/')) {
                showToast('⚠️ Please upload a valid image file', 'error');
                return;
            }
            
            currentFile = file;
            
            // Preview
            const reader = new FileReader();
            reader.onload = (e) => {
                document.getElementById('previewImage').src = e.target.result;
                document.getElementById('previewFileName').textContent = `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
                document.getElementById('filePreview').style.display = 'block';
            };
            reader.readAsDataURL(file);
            
            // Upload
            const formData = new FormData();
            formData.append('image', file);
            
            document.getElementById('spinnerContainer').style.display = 'block';
            document.getElementById('resultArea').style.display = 'none';
            
            fetch('/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                document.getElementById('spinnerContainer').style.display = 'none';
                if (data.error) {
                    showToast('❌ ' + data.error, 'error');
                    return;
                }
                metadataData = data;
                displayMetadata(data);
                document.getElementById('resultArea').style.display = 'block';
                showToast('✅ Metadata successfully extracted!', 'success');
            })
            .catch(err => {
                document.getElementById('spinnerContainer').style.display = 'none';
                showToast('❌ Server error: ' + err.message, 'error');
            });
        }
        
        // ---------- Display Metadata ----------
        function displayMetadata(data) {
            // Summary
            const summary = data.summary || {};
            let summaryHTML = '<div class="summary-grid">';
            const summaryLabels = {
                'FileName': '📄 File',
                'Make': '📷 Brand',
                'Model': '📸 Model',
                'DateTimeOriginal': '📅 Date',
                'ImageSize': '🖼️ Size',
                'FileSize': '📦 File Size'
            };
            for (const [key, value] of Object.entries(summary)) {
                if (value && value !== 'Not Available') {
                    const label = summaryLabels[key] || key;
                    summaryHTML += `
                        <div class="summary-item">
                            <div class="label">${label}</div>
                            <div class="value">${value}</div>
                        </div>
                    `;
                }
            }
            // GPS in summary
            if (data.gps) {
                summaryHTML += `
                    <div class="summary-item">
                        <div class="label">🌍 GPS</div>
                        <div class="value">
                            ${data.gps}
                            <a href="https://www.google.com/maps?q=${encodeURIComponent(data.gps)}" target="_blank" class="gps-link">
                                <i class="fas fa-map-marker-alt"></i> Map
                            </a>
                        </div>
                    </div>
                `;
            }
            summaryHTML += '</div>';
            document.getElementById('summaryContainer').innerHTML = summaryHTML;
            
            // Categories
            const categories = data.categories || {};
            let catHTML = '';
            for (const [catName, catData] of Object.entries(categories)) {
                const icon = catData.icon || '📌';
                const items = catData.data || {};
                if (Object.keys(items).length === 0) continue;
                
                catHTML += `
                    <div class="category-card">
                        <div class="category-title">${icon} ${catName}</div>
                `;
                for (const [key, value] of Object.entries(items)) {
                    let label = key.replace(/([A-Z])/g, ' $1').trim();
                    label = label.replace(/GPS/g, 'GPS ');
                    
                    // Special formatting for some values
                    let displayValue = value;
                    if (typeof value === 'number') {
                        displayValue = value.toLocaleString();
                    }
                    
                    catHTML += `
                        <div class="metadata-row">
                            <span class="metadata-key">${label}</span>
                            <span class="metadata-value">${displayValue}</span>
                            <button class="copy-btn" onclick="copyValue('${key.replace(/'/g, "\\'")}')" title="Copy">
                                <i class="fas fa-copy"></i>
                            </button>
                        </div>
                    `;
                }
                catHTML += '</div>';
            }
            document.getElementById('categoriesContainer').innerHTML = catHTML || '<p style="color: var(--text-secondary);">Koi metadata nahi mila</p>';
            
            // Raw JSON
            document.getElementById('rawJson').textContent = JSON.stringify(data.all_raw || {}, null, 2);
        }
        
        // ---------- Utility Functions ----------
        function copyValue(key) {
            if (!metadataData) return;
            // Find value in all_raw
            const raw = metadataData.all_raw || {};
            const value = raw[key];
            if (value !== undefined) {
                navigator.clipboard.writeText(String(value)).then(() => {
                    showToast('✅ Copied: ' + key);
                });
            }
        }
        
        function copyAllData() {
            if (!metadataData) return;
            const text = JSON.stringify(metadataData.all_raw, null, 2);
            navigator.clipboard.writeText(text).then(() => {
                showToast('✅ All data copied!');
            });
        }
        
        function downloadJSON() {
            if (!metadataData) return;
            const json = JSON.stringify(metadataData.all_raw, null, 2);
            const blob = new Blob([json], {type: 'application/json'});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `metadata_${Date.now()}.json`;
            a.click();
            URL.revokeObjectURL(url);
            showToast('✅ JSON downloaded!');
        }
        
        function toggleRaw() {
            const raw = document.getElementById('rawJson');
            raw.style.display = raw.style.display === 'block' ? 'none' : 'block';
        }
        
        function toggleTheme() {
            document.body.classList.toggle('light-theme');
            const icon = document.querySelector('.theme-toggle i');
            if (document.body.classList.contains('light-theme')) {
                icon.className = 'fas fa-sun';
            } else {
                icon.className = 'fas fa-moon';
            }
        }
        
        function showToast(message, type = 'success') {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.style.display = 'block';
            toast.style.borderColor = type === 'error' ? '#ff4444' : 'var(--accent)';
            clearTimeout(toast._timeout);
            toast._timeout = setTimeout(() => {
                toast.style.display = 'none';
            }, 3000);
        }
        
        // ---------- Keyboard Shortcuts ----------
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'Enter') {
                document.getElementById('fileInput').click();
            }
            if (e.ctrlKey && e.key === 'j') {
                toggleRaw();
            }
        });
    </script>
</body>
</html>
'''

# ---------- FLASK ROUTES ----------
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/upload', methods=['POST'])
def upload_image():
    if 'image' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'Empty filename'}), 400
    
    # Allowed extensions
    allowed = {'jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'tif', 'webp', 
               'heic', 'heif', 'raw', 'cr2', 'nef', 'arw', 'orf', 'rw2', 'ico'}
    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in allowed:
        return jsonify({'error': f'Unsupported file: .{ext}'}), 400
    
    # Save temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{ext}') as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name
    
    try:
        result = extract_metadata(tmp_path)
        if 'error' in result:
            return jsonify(result)
        
        friendly = parse_metadata_to_readable(result['metadata'])
        return jsonify(friendly)
        
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

if __name__ == '__main__':
    print("""
    ╔═══════════════════════════════════════════════════════════════════╗
    ║                                                                   ║
    ║   📸 Smart Metadata Viewer v3.0                                  ║
    ║   ─────────────────────────────────────────────────────────────   ║
    ║   🔥 Professional Image Metadata Extractor                       ║
    ║   📡 Telegram: @Black_Hats_Hackers                              ║
    ║                                                                   ║
    ║   🌐 Server: http://127.0.0.1:5000                              ║
    ║   🛑 Press Ctrl+C to stop                                        ║
    ║                                                                   ║
    ╚═══════════════════════════════════════════════════════════════════╝
    """)
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
