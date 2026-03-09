"""
Automatic password rotation scheduler

Schedules and executes automatic password rotations on a defined schedule.
"""

import asyncio
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Callable
from .models import RotationPolicy, RotationScheduleEntry


class PasswordRotationScheduler:
    """Manages automatic password rotation schedule"""
    
    def __init__(self, db_path: str = "~/.tools/rotation_schedule.db"):
        """Initialize rotation scheduler"""
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self.rotation_tasks = {}
    
    def _init_db(self) -> None:
        """Initialize schedule database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rotation_schedule (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    host TEXT NOT NULL,
                    last_rotation TEXT,
                    next_rotation TEXT,
                    rotation_enabled BOOLEAN DEFAULT 1,
                    days_until_next INTEGER,
                    policy_name TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rotation_history (
                    id TEXT PRIMARY KEY,
                    schedule_id TEXT,
                    rotation_time TEXT,
                    status TEXT,
                    error_message TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(schedule_id) REFERENCES rotation_schedule(id)
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_next_rotation 
                ON rotation_schedule(next_rotation)
            """)
            conn.commit()
    
    def add_rotation_entry(self, entry: RotationScheduleEntry) -> bool:
        """Add entry to rotation schedule"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO rotation_schedule (
                        id, username, host, last_rotation, next_rotation,
                        rotation_enabled, days_until_next
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    entry.id,
                    entry.username,
                    entry.host,
                    entry.last_rotation.isoformat() if entry.last_rotation else None,
                    entry.next_rotation.isoformat() if entry.next_rotation else None,
                    entry.rotation_enabled,
                    entry.days_until_next
                ))
                conn.commit()
            return True
        except Exception as e:
            print(f"Error adding rotation entry: {e}")
            return False
    
    def get_due_rotations(self) -> List[RotationScheduleEntry]:
        """Get all rotations due to run"""
        now = datetime.utcnow()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM rotation_schedule 
                WHERE rotation_enabled = 1 
                AND (next_rotation IS NULL OR next_rotation <= ?)
                ORDER BY next_rotation ASC
            """, (now.isoformat(),))
            
            entries = []
            for row in cursor.fetchall():
                entry = RotationScheduleEntry(
                    id=row['id'],
                    username=row['username'],
                    host=row['host'],
                    last_rotation=datetime.fromisoformat(row['last_rotation']) if row['last_rotation'] else None,
                    next_rotation=datetime.fromisoformat(row['next_rotation']) if row['next_rotation'] else None,
                    rotation_enabled=bool(row['rotation_enabled']),
                    days_until_next=row['days_until_next']
                )
                entries.append(entry)
            
            return entries
    
    def get_upcoming_rotations(self, days_ahead: int = 7) -> List[RotationScheduleEntry]:
        """Get rotations scheduled within N days"""
        now = datetime.utcnow()
        future = now + timedelta(days=days_ahead)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM rotation_schedule 
                WHERE rotation_enabled = 1 
                AND next_rotation BETWEEN ? AND ?
                ORDER BY next_rotation ASC
            """, (now.isoformat(), future.isoformat()))
            
            entries = []
            for row in cursor.fetchall():
                entry = RotationScheduleEntry(
                    id=row['id'],
                    username=row['username'],
                    host=row['host'],
                    last_rotation=datetime.fromisoformat(row['last_rotation']) if row['last_rotation'] else None,
                    next_rotation=datetime.fromisoformat(row['next_rotation']) if row['next_rotation'] else None,
                    rotation_enabled=bool(row['rotation_enabled']),
                    days_until_next=row['days_until_next']
                )
                entries.append(entry)
            
            return entries
    
    def update_rotation_time(self, entry_id: str, next_rotation: datetime) -> bool:
        """Update next rotation time for entry"""
        try:
            days_until = (next_rotation - datetime.utcnow()).days
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    UPDATE rotation_schedule 
                    SET next_rotation = ?, days_until_next = ?
                    WHERE id = ?
                """, (next_rotation.isoformat(), days_until, entry_id))
                conn.commit()
            
            return True
        except Exception as e:
            print(f"Error updating rotation time: {e}")
            return False
    
    def mark_rotation_completed(
        self,
        entry_id: str,
        policy: RotationPolicy,
        success: bool = True,
        error: Optional[str] = None
    ) -> bool:
        """Mark rotation as completed and schedule next one"""
        try:
            now = datetime.utcnow()
            next_rotation = now + timedelta(days=policy.rotation_interval_days)
            
            with sqlite3.connect(self.db_path) as conn:
                # Update schedule
                conn.execute("""
                    UPDATE rotation_schedule 
                    SET last_rotation = ?, next_rotation = ?, days_until_next = ?
                    WHERE id = ?
                """, (
                    now.isoformat(),
                    next_rotation.isoformat(),
                    policy.rotation_interval_days,
                    entry_id
                ))
                
                # LogHistory
                history_id = str(__import__('uuid').uuid4())
                conn.execute("""
                    INSERT INTO rotation_history (
                        id, schedule_id, rotation_time, status, error_message
                    ) VALUES (?, ?, ?, ?, ?)
                """, (
                    history_id,
                    entry_id,
                    now.isoformat(),
                    'success' if success else 'failed',
                    error
                ))
                
                conn.commit()
            
            return True
        except Exception as e:
            print(f"Error marking rotation completed: {e}")
            return False
    
    async def schedule_rotation(
        self,
        policy: RotationPolicy,
        change_password_callback: Callable
    ) -> None:
        """
        Main scheduler loop
        
        Args:
        - policy: Rotation policy
        - change_password_callback: async function to call for rotation
                                    Signature: async (host, username) -> bool
        """
        print(f"Starting password rotation scheduler...")
        print(f"Interval: every {policy.rotation_interval_days} days")
        print(f"Time: {policy.rotate_at_hour:02d}:{policy.rotate_at_minute:02d}")
        
        while True:
            try:
                now = datetime.utcnow()
                
                # Check for due rotations
                due = self.get_due_rotations()
                
                for entry in due:
                    print(f"🔄 Rotating password for {entry.username}@{entry.host}")
                    
                    try:
                        success = await change_password_callback(
                            entry.host,
                            entry.username
                        )
                        
                        self.mark_rotation_completed(
                            entry.id,
                            policy,
                            success=success
                        )
                        
                        if success:
                            print(f"✅ Rotation successful for {entry.username}@{entry.host}")
                        else:
                            print(f"❌ Rotation failed for {entry.username}@{entry.host}")
                    
                    except Exception as e:
                        print(f"❌ Error during rotation: {e}")
                        self.mark_rotation_completed(
                            entry.id,
                            policy,
                            success=False,
                            error=str(e)
                        )
                
                # Sleep until next check (check every hour)
                await asyncio.sleep(3600)
            
            except Exception as e:
                print(f"Scheduler error: {e}")
                await asyncio.sleep(60)
    
    def get_rotation_statistics(self) -> dict:
        """Get rotation statistics"""
        with sqlite3.connect(self.db_path) as conn:
            # Total scheduled
            total = conn.execute(
                "SELECT COUNT(*) as count FROM rotation_schedule"
            ).fetchone()[0]
            
            # Enabled
            enabled = conn.execute(
                "SELECT COUNT(*) as count FROM rotation_schedule WHERE rotation_enabled = 1"
            ).fetchone()[0]
            
            # Due now
            due = conn.execute(
                "SELECT COUNT(*) as count FROM rotation_schedule WHERE next_rotation <= datetime('now')"
            ).fetchone()[0]
            
            # Recent rotations (last 7 days)
            recent = conn.execute("""
                SELECT COUNT(*) as count FROM rotation_history 
                WHERE rotation_time >= datetime('now', '-7 days')
            """).fetchone()[0]
            
            # Success rate (last 30 days)
            stats = conn.execute("""
                SELECT 
                    status,
                    COUNT(*) as count
                FROM rotation_history
                WHERE rotation_time >= datetime('now', '-30 days')
                GROUP BY status
            """).fetchall()
            
            success_stats = {status: count for status, count in stats}
            
            return {
                'total_scheduled': total,
                'enabled': enabled,
                'due_now': due,
                'recent_rotations': recent,
                'success_rate': {
                    'success': success_stats.get('success', 0),
                    'failed': success_stats.get('failed', 0),
                }
            }
