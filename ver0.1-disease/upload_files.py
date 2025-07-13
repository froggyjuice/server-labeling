#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
파일 업로드 스크립트
지정된 폴더의 파일들을 데이터베이스에 업로드합니다.
"""

import os
import sys
from pathlib import Path

# 프로젝트 루트 디렉토리를 Python 경로에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from main import app, db, UPLOAD_FOLDER
from user import User, File

def upload_files_from_folder(folder_path):
    """
    지정된 폴더의 파일들을 데이터베이스에 업로드합니다.
    
    Args:
        folder_path (str): 파일들이 있는 폴더 경로
    """
    with app.app_context():
        # admin 사용자 찾기 (없으면 생성)
        admin_user = User.query.filter_by(username="admin").first()
        if not admin_user:
            print("admin 사용자가 없습니다. 생성합니다...")
            admin_user = User(
                username="admin",
                email="admin@example.com"
            )
            admin_user.set_password("password123")
            db.session.add(admin_user)
            db.session.commit()
            print("admin 사용자가 생성되었습니다.")
        
        # 폴더 경로 확인
        if not os.path.exists(folder_path):
            print(f"오류: 폴더 '{folder_path}'가 존재하지 않습니다.")
            return
        
        # uploads 폴더가 없으면 생성
        if not os.path.exists(UPLOAD_FOLDER):
            os.makedirs(UPLOAD_FOLDER)
            print(f"uploads 폴더를 생성했습니다: {UPLOAD_FOLDER}")
        
        # 폴더 내 파일들 처리
        allowed_extensions = {'.txt', '.jpg', '.jpeg', '.png'}
        uploaded_count = 0
        skipped_count = 0
        
        print(f"\n📁 폴더 '{folder_path}'에서 파일을 검색합니다...")
        
        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            
            # 파일인지 확인
            if not os.path.isfile(file_path):
                continue
            
            # 파일 확장자 확인
            file_ext = os.path.splitext(filename)[1].lower()
            if file_ext not in allowed_extensions:
                print(f"⚠️  건너뜀: {filename} (지원되지 않는 확장자)")
                skipped_count += 1
                continue
            
            # 이미 데이터베이스에 존재하는지 확인
            existing_file = File.query.filter_by(filename=filename).first()
            if existing_file:
                print(f"⚠️  건너뜀: {filename} (이미 데이터베이스에 존재)")
                skipped_count += 1
                continue
            
            try:
                # 파일 크기 확인
                file_size = os.path.getsize(file_path)
                
                # uploads 폴더로 파일 복사
                dest_path = os.path.join(UPLOAD_FOLDER, filename)
                
                # 파일이 이미 uploads 폴더에 있는지 확인
                if not os.path.exists(dest_path):
                    import shutil
                    shutil.copy2(file_path, dest_path)
                    print(f"📋 복사됨: {filename} -> uploads/")
                
                # 데이터베이스에 파일 정보 저장
                new_file = File(
                    filename=filename,
                    file_path=dest_path,
                    file_size=file_size,
                    uploaded_by=admin_user.id
                )
                
                db.session.add(new_file)
                db.session.commit()
                
                print(f"✅ 업로드됨: {filename} ({file_size} bytes)")
                uploaded_count += 1
                
            except Exception as e:
                print(f"❌ 오류: {filename} - {str(e)}")
                db.session.rollback()
        
        print(f"\n📊 업로드 완료!")
        print(f"   ✅ 성공: {uploaded_count}개 파일")
        print(f"   ⚠️  건너뜀: {skipped_count}개 파일")
        print(f"   📁 총 처리: {uploaded_count + skipped_count}개 파일")

def main():
    """메인 함수"""
    print("🚀 파일 업로드 스크립트")
    print("=" * 50)
    
    if len(sys.argv) != 2:
        print("사용법: python upload_files.py <폴더경로>")
        print("\n예시:")
        print("  python upload_files.py ./my_files")
        print("  python upload_files.py C:/Users/user/Documents/files")
        return
    
    folder_path = sys.argv[1]
    
    # 사용자 확인
    print(f"폴더 경로: {folder_path}")
    response = input("\n이 폴더의 파일들을 데이터베이스에 업로드하시겠습니까? (y/N): ")
    
    if response.lower() in ['y', 'yes']:
        upload_files_from_folder(folder_path)
    else:
        print("업로드가 취소되었습니다.")

if __name__ == "__main__":
    main() 