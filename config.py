from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

DEFINITIONS_DIR = REPO_ROOT / "definitions"
OUTPUT_DIR = REPO_ROOT / "out"

# Pick one backend; install the matching driver extra.
# Examples:
#   oracle      "oracle+oracledb://analyst@oradb.uni.edu:1521/?service_name=PROD"
#   postgres    "postgresql+psycopg://analyst@dbhost:5432/dbname"
#   mysql       "mysql+pymysql://analyst@dbhost:3306/dbname"
#   sqlserver   "mssql+pyodbc://analyst@dbhost:1433/dbname?driver=ODBC+Driver+18+for+SQL+Server"
#   sqlite      "sqlite:///path/to/local.sqlite"   (no user, no password)
DATABASE_URL = "oracle+oracledb://analyst_readonly@oradb.uni.edu:1521/?service_name=PROD"
KEYRING_SERVICE = "carta_db"

ACTIVE: list[str] = [
    # "enrollment_by_term",
]
