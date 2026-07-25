import sqlite3
conn = sqlite3.connect('storage/knowledge_base.db')
conn.execute("DELETE FROM chunks WHERE source LIKE 'test_%' OR source = 'test.txt'")
conn.commit()
conn.close()
print("OK - cleaned test data")