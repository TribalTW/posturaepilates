from datetime import datetime, timedelta
import hashlib
import re
import secrets
from zoneinfo import ZoneInfo

_VALORI_DISPARI = {"0": 1, "1": 0, "2": 5, "3": 7, "4": 9, "5": 13, "6": 15, "7": 17, "8": 19, "9": 21, "A": 1, "B": 0, "C": 5, "D": 7, "E": 9, "F": 13, "G": 15, "H": 17, "I": 19, "J": 21, "K": 2, "L": 4, "M": 18, "N": 20, "O": 11, "P": 3, "Q": 6, "R": 8, "S": 12, "T": 14, "U": 16, "V": 10, "W": 22, "X": 25, "Y": 24, "Z": 23}
_VALORI_PARI = {"0": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9, "A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5, "G": 6, "H": 7, "I": 8, "J": 9, "K": 10, "L": 11, "M": 12, "N": 13, "O": 14, "P": 15, "Q": 16, "R": 17, "S": 18, "T": 19, "U": 20, "V": 21, "W": 22, "X": 23, "Y": 24, "Z": 25}
_LETTERE_RESTO = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

def estrai_consonanti_vocali(testo):
    testo = testo.upper()
    return "".join([c for c in testo if c.isalpha() and c not in "AEIOU"]), "".join([c for c in testo if c.isalpha() and c in "AEIOU"])

def calcola_iniziali_cf(cognome, nome):
    c_cons, c_voc = estrai_consonanti_vocali(cognome)
    n_cons, n_voc = estrai_consonanti_vocali(nome)
    cog_cf = (c_cons + c_voc + "XXX")[:3]
    nome_cf = (n_cons[0] + n_cons[2] + n_cons[3]) if len(n_cons) >= 4 else (n_cons + n_voc + "XXX")[:3]
    return cog_cf, nome_cf

def calcola_carattere_controllo_cf(cf_15):
    totale = sum(_VALORI_DISPARI[c] if (i + 1) % 2 != 0 else _VALORI_PARI[c] for i, c in enumerate(cf_15))
    return _LETTERE_RESTO[totale % 26]

def valida_codice_fiscale(nome, cognome, cf):
    cf = cf.strip().upper()
    if not re.match(r"^[A-Z]{6}[0-9]{2}[ABCDEHLMPRST][0-9]{2}[A-Z][0-9]{3}[A-Z]$", cf):
        return False, "Formato Codice Fiscale non valido."
    cog_e, nome_e = calcola_iniziali_cf(cognome, nome)
    if cf[:3] != cog_e or cf[3:6] != nome_e:
        return False, "Codice Fiscale non corrispondente a Nome/Cognome."
    if cf[15] != calcola_carattere_controllo_cf(cf[:15]):
        return False, "Carattere di controllo del Codice Fiscale non valido."
    return True, ""

def hash_password(password, salt=None):
    if salt is None: salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
    return salt, pwd_hash

def verifica_password(password, salt, pwd_hash_atteso):
    _, pwd_hash_calcolato = hash_password(password, salt)
    return secrets.compare_digest(pwd_hash_calcolato, pwd_hash_atteso)

def get_orari_per_data(d):
    weekday = d.weekday()
    if weekday == 5: return ["08:00", "09:00", "10:00", "11:00", "12:00", "13:00"]
    elif weekday == 6: return []
    return ["08:00", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00", "19:00"]

def get_current_time_local():
    try: return datetime.now(ZoneInfo("Europe/Rome"))
    except Exception: return datetime.now()

def get_orari_disponibili_filtrati(data_str: str, orari_teorici: list) -> list:
    """
    Filtra gli orari teorici rimuovendo quelli già passati se la data selezionata è oggi.
    """
    now_local = get_current_time_local()
    oggi_str = now_local.strftime("%Y-%m-%d")
    ora_corrente = now_local.time()

    orari_validi = []
    for ora in orari_teorici:
        if data_str == oggi_str:
            try:
                ora_obj = datetime.strptime(ora, "%H:%M").time()
                if ora_obj <= ora_corrente:
                    continue  # Salta l'orario perché è già passato
            except ValueError:
                pass
        orari_validi.append(ora)
        
    return orari_validi

def genera_file_ics(trattamento, data_str, ora_str):
    dt_inizio = datetime.strptime(f"{data_str} {ora_str}", "%Y-%m-%d %H:%M")
    dt_fine = dt_inizio + timedelta(minutes=50)
    fmt = "%Y%m%dT%H%M00"
    return f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Postura e Pilates//Dott.ssa Roberta Sinagra//IT
CALSCALE:GREGORIAN
METHOD:PUBLISH
BEGIN:VEVENT
SUMMARY:Pilates: {trattamento} - Dott.ssa Roberta Sinagra
DESCRIPTION:Appuntamento di Postura & Pilates.\\nRicorda calzini antiscivolo e asciugamano.
LOCATION:Studio Dott.ssa Roberta Sinagra
DTSTART:{dt_inizio.strftime(fmt)}
DTEND:{dt_fine.strftime(fmt)}
BEGIN:VALARM
TRIGGER:-PT60M
ACTION:DISPLAY
DESCRIPTION:Promemoria: Tra 1 ora hai la lezione!
END:VALARM
END:VEVENT
END:VCALENDAR"""
