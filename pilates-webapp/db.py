import os
from sqlalchemy import create_engine, text

# Prende l'URL del DB dalle variabili d'ambiente (Obbligatorio per sicurezza)
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("Attenzione: La variabile d'ambiente DATABASE_URL non è configurata.")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def init_db():
    with engine.begin() as conn:

        # ============================================================
        # PRENOTAZIONI
        # ============================================================
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS prenotazioni (
                id SERIAL PRIMARY KEY,

                nome TEXT NOT NULL,
                data TEXT NOT NULL,
                ora TEXT NOT NULL,
                trattamento TEXT NOT NULL,
                data_creazione TEXT NOT NULL,
                device_id TEXT,

                -- Partecipante 1
                codice_fiscale TEXT,
                stato_presenza TEXT DEFAULT 'Assente',
                stato TEXT DEFAULT 'confermata',

                -- Partecipante 2
                nome_2 TEXT,
                codice_fiscale_2 TEXT,
                stato_2 TEXT DEFAULT 'confermata',

                -- Gestione consumo seduta
                seduta_scalata BOOLEAN DEFAULT false,
                seduta_scalata_2 BOOLEAN DEFAULT false,

                -- Indica se la seduta consumata è ordinaria
                -- oppure un recupero
                tipo_seduta_scalata TEXT,
                tipo_seduta_scalata_2 TEXT
            );
        """))

        # ============================================================
        # DISPOSITIVI BANNATI
        # ============================================================
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS banned_devices (
                device_id TEXT PRIMARY KEY
            );
        """))

        # ============================================================
        # UTENTI
        # ============================================================
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS utenti (
                id SERIAL PRIMARY KEY,

                nome TEXT NOT NULL,
                cognome TEXT NOT NULL,
                codice_fiscale TEXT NOT NULL UNIQUE,

                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,

                data_registrazione TEXT NOT NULL,

                bannato BOOLEAN DEFAULT false,

                email TEXT,

                reset_code VARCHAR(6),
                reset_expires_at TIMESTAMP,

                -- ==================================================
                -- DATI PERSONALI
                -- ==================================================
                data_nascita TEXT,
                luogo_nascita TEXT,
                luogo_residenza TEXT,
                telefono TEXT,
                note TEXT,

                -- ==================================================
                -- ABBONAMENTO
                -- ==================================================
                tipo_abbonamento TEXT,
                data_inizio_abbonamento TEXT,
                data_fine_abbonamento TEXT,

                -- Per il pacchetto "10 sedute"
                sedute_totali INTEGER DEFAULT 0,
                sedute_residue INTEGER DEFAULT 0,

                -- Recuperi utilizzati per Mensile/Trimestrale
                recuperi_utilizzati INTEGER DEFAULT 0,

                -- ==================================================
                -- PAGAMENTO
                -- ==================================================
                pagamento_effettuato BOOLEAN DEFAULT false,
                metodo_pagamento TEXT
            );
        """))

        # ============================================================
        # MIGRAZIONI
        # ============================================================
        # Queste servono anche se il database esiste già.
        # In questo modo non perdiamo i dati attuali.

        colonne_prenotazioni = [
            "ALTER TABLE prenotazioni ADD COLUMN IF NOT EXISTS nome_2 TEXT",
            "ALTER TABLE prenotazioni ADD COLUMN IF NOT EXISTS codice_fiscale_2 TEXT",
            "ALTER TABLE prenotazioni ADD COLUMN IF NOT EXISTS stato_2 TEXT DEFAULT 'confermata'",
            "ALTER TABLE prenotazioni ADD COLUMN IF NOT EXISTS seduta_scalata BOOLEAN DEFAULT false",
            "ALTER TABLE prenotazioni ADD COLUMN IF NOT EXISTS seduta_scalata_2 BOOLEAN DEFAULT false",
            "ALTER TABLE prenotazioni ADD COLUMN IF NOT EXISTS tipo_seduta_scalata TEXT",
            "ALTER TABLE prenotazioni ADD COLUMN IF NOT EXISTS tipo_seduta_scalata_2 TEXT",
        ]

        colonne_utenti = [
            "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS bannato BOOLEAN DEFAULT false",
            "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS email TEXT",
            "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS reset_code VARCHAR(6)",
            "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS reset_expires_at TIMESTAMP",

            "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS data_nascita TEXT",
            "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS luogo_nascita TEXT",
            "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS luogo_residenza TEXT",
            "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS telefono TEXT",
            "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS note TEXT",

            "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS tipo_abbonamento TEXT",
            "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS data_inizio_abbonamento TEXT",
            "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS data_fine_abbonamento TEXT",

            "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS sedute_totali INTEGER DEFAULT 0",
            "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS sedute_residue INTEGER DEFAULT 0",
            "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS recuperi_utilizzati INTEGER DEFAULT 0",

            "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS pagamento_effettuato BOOLEAN DEFAULT false",
            "ALTER TABLE utenti ADD COLUMN IF NOT EXISTS metodo_pagamento TEXT",
        ]

        for query in colonne_prenotazioni + colonne_utenti:
            try:
                conn.execute(text(query))
            except Exception as e:
                print(f"Errore migrazione database: {e}")

        # ============================================================
        # VALORI DEFAULT PER EVENTUALI RECORD ESISTENTI
        # ============================================================
        conn.execute(text("""
            UPDATE utenti
            SET sedute_totali = COALESCE(sedute_totali, 0),
                sedute_residue = COALESCE(sedute_residue, 0),
                recuperi_utilizzati = COALESCE(recuperi_utilizzati, 0),
                pagamento_effettuato = COALESCE(pagamento_effettuato, false)
        """))

        conn.execute(text("""
            UPDATE prenotazioni
            SET seduta_scalata = COALESCE(seduta_scalata, false),
                seduta_scalata_2 = COALESCE(seduta_scalata_2, false)
        """))
