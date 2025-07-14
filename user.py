from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone, timedelta

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone(timedelta(hours=9))))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class File(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False, unique=True)
    file_path = db.Column(db.String(500), nullable=False)  # 실제 파일 경로
    file_size = db.Column(db.Integer)  # 파일 크기 (바이트)
    upload_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone(timedelta(hours=9))))
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # 관계 설정 (관계는 데이터베이스에서 테이블 간의 연결을 의미합니다)
    user = db.relationship('User', backref=db.backref('files', lazy=True))
    # cascade delete 설정: 파일이 삭제되면 관련된 라벨들도 자동 삭제
    labels = db.relationship('Label', backref='file', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<File {self.filename}>'

    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'file_size': self.file_size,
            'upload_date': self.upload_date.isoformat() if self.upload_date else None,
            'uploaded_by': self.user.username if self.user else None
        }

class Label(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    file_id = db.Column(db.Integer, db.ForeignKey('file.id', ondelete='CASCADE'), nullable=False)
    disease = db.Column(db.String(100), nullable=False)         # 질환
    view_type = db.Column(db.String(20), nullable=False)        # 사진 종류 (AP, LATDEQ, LAT, PA)
    code = db.Column(db.String(20), nullable=False)             # 번호 (예: RDS_1, BPD_1)
    description = db.Column(db.String(255), nullable=False)     # 흉부 X선 소견
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone(timedelta(hours=9))))

    # 관계 설정
    user = db.relationship('User', backref=db.backref('labels', lazy=True))

    def __repr__(self):
        return f'<Label {self.user.username} -> {self.file.filename}: {self.disease}/{self.code}>'

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'file_id': self.file_id,
            'disease': self.disease,
            'view_type': self.view_type,
            'code': self.code,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'username': self.user.username if self.user else None,
            'filename': self.file.filename if self.file else None
        } 