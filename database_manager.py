#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
안전한 통합 데이터베이스 관리 도구 (1/2)
- 개발/운영 환경 분리
- 안전한 데이터베이스 관리 (재생성/초기화/마이그레이션/복구)
- 백업/복원 및 파일 업로드
- 무결성 검증 및 자동 수정
"""

import os
import sys
import sqlite3
import shutil
import json
from datetime import datetime
from pathlib import Path
from flask import Flask
from sqlalchemy import inspect

# 프로젝트 루트 디렉토리를 Python 경로에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from user import db, User, File, Label

# ==================== 환경 설정 ====================

# 단일 환경 설정
DB_PATH = 'database/app.db'
UPLOAD_FOLDER = 'uploads'
BACKUP_DIR = 'database/backups'

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(os.path.dirname(__file__), DB_PATH)}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# 백업 디렉토리 경로
BACKUP_DIR_PATH = os.path.join(os.path.dirname(__file__), BACKUP_DIR)
UPLOAD_FOLDER_PATH = os.path.join(os.path.dirname(__file__), UPLOAD_FOLDER)

# ==================== 환경 관리 ====================
def show_environment_info():
    print(f"\n[환경 정보]")
    print(f"  데이터베이스: {DB_PATH}")
    print(f"  업로드 폴더: {UPLOAD_FOLDER}")
    print(f"  백업 폴더: {BACKUP_DIR}")

# ==================== 백업/복원 기능 ====================
def ensure_backup_dir():
    if not os.path.exists(BACKUP_DIR_PATH):
        os.makedirs(BACKUP_DIR_PATH)

def create_backup(description=""):
    ensure_backup_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"app_backup_{timestamp}.db"
    backup_path = os.path.join(BACKUP_DIR_PATH, backup_filename)
    current_db = os.path.join(os.path.dirname(__file__), DB_PATH)
    if os.path.exists(current_db):
        shutil.copy2(current_db, backup_path)
        print(f"✅ 백업 생성 완료: {backup_filename}")
        return backup_path
    else:
        print("❌ 현재 데이터베이스 파일을 찾을 수 없습니다.")
        return None

def list_backups():
    ensure_backup_dir()
    return [f for f in os.listdir(BACKUP_DIR_PATH) if f.endswith('.db')]

def restore_backup(backup_filename):
    backup_path = os.path.join(BACKUP_DIR_PATH, backup_filename)
    current_db = os.path.join(os.path.dirname(__file__), DB_PATH)
    if not os.path.exists(backup_path):
        print(f"❌ 백업 파일을 찾을 수 없습니다: {backup_filename}")
        return False
    confirm = input("정말로 복원하시겠습니까? (yes를 입력하세요): ")
    if confirm.lower() != 'yes':
        print("복원이 취소되었습니다.")
        return False
    shutil.copy2(backup_path, current_db)
    print(f"✅ 백업에서 복원 완료: {backup_filename}")
    return True

# ==================== 데이터베이스 관리 기능 ====================
def connect_database():
    db_path = os.path.join(os.path.dirname(__file__), DB_PATH)
    return sqlite3.connect(db_path)

def create_database_with_cascade():
    """CASCADE DELETE를 지원하는 새로운 데이터베이스 생성"""
    with app.app_context():
        try:
            # 기존 데이터베이스 백업
            if os.path.exists(os.path.join(os.path.dirname(__file__), DB_PATH)):
                backup_path = create_backup("CASCADE_UPDATE_BACKUP")
                print(f"✅ 기존 데이터베이스 백업 완료: {backup_path}")
            
            # 데이터베이스 삭제 후 재생성
            db_path = os.path.join(os.path.dirname(__file__), DB_PATH)
            if os.path.exists(db_path):
                os.remove(db_path)
                print("✅ 기존 데이터베이스 삭제 완료")
            
            # 새로운 데이터베이스 생성 (CASCADE DELETE 지원)
            db.create_all()
            print("✅ CASCADE DELETE를 지원하는 새로운 데이터베이스 생성 완료")
            
            # 샘플 사용자 추가
            add_sample_user()
            
            print("✅ 데이터베이스 업그레이드가 완료되었습니다.")
            print("⚠️  기존 데이터는 백업 파일에서 복원할 수 있습니다.")
            return True
            
        except Exception as e:
            print(f"❌ 데이터베이스 생성 중 오류 발생: {e}")
            return False

def view_all_users():
    conn = connect_database()
    cursor = conn.cursor()
    
    print("=== 모든 사용자 정보 ===")
    try:
        cursor.execute("SELECT id, username, email, created_at FROM user")
        users = cursor.fetchall()
        if users:
            for user in users:
                print(f"ID: {user[0]}, 사용자명: {user[1]}, 이메일: {user[2]}, 가입일: {user[3]}")
        else:
            print("사용자가 없습니다.")
    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            print("❌ 사용자 테이블이 존재하지 않습니다.")
            print("데이터베이스가 초기화되지 않았습니다.")
            print("환경 전환을 다시 시도하거나 데이터베이스를 생성하세요.")
        else:
            print(f"❌ 데이터베이스 오류: {e}")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
    finally:
        conn.close()

def view_all_files():
    conn = connect_database()
    cursor = conn.cursor()
    
    print("\n=== 모든 파일 정보 ===")
    try:
        cursor.execute("""
            SELECT f.id, f.filename, f.file_size, f.upload_date, u.username 
            FROM file f 
            JOIN user u ON f.uploaded_by = u.id
        """)
        files = cursor.fetchall()
        if files:
            for file in files:
                size_kb = file[2] / 1024 if file[2] else 0
                print(f"ID: {file[0]}, 파일명: {file[1]}, 크기: {size_kb:.1f}KB, 업로드일: {file[3]}, 업로더: {file[4]}")
        else:
            print("파일이 없습니다.")
    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            print("❌ 파일 테이블이 존재하지 않습니다.")
            print("데이터베이스가 초기화되지 않았습니다.")
            print("환경 전환을 다시 시도하거나 데이터베이스를 생성하세요.")
        else:
            print(f"❌ 데이터베이스 오류: {e}")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
    finally:
        conn.close()

def add_sample_user():
    with app.app_context():
        existing_admin = User.query.filter_by(username="admin").first()
        if existing_admin:
            print("ℹ️ admin 사용자가 이미 존재합니다.")
            return existing_admin
        new_user = User(username="admin", email="admin@example.com")
        new_user.set_password("password123")
        db.session.add(new_user)
        db.session.commit()
        print("✅ 샘플 사용자가 추가되었습니다: admin/password123")
        return new_user

# ==================== 파일 업로드 기능 ====================
def upload_files_from_folder(folder_path):
    """지정된 폴더의 파일들을 데이터베이스에 업로드 (하위 폴더 재귀 처리, DICOM 변환 포함)"""
    with app.app_context():
        # admin 사용자 찾기 (없으면 생성)
        admin_user = add_sample_user()
        
        # 폴더 경로 확인
        if not os.path.exists(folder_path):
            print(f"❌ 오류: 폴더 '{folder_path}'가 존재하지 않습니다.")
            return
        
        # 업로드 폴더가 없으면 생성
        if not os.path.exists(UPLOAD_FOLDER_PATH):
            os.makedirs(UPLOAD_FOLDER_PATH)
            print(f"✅ 업로드 폴더를 생성했습니다: {UPLOAD_FOLDER_PATH}")
        
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
                        # DICOM 파일: PNG로 변환하여 환경별 uploads에 캐싱
                        import pydicom
                        from PIL import Image
                        import numpy as np
                        
                        # PNG 파일명 생성 (폴더 구조 유지)
                        png_filename = os.path.splitext(db_filename)[0] + '.png'
                        png_path = os.path.join(UPLOAD_FOLDER_PATH, png_filename)
                        
                        # 업로드 폴더에 하위 폴더 구조 생성
                        png_dir = os.path.dirname(png_path)
                        if png_dir != UPLOAD_FOLDER_PATH and not os.path.exists(png_dir):
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

# ==================== 데이터베이스 무결성 검증 ====================
def verify_database_integrity():
    with app.app_context():
        inspector = inspect(db.engine)
        required_tables = ['user', 'file', 'label']
        existing_tables = inspector.get_table_names()
        missing_tables = [table for table in required_tables if table not in existing_tables]
        if missing_tables:
            print(f"❌ 누락된 테이블: {missing_tables}")
            return False
        print("✅ 모든 필수 테이블이 존재합니다.")
        return True

# ==================== Excel Export 기능 ====================
def export_to_excel():
    """데이터베이스를 Excel 파일로 내보내기"""
    try:
        import pandas as pd
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
    except ImportError:
        print("❌ Excel export를 위해 필요한 패키지가 설치되지 않았습니다.")
        print("다음 명령어로 설치하세요:")
        print("pip install pandas openpyxl")
        return False
    
    with app.app_context():
        try:
            # Excel 파일명 생성
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            excel_filename = f"database_export_{timestamp}.xlsx"
            excel_path = os.path.join(os.path.dirname(__file__), excel_filename)
            
            print(f"📊 데이터베이스를 Excel로 내보내는 중...")
            print(f"파일: {excel_filename}")
            
            # 1. 사용자 데이터 내보내기
            users_data = []
            users = User.query.all()
            for user in users:
                users_data.append({
                    'ID': user.id,
                    '사용자명': user.username,
                    '이메일': user.email,
                    '가입일': user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else ''
                })
            
            # 2. 파일 데이터 내보내기
            files_data = []
            files = File.query.all()
            for file in files:
                size_kb = file.file_size / 1024 if file.file_size else 0
                files_data.append({
                    'ID': file.id,
                    '파일명': file.filename,
                    '파일경로': file.file_path,
                    '크기(KB)': round(size_kb, 1),
                    '업로드일': file.upload_date.strftime('%Y-%m-%d %H:%M:%S') if file.upload_date else '',
                    '업로더ID': file.uploaded_by
                })
            
            # 3. 라벨 데이터 내보내기
            labels_data = []
            labels = Label.query.all()
            for label in labels:
                labels_data.append({
                    'ID': label.id,
                    '사용자ID': label.user_id,
                    '파일ID': label.file_id,
                    '질환': label.disease,
                    '사진종류': label.view_type,
                    '코드': label.code,
                    '설명': label.description,
                    '생성일': label.created_at.strftime('%Y-%m-%d %H:%M:%S') if label.created_at else ''
                })
            
            # Excel 파일 생성
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                # 사용자 시트
                if users_data:
                    df_users = pd.DataFrame(users_data)
                    df_users.to_excel(writer, sheet_name='사용자', index=False)
                
                # 파일 시트
                if files_data:
                    df_files = pd.DataFrame(files_data)
                    df_files.to_excel(writer, sheet_name='파일', index=False)
                
                # 라벨 시트
                if labels_data:
                    df_labels = pd.DataFrame(labels_data)
                    df_labels.to_excel(writer, sheet_name='라벨', index=False)
                
                # 요약 시트
                summary_data = {
                    '항목': ['사용자', '파일', '라벨', '총 크기(KB)'],
                    '개수': [
                        len(users_data),
                        len(files_data),
                        len(labels_data),
                        round(sum(f['크기(KB)'] for f in files_data), 1)
                    ]
                }
                df_summary = pd.DataFrame(summary_data)
                df_summary.to_excel(writer, sheet_name='요약', index=False)
            
            print(f"✅ Excel 파일이 생성되었습니다: {excel_filename}")
            print(f"📊 내보낸 데이터:")
            print(f"  - 사용자: {len(users_data)}명")
            print(f"  - 파일: {len(files_data)}개")
            print(f"  - 라벨: {len(labels_data)}개")
            print(f"  - 총 크기: {round(sum(f['크기(KB)'] for f in files_data), 1)}KB")
            
            return True
            
        except Exception as e:
            print(f"❌ Excel 내보내기 중 오류 발생: {e}")
            return False

def export_selected_data(data_type):
    """선택한 데이터만 Excel로 내보내기"""
    try:
        import pandas as pd
    except ImportError:
        print("❌ Excel export를 위해 필요한 패키지가 설치되지 않았습니다.")
        print("다음 명령어로 설치하세요:")
        print("pip install pandas openpyxl")
        return False
    
    with app.app_context():
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            excel_filename = f"{data_type}_export_{timestamp}.xlsx"
            excel_path = os.path.join(os.path.dirname(__file__), excel_filename)
            
            if data_type == 'users':
                users_data = []
                users = User.query.all()
                for user in users:
                    users_data.append({
                        'ID': user.id,
                        '사용자명': user.username,
                        '이메일': user.email,
                        '가입일': user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else ''
                    })
                df = pd.DataFrame(users_data)
                sheet_name = '사용자'
                
            elif data_type == 'files':
                files_data = []
                files = File.query.all()
                for file in files:
                    size_kb = file.file_size / 1024 if file.file_size else 0
                    files_data.append({
                        'ID': file.id,
                        '파일명': file.filename,
                        '파일경로': file.file_path,
                        '크기(KB)': round(size_kb, 1),
                        '업로드일': file.upload_date.strftime('%Y-%m-%d %H:%M:%S') if file.upload_date else '',
                        '업로더ID': file.uploaded_by
                    })
                df = pd.DataFrame(files_data)
                sheet_name = '파일'
                
            elif data_type == 'labels':
                labels_data = []
                labels = Label.query.all()
                for label in labels:
                    labels_data.append({
                        'ID': label.id,
                        '사용자ID': label.user_id,
                        '파일ID': label.file_id,
                        '질환': label.disease,
                        '사진종류': label.view_type,
                        '코드': label.code,
                        '설명': label.description,
                        '생성일': label.created_at.strftime('%Y-%m-%d %H:%M:%S') if label.created_at else ''
                    })
                df = pd.DataFrame(labels_data)
                sheet_name = '라벨'
            
            df.to_excel(excel_path, sheet_name=sheet_name, index=False)
            print(f"✅ {sheet_name} 데이터가 Excel로 내보내졌습니다: {excel_filename}")
            return True
            
        except Exception as e:
            print(f"❌ Excel 내보내기 중 오류 발생: {e}")
            return False

# ==================== SQLite 뷰어 기능 ====================
def open_database_viewer():
    """SQLite 데이터베이스 뷰어 GUI 열기"""
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
    except ImportError:
        print("❌ tkinter가 설치되지 않았습니다.")
        return False
    
    class DatabaseViewer:
        def __init__(self, root):
            self.root = root
            self.root.title("데이터베이스 뷰어")
            self.root.geometry("1200x800")
            
            # 데이터베이스 경로
            self.db_path = os.path.join(os.path.dirname(__file__), DB_PATH)
            
            # 탭 생성
            self.notebook = ttk.Notebook(root)
            self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
            
            # 사용자 탭
            self.create_users_tab()
            
            # 파일 탭
            self.create_files_tab()
            
            # 라벨링 정보 탭
            self.create_labels_tab()
            
            # 새로고침 버튼
            refresh_btn = tk.Button(root, text="새로고침", command=self.refresh_all)
            refresh_btn.pack(pady=5)

        def create_users_tab(self):
            """사용자 정보 탭 생성"""
            users_frame = ttk.Frame(self.notebook)
            self.notebook.add(users_frame, text="사용자")
            
            # 트리뷰 생성
            columns = ('ID', '사용자명', '이메일', '가입일')
            self.users_tree = ttk.Treeview(users_frame, columns=columns, show='headings')
            
            # 컬럼 설정
            for col in columns:
                self.users_tree.heading(col, text=col)
                self.users_tree.column(col, width=150)
            
            # 스크롤바
            users_scrollbar = ttk.Scrollbar(users_frame, orient='vertical', command=self.users_tree.yview)
            self.users_tree.configure(yscrollcommand=users_scrollbar.set)
            
            # 배치
            self.users_tree.pack(side='left', fill='both', expand=True)
            users_scrollbar.pack(side='right', fill='y')
            
            # 사용자 데이터 로드
            self.load_users()

        def create_files_tab(self):
            """파일 정보 탭 생성"""
            files_frame = ttk.Frame(self.notebook)
            self.notebook.add(files_frame, text="파일")
            
            # 트리뷰 생성
            columns = ('ID', '파일명', '크기(KB)', '업로드일', '업로더')
            self.files_tree = ttk.Treeview(files_frame, columns=columns, show='headings')
            
            # 컬럼 설정
            for col in columns:
                self.files_tree.heading(col, text=col)
                self.files_tree.column(col, width=120)
            
            # 스크롤바
            files_scrollbar = ttk.Scrollbar(files_frame, orient='vertical', command=self.files_tree.yview)
            self.files_tree.configure(yscrollcommand=files_scrollbar.set)
            
            # 배치
            self.files_tree.pack(side='left', fill='both', expand=True)
            files_scrollbar.pack(side='right', fill='y')
            
            # 파일 데이터 로드
            self.load_files()

        def create_labels_tab(self):
            """라벨링 정보 탭 생성"""
            labels_frame = ttk.Frame(self.notebook)
            self.notebook.add(labels_frame, text="라벨링 정보")
            
            # 트리뷰 생성
            columns = ('ID', '사용자명', '파일명', '질환', '사진종류', '번호', '흉부X선소견', '최종기록일시')
            self.labels_tree = ttk.Treeview(labels_frame, columns=columns, show='headings')
            
            # 컬럼 설정
            column_widths = {
                'ID': 50,
                '사용자명': 100,
                '파일명': 120,
                '질환': 200,
                '사진종류': 80,
                '번호': 80,
                '흉부X선소견': 250,
                '최종기록일시': 150
            }
            
            for col in columns:
                self.labels_tree.heading(col, text=col)
                self.labels_tree.column(col, width=column_widths.get(col, 100))
            
            # 스크롤바
            labels_scrollbar = ttk.Scrollbar(labels_frame, orient='vertical', command=self.labels_tree.yview)
            self.labels_tree.configure(yscrollcommand=labels_scrollbar.set)
            
            # 배치
            self.labels_tree.pack(side='left', fill='both', expand=True)
            labels_scrollbar.pack(side='right', fill='y')
            
            # 라벨링 데이터 로드
            self.load_labels()

        def load_users(self):
            """사용자 데이터 로드"""
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # 기존 데이터 삭제
                for item in self.users_tree.get_children():
                    self.users_tree.delete(item)
                
                # 사용자 데이터 조회
                cursor.execute("SELECT id, username, email, created_at FROM user")
                users = cursor.fetchall()
                
                # 트리뷰에 데이터 추가
                for user in users:
                    self.users_tree.insert('', 'end', values=user)
                
                conn.close()
                
            except Exception as e:
                messagebox.showerror("오류", f"사용자 데이터 로드 실패: {str(e)}")

        def load_files(self):
            """파일 데이터 로드"""
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # 기존 데이터 삭제
                for item in self.files_tree.get_children():
                    self.files_tree.delete(item)
                
                # 파일 데이터 조회
                cursor.execute("""
                    SELECT f.id, f.filename, f.file_size, f.upload_date, u.username 
                    FROM file f 
                    JOIN user u ON f.uploaded_by = u.id
                """)
                files = cursor.fetchall()
                
                # 트리뷰에 데이터 추가
                for file in files:
                    size_kb = file[2] / 1024 if file[2] else 0
                    self.files_tree.insert('', 'end', values=(
                        file[0], file[1], f"{size_kb:.1f}", file[3], file[4]
                    ))
                
                conn.close()
                
            except Exception as e:
                messagebox.showerror("오류", f"파일 데이터 로드 실패: {str(e)}")

        def load_labels(self):
            """라벨링 데이터 로드"""
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # 기존 데이터 삭제
                for item in self.labels_tree.get_children():
                    self.labels_tree.delete(item)
                
                # 라벨링 데이터 조회
                cursor.execute("""
                    SELECT l.id, u.username, f.filename, l.disease, l.view_type, l.code, l.description, l.created_at
                    FROM label l
                    JOIN user u ON l.user_id = u.id
                    JOIN file f ON l.file_id = f.id
                    ORDER BY l.created_at DESC
                """)
                labels = cursor.fetchall()
                
                # 트리뷰에 데이터 추가
                for label in labels:
                    self.labels_tree.insert('', 'end', values=label)
                
                conn.close()
                
            except Exception as e:
                messagebox.showerror("오류", f"라벨링 데이터 로드 실패: {str(e)}")

        def refresh_all(self):
            """모든 데이터 새로고침"""
            self.load_users()
            self.load_files()
            self.load_labels()
            messagebox.showinfo("완료", "데이터가 새로고침되었습니다.")

    # GUI 실행
    root = tk.Tk()
    app = DatabaseViewer(root)
    root.mainloop()
    return True

# ==================== 파일 삭제 기능 ====================
def delete_file_by_id(file_id):
    """파일 ID로 파일 삭제 (CASCADE DELETE 지원)"""
    with app.app_context():
        try:
            file = db.session.get(File, file_id)
            if file:
                # 관련 라벨 개수 확인
                label_count = Label.query.filter_by(file_id=file_id).count()
                
                print(f"⚠️ 파일 삭제 확인:")
                print(f"   파일명: {file.filename}")
                print(f"   크기: {file.file_size} bytes")
                print(f"   경로: {file.file_path}")
                print(f"   관련 라벨: {label_count}개")
                
                if label_count > 0:
                    print(f"   ⚠️  이 파일과 관련된 라벨 {label_count}개도 함께 삭제됩니다.")
                
                confirm = input("정말로 삭제하시겠습니까? (yes를 입력하세요): ")
                if confirm.lower() != 'yes':
                    print("삭제가 취소되었습니다.")
                    return False
                
                # 실제 파일도 삭제
                if os.path.exists(file.file_path):
                    os.remove(file.file_path)
                    print(f"✅ 실제 파일 삭제: {file.file_path}")
                
                # 데이터베이스에서 삭제 (CASCADE DELETE로 관련 라벨도 자동 삭제)
                db.session.delete(file)
                db.session.commit()
                print(f"✅ 파일 {file.filename}이(가) 삭제되었습니다.")
                if label_count > 0:
                    print(f"✅ 관련 라벨 {label_count}개도 함께 삭제되었습니다.")
                return True
            else:
                print("❌ 파일을 찾을 수 없습니다.")
                return False
        except Exception as e:
            print(f"❌ 파일 삭제 중 오류 발생: {e}")
            db.session.rollback()
            return False

def delete_multiple_files_by_ids(file_ids):
    """여러 파일 ID로 파일들 삭제 (CASCADE DELETE 지원)"""
    with app.app_context():
        try:
            # 파일 ID들을 정수로 변환
            file_id_list = []
            for file_id_str in file_ids:
                try:
                    file_id_list.append(int(file_id_str.strip()))
                except ValueError:
                    print(f"❌ 잘못된 파일 ID: {file_id_str}")
                    return False
            
            # 파일들 조회
            files = []
            total_labels = 0
            for file_id in file_id_list:
                file = db.session.get(File, file_id)
                if file:
                    files.append(file)
                    # 관련 라벨 개수 확인
                    label_count = Label.query.filter_by(file_id=file_id).count()
                    total_labels += label_count
                else:
                    print(f"❌ 파일 ID {file_id}를 찾을 수 없습니다.")
            
            if not files:
                print("❌ 삭제할 파일이 없습니다.")
                return False
            
            # 삭제할 파일 목록 표시
            print(f"\n⚠️ 삭제할 파일 목록 ({len(files)}개):")
            total_size = 0
            for file in files:
                size_kb = file.file_size / 1024 if file.file_size else 0
                total_size += file.file_size
                label_count = Label.query.filter_by(file_id=file.id).count()
                print(f"   - {file.filename} ({size_kb:.1f}KB) [라벨: {label_count}개]")
            
            print(f"\n총 크기: {total_size/1024:.1f}KB")
            print(f"총 관련 라벨: {total_labels}개")
            
            if total_labels > 0:
                print(f"⚠️  이 파일들과 관련된 라벨 {total_labels}개도 함께 삭제됩니다.")
            
            # 사용자 확인
            confirm = input("\n정말로 이 파일들을 삭제하시겠습니까? (yes를 입력하세요): ")
            if confirm.lower() != 'yes':
                print("삭제가 취소되었습니다.")
                return False
            
            # 파일들 삭제
            deleted_count = 0
            deleted_labels = 0
            for file in files:
                try:
                    # 관련 라벨 개수 확인
                    label_count = Label.query.filter_by(file_id=file.id).count()
                    
                    # 실제 파일도 삭제
                    if os.path.exists(file.file_path):
                        os.remove(file.file_path)
                        print(f"✅ 실제 파일 삭제: {file.file_path}")
                    
                    # 데이터베이스에서 삭제 (CASCADE DELETE로 관련 라벨도 자동 삭제)
                    db.session.delete(file)
                    deleted_count += 1
                    deleted_labels += label_count
                    
                except Exception as e:
                    print(f"❌ 파일 {file.filename} 삭제 중 오류: {e}")
            
            # 변경사항 저장
            db.session.commit()
            print(f"✅ {deleted_count}개의 파일이 삭제되었습니다.")
            if deleted_labels > 0:
                print(f"✅ 관련 라벨 {deleted_labels}개도 함께 삭제되었습니다.")
            return True
            
        except Exception as e:
            print(f"❌ 다중 파일 삭제 중 오류 발생: {e}")
            db.session.rollback()
            return False

def delete_file_by_name(filename):
    """파일명으로 파일 삭제"""
    with app.app_context():
        try:
            file = File.query.filter_by(filename=filename).first()
            if file:
                return delete_file_by_id(file.id)
            else:
                print(f"❌ 파일을 찾을 수 없습니다: {filename}")
                return False
        except Exception as e:
            print(f"❌ 파일 삭제 중 오류 발생: {e}")
            return False

def list_files_for_deletion():
    """삭제할 파일 목록 표시 (라벨 개수 포함)"""
    with app.app_context():
        try:
            files = File.query.all()
            if files:
                print("\n=== 삭제 가능한 파일 목록 ===")
                for file in files:
                    size_kb = file.file_size / 1024 if file.file_size else 0
                    label_count = Label.query.filter_by(file_id=file.id).count()
                    print(f"ID: {file.id}, 파일명: {file.filename}, 크기: {size_kb:.1f}KB, 라벨: {label_count}개")
                return files
            else:
                print("삭제할 파일이 없습니다.")
                return []
        except Exception as e:
            print(f"❌ 파일 목록 조회 중 오류: {e}")
            return []

# ==================== 메뉴 업데이트 ====================
def main():
    while True:
        print("\n" + "="*50)
        print("🗄️  통합 데이터베이스 관리 도구")
        print("="*50)
        print("1. 모든 사용자 조회")
        print("2. 모든 파일 조회")
        print("3. 폴더에서 파일 업로드")
        print("4. 데이터베이스 백업")
        print("5. 백업 목록 조회")
        print("6. 백업에서 복원")
        print("7. 무결성 검증")
        print("8. Excel로 전체 데이터 내보내기")
        print("9. Excel로 선택 데이터 내보내기")
        print("10. SQLite 뷰어 열기")
        print("11. 파일 삭제")
        print("12. CASCADE DELETE 지원 DB 생성")
        print("13. 종료")
        choice = input("\n선택하세요 (1-13): ")
        if choice == '1':
            view_all_users()
        elif choice == '2':
            view_all_files()
        elif choice == '3':
            folder_path = input("업로드할 폴더 경로를 입력하세요: ")
            upload_files_from_folder(folder_path)
        elif choice == '4':
            create_backup()
        elif choice == '5':
            backups = list_backups()
            print("\n=== 백업 목록 ===")
            for b in backups:
                print(b)
        elif choice == '6':
            backups = list_backups()
            for i, b in enumerate(backups, 1):
                print(f"{i}. {b}")
            idx = input("복원할 백업 번호를 입력하세요: ")
            try:
                idx = int(idx) - 1
                if 0 <= idx < len(backups):
                    restore_backup(backups[idx])
            except:
                print("잘못된 입력입니다.")
        elif choice == '7':
            verify_database_integrity()
        elif choice == '8':
            export_to_excel()
        elif choice == '9':
            print("\n내보낼 데이터를 선택하세요:")
            print("1. 사용자 데이터")
            print("2. 파일 데이터")
            print("3. 라벨 데이터")
            data_choice = input("선택하세요 (1-3): ")
            if data_choice == '1':
                export_selected_data('users')
            elif data_choice == '2':
                export_selected_data('files')
            elif data_choice == '3':
                export_selected_data('labels')
            else:
                print("잘못된 선택입니다.")
        elif choice == '10':
            open_database_viewer()
        elif choice == '11':
            print("\n=== 파일 삭제 ===")
            print("1. 파일 ID로 삭제")
            print("2. 파일명으로 삭제")
            print("3. 파일 목록 보기")
            print("4. 여러 파일 한번에 삭제")
            delete_choice = input("선택하세요 (1-4): ")
            if delete_choice == '1':
                file_id = input("삭제할 파일 ID를 입력하세요: ")
                try:
                    delete_file_by_id(int(file_id))
                except ValueError:
                    print("올바른 숫자를 입력하세요.")
            elif delete_choice == '2':
                filename = input("삭제할 파일명을 입력하세요: ")
                delete_file_by_name(filename)
            elif delete_choice == '3':
                list_files_for_deletion()
            elif delete_choice == '4':
                print("\n=== 여러 파일 삭제 ===")
                print("파일 ID를 쉼표로 구분하여 입력하세요.")
                print("예시: 11, 12, 13")
                file_ids_input = input("삭제할 파일 ID들을 입력하세요: ")
                if file_ids_input.strip():
                    file_ids = [id.strip() for id in file_ids_input.split(',')]
                    delete_multiple_files_by_ids(file_ids)
                else:
                    print("파일 ID를 입력해주세요.")
            else:
                print("잘못된 선택입니다.")
        elif choice == '12':
            print("\n=== CASCADE DELETE 지원 데이터베이스 생성 ===")
            print("⚠️  이 작업은 기존 데이터베이스를 백업하고 새로운 스키마로 재생성합니다.")
            confirm = input("계속하시겠습니까? (yes를 입력하세요): ")
            if confirm.lower() == 'yes':
                create_database_with_cascade()
            else:
                print("작업이 취소되었습니다.")
        elif choice == '13':
            print("프로그램을 종료합니다.")
            break
        else:
            print("올바른 선택을 해주세요.")

if __name__ == "__main__":
    main() 