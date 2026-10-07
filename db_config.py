import mysql.connector

# ========================================================
# MySQL Database Connection Configuration
# Change host, user, password as per your local MySQL setup
# ========================================================
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'Mahimas#6244',          # Enter your MySQL root password here (default in XAMPP is empty)
    'database': 'college_event_db',
    'port': 3306
}

def get_db_connection():
    """
    Establishes and returns a connection to the MySQL database.
    """
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except mysql.connector.Error as err:
        print(f"[Database Error]: Could not connect to MySQL: {err}")
        return None
