import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
from datetime import datetime

class DatabaseViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("데이터베이스 뷰어")
        self.root.geometry("1000x700")
        
        # 데이터베이스 경로
        self.db_path = os.path.join(os.path.dirname(__file__), 'database', 'app.db')
        
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
        columns = ('ID', '사용자명', '파일명', '라벨', '라벨링일')
        self.labels_tree = ttk.Treeview(labels_frame, columns=columns, show='headings')
        
        # 컬럼 설정
        for col in columns:
            self.labels_tree.heading(col, text=col)
            self.labels_tree.column(col, width=150)
        
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
                SELECT l.id, u.username, f.filename, l.label_type, l.created_at
                FROM label l
                JOIN user u ON l.user_id = u.id
                JOIN file f ON l.file_id = f.id
                ORDER BY l.created_at DESC
            """)
            labels = cursor.fetchall()
            
            # 트리뷰에 데이터 추가
            for label in labels:
                # 라벨 값을 한글로 변환
                label_text = "좋아요" if label[3] == "like" else "싫어요" if label[3] == "dislike" else label[3]
                self.labels_tree.insert('', 'end', values=(
                    label[0], label[1], label[2], label_text, label[4]
                ))
            
            conn.close()
            
        except Exception as e:
            messagebox.showerror("오류", f"라벨링 데이터 로드 실패: {str(e)}")

    def refresh_all(self):
        """모든 데이터 새로고침"""
        self.load_users()
        self.load_files()
        self.load_labels()
        messagebox.showinfo("알림", "데이터가 새로고침되었습니다.")

def main():
    root = tk.Tk()
    app = DatabaseViewer(root)
    root.mainloop()

if __name__ == "__main__":
    main() 