# actions.py
from typing import Any, Text, Dict, List, Optional
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
import logging
import os
import mysql.connector
from mysql.connector import Error
from datetime import datetime

# Setup logging
logger = logging.getLogger(__name__)

# --- KONFIGURASI DATABASE ---
# PENTING: Untuk production, gunakan environment variables!
# Kredensial diambil dari environment variables untuk keamanan.
DB_CONFIG = {
    'host': os.getenv("DB_HOST", "195.88.211.130"),
    'port': int(os.getenv("DB_PORT", 3306)),
    'user': os.getenv("DB_USER", "adatkumy_rangga"),
    'password': os.getenv("DB_PASSWORD", "tupperware123"),
    'database': os.getenv("DB_NAME", "adatkumy_adatku"),
    'connect_timeout': 10,
    'raise_on_warnings': False,
    'charset': 'utf8mb4',
    'use_unicode': True
}

def create_db_connection():
    """
    Menciptakan koneksi ke database MySQL.
    
    Returns:
        connection: MySQL connection object atau None jika gagal
    """
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        if connection.is_connected():
            logger.info("Berhasil terhubung ke database MySQL")
            return connection
    except Error as e:
        logger.error(f"Error saat menghubungkan ke MySQL: {e}")
        return None

def close_db_connection(connection, cursor=None):
    """
    Menutup koneksi database dengan aman.
    
    Args:
        connection: MySQL connection object
        cursor: MySQL cursor object (optional)
    """
    try:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
            logger.info("Koneksi database ditutup")
    except Error as e:
        logger.error(f"Error saat menutup koneksi: {e}")

class ActionCheckStatus(Action):
    """Action untuk mengecek status reservasi/pesanan dari database."""
    
    def name(self) -> Text:
        return "action_check_status"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        transaction_id = tracker.get_slot("transaction_id")

        # Validasi transaction_id
        if not transaction_id:
            logger.warning("Slot 'transaction_id' kosong")
            dispatcher.utter_message(response="utter_ask_transaction_id")
            return [SlotSet("transaction_id", None)]
        
        # Bersihkan whitespace dan konversi ke string
        transaction_id = str(transaction_id).strip()
        
        # Validasi format (harus angka dan minimal 10 digit)
        if not transaction_id.isdigit() or len(transaction_id) < 10:
            logger.warning(f"transaction_id tidak valid: '{transaction_id}'")
            dispatcher.utter_message(
                text="Nomor order tidak valid. Pastikan Anda memasukkan nomor order yang benar (minimal 10 digit angka)."
            )
            return [SlotSet("transaction_id", None)]

        logger.info(f"Mencari reservasi dengan Order ID: {transaction_id}")

        # Buat koneksi database
        connection = create_db_connection()
        if not connection:
            dispatcher.utter_message(
                text="Maaf, saya tidak dapat terhubung ke database saat ini. Silakan coba lagi nanti."
            )
            return [SlotSet("transaction_id", None)]

        cursor = None
        try:
            cursor = connection.cursor(dictionary=True)
            
            # Query database untuk mendapatkan detail reservasi
            query = """
                SELECT
                    r.order_id,
                    r.status,
                    r.payment_status,
                    r.start_date,
                    r.end_date,
                    pa.nama as nama_pakaian
                FROM reservations r
                JOIN pakaian_adats pa ON r.pakaian_adat_id = pa.id
                WHERE r.order_id = %s
                LIMIT 1
            """
            cursor.execute(query, (transaction_id,))
            result = cursor.fetchone()
            
            # Cast result ke Dict untuk type checker
            reservation: Optional[Dict[str, Any]] = result  # type: ignore

            if reservation and isinstance(reservation, dict):
                # Ambil data dari hasil query
                order_id = reservation.get("order_id", transaction_id)
                status = reservation.get("status", "Tidak diketahui")
                payment_status = reservation.get("payment_status", "Tidak diketahui")
                tgl_sewa = reservation.get("start_date")
                tgl_kembali = reservation.get("end_date")
                nama_pakaian = reservation.get("nama_pakaian", "Tidak diketahui")

                # Format pesan response
                pesan = f"📋 Status Reservasi #{order_id}:\n"
                pesan += f"• Status Sewa: {status}\n"
                pesan += f"• Pakaian Adat: {nama_pakaian}\n"
                pesan += f"• Status Pembayaran: {payment_status}\n"
                
                # Format tanggal dengan aman
                if tgl_sewa:
                    try:
                        if isinstance(tgl_sewa, str):
                            tgl_sewa_obj = datetime.strptime(tgl_sewa, '%Y-%m-%d')
                            pesan += f"• Tanggal Sewa: {tgl_sewa_obj.strftime('%d %B %Y')}\n"
                        else:
                            pesan += f"• Tanggal Sewa: {tgl_sewa.strftime('%d %B %Y')}\n"
                    except Exception as e:
                        logger.error(f"Error format tgl_sewa: {e}")
                        pesan += f"• Tanggal Sewa: {tgl_sewa}\n"
                
                if tgl_kembali:
                    try:
                        if isinstance(tgl_kembali, str):
                            tgl_kembali_obj = datetime.strptime(tgl_kembali, '%Y-%m-%d')
                            pesan += f"• Tanggal Kembali: {tgl_kembali_obj.strftime('%d %B %Y')}"
                        else:
                            pesan += f"• Tanggal Kembali: {tgl_kembali.strftime('%d %B %Y')}"
                    except Exception as e:
                        logger.error(f"Error format tgl_kembali: {e}")
                        pesan += f"• Tanggal Kembali: {tgl_kembali}"
                
                logger.info(f"Reservasi ditemukan: Order ID {order_id}, Status: {status}")
            else:
                pesan = f"❌ Maaf, reservasi dengan nomor order {transaction_id} tidak ditemukan.\n"
                pesan += "Pastikan nomor order yang Anda masukkan benar."
                logger.warning(f"Reservasi tidak ditemukan: Order ID {transaction_id}")

            dispatcher.utter_message(text=pesan)

        except Error as e:
            logger.error(f"ActionCheckStatus: Error query database: {e}")
            dispatcher.utter_message(
                text="Maaf, terjadi kesalahan saat memeriksa status reservasi. Silakan coba lagi."
            )
        except Exception as e:
            logger.error(f"ActionCheckStatus: Unexpected error: {e}")
            dispatcher.utter_message(
                text="Maaf, terjadi kesalahan sistem. Silakan coba lagi."
            )
        finally:
            close_db_connection(connection, cursor)

        return [SlotSet("transaction_id", None)]