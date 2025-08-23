import os
import sys
from datetime import datetime, timezone, timedelta

from flask import Flask, send_from_directory, request, jsonify, session, redirect, url_for, send_file
from flask_cors import CORS
from user import db, User, File, Label, ensure_database_permissions
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
        # SSH 환경에서 데이터베이스 권한 문제 해결
        try:
            # 데이터베이스 권한 확인
            ensure_database_permissions()
            
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
            
        except Exception as e:
            print(f"❌ 데이터베이스 초기화 중 오류: {e}")
            print(f"오류 타입: {type(e).__name__}")
            import traceback
            print(f"상세 오류: {traceback.format_exc()}")
            print("데이터베이스 권한 문제가 발생했습니다.")
            print("SSH 환경에서 데이터베이스 파일 권한을 확인하세요.")

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
        print(f"❌ 회원가입 오류: {e}")
        print(f"오류 타입: {type(e).__name__}")
        import traceback
        print(f"상세 오류: {traceback.format_exc()}")
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

# 파일 목록 조회 API 엔드포인트 (페이지네이션 + 지연 로딩 적용)
@app.route('/api/files', methods=['GET'])
def get_files():
    user_id = session.get('user_id')
    
    # 페이지네이션 파라미터
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)  # 한 번에 20개씩
    tab = request.args.get('tab', 'all')  # 탭 필터링
    
    # 기본 쿼리 (파일명 오름차순 정렬)
    query = File.query.order_by(File.filename.asc())
    
    # 탭별 필터링
    if tab == 'completed':
        # 완료된 파일만 (라벨이 있는 파일)
        query = query.join(Label, File.id == Label.file_id).filter(Label.user_id == user_id)
    elif tab == 'incomplete':
        # 미완료 파일만 (라벨이 없는 파일)
        subquery = db.session.query(Label.file_id).filter(Label.user_id == user_id).subquery()
        query = query.filter(~File.id.in_(subquery))
    
    # 페이지네이션 적용
    pagination = query.paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
    
    files_with_labels = []
    for file in pagination.items:
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
        
        # 라벨링 통계는 별도 API로 분리하여 성능 향상
        file_dict['has_labels'] = Label.query.filter_by(file_id=file.id).count() > 0
        
        files_with_labels.append(file_dict)
    
    return jsonify({
        'success': True,
        'files': files_with_labels,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': pagination.total,
            'pages': pagination.pages,
            'has_next': pagination.has_next,
            'has_prev': pagination.has_prev
        }
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

# 이미지 파일 표시 API 엔드포인트 (실시간 DICOM 변환)
@app.route('/api/files/<int:file_id>/image', methods=['GET'])
def get_image(file_id):
    file = File.query.get_or_404(file_id)
    try:
        # DICOM 파일인지 확인
        if file.filename.lower().endswith('.dcm'):
            # 실시간 DICOM → PNG 변환
            import pydicom
            from PIL import Image
            import numpy as np
            import io
            
            # DICOM 파일 읽기
            ds = pydicom.dcmread(file.file_path)
            arr = ds.pixel_array
            
            # 정규화 (0-255 범위로)
            arr = arr.astype(float)
            arr = (arr - arr.min()) / (arr.max() - arr.min()) * 255.0
            arr = arr.astype(np.uint8)
            
            # 2D 배열로 변환 (3D인 경우 첫 번째 슬라이스 사용)
            if arr.ndim == 2:
                img = Image.fromarray(arr)
            else:
                img = Image.fromarray(arr[0])
            
            # 메모리에서 PNG로 변환
            img_io = io.BytesIO()
            img.save(img_io, 'PNG')
            img_io.seek(0)
            
            # PNG 데이터를 브라우저로 전송 (파일 저장 안함)
            return send_file(img_io, mimetype='image/png')
            
        else:
            # 일반 이미지 파일 (PNG, JPG 등)
            filename_lower = file.filename.lower()
            if filename_lower.endswith('.png'):
                mimetype = 'image/png'
            elif filename_lower.endswith(('.jpg', '.jpeg')):
                mimetype = 'image/jpeg'
            else:
                mimetype = 'image/jpeg'  # 기본값
            
            return send_file(file.file_path, mimetype=mimetype)
            
    except Exception as e:
        print(f"❌ 이미지 처리 오류: {e}")
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
        diseases = data['disease']  # 이제 리스트 형태로 받음
        view_type = data['view_type']
        code = data['code']
        description = data['description']
        
        # 질환 유효성 검사 (리스트 형태로 처리)
        valid_diseases = [
            'Respiratory Distress Syndrome', 'Bronchopulmonary Dysplasia', 
            'Pneumothorax', 'Pulmonary Interstitial Emphysema', 
            'Pneumomediastinum', 'Subcutaneous Emphysema', 
            'Pneumopericardium', 'Necrotizing Enterocolitis'
        ]
        
        # disease가 리스트인지 확인하고 유효성 검사
        if isinstance(diseases, str):
            # 기존 단일 질환 형태와의 호환성을 위해
            diseases = [diseases]
        
        for disease in diseases:
            if disease not in valid_diseases:
                return jsonify({'success': False, 'error': f'올바르지 않은 질환입니다: {disease}'}), 400
        
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
            existing_label.set_diseases(diseases)  # 새로운 메서드 사용
            existing_label.view_type = view_type
            existing_label.code = code
            existing_label.description = description
            existing_label.created_at = get_kst_now()  # KST 기준으로 업데이트
            disease_str = ', '.join(diseases)
            message = f"라벨이 업데이트되었습니다: {disease_str} - {code}"
        else:
            # 새 라벨 생성
            new_label = Label(
                user_id=session['user_id'],
                file_id=file_id,
                view_type=view_type,
                code=code,
                description=description,
                created_at=get_kst_now()  # KST 기준으로 생성
            )
            new_label.set_diseases(diseases)  # 새로운 메서드 사용
            db.session.add(new_label)
            disease_str = ', '.join(diseases)
            message = f"라벨이 추가되었습니다: {disease_str} - {code}"
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': message
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': '서버 오류가 발생했습니다.'}), 500

# 사용자 라벨링 기록 조회 API
@app.route('/api/label/history/<int:file_id>', methods=['GET'])
def get_user_label_history(file_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': '로그인이 필요합니다.'}), 401
    
    try:
        # 현재 사용자의 해당 파일에 대한 라벨링 기록 조회
        label = Label.query.filter_by(
            user_id=session['user_id'], 
            file_id=file_id
        ).first()
        
        if label:
            return jsonify({
                'success': True,
                'has_history': True,
                'label': {
                    'disease': label.get_diseases(),  # 리스트 형태로 반환
                    'disease_string': ', '.join(label.get_diseases()),  # 문자열 형태로도 제공
                    'view_type': label.view_type,
                    'code': label.code,
                    'description': label.description,
                    'created_at': label.created_at.strftime('%Y-%m-%d %H:%M:%S') if label.created_at else None
                }
            }), 200
        else:
            return jsonify({
                'success': True,
                'has_history': False,
                'message': '이 파일에 대한 라벨링 기록이 없습니다.'
            }), 200
            
    except Exception as e:
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
            # JSON 형태로 저장된 질환들을 검색하기 위해 LIKE 연산자 사용
            count = Label.query.filter(Label.disease.like(f'%"{disease}"%')).count()
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
                count = sum(1 for label in user_labels if label.has_disease(disease))
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

# 라벨링 방법 도움말 API 엔드포인트
@app.route('/api/help', methods=['GET'])
def get_help():
    try:
        help_content = {
            'success': True,
            'help': {
                'system_intro': {
                    'title': '신생아 주요 질환 X-ray 소견 라벨링 시스템이란?',
                    'content': '''
                    신생아 질환 진단은 임상 소견, 증상, 그리고 X-ray 소견을 종합적으로 고려해야 합니다. 하지만 기존 인공지능 진단 소프트웨어는 X-ray 영상 단독 진단에 치우쳐 명확한 근거 제시가 어렵다는 한계가 있습니다.

                    이러한 한계를 극복하기 위해, 본 라벨링 시스템은 전문의가 X-ray 영상에서만 파악 가능한 특징적인 소견을 중심으로 신생아 주요 질환을 1차적으로 분류하고자 합니다.

                    궁극적인 목표는 이 X-ray 소견들을 기반으로 질병을 예측하고, 의료 기록 작성을 돕는 보조 도구를 개발하는 것입니다.

                    본 시스템에서 다루는 신생아 주요 질환과 각 질환별 X-ray 영상에서 관찰되는 고유한 패턴(X-ray 영상의 특징 여부만 체크)은 다음과 같습니다.

                    1. 신생아 호흡 곤란 증후군 (RDS: Respiratory Distress Syndrome)
                    RDS_1: 폐 용적 감소 (Hypoventilation)
                    RDS_2: 폐포 허탈로 인한 과립성 음영 (ground glass appearance)
                    RDS_3: Air-bronchogram (기관지 내 음영)
                    RDS_4: 폐 전체 white-out 양상, 심장 경계 불분명

                    2. 기관지폐이형성증 (BPD: Bronchopulmonary Dysplasia)
                    BPD_1: 미만성 음영 증가
                    BPD_2: 폐 용적 정상 또는 감소
                    BPD_3: 전반적 폐 과팽창
                    BPD_4: 무기폐와 과투과성 부위 혼재

                    3. 기흉 (Pneumothorax)
                    PTX_1: 종격동의 반대쪽 이동 (Chest AP)
                    PTX_2: 편평해진 횡격막 (기흉 쪽)
                    PTX_3: 기흉 쪽 폐의 허탈
                    PTX_4: Lateral decubitus에서 소기흉 확인 가능
                    PTX_5: Cross-table lateral: 팬케이크 모양의 공기

                    4. 폐쇄성 간질성 폐기종 (PIE: Pulmonary Interstitial Emphysema)
                    PIE_1: 낭성 또는 선상의 공기 음영 (국소/양폐)

                    5. 종격동 기종 (Pneumomediastinum)
                    PMS_1: 흉부 중앙의 공기 음영
                    PMS_2: 흉선 주위의 공기 → "요트의 돛"(sail sign)
                    PMS_3: Lateral view에서 명확하게 관찰됨

                    6. 피하기종 (Subcutaneous Emphysema)
                    STE_1: 피하 조직 내 불규칙한 방사선 투과성 음영이 관찰됩니다.

                    7. 심낭 기종 (Pneumopericardium)
                    PPC_1: 심장 하부의 공기 음영 (심장 전체를 둘러싸는 공기 음영이 더 특징적일 수 있습니다.)

                    8. 괴사성 장염 (NEC: Necrotizing Enterocolitis)
                    NEC_1: Ileus (장 마비)
                    NEC_2: Pneumatosis intestinalis (장벽 내 공기)
                    NEC_3: Portal 또는 hepatic vein gas
                    NEC_4: Ascites (복수)
                    NEC_5: Pneumoperitoneum (복강 내 공기)
                    '''
                },
                'labeling_guide': {
                    'title': '라벨링 방법 도움말',
                    'steps': [
                        {
                            'step': 1,
                            'action': '이미지보기',
                            'description': '이미지를 새 창에서 확인합니다.',
                            'button_style': 'blue',
                            'emoji': '🩻'
                        },
                        {
                            'step': 2,
                            'action': '라벨링',
                            'description': '라벨링을 위한 팝업창을 엽니다.',
                            'button_style': 'green',
                            'emoji': '🏷️',
                            'sub_steps': [
                                {
                                    'title': '질환 선택',
                                    'description': '질환을 선택하시면 "흉부 X선 소견(복수 선택 가능)"이 나오며, 해당되는 소견을 선택해주시면 됩니다. 만약 X-ray 소견이 없을 경우 "정상"으로 체크해주시면 됩니다.',
                                    'options': ['정상', 'RDS', 'BPD', 'Pneumothorax', 'PIE', 'Pneumomediastinum', 'Subcutaneous Emphysema', 'Pneumopericardium', 'NEC']
                                },
                                {
                                    'title': '사진 종류',
                                    'description': '사진의 종류를 선택해주시면 됩니다.',
                                    'options': ['AP', 'LATDEQ', 'LAT', 'PA']
                                },
                                {
                                    'title': '번호',
                                    'description': '자동으로 기입됩니다.'
                                },
                                {
                                    'title': '최종 소견',
                                    'description': '자동으로 기입됩니다.'
                                }
                            ]
                        },
                        {
                            'step': 3,
                            'action': '기록보기',
                            'description': '이전 라벨링 기록을 확인할 수 있습니다.',
                            'button_style': 'teal',
                            'emoji': '📋'
                        }
                    ]
                }
            }
        }
        
        return jsonify(help_content), 200
        
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
            
            .header-buttons {{
                display: flex;
                gap: 10px;
                align-items: center;
            }}
            
            .help-btn {{
                padding: 10px 20px;
                background-color: #17a2b8;
                color: white;
                border: none;
                border-radius: 5px;
                cursor: pointer;
            }}
            
            .help-btn:hover {{
                background-color: #138496;
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
            .history-btn {{
                background-color: #17a2b8;
                color: white;
            }}
            .like-btn:hover {{
                background-color: #218838;
            }}
            .history-btn:hover {{
                background-color: #138496;
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
                width: 95%;
                max-width: 700px;
                max-height: 80vh;
                overflow-y: auto;
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
                max-width: 100%;
                overflow-x: hidden;
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
            
            /* 흉부 X선 소견 제목 스타일 */
            .symptom-title {{
                font-size: 16px;
                font-weight: bold;
                margin-bottom: 8px;
                margin-top: 10px;
                color: #222;
            }}
            
            .symptom-title .subtitle {{
                font-size: 12px;
                font-weight: normal;
                color: #666;
            }}
            
            .symptoms-table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 10px;
            }}

            .symptom-row {{
                border-bottom: 1px solid #f0f0f0;
            }}

            .symptom-row:hover {{
                background-color: #f8f9fa;
            }}

            .symptom-label {{
                padding: 8px 12px;
                text-align: left;
                vertical-align: middle;
                width: 85%;
            }}

            .symptom-label label {{
                font-size: 13px;
                color: #333;
                line-height: 1.4;
                font-weight: normal;
                cursor: pointer;
                display: block;
            }}

            .symptom-disease {{
                padding: 8px 12px;
                text-align: center;
                vertical-align: middle;
                width: 15%;
                font-weight: bold;
                color: #007bff;
                background-color: #f8f9fa;
            }}
            
            .symptom-checkbox {{
                padding: 8px 12px;
                text-align: center;
                vertical-align: middle;
                width: 15%;
            }}

            .symptom-checkbox input {{
                width: 16px;
                height: 16px;
                margin: 0;
                cursor: pointer;
            }}
            
            .required {{
                color: #dc3545;
                font-weight: bold;
            }}
            
            .form-group select,
            .form-group input,
            .form-group textarea {{
                width: 100%;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 5px;
                font-size: 14px;
                box-sizing: border-box;
            }}
            
            .form-group textarea {{
                height: 80px;
                resize: vertical;
            }}
            
            .modal-footer {{
                padding: 20px 24px 24px 24px;
                border-top: 1px solid #eee;
                text-align: right;
                display: flex;
                justify-content: flex-end;
                gap: 12px;
            }}
            
            .modal-footer button {{
                margin-left: 0;
            }}
            
            .btn-secondary {{
                background-color: #6c757d;
                color: white;
            }}
            
            /* 탭 스타일 */
            .tab-container {{
                margin-top: 20px;
            }}
            
            .tab-buttons {{
                display: flex;
                border-bottom: 2px solid #dee2e6;
                margin-bottom: 20px;
            }}
            
            .tab-btn {{
                padding: 12px 24px;
                background-color: #f8f9fa;
                border: none;
                border-bottom: 3px solid transparent;
                cursor: pointer;
                font-size: 14px;
                font-weight: 500;
                color: #6c757d;
                transition: all 0.3s ease;
            }}
            
            .tab-btn:hover {{
                background-color: #e9ecef;
                color: #495057;
            }}
            
            .tab-btn.active {{
                background-color: #007bff;
                color: white;
                border-bottom-color: #007bff;
            }}
            
            .tab-content {{
                min-height: 200px;
            }}
            
            /* 페이지네이션 스타일 */
            .pagination {{
                display: flex;
                justify-content: center;
                align-items: center;
                gap: 10px;
                margin-top: 20px;
                padding: 15px;
            }}
            
            .pagination button {{
                padding: 8px 16px;
                border: 1px solid #ddd;
                background-color: white;
                color: #333;
                cursor: pointer;
                border-radius: 4px;
                transition: all 0.3s ease;
            }}
            
            .pagination button:hover {{
                background-color: #f8f9fa;
                border-color: #007bff;
            }}
            
            .pagination button:disabled {{
                background-color: #f8f9fa;
                color: #6c757d;
                cursor: not-allowed;
                border-color: #ddd;
            }}
            
            .pagination span {{
                font-weight: bold;
                color: #333;
            }}
            
            /* 지연 로딩 이미지 스타일 */
            .lazy {{
                opacity: 0;
                transition: opacity 0.3s ease;
            }}
            
            .lazy.loaded {{
                opacity: 1;
            }}
            
            /* 로딩 스피너 */
            .loading {{
                text-align: center;
                padding: 20px;
                color: #666;
            }}
            
            .loading::after {{
                content: '';
                display: inline-block;
                width: 20px;
                height: 20px;
                border: 3px solid #f3f3f3;
                border-top: 3px solid #007bff;
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin-left: 10px;
            }}
            
            @keyframes spin {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}
            

            
            /* 도움말 스타일 */
            .help-section {{
                margin-bottom: 30px;
                padding: 20px;
                background-color: #f8f9fa;
                border-radius: 8px;
                border-left: 4px solid #17a2b8;
            }}
            
            .help-section h3 {{
                color: #2c3e50;
                margin-bottom: 15px;
                font-size: 20px;
            }}
            
            .help-steps {{
                margin-top: 20px;
            }}
            
            .help-step {{
                background-color: white;
                border-radius: 8px;
                padding: 15px;
                margin-bottom: 15px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                border-left: 4px solid #28a745;
            }}
            
            .help-step h4 {{
                color: #2c3e50;
                margin-bottom: 10px;
                font-size: 16px;
            }}
            
            .help-step .step-number {{
                background-color: #28a745;
                color: white;
                border-radius: 50%;
                width: 25px;
                height: 25px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
                margin-right: 10px;
            }}
            
            .help-sub-steps {{
                margin-top: 15px;
                padding-left: 20px;
            }}
            
            .help-sub-step {{
                background-color: #f8f9fa;
                border-radius: 5px;
                padding: 10px;
                margin-bottom: 10px;
                border-left: 3px solid #17a2b8;
            }}
            
            .help-sub-step h5 {{
                color: #495057;
                margin-bottom: 5px;
                font-size: 14px;
                font-weight: 600;
            }}
            
            .help-options {{
                display: flex;
                flex-wrap: wrap;
                gap: 5px;
                margin-top: 5px;
            }}
            
            .help-option {{
                background-color: #007bff;
                color: white;
                padding: 3px 8px;
                border-radius: 12px;
                font-size: 12px;
                font-weight: 500;
            }}
            
            /* 도움말 액션 버튼 스타일 */
            .help-action-btn {{
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 500;
                color: white;
                cursor: default;
                margin-left: 10px;
                display: inline-flex;
                align-items: center;
                gap: 4px;
            }}
            
            .help-btn-blue {{
                background-color: #007bff;
            }}
            
            .help-btn-green {{
                background-color: #28a745;
            }}
            
            .help-btn-teal {{
                background-color: #17a2b8;
            }}
            
            .help-btn-default {{
                background-color: #6c757d;
            }}
            
            /* 질환 체크박스 스타일 */
            .disease-checkboxes {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 10px;
                margin-top: 10px;
            }}
            
            .disease-option {{
                display: flex;
                align-items: center;
                padding: 8px 12px;
                border: 1px solid #ddd;
                border-radius: 5px;
                background-color: #f8f9fa;
                transition: all 0.2s ease;
            }}
            
            .disease-option:hover {{
                background-color: #e9ecef;
                border-color: #007bff;
            }}
            
            .disease-option input[type="checkbox"] {{
                margin-right: 8px;
                width: 16px;
                height: 16px;
                cursor: pointer;
            }}
            
            .disease-option label {{
                cursor: pointer;
                font-size: 14px;
                color: #333;
                margin: 0;
                flex: 1;
            }}
            
            .disease-option input[type="checkbox"]:checked + label {{
                font-weight: bold;
                color: #007bff;
            }}
            
            /* 도움말 탭 스타일 */
            .help-tab-buttons {{
                display: flex;
                border-bottom: 2px solid #dee2e6;
                margin-bottom: 20px;
            }}
            
            .help-tab-btn {{
                padding: 12px 24px;
                background-color: #f8f9fa;
                border: none;
                border-bottom: 3px solid transparent;
                cursor: pointer;
                font-size: 14px;
                font-weight: 500;
                color: #6c757d;
                transition: all 0.3s ease;
                flex: 1;
            }}
            
            .help-tab-btn:hover {{
                background-color: #e9ecef;
                color: #495057;
            }}
            
            .help-tab-btn.active {{
                background-color: #17a2b8;
                color: white;
                border-bottom-color: #17a2b8;
            }}
            
            .help-tab-content {{
                min-height: 400px;
            }}
            
            .help-tab {{
                display: none;
            }}
            
            .help-tab.active {{
                display: block;
            }}
            
            .label-btn.image-btn {{
                background-color: #007bff;
                color: #fff;
                border: none;
                border-radius: 3px;
                padding: 3px 12px;
                font-size: 11px;
                margin-left: 2px;
                display: inline-flex;
                align-items: center;
                gap: 4px;
                cursor: pointer;
                transition: background 0.2s;
            }}
            .label-btn.image-btn:hover {{
                background-color: #0056b3;
            }}

            /* 도움말 개선 스타일 */
            .help-section {{
                margin-bottom: 30px;
                padding: 25px;
                background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                border-radius: 12px;
                border-left: 5px solid #17a2b8;
                box-shadow: 0 4px 15px rgba(0,0,0,0.08);
            }}

            .help-section h3 {{ 
                color: #2c3e50;
                margin-bottom: 20px;
                font-size: 24px;
                font-weight: 700;
                text-align: center;
                padding-bottom: 15px;
                border-bottom: 2px solid #17a2b8;
            }}

            .help-content {{ 
                background: white;
                padding: 20px;
                border-radius: 8px;
                line-height: 1.8;
                font-size: 15px;
                color: #444;
                box-shadow: inset 0 2px 8px rgba(0,0,0,0.05);
            }}

            .disease-list {{
                background: #f8f9fa;
                padding: 15px;
                border-radius: 8px;
                margin: 15px 0;
                border-left: 4px solid #28a745;
            }}

            .disease-item {{
                margin: 10px 0;
                padding: 8px 0;
                border-bottom: 1px solid #dee2e6;
            }}

            .disease-item:last-child {{
                border-bottom: none;
            }}

            .disease-title {{
                font-weight: 600;
                color: #2c3e50;
                margin-bottom: 5px;
            }}

            .disease-codes {{
                font-size: 14px;
                color: #6c757d;
                margin-left: 15px;
            }}


        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🏷️ 라벨링 시스템 - 환영합니다, {user.username}님!</h1>
                <div class="header-buttons">
                    <button class="help-btn" onclick="showHelp()">❓ 도움말</button>
                    <button class="logout-btn" onclick="logout()">로그아웃</button>
                </div>
            </div>
            
            <p>이메일: {user.email}</p>
            <p>가입일: {user.created_at.strftime('%Y년 %m월 %d일')}</p>
            
            <!-- 라벨링 대시보드 -->
            <div id="labelingDashboard">
                <div class="stats">
                    <div class="stat-item">
                        <div class="stat-number" id="totalFiles">0</div>
                        <div class="stat-label">총 파일</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-number" id="userLabels">0</div>
                        <div class="stat-label">내 라벨링</div>
                    </div>
                </div>
                
                <div id="message"></div>
                
                <div class="file-list">
                    <h3>📋 라벨링할 파일 목록</h3>
                    <div class="tab-container">
                        <div class="tab-buttons">
                            <button class="tab-btn active" onclick="switchTab('all')">전체</button>
                            <button class="tab-btn" onclick="switchTab('completed')">완료</button>
                            <button class="tab-btn" onclick="switchTab('incomplete')">미완료</button>
                        </div>
                        <div class="tab-content">
                            <div id="fileList">로딩 중...</div>
                            <div id="pagination" class="pagination"></div>
                        </div>
                    </div>
                </div>
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
                    <div id="labelingModalMessage" class="message" style="display:none;"></div>
                    <div class="form-group">
                        <label>질환 선택 <span class="subtitle">(복수 선택 가능)</span>: <span class="required">*</span></label>
                        <div id="diseaseContainer" class="disease-checkboxes">
                            <div class="disease-option">
                                <input type="checkbox" id="disease_normal" value="정상" onchange="updateSymptoms()">
                                <label for="disease_normal">정상</label>
                            </div>
                            <div class="disease-option">
                                <input type="checkbox" id="disease_rds" value="Respiratory Distress Syndrome" onchange="updateSymptoms()">
                                <label for="disease_rds">Respiratory Distress Syndrome</label>
                            </div>
                            <div class="disease-option">
                                <input type="checkbox" id="disease_bpd" value="Bronchopulmonary Dysplasia" onchange="updateSymptoms()">
                                <label for="disease_bpd">Bronchopulmonary Dysplasia</label>
                            </div>
                            <div class="disease-option">
                                <input type="checkbox" id="disease_pneumothorax" value="Pneumothorax" onchange="updateSymptoms()">
                                <label for="disease_pneumothorax">Pneumothorax</label>
                            </div>
                            <div class="disease-option">
                                <input type="checkbox" id="disease_pie" value="Pulmonary Interstitial Emphysema" onchange="updateSymptoms()">
                                <label for="disease_pie">Pulmonary Interstitial Emphysema</label>
                            </div>
                            <div class="disease-option">
                                <input type="checkbox" id="disease_pneumomediastinum" value="Pneumomediastinum" onchange="updateSymptoms()">
                                <label for="disease_pneumomediastinum">Pneumomediastinum</label>
                            </div>
                            <div class="disease-option">
                                <input type="checkbox" id="disease_subcutaneous" value="Subcutaneous Emphysema" onchange="updateSymptoms()">
                                <label for="disease_subcutaneous">Subcutaneous Emphysema</label>
                            </div>
                            <div class="disease-option">
                                <input type="checkbox" id="disease_pneumopericardium" value="Pneumopericardium" onchange="updateSymptoms()">
                                <label for="disease_pneumopericardium">Pneumopericardium</label>
                            </div>
                            <div class="disease-option">
                                <input type="checkbox" id="disease_nec" value="Necrotizing Enterocolitis" onchange="updateSymptoms()">
                                <label for="disease_nec">Necrotizing Enterocolitis</label>
                            </div>
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label for="viewTypeSelect">사진 종류: <span class="required">*</span></label>
                        <select id="viewTypeSelect">
                            <option value="">사진 종류를 선택하세요</option>
                            <option value="AP">AP</option>
                            <option value="LATDEQ">LATDEQ</option>
                            <option value="LAT">LAT</option>
                            <option value="PA">PA</option>
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label class="symptom-title">흉부 X선 소견 <span class="subtitle">(복수 선택 가능)</span>:</label>
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
        
        <!-- 라벨링 기록 모달 -->
        <div id="historyModal" class="modal" style="display: none;">
            <div class="modal-content">
                <div class="modal-header">
                    <h2>📋 라벨링 기록</h2>
                    <span class="close" onclick="closeHistoryModal()">&times;</span>
                </div>
                <div class="modal-body" id="historyContent">
                    <!-- 기록 내용이 여기에 표시됩니다 -->
                </div>
                <div class="modal-footer">
                    <button onclick="closeHistoryModal()" class="btn btn-secondary">닫기</button>
                </div>
            </div>
        </div>
        
        <!-- 도움말 모달 -->
        <div id="helpModal" class="modal" style="display: none;">
            <div class="modal-content" style="max-width: 900px; max-height: 80vh; overflow-y: auto;">
                <div class="modal-header">
                    <h2>❓ 라벨링 시스템 도움말</h2>
                    <span class="close" onclick="closeHelpModal()">&times;</span>
                </div>
                <div class="modal-body">
                    <!-- 도움말 탭 버튼 -->
                    <div class="help-tab-buttons">
                        <button class="help-tab-btn active" onclick="switchHelpTab('system')">📋 시스템 설명</button>
                        <button class="help-tab-btn" onclick="switchHelpTab('guide')">📖 라벨링 방법</button>
                    </div>
                    
                    <!-- 도움말 탭 내용 -->
                    <div class="help-tab-content">
                        <div id="systemTab" class="help-tab active">
                            <!-- 시스템 설명 내용 -->
                        </div>
                        <div id="guideTab" class="help-tab">
                            <!-- 라벨링 방법 내용 -->
                        </div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button onclick="closeHelpModal()" class="btn btn-secondary">닫기</button>
                </div>
            </div>
        </div>
        
        <script>
            // 전역 변수
            let currentFileId = null;
            let allFiles = [];
            let currentTab = 'all';
            let currentPage = 1;
            let currentPagination = null;
            
            // 파일 목록 로드 (페이지네이션 적용)
            function loadFiles(page = 1) {{
                currentPage = page;
                const perPage = 20;
                const tab = currentTab;
                
                // 로딩 표시
                document.getElementById('fileList').innerHTML = '<div class="loading">파일 목록을 불러오는 중...</div>';
                
                fetch(`/api/files?page=${{page}}&per_page=${{perPage}}&tab=${{tab}}`)
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        allFiles = data.files;
                        currentPagination = data.pagination;
                        
                        displayFiles(allFiles);
                        updateStats(data.pagination);
                        updatePagination(data.pagination);
                        
                        // 이미지 지연 로딩 적용
                        lazyLoadImages();
                    }}
                }})
                .catch(error => {{
                    console.error('파일 목록 로드 실패:', error);
                    document.getElementById('fileList').innerHTML = '<p>파일 목록을 불러오는데 실패했습니다.</p>';
                }});
            }}
            
            // 탭 전환
            function switchTab(tabName) {{
                currentTab = tabName;
                currentPage = 1; // 탭 변경 시 첫 페이지로
                
                // 탭 버튼 활성화 상태 변경
                document.querySelectorAll('.tab-btn').forEach(btn => {{
                    btn.classList.remove('active');
                }});
                event.target.classList.add('active');
                
                // 파일 목록 새로 로드
                loadFiles(1);
            }}
            
            // 통계 업데이트
            function updateStats(pagination) {{
                document.getElementById('totalFiles').textContent = pagination.total;
                // 사용자 라벨링 수는 별도 계산 필요
                const userLabels = allFiles.filter(file => file.user_label).length;
                document.getElementById('userLabels').textContent = userLabels;
            }}
            
            // 페이지네이션 업데이트
            function updatePagination(pagination) {{
                const paginationDiv = document.getElementById('pagination');
                if (!paginationDiv) return;
                
                let html = '';
                
                if (pagination.has_prev) {{
                    html += `<button onclick="loadFiles(${{pagination.page - 1}})" class="btn btn-secondary">이전</button>`;
                }} else {{
                    html += `<button disabled class="btn btn-secondary">이전</button>`;
                }}
                
                html += `<span>${{pagination.page}} / ${{pagination.pages}}</span>`;
                
                if (pagination.has_next) {{
                    html += `<button onclick="loadFiles(${{pagination.page + 1}})" class="btn btn-secondary">다음</button>`;
                }} else {{
                    html += `<button disabled class="btn btn-secondary">다음</button>`;
                }}
                
                paginationDiv.innerHTML = html;
            }}
            
            // 이미지 지연 로딩
            function lazyLoadImages() {{
                const imageObserver = new IntersectionObserver((entries, observer) => {{
                    entries.forEach(entry => {{
                        if (entry.isIntersecting) {{
                            const img = entry.target;
                            img.src = img.dataset.src;
                            img.classList.add('loaded');
                            observer.unobserve(img);
                        }}
                    }});
                }}, {{
                    rootMargin: '50px 0px', // 50px 전에 미리 로드
                    threshold: 0.1
                }});
                
                document.querySelectorAll('img[data-src]').forEach(img => {{
                    imageObserver.observe(img);
                }});
            }}
            
            // 파일 목록 표시 (지연 로딩 적용)
            function displayFiles(files) {{
                const fileList = document.getElementById('fileList');
                if (files.length === 0) {{
                    fileList.innerHTML = '<p>업로드된 파일이 없습니다.</p>';
                    return;
                }}
                
                fileList.innerHTML = files.map(file => {{
                    const isImage = file.filename.toLowerCase().endsWith('.jpg') || 
                                   file.filename.toLowerCase().endsWith('.jpeg') || 
                                   file.filename.toLowerCase().endsWith('.png') ||
                                   file.filename.toLowerCase().endsWith('.dcm');
                    
                    return `
                        <div class="file-item">
                            <div class="file-info">
                                <strong>${{file.filename}}</strong><br>
                                <small>업로드: ${{file.uploaded_by}} | 크기: ${{(file.file_size / 1024).toFixed(1)}}KB</small><br>
                                <small>라벨링 기록: ${{file.user_label ? '✅' : '✖️'}}</small>
                                ${{isImage ? `<br><img class="lazy" data-src="/api/files/${{file.id}}/image" style="max-width: 200px; max-height: 150px; margin-top: 10px; border-radius: 5px;" alt="썸네일">` : ''}}
                            </div>
                            <div class="file-actions">
                                <div class="label-buttons">
                                    <button class="label-btn like-btn" onclick="openLabelingModal(${{file.id}})">🏷️ 라벨링</button>
                                    <button class="label-btn history-btn" onclick="viewLabelHistory(${{file.id}})">📋 기록보기</button>
                                    ${{isImage ? '<button class=\\"label-btn image-btn\\" onclick=\\"viewContent(' + file.id + ')\\">🩻 이미지보기</button>' : '<button class=\\"btn btn-primary\\" onclick=\\"viewContent(' + file.id + ')\\">📄 내용보기</button>'}}
                                </div>
                            </div>
                        </div>
                    `;
                }}).join('');
            }}
            
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
                // 질환 체크박스 초기화
                document.querySelectorAll('#diseaseContainer input[type="checkbox"]').forEach(cb => {{
                    cb.checked = false;
                }});
                document.getElementById('viewTypeSelect').value = '';
                document.getElementById('codeInput').value = '';
                document.getElementById('descriptionInput').value = '';
                document.getElementById('symptomsContainer').innerHTML = '<p>질환을 먼저 선택해주세요.</p>';
                
                // 기존 라벨링 기록이 있는지 확인
                if (currentFileId) {{
                    loadExistingLabel();
                }}
            }}
            
            // 기존 라벨링 기록 불러오기
            function loadExistingLabel() {{
                fetch(`/api/label/history/${{currentFileId}}`)
                .then(response => response.json())
                .then(data => {{
                    if (data.success && data.has_history) {{
                        populateModalWithHistory(data.label);
                    }}
                }})
                .catch(error => {{
                    console.error('기존 라벨링 기록 불러오기 실패:', error);
                }});
            }}
            
            // 기존 기록으로 모달 채우기
            function populateModalWithHistory(label) {{
                // 질환 체크박스 설정
                const diseases = Array.isArray(label.disease) ? label.disease : [label.disease];
                diseases.forEach(disease => {{
                    const checkbox = document.querySelector(`#diseaseContainer input[value="${{disease}}"]`);
                    if (checkbox) {{
                        checkbox.checked = true;
                    }}
                }});
                
                // 사진 종류 설정
                document.getElementById('viewTypeSelect').value = label.view_type;
                
                // 소견 업데이트
                updateSymptoms();
                
                // 코드와 설명 설정 (소견 업데이트 후에 실행)
                setTimeout(() => {{
                    document.getElementById('codeInput').value = label.code;
                    document.getElementById('descriptionInput').value = label.description;
                    
                    // 선택된 소견 체크박스 설정
                    const codes = label.code.split(', ').map(code => code.trim());
                    codes.forEach(code => {{
                        const checkbox = document.getElementById(code);
                        if (checkbox) {{
                            checkbox.checked = true;
                        }}
                    }});
                }}, 100);
            }}
            
            // 질환 선택에 따른 소견 업데이트
            function updateSymptoms() {{
                const selectedDiseases = getSelectedDiseases();
                const container = document.getElementById('symptomsContainer');
                const codeInput = document.getElementById('codeInput');
                const descriptionInput = document.getElementById('descriptionInput');
                
                if (selectedDiseases.length === 0) {{
                    container.innerHTML = '<p>질환을 먼저 선택해주세요.</p>';
                    codeInput.readOnly = true;
                    descriptionInput.readOnly = true;
                    return;
                }}
                
                // 정상만 선택된 경우
                if (selectedDiseases.length === 1 && selectedDiseases[0] === '정상') {{
                    container.innerHTML = '<p>정상 소견입니다.</p>';
                    codeInput.readOnly = true;
                    codeInput.value = 'NORMAL';
                    descriptionInput.readOnly = true;
                    descriptionInput.value = '정상';
                    return;
                }}
                
                // 정상이 다른 질환과 함께 선택된 경우, 정상 제거
                if (selectedDiseases.includes('정상')) {{
                    selectedDiseases.splice(selectedDiseases.indexOf('정상'), 1);
                }}
                
                // 모든 선택된 질환의 소견들을 합쳐서 표시
                let allSymptoms = [];
                selectedDiseases.forEach(disease => {{
                    const symptoms = getSymptomsByDisease(disease);
                    if (symptoms) {{
                        allSymptoms = allSymptoms.concat(symptoms);
                    }}
                }});
                
                if (allSymptoms.length === 0) {{
                    container.innerHTML = '<p>선택된 질환에 대한 소견이 없습니다.</p>';
                    codeInput.readOnly = true;
                    descriptionInput.readOnly = true;
                    return;
                }}
                
                let html = '<table class="symptoms-table">';
                html += '<tr><th>질환</th><th>소견</th><th>선택</th></tr>';

                allSymptoms.forEach(symptom => {{
                    html += '<tr class="symptom-row">';
                    html += '<td class="symptom-disease">' + getDiseaseByCode(symptom.code) + '</td>';
                    html += '<td class="symptom-label">';
                    html += '<label for="' + symptom.code + '">' + symptom.description + '</label>';
                    html += '</td>';
                    html += '<td class="symptom-checkbox">';
                    html += '<input type="checkbox" id="' + symptom.code + '" value="' + symptom.code + '" onchange="updateCodeAndDescription()">';
                    html += '</td>';
                    html += '</tr>';
                }});

                container.innerHTML = html;
                codeInput.readOnly = true;
                descriptionInput.readOnly = true;
            }}
            
            // 선택된 질환들 가져오기
            function getSelectedDiseases() {{
                const checkboxes = document.querySelectorAll('#diseaseContainer input[type="checkbox"]:checked');
                return Array.from(checkboxes).map(cb => cb.value);
            }}
            
            // 코드로 질환 찾기
            function getDiseaseByCode(code) {{
                const diseaseMap = {{
                    'RDS_1': 'RDS', 'RDS_2': 'RDS', 'RDS_3': 'RDS', 'RDS_4': 'RDS',
                    'BPD_1': 'BPD', 'BPD_2': 'BPD', 'BPD_3': 'BPD', 'BPD_4': 'BPD',
                    'PTX_1': 'PTX', 'PTX_2': 'PTX', 'PTX_3': 'PTX', 'PTX_4': 'PTX', 'PTX_5': 'PTX',
                    'PIE_1': 'PIE',
                    'PMS_1': 'PMS', 'PMS_2': 'PMS', 'PMS_3': 'PMS',
                    'SEM_1': 'SEM',
                    'PPC_1': 'PPC',
                    'NEC_1': 'NEC', 'NEC_2': 'NEC', 'NEC_3': 'NEC', 'NEC_4': 'NEC', 'NEC_5': 'NEC'
                }};
                return diseaseMap[code] || '';
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
                    ],
                    '직접 입력': []
                }};
                
                return symptoms[disease] || [];
            }}
            
            // 선택된 소견에 따라 코드와 설명 업데이트
            function updateCodeAndDescription() {{
                const selectedDiseases = getSelectedDiseases();
                
                // 정상만 선택된 경우 처리하지 않음
                if (selectedDiseases.length === 1 && selectedDiseases[0] === '정상') {{
                    return;
                }}
                
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
                const selectedDiseases = getSelectedDiseases();
                const viewType = document.getElementById('viewTypeSelect').value;
                const code = document.getElementById('codeInput').value;
                const description = document.getElementById('descriptionInput').value;
                
                // 필수 필드 검증
                if (selectedDiseases.length === 0) {{
                    showMessage('질환을 선택해주세요.', 'error');
                    return;
                }}
                
                if (!viewType) {{
                    showMessage('사진 종류를 선택해주세요.', 'error');
                    document.getElementById('viewTypeSelect').focus();
                    return;
                }}
                
                if (!description) {{
                    showMessage('최종 소견을 입력해주세요.', 'error');
                    document.getElementById('descriptionInput').focus();
                    return;
                }}
                
                // 정상이 아닌 경우에만 코드 검증
                if (!(selectedDiseases.length === 1 && selectedDiseases[0] === '정상') && !code) {{
                    showMessage('소견을 선택해주세요.', 'error');
                    return;
                }}
                
                addLabel(currentFileId, selectedDiseases, viewType, code, description);
                closeLabelingModal();
            }}
            
            // 라벨링 추가
            function addLabel(fileId, diseases, viewType, code, description) {{
                fetch('/api/label', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json'
                    }},
                    body: JSON.stringify({{
                        file_id: fileId,
                        disease: diseases,  // 이제 리스트 형태로 전송
                        view_type: viewType,
                        code: code,
                        description: description
                    }})
                }})
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        showMessage(data.message, 'success');
                        loadFiles(currentPage); // 현재 페이지 새로고침
                    }} else {{
                        showMessage(data.error || '라벨링 실패', 'error');
                    }}
                }})
                .catch(error => {{
                    showMessage('서버 오류가 발생했습니다.', 'error');
                }});
            }}
            
            // 라벨링 기록 조회
            function viewLabelHistory(fileId) {{
                fetch(`/api/label/history/${{fileId}}`)
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        if (data.has_history) {{
                            displayLabelHistory(data.label);
                        }} else {{
                            displayNoHistory(data.message);
                        }}
                        document.getElementById('historyModal').style.display = 'block';
                    }} else {{
                        showMessage(data.error || '기록 조회 실패', 'error');
                    }}
                }})
                .catch(error => {{
                    showMessage('서버 오류가 발생했습니다.', 'error');
                }});
            }}
            
            // 라벨링 기록 표시
            function displayLabelHistory(label) {{
                const content = document.getElementById('historyContent');
                const diseases = Array.isArray(label.disease) ? label.disease.join(', ') : label.disease;
                content.innerHTML = `
                    <div class="history-item">
                        <h3>✅ 라벨링 기록이 있습니다</h3>
                        <div class="history-details">
                            <p><strong>질환:</strong> ${{diseases}}</p>
                            <p><strong>사진 종류:</strong> ${{label.view_type}}</p>
                            <p><strong>번호:</strong> ${{label.code}}</p>
                            <p><strong>최종 소견:</strong></p>
                            <div class="description-box">
                                ${{label.description.replace(/\\n/g, '<br>')}}
                            </div>
                            <p><strong>라벨링 시간:</strong> ${{label.created_at}}</p>
                        </div>
                    </div>
                `;
            }}
            
            // 기록 없음 표시
            function displayNoHistory(message) {{
                const content = document.getElementById('historyContent');
                content.innerHTML = `
                    <div class="history-item">
                        <h3>❌ 라벨링 기록이 없습니다</h3>
                        <p>${{message}}</p>
                        <p>이 파일에 대해 아직 라벨링을 하지 않았습니다.</p>
                    </div>
                `;
            }}
            
            // 기록 모달 닫기
            function closeHistoryModal() {{
                document.getElementById('historyModal').style.display = 'none';
            }}
            
            // 도움말 표시
            function showHelp() {{
                fetch('/api/help')
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        displayHelp(data.help);
                        document.getElementById('helpModal').style.display = 'block';
                    }} else {{
                        showMessage(data.error || '도움말을 불러올 수 없습니다.', 'error');
                    }}
                }})
                .catch(error => {{
                    showMessage('서버 오류가 발생했습니다.', 'error');
                }});
            }}
            
            // 도움말 내용 표시
            function displayHelp(help) {{
                // 시스템 설명 탭 내용
                const systemTab = document.getElementById('systemTab');
                systemTab.innerHTML = `
                    <div class="help-section">
                        <h3>${{help.system_intro.title}}</h3>
                        <div style="white-space: pre-line; line-height: 1.6; color: #495057;">
                            ${{help.system_intro.content.replace(/(\d+\.\s+[^\\n]+)/g, '<strong style="color: #2c3e50; font-size: 15px;">$1</strong>')}}
                        </div>
                    </div>
                `;
                
                // 라벨링 방법 탭 내용
                const guideTab = document.getElementById('guideTab');
                let guideHtml = `
                    <div class="help-section">
                        <h3>${{help.labeling_guide.title}}</h3>
                        <div class="help-steps">
                `;
                
                help.labeling_guide.steps.forEach(step => {{
                    const buttonClass = step.button_style === 'blue' ? 'help-btn-blue' : 
                                       step.button_style === 'green' ? 'help-btn-green' : 
                                       step.button_style === 'teal' ? 'help-btn-teal' : 'help-btn-default';
                    
                    guideHtml += `
                        <div class="help-step">
                            <h4>
                                <span class="step-number">${{step.step}}</span>
                                <button class="help-action-btn ${{buttonClass}}">${{step.emoji}} ${{step.action}}</button>
                            </h4>
                            <p>${{step.description}}</p>
                    `;
                    
                    if (step.sub_steps) {{
                        guideHtml += '<div class="help-sub-steps">';
                        step.sub_steps.forEach(subStep => {{
                            guideHtml += `
                                <div class="help-sub-step">
                                    <h5>${{subStep.title}}</h5>
                                    <p>${{subStep.description}}</p>
                            `;
                            
                            if (subStep.options) {{
                                guideHtml += '<div class="help-options">';
                                subStep.options.forEach(option => {{
                                    guideHtml += `<span class="help-option">${{option}}</span>`;
                                }});
                                guideHtml += '</div>';
                            }}
                            
                            guideHtml += '</div>';
                        }});
                        guideHtml += '</div>';
                    }}
                    
                    guideHtml += '</div>';
                }});
                
                guideHtml += `
                        </div>
                    </div>
                `;
                
                guideTab.innerHTML = guideHtml;
            }}
            
            // 도움말 탭 전환
            function switchHelpTab(tabName) {{
                // 모든 탭 버튼 비활성화
                document.querySelectorAll('.help-tab-btn').forEach(btn => {{
                    btn.classList.remove('active');
                }});
                
                // 모든 탭 내용 숨기기
                document.querySelectorAll('.help-tab').forEach(tab => {{
                    tab.classList.remove('active');
                }});
                
                // 선택된 탭 활성화
                if (tabName === 'system') {{
                    document.querySelector('.help-tab-btn:first-child').classList.add('active');
                    document.getElementById('systemTab').classList.add('active');
                }} else if (tabName === 'guide') {{
                    document.querySelector('.help-tab-btn:last-child').classList.add('active');
                    document.getElementById('guideTab').classList.add('active');
                }}
            }}
            
            // 도움말 모달 닫기
            function closeHelpModal() {{
                document.getElementById('helpModal').style.display = 'none';
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
                // 라벨링 모달이 열려있으면 모달 내부에 메시지 표시
                const labelingModal = document.getElementById('labelingModal');
                const modalMessageDiv = document.getElementById('labelingModalMessage');
                if (labelingModal && labelingModal.style.display === 'block' && modalMessageDiv) {{
                    modalMessageDiv.textContent = message;
                    modalMessageDiv.className = `message ${{type}}`;
                    modalMessageDiv.style.display = 'block';
                    setTimeout(() => {{
                        modalMessageDiv.textContent = '';
                        modalMessageDiv.className = 'message';
                        modalMessageDiv.style.display = 'none';
                    }}, 3000);
                }} else {{
                    const messageDiv = document.getElementById('message');
                    messageDiv.textContent = message;
                    messageDiv.className = `message ${{type}}`;
                    setTimeout(() => {{
                        messageDiv.textContent = '';
                        messageDiv.className = '';
                    }}, 3000);
                }}
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
            loadFiles(1);
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
