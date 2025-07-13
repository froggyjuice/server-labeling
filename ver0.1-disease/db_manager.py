import sqlite3
import os
from user import db, User, File
from flask import Flask

def connect_database():
    """데이터베이스에 직접 연결"""
    db_path = os.path.join(os.path.dirname(__file__), 'database', 'app.db')
    return sqlite3.connect(db_path)

def view_all_users():
    """모든 사용자 정보 조회"""
    conn = connect_database()
    cursor = conn.cursor()
    
    print("=== 모든 사용자 정보 ===")
    cursor.execute("SELECT id, username, email, created_at FROM user")
    users = cursor.fetchall()
    
    for user in users:
        print(f"ID: {user[0]}, 사용자명: {user[1]}, 이메일: {user[2]}, 가입일: {user[3]}")
    
    conn.close()

def view_all_files():
    """모든 파일 정보 조회"""
    conn = connect_database()
    cursor = conn.cursor()
    
    print("\n=== 모든 파일 정보 ===")
    cursor.execute("""
        SELECT f.id, f.filename, f.file_size, f.upload_date, u.username 
        FROM file f 
        JOIN user u ON f.uploaded_by = u.id
    """)
    files = cursor.fetchall()
    
    for file in files:
        size_kb = file[2] / 1024 if file[2] else 0
        print(f"ID: {file[0]}, 파일명: {file[1]}, 크기: {size_kb:.1f}KB, 업로드일: {file[3]}, 업로더: {file[4]}")
    
    conn.close()

def add_sample_user():
    """샘플 사용자 추가"""
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(os.path.dirname(__file__), 'database', 'app.db')}"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    
    with app.app_context():
        # 새 사용자 생성
        new_user = User(
            username="admin",
            email="admin@example.com"
        )
        new_user.set_password("password123")
        
        db.session.add(new_user)
        db.session.commit()
        print("샘플 사용자가 추가되었습니다: admin/password123")

def search_files_by_user(username):
    """특정 사용자가 업로드한 파일 검색"""
    conn = connect_database()
    cursor = conn.cursor()
    
    print(f"\n=== {username}이(가) 업로드한 파일 ===")
    cursor.execute("""
        SELECT f.filename, f.file_size, f.upload_date 
        FROM file f 
        JOIN user u ON f.uploaded_by = u.id 
        WHERE u.username = ?
    """, (username,))
    files = cursor.fetchall()
    
    if files:
        for file in files:
            size_kb = file[1] / 1024 if file[1] else 0
            print(f"파일명: {file[0]}, 크기: {size_kb:.1f}KB, 업로드일: {file[2]}")
    else:
        print("업로드한 파일이 없습니다.")
    
    conn.close()

def delete_file(file_id):
    """파일 삭제"""
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(os.path.dirname(__file__), 'database', 'app.db')}"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    
    with app.app_context():
        file = File.query.get(file_id)
        if file:
            # 실제 파일도 삭제
            if os.path.exists(file.file_path):
                os.remove(file.file_path)
            
            db.session.delete(file)
            db.session.commit()
            print(f"파일 {file.filename}이(가) 삭제되었습니다.")
        else:
            print("파일을 찾을 수 없습니다.")

def main():
    """메인 메뉴"""
    while True:
        print("\n=== 데이터베이스 관리 도구 ===")
        print("1. 모든 사용자 조회")
        print("2. 모든 파일 조회")
        print("3. 특정 사용자의 파일 검색")
        print("4. 샘플 사용자 추가")
        print("5. 파일 삭제")
        print("6. 종료")
        
        choice = input("\n선택하세요 (1-6): ")
        
        if choice == '1':
            view_all_users()
        elif choice == '2':
            view_all_files()
        elif choice == '3':
            username = input("사용자명을 입력하세요: ")
            search_files_by_user(username)
        elif choice == '4':
            add_sample_user()
        elif choice == '5':
            file_id = input("삭제할 파일 ID를 입력하세요: ")
            try:
                delete_file(int(file_id))
            except ValueError:
                print("올바른 숫자를 입력하세요.")
        elif choice == '6':
            print("프로그램을 종료합니다.")
            break
        else:
            print("올바른 선택을 해주세요.")

if __name__ == "__main__":
    main() 