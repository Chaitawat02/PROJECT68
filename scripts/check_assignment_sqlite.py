import sqlite3

DB = 'db.sqlite3'
ASSIGN_ID = '0753009317977'

con = sqlite3.connect(DB)
cur = con.cursor()

try:
    cur.execute("SELECT assignment_id, speaker_id, booking_id, status, assigned_at FROM main_speakerassignment WHERE assignment_id = ?", (ASSIGN_ID,))
    rows = cur.fetchall()
    if not rows:
        print('No assignment found with assignment_id =', ASSIGN_ID)
    else:
        for r in rows:
            print('assignment_id:', r[0], 'speaker_id:', r[1], 'booking_id:', r[2], 'status:', r[3], 'assigned_at:', r[4])
finally:
    con.close()
