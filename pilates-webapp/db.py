import os
from sqlalchemy import create_engine, text

# Prende l'URL del DB dalle variabili d'ambiente (Render) o usa un valore di test
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://postgres.ftybzhmrxsviwvlpkdgp:MarvinRoberta2026!@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

def init_db():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS prenotazioni (
                id SERIAL PRIMARY KEY, nome TEXT NOT NULL, data TEXT NOT NULL, ora TEXT NOT NULL,
                trattamento TEXT NOT NULL, data_creazione TEXT NOT NULL, device_id TEXT,
                stato_presenza TEXT DEFAULT 'Assente', codice_fiscale TEXT, codice_fiscale_2 TEXT
            );
            CREATE TABLE IF NOT EXISTS banned_devices (device_id TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS utenti (
                id SERIAL PRIMARY KEY, nome TEXT NOT NULL, cognome TEXT NOT NULL,
                codice_fiscale TEXT NOT NULL UNIQUE, password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL, data_registrazione TEXT NOT NULL
            );
        """))