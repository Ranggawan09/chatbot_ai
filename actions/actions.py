# actions.py
from typing import Any, Text, Dict, List, Optional
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
import logging
import os
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv
from datetime import datetime

# Setup logging
logger = logging.getLogger(__name__)

# Muat variabel lingkungan dari file .env
load_dotenv()

# --- KONFIGURASI DATABASE ---
DB_CONFIG = {
    # Ambil konfigurasi dari environment variables
    'host': os.getenv("DB_HOST"),
    'port': int(os.getenv("DB_PORT") or 3306),
    'user': os.getenv("DB_USER"),
    'password': os.getenv("DB_PASSWORD"),
    'database': os.getenv("DB_NAME"),
    'connect_timeout': 10,
    'raise_on_warnings': False,
    'charset': 'utf8mb4',
    'use_unicode': True
}

def create_db_connection():
    """Menciptakan koneksi ke database MySQL."""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        if connection.is_connected():
            logger.info("Berhasil terhubung ke database MySQL")
            return connection
    except Error as e:
        logger.error(f"Error saat menghubungkan ke MySQL: {e}")
        return None

def close_db_connection(connection, cursor=None):
    """Menutup koneksi database dengan aman."""
    try:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
            logger.info("Koneksi database ditutup")
    except Error as e:
        logger.error(f"Error saat menutup koneksi: {e}")


class ActionCheckAvailability(Action):
    """Action untuk mengecek ketersediaan stok pakaian adat."""
    
    def name(self) -> Text:
        return "action_check_availability"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        nama_baju_slot = tracker.get_slot("nama_baju")

        # Validasi input
        if not nama_baju_slot or str(nama_baju_slot).strip() == "":
            logger.warning("Slot 'nama_baju' kosong")
            dispatcher.utter_message(response="utter_ask_nama_baju")
            return [SlotSet("nama_baju", None)]

        nama_baju_slot = str(nama_baju_slot).strip()
        logger.info(f"Mencari pakaian: {nama_baju_slot}")

        connection = create_db_connection()
        if not connection:
            dispatcher.utter_message(
                text="Maaf, tidak dapat terhubung ke database. Silakan coba lagi."
            )
            return [SlotSet("nama_baju", None)]

        cursor = None
        try:
            cursor = connection.cursor(dictionary=True)
            
            # Query JOIN pakaian_adats dengan pakaian_variants
            query = """
                SELECT 
                    pa.id,
                    pa.nama,
                    pa.jenis,
                    pa.asal,
                    pa.warna,
                    pa.price_per_day,
                    pa.status as status_pakaian,
                    pv.size,
                    pv.quantity
                FROM pakaian_adats pa
                LEFT JOIN pakaian_variants pv ON pa.id = pv.pakaian_adat_id
                WHERE pa.nama LIKE %s AND pa.status = 'Tersedia'
                ORDER BY pv.size
            """
            cursor.execute(query, (f"%{nama_baju_slot}%",))
            results = cursor.fetchall()
            
            variants: List[Dict[str, Any]] = results  # type: ignore

            if variants and len(variants) > 0:
                # Ambil info dasar
                first_item = variants[0] if isinstance(variants[0], dict) else {}
                nama = first_item.get("nama", "Tidak diketahui")
                jenis = first_item.get("jenis", "-")
                asal = first_item.get("asal", "-")
                warna = first_item.get("warna", "-")
                harga = first_item.get("price_per_day", 0)
                
                # Hitung stok per size
                total_stok = 0
                detail_stok = []
                ada_stok = False
                
                for variant in variants:
                    if isinstance(variant, dict):
                        size = variant.get("size", "Unknown")
                        quantity = variant.get("quantity", 0)
                        
                        if quantity and quantity > 0:
                            ada_stok = True
                            detail_stok.append(f"Size {size}: {quantity} unit")
                            total_stok += quantity
                        else:
                            detail_stok.append(f"Size {size}: Habis")
                
                # Format response
                status = "✅ Tersedia" if ada_stok else "❌ Habis"
                
                pesan = f"📦 Informasi Ketersediaan '{nama}':\n\n"
                pesan += f"🏷️ Jenis: {jenis}\n"
                pesan += f"📍 Asal: {asal}\n"
                pesan += f"🎨 Warna: {warna}\n"
                pesan += f"💰 Harga Sewa: Rp {harga:,.0f}/hari\n"
                pesan += f"📊 Status: {status}\n"
                pesan += f"📦 Total Stok: {total_stok} unit\n\n"
                pesan += "📏 Detail per Size:\n"
                
                for detail in detail_stok:
                    pesan += f"  • {detail}\n"
                
                pesan = pesan.rstrip()
                
                logger.info(f"Pakaian ditemukan: {nama}, Total stok: {total_stok}")
            else:
                pesan = f"❌ Maaf, pakaian '{nama_baju_slot}' tidak ditemukan atau sedang tidak tersedia.\n"
                pesan += "Coba cari dengan nama lain atau ketik 'lihat katalog'."
                logger.warning(f"Pakaian tidak ditemukan: {nama_baju_slot}")

            dispatcher.utter_message(text=pesan)

        except Error as e:
            logger.error(f"ActionCheckAvailability Error: {e}")
            dispatcher.utter_message(
                text="Maaf, terjadi kesalahan saat mengecek stok."
            )
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            dispatcher.utter_message(
                text="Maaf, terjadi kesalahan sistem."
            )
        finally:
            close_db_connection(connection, cursor)
        
        return [SlotSet("nama_baju", None)]


class ActionRecommendByColor(Action):
    """Action untuk rekomendasi pakaian berdasarkan warna."""
    
    def name(self) -> Text:
        return "action_recommend_by_color"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        warna_slot = tracker.get_slot("warna")

        # Validasi input
        if not warna_slot or str(warna_slot).strip() == "":
            logger.warning("Slot 'warna' kosong")
            dispatcher.utter_message(response="utter_ask_warna")
            return [SlotSet("warna", None)]

        warna_slot = str(warna_slot).strip()
        logger.info(f"Mencari pakaian dengan warna: {warna_slot}")

        connection = create_db_connection()
        if not connection:
            dispatcher.utter_message(
                text="Maaf, tidak dapat terhubung ke database."
            )
            return [SlotSet("warna", None)]

        cursor = None
        try:
            cursor = connection.cursor(dictionary=True)
            
            # Query untuk mencari pakaian berdasarkan warna
            query = """
                SELECT 
                    pa.id,
                    pa.nama,
                    pa.jenis,
                    pa.asal,
                    pa.warna,
                    pa.price_per_day,
                    COALESCE(SUM(pv.quantity), 0) as total_stok
                FROM pakaian_adats pa
                LEFT JOIN pakaian_variants pv ON pa.id = pv.pakaian_adat_id
                WHERE pa.warna LIKE %s AND pa.status = 'Tersedia'
                GROUP BY pa.id, pa.nama, pa.jenis, pa.asal, pa.warna, pa.price_per_day
                HAVING total_stok > 0
                ORDER BY total_stok DESC
                LIMIT 5
            """
            cursor.execute(query, (f"%{warna_slot}%",))
            results = cursor.fetchall()
            
            pakaians: List[Dict[str, Any]] = results  # type: ignore

            if pakaians and len(pakaians) > 0:
                pesan = f"🎨 Rekomendasi Pakaian Warna '{warna_slot.title()}':\n\n"
                
                for idx, pakaian in enumerate(pakaians, 1):
                    if isinstance(pakaian, dict):
                        nama = pakaian.get("nama", "-")
                        jenis = pakaian.get("jenis", "-")
                        asal = pakaian.get("asal", "-")
                        warna = pakaian.get("warna", "-")
                        harga = pakaian.get("price_per_day", 0)
                        stok = pakaian.get("total_stok", 0)
                        
                        pesan += f"{idx}. {nama}\n"
                        pesan += f"   🏷️ Jenis: {jenis}\n"
                        pesan += f"   📍 Asal: {asal}\n"
                        pesan += f"   🎨 Warna: {warna}\n"
                        pesan += f"   💰 Harga: Rp {harga:,.0f}/hari\n"
                        pesan += f"   📦 Stok: {stok} unit\n\n"
                
                pesan += "Untuk cek detail stok per size, ketik:\n"
                pesan += "'cek ketersediaan [nama pakaian]'"
                
                logger.info(f"Ditemukan {len(pakaians)} pakaian warna {warna_slot}")
            else:
                pesan = f"❌ Maaf, tidak ada pakaian dengan warna '{warna_slot}' yang tersedia saat ini.\n\n"
                pesan += "Warna yang tersedia: Merah, Putih, Hijau, Kuning, Biru, Hitam, dll.\n"
                pesan += "Ketik 'lihat katalog' untuk melihat semua pakaian."
                logger.warning(f"Tidak ada pakaian dengan warna: {warna_slot}")

            dispatcher.utter_message(text=pesan)

        except Error as e:
            logger.error(f"ActionRecommendByColor Error: {e}")
            dispatcher.utter_message(
                text="Maaf, terjadi kesalahan saat mencari rekomendasi."
            )
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            dispatcher.utter_message(
                text="Maaf, terjadi kesalahan sistem."
            )
        finally:
            close_db_connection(connection, cursor)
        
        return [SlotSet("warna", None)]


class ActionCheckStatus(Action):
    """Action untuk mengecek status reservasi dengan multiple items."""
    
    def name(self) -> Text:
        return "action_check_status"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        transaction_id = tracker.get_slot("transaction_id")

        if not transaction_id:
            logger.warning("Slot 'transaction_id' kosong")
            dispatcher.utter_message(response="utter_ask_transaction_id")
            return [SlotSet("transaction_id", None)]
        
        transaction_id = str(transaction_id).strip()
        
        # Validasi format
        if not transaction_id.isdigit() or len(transaction_id) < 10:
            logger.warning(f"transaction_id tidak valid: '{transaction_id}'")
            dispatcher.utter_message(
                text="Nomor order tidak valid. Masukkan nomor order yang benar (minimal 10 digit)."
            )
            return [SlotSet("transaction_id", None)]

        logger.info(f"Mencari reservasi Order ID: {transaction_id}")

        connection = create_db_connection()
        if not connection:
            dispatcher.utter_message(
                text="Maaf, tidak dapat terhubung ke database."
            )
            return [SlotSet("transaction_id", None)]

        cursor = None
        try:
            cursor = connection.cursor(dictionary=True)
            
            # Query untuk mendapatkan SEMUA item dalam 1 order_id (TANPA LIMIT 1)
            query = """
                SELECT
                    r.id as reservation_id,
                    r.order_id,
                    r.status,
                    r.payment_status,
                    r.start_date,
                    r.end_date,
                    r.days,
                    r.price_per_day,
                    r.total_price,
                    r.quantity,
                    pa.nama as nama_pakaian,
                    pa.jenis,
                    pa.asal,
                    pv.size
                FROM reservations r
                JOIN pakaian_adats pa ON r.pakaian_adat_id = pa.id
                LEFT JOIN pakaian_variants pv ON r.pakaian_variant_id = pv.id
                WHERE r.order_id = %s
                ORDER BY r.id
            """
            cursor.execute(query, (transaction_id,))
            results = cursor.fetchall()
            
            reservations: List[Dict[str, Any]] = results  # type: ignore

            if reservations and len(reservations) > 0:
                # Ambil info umum dari reservasi pertama
                first_reservation = reservations[0] if isinstance(reservations[0], dict) else {}
                order_id = first_reservation.get("order_id", transaction_id)
                status = first_reservation.get("status", "Tidak diketahui")
                payment_status = first_reservation.get("payment_status", "Tidak diketahui")
                start_date = first_reservation.get("start_date")
                end_date = first_reservation.get("end_date")
                days = first_reservation.get("days", 0)
                
                # Hitung total harga dari semua item
                grand_total = sum(
                    res.get("total_price", 0) 
                    for res in reservations 
                    if isinstance(res, dict)
                )
                
                # Header pesan
                pesan = f"📋 Status Reservasi #{order_id}\n\n"
                pesan += f"📊 Status Sewa: {status}\n"
                pesan += f"💳 Status Pembayaran: {payment_status}\n"
                
                # Format tanggal
                if start_date:
                    try:
                        if isinstance(start_date, str):
                            date_obj = datetime.strptime(start_date, '%Y-%m-%d')
                            pesan += f"📅 Tanggal Sewa: {date_obj.strftime('%d %B %Y')}\n"
                        else:
                            pesan += f"📅 Tanggal Sewa: {start_date.strftime('%d %B %Y')}\n"
                    except:
                        pesan += f"📅 Tanggal Sewa: {start_date}\n"
                
                if end_date:
                    try:
                        if isinstance(end_date, str):
                            date_obj = datetime.strptime(end_date, '%Y-%m-%d')
                            pesan += f"📅 Tanggal Kembali: {date_obj.strftime('%d %B %Y')}\n"
                        else:
                            pesan += f"📅 Tanggal Kembali: {end_date.strftime('%d %B %Y')}\n"
                    except:
                        pesan += f"📅 Tanggal Kembali: {end_date}\n"
                
                pesan += f"⏱️ Durasi: {days} hari\n\n"
                
                # Detail pakaian yang dipesan
                pesan += f"👗 Pakaian yang Disewa ({len(reservations)} item):\n\n"
                
                for idx, reservation in enumerate(reservations, 1):
                    if isinstance(reservation, dict):
                        nama_pakaian = reservation.get("nama_pakaian", "-")
                        jenis = reservation.get("jenis", "-")
                        asal = reservation.get("asal", "-")
                        size = reservation.get("size", "-")
                        quantity = reservation.get("quantity", 1)
                        price_per_day = reservation.get("price_per_day", 0)
                        subtotal = reservation.get("total_price", 0)
                        
                        pesan += f"{idx}. {nama_pakaian}\n"
                        pesan += f"   🏷️ Jenis: {jenis} ({asal})\n"
                        pesan += f"   📏 Size: {size}\n"
                        pesan += f"   📦 Jumlah: {quantity} pcs\n"
                        pesan += f"   💰 Harga/hari: Rp {price_per_day:,.0f}\n"
                        pesan += f"   💵 Subtotal: Rp {subtotal:,.0f}\n\n"
                
                # Total keseluruhan
                pesan += f"💰 TOTAL PEMBAYARAN: Rp {grand_total:,.0f}"
                
                logger.info(f"Reservasi ditemukan: {order_id}, {len(reservations)} item, Total: Rp {grand_total:,.0f}")
            else:
                pesan = f"❌ Maaf, reservasi #{transaction_id} tidak ditemukan.\n"
                pesan += "Pastikan nomor order yang Anda masukkan benar."
                logger.warning(f"Reservasi tidak ditemukan: {transaction_id}")

            dispatcher.utter_message(text=pesan)

        except Error as e:
            logger.error(f"ActionCheckStatus Error: {e}")
            dispatcher.utter_message(
                text="Maaf, terjadi kesalahan saat mengecek status."
            )
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            dispatcher.utter_message(
                text="Maaf, terjadi kesalahan sistem."
            )
        finally:
            close_db_connection(connection, cursor)

        return [SlotSet("transaction_id", None)]