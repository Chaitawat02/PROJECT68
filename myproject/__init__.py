"""myproject package initialization."""

# Use PyMySQL as MySQLdb shim when available (works on Windows)
try:
	import pymysql
	pymysql.install_as_MySQLdb()
except Exception:
	pass

