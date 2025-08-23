#!/usr/bin/env python3
"""
질환 데이터 마이그레이션 스크립트
기존 단일 질환 데이터를 JSON 배열 형태로 변환
"""

import sqlite3
import json
import os
from datetime import datetime

def migrate_disease_to_json():
    """기존 단일 질환 데이터를 JSON 배열 형태로 마이그레이션"""
    
    # 데이터베이스 경로
    db_path = os.path.join('database', 'app.db')
    
    if not os.path.exists(db_path):
        print(f"❌ 데이터베이스 파일을 찾을 수 없습니다: {db_path}")
        return False
    
    # 백업 생성
    backup_path = os.path.join('database', f'app_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')
    try:
        import shutil
        shutil.copy2(db_path, backup_path)
        print(f"✅ 데이터베이스 백업 생성: {backup_path}")
    except Exception as e:
        print(f"⚠️ 백업 생성 실패: {e}")
        return False
    
    try:
        # 데이터베이스 연결
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 기존 라벨 데이터 조회
        cursor.execute("SELECT id, disease FROM label")
        labels = cursor.fetchall()
        
        print(f"📊 총 {len(labels)}개의 라벨 데이터를 마이그레이션합니다...")
        
        migrated_count = 0
        for label_id, old_disease in labels:
            try:
                # 기존 질환을 JSON 배열로 변환
                if old_disease:
                    # 이미 JSON 형태인지 확인
                    try:
                        json.loads(old_disease)
                        # 이미 JSON 형태라면 건너뛰기
                        print(f"⏭️ 라벨 {label_id}: 이미 JSON 형태입니다")
                        continue
                    except (json.JSONDecodeError, TypeError):
                        # 단일 질환을 배열로 변환
                        new_disease_json = json.dumps([old_disease], ensure_ascii=False)
                        
                        # 데이터베이스 업데이트
                        cursor.execute(
                            "UPDATE label SET disease = ? WHERE id = ?",
                            (new_disease_json, label_id)
                        )
                        
                        migrated_count += 1
                        print(f"✅ 라벨 {label_id}: '{old_disease}' → {new_disease_json}")
                else:
                    print(f"⚠️ 라벨 {label_id}: 질환 데이터가 없습니다")
                    
            except Exception as e:
                print(f"❌ 라벨 {label_id} 마이그레이션 실패: {e}")
                continue
        
        # 변경사항 저장
        conn.commit()
        print(f"🎉 마이그레이션 완료! {migrated_count}개 라벨이 업데이트되었습니다.")
        
        # 마이그레이션 결과 확인
        cursor.execute("SELECT COUNT(*) FROM label")
        total_labels = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM label WHERE disease LIKE '[%'")
        json_labels = cursor.fetchone()[0]
        
        print(f"📈 마이그레이션 결과:")
        print(f"   - 총 라벨 수: {total_labels}")
        print(f"   - JSON 형태 라벨 수: {json_labels}")
        print(f"   - 변환률: {(json_labels/total_labels*100):.1f}%")
        
        return True
        
    except Exception as e:
        print(f"❌ 마이그레이션 중 오류 발생: {e}")
        return False
        
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    print("🔄 질환 데이터 마이그레이션을 시작합니다...")
    print("=" * 50)
    
    success = migrate_disease_to_json()
    
    print("=" * 50)
    if success:
        print("✅ 마이그레이션이 성공적으로 완료되었습니다!")
        print("💡 이제 라벨링 시스템에서 질환 중복선택이 가능합니다.")
    else:
        print("❌ 마이그레이션이 실패했습니다.")
        print("💡 백업 파일을 확인하고 수동으로 복구하세요.") 