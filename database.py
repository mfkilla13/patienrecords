import sqlite3
from datetime import datetime

class Database:
    def __init__(self, db_name='patients.db'):
        self.conn = sqlite3.connect(db_name)
        self.create_tables()

    def create_tables(self):
        # Fresh schema: store address components separately
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
                apartment TEXT
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
        # Add record_type column if it doesn't exist (for migration)
        try:
            self.conn.execute('ALTER TABLE histories ADD COLUMN record_type TEXT DEFAULT ""')
        except sqlite3.OperationalError:
            pass  # column already exists
        try:
            self.conn.execute('ALTER TABLE histories ADD COLUMN diag_admission TEXT DEFAULT ""')
        except sqlite3.OperationalError:
            pass
        try:
            self.conn.execute('ALTER TABLE histories ADD COLUMN diag_clinical TEXT DEFAULT ""')
        except sqlite3.OperationalError:
            pass
        try:
            self.conn.execute('ALTER TABLE histories ADD COLUMN diag_comorbid TEXT DEFAULT ""')
        except sqlite3.OperationalError:
            pass
        try:
            self.conn.execute('ALTER TABLE histories ADD COLUMN history_id INTEGER')
        except sqlite3.OperationalError:
            pass
        self.conn.commit()

    def add_patient(self, surname, name='', dob='', city='', street='', house='', apartment=''):
        created_at = datetime.now().isoformat()
        cursor = self.conn.execute(
            'INSERT INTO patients (surname, name, dob, created_at, city, street, house, apartment) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (surname, name, dob, created_at, city, street, house, apartment),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_patients(self):
        cursor = self.conn.execute('SELECT * FROM patients ORDER BY surname')
        return cursor.fetchall()

    def get_patient_by_id(self, patient_id):
        cursor = self.conn.execute('SELECT * FROM patients WHERE id = ?', (patient_id,))
        return cursor.fetchone()

    def add_history(self, patient_id, record_type, examination, diagnosis='', treatment='', notes='', diag_admission='', diag_clinical='', diag_comorbid='', history_id=None):
        visit_date = datetime.now().isoformat()
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

    def update_patient(self, patient_id, surname, name, dob, city='', street='', house='', apartment=''):
        self.conn.execute(
            'UPDATE patients SET surname = ?, name = ?, dob = ?, city = ?, street = ?, house = ?, apartment = ? WHERE id = ?',
            (surname, name, dob, city, street, house, apartment, patient_id),
        )
        self.conn.commit()

    def delete_patient(self, patient_id):
        self.conn.execute('DELETE FROM histories WHERE patient_id = ?', (patient_id,))
        self.conn.execute('DELETE FROM patients WHERE id = ?', (patient_id,))
        self.conn.commit()

    def get_histories(self, patient_id):
        cursor = self.conn.execute('SELECT id, patient_id, visit_date, record_type, examination, diagnosis, treatment, notes, diag_admission, diag_clinical, diag_comorbid, history_id FROM histories WHERE patient_id = ? ORDER BY visit_date DESC', (patient_id,))
        return cursor.fetchall()

    def get_history_by_id(self, record_id):
        cursor = self.conn.execute('SELECT id, patient_id, visit_date, record_type, examination, diagnosis, treatment, notes, diag_admission, diag_clinical, diag_comorbid, history_id FROM histories WHERE id = ?', (record_id,))
        return cursor.fetchone()

    def has_primary_exam(self, patient_id):
        cursor = self.conn.execute('SELECT 1 FROM histories WHERE patient_id = ? AND record_type = "primary_exam" LIMIT 1', (patient_id,))
        return cursor.fetchone() is not None

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
        # Затем сами записи
        self.conn.execute('DELETE FROM histories WHERE history_id = ?', (history_id,))
        self.conn.commit()

    def get_next_history_number(self) -> int:
        """Возвращает следующий номер истории болезни (history_id), начиная с 1."""
        cursor = self.conn.execute('SELECT COALESCE(MAX(history_id), 0) + 1 FROM histories')
        row = cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else 1

    def close(self):
        self.conn.close()