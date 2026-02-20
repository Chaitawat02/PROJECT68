import sqlite3, json, sys, os

db = os.path.join(os.getcwd(), 'db.sqlite3')
if not os.path.exists(db):
    print('ERROR: db.sqlite3 not found', file=sys.stderr)
    sys.exit(1)

con = sqlite3.connect(db)
cur = con.cursor()
try:
    cur.execute('SELECT id, Si_ID, Si_name, target_index FROM main_silkpattern ORDER BY target_index')
    rows = cur.fetchall()
    for r in rows:
        obj = {'id': r[0], 'Si_ID': r[1], 'Si_name': r[2], 'target_index': r[3]}
        print(json.dumps(obj, ensure_ascii=False))
except Exception as e:
    print('ERROR', e)
finally:
    con.close()
