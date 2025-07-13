import os
import sys
from flask import Flask
from user import db, User, File, Label

# Flask 앱 생성
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(os.path.dirname(__file__), 'database', 'app.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# 파일 업로드 폴더 경로
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')

def create_database_with_cascade():
    """CASCADE DELETE가 포함된 올바른 스키마로 데이터베이스 생성"""
    with app.app_context():
        # 기존 테이블 삭제 (있다면)
        db.drop_all()
        
        # 새 테이블 생성
        db.create_all()
        
        # CASCADE DELETE 설정을 위한 외래키 제약조건 추가
        from sqlalchemy import text
        
        # label 테이블의 외래키 제약조건 수정
        db.session.execute(text("""
            DROP TABLE IF EXISTS label;
        """))
        
        db.session.execute(text("""
            CREATE TABLE label (
                id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                file_id INTEGER NOT NULL,
                label_type VARCHAR(10) NOT NULL,
                created_at DATETIME,
                PRIMARY KEY (id),
                FOREIGN KEY(user_id) REFERENCES user (id) ON DELETE CASCADE,
                FOREIGN KEY(file_id) REFERENCES file (id) ON DELETE CASCADE
            );
        """))
        
        db.session.commit()
        print("✅ 데이터베이스가 CASCADE DELETE와 함께 생성되었습니다.")

def add_sample_data():
    """샘플 데이터 추가"""
    with app.app_context():
        try:
            # 관리자 사용자 추가
            admin_user = User(
                username="admin",
                email="admin@example.com"
            )
            admin_user.set_password("password123")
            db.session.add(admin_user)
            db.session.commit()
            print("✅ 관리자 사용자가 추가되었습니다: admin/password123")
            
            # uploads 폴더의 파일들을 올바른 경로로 등록
            if os.path.exists(UPLOAD_FOLDER):
                for filename in os.listdir(UPLOAD_FOLDER):
                    if filename.lower().endswith(('.txt', '.jpg', '.jpeg', '.png')):
                        file_path = os.path.join(UPLOAD_FOLDER, filename)
                        file_size = os.path.getsize(file_path)
                        
                        # 파일 정보 추가
                        file_record = File(
                            filename=filename,
                            file_path=file_path,  # 현재 실제 경로 사용
                            file_size=file_size,
                            uploaded_by=admin_user.id
                        )
                        db.session.add(file_record)
                
                db.session.commit()
                print(f"✅ {len(os.listdir(UPLOAD_FOLDER))}개의 파일이 데이터베이스에 등록되었습니다.")
            
        except Exception as e:
            print(f"❌ 샘플 데이터 추가 중 오류: {e}")
            db.session.rollback()

def verify_database():
    """데이터베이스 상태 확인"""
    with app.app_context():
        try:
            user_count = User.query.count()
            file_count = File.query.count()
            label_count = Label.query.count()
            
            print(f"\n📊 데이터베이스 상태:")
            print(f"  - 사용자: {user_count}명")
            print(f"  - 파일: {file_count}개")
            print(f"  - 라벨: {label_count}개")
            
            # 파일 목록 출력
            files = File.query.all()
            print(f"\n📁 등록된 파일:")
            for file in files:
                print(f"  - {file.filename} ({file.file_size} bytes)")
                print(f"    경로: {file.file_path}")
            
        except Exception as e:
            print(f"❌ 데이터베이스 확인 중 오류: {e}")

if __name__ == "__main__":
    print("🔧 SQLite 데이터베이스 정상화 작업을 시작합니다...")
    
    # 1. 올바른 스키마로 데이터베이스 생성
    create_database_with_cascade()
    
    # 2. 샘플 데이터 추가
    add_sample_data()
    
    # 3. 데이터베이스 상태 확인
    verify_database()
    
    print("\n✅ SQLite 데이터베이스 정상화가 완료되었습니다!") 