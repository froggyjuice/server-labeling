import os
import sys
from datetime import datetime, timezone, timedelta

from flask import Flask, send_from_directory, request, jsonify, session, redirect, url_for, send_file
from flask_cors import CORS
from user import db, User, File, Label
from werkzeug.utils import secure_filename
from sqlalchemy import inspect

# static/index.html 파일을 웹에서 접근 가능하게 제공
app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))
app.config['SECRET_KEY'] = 'asdf#FGSgvasgf$5$WGT'

# CORS 설정: 다른 도메인에서의 요청 허용 (나중에 프론트엔드 추가 시 필요)
CORS(app, supports_credentials=True, origins=['http://localhost:5173'])

# 데이터베이스 설정
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(os.path.dirname(__file__), 'database', 'app.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# 파일 업로드 설정
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
ALLOWED_EXTENSIONS = {'txt', 'jpg', 'jpeg', 'png', 'dcm'}  # 허용할 파일 확장자 (텍스트 + 이미지 + DICOM)

def get_kst_now():
    """KST 기준 현재 시간 반환"""
    utc_now = datetime.now(timezone.utc)
    kst = timezone(timedelta(hours=9))
    return utc_now.astimezone(kst)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def init_database():
    """데이터베이스 초기화 및 마이그레이션"""
    with app.app_context():
        # 데이터베이스 엔진 생성
        engine = db.engine
        
        # 기존 테이블 확인
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        
        print(f"기존 테이블: {existing_tables}")
        
        # 필요한 테이블 목록
        required_tables = ['user', 'file', 'label']
        
        # 누락된 테이블 확인
        missing_tables = [table for table in required_tables if table not in existing_tables]
        
        if missing_tables:
            print(f"누락된 테이블: {missing_tables}")
            print("테이블을 생성합니다...")
            db.create_all()
            print("모든 테이블이 생성되었습니다.")
        else:
            print("모든 필요한 테이블이 존재합니다.")
            
            # 기존 테이블 구조 확인
            for table_name in required_tables:
                if table_name in existing_tables:
                    columns = inspector.get_columns(table_name)
                    print(f"\n{table_name} 테이블 구조:")
                    for column in columns:
                        print(f"  - {column['name']}: {column['type']}")
        
        # 샘플 데이터 추가 (선택사항)
        add_sample_data()

def add_sample_data():
    """샘플 데이터 추가 (데이터베이스가 비어있을 때만)"""
    try:
        # 사용자가 없으면 샘플 사용자 추가
        if User.query.count() == 0:
            sample_user = User(
                username="admin",
                email="admin@example.com"
            )
            sample_user.set_password("password123")
            db.session.add(sample_user)
            db.session.commit()
            print("샘플 사용자가 추가되었습니다: admin/password123")
        
        # 파일이 없으면 샘플 파일 정보 추가
        if File.query.count() == 0:
            # uploads 폴더의 파일들을 데이터베이스에 등록
            if os.path.exists(UPLOAD_FOLDER):
                for filename in os.listdir(UPLOAD_FOLDER):
                    if filename.lower().endswith(('.txt', '.jpg', '.jpeg', '.png', '.dcm')):
                        file_path = os.path.join(UPLOAD_FOLDER, filename)
                        file_size = os.path.getsize(file_path)
                        
                        # admin 사용자 찾기
                        admin_user = User.query.filter_by(username="admin").first()
                        if admin_user:
                            sample_file = File(
                                filename=filename,
                                file_path=file_path,
                                file_size=file_size,
                                uploaded_by=admin_user.id
                            )
                            db.session.add(sample_file)
                
                db.session.commit()
                print("샘플 파일 정보가 데이터베이스에 추가되었습니다.")
        
    except Exception as e:
        print(f"샘플 데이터 추가 중 오류: {e}")
        db.session.rollback()

# 데이터베이스 초기화
init_database()

# 회원가입 API 엔드포인트
@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.get_json()  # JSON 데이터를 Python 딕셔너리로 변환
        
        # 필수 필드 검증
        if not all(key in data for key in ['username', 'email', 'password']):
            return jsonify({'success': False, 'error': '모든 필드를 입력해주세요.'}), 400
        
        # 사용자명 중복 확인
        if User.query.filter_by(username=data['username']).first():
            return jsonify({'success': False, 'error': '이미 존재하는 사용자명입니다.'}), 400
        
        # 이메일 중복 확인
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'success': False, 'error': '이미 존재하는 이메일입니다.'}), 400
        
        # 새 사용자 생성
        new_user = User(
            username=data['username'],
            email=data['email']
        )
        new_user.set_password(data['password'])  # 비밀번호 해시화하여 저장
        
        db.session.add(new_user)  # 데이터베이스에 사용자 추가
        db.session.commit()  # 변경사항 저장
        
        return jsonify({'success': True, 'message': '회원가입이 완료되었습니다.'}), 201
        
    except Exception as e:
        db.session.rollback()  # 오류 발생 시 변경사항 되돌리기
        return jsonify({'success': False, 'error': '서버 오류가 발생했습니다.'}), 500

# 로그인 API 엔드포인트
@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        
        # 필수 필드 검증
        if not all(key in data for key in ['username', 'password']):
            return jsonify({'success': False, 'error': '사용자명과 비밀번호를 입력해주세요.'}), 400
        
        # 사용자 찾기
        user = User.query.filter_by(username=data['username']).first()
        
        if user and user.check_password(data['password']):  # 비밀번호 확인
            session['user_id'] = user.id  # 세션에 사용자 ID 저장 (세션은 사용자의 로그인 상태를 유지하는 서버 측 저장소입니다)
            return jsonify({
                'success': True, 
                'message': '로그인 성공!',
                'user': user.to_dict()
            }), 200
        else:
            return jsonify({'success': False, 'error': '사용자명 또는 비밀번호가 올바르지 않습니다.'}), 401
            
    except Exception as e:
        return jsonify({'success': False, 'error': '서버 오류가 발생했습니다.'}), 500

# 로그아웃 API 엔드포인트
@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)  # 세션에서 사용자 정보 제거
    return jsonify({'success': True, 'message': '로그아웃되었습니다.'}), 200

# 현재 사용자 정보 확인 API 엔드포인트
@app.route('/api/me', methods=['GET'])
def get_current_user():
    user_id = session.get('user_id')
    if user_id:
        user = User.query.get(user_id)
        if user:
            return jsonify({'success': True, 'user': user.to_dict()}), 200
    return jsonify({'success': False, 'error': '로그인이 필요합니다.'}), 401



# 파일 목록 조회 API 엔드포인트 (라벨링 정보 포함)
@app.route('/api/files', methods=['GET'])
def get_files():
    user_id = session.get('user_id')
    files = File.query.all()
    
    files_with_labels = []
    for file in files:
        file_dict = file.to_dict()
        
        # 현재 사용자의 라벨링 정보 추가
        if user_id:
            user_label = Label.query.filter_by(user_id=user_id, file_id=file.id).first()
            if user_label:
                file_dict['user_label'] = {
                    'disease': user_label.disease,
                    'view_type': user_label.view_type,
                    'code': user_label.code,
                    'description': user_label.description
                }
            else:
                file_dict['user_label'] = None
        else:
            file_dict['user_label'] = None
        
        # 전체 라벨링 통계 추가 (질환별)
        disease_stats = {}
        diseases = [
            'Respiratory Distress Syndrome', 'Bronchopulmonary Dysplasia', 
            'Pneumothorax', 'Pulmonary Interstitial Emphysema', 
            'Pneumomediastinum', 'Subcutaneous Emphysema', 
            'Pneumopericardium', 'Necrotizing Enterocolitis'
        ]
        
        for disease in diseases:
            count = Label.query.filter_by(file_id=file.id, disease=disease).count()
            disease_stats[disease] = count
        
        file_dict['disease_stats'] = disease_stats
        file_dict['total_labels'] = sum(disease_stats.values())
        
        files_with_labels.append(file_dict)
    
    return jsonify({
        'success': True,
        'files': files_with_labels
    }), 200

# 파일 다운로드 API 엔드포인트
@app.route('/api/files/<int:file_id>/download', methods=['GET'])
def download_file(file_id):
    file = File.query.get_or_404(file_id)
    return send_file(file.file_path, as_attachment=True, download_name=file.filename)

# 파일 내용 조회 API 엔드포인트
@app.route('/api/files/<int:file_id>/content', methods=['GET'])
def get_file_content(file_id):
    file = File.query.get_or_404(file_id)
    try:
        # 이미지 파일인지 확인
        if file.filename.lower().endswith(('.jpg', '.jpeg', '.png', '.dcm')):
            return jsonify({
                'success': True,
                'content': None,
                'filename': file.filename,
                'is_image': True,
                'image_url': f'/api/files/{file_id}/image'
            }), 200
        else:
            # 텍스트 파일인 경우
            with open(file.file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return jsonify({
                'success': True,
                'content': content,
                'filename': file.filename,
                'is_image': False
            }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': '파일을 읽을 수 없습니다.'}), 500

# 이미지 파일 표시 API 엔드포인트
@app.route('/api/files/<int:file_id>/image', methods=['GET'])
def get_image(file_id):
    file = File.query.get_or_404(file_id)
    try:
        # 파일 확장자에 따라 MIME 타입 결정
        filename_lower = file.filename.lower()
        if filename_lower.endswith('.dcm'):
            import io
            import pydicom
            from PIL import Image
            import numpy as np
            ds = pydicom.dcmread(file.file_path)
            arr = ds.pixel_array
            # Normalize to 0-255 for display
            arr = arr.astype(float)
            arr = (arr - arr.min()) / (arr.max() - arr.min()) * 255.0
            arr = arr.astype(np.uint8)
            if arr.ndim == 2:
                img = Image.fromarray(arr)
            else:
                img = Image.fromarray(arr[0])
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)
            return send_file(buf, mimetype='image/png')
        elif filename_lower.endswith('.png'):
            mimetype = 'image/png'
        elif filename_lower.endswith(('.jpg', '.jpeg')):
            mimetype = 'image/jpeg'
        else:
            mimetype = 'image/jpeg'  # 기본값
        return send_file(file.file_path, mimetype=mimetype)
    except Exception as e:
        return jsonify({'success': False, 'error': '이미지를 불러올 수 없습니다.'}), 500

# 라벨링 API 엔드포인트
@app.route('/api/label', methods=['POST'])
def add_label():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': '로그인이 필요합니다.'}), 401
    
    try:
        data = request.get_json()
        
        # 새로운 필수 필드들
        required_fields = ['file_id', 'disease', 'view_type', 'code', 'description']
        if not all(key in data for key in required_fields):
            return jsonify({'success': False, 'error': '모든 필수 필드를 입력해주세요.'}), 400
        
        file_id = data['file_id']
        disease = data['disease']
        view_type = data['view_type']
        code = data['code']
        description = data['description']
        
        # 질환 유효성 검사
        valid_diseases = [
            'Respiratory Distress Syndrome', 'Bronchopulmonary Dysplasia', 
            'Pneumothorax', 'Pulmonary Interstitial Emphysema', 
            'Pneumomediastinum', 'Subcutaneous Emphysema', 
            'Pneumopericardium', 'Necrotizing Enterocolitis'
        ]
        if disease not in valid_diseases:
            return jsonify({'success': False, 'error': '올바르지 않은 질환입니다.'}), 400
        
        # 사진 종류 유효성 검사
        valid_view_types = ['AP', 'LATDEQ', 'LAT', 'PA']
        if view_type not in valid_view_types:
            return jsonify({'success': False, 'error': '올바르지 않은 사진 종류입니다.'}), 400
        
        # 기존 라벨 확인 (업데이트식 구조 유지)
        existing_label = Label.query.filter_by(
            user_id=session['user_id'], 
            file_id=file_id
        ).first()
        
        if existing_label:
            # 기존 라벨이 있으면 업데이트 (덮어쓰기)
            existing_label.disease = disease
            existing_label.view_type = view_type
            existing_label.code = code
            existing_label.description = description
            existing_label.created_at = get_kst_now()  # KST 기준으로 업데이트
            message = f"라벨이 업데이트되었습니다: {disease} - {code}"
        else:
            # 새 라벨 생성
            new_label = Label(
                user_id=session['user_id'],
                file_id=file_id,
                disease=disease,
                view_type=view_type,
                code=code,
                description=description,
                created_at=get_kst_now()  # KST 기준으로 생성
            )
            db.session.add(new_label)
            message = f"라벨이 추가되었습니다: {disease} - {code}"
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': message
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': '서버 오류가 발생했습니다.'}), 500

# 라벨링 통계 API 엔드포인트
@app.route('/api/label/stats', methods=['GET'])
def get_label_stats():
    try:
        # 전체 통계
        total_labels = Label.query.count()
        
        # 질환별 통계
        disease_stats = {}
        diseases = [
            'Respiratory Distress Syndrome', 'Bronchopulmonary Dysplasia', 
            'Pneumothorax', 'Pulmonary Interstitial Emphysema', 
            'Pneumomediastinum', 'Subcutaneous Emphysema', 
            'Pneumopericardium', 'Necrotizing Enterocolitis'
        ]
        
        for disease in diseases:
            count = Label.query.filter_by(disease=disease).count()
            disease_stats[disease] = count
        
        # 사진 종류별 통계
        view_stats = {}
        view_types = ['AP', 'LATDEQ', 'LAT', 'PA']
        for view_type in view_types:
            count = Label.query.filter_by(view_type=view_type).count()
            view_stats[view_type] = count
        
        # 사용자별 통계
        user_stats = {}
        if 'user_id' in session:
            user_labels = Label.query.filter_by(user_id=session['user_id']).all()
            user_disease_stats = {}
            user_view_stats = {}
            
            for disease in diseases:
                count = sum(1 for label in user_labels if label.disease == disease)
                user_disease_stats[disease] = count
            
            for view_type in view_types:
                count = sum(1 for label in user_labels if label.view_type == view_type)
                user_view_stats[view_type] = count
            
            user_stats = {
                'total': len(user_labels),
                'diseases': user_disease_stats,
                'view_types': user_view_stats
            }
        
        return jsonify({
            'success': True,
            'total': {
                'total_labels': total_labels,
                'diseases': disease_stats,
                'view_types': view_stats
            },
            'user': user_stats
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': '서버 오류가 발생했습니다.'}), 500

# 대시보드 페이지 (로그인 후 리다이렉트될 페이지)
@app.route('/dashboard')
def dashboard():
    user_id = session.get('user_id')
    if not user_id:
        return redirect('/')  # 로그인되지 않은 경우 홈페이지로 리다이렉트
    
    user = User.query.get(user_id)
    if not user:
        session.pop('user_id', None)
        return redirect('/')
    
    # 간단한 대시보드 HTML 반환
    return f'''
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>대시보드</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background-color: #f5f5f5;
            }}
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            .header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 30px;
                padding-bottom: 20px;
                border-bottom: 1px solid #eee;
            }}
            .logout-btn {{
                padding: 10px 20px;
                background-color: #dc3545;
                color: white;
                border: none;
                border-radius: 5px;
                cursor: pointer;
            }}
            .logout-btn:hover {{
                background-color: #c82333;
            }}

            .file-list {{
                margin-top: 30px;
            }}
            .file-item {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 15px;
                border: 1px solid #eee;
                border-radius: 5px;
                margin-bottom: 10px;
            }}
            .file-info {{
                flex: 1;
            }}
            .file-actions {{
                display: flex;
                gap: 10px;
                align-items: center;
            }}
            .btn {{
                padding: 5px 10px;
                border: none;
                border-radius: 3px;
                cursor: pointer;
                text-decoration: none;
                color: white;
                font-size: 12px;
            }}
            .btn-primary {{
                background-color: #007bff;
            }}
            .btn-success {{
                background-color: #28a745;
            }}
            .btn-danger {{
                background-color: #dc3545;
            }}
            .btn-warning {{
                background-color: #ffc107;
                color: #212529;
            }}
            .label-buttons {{
                display: flex;
                gap: 5px;
            }}
            .label-btn {{
                padding: 3px 8px;
                border: none;
                border-radius: 3px;
                cursor: pointer;
                font-size: 11px;
            }}
            .like-btn {{
                background-color: #28a745;
                color: white;
            }}
            .dislike-btn {{
                background-color: #dc3545;
                color: white;
            }}
            .like-btn.active {{
                background-color: #155724;
            }}
            .dislike-btn.active {{
                background-color: #721c24;
            }}
            .stats {{
                display: flex;
                gap: 20px;
                margin-bottom: 20px;
                padding: 15px;
                background-color: #f8f9fa;
                border-radius: 5px;
            }}
            .stat-item {{
                text-align: center;
            }}
            .stat-number {{
                font-size: 24px;
                font-weight: bold;
                color: #007bff;
            }}
            .stat-label {{
                font-size: 12px;
                color: #666;
            }}
            .message {{
                margin: 10px 0;
                padding: 10px;
                border-radius: 5px;
                text-align: center;
            }}
            .success {{
                background-color: #d4edda;
                color: #155724;
            }}
            .error {{
                background-color: #f8d7da;
                color: #721c24;
            }}
            
            /* 모달 스타일 */
            .modal {{
                display: none;
                position: fixed;
                z-index: 1000;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0,0,0,0.5);
            }}
            
            .modal-content {{
                background-color: white;
                margin: 5% auto;
                padding: 0;
                border-radius: 10px;
                width: 80%;
                max-width: 600px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.3);
            }}
            
            .modal-header {{
                padding: 20px;
                border-bottom: 1px solid #eee;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            
            .modal-header h2 {{
                margin: 0;
                color: #333;
            }}
            
            .close {{
                color: #aaa;
                font-size: 28px;
                font-weight: bold;
                cursor: pointer;
            }}
            
            .close:hover {{
                color: #000;
            }}
            
            .modal-body {{
                padding: 20px;
            }}
            
            .form-group {{
                margin-bottom: 20px;
            }}
            
            .form-group label {{
                display: block;
                margin-bottom: 5px;
                font-weight: bold;
                color: #333;
            }}
            
            .form-group select,
            .form-group input,
            .form-group textarea {{
                width: 100%;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 5px;
                font-size: 14px;
            }}
            
            .form-group textarea {{
                height: 80px;
                resize: vertical;
            }}
            
            .symptom-checkbox {{
                margin: 5px 0;
            }}
            
            .symptom-checkbox input {{
                width: auto;
                margin-right: 10px;
            }}
            
            .modal-footer {{
                padding: 20px;
                border-top: 1px solid #eee;
                text-align: right;
            }}
            
            .modal-footer button {{
                margin-left: 10px;
            }}
            
            .btn-secondary {{
                background-color: #6c757d;
                color: white;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🏷️ 라벨링 시스템 - 환영합니다, {user.username}님!</h1>
                <button class="logout-btn" onclick="logout()">로그아웃</button>
            </div>
            
            <p>이메일: {user.email}</p>
            <p>가입일: {user.created_at.strftime('%Y년 %m월 %d일')}</p>
            
            <div class="stats">
                <div class="stat-item">
                    <div class="stat-number" id="totalFiles">0</div>
                    <div class="stat-label">총 파일</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number" id="totalLabels">0</div>
                    <div class="stat-label">총 라벨링</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number" id="userLabels">0</div>
                    <div class="stat-label">내 라벨링</div>
                </div>
            </div>
            

            
            <div id="message"></div>
            
            <div class="file-list">
                <h3>📋 라벨링할 파일 목록</h3>
                <div id="fileList">로딩 중...</div>
            </div>
        </div>
        
        <!-- 라벨링 모달 -->
        <div id="labelingModal" class="modal" style="display: none;">
            <div class="modal-content">
                <div class="modal-header">
                    <h2>🏷️ 라벨링</h2>
                    <span class="close" onclick="closeLabelingModal()">&times;</span>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label for="diseaseSelect">질환 선택:</label>
                        <select id="diseaseSelect" onchange="updateSymptoms()">
                            <option value="">질환을 선택하세요</option>
                            <option value="Respiratory Distress Syndrome">Respiratory Distress Syndrome</option>
                            <option value="Bronchopulmonary Dysplasia">Bronchopulmonary Dysplasia</option>
                            <option value="Pneumothorax">Pneumothorax</option>
                            <option value="Pulmonary Interstitial Emphysema">Pulmonary Interstitial Emphysema</option>
                            <option value="Pneumomediastinum">Pneumomediastinum</option>
                            <option value="Subcutaneous Emphysema">Subcutaneous Emphysema</option>
                            <option value="Pneumopericardium">Pneumopericardium</option>
                            <option value="Necrotizing Enterocolitis">Necrotizing Enterocolitis</option>
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label for="viewTypeSelect">사진 종류:</label>
                        <select id="viewTypeSelect">
                            <option value="">사진 종류를 선택하세요</option>
                            <option value="AP">AP</option>
                            <option value="LATDEQ">LATDEQ</option>
                            <option value="LAT">LAT</option>
                            <option value="PA">PA</option>
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label>흉부 X선 소견 (복수 선택 가능):</label>
                        <div id="symptomsContainer">
                            <p>질환을 먼저 선택해주세요.</p>
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label for="codeInput">번호:</label>
                        <input type="text" id="codeInput" placeholder="예: RDS_1, RDS_2" readonly>
                    </div>
                    
                    <div class="form-group">
                        <label for="descriptionInput">최종 소견:</label>
                        <textarea id="descriptionInput" placeholder="선택된 소견들이 자동으로 입력됩니다." readonly></textarea>
                    </div>
                </div>
                <div class="modal-footer">
                    <button onclick="submitLabeling()" class="btn btn-primary">라벨링 저장</button>
                    <button onclick="closeLabelingModal()" class="btn btn-secondary">취소</button>
                </div>
            </div>
        </div>
        
        <script>
            // 파일 목록 로드
            function loadFiles() {{
                fetch('/api/files')
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        displayFiles(data.files);
                        updateStats(data.files);
                    }}
                }})
                .catch(error => {{
                    console.error('파일 목록 로드 실패:', error);
                }});
            }}
            
            // 통계 업데이트
            function updateStats(files) {{
                const totalFiles = files.length;
                const totalLabels = files.reduce((sum, file) => sum + file.total_labels, 0);
                const userLabels = files.filter(file => file.user_label).length;
                
                document.getElementById('totalFiles').textContent = totalFiles;
                document.getElementById('totalLabels').textContent = totalLabels;
                document.getElementById('userLabels').textContent = userLabels;
            }}
            
            // 파일 목록 표시
            function displayFiles(files) {{
                const fileList = document.getElementById('fileList');
                if (files.length === 0) {{
                    fileList.innerHTML = '<p>업로드된 파일이 없습니다.</p>';
                    return;
                }}
                
                fileList.innerHTML = files.map(file => {{
                    const isImage = file.filename.toLowerCase().endsWith('.jpg') || 
                                   file.filename.toLowerCase().endsWith('.jpeg') || 
                                   file.filename.toLowerCase().endsWith('.png');
                    
                    // 질환별 라벨링 통계 표시
                    const diseaseStats = file.disease_stats || {{}};
                    const totalLabels = file.total_labels || 0;
                    
                    return `
                        <div class="file-item">
                            <div class="file-info">
                                <strong>${{file.filename}}</strong><br>
                                <small>업로드: ${{file.uploaded_by}} | 크기: ${{(file.file_size / 1024).toFixed(1)}}KB</small><br>
                                <small>라벨링 기록: ${{file.user_label ? '✅' : '✖️'}}</small>
                                ${{isImage ? `<br><img src="/api/files/${{file.id}}/image" style="max-width: 200px; max-height: 150px; margin-top: 10px; border-radius: 5px;">` : ''}}
                            </div>
                            <div class="file-actions">
                                <div class="label-buttons">
                                    <button class="label-btn like-btn" onclick="openLabelingModal(${{file.id}})">🏷️ 라벨링</button>
                                </div>
                                <button class="btn btn-primary" onclick="viewContent(${{file.id}})">${{isImage ? '이미지보기' : '내용보기'}}</button>
                            </div>
                        </div>
                    `;
                }}).join('');
            }}
            
            // 전역 변수
            let currentFileId = null;
            
            // 라벨링 모달 열기
            function openLabelingModal(fileId) {{
                currentFileId = fileId;
                document.getElementById('labelingModal').style.display = 'block';
                resetModal();
            }}
            
            // 모달 닫기
            function closeLabelingModal() {{
                document.getElementById('labelingModal').style.display = 'none';
                currentFileId = null;
            }}
            
            // 모달 초기화
            function resetModal() {{
                document.getElementById('diseaseSelect').value = '';
                document.getElementById('viewTypeSelect').value = '';
                document.getElementById('codeInput').value = '';
                document.getElementById('descriptionInput').value = '';
                document.getElementById('symptomsContainer').innerHTML = '<p>질환을 먼저 선택해주세요.</p>';
            }}
            
            // 질환 선택에 따른 소견 업데이트
            function updateSymptoms() {{
                const disease = document.getElementById('diseaseSelect').value;
                const container = document.getElementById('symptomsContainer');
                
                if (!disease) {{
                    container.innerHTML = '<p>질환을 먼저 선택해주세요.</p>';
                    return;
                }}
                
                const symptoms = getSymptomsByDisease(disease);
                let html = '';
                
                symptoms.forEach(symptom => {{
                    html += `
                        <div class="symptom-checkbox">
                            <input type="checkbox" id="${{symptom.code}}" value="${{symptom.code}}" onchange="updateCodeAndDescription()">
                            <label for="${{symptom.code}}">${{symptom.description}}</label>
                        </div>
                    `;
                }});
                
                container.innerHTML = html;
            }}
            
            // 질환별 소견 데이터
            function getSymptomsByDisease(disease) {{
                const symptoms = {{
                    'Respiratory Distress Syndrome': [
                        {{code: 'RDS_1', description: '폐용적의 감소(Hypoventilation)'}},
                        {{code: 'RDS_2', description: '폐포 허탈로 인한 과립성 음영 (Ground Glass Appearance)'}},
                        {{code: 'RDS_3', description: '기관지 내 음영 (Air-bronchogram)'}},
                        {{code: 'RDS_4', description: '폐 전체 white-out 양상, 심장 경계 불분명'}}
                    ],
                    'Bronchopulmonary Dysplasia': [
                        {{code: 'BPD_1', description: '미만성 음영 증가'}},
                        {{code: 'BPD_2', description: '폐용적 정상 또는 감소'}},
                        {{code: 'BPD_3', description: '전반적 과팽창'}},
                        {{code: 'BPD_4', description: '무기폐와 과투과성 부위 혼재'}}
                    ],
                    'Pneumothorax': [
                        {{code: 'PTX_1', description: '종격동의 반대쪽 이동(Chest AP)'}},
                        {{code: 'PTX_2', description: '편평해진 횡격막(기흉쪽)'}},
                        {{code: 'PTX_3', description: '기흉 쪽 폐의 허탈'}},
                        {{code: 'PTX_4', description: 'Lateral decubitus에서 소기흉 확인 가능'}},
                        {{code: 'PTX_5', description: 'Cross-table lateral: 팬케이크 모양의 공기'}}
                    ],
                    'Pulmonary Interstitial Emphysema': [
                        {{code: 'PIE_1', description: '낭성 또는 선상의 공기 음영 (국소/양폐)'}}
                    ],
                    'Pneumomediastinum': [
                        {{code: 'PMS_1', description: '흉부 중앙의 공기 음영'}},
                        {{code: 'PMS_2', description: '흉선 주위의 공기, "요트의 돛" (sail sign)'}},
                        {{code: 'PMS_3', description: 'Lateral view에서 명확히 관찰됨'}}
                    ],
                    'Subcutaneous Emphysema': [
                        {{code: 'SEM_1', description: '-'}}
                    ],
                    'Pneumopericardium': [
                        {{code: 'PPC_1', description: '심장하부의 공기 음영'}}
                    ],
                    'Necrotizing Enterocolitis': [
                        {{code: 'NEC_1', description: '장 마비 (Ileus)'}},
                        {{code: 'NEC_2', description: '장벽 내 공기 (Pneumatosis Intestinalis)'}},
                        {{code: 'NEC_3', description: 'Portal 또는 Hepatic vein gas'}},
                        {{code: 'NEC_4', description: '복수 (Ascites)'}},
                        {{code: 'NEC_5', description: '복강 내 공기 (Pneumoperitoneum)'}}
                    ]
                }};
                
                return symptoms[disease] || [];
            }}
            
            // 선택된 소견에 따라 코드와 설명 업데이트
            function updateCodeAndDescription() {{
                const checkboxes = document.querySelectorAll('#symptomsContainer input[type="checkbox"]:checked');
                const codes = [];
                const descriptions = [];
                
                checkboxes.forEach(checkbox => {{
                    codes.push(checkbox.value);
                    const label = document.querySelector(`label[for="${{checkbox.value}}"]`);
                    descriptions.push(label.textContent);
                }});
                
                document.getElementById('codeInput').value = codes.join(', ');
                document.getElementById('descriptionInput').value = descriptions.join('\\n');
            }}
            
            // 라벨링 제출
            function submitLabeling() {{
                const disease = document.getElementById('diseaseSelect').value;
                const viewType = document.getElementById('viewTypeSelect').value;
                const code = document.getElementById('codeInput').value;
                const description = document.getElementById('descriptionInput').value;
                
                if (!disease || !viewType || !code || !description) {{
                    showMessage('모든 필드를 입력해주세요.', 'error');
                    return;
                }}
                
                addLabel(currentFileId, disease, viewType, code, description);
                closeLabelingModal();
            }}
            
            // 라벨링 추가
            function addLabel(fileId, disease, viewType, code, description) {{
                fetch('/api/label', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json'
                    }},
                    body: JSON.stringify({{
                        file_id: fileId,
                        disease: disease,
                        view_type: viewType,
                        code: code,
                        description: description
                    }})
                }})
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        showMessage(data.message, 'success');
                        loadFiles(); // 파일 목록 새로고침
                    }} else {{
                        showMessage(data.error || '라벨링 실패', 'error');
                    }}
                }})
                .catch(error => {{
                    showMessage('서버 오류가 발생했습니다.', 'error');
                }});
            }}
            

            
            // 파일 내용 보기
            function viewContent(fileId) {{
                fetch(`/api/files/${{fileId}}/content`)
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        if (data.is_image) {{
                            // 이미지 파일인 경우 새 창에서 열기
                            window.open(`/api/files/${{fileId}}/image`, '_blank');
                        }} else {{
                            // 텍스트 파일인 경우 알림으로 표시
                            alert(`파일명: ${{data.filename}}\\n\\n내용:\\n${{data.content}}`);
                        }}
                    }} else {{
                        showMessage(data.error || '파일을 읽을 수 없습니다.', 'error');
                    }}
                }})
                .catch(error => {{
                    showMessage('서버 오류가 발생했습니다.', 'error');
                }});
            }}
            
            function showMessage(message, type) {{
                const messageDiv = document.getElementById('message');
                messageDiv.textContent = message;
                messageDiv.className = `message ${{type}}`;
                setTimeout(() => {{
                    messageDiv.textContent = '';
                    messageDiv.className = '';
                }}, 3000);
            }}
            
            function logout() {{
                fetch('/api/logout', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json'
                    }}
                }})
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        window.location.href = '/';
                    }}
                }});
            }}
            
            // 페이지 로드 시 파일 목록 로드
            loadFiles();
        </script>
    </body>
    </html>
    '''

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static_folder_path = app.static_folder
    if static_folder_path is None:
            return "Static folder not configured", 404

    if path != "" and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)
    else:
        index_path = os.path.join(static_folder_path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, 'index.html')
        else:
            return "index.html not found", 404


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
