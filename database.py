import sqlite3
from pathlib import Path
from datetime import datetime
import sys

class Database:
    CURRENT_SCHEMA_VERSION = 3

    def __init__(self, db_name='patients.db'):
        self.db_name = self._resolve_db_path(db_name)
        self._db_file_existed_before_connect = self._database_file_exists()
        self.conn = sqlite3.connect(self.db_name)
        self.conn.execute('PRAGMA foreign_keys = ON')
        self.migrate_schema()

    def _resolve_db_path(self, db_name):
        if db_name == ':memory:':
            return db_name
        db_path = Path(db_name)
        if db_path.is_absolute():
            return str(db_path)
        if getattr(sys, "frozen", False):
            return str(Path(sys.executable).resolve().parent / db_name)
        return str((Path(__file__).resolve().parent / db_name).resolve())

    def migrate_schema(self):
        user_version = self._get_user_version()
        if user_version < self.CURRENT_SCHEMA_VERSION:
            self._backup_database_before_migration()
        try:
            self.conn.execute('BEGIN')
            self.create_tables()
            self._ensure_schema_columns()
            self._migrate_medical_cases()
            self._migrate_diagnostics_to_cases()
            self.conn.execute(f'PRAGMA user_version = {self.CURRENT_SCHEMA_VERSION}')
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def create_tables(self):
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY,
                surname TEXT NOT NULL,
                name TEXT,
                dob TEXT,
                created_at TEXT,
                city TEXT,
                street TEXT,
                house TEXT,
                apartment TEXT,
                patronymic TEXT
            )
        ''')
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS medical_cases (
                id INTEGER PRIMARY KEY,
                patient_id INTEGER NOT NULL,
                card_number TEXT NOT NULL,
                admission_date TEXT,
                admission_time TEXT,
                discharge_date TEXT,
                discharge_time TEXT,
                outcome TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                final_diagnosis TEXT,
                discharge_summary TEXT,
                recommendations TEXT,
                created_at TEXT,
                closed_at TEXT,
                FOREIGN KEY (patient_id) REFERENCES patients (id)
            )
        ''')
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS histories (
                id INTEGER PRIMARY KEY,
                patient_id INTEGER,
                visit_date TEXT,
                record_type TEXT,
                examination TEXT,
                diagnosis TEXT,
                treatment TEXT,
                notes TEXT,
                diag_admission TEXT,
                diag_clinical TEXT,
                diag_comorbid TEXT,
                history_id INTEGER,
                FOREIGN KEY (patient_id) REFERENCES patients (id)
            )
        ''')
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS case_print_state (
                case_id INTEGER PRIMARY KEY,
                diary_current_page_used_mm INTEGER NOT NULL DEFAULT 0,
                diary_last_printed_at TEXT,
                diary_last_batch_id TEXT,
                FOREIGN KEY (case_id) REFERENCES medical_cases (id)
            )
        ''')
        # Appointments / plan items tied to a specific history
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY,
                history_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                method TEXT,
                freq TEXT,
                date_assign TEXT,
                date_cancel TEXT,
                created_at TEXT,
                FOREIGN KEY (history_id) REFERENCES histories (id)
            )
        ''')
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS diagnostics (
                id INTEGER PRIMARY KEY,
                patient_id INTEGER NOT NULL,
                history_id INTEGER,
                study_date TEXT,
                name TEXT,
                results TEXT,
                created_at TEXT,
                FOREIGN KEY (patient_id) REFERENCES patients (id)
            )
        ''')

    def _get_user_version(self):
        row = self.conn.execute('PRAGMA user_version').fetchone()
        return int(row[0]) if row else 0

    def _backup_database_before_migration(self):
        if self.db_name == ':memory:':
            return
        if not self._db_file_existed_before_connect:
            return
        db_path = Path(self.db_name)
        if not db_path.exists() or not db_path.is_file():
            return
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        backup_dir = db_path.parent / 'backups'
        backup_dir.mkdir(exist_ok=True)
        backup_path = backup_dir / f'{db_path.stem}_backup_before_migration_{timestamp}{db_path.suffix}'
        with sqlite3.connect(backup_path) as backup_conn:
            self.conn.backup(backup_conn)

    def _database_file_exists(self):
        if self.db_name == ':memory:':
            return False
        return Path(self.db_name).is_file()

    def _table_columns(self, table_name):
        cursor = self.conn.execute(f'PRAGMA table_info({table_name})')
        return {row[1] for row in cursor.fetchall()}

    def _ensure_columns(self, table_name, columns):
        existing_columns = self._table_columns(table_name)
        for column_name, column_definition in columns:
            if column_name not in existing_columns:
                self.conn.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_definition}')
                existing_columns.add(column_name)

    def _ensure_schema_columns(self):
        self._ensure_columns('patients', [
            ('surname', 'surname TEXT DEFAULT ""'),
            ('name', 'name TEXT DEFAULT ""'),
            ('dob', 'dob TEXT DEFAULT ""'),
            ('created_at', 'created_at TEXT'),
            ('city', 'city TEXT DEFAULT ""'),
            ('street', 'street TEXT DEFAULT ""'),
            ('house', 'house TEXT DEFAULT ""'),
            ('apartment', 'apartment TEXT DEFAULT ""'),
            ('patronymic', 'patronymic TEXT DEFAULT ""'),
        ])
        self._ensure_columns('histories', [
            ('patient_id', 'patient_id INTEGER'),
            ('visit_date', 'visit_date TEXT'),
            ('record_type', 'record_type TEXT DEFAULT ""'),
            ('examination', 'examination TEXT DEFAULT ""'),
            ('diagnosis', 'diagnosis TEXT DEFAULT ""'),
            ('treatment', 'treatment TEXT DEFAULT ""'),
            ('notes', 'notes TEXT DEFAULT ""'),
            ('diag_admission', 'diag_admission TEXT DEFAULT ""'),
            ('diag_clinical', 'diag_clinical TEXT DEFAULT ""'),
            ('diag_comorbid', 'diag_comorbid TEXT DEFAULT ""'),
            ('history_id', 'history_id INTEGER'),
            ('printed_at', 'printed_at TEXT'),
            ('print_batch_id', 'print_batch_id TEXT'),
            ('print_top_offset_mm', 'print_top_offset_mm INTEGER'),
        ])
        self._ensure_columns('appointments', [
            ('history_id', 'history_id INTEGER'),
            ('name', 'name TEXT DEFAULT ""'),
            ('method', 'method TEXT DEFAULT ""'),
            ('freq', 'freq TEXT DEFAULT ""'),
            ('date_assign', 'date_assign TEXT DEFAULT ""'),
            ('date_cancel', 'date_cancel TEXT DEFAULT ""'),
            ('created_at', 'created_at TEXT'),
        ])
        self._ensure_columns('diagnostics', [
            ('patient_id', 'patient_id INTEGER'),
            ('history_id', 'history_id INTEGER'),
            ('study_date', 'study_date TEXT DEFAULT ""'),
            ('name', 'name TEXT DEFAULT ""'),
            ('results', 'results TEXT DEFAULT ""'),
            ('created_at', 'created_at TEXT'),
        ])
        self._ensure_columns('medical_cases', [
            ('patient_id', 'patient_id INTEGER'),
            ('card_number', 'card_number TEXT DEFAULT ""'),
            ('admission_date', 'admission_date TEXT DEFAULT ""'),
            ('admission_time', 'admission_time TEXT DEFAULT ""'),
            ('discharge_date', 'discharge_date TEXT DEFAULT ""'),
            ('discharge_time', 'discharge_time TEXT DEFAULT ""'),
            ('outcome', 'outcome TEXT DEFAULT ""'),
            ('status', 'status TEXT NOT NULL DEFAULT "active"'),
            ('final_diagnosis', 'final_diagnosis TEXT DEFAULT ""'),
            ('discharge_summary', 'discharge_summary TEXT DEFAULT ""'),
            ('recommendations', 'recommendations TEXT DEFAULT ""'),
            ('created_at', 'created_at TEXT'),
            ('closed_at', 'closed_at TEXT'),
        ])

    def _migrate_medical_cases(self):
        self.conn.execute('''
            INSERT OR IGNORE INTO medical_cases (
                id, patient_id, card_number, admission_date, admission_time,
                outcome, status, final_diagnosis, created_at
            )
            SELECT
                h.history_id,
                h.patient_id,
                CAST(h.history_id AS TEXT),
                '',
                '',
                '',
                'active',
                COALESCE(MAX(NULLIF(h.diag_clinical, '')), MAX(NULLIF(h.diag_admission, '')), ''),
                MIN(h.visit_date)
            FROM histories h
            WHERE h.history_id IS NOT NULL
            GROUP BY h.history_id, h.patient_id
        ''')
        cursor = self.conn.execute('SELECT DISTINCT patient_id FROM histories WHERE history_id IS NULL')
        for (patient_id,) in cursor.fetchall():
            created_at = datetime.now().isoformat()
            next_number = self.get_next_history_number()
            case_cursor = self.conn.execute(
                '''INSERT INTO medical_cases (
                       patient_id, card_number, admission_date, admission_time,
                       outcome, status, final_diagnosis, created_at
                   ) VALUES (?, ?, '', '', '', 'active', '', ?)''',
                (patient_id, str(next_number), created_at),
            )
            self.conn.execute(
                'UPDATE histories SET history_id = ? WHERE patient_id = ? AND history_id IS NULL',
                (case_cursor.lastrowid, patient_id),
            )

    def _migrate_diagnostics_to_cases(self):
        self.conn.execute('''
            UPDATE diagnostics
               SET history_id = (
                   SELECT MIN(c.id)
                     FROM medical_cases c
                    WHERE c.patient_id = diagnostics.patient_id
               )
             WHERE history_id IS NULL
               AND (
                   SELECT COUNT(*)
                     FROM medical_cases c
                    WHERE c.patient_id = diagnostics.patient_id
               ) = 1
        ''')

    def add_patient(self, surname, name='', dob='', city='', street='', house='', apartment='', patronymic=''):
        created_at = datetime.now().isoformat()
        cursor = self.conn.execute(
            'INSERT INTO patients (surname, name, dob, created_at, city, street, house, apartment, patronymic) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (surname, name, dob, created_at, city, street, house, apartment, patronymic),
        )
        self.conn.commit()
        return cursor.lastrowid

    def create_medical_case(self, patient_id, card_number, admission_date='', admission_time='', final_diagnosis=''):
        created_at = datetime.now().isoformat()
        cursor = self.conn.execute(
            '''INSERT INTO medical_cases (
                   patient_id, card_number, admission_date, admission_time,
                   status, final_diagnosis, created_at
               ) VALUES (?, ?, ?, ?, 'active', ?, ?)''',
            (patient_id, card_number, admission_date, admission_time, final_diagnosis, created_at),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_case_by_id(self, case_id):
        cursor = self.conn.execute(
            '''SELECT id, patient_id, card_number, admission_date, admission_time,
                      discharge_date, discharge_time, outcome, status,
                      final_diagnosis, discharge_summary, recommendations,
                      created_at, closed_at
               FROM medical_cases WHERE id = ?''',
            (case_id,),
        )
        return cursor.fetchone()

    def get_cases(self, status=None):
        params = []
        where = ''
        if status:
            where = 'WHERE c.status = ?'
            params.append(status)
        cursor = self.conn.execute(
            f'''SELECT
                    c.id, c.patient_id, c.card_number, c.admission_date, c.admission_time,
                    c.discharge_date, c.discharge_time, c.outcome, c.status,
                    c.final_diagnosis, c.discharge_summary, c.recommendations,
                    c.created_at, c.closed_at,
                    p.surname, p.name, p.dob, p.patronymic
                FROM medical_cases c
                JOIN patients p ON p.id = c.patient_id
                {where}
                ORDER BY COALESCE(c.closed_at, c.created_at) DESC, c.id DESC''',
            params,
        )
        return cursor.fetchall()

    def update_case_admission(self, case_id, card_number, admission_date='', admission_time='', final_diagnosis=''):
        self.conn.execute(
            '''UPDATE medical_cases
               SET card_number = ?, admission_date = ?, admission_time = ?, final_diagnosis = ?
               WHERE id = ?''',
            (card_number, admission_date, admission_time, final_diagnosis, case_id),
        )
        self.conn.commit()

    def discharge_case(self, case_id, discharge_date='', discharge_time='', outcome='', final_diagnosis='', discharge_summary='', recommendations=''):
        closed_at = datetime.now().isoformat()
        self.conn.execute(
            '''UPDATE medical_cases
               SET discharge_date = ?, discharge_time = ?, outcome = ?, status = 'archived',
                   final_diagnosis = ?, discharge_summary = ?, recommendations = ?, closed_at = ?
               WHERE id = ?''',
            (discharge_date, discharge_time, outcome, final_diagnosis, discharge_summary, recommendations, closed_at, case_id),
        )
        self.conn.commit()

    def reopen_case(self, case_id):
        self.conn.execute(
            '''UPDATE medical_cases
               SET status = 'active', closed_at = NULL
               WHERE id = ?''',
            (case_id,),
        )
        self.conn.commit()

    def get_patients(self):
        cursor = self.conn.execute('SELECT * FROM patients ORDER BY surname')
        return cursor.fetchall()

    def get_patient_by_id(self, patient_id):
        cursor = self.conn.execute('SELECT * FROM patients WHERE id = ?', (patient_id,))
        return cursor.fetchone()

    def add_history(self, patient_id, record_type, examination, diagnosis='', treatment='', notes='', diag_admission='', diag_clinical='', diag_comorbid='', history_id=None, visit_date=None):
        visit_date = visit_date or datetime.now().isoformat()
        cursor = self.conn.execute('INSERT INTO histories (patient_id, visit_date, record_type, examination, diagnosis, treatment, notes, diag_admission, diag_clinical, diag_comorbid, history_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                          (patient_id, visit_date, record_type, examination, diagnosis, treatment, notes, diag_admission, diag_clinical, diag_comorbid, history_id))
        self.conn.commit()
        return cursor.lastrowid

    def add_appointment(self, history_id, name, method='', freq='', date_assign='', date_cancel=''):
        created_at = datetime.now().isoformat()
        cursor = self.conn.execute(
            'INSERT INTO appointments (history_id, name, method, freq, date_assign, date_cancel, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (history_id, name, method, freq, date_assign, date_cancel, created_at)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_history_record(self, patient_id, record_type, logical_history_id=None):
        if logical_history_id is None:
            cursor = self.conn.execute(
                'SELECT id, patient_id, visit_date, record_type, examination, diagnosis, treatment, notes, diag_admission, diag_clinical, diag_comorbid, history_id FROM histories WHERE patient_id = ? AND record_type = ? ORDER BY visit_date DESC LIMIT 1',
                (patient_id, record_type),
            )
        else:
            cursor = self.conn.execute(
                'SELECT id, patient_id, visit_date, record_type, examination, diagnosis, treatment, notes, diag_admission, diag_clinical, diag_comorbid, history_id FROM histories WHERE patient_id = ? AND record_type = ? AND history_id = ? ORDER BY visit_date DESC LIMIT 1',
                (patient_id, record_type, logical_history_id),
            )
        return cursor.fetchone()

    def has_primary_exam(self, patient_id, logical_history_id=None):
        if logical_history_id is None:
            cursor = self.conn.execute('SELECT 1 FROM histories WHERE patient_id = ? AND record_type = "primary_exam" LIMIT 1', (patient_id,))
        else:
            cursor = self.conn.execute('SELECT 1 FROM histories WHERE patient_id = ? AND record_type = "primary_exam" AND history_id = ? LIMIT 1', (patient_id, logical_history_id))
        return cursor.fetchone() is not None

    def get_appointments(self, history_id):
        cursor = self.conn.execute('SELECT id, history_id, name, method, freq, date_assign, date_cancel, created_at FROM appointments WHERE history_id = ? ORDER BY id', (history_id,))
        return cursor.fetchall()

    def get_appointments_for_patient(self, patient_id):
        # Join appointments with histories to return all appointments for a given patient
        cursor = self.conn.execute(
            '''SELECT a.id, a.history_id, a.name, a.method, a.freq, a.date_assign, a.date_cancel, a.created_at
               FROM appointments a
               JOIN histories h ON a.history_id = h.id
               WHERE h.patient_id = ?
               ORDER BY a.created_at, a.id''',
            (patient_id,)
        )
        return cursor.fetchall()

    def get_appointments_for_logical_history(self, patient_id, logical_history_id):
        cursor = self.conn.execute(
            '''SELECT a.id, a.history_id, a.name, a.method, a.freq, a.date_assign, a.date_cancel, a.created_at
               FROM appointments a
               JOIN histories h ON a.history_id = h.id
               WHERE h.patient_id = ? AND h.history_id = ?
               ORDER BY a.created_at, a.id''',
            (patient_id, logical_history_id)
        )
        return cursor.fetchall()

    def delete_appointment(self, appointment_id):
        self.conn.execute('DELETE FROM appointments WHERE id = ?', (appointment_id,))
        self.conn.commit()

    def update_appointment(self, appointment_id, name, method, freq, date_assign, date_cancel):
        self.conn.execute('UPDATE appointments SET name = ?, method = ?, freq = ?, date_assign = ?, date_cancel = ? WHERE id = ?',
                          (name, method, freq, date_assign, date_cancel, appointment_id))
        self.conn.commit()

    def delete_appointments_for_history(self, history_id):
        self.conn.execute('DELETE FROM appointments WHERE history_id = ?', (history_id,))
        self.conn.commit()

    def update_patient(self, patient_id, surname, name, dob, city='', street='', house='', apartment='', patronymic=''):
        self.conn.execute(
            'UPDATE patients SET surname = ?, name = ?, dob = ?, city = ?, street = ?, house = ?, apartment = ?, patronymic = ? WHERE id = ?',
            (surname, name, dob, city, street, house, apartment, patronymic, patient_id),
        )
        self.conn.commit()

    def delete_patient(self, patient_id):
        self.conn.execute('''
            DELETE FROM appointments
            WHERE history_id IN (SELECT id FROM histories WHERE patient_id = ?)
        ''', (patient_id,))
        self.conn.execute('DELETE FROM diagnostics WHERE patient_id = ?', (patient_id,))
        self.conn.execute('DELETE FROM histories WHERE patient_id = ?', (patient_id,))
        self.conn.execute('''
            DELETE FROM case_print_state
            WHERE case_id IN (SELECT id FROM medical_cases WHERE patient_id = ?)
        ''', (patient_id,))
        self.conn.execute('DELETE FROM medical_cases WHERE patient_id = ?', (patient_id,))
        self.conn.execute('DELETE FROM patients WHERE id = ?', (patient_id,))
        self.conn.commit()

    def get_histories(self, patient_id):
        cursor = self.conn.execute('SELECT id, patient_id, visit_date, record_type, examination, diagnosis, treatment, notes, diag_admission, diag_clinical, diag_comorbid, history_id FROM histories WHERE patient_id = ? ORDER BY visit_date DESC', (patient_id,))
        return cursor.fetchall()

    def get_history_by_id(self, record_id):
        cursor = self.conn.execute('SELECT id, patient_id, visit_date, record_type, examination, diagnosis, treatment, notes, diag_admission, diag_clinical, diag_comorbid, history_id FROM histories WHERE id = ?', (record_id,))
        return cursor.fetchone()

    def get_diary_records_for_case(self, patient_id, logical_history_id, only_unprinted=False):
        params = [patient_id, logical_history_id]
        printed_filter = ''
        if only_unprinted:
            printed_filter = ' AND printed_at IS NULL'
        cursor = self.conn.execute(f'''
            SELECT id, patient_id, visit_date, record_type, examination, diagnosis, treatment, notes,
                   diag_admission, diag_clinical, diag_comorbid, history_id,
                   printed_at, print_batch_id, print_top_offset_mm
              FROM histories
             WHERE patient_id = ?
               AND history_id = ?
               AND record_type = 'diary'
               {printed_filter}
             ORDER BY visit_date ASC, id ASC
        ''', params)
        return cursor.fetchall()

    def get_case_print_state(self, case_id):
        cursor = self.conn.execute('''
            SELECT case_id, diary_current_page_used_mm, diary_last_printed_at, diary_last_batch_id
              FROM case_print_state
             WHERE case_id = ?
        ''', (case_id,))
        row = cursor.fetchone()
        if row:
            return row
        return (case_id, 0, None, None)

    def mark_histories_printed(self, record_ids, batch_id, top_offset_mm, printed_at=None):
        if not record_ids:
            return
        printed_at = printed_at or datetime.now().isoformat()
        self.conn.executemany(
            'UPDATE histories SET printed_at = ?, print_batch_id = ?, print_top_offset_mm = ? WHERE id = ?',
            [(printed_at, batch_id, top_offset_mm, record_id) for record_id in record_ids],
        )
        self.conn.commit()

    def update_case_diary_print_state(self, case_id, used_mm, batch_id, printed_at=None):
        printed_at = printed_at or datetime.now().isoformat()
        self.conn.execute('''
            INSERT INTO case_print_state (
                case_id, diary_current_page_used_mm, diary_last_printed_at, diary_last_batch_id
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(case_id) DO UPDATE SET
                diary_current_page_used_mm = excluded.diary_current_page_used_mm,
                diary_last_printed_at = excluded.diary_last_printed_at,
                diary_last_batch_id = excluded.diary_last_batch_id
        ''', (case_id, int(used_mm), printed_at, batch_id))
        self.conn.commit()

    def update_history(self, history_id_row, record_type, examination, diagnosis, treatment, notes, visit_date=None, diag_admission='', diag_clinical='', diag_comorbid='', logical_history_id=None):
        if visit_date is not None:
            self.conn.execute('UPDATE histories SET record_type = ?, examination = ?, diagnosis = ?, treatment = ?, notes = ?, visit_date = ?, diag_admission = ?, diag_clinical = ?, diag_comorbid = ?, history_id = ? WHERE id = ?',
                              (record_type, examination, diagnosis, treatment, notes, visit_date, diag_admission, diag_clinical, diag_comorbid, logical_history_id, history_id_row))
        else:
            self.conn.execute('UPDATE histories SET record_type = ?, examination = ?, diagnosis = ?, treatment = ?, notes = ?, diag_admission = ?, diag_clinical = ?, diag_comorbid = ?, history_id = ? WHERE id = ?',
                              (record_type, examination, diagnosis, treatment, notes, diag_admission, diag_clinical, diag_comorbid, logical_history_id, history_id_row))
        self.conn.commit()

    def delete_history(self, record_id):
        # remove appointments tied to this record first if it's a plan/hist
        try:
            self.conn.execute('DELETE FROM appointments WHERE history_id = ?', (record_id,))
        except Exception:
            pass
        self.conn.execute('DELETE FROM histories WHERE id = ?', (record_id,))
        self.conn.commit()

    def delete_entire_history_group(self, history_id):
        """Удаляет все записи, связанные с логическим номером истории болезни (history_id)."""
        if not history_id:
            return
        # Сначала назначения для всех записей этой группы
        self.conn.execute('''
            DELETE FROM appointments 
            WHERE history_id IN (SELECT id FROM histories WHERE history_id = ?)
        ''', (history_id,))
        self.conn.execute('DELETE FROM diagnostics WHERE history_id = ?', (history_id,))
        # Затем сами записи
        self.conn.execute('DELETE FROM histories WHERE history_id = ?', (history_id,))
        self.conn.execute('DELETE FROM medical_cases WHERE id = ?', (history_id,))
        self.conn.commit()

    def add_diagnostic(self, patient_id, logical_history_id, study_date='', name='', results=''):
        created_at = datetime.now().isoformat()
        cursor = self.conn.execute(
            'INSERT INTO diagnostics (patient_id, history_id, study_date, name, results, created_at) VALUES (?, ?, ?, ?, ?, ?)',
            (patient_id, logical_history_id, study_date, name, results, created_at),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_diagnostics(self, patient_id, logical_history_id=None):
        if logical_history_id is None:
            cursor = self.conn.execute(
                'SELECT id, patient_id, history_id, study_date, name, results, created_at FROM diagnostics WHERE patient_id = ? ORDER BY created_at, id',
                (patient_id,),
            )
        else:
            cursor = self.conn.execute(
                'SELECT id, patient_id, history_id, study_date, name, results, created_at FROM diagnostics WHERE patient_id = ? AND history_id = ? ORDER BY created_at, id',
                (patient_id, logical_history_id),
            )
        return cursor.fetchall()

    def update_diagnostic(self, diagnostic_id, study_date='', name='', results=''):
        self.conn.execute(
            'UPDATE diagnostics SET study_date = ?, name = ?, results = ? WHERE id = ?',
            (study_date, name, results, diagnostic_id),
        )
        self.conn.commit()

    def delete_diagnostic(self, diagnostic_id):
        self.conn.execute('DELETE FROM diagnostics WHERE id = ?', (diagnostic_id,))
        self.conn.commit()

    def get_next_history_number(self) -> int:
        """Возвращает следующий номер истории болезни (history_id), начиная с 1."""
        cursor = self.conn.execute('SELECT COALESCE(MAX(id), 0) + 1 FROM medical_cases')
        row = cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else 1

    def close(self):
        self.conn.close()
