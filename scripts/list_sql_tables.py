import sqlite3
con=sqlite3.connect('db.sqlite3')
cur=con.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
for row in cur.fetchall():
    print(row[0])
con.close()
