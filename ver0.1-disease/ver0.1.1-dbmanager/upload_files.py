#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
파일 업로드 스크립트
지정된 폴더의 파일들을 데이터베이스에 업로드합니다.
하위 폴더도 재귀적으로 처리합니다.
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
    하위 폴더도 재귀적으로 처리합니다.
    
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
        
        # uploads 폴더가 없으면 생성 (DICOM 변환 파일용)
        if not os.path.exists(UPLOAD_FOLDER):
            os.makedirs(UPLOAD_FOLDER)
            print(f"uploads 폴더를 생성했습니다: {UPLOAD_FOLDER}")
        
        # 폴더 내 파일들 처리
        allowed_extensions = {'.txt', '.jpg', '.jpeg', '.png', '.dcm'}
        uploaded_count = 0
        skipped_count = 0
        
        print(f"\n📁 폴더 '{folder_path}'에서 파일을 검색합니다...")
        
        # 재귀적으로 모든 파일 찾기
        for root, dirs, files in os.walk(folder_path):
            # 상대 경로 계산
            rel_root = os.path.relpath(root, folder_path)
            if rel_root == '.':
                rel_root = ''
            
            print(f"\n📂 하위 폴더: {rel_root if rel_root else '루트'}")
            
            for filename in files:
                file_path = os.path.join(root, filename)
                
                # 파일 확장자 확인
                file_ext = os.path.splitext(filename)[1].lower()
                if file_ext not in allowed_extensions:
                    print(f"  ⚠️  건너뜀: {filename} (지원되지 않는 확장자)")
                    skipped_count += 1
                    continue
                
                # 폴더 구조를 반영한 파일명 생성
                if rel_root:
                    db_filename = f"{rel_root}/{filename}"
                else:
                    db_filename = filename
                
                # 이미 데이터베이스에 존재하는지 확인
                existing_file = File.query.filter_by(filename=db_filename).first()
                if existing_file:
                    print(f"  ⚠️  건너뜀: {db_filename} (이미 데이터베이스에 존재)")
                    skipped_count += 1
                    continue
                
                try:
                    # 파일 크기 확인
                    file_size = os.path.getsize(file_path)
                    
                    if file_ext == '.dcm':
                        # DICOM 파일: PNG로 변환하여 uploads에 캐싱
                        import pydicom
                        from PIL import Image
                        import numpy as np
                        
                        # PNG 파일명 생성 (폴더 구조 유지)
                        png_filename = os.path.splitext(db_filename)[0] + '.png'
                        png_path = os.path.join(UPLOAD_FOLDER, png_filename)
                        
                        # uploads 폴더에 하위 폴더 구조 생성
                        png_dir = os.path.dirname(png_path)
                        if png_dir != UPLOAD_FOLDER and not os.path.exists(png_dir):
                            os.makedirs(png_dir)
                        
                        # 이미 변환된 PNG가 있는지 확인
                        if not os.path.exists(png_path):
                            # DICOM 파일 읽기 및 PNG 변환
                            ds = pydicom.dcmread(file_path)
                            arr = ds.pixel_array
                            
                            # Normalize to 0-255 for display
                            arr = arr.astype(float)
                            arr = (arr - arr.min()) / (arr.max() - arr.min()) * 255.0
                            arr = arr.astype(np.uint8)
                            
                            if arr.ndim == 2:
                                img = Image.fromarray(arr)
                            else:
                                img = Image.fromarray(arr[0])
                            
                            # PNG로 저장
                            img.save(png_path, format='PNG')
                            print(f"  🔄 변환됨: {filename} -> {png_filename}")
                        else:
                            print(f"  📋 캐시 사용: {png_filename} (이미 변환됨)")
                        
                        # 데이터베이스에 PNG 파일 정보가 이미 있는지 확인
                        existing_png = File.query.filter_by(filename=png_filename).first()
                        if existing_png:
                            print(f"  ⚠️  건너뜀: {png_filename} (이미 데이터베이스에 존재)")
                            skipped_count += 1
                            continue
                        
                        # 데이터베이스에 PNG 파일 정보 저장
                        png_size = os.path.getsize(png_path)
                        new_file = File(
                            filename=png_filename,
                            file_path=png_path,
                            file_size=png_size,
                            uploaded_by=admin_user.id
                        )
                        
                        db.session.add(new_file)
                        db.session.commit()
                        
                        print(f"  ✅ 등록됨: {png_filename} (DICOM 변환)")
                        uploaded_count += 1
                        
                    else:
                        # 일반 파일: 원본 경로 그대로 참조 (복사하지 않음)
                        new_file = File(
                            filename=db_filename,
                            file_path=file_path,  # 원본 경로 그대로 사용
                            file_size=file_size,
                            uploaded_by=admin_user.id
                        )
                        
                        db.session.add(new_file)
                        db.session.commit()
                        
                        print(f"  ✅ 등록됨: {db_filename} (경로 참조)")
                        uploaded_count += 1
                    
                except Exception as e:
                    print(f"  ❌ 오류: {db_filename} - {str(e)}")
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