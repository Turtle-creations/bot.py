import re
import sqlite3
from contextlib import contextmanager

from config import DATABASE_BACKEND, DATABASE_DSN, DATA_DIR


class PostgresCursorAdapter:
    _AUTO_INCREMENT_COLUMNS = {
        "users": "user_id",
        "exams": "exam_id",
        "exam_sets": "set_id",
        "questions": "question_id",
        "notifications": "notification_id",
        "quiz_attempts": "attempt_id",
        "support_messages": "support_id",
    }

    def __init__(self, cursor, sql: str):
        self._cursor = cursor
        self._sql = sql
        self._buffered_row = None
        self.lastrowid = None

    def execute(self, sql: str, params=None):
        self._sql = sql
        query = sql.replace("datetime('now')", "CURRENT_TIMESTAMP").replace("?", "%s")
        normalized = sql.strip().lower()
        returning_column = None
        match = re.match(r"insert\s+into\s+([a-z_]+)", normalized)
        if match and "returning" not in normalized:
            table_name = match.group(1)
            returning_column = self._AUTO_INCREMENT_COLUMNS.get(table_name)
            if returning_column:
                query = f"{query} RETURNING {returning_column}"

        self._cursor.execute(query, params or ())
        if returning_column:
            row = self._cursor.fetchone()
            self._buffered_row = row
            if row:
                self.lastrowid = row[returning_column]
        return self

    def fetchone(self):
        if self._buffered_row is not None:
            row = self._buffered_row
            self._buffered_row = None
            return row
        return self._cursor.fetchone()

    def fetchall(self):
        rows = []
        if self._buffered_row is not None:
            rows.append(self._buffered_row)
            self._buffered_row = None
        rows.extend(self._cursor.fetchall())
        return rows

    @property
    def rowcount(self):
        return self._cursor.rowcount


class PostgresConnectionAdapter:
    def __init__(self, connection):
        self._connection = connection

    def execute(self, sql: str, params=None):
        cursor = self._connection.cursor()
        return PostgresCursorAdapter(cursor, sql).execute(sql, params)

    def close(self):
        self._connection.close()

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()


class Database:
    _COMMON_COLUMNS = {
        "users": (
            ("login_identifier", "TEXT", "TEXT"),
            ("email", "TEXT", "TEXT"),
            ("phone_number", "TEXT", "TEXT"),
            ("password_hash", "TEXT", "TEXT"),
            ("user_role", "TEXT NOT NULL DEFAULT 'user'", "TEXT NOT NULL DEFAULT 'user'"),
            ("is_premium", "INTEGER NOT NULL DEFAULT 0", "INTEGER NOT NULL DEFAULT 0"),
            ("premium_expires_at", "TEXT", "TEXT"),
            ("daily_question_date", "TEXT", "TEXT"),
            ("daily_question_count", "INTEGER NOT NULL DEFAULT 0", "INTEGER NOT NULL DEFAULT 0"),
            ("pdf_generation_count", "INTEGER NOT NULL DEFAULT 0", "INTEGER NOT NULL DEFAULT 0"),
            ("quiz_played", "INTEGER NOT NULL DEFAULT 0", "INTEGER NOT NULL DEFAULT 0"),
            ("correct_answers", "INTEGER NOT NULL DEFAULT 0", "INTEGER NOT NULL DEFAULT 0"),
            ("wrong_answers", "INTEGER NOT NULL DEFAULT 0", "INTEGER NOT NULL DEFAULT 0"),
            ("score", "REAL NOT NULL DEFAULT 0", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
            ("updated_at", "TEXT NOT NULL DEFAULT ''", "TEXT NOT NULL DEFAULT ''"),
        ),
        "exam_sets": (
            ("is_premium_locked", "INTEGER NOT NULL DEFAULT 0", "INTEGER NOT NULL DEFAULT 0"),
        ),
        "support_messages": (
            ("admin_chat_id", "INTEGER", "BIGINT"),
            ("admin_message_id", "INTEGER", "BIGINT"),
        ),
        "processed_webhooks": (
            ("payment_id", "TEXT", "TEXT"),
            ("order_id", "TEXT", "TEXT"),
            ("last_seen_at", "TEXT", "TEXT"),
            ("duplicate_count", "INTEGER NOT NULL DEFAULT 0", "INTEGER NOT NULL DEFAULT 0"),
        ),
        "password_reset_requests": (
            ("requested_ip", "TEXT", "TEXT"),
            ("otp_verified_at", "TEXT", "TEXT"),
            ("used_at", "TEXT", "TEXT"),
            ("reset_token_hash", "TEXT", "TEXT"),
            ("reset_expires_at", "TEXT", "TEXT"),
            ("password_reset_at", "TEXT", "TEXT"),
        ),
    }

    def __init__(self, backend: str, dsn: str):
        self.backend = backend
        self.dsn = dsn

    @property
    def is_sqlite(self) -> bool:
        return self.backend == "sqlite"

    @property
    def is_postgres(self) -> bool:
        return self.backend == "postgres"

    def initialize(self):
        if self.is_sqlite:
            DATA_DIR.mkdir(parents=True, exist_ok=True)

        with self.connection() as conn:
            if self.is_sqlite:
                conn.executescript(self._sqlite_schema())
            else:
                self._initialize_postgres(conn)
            self._ensure_common_columns(conn)

            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_login_identifier ON users(login_identifier) WHERE login_identifier IS NOT NULL"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_password_reset_email_created ON password_reset_requests(email, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_password_reset_user_created ON password_reset_requests(user_id, created_at DESC)"
            )

    @contextmanager
    def connection(self):
        if self.is_sqlite:
            conn = sqlite3.connect(self.dsn, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA temp_store=MEMORY")
        else:
            from psycopg import connect
            from psycopg.rows import dict_row

            raw_connection = connect(self.dsn, row_factory=dict_row)
            raw_connection.execute("SET client_encoding TO 'UTF8'")
            conn = PostgresConnectionAdapter(raw_connection)

        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def table_exists(self, table_name: str) -> bool:
        with self.connection() as conn:
            if self.is_sqlite:
                row = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (table_name,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = %s
                    """.replace("%s", "?"),
                    (table_name,),
                ).fetchone()
        return bool(row)

    def tables_exist(self, table_names: set[str]) -> bool:
        with self.connection() as conn:
            placeholders = ", ".join("?" for _ in table_names)
            if self.is_sqlite:
                query = (
                    "SELECT name FROM sqlite_master "
                    f"WHERE type = 'table' AND name IN ({placeholders})"
                )
            else:
                query = (
                    "SELECT table_name AS name FROM information_schema.tables "
                    f"WHERE table_schema = 'public' AND table_name IN ({placeholders})"
                )
            rows = conn.execute(query, tuple(table_names)).fetchall()
        return {row["name"] for row in rows} == set(table_names)

    def users_table_has_integer_primary_key(self, conn) -> bool:
        if self.is_sqlite:
            schema_rows = conn.execute("PRAGMA table_info(users)").fetchall()
            for row in schema_rows:
                if row["name"] == "user_id" and int(row["pk"] or 0) == 1:
                    return str(row["type"] or "").strip().upper() == "INTEGER"
            return False

        details = conn.execute(
            """
            SELECT data_type, is_identity
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'user_id'
            """,
        ).fetchone()
        if not details:
            return False
        return str(details["data_type"]).lower() in {"integer", "bigint"} and str(details["is_identity"]).upper() == "YES"

    def _ensure_column(self, conn, table_name: str, column_name: str, definition: str):
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
        if column_name not in columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    def _ensure_postgres_column(self, conn, table_name: str, column_name: str, definition: str):
        row = conn.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = ? AND column_name = ?
            """,
            (table_name, column_name),
        ).fetchone()
        if not row:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    def _ensure_common_columns(self, conn):
        definition_index = 1 if self.is_postgres else 0
        ensure_column = self._ensure_postgres_column if self.is_postgres else self._ensure_column
        for table_name, columns in self._COMMON_COLUMNS.items():
            for column_name, sqlite_definition, postgres_definition in columns:
                definition = (sqlite_definition, postgres_definition)[definition_index]
                ensure_column(conn, table_name, column_name, definition)

    def _initialize_postgres(self, conn):
        statements = [
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                username TEXT,
                login_identifier TEXT,
                email TEXT,
                phone_number TEXT,
                password_hash TEXT,
                user_role TEXT NOT NULL DEFAULT 'user',
                full_name TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                is_premium INTEGER NOT NULL DEFAULT 0,
                premium_expires_at TEXT,
                daily_question_date TEXT,
                daily_question_count INTEGER NOT NULL DEFAULT 0,
                pdf_generation_count INTEGER NOT NULL DEFAULT 0,
                quiz_played INTEGER NOT NULL DEFAULT 0,
                correct_answers INTEGER NOT NULL DEFAULT 0,
                wrong_answers INTEGER NOT NULL DEFAULT 0,
                score DOUBLE PRECISION NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS exams (
                exam_id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                title TEXT NOT NULL UNIQUE,
                description TEXT,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS exam_sets (
                set_id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                exam_id INTEGER NOT NULL REFERENCES exams(exam_id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT,
                is_premium_locked INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE (exam_id, title)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS questions (
                question_id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                exam_id INTEGER NOT NULL REFERENCES exams(exam_id) ON DELETE CASCADE,
                set_id INTEGER NOT NULL REFERENCES exam_sets(set_id) ON DELETE CASCADE,
                question_text TEXT NOT NULL,
                option_a TEXT NOT NULL,
                option_b TEXT NOT NULL,
                option_c TEXT NOT NULL,
                option_d TEXT NOT NULL,
                correct_option TEXT NOT NULL,
                explanation TEXT,
                image_path TEXT,
                time_limit INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS notifications (
                notification_id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                message TEXT NOT NULL,
                kind TEXT NOT NULL,
                day_of_week INTEGER,
                send_time TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                last_sent_at TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS payment_orders (
                order_id TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                plan_type TEXT NOT NULL,
                amount INTEGER NOT NULL,
                currency TEXT NOT NULL,
                status TEXT NOT NULL,
                payment_url TEXT,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS payments (
                payment_id TEXT PRIMARY KEY,
                order_id TEXT,
                user_id BIGINT NOT NULL,
                plan_type TEXT NOT NULL,
                amount INTEGER NOT NULL,
                currency TEXT NOT NULL,
                status TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                expiry_date TEXT NOT NULL,
                raw_payload TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS processed_webhooks (
                event_id TEXT PRIMARY KEY,
                payment_id TEXT,
                order_id TEXT,
                received_at TEXT NOT NULL,
                last_seen_at TEXT,
                duplicate_count INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS quiz_attempts (
                attempt_id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                user_id BIGINT NOT NULL,
                set_id INTEGER NOT NULL,
                requested_count INTEGER NOT NULL,
                correct_count INTEGER NOT NULL DEFAULT 0,
                wrong_count INTEGER NOT NULL DEFAULT 0,
                skipped_count INTEGER NOT NULL DEFAULT 0,
                ended_reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS support_messages (
                support_id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                user_id BIGINT NOT NULL,
                username TEXT,
                full_name TEXT,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                admin_reply TEXT,
                replied_at TEXT,
                admin_chat_id BIGINT,
                admin_message_id BIGINT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS password_reset_requests (
                reset_id TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                email TEXT NOT NULL,
                otp_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                requested_ip TEXT,
                otp_verified_at TEXT,
                used_at TEXT,
                reset_token_hash TEXT,
                reset_expires_at TEXT,
                password_reset_at TEXT
            )
            """,
        ]
        for statement in statements:
            conn.execute(statement)

    def _sqlite_schema(self) -> str:
        return """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            login_identifier TEXT,
            email TEXT,
            phone_number TEXT,
            password_hash TEXT,
            user_role TEXT NOT NULL DEFAULT 'user',
            full_name TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            is_premium INTEGER NOT NULL DEFAULT 0,
            premium_expires_at TEXT,
            daily_question_date TEXT,
            daily_question_count INTEGER NOT NULL DEFAULT 0,
            pdf_generation_count INTEGER NOT NULL DEFAULT 0,
            quiz_played INTEGER NOT NULL DEFAULT 0,
            correct_answers INTEGER NOT NULL DEFAULT 0,
            wrong_answers INTEGER NOT NULL DEFAULT 0,
            score REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS exams (
            exam_id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL UNIQUE,
            description TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS exam_sets (
            set_id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            is_premium_locked INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE (exam_id, title),
            FOREIGN KEY (exam_id) REFERENCES exams(exam_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS questions (
            question_id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id INTEGER NOT NULL,
            set_id INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            option_a TEXT NOT NULL,
            option_b TEXT NOT NULL,
            option_c TEXT NOT NULL,
            option_d TEXT NOT NULL,
            correct_option TEXT NOT NULL,
            explanation TEXT,
            image_path TEXT,
            time_limit INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (exam_id) REFERENCES exams(exam_id) ON DELETE CASCADE,
            FOREIGN KEY (set_id) REFERENCES exam_sets(set_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS notifications (
            notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            kind TEXT NOT NULL,
            day_of_week INTEGER,
            send_time TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            last_sent_at TEXT
        );

        CREATE TABLE IF NOT EXISTS payment_orders (
            order_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            plan_type TEXT NOT NULL,
            amount INTEGER NOT NULL,
            currency TEXT NOT NULL,
            status TEXT NOT NULL,
            payment_url TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS payments (
            payment_id TEXT PRIMARY KEY,
            order_id TEXT,
            user_id INTEGER NOT NULL,
            plan_type TEXT NOT NULL,
            amount INTEGER NOT NULL,
            currency TEXT NOT NULL,
            status TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            expiry_date TEXT NOT NULL,
            raw_payload TEXT
        );

        CREATE TABLE IF NOT EXISTS processed_webhooks (
            event_id TEXT PRIMARY KEY,
            payment_id TEXT,
            order_id TEXT,
            received_at TEXT NOT NULL,
            last_seen_at TEXT,
            duplicate_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS quiz_attempts (
            attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            set_id INTEGER NOT NULL,
            requested_count INTEGER NOT NULL,
            correct_count INTEGER NOT NULL DEFAULT 0,
            wrong_count INTEGER NOT NULL DEFAULT 0,
            skipped_count INTEGER NOT NULL DEFAULT 0,
            ended_reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS support_messages (
            support_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            full_name TEXT,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            admin_reply TEXT,
            replied_at TEXT,
            admin_chat_id INTEGER,
            admin_message_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS password_reset_requests (
            reset_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            email TEXT NOT NULL,
            otp_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            requested_ip TEXT,
            otp_verified_at TEXT,
            used_at TEXT,
            reset_token_hash TEXT,
            reset_expires_at TEXT,
            password_reset_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );
        """


database = Database(DATABASE_BACKEND, DATABASE_DSN)
